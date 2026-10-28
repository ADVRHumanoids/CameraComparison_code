"""Download and extract the paper's Dataverse bags without acquisition logs.

Usage: python main.py download [--dataset PATH] [--stream].
Inputs: IIT Dataverse DOI 10.48557/LUONQB, release 1.0; optional DATAVERSE_TOKEN.
Outputs: retained .tar.xz archives, recording directories, release metadata.
Requires: Python 3.12+ standard library with lzma support; no ROS installation.
Streaming mode preserves staging on failure and never stores compressed archives.
"""

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .storage import staging_directory


SERVER = "https://dataverse.iit.it"
DOI = "doi:10.48557/LUONQB"
VERSION = "1.0"
BLOCK_SIZE = 1024 * 1024
RESERVE_BYTES = 1024**3
COMPLETION_FILE = ".paper_reproduction_extracted.json"


def open_remote(url):
    """Use credentials only for the explicitly addressed Dataverse request."""
    request = Request(url)
    token = os.environ.get("DATAVERSE_TOKEN")
    if token:
        # Redirected storage hosts must not receive the Dataverse API token.
        request.add_unredirected_header("X-Dataverse-key", token)
    return urlopen(request, timeout=120)


def require_space(directory, needed):
    """Leave a 1 GiB margin and fail before starting the next disk write."""
    if shutil.disk_usage(directory).free < needed + RESERVE_BYTES:
        raise RuntimeError(f"Insufficient free space under {directory}; need {needed} bytes plus 1 GiB reserve")


def safe_path(root, relative):
    """Reject metadata paths that escape the destination, including via symlinks."""
    relative = PurePosixPath(relative)
    if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative):
        raise ValueError(f"Unsafe dataset path: {relative}")
    result = root.joinpath(*relative.parts)
    if not result.resolve().is_relative_to(root):
        raise ValueError(f"Dataset path escapes destination: {relative}")
    return result


def verified(path, size, checksum):
    """Check complete file content against the release's published checksum."""
    if not path.is_file() or path.is_symlink() or path.stat().st_size != size:
        return False
    algorithm = checksum["type"].lower().replace("-", "")
    if algorithm not in {"md5", "sha1", "sha256", "sha512"}:
        raise ValueError(f"Unsupported published checksum: {algorithm}")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, algorithm).hexdigest()
    return digest.lower() == checksum["value"].lower()


def extraction_complete(destination, checksum):
    """Reuse only a complete extraction tied to the published archive checksum."""
    if not destination.exists() and not destination.is_symlink():
        return False
    marker = destination / COMPLETION_FILE
    if destination.is_symlink() or not marker.is_file():
        raise RuntimeError(f"Preserving existing recording without our completion marker: {destination}")
    completed = json.loads(marker.read_text())
    files = completed.get("files", {})
    if completed.get("checksum") != checksum or not files:
        raise RuntimeError(f"Extraction identity differs: {destination}")
    for name, size in files.items():
        path = safe_path(destination.resolve(), name)
        if not path.is_file() or path.is_symlink() or path.stat().st_size != size:
            raise RuntimeError(f"Extracted file missing or changed: {path}")
    return True


class CheckedStream:
    """Hash every compressed byte read, including bytes buffered by tarfile."""

    def __init__(self, source, size, checksum):
        self.source, self.size, self.count = source, size, 0
        algorithm = checksum["type"].lower().replace("-", "")
        if algorithm not in {"md5", "sha1", "sha256", "sha512"}:
            raise ValueError(f"Unsupported published checksum: {algorithm}")
        self.digest = hashlib.new(algorithm)

    def read(self, size=-1):
        data = self.source.read(size)
        self.count += len(data)
        if self.count > self.size:
            raise ValueError("Stream exceeds published archive size")
        self.digest.update(data)
        return data


def stream_recording(root, entry):
    """Extract a checksum-verified network stream; preserve all staging directories."""
    data = entry["dataFile"]
    archive = safe_path(root, str(PurePosixPath(entry.get("directoryLabel") or "") / data["filename"]))
    destination = archive.with_name(archive.name.removesuffix(".tar.xz"))
    checksum = data["checksum"]
    if extraction_complete(destination, checksum):
        print(f"Already extracted: {destination.relative_to(root)}", flush=True)
        return
    archive.parent.mkdir(parents=True, exist_ok=True)
    require_space(archive.parent, 0)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.stream-", dir=archive.parent))
    print(f"Streaming: {destination.relative_to(root)} ({data['filesize']} compressed bytes)", flush=True)
    with open_remote(f"{SERVER}/api/access/datafile/{int(data['id'])}") as response:
        stream = CheckedStream(response, int(data["filesize"]), checksum)
        with tarfile.open(fileobj=stream, mode="r|xz") as source:
            for member in source:
                name = PurePosixPath(member.name)
                if name.is_absolute() or ".." in name.parts or "\\" in member.name:
                    raise ValueError(f"Unsafe archive member; staging preserved at {staging}: {member.name}")
                if not (member.isfile() or member.isdir()) or member.issparse():
                    raise ValueError(f"Unsupported archive member; staging preserved at {staging}: {member.name}")
                safe_path(staging.resolve(), member.name)
                require_space(archive.parent, member.size)
                source.extract(member, staging, filter="data")
        # tarfile may stop at the end marker before the HTTP response ends.
        while stream.read(BLOCK_SIZE):
            pass
        if stream.count != int(data["filesize"]) or stream.digest.hexdigest().lower() != checksum["value"].lower():
            raise ValueError(f"Stream size/checksum mismatch; staging preserved at {staging}")
    entries = list(staging.iterdir())
    contents = entries[0] if len(entries) == 1 and entries[0].is_dir() else staging
    if not (contents / "metadata.yaml").is_file() or not list(contents.glob("*.mcap")):
        raise ValueError(f"Stream lacks metadata/MCAP; staging preserved at {staging}")
    files = {str(p.relative_to(contents)): p.stat().st_size for p in contents.rglob("*") if p.is_file()}
    if COMPLETION_FILE in files:
        raise ValueError(f"Reserved marker in archive; staging preserved at {staging}")
    (contents / COMPLETION_FILE).write_text(json.dumps({"checksum": checksum, "files": files}, indent=2) + "\n")
    contents.rename(destination)
    print(f"Verified and extracted: {destination.relative_to(root)} ({sum(files.values())} bytes)", flush=True)


def download_file(root, entry):
    """Restart incomplete files and publish downloads only after verification."""
    data = entry["dataFile"]
    relative = str(PurePosixPath(entry.get("directoryLabel") or "") / data["filename"])
    # Keep the published README separate from this folder's usage documentation.
    destination = safe_path(root, "DATASET_README.md" if relative == "README.md" else relative)
    size = int(data["filesize"])
    if size <= 0:
        raise ValueError(f"Invalid published file size: {data['filename']}")
    if verified(destination, size, data["checksum"]):
        print(f"Verified existing: {destination.relative_to(root)}", flush=True)
        return destination
    if destination.exists() or destination.is_symlink():
        raise RuntimeError(f"Existing file does not match the release; preserve and inspect it: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    require_space(destination.parent, size)
    # Keep earlier partial transfers untouched; this run owns a fresh staging file.
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.part-", dir=destination.parent)
    os.close(descriptor)
    partial = Path(temporary)
    print(f"Downloading: {destination.relative_to(root)} ({size} bytes)", flush=True)
    with open_remote(f"{SERVER}/api/access/datafile/{int(data['id'])}") as source, partial.open("wb") as target:
        while chunk := source.read(BLOCK_SIZE):
            if target.tell() + len(chunk) > size:
                raise ValueError(f"Download exceeds published size: {destination.name}")
            require_space(destination.parent, len(chunk))
            target.write(chunk)
    if not verified(partial, size, data["checksum"]):
        raise ValueError(f"Downloaded size/checksum mismatch: {partial}")
    partial.replace(destination)
    return destination


def extract_recording(archive, checksum):
    """Extract regular files into staging, then publish one complete recording."""
    destination = archive.with_name(archive.name.removesuffix(".tar.xz"))
    if extraction_complete(destination, checksum):
        print(f"Already extracted: {destination.name}", flush=True)
        return

    print(f"Extracting: {archive.name}", flush=True)
    with tarfile.open(archive, "r:xz") as source:
        members = source.getmembers()
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or "\\" in member.name:
                raise ValueError(f"Unsafe archive member: {member.name}")
            if not (member.isfile() or member.isdir()) or member.issparse():
                raise ValueError(f"Unsupported archive member: {member.name}")
        require_space(archive.parent, sum(member.size for member in members if member.isfile()))
        with staging_directory(prefix=".extract-", dir=archive.parent) as temporary:
            staging = Path(temporary)
            source.extractall(staging, members=members, filter="data")
            entries = list(staging.iterdir())
            contents = entries[0] if len(entries) == 1 and entries[0].is_dir() else staging
            if not (contents / "metadata.yaml").is_file() or not list(contents.glob("*.mcap")):
                raise ValueError(f"Archive lacks recording metadata/MCAP: {archive.name}")
            files = {str(p.relative_to(contents)): p.stat().st_size for p in contents.rglob("*") if p.is_file()}
            if COMPLETION_FILE in files:
                raise ValueError(f"Archive contains reserved completion marker: {archive.name}")
            (contents / COMPLETION_FILE).write_text(json.dumps({"checksum": checksum, "files": files}, indent=2) + "\n")
            contents.rename(destination)


def release_entries():
    """Fetch and validate the published release and its complete recording design."""
    query = urlencode({"persistentId": DOI})
    with open_remote(f"{SERVER}/api/datasets/:persistentId/versions/{VERSION}?{query}") as response:
        metadata = json.load(response)
    if metadata.get("status") != "OK":
        raise ValueError("Dataverse did not return successful release metadata")
    release = metadata["data"]
    if (release["versionNumber"], release["versionMinorNumber"], release["versionState"]) != (1, 0, "RELEASED"):
        raise ValueError("Dataverse metadata is not published release 1.0")

    configurations = [f"{camera}_{resolution}" for camera in ("rsi", "rsf") for resolution in ("hd", "sd")]
    configurations += [f"{camera}_{resolution}_{mode}" for camera in ("zedx", "zedxm")
                       for resolution in ("hd", "sd") for mode in ("neural", "neural_light", "neural_plus")]
    expected = set()
    for light in ("natural", "artificial"):
        for distance in ("0400", "0600", "0800", "1000", "1400", "1800", "2200", "2600", "3000"):
            for config in configurations:
                camera, rest = config.split("_", 1)
                expected.add(f"{light}/{distance}/{camera}_{distance}_{rest}_{light}.tar.xz")
    selected, found = [], set()
    for entry in release["files"]:
        name = entry["dataFile"]["filename"]
        relative = str(PurePosixPath(entry.get("directoryLabel") or "") / name)
        if relative not in expected and relative != "README.md":
            continue
        if relative in found:
            raise ValueError(f"Duplicate release file: {relative}")
        found.add(relative)
        selected.append(entry)
    if expected - found:
        raise ValueError(f"Release is missing {len(expected - found)} expected recording archives")

    return metadata, selected


def download_dataset(dataset, stream=False, workers=1):
    """Download the exact 288-recording design; never select log archives."""
    root = dataset.expanduser().resolve()
    if workers < 1:
        raise ValueError("Download workers must be positive")
    metadata, selected = release_entries()

    root.mkdir(parents=True, exist_ok=True)
    manifest = root / "release_metadata.json"
    if manifest.is_symlink():
        raise ValueError(f"Unsafe metadata destination: {manifest}")
    if manifest.exists():
        if json.loads(manifest.read_text()) != metadata:
            raise ValueError(f"Preserving different release metadata: {manifest}; use a new dataset destination")
    else:
        manifest.write_text(json.dumps(metadata, indent=2) + "\n")
    print("Release 1.0: 288 recording archives; acquisition logs excluded.", flush=True)
    def transfer(entry):
        if stream and entry["dataFile"]["filename"].endswith(".tar.xz"):
            stream_recording(root, entry)
            return
        archive = download_file(root, entry)
        if archive.name.endswith(".tar.xz"):
            extract_recording(archive, entry["dataFile"]["checksum"])
    if workers == 1:
        for entry in selected:
            transfer(entry)
    else:
        failed = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(transfer, entry): entry["dataFile"]["filename"] for entry in selected}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as error:
                    failed.append(futures[future])
                    print(f"Transfer failed (all staging preserved): {futures[future]}: {error}", flush=True)
        if failed:
            raise RuntimeError(f"{len(failed)} transfer(s) failed; rerun to retry while keeping completed recordings: {failed}")
