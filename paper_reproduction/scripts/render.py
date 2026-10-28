"""Render computed paper figures/tables from validated standalone artifacts only.

Usage: python main.py render [--output ANALYSIS] [--destination FOLDER]
       [--figure revision/temporal_maps ...]
Outputs: figures/ matching manuscript paths, tables/ CSV/LaTeX pairs,
         render_manifest.json with source/input/output/font hashes and selection.
No raw bag, downloader, revision_analysis or reference-asset access is performed.
"""

import json
from pathlib import Path
import shutil

import matplotlib
from matplotlib import font_manager
import numpy as np
import pandas as pd

from .analysis_tables import coverage_inventory
from .storage import staging_directory
from .extract import atomic_json, sha256
from . import render_plots as plots


def register_fonts():
    """Use bundled fonts consistently, independent of system font installations."""
    bundled = Path(__file__).resolve().parents[1] / "fonts"
    dejavu = Path(matplotlib.get_data_path()) / "fonts/ttf"
    files = [bundled / f"LiberationSerif-{style}.ttf" for style in ("Regular", "Bold", "Italic", "BoldItalic")]
    files += [dejavu / f"DejaVuSans{suffix}.ttf" for suffix in ("", "-Bold", "-Oblique", "-BoldOblique")]
    for path in files:
        if not path.is_file():
            raise ValueError(f"Required bundled font missing: {path}")
    # Prefer the shipped versions even if another version is installed globally.
    font_manager.fontManager.ttflist = [font for font in font_manager.fontManager.ttflist
                                      if font.name not in ("Liberation Serif", "DejaVu Sans")]
    for path in files:
        font_manager.fontManager.addfont(path)
    return {name: font_manager.findfont(name, fallback_to_default=False)
            for name in ("Liberation Serif", "DejaVu Sans")}


def validate_file(analysis, name, filename, derived, inputs):
    """Verify the file checksum and its producer's link to the extraction manifest."""
    folder = analysis / ("derived/recordings" if derived else "recordings") / name
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Missing {'analysis' if derived else 'extraction'} for {name}; run the preceding stage first")
    manifest = json.loads(manifest_path.read_text())
    if derived:
        source = analysis / "recordings" / name / "manifest.json"
        if manifest["fingerprint"]["extraction_manifest_sha256"] != sha256(source):
            raise ValueError(f"Derived input is stale: {name}")
        for basename, digest in manifest["fingerprint"]["identity"]["source_sha256"].items():
            if sha256(Path(__file__).with_name(basename)) != digest:
                raise ValueError(f"Analysis code changed; rerun analysis in a fresh root: {name}")
    path = folder / filename
    expected = manifest["output_sha256"].get(filename)
    if expected is None or not path.is_file() or sha256(path) != expected:
        raise ValueError(f"Missing or modified render input: {path}")
    inputs[str(manifest_path)] = sha256(manifest_path)
    inputs[str(path)] = expected
    return path


def validated_tables(analysis, inputs):
    """Require complete-design tables, never promote focused results to full figures."""
    folder = analysis / "derived/tables"; path = folder / "manifest.json"
    if not path.is_file():
        raise ValueError("Full rendering needs complete derived/tables; finish extract and analyze for all 288 recordings")
    manifest = json.loads(path.read_text())
    if manifest["recording_count"] != 288 or len(manifest["recording_manifests"]) != 288:
        raise ValueError("Full rendering requires 288 recording manifests")
    for name, expected in manifest["recording_manifests"].items():
        recording = analysis / "derived/recordings" / name / "manifest.json"
        if sha256(recording) != expected:
            raise ValueError(f"Aggregate table input changed: {name}")
        checkpoint = json.loads(recording.read_text())
        if checkpoint["fingerprint"]["extraction_manifest_sha256"] != sha256(analysis / "recordings" / name / "manifest.json"):
            raise ValueError(f"Aggregate extraction input changed: {name}")
        for basename, digest in checkpoint["fingerprint"]["identity"]["source_sha256"].items():
            if sha256(Path(__file__).with_name(basename)) != digest:
                raise ValueError(f"Aggregate analysis code changed: {name}")
    for name, expected in manifest["output_sha256"].items():
        target = folder / name
        if Path(name).name != name or sha256(target) != expected:
            raise ValueError(f"Aggregate table changed: {name}")
        inputs[str(target)] = expected
    inputs[str(path)] = sha256(path)
    return folder


def render_paper(analysis, destination, figures=None):
    """Preflight selected inputs, stage all outputs and preserve edited/unowned files."""
    analysis, destination = analysis.expanduser().resolve(), destination.expanduser().resolve()
    if destination.is_relative_to(analysis):
        raise ValueError("Render destination must be outside the analysis input tree")
    known = [row["paper_item"] for row in coverage_inventory()["figures"]]
    selected = known if figures is None else ["figures/" + name.removeprefix("figures/").removesuffix(".pdf") + ".pdf" for name in figures]
    if len(set(selected)) != len(selected) or any(name not in known for name in selected):
        raise ValueError("Figure selection must contain distinct computed manuscript paths, e.g. revision/temporal_maps")
    if matplotlib.__version__ != "3.10.8":
        raise ValueError("Exact rendering requires matplotlib==3.10.8; install requirements.txt")
    fonts = register_fonts()
    inputs, arrays, table_folder = {}, {}, None
    def load(name, filename, derived=True):
        key = (name, filename, derived)
        if key not in arrays:
            path = validate_file(analysis, name, filename, derived, inputs)
            with np.load(path, allow_pickle=False) as cache:
                arrays[key] = {name: cache[name] for name in cache.files}
        return arrays[key]
    summary_names = {"zed_mode_envelope", "bias_conditions", "configuration_envelope_no_bias", "boundary_ratio_distance"}
    if figures is None or any(name.startswith("figures/plots/") or Path(name).stem in summary_names for name in selected):
        table_folder = validated_tables(analysis, inputs)
    summary = pd.read_csv(table_folder / "recording_summary.csv") if table_folder else None
    frames = pd.read_csv(table_folder / "plot_frames.csv") if table_folder and any("/plots/" in name for name in selected) else None
    # Collect every dependency before producing any figure or output directory.
    for relative in selected:
        name = Path(relative).stem
        if name == "temporal_maps":
            for camera in plots.LABEL: load(plots.recording_name(camera), "pixels.npz", False)
        elif name == "zed_boundary_example":
            for mode in ("neural_light", "neural_plus"):
                recording = plots.recording_name("zedxm", mode=mode)
                load(recording, "pixels.npz", False); load(recording, "boundary_reference.npz")
        elif name.startswith("plane_residual_frame150_"):
            distance = int(name.split("_")[3])
            for camera in plots.LABEL: load(plots.recording_name(camera, distance), "residual_map.npz")
        elif name.startswith("pcl_"):
            for camera in ("rsf", "zedxm"): load(plots.recording_name(camera), "pointcloud.npz")
    previous_path = destination / "render_manifest.json"
    previous = json.loads(previous_path.read_text()) if previous_path.is_file() else {"output_sha256": {}}
    for name, digest in previous["output_sha256"].items():
        target = destination / name
        if not target.is_file() or sha256(target) != digest:
            raise ValueError(f"Previously rendered file changed; preserve it and use a new --destination: {target}")
    destination.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(destination).free < 512 * 1024**2:
        raise RuntimeError("Rendering requires at least 512 MiB free")
    with staging_directory(prefix=".render-", dir=destination) as temporary:
        staging = Path(temporary)
        for relative in selected:
            name = Path(relative).stem; default = "/plots/" in relative or name.startswith("pcl_")
            style = matplotlib.rcParamsDefault.copy() if default else {**matplotlib.rcParamsDefault, **plots.STYLE}
            if name.startswith("plane_residual_frame150_"):
                style.update({"font.size": 10, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5})
            with matplotlib.rc_context(style):
                if "/plots/" in relative:
                    span = Path(relative).parts[2]; base = name.split("_depth_errors")[0] if "/depth/" in relative else name.split("_avg_vs_rmse")[0].rsplit("_", 1)[0]
                    camera, mode = base.split("_", 1); mode = "stereo" if mode == "default" else mode
                    resolution = None if "/depth/" in relative else name.split("_avg_vs_rmse")[0].rsplit("_", 1)[1].lower()
                    figure = plots.distribution(frames, camera, mode, span, resolution)
                elif name in summary_names:
                    figure = plots.boundary_ratio_distance(pd.read_csv(table_folder / "boundary_primary.csv")) if name == "boundary_ratio_distance" else plots.summary_plot(summary, name)
                elif name == "temporal_maps":
                    figure = plots.temporal_maps({plots.recording_name(c): load(plots.recording_name(c), "pixels.npz", False) for c in plots.LABEL})
                elif name == "zed_boundary_example":
                    names = [plots.recording_name("zedxm", mode=mode) for mode in ("neural_light", "neural_plus")]
                    figure = plots.boundary_example({n: load(n, "pixels.npz", False) for n in names}, {n: load(n, "boundary_reference.npz") for n in names})
                elif name.startswith("plane_residual_frame150_"):
                    distance = int(name.split("_")[3])
                    figure = plots.residual_maps({c: load(plots.recording_name(c, distance), "residual_map.npz") for c in plots.LABEL})
                else:
                    figure = plots.point_cloud({plots.recording_name(c): load(plots.recording_name(c), "pointcloud.npz") for c in ("rsf", "zedxm")}, name.removeprefix("pcl_"))
                target = staging / relative; target.parent.mkdir(parents=True, exist_ok=True)
                dpi = 300 if "/plots/" in relative or name.startswith("plane_residual_frame150_") else 200 if name.startswith("pcl_") else 220
                # Constrained layout shifts slightly on save; preserve each original save order.
                if default or name.startswith("plane_residual_frame150_"):
                    figure.savefig(target.with_suffix(".png"), dpi=dpi, bbox_inches="tight")
                    figure.savefig(target, bbox_inches="tight", **({"dpi": 300} if name.startswith("plane_residual_frame150_") else {}))
                else:
                    figure.savefig(target, bbox_inches="tight")
                    figure.savefig(target.with_suffix(".png"), dpi=dpi, bbox_inches="tight")
                plots.plt.close(figure)
            print(f"Rendered {relative}", flush=True)
        if figures is None:
            from .render_tables import render_tables
            render_tables(table_folder, staging / "tables")
        generated = {str(p.relative_to(staging)): p for p in staging.rglob("*") if p.is_file()}
        for relative in generated:
            target = destination / relative
            if target.exists() and relative not in previous["output_sha256"]:
                raise ValueError(f"Preserving existing unowned output; use a new --destination: {target}")
        hashes = previous["output_sha256"].copy()
        for relative, source in generated.items():
            hashes[relative] = sha256(source)
            target = destination / relative; target.parent.mkdir(parents=True, exist_ok=True); source.replace(target)
        here = Path(__file__).resolve().parent
        manifest = dict(selection=selected, full_render=figures is None, input_sha256=inputs, output_sha256=hashes,
                        source_sha256={name: sha256(here / name) for name in ("render.py", "render_plots.py", "render_tables.py")},
                        matplotlib=matplotlib.__version__, fonts={name: {"path": path, "sha256": sha256(Path(path))} for name, path in fonts.items()})
        atomic_json(previous_path, manifest)
