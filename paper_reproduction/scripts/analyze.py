"""Derive paper measurements from standalone extraction outputs and recorded depth.

Usage: python main.py analyze --dataset PATH [--recording NAME] [--output PATH]
Inputs: analysis/recordings/NAME artifacts from extract; original read-only MCAP.
Outputs: analysis/derived/recordings/NAME CSV/NPZ plus full-dataset tables only
         when all 288 extracted recordings are available. No logs or old caches.
"""

import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from . import analysis_math as math
from .storage import staging_directory
from .bag_io import image_array, read_messages, stamp
from .extract import (atomic_json, check_space, discover, extraction_identity, input_identity,
                      interior_mask, metric, recording_metadata, sha256)


def checked_extraction(path, source):
    """Validate source/output identities before reading any derived measurements."""
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest["extraction_identity"] != extraction_identity() or manifest["input_identity"] != input_identity(path):
        raise ValueError(f"Stale input extraction: {path.name}; rerun extract into a fresh --output")
    required = {"frames.csv", "pixels.npz", "samples.npz"}
    if set(manifest["output_sha256"]) != required:
        raise ValueError(f"Incomplete extraction manifest: {path.name}")
    for name in required:
        if sha256(source / name) != manifest["output_sha256"][name]:
            raise ValueError(f"Changed extraction output: {source / name}")
    frame = pd.read_csv(source / "frames.csv")
    if frame.accepted.dtype != bool or frame.timestamp_ns.duplicated().any():
        raise ValueError("Invalid acceptance flags or duplicate extracted timestamps")
    if len(frame) != manifest["bag_frames"] or int(frame.accepted.sum()) != manifest["frames"]:
        raise ValueError("Extracted population does not match its manifest")
    return manifest, frame


def boundary_analysis(accepted, pixels, samples):
    """Classify true internal colour transitions and retain all quality/sensitivity rows."""
    first = accepted.iloc[0]
    polygon = np.asarray(json.loads(first.polygon_xy), np.float32)
    np.testing.assert_array_equal(polygon, samples["first_polygon_xy"])
    transform = cv2.getPerspectiveTransform(polygon, np.array([[0, 0], [6, 0], [6, 6], [0, 6]], np.float32))
    inverse = np.linalg.inv(transform)
    u, v = pixels["cols"], pixels["rows"]
    points = cv2.perspectiveTransform(np.column_stack([u, v]).astype(np.float32).reshape(-1, 1, 2), transform).reshape(-1, 2)
    grid = math.marker_grid(int(first.selected_marker_id))
    distance = math.edge_distance(points, math.transitions(grid))
    gray = cv2.cvtColor(samples["first_rgb"], cv2.COLOR_BGR2GRAY)
    origin = samples["first_origin_uv"]
    centers = np.array([(col + .5, row + .5) for row in range(6) for col in range(6)], np.float32)
    projected = cv2.perspectiveTransform(centers.reshape(-1, 1, 2), inverse).reshape(-1, 2) - origin
    intensity = cv2.remap(gray, projected[:, 0].astype(np.float32).reshape(6, 6),
                          projected[:, 1].astype(np.float32).reshape(6, 6), cv2.INTER_LINEAR)
    black, white_level = float(np.median(intensity[~grid])), float(np.median(intensity[grid]))
    agreement = float(np.mean((intensity > (black + white_level) / 2) == grid))
    pitch = float(np.linalg.norm(np.roll(polygon, -1, axis=0) - polygon, axis=1).min() / 6)
    polygons = np.array([json.loads(value) for value in accepted.polygon_xy])
    displacement = np.sqrt(np.mean(np.sum((polygons - polygon)**2, axis=2), axis=1))
    motion = float(np.percentile(displacement, 95) / pitch)
    sd = pixels["temporal_sd_m"] * 1000
    coverage = pixels["count"] / int(pixels["evaluated_frames"])
    domain = ((points[:, 0] >= .3) & (points[:, 0] <= 5.7) & (points[:, 1] >= .3)
              & (points[:, 1] <= 5.7) & np.isfinite(sd))
    white = grid[np.clip(points[:, 1].astype(int), 0, 5), np.clip(points[:, 0].astype(int), 0, 5)]
    gradient = np.hypot(cv2.Sobel(gray.astype(float), cv2.CV_64F, 1, 0), cv2.Sobel(gray.astype(float), cv2.CV_64F, 0, 1))
    gradient = gradient[v - int(origin[1]), u - int(origin[0])]
    quality = dict(marker_id=int(first.selected_marker_id), cell_pitch_px=pitch,
                   template_cell_agreement=agreement, white_black_contrast=white_level - black,
                   corner_motion_p95_cells=motion, evaluated_frames=len(accepted))
    rows, profiles = [], []
    quality_ok = pitch >= 4 and agreement >= .85 and white_level - black >= 15 and motion <= .15
    for cutoff in (.9, .95, 1.):
        keep = domain & (coverage >= cutoff)
        for width in (.1, .15, .2):
            row = math.summarize_band(sd, distance, keep, white, coverage, width)
            row.update(quality, coverage_threshold=cutoff, edge_width_cells=width, alignment="nominal")
            row["primary_eligible"] = bool(quality_ok and row["edge_pixels"] >= 20 and row["interior_pixels"] >= 20
                                           and np.isfinite(row["edge_interior_ratio"]))
            row["gradient_sd_spearman"] = (float(spearmanr(gradient[keep], sd[keep]).statistic)
                if keep.sum() > 2 and np.std(gradient[keep]) > 0 and np.std(sd[keep]) > 0 else np.nan)
            rows.append(row)
    eligible = domain & (coverage >= .9)
    for dx, dy in ((-.5, 0), (.5, 0), (0, -.5), (0, .5)):
        shifted_distance = math.edge_distance(points + [dx / pitch, dy / pitch], math.transitions(grid))
        row = math.summarize_band(sd, shifted_distance, eligible, white, coverage, .15)
        row.update(quality, coverage_threshold=.9, edge_width_cells=.15,
                   alignment=f"shift_{dx}_{dy}", primary_eligible=False)
        rows.append(row)
    for lo, hi in zip(math.BINS[:-1], math.BINS[1:]):
        keep = eligible & (distance >= lo) & (distance < hi)
        profiles.append(dict(**quality, distance_low_cells=lo, distance_high_cells=hi, pixels=int(keep.sum()),
                             median_sd_mm=float(np.median(sd[keep])) if keep.any() else np.nan,
                             rms_sd_mm=float(np.sqrt(np.mean(sd[keep]**2))) if keep.any() else np.nan))
    arrays = dict(rows=v, cols=u, marker_points=points, distance_cells=distance,
                  white=white, domain=domain, eligible=eligible, coverage=coverage, temporal_sd_mm=sd)
    return pd.DataFrame(rows), pd.DataFrame(profiles), arrays


def stream_geometry(path, accepted, pixels, samples, staging):
    """Fit planes and row/column profiles in one accepted-depth pass, without RGB redetection."""
    polygons = [np.array(json.loads(value), np.int32) for value in accepted.polygon_xy]
    all_points = np.concatenate(polygons)
    low, high = all_points.min(axis=0), all_points.max(axis=0)
    row_pixels, column_pixels = np.arange(low[1], high[1] + 1), np.arange(low[0], high[0] + 1)
    positions = [math.coordinates(row_pixels), math.coordinates(column_pixels)]
    complete = pixels["count"] == len(accepted)
    if complete.sum() < 3:
        raise ValueError("Fewer than three complete-valid pixels for profile sensitivity analysis")
    fixed = np.zeros((len(row_pixels), len(column_pixels)), bool)
    fixed[pixels["rows"][complete] - low[1], pixels["cols"][complete] - low[0]] = True
    cached = {f"{support}_{axis}_mm": np.full((len(accepted), len(pos)), np.nan)
              for support in ("roi", "fixed_interior") for axis, pos in zip(("vertical", "horizontal"), positions)}
    lookup = {int(row.timestamp_ns): (i, row, polygon) for i, (row, polygon) in
              enumerate(zip(accepted.itertuples(), polygons))}
    k = samples["camera_info_k"]
    seen, planes, profiles, status = set(), [], [], {}
    for topic, message in read_messages(path, status):
        if topic == "/rgb_image" and stamp(message) == int(accepted.iloc[0].timestamp_ns):
            # The printed-boundary figure uses the original wider context crop.
            polygon = polygons[0]
            rgb = image_array(message)
            pad = max(12, int(np.ceil(.25 * np.ptp(polygon, axis=0).max())))
            origin = np.maximum(polygon.min(axis=0) - pad, 0)
            end = np.minimum(polygon.max(axis=0) + pad + 1, [rgb.shape[1], rgb.shape[0]])
            np.savez_compressed(staging / "boundary_reference.npz",
                rgb=rgb[origin[1]:end[1], origin[0]:end[0]], origin_uv=origin, polygon_xy=polygon,
                timestamp_ns=np.int64(stamp(message)), marker_id=np.int64(accepted.iloc[0].selected_marker_id))
        if topic != "/depth_image" or stamp(message) not in lookup:
            continue
        timestamp = stamp(message)
        if timestamp in seen:
            raise ValueError("Duplicate accepted depth timestamp")
        seen.add(timestamp)
        i, row, polygon = lookup[timestamp]
        depth = image_array(message)
        if depth.shape != (row.height, row.width):
            raise ValueError("Depth dimensions differ from extraction")
        mask = np.zeros(depth.shape, np.uint8)
        cv2.fillPoly(mask, [polygon], 1)
        valid = (mask > 0) & np.isfinite(depth) & (depth > 0)
        reproduced = metric(depth[valid], row.distance_m, row.offset_m)
        if reproduced["valid_count"] != row.valid_count:
            raise ValueError("Accepted valid-depth population changed")
        np.testing.assert_allclose([reproduced[key] for key in ("bias_m", "rmse_m", "spatial_var_m2")],
                                   [row.bias_m, row.rmse_m, row.spatial_var_m2], atol=2e-13, rtol=1e-9)
        v, u = np.nonzero(valid)
        z = depth[v, u]
        x, y = (u - k[0, 2]) * z / k[0, 0], (v - k[1, 2]) * z / k[1, 1]
        fit = math.fit_plane(x, y, z)
        planes.append(dict(frame=int(row.frame), timestamp_ns=timestamp, pixels=len(z), **fit))
        inside = interior_mask(mask, polygon)
        if not np.all(inside[pixels["rows"][complete], pixels["cols"][complete]]
                      & valid[pixels["rows"][complete], pixels["cols"][complete]]):
            raise ValueError("Complete-valid support no longer belongs to the accepted interior")
        crop = (slice(low[1], high[1] + 1), slice(low[0], high[0] + 1))
        error = (depth[crop] + row.offset_m - row.distance_m) * 1000
        for support, support_mask in (("roi", valid[crop]), ("fixed_interior", fixed)):
            for axis, position, profile in zip(("vertical", "horizontal"), positions,
                                                math.profiles(np.where(support_mask, error, np.nan))):
                cached[f"{support}_{axis}_mm"][i] = profile
                profiles.append(dict(frame=int(row.frame), timestamp_ns=timestamp, support=support,
                                     axis=axis, **math.fit_profile(position, profile)))
        if row.frame == 150 and "frame150_depth_m" in samples:
            if timestamp != int(samples["frame150_timestamp_ns"]):
                raise ValueError("Paper example timestamp differs from accepted frame 150")
            predicted = fit["a"] * x + fit["b"] * y + fit["c"]
            origin = samples["frame150_origin_uv"]
            shape = samples["frame150_depth_m"].shape
            heat = np.full(shape, np.nan)
            heat[v - origin[1], u - origin[0]] = (z - predicted) * 1000
            np.savez_compressed(staging / "residual_map.npz", residual_mm=heat,
                roi_mask=(mask > 0)[origin[1]:origin[1] + shape[0], origin[0]:origin[0] + shape[1]],
                polygon_xy=polygon, origin_uv=origin, frame=np.int64(150), timestamp_ns=np.int64(timestamp),
                a=fit["a"], b=fit["b"], c=fit["c"])
            if row.distance_m == 1.8 and row.camera in ("rsf", "zedxm"):
                colours = samples["frame150_rgb"][v - origin[1], u - origin[0], :3][:, ::-1] / 255.
                np.savez_compressed(staging / "pointcloud.npz", x_mm=x * 1000, y_mm=y * 1000,
                                    z_reference_mm=(z + row.offset_m) * 1000, rgb=colours,
                                    frame=np.int64(150), timestamp_ns=np.int64(timestamp))
    if seen != set(lookup):
        raise ValueError(f"Missing {len(set(lookup) - seen)} accepted depth frames")
    np.savez_compressed(staging / "profiles.npz", frame=accepted.frame.to_numpy(np.int64),
                        timestamp_ns=accepted.timestamp_ns.to_numpy(np.int64), row_pixels=row_pixels,
                        column_pixels=column_pixels, vertical_x=positions[0], horizontal_x=positions[1], **cached)
    return pd.DataFrame(planes), pd.DataFrame(profiles), cached, positions, status


def profile_summary(table, cached, positions):
    """Distinguish mean frame fits from a fit of the mean profile on each support."""
    result = {}
    for (support, axis), group in table.groupby(["support", "axis"]):
        prefix = f"{support}_{axis}_"
        for metric in ("offset_mm", "gradient_mm", "bow_mm", "irregular_rms_mm"):
            values = group[metric].to_numpy()
            result[prefix + "mean_" + metric] = float(values.mean())
            result[prefix + "temporal_sd_" + metric] = float(values.std(ddof=0))
            if metric in ("gradient_mm", "bow_mm"):
                result[prefix + "positive_fraction_" + metric] = float(np.mean(values > 0))
                result[prefix + "same_sign_fraction_" + metric] = float(np.mean(values * values.mean() > 0))
        profiles = cached[f"{support}_{axis}_mm"]
        occupied = np.isfinite(profiles).any(axis=0)
        fit = math.fit_profile(positions[0 if axis == "vertical" else 1][occupied],
                               np.nanmean(profiles[:, occupied], axis=0))
        result.update({prefix + "mean_profile_" + key: value for key, value in fit.items()})
    return result


def analyze_recording(path, source, derived, seed, identity):
    """Publish one complete, fingerprinted analysis; resume only identical inputs."""
    manifest, frames = checked_extraction(path, source)
    fingerprint = dict(extraction_manifest_sha256=sha256(source / "manifest.json"), identity=identity, seed=seed)
    destination = derived / "recordings" / path.name
    if destination.exists():
        checkpoint = json.loads((destination / "manifest.json").read_text())
        if checkpoint["fingerprint"] != fingerprint:
            raise ValueError(f"Stale derived analysis: {path.name}; use a fresh analysis root")
        for name, digest in checkpoint["output_sha256"].items():
            if sha256(destination / name) != digest:
                raise ValueError(f"Modified derived artifact: {destination / name}")
        return checkpoint["summary"], True
    accepted = frames[frames.accepted].sort_values("frame").copy()
    with np.load(source / "pixels.npz", allow_pickle=False) as cache:
        pixels = {key: cache[key] for key in cache.files}
    with np.load(source / "samples.npz", allow_pickle=False) as cache:
        samples = {key: cache[key] for key in cache.files}
    if int(pixels["evaluated_frames"]) != len(accepted):
        raise ValueError("Temporal denominator differs from accepted population")
    check_space(derived, 1)
    with staging_directory(prefix=".analyze-", dir=derived / "recordings") as temporary:
        staging = Path(temporary)
        planes, profiles, cached, positions, status = stream_geometry(path, accepted, pixels, samples, staging)
        planes.to_csv(staging / "planes.csv", index=False)
        accepted["plane_residual_sd_m"] = np.sqrt(planes.residual_var_m2.to_numpy())
        summary, bootstrap = math.recording_summary(accepted, seed)
        summary.update(recording_metadata(path.name), bag_frames=manifest["bag_frames"],
                       excluded_frames=manifest["excluded_frames"], partial_recording=manifest["partial_recording"],
                       unavailable_pairs=manifest["unavailable_pairs"], pixel_temporal_rms_m=manifest["pixel_temporal_rms_m"],
                       complete_pixel_temporal_rms_m=float(np.sqrt(np.mean(pixels["temporal_sd_m"][pixels["count"] == len(accepted)]**2))))
        angles, normals = math.frame_geometry(planes.a, planes.b)
        normal = normals.mean(axis=0)
        normal /= np.linalg.norm(normal)
        geometry = dict(S_mm=summary["spatial_sd_m"] * 1000, S_pl_mm=summary["plane_residual_sd_m"] * 1000,
                        theta_h_deg=float(np.median(angles[:, 0])), theta_v_deg=float(np.median(angles[:, 1])),
                        normal_x=float(normal[0]), normal_y=float(normal[1]), normal_z=float(normal[2]),
                        reduction_pct=100 * (1 - summary["plane_residual_sd_m"] / summary["spatial_sd_m"]) if summary["spatial_sd_m"] else 0.)
        summary.update(geometry)
        np.savez_compressed(staging / "bootstrap.npz", estimates=bootstrap, metrics=np.array(math.METRICS))
        boundaries, distances, boundary_pixels = boundary_analysis(accepted, pixels, samples)
        boundaries.to_csv(staging / "boundary_metrics.csv", index=False)
        distances.to_csv(staging / "boundary_distance_profiles.csv", index=False)
        np.savez_compressed(staging / "boundary_pixels.npz", **boundary_pixels)
        if manifest["input_identity"] != input_identity(path):
            raise ValueError("Raw input changed during analysis")
        checkpoint = dict(fingerprint=fingerprint, summary=summary,
                          profile_summary=profile_summary(profiles, cached, positions), reader=status,
                          output_sha256={p.name: sha256(p) for p in sorted(staging.iterdir())})
        atomic_json(staging / "manifest.json", checkpoint)
        staging.rename(destination)
    return summary, False


def analyze_dataset(dataset, output, recording=None):
    """Keep focused analyses separate from the all-recording table export."""
    dataset, output = dataset.expanduser().resolve(), output.expanduser().resolve()
    if output.is_relative_to(dataset) or dataset.is_relative_to(output):
        raise ValueError("Analysis output and dataset must be separate directory trees")
    records = discover(dataset)
    # Seed identity must not depend on which downloads have finished so far.
    configurations = [(camera, "stereo") for camera in ("rsi", "rsf")] + [
        (camera, mode) for camera in ("zedx", "zedxm") for mode in ("neural", "neural_light", "neural_plus")]
    design = sorted(f"{light}/{distance:04d}/{camera}_{distance:04d}_{res}"
        + ("" if mode == "stereo" else "_" + mode) + "_" + light
        for camera, mode in configurations for distance in (400, 600, 800, 1000, 1400, 1800, 2200, 2600, 3000)
        for res in ("hd", "sd") for light in ("natural", "artificial"))
    indices = {Path(path).name: index for index, path in enumerate(design)}
    selected = [(indices[row["recording"]], row) for row in records if recording is None or row["recording"] == recording]
    if not selected:
        raise ValueError(f"Recording not found: {recording}")
    if recording is None and len(records) != 288:
        raise ValueError("Full analysis requires the 288-recording design")
    missing = [row["recording"] for _, row in selected if not (output / "recordings" / row["recording"] / "manifest.json").is_file()]
    if missing:
        raise ValueError(f"Missing extraction for {len(missing)} recording(s), starting with {missing[0]}; run extract first")
    derived = output / "derived"
    (derived / "recordings").mkdir(parents=True, exist_ok=True)
    budget = check_space(derived, len(selected))
    here = Path(__file__).resolve().parent
    identity = dict(source_sha256={p.name: sha256(p) for p in [Path(__file__), here / "analysis_math.py", here / "analysis_tables.py"]},
                    extraction=extraction_identity())
    progress = dict(selection=recording, status="in_progress", selected_recordings=len(selected),
                    output_budget_bytes=budget, completed=[])
    atomic_json(derived / "analysis.json", progress)
    cv2.setNumThreads(1)
    try:
        for number, (index, record) in enumerate(selected, 1):
            name = record["recording"]
            print(f"[{number}/{len(selected)}] Analyze {name}", flush=True)
            summary, reused = analyze_recording(dataset / record["bag_path"], output / "recordings" / name,
                                                derived, 20261012 + index, identity)
            progress["completed"].append(dict(recording=name, reused=reused, frames=summary["frames"]))
            atomic_json(derived / "analysis.json", progress)
            print(f"  {'Reused' if reused else 'Analyzed'}: {summary['frames']} accepted frames", flush=True)
        from .analysis_tables import coverage_inventory, export_tables
        atomic_json(derived / "coverage.json", coverage_inventory())
        if recording is None:
            export_tables(output, records)
        progress["status"] = "complete" if recording is None else "focused_complete"
        atomic_json(derived / "analysis.json", progress)
    except Exception as error:
        progress.update(status="failed", error=f"{type(error).__name__}: {error}")
        atomic_json(derived / "analysis.json", progress)
        raise
