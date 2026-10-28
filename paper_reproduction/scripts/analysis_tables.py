"""Export full-dataset numerical tables and the computed-paper coverage inventory.

Called by: main.py analyze after all selected recordings finish.
Inputs: standalone extraction and derived CSV/NPZ/JSON; no raw bags or logs.
Outputs: analysis/derived/tables/ CSV/NPZ and a checksum manifest. Rendering is
         deferred to step 4; matched modes are separate acquisitions, not frame pairs.
"""

from itertools import combinations, product
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .analysis_math import METRICS, frame_geometry, normal_angle
from .storage import staging_directory
from .extract import atomic_json, recording_metadata, sha256


KEYS = ["recording", "camera", "mode", "resolution", "lighting", "distance_m"]
MODES = ["neural_light", "neural", "neural_plus"]
SCALARS = [*METRICS, "pixel_temporal_rms_m", "plane_residual_sd_m"]


def contrasts(summary, samples, keys, field, pairs):
    """Subtract independently recorded conditions without pairing their frame indices."""
    rows = []
    for values, group in summary.groupby(keys):
        for left, right in pairs:
            a, b = group[group[field] == left], group[group[field] == right]
            if len(a) != 1 or len(b) != 1:
                raise ValueError(f"Incomplete or duplicate matched comparison: {values}, {left}/{right}")
            a, b = a.iloc[0], b.iloc[0]
            row = dict(zip(keys, values if isinstance(values, tuple) else (values,)))
            row.update(left=left, right=right, left_recording=a.recording, right_recording=b.recording,
                       left_frames=int(a.frames), right_frames=int(b.frames),
                       partial_images=bool(a.partial_recording or b.partial_recording),
                       interval_reliable=bool(a.interval_reliable and b.interval_reliable
                                              and not a.partial_recording and not b.partial_recording))
            for metric in SCALARS:
                row[metric + "_difference"] = float(a[metric] - b[metric])
            for index, metric in enumerate(METRICS):
                difference = samples[a.recording][:, index] - samples[b.recording][:, index]
                row[metric + "_lo"], row[metric + "_hi"] = np.quantile(difference, [.025, .975])
            rows.append(row)
    return pd.DataFrame(rows)


def invalid_extrema(frames):
    """For affected frames only, pair count extrema with that exact frame's ROI percentage."""
    rows = []
    for name, group in frames[frames.accepted & (frames.invalid_pixels > 0)].groupby("recording"):
        group = group.sort_values("frame")
        row = dict(recording=name, affected_frames=len(group), count_mean=float(group.invalid_pixels.mean()),
                   percent_mean=float((100 * group.invalid_pixels / group.mask_count).mean()))
        for label, index in (("min", group.invalid_pixels.idxmin()), ("max", group.invalid_pixels.idxmax())):
            selected = group.loc[index]
            row.update({f"count_{label}": int(selected.invalid_pixels), f"frame_{label}": int(selected.frame),
                        f"percent_at_count_{label}": float(100 * selected.invalid_pixels / selected.mask_count)})
        rows.append(row)
    return pd.DataFrame(rows, columns=["recording", "affected_frames", "count_mean", "percent_mean",
                                      "count_min", "frame_min", "percent_at_count_min", "count_max",
                                      "frame_max", "percent_at_count_max"])


def envelopes(summary):
    """Preserve equal recording weights across the four resolution/light configurations."""
    rows = []
    for (camera, mode, distance), group in summary.groupby(["camera", "mode", "distance_m"]):
        if len(group) != 4 or set(zip(group.resolution, group.lighting)) != set(product(("hd", "sd"), ("natural", "artificial"))):
            raise ValueError("Configuration envelope requires exactly four distinct conditions")
        for metric in ("absolute_bias_m", "spatial_sd_m", "rmse_m", "pixel_temporal_rms_m"):
            values = group[metric].to_numpy() * 1000
            rows.append(dict(camera=camera, mode=mode, distance_m=distance, metric=metric,
                             min_mm=values.min(), median_mm=np.median(values), max_mm=values.max(),
                             configurations=4, min_frames=int(group.frames.min()), max_frames=int(group.frames.max())))
    return pd.DataFrame(rows)


def mode_separations(summary, normals):
    """Compare +Z-oriented representative normals and all cross-acquisition frame normals."""
    rows = []
    keys = ["camera", "distance_m", "lighting", "resolution"]
    for values, group in summary[summary.camera.str.startswith("zed")].groupby(keys):
        group = group.set_index("mode")
        if set(group.index) != set(MODES) or len(group) != 3:
            raise ValueError("Orientation diagnostic requires three distinct modes")
        for left, right in combinations(MODES, 2):
            a, b = group.loc[left], group.loc[right]
            angle = np.degrees(np.arccos(np.clip(normals[a.recording] @ normals[b.recording].T, -1, 1)))
            row = dict(zip(keys, values))
            row.update(mode_a=left, mode_b=right, recording_a=a.recording, recording_b=b.recording,
                       frames_a=int(a.frames), frames_b=int(b.frames),
                       normal_separation_deg=normal_angle(a[["normal_x", "normal_y", "normal_z"]].to_numpy(float),
                                                         b[["normal_x", "normal_y", "normal_z"]].to_numpy(float)),
                       delta_theta_h_deg=b.theta_h_deg - a.theta_h_deg,
                       delta_theta_v_deg=b.theta_v_deg - a.theta_v_deg,
                       cross_frame_median_separation_deg=float(np.median(angle)),
                       cross_frame_p05_separation_deg=float(np.quantile(angle, .05)),
                       cross_frame_p95_separation_deg=float(np.quantile(angle, .95)))
            rows.append(row)
    return pd.DataFrame(rows)


def profile_groups(records, grouping):
    """Retain bowing sign persistence, magnitude and fixed-support sensitivity separately."""
    rows = []
    for values, group in records.groupby(grouping):
        for support, axis in product(("roi", "fixed_interior"), ("vertical", "horizontal")):
            prefix = f"{support}_{axis}_"
            row = dict(zip(grouping, values if isinstance(values, tuple) else (values,)))
            row.update(support=support, axis=axis, recordings=len(group))
            for metric in ("offset_mm", "gradient_mm", "bow_mm", "irregular_rms_mm"):
                series = group[prefix + "mean_" + metric]
                row["median_mean_" + metric] = float(series.median())
                row["median_abs_mean_" + metric] = float(series.abs().median())
                row["q25_mean_" + metric], row["q75_mean_" + metric] = series.quantile([.25, .75])
                if metric in ("gradient_mm", "bow_mm"):
                    row["positive_95pct_frames_recordings_" + metric] = int((group[prefix + "positive_fraction_" + metric] >= .95).sum())
                    row["negative_95pct_frames_recordings_" + metric] = int((group[prefix + "positive_fraction_" + metric] <= .05).sum())
            rows.append(row)
    return pd.DataFrame(rows)


def coverage_inventory():
    """List computed items in the active manuscript without copying reference assets."""
    figures, tables = [], []
    for span in ("short", "long"):
        for camera, mode in [(c, "default") for c in ("rsi", "rsf")] + list(product(("zedx", "zedxm"), ("neural", "neural_light", "neural_plus"))):
            for relative in [f"depth/{camera}_{mode}_depth_errors.pdf",
                             *[f"scatter/{camera}_{mode}_{res}_avg_vs_rmse.pdf" for res in ("SD", "HD")]]:
                figures.append(dict(paper_item=f"figures/plots/{span}/{relative}",
                                    inputs=["recordings/*/frames.csv"], script="scripts/extract.py"))
    # The active scatter appendices use PLUS for ZED; depth appendices use all modes.
    figures = [row for row in figures if "/scatter/zed" not in row["paper_item"] or "neural_plus_" in row["paper_item"]]
    for name, inputs in [
        ("zed_mode_envelope", ["derived/tables/configuration_envelopes.csv"]),
        ("bias_conditions", ["derived/tables/recording_summary.csv"]),
        ("configuration_envelope_no_bias", ["derived/tables/configuration_envelopes.csv"]),
        ("temporal_maps", ["recordings/*/pixels.npz"]),
        ("boundary_ratio_distance", ["derived/tables/boundary_primary.csv"]),
        ("zed_boundary_example", ["derived/recordings/*/boundary_pixels.npz", "recordings/*/samples.npz"]),
        *[(f"plane_residual_frame150_{distance}_hd_natural", ["derived/recordings/*/residual_map.npz"]) for distance in (1000, 1800, 3000)]]:
        figures.append(dict(paper_item=f"figures/revision/{name}.pdf", inputs=inputs, script="scripts/analyze.py"))
    for name in ("rsf_1800_hd_natural", "zedxm_1800_hd_neural_plus_natural"):
        figures.append(dict(paper_item=f"figures/pcl_{name}.pdf", inputs=[f"derived/recordings/{name}/pointcloud.npz"], script="scripts/analyze.py"))
    for label, inputs in [("tab:excluded_frames", ["derived/tables/frame_exclusions.csv"]),
                          ("tab:invalid_pixel_counts", ["derived/tables/invalid_pixel_extrema.csv"]),
                          ("tab:near_spec", ["derived/tables/manufacturer_context.csv"]),
                          *[(f"tab:appendix-d-{letter}", ["derived/tables/plane_table_values.csv"]) for letter in "abcd"]]:
        tables.append(dict(paper_item=label, inputs=inputs, script="scripts/analysis_tables.py"))
    return dict(figures=figures, tables=tables, render_status="Step 4 pending", text_measurements=[
        "derived/tables/camera_contrasts.csv", "derived/tables/realsense_contrasts.csv",
        "derived/tables/mode_contrasts.csv", "derived/tables/plane_distance_summary.csv",
        "derived/tables/mode_disagreement_summary.csv", "derived/tables/profile_distance_summary.csv",
        "derived/tables/profile_camera_mode_summary.csv", "derived/tables/boundary_group_summary.csv",
        "derived/tables/paper_counts.csv"])


def export_tables(output, records):
    """Atomically publish complete numerical tables; never replace them with a subset."""
    derived = output / "derived"
    names = [row["recording"] for row in records]
    if len(names) != 288 or len(set(names)) != 288:
        raise ValueError("Global tables require 288 distinct recordings")
    identities = {name: sha256(derived / "recordings" / name / "manifest.json") for name in names}
    destination = derived / "tables"
    if destination.exists():
        previous = json.loads((destination / "manifest.json").read_text())
        if previous["recording_manifests"] != identities or any(sha256(destination / name) != digest for name, digest in previous["output_sha256"].items()):
            raise ValueError("Global tables are stale/modified; use a fresh analysis root")
        return
    summaries, frames, boundaries, boundary_distances, profiles, normals, samples = [], [], [], [], [], {}, {}
    for name in names:
        folder = derived / "recordings" / name
        checkpoint = json.loads((folder / "manifest.json").read_text())
        summary = checkpoint["summary"]
        metadata = recording_metadata(name)
        summaries.append(summary)
        frames.append(pd.read_csv(output / "recordings" / name / "frames.csv"))
        for filename, rows in (("boundary_metrics.csv", boundaries), ("boundary_distance_profiles.csv", boundary_distances)):
            rows.append(pd.read_csv(folder / filename).assign(**metadata))
        profiles.append(dict(**metadata, **checkpoint["profile_summary"]))
        plane = pd.read_csv(folder / "planes.csv")
        _, normals[name] = frame_geometry(plane.a, plane.b)
        with np.load(folder / "bootstrap.npz", allow_pickle=False) as cache:
            samples[name] = cache["estimates"]
    summary, frame = pd.DataFrame(summaries), pd.concat(frames, ignore_index=True)
    profile = pd.DataFrame(profiles)
    if summary[KEYS[1:]].duplicated().any() or not np.isfinite(summary[SCALARS].to_numpy()).all():
        raise ValueError("Invalid full-recording summaries")
    with staging_directory(prefix=".tables-", dir=derived) as temporary:
        target = Path(temporary)
        def write(name, table):
            table.to_csv(target / f"{name}.csv", index=False)
        write("recording_summary", summary)
        write("frame_inclusion", frame)
        write("plot_frames", frame[frame.accepted])
        write("frame_exclusions", frame[~frame.accepted])
        write("invalid_pixel_extrema", invalid_extrema(frame).merge(summary[KEYS], on="recording", validate="one_to_one"))
        near = summary[(summary.resolution == "hd") & (summary.lighting == "natural") & summary.distance_m.isin([1.8, 2.2])
                       & (summary["mode"].eq("neural_plus") | summary.camera.isin(["rsi", "rsf"]))].copy()
        near["bias_mm"], near["absolute_bias_percent"] = near.bias_m * 1000, 100 * near.bias_m.abs() / near.distance_m
        write("manufacturer_context", near[KEYS + ["bias_mm", "absolute_bias_percent"]])
        write("configuration_envelopes", envelopes(summary))
        geometry_columns = ["S_mm", "S_pl_mm", "theta_h_deg", "theta_v_deg", "reduction_pct", "normal_x", "normal_y", "normal_z"]
        write("plane_table_values", summary[KEYS + ["frames"] + geometry_columns])
        write("plane_distance_summary", summary.groupby(["camera", "mode", "distance_m"])[geometry_columns].agg(["mean", "median"]).pipe(
            lambda table: table.set_axis(["_".join(column) for column in table.columns], axis=1)).reset_index())
        modes = mode_separations(summary, normals)
        write("mode_normal_separations", modes)
        disagreement = modes.groupby(["camera", "distance_m", "lighting", "resolution"]).normal_separation_deg.max().rename("max_separation_deg").reset_index()
        disagreement["range"] = np.where(disagreement.distance_m <= 1., "short", "long")
        write("mode_disagreement", disagreement)
        write("mode_disagreement_summary", disagreement.groupby(["camera", "range"]).max_separation_deg.agg(["count", "median"]).reset_index())
        write("profile_recording_summary", profile)
        write("profile_camera_mode_summary", profile_groups(profile, ["camera", "mode"]))
        write("profile_distance_summary", profile_groups(profile, ["camera", "mode", "distance_m"]))
        modes = contrasts(summary[summary.camera.str.startswith("zed")], samples, ["camera", "distance_m", "resolution", "lighting"], "mode", list(combinations(MODES, 2)))
        rs = contrasts(summary[summary.camera.isin(["rsi", "rsf"])], samples, ["distance_m", "resolution", "lighting"], "camera", [("rsi", "rsf")])
        cross = pd.concat([contrasts(summary[summary["mode"].eq(mode) | summary.camera.isin(["rsi", "rsf"])], samples,
            ["distance_m", "resolution", "lighting"], "camera", list(product(("rsi", "rsf"), ("zedx", "zedxm")))).assign(zed_mode=mode) for mode in MODES], ignore_index=True)
        write("mode_contrasts", modes)
        write("realsense_contrasts", rs)
        write("camera_contrasts", cross)
        write("resolution_contrasts", contrasts(summary, samples, ["camera", "mode", "distance_m", "lighting"], "resolution", [("hd", "sd")]))
        write("illumination_contrasts", contrasts(summary, samples, ["camera", "mode", "distance_m", "resolution"], "lighting", [("natural", "artificial")]))
        np.savez_compressed(target / "bootstrap_estimates.npz", **samples)
        boundary = pd.concat(boundaries, ignore_index=True)
        write("boundary_metrics", boundary)
        write("boundary_distance_profiles", pd.concat(boundary_distances, ignore_index=True))
        primary = boundary[boundary.coverage_threshold.eq(.9) & boundary.edge_width_cells.eq(.15) & boundary.alignment.eq("nominal")].copy()
        primary["exclusion_reasons"] = primary.apply(lambda row: ";".join(label for label, fail in [
            ("cell_pitch_below_4px", row.cell_pitch_px < 4), ("template_agreement_below_085", row.template_cell_agreement < .85),
            ("rgb_contrast_below_15", row.white_black_contrast < 15), ("corner_displacement_above_015cell", row.corner_motion_p95_cells > .15),
            ("boundary_pixels_below_20", row.edge_pixels < 20), ("interior_pixels_below_20", row.interior_pixels < 20),
            ("nonfinite_ratio", not np.isfinite(row.edge_interior_ratio))] if fail), axis=1)
        if not np.array_equal(primary.primary_eligible.to_numpy(), primary.exclusion_reasons.eq("").to_numpy()):
            raise ValueError("Boundary eligibility and reasons disagree")
        write("boundary_primary", primary)
        good = primary[primary.primary_eligible]
        group = good.groupby(["camera", "mode"]).agg(eligible_recordings=("recording", "size"), median_Q=("edge_interior_ratio", "median"),
            median_boundary_sd_mm=("edge_median_sd_mm", "median"), median_interior_sd_mm=("interior_median_sd_mm", "median"),
            median_paired_interior_minus_boundary_mm=("absolute_drop_mm", "median"),
            Q_below_one=("edge_interior_ratio", lambda x: int((x < 1).sum())),
            black_Q_below_one=("black_ratio", lambda x: int((x < 1).sum())), white_Q_below_one=("white_ratio", lambda x: int((x < 1).sum()))).reset_index()
        write("boundary_group_summary", group)
        matched = []
        for left, right in combinations(MODES, 2):
            pair = good[good["mode"] == left].merge(good[good["mode"] == right],
                on=["camera", "distance_m", "resolution", "lighting", "marker_id"], suffixes=("_left", "_right"), validate="one_to_one")
            pair["left_mode"], pair["right_mode"] = left, right
            pair["relative_contrast_difference"] = pair.edge_interior_ratio_right - pair.edge_interior_ratio_left
            matched.append(pair)
        write("boundary_matched_modes", pd.concat(matched, ignore_index=True))
        plus = cross[cross.zed_mode == "neural_plus"]
        counts = [("available_pairs", int(summary.bag_frames.sum()), "pairs"),
                  ("accepted_pairs", int(summary.frames.sum()), "pairs"),
                  ("excluded_pairs", int(summary.excluded_frames.sum()), "pairs"),
                  ("D435f_lower_absolute_bias_than_D435i", int((rs.absolute_bias_m_difference > 0).sum()), "of 36 conditions"),
                  ("D435f_lower_RMSE_than_D435i", int((rs.rmse_m_difference > 0).sum()), "of 36 conditions"),
                  ("RealSense_higher_spatial_SD_than_PLUS", int((plus.spatial_sd_m_difference > 0).sum()), "of 144 comparisons"),
                  ("RealSense_higher_residual_SD_than_PLUS", int((plus.plane_residual_sd_m_difference > 0).sum()), "of 144 comparisons"),
                  ("RealSense_higher_temporal_RMS_than_PLUS", int((plus.pixel_temporal_rms_m_difference > 0).sum()), "of 144 comparisons"),
                  ("ZED_horizontal_positive_bow_in_95pct_frames", int((profile.loc[profile.camera.str.startswith("zed"), "roi_horizontal_positive_fraction_bow_mm"] >= .95).sum()), "of 216 recordings"),
                  ("boundary_eligible_recordings", len(good), "of 288 recordings")]
        write("paper_counts", pd.DataFrame(counts, columns=["measurement", "value", "population"]))
        manifest = dict(recording_manifests=identities, output_sha256={p.name: sha256(p) for p in sorted(target.iterdir())},
                        recording_count=288, accepted_frames=int(summary.frames.sum()), available_pairs=int(summary.bag_frames.sum()))
        atomic_json(target / "manifest.json", manifest)
        target.rename(destination)
