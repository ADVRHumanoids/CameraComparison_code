"""Extract compact, log-free measurements from the paper's archived ROS 2 bags.

Usage: python main.py extract --dataset PATH [--recording NAME] [--output PATH]
Inputs: recording directory names, metadata.yaml, RGB/depth, CameraInfo and TF.
Outputs: inventory.csv, extraction.json, recordings/NAME/{frames.csv,pixels.npz,
         samples.npz,manifest.json}; SI units unless indicated by a column suffix.
Adapted from the repository's numerical reconstruction. Uses no old outputs/logs.
"""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import shutil

import cv2
import numpy as np
import pandas as pd

from .bag_io import PARTIAL_RECORDING, image_array, paired_frames, read_messages, stamp
from .storage import staging_directory


NAME = re.compile(r"(rsi|rsf|zedx|zedxm)_(\d{4})_(hd|sd)(?:_(neural(?:_light|_plus)?))?_(natural|artificial)")
DISTANCES = {400, 600, 800, 1000, 1400, 1800, 2200, 2600, 3000}
PACKAGES = ("numpy", "pandas", "opencv-contrib-python-headless", "rosbags", "scipy", "mcap", "lz4", "zstandard")
RESERVE_BYTES = 512 * 1024**2


def sha256(path):
    """Hash small code/metadata/output files, without rereading multi-GB bags."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_json(path, value):
    """Publish progress only after the complete JSON has been written."""
    temporary = path.with_suffix(".json.part")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def recording_metadata(name):
    """Derive nominal distance and configuration from the acquisition identifier."""
    match = NAME.fullmatch(name)
    if not match:
        raise ValueError(f"Invalid recording name: {name}")
    camera, distance, resolution, mode, light = match.groups()
    if int(distance) not in DISTANCES or (camera.startswith("zed") != (mode is not None)):
        raise ValueError(f"Invalid paper configuration: {name}")
    return dict(recording=name, camera=camera, distance_m=int(distance) / 1000,
                resolution=resolution, mode=mode or "stereo", lighting=light)


def discover(dataset):
    """Inventory only bag manifests, rejecting duplicate or misplaced identities."""
    records, names = [], set()
    for manifest in sorted(dataset.rglob("metadata.yaml")):
        if any(part.startswith(".") for part in manifest.relative_to(dataset).parts):
            continue  # Streaming downloads publish only after their hidden staging is verified.
        path = manifest.parent
        metadata = recording_metadata(path.name)
        expected = Path(metadata["lighting"]) / f"{int(round(metadata['distance_m'] * 1000)):04d}" / path.name
        if path.relative_to(dataset) != expected or path.name in names:
            raise ValueError(f"Duplicate or misplaced recording: {path}")
        files = sorted(path.glob("*.mcap"))
        if not files:
            raise ValueError(f"Recording has no MCAP files: {path}")
        names.add(path.name)
        records.append(dict(**metadata, bag_path=str(expected), mcap_files=len(files),
                            bag_bytes=sum(p.stat().st_size for p in files)))
    if not records:
        raise ValueError(f"No recording manifests found under {dataset}")
    return records


def select_target(rgb, detector, locked_id):
    """Accept exactly one eligible marker and keep its first unambiguous ID."""
    corners, ids, _ = detector.detectMarkers(rgb)
    detected = [] if ids is None else [int(value) for value in ids.ravel()]
    eligible = [index for index, value in enumerate(detected) if value in (0, 3)]
    if not eligible:
        return None, None, locked_id, detected, None, "no_eligible_target"
    if len(eligible) != 1:
        return None, None, locked_id, detected, None, "ambiguous_eligible_targets"
    index = eligible[0]
    selected = detected[index]
    locked_id = selected if locked_id is None else locked_id
    if selected != locked_id:
        return None, None, locked_id, detected, selected, "marker_id_changed"
    polygon = corners[index][0].astype(np.int32)
    mask = np.zeros(rgb.shape[:2], np.uint8)
    cv2.fillPoly(mask, [polygon], 1)
    return mask.astype(bool), polygon, locked_id, detected, selected, "accepted"


def interior_mask(mask, polygon):
    """Erode by 5% of the shortest integer-corner side, rounded up to one pixel."""
    radius = max(1, int(np.ceil(.05 * np.linalg.norm(np.roll(polygon, -1, axis=0) - polygon, axis=1).min())))
    return cv2.erode(mask.astype(np.uint8), np.ones((2 * radius + 1, 2 * radius + 1), np.uint8)).astype(bool)


def metric(values, ground_truth, offset):
    """Use the same positive finite optical depths for all population moments."""
    valid = values[np.isfinite(values) & (values > 0)] + offset
    if not len(valid):
        return dict(valid_count=0, bias_m=np.nan, rmse_m=np.nan, spatial_var_m2=np.nan)
    errors = valid - ground_truth
    return dict(valid_count=len(valid), mean_depth_m=float(valid.mean()), bias_m=float(errors.mean()),
                rmse_m=float(np.sqrt(np.mean(errors**2))), spatial_var_m2=float(valid.var()),
                positive_fraction=float(np.mean(errors > 0)), negative_fraction=float(np.mean(errors < 0)),
                positive_contribution_m=float(np.maximum(errors, 0).mean()),
                negative_contribution_m=float(np.minimum(errors, 0).mean()))


class TemporalPixels:
    """Accumulate population moments at fixed pixels using accepted frames only."""

    def __init__(self, inside):
        self.rows, self.cols = np.nonzero(inside)
        self.count = np.zeros(len(self.rows), np.int64)
        self.mean = np.zeros(len(self.rows), np.float64)
        self.m2 = np.zeros(len(self.rows), np.float64)
        self.frames = 0

    def update(self, depth, inside):
        """Welford updates avoid storing depth videos or losing precision."""
        values = depth[self.rows, self.cols]
        valid = np.isfinite(values) & (values > 0) & inside[self.rows, self.cols]
        self.frames += 1
        self.count[valid] += 1
        delta = values[valid] - self.mean[valid]
        self.mean[valid] += delta / self.count[valid]
        self.m2[valid] += delta * (values[valid] - self.mean[valid])
        return float(inside[self.rows, self.cols].mean())

    def arrays(self):
        """Keep counts and coordinates so later analyses can select their support."""
        variance = np.divide(self.m2, self.count, out=np.full(len(self.count), np.nan), where=self.count >= 2)
        return dict(rows=self.rows, cols=self.cols, count=self.count, mean_depth_m=self.mean,
                    temporal_sd_m=np.sqrt(np.maximum(variance, 0)), evaluated_frames=np.int64(self.frames))


def input_identity(path):
    """Record metadata SHA-256 and raw sizes/mtimes without a second bag pass."""
    return dict(metadata_sha256=sha256(path / "metadata.yaml"), raw_files=[
        dict(name=p.name, bytes=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns) for p in sorted(path.glob("*.mcap"))])


def extraction_identity():
    """Invalidate checkpoints when extraction code, dependencies or rules change."""
    here = Path(__file__).resolve().parent
    return dict(source_sha256={p.name: sha256(p) for p in [Path(__file__), here / "bag_io.py"]},
                versions={name: importlib.metadata.version(name) for name in PACKAGES},
                marker_ids=[0, 3], mean_error_cutoff_m=.3, temporal_coverage=.9)


def check_space(output, recordings):
    """Budget compact outputs before starting, retaining a 1 GiB free margin."""
    # The verified complete extraction/analysis currently occupies under 400 MB.
    needed = recordings * 2 * 1024**2
    if shutil.disk_usage(output).free < needed + RESERVE_BYTES:
        raise RuntimeError(f"Insufficient output space: need {needed} bytes plus a 512 MiB reserve")
    return needed


def extract_recording(path, output, identity):
    """Stream one recording and commit its artifacts together after validation."""
    metadata = recording_metadata(path.name)
    raw_identity = input_identity(path)
    destination = output / "recordings" / path.name
    if destination.exists():
        manifest = json.loads((destination / "manifest.json").read_text())
        if manifest["extraction_identity"] != identity or manifest["input_identity"] != raw_identity:
            raise ValueError(f"Stale extraction for {path.name}; use a fresh --output directory")
        if any(sha256(destination / name) != digest for name, digest in manifest["output_sha256"].items()):
            raise ValueError(f"Changed output for {path.name}; use a fresh --output directory")
        return manifest, True

    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250),
                                     cv2.aruco.DetectorParameters())
    rows, samples, status = [], {}, {}
    locked_id, temporal, dimensions = None, None, None
    for rgb_message, depth_message, info, matrix in paired_frames(read_messages(path, status), status):
        rgb, depth = image_array(rgb_message), image_array(depth_message)
        if depth_message.encoding not in ("16UC1", "32FC1") or depth.ndim != 2 or rgb.shape[:2] != depth.shape:
            raise ValueError("Unsupported depth or differing RGB/depth dimensions")
        if dimensions is not None and dimensions != depth.shape:
            raise ValueError("Image dimensions changed within recording")
        dimensions = depth.shape
        index = len(rows)
        if index >= 300:
            raise ValueError("More than 300 evaluated image pairs")
        row = dict(**metadata, frame=index, timestamp_ns=stamp(depth_message), rgb_timestamp_ns=stamp(rgb_message),
                   width=depth.shape[1], height=depth.shape[0], encoding=depth_message.encoding,
                   optical_frame=depth_message.header.frame_id, accepted=False, roi_detected=False,
                   selected_marker_id=None, mask_count=0, valid_count=0)
        mask, polygon, locked_id, detected, selected, reason = select_target(rgb, detector, locked_id)
        row.update(detected_ids=json.dumps(detected), selected_marker_id=selected, exclusion_reason=reason)
        if mask is None:
            rows.append(row)
            continue
        offset = float(matrix[2, 3])
        row.update(roi_detected=True, polygon_xy=json.dumps(polygon.tolist()), offset_m=offset,
                   rotation_from_reference_deg=float(np.degrees(np.arccos(np.clip(matrix[2, 2], -1, 1)))),
                   mask_count=int(mask.sum()), **metric(depth[mask], metadata["distance_m"], offset))
        row["invalid_pixels"] = row["mask_count"] - row["valid_count"]
        row["valid_fraction"] = row["valid_count"] / row["mask_count"]
        if row["valid_count"] == 0:
            row["exclusion_reason"] = "no_valid_depth"
        elif abs(row["bias_m"]) > .3:
            row["exclusion_reason"] = "mean_error_gt_0.3m"
        else:
            row["accepted"] = True
            inside = interior_mask(mask, polygon)
            if temporal is None:
                if not inside.any():
                    raise ValueError("First accepted target has an empty eroded interior")
                temporal = TemporalPixels(inside)
                samples.update(first_polygon_xy=polygon, first_timestamp_ns=np.int64(row["timestamp_ns"]),
                               first_frame=np.int64(index), first_marker_id=np.int64(selected),
                               camera_info_k=np.asarray(info.k).reshape(3, 3), reference_transform=matrix)
                low = np.maximum(polygon.min(axis=0) - 12, 0)
                high = np.minimum(polygon.max(axis=0) + 13, [depth.shape[1], depth.shape[0]])
                samples.update(first_rgb=rgb[low[1]:high[1], low[0]:high[0]].copy(), first_origin_uv=low)
            row["fixed_interior_overlap_fraction"] = temporal.update(depth, inside)
            row.update({"interior_" + k: v for k, v in metric(depth[inside], metadata["distance_m"], offset).items()})
            row["interior_mask_count"] = int(inside.sum())
            # Only the twelve paper-required frame-150 crops need raw pixel storage.
            if (index == 150 and metadata["resolution"] == "hd" and metadata["lighting"] == "natural"
                    and metadata["distance_m"] in (1., 1.8, 3.) and metadata["mode"] in ("stereo", "neural_plus")):
                low = np.maximum(polygon.min(axis=0), 0)
                high = np.minimum(polygon.max(axis=0) + 1, [depth.shape[1], depth.shape[0]])
                bounds = (slice(low[1], high[1]), slice(low[0], high[0]))
                samples.update(frame150_depth_m=depth[bounds].copy(), frame150_rgb=rgb[bounds].copy(),
                               frame150_origin_uv=low, frame150_polygon_xy=polygon,
                               frame150_timestamp_ns=np.int64(row["timestamp_ns"]), frame150_offset_m=np.float64(offset))
        rows.append(row)
    partial = path.name == PARTIAL_RECORDING
    expected = 155 if partial else 300
    if len(rows) != expected or (not partial and status.get("reader_error")):
        raise ValueError(f"{path.name}: expected {expected} pairs, found {len(rows)}; {status}")
    if temporal is None:
        raise ValueError(f"No accepted target frames in {path.name}")
    if raw_identity != input_identity(path):
        raise ValueError("Input recording changed during extraction")
    arrays = temporal.arrays()
    eligible = (arrays["count"] >= max(2, int(np.ceil(.9 * temporal.frames)))) & np.isfinite(arrays["temporal_sd_m"])
    if not eligible.any():
        raise ValueError("No fixed pixels meet 90% temporal coverage")
    manifest = dict(**metadata, bag_frames=len(rows), frames=temporal.frames,
                    excluded_frames=len(rows) - temporal.frames, locked_marker_id=locked_id,
                    expected_frames=300, unavailable_pairs=300 - len(rows), partial_recording=partial,
                    temporal_pixels_90pct=int(eligible.sum()), complete_pixels=int((temporal.count == temporal.frames).sum()),
                    pixel_temporal_rms_m=float(np.sqrt(np.mean(arrays["temporal_sd_m"][eligible]**2))),
                    input_identity=raw_identity, extraction_identity=identity, **status)
    check_space(output, 1)
    with staging_directory(prefix=".extract-", dir=output / "recordings") as temporary:
        staging = Path(temporary)
        pd.DataFrame(rows).to_csv(staging / "frames.csv", index=False)
        np.savez_compressed(staging / "pixels.npz", **arrays)
        np.savez_compressed(staging / "samples.npz", **samples)
        manifest["output_sha256"] = {p.name: sha256(p) for p in sorted(staging.iterdir())}
        atomic_json(staging / "manifest.json", manifest)
        staging.rename(destination)
    return manifest, False


def extract_dataset(dataset, output, recording=None):
    """Inventory inputs, check storage and resume verified per-recording outputs."""
    dataset, output = dataset.expanduser().resolve(), output.expanduser().resolve()
    if not dataset.is_dir():
        raise ValueError(f"Dataset directory does not exist: {dataset}")
    if output.is_relative_to(dataset) or dataset.is_relative_to(output):
        raise ValueError("Analysis output and dataset must be separate directory trees")
    records = discover(dataset)
    if recording is not None and recording not in {r["recording"] for r in records}:
        raise ValueError(f"Recording not found: {recording}")
    if recording is None and len(records) != 288:
        raise ValueError("Full extraction requires 288 recordings; use --recording for a focused run")
    selected = [r for r in records if recording is None or r["recording"] == recording]
    output.mkdir(parents=True, exist_ok=True)
    (output / "recordings").mkdir(exist_ok=True)
    budget = check_space(output, len(selected))
    identity = extraction_identity()
    cv2.setNumThreads(1)
    inventory = output / "inventory.csv"
    temporary_inventory = inventory.with_suffix(".csv.part")
    pd.DataFrame(records).to_csv(temporary_inventory, index=False)
    temporary_inventory.replace(inventory)
    progress = dict(dataset=str(dataset), inventory_recordings=len(records), selected_recordings=len(selected),
                    selection=recording, output_budget_bytes=budget, status="in_progress", completed=[])
    atomic_json(output / "extraction.json", progress)
    try:
        for index, record in enumerate(selected, 1):
            print(f"[{index}/{len(selected)}] {record['recording']}", flush=True)
            manifest, reused = extract_recording(dataset / record["bag_path"], output, identity)
            progress["completed"].append(dict(recording=record["recording"], frames=manifest["frames"],
                                              bag_frames=manifest["bag_frames"], reused=reused,
                                              partial_recording=manifest["partial_recording"]))
            atomic_json(output / "extraction.json", progress)
            print(f"  {'Reused' if reused else 'Extracted'}: {manifest['frames']}/{manifest['bag_frames']} accepted", flush=True)
        progress["status"] = "complete" if recording is None else "focused_complete"
        atomic_json(output / "extraction.json", progress)
    except Exception as error:
        progress.update(status="failed", error=f"{type(error).__name__}: {error}")
        atomic_json(output / "extraction.json", progress)
        raise
