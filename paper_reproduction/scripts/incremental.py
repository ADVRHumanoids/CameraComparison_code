"""Download, extract and analyze recordings sequentially, then render the paper.

Called by main.py incremental_download or incremental_all. A dedicated cache holds raw downloads;
only successfully analyzed downloads in that cache are removed. Compact results
and progress survive interruptions. Existing datasets are never accepted as cache.
"""

import json
from pathlib import Path

import cv2
import pandas as pd

from . import analyze, analysis_tables, download_dataset as download
from .extract import atomic_json, extraction_identity, extract_recording, recording_metadata, sha256
from .render import render_paper


def validate_checkpoint(output, name, identity):
    """Verify retained artifacts before skipping downloads or removing raw data."""
    source = output / "recordings" / name
    derived = output / "derived/recordings" / name
    extraction = json.loads((source / "manifest.json").read_text())
    checkpoint = json.loads((derived / "manifest.json").read_text())
    if extraction["extraction_identity"] != identity["extraction"]:
        raise ValueError(f"Extraction code changed: {name}; use a fresh output/cache")
    fingerprint = checkpoint["fingerprint"]
    if fingerprint["identity"] != identity or fingerprint["extraction_manifest_sha256"] != sha256(source / "manifest.json"):
        raise ValueError(f"Analysis changed: {name}; use a fresh output/cache")
    for folder, manifest in ((source, extraction), (derived, checkpoint)):
        for filename, digest in manifest["output_sha256"].items():
            if Path(filename).name != filename or sha256(folder / filename) != digest:
                raise ValueError(f"Changed checkpoint: {name}/{filename}")


def remove_download(bag, files):
    """Remove only inventoried cache files; tolerate interrupted prior cleanup."""
    if not bag.exists():
        return
    expected = set(files) | {download.COMPLETION_FILE}
    for path in bag.rglob("*"):
        if path.is_symlink() or (path.is_file() and str(path.relative_to(bag)) not in expected):
            raise ValueError(f"Unexpected cache content preserved: {path}")
    for name, size in files.items():
        path = download.safe_path(bag.resolve(), name)
        if path.exists() and path.stat().st_size != size:
            raise ValueError(f"Changed raw file preserved: {path}")
    for name in expected:
        download.safe_path(bag.resolve(), name).unlink(missing_ok=True)
    for path in sorted(bag.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir():
            path.rmdir()
    bag.rmdir()


def incremental_download(cache, output, destination):
    """Resume verified compact outputs; raw cache peaks at one recording."""
    cache, output, destination = [p.expanduser().resolve() for p in (cache, output, destination)]
    if (cache == destination or cache.is_relative_to(output) or output.is_relative_to(cache)
            or destination.is_relative_to(cache) or cache.is_relative_to(destination)
            or destination.is_relative_to(output)):
        raise ValueError("Cache must be separate from analysis and render destination")
    state_path = cache / "incremental.json"
    if not state_path.exists():
        if cache.exists() and any(cache.iterdir()):
            raise ValueError("Incremental cache must be new or empty; existing datasets are preserved")
        if output.exists() and any(output.iterdir()):
            raise ValueError("Use a new analysis output for an incremental run")
        cache.mkdir(parents=True, exist_ok=True)
        atomic_json(state_path, dict(output=str(output), destination=str(destination), completed={}, status="in_progress"))
    state = json.loads(state_path.read_text())
    if state["output"] != str(output) or state["destination"] != str(destination):
        raise ValueError("Resume with the original output and destination paths")
    metadata_path = cache / "release_metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
        entries = metadata["entries"]
    else:
        release, entries = download.release_entries()
        atomic_json(metadata_path, dict(release=release, entries=entries))
    entries = sorted([entry for entry in entries if entry["dataFile"]["filename"].endswith(".tar.xz")],
                     key=lambda entry: entry.get("directoryLabel", "") + "/" + entry["dataFile"]["filename"])
    if len(entries) != 288:
        raise ValueError("Incremental run requires the complete 288-recording release")
    (output / "recordings").mkdir(parents=True, exist_ok=True)
    derived = output / "derived"
    (derived / "recordings").mkdir(parents=True, exist_ok=True)
    here = Path(__file__).parent
    identity = dict(source_sha256={p.name: sha256(p) for p in [here / "analyze.py", here / "analysis_math.py", here / "analysis_tables.py"]},
                    extraction=extraction_identity())
    cv2.setNumThreads(1)
    records = []
    for index, entry in enumerate(entries):
        relative = str(Path(entry.get("directoryLabel") or "") / entry["dataFile"]["filename"]).removesuffix(".tar.xz")
        bag = download.safe_path(cache, relative)
        name = bag.name
        records.append(dict(**recording_metadata(name), bag_path=relative))
        print(f"[{index + 1}/288] Incremental {name}", flush=True)
        if name not in state["completed"]:
            download.stream_recording(cache, entry)
            extract_recording(bag, output, identity["extraction"])
            analyze.analyze_recording(bag, output / "recordings" / name, derived, 20261012 + index, identity)
            validate_checkpoint(output, name, identity)
            marker = json.loads((bag / download.COMPLETION_FILE).read_text())
            state["completed"][name] = dict(files=marker["files"])
            atomic_json(state_path, state)
        else:
            validate_checkpoint(output, name, identity)
        remove_download(bag, state["completed"][name]["files"])
    pd.DataFrame(records).to_csv(output / "inventory.csv", index=False)
    atomic_json(derived / "coverage.json", analysis_tables.coverage_inventory())
    analysis_tables.export_tables(output, records)
    state["status"] = "analyzed"
    atomic_json(state_path, state)


def incremental_all(cache, output, destination):
    """Resume incremental numerical processing, then render the complete paper."""
    incremental_download(cache, output, destination)
    render_paper(output, destination)
    state_path = cache.expanduser().resolve() / "incremental.json"
    state = json.loads(state_path.read_text())
    state["status"] = "complete"
    atomic_json(state_path, state)
