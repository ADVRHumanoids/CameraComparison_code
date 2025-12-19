#!/usr/bin/env bash
set -euo pipefail

# dataverse_downloader.sh
# Download files listed in a local dataset metadata export (dataverse_json or DDI)
# and optionally decompress archives and collect txt logs.
#
# Usage:
#   API_TOKEN="..." SERVER_URL="https://dataverse.iit.it" PERSISTENT_ID="doi:..." \
#     ./dataverse_downloader.sh [--decompress|-d]
#
# Or edit the variables below.

# -------------------- USER-CONFIGURABLE VARIABLES --------------------
# Either export these in your environment before running the script,
# or edit them here.
: "${API_TOKEN:=""}"                     # your Dataverse API token (required)
: "${SERVER_URL:="https://dataverse.iit.it/"}"
: "${PERSISTENT_ID:="doi:10.48557/LUONQB"}"
: "${METADATA_FORMAT:="dataverse_json"}" # dataverse_json or ddi, etc.
: "${VERSION:=":draft"}"                 # e.g. :draft or :latest
: "${DATA_JSON:="dataset.json"}"
: "${FOLDER:="dataset"}" # top-level download folder
# --------------------------------------------------------------------


# --- Function to decompress archives and collect logs ---
decompress_archives() {
  echo "Decompressing archives under $FOLDER ..."

  # -----------------------------
  # 1) Decompress NON-logs .tar.xz
  # -----------------------------
  find "$FOLDER" -type f -name '*.tar.xz' ! -name 'logs_*.tar.xz' -print0 |
  while IFS= read -r -d '' archive; do
    parent_dir="$(dirname "$archive")"
    base_name="$(basename "${archive%.tar.xz}")"
    dest="$parent_dir/$base_name"

    echo "Extracting archive: $archive → $dest/ (safe extract)"
    tmpdir=$(mktemp -d)
    tar -xJf "$archive" -C "$tmpdir"

    # If the archive contains a single top-level directory, move its contents
    # into the destination (avoid dest/dest nesting). Otherwise move all entries.
    entries=("$tmpdir"/*)
    mkdir -p "$dest"
    if [ ${#entries[@]} -eq 1 ] && [ -d "${entries[0]}" ]; then
      shopt -s dotglob
      mv "${entries[0]}"/* "$dest"/ 2>/dev/null || true
      shopt -u dotglob
    else
      shopt -s dotglob
      mv "$tmpdir"/* "$dest"/ 2>/dev/null || true
      shopt -u dotglob
    fi

    rm -rf "$tmpdir"
    [[ "$CLEAN_ARCHIVES" == "true" ]] && rm -f "$archive"
  done

  # -----------------------------
  # 2) Decompress ZIP archives
  # -----------------------------
  find "$FOLDER" -type f -name '*.zip' -print0 |
  while IFS= read -r -d '' archive; do
    parent_dir="$(dirname "$archive")"
    base="${archive%.zip}"
    dest="$base"

    echo "Extracting zip: $archive → $dest/"
    tmpdir=$(mktemp -d)
    unzip -q -o "$archive" -d "$tmpdir"

    entries=("$tmpdir"/*)
    if [[ ${#entries[@]} -eq 1 && -d "${entries[0]}" ]]; then
      mv "${entries[0]}" "$dest"
    else
      mkdir -p "$dest"
      shopt -s dotglob
      mv "$tmpdir"/* "$dest"/ 2>/dev/null || true
      shopt -u dotglob
    fi
    rm -rf "$tmpdir"

    [[ "$CLEAN_ARCHIVES" == "true" ]] && rm -f "$archive"
  done

  # ------------------------------------------------
  # 3) Decompress logs archives and promote *.txt
  # ------------------------------------------------
  find "$FOLDER" -type f -name 'logs_*.tar.xz' -print0 |
  while IFS= read -r -d '' archive; do
    parent_dir="$(dirname "$archive")"
    logs_base="$(basename "$archive" .tar.xz)"
    extracted_dir="$parent_dir/$logs_base"

    echo "Processing logs archive: $archive"

    # Extract logs archive
    tar -xJf "$archive" -C "$parent_dir"

    # Move all txt files up one level
    shopt -s nullglob
    txt_files=( "$extracted_dir"/*.txt )
    shopt -u nullglob

    if [[ ${#txt_files[@]} -eq 0 ]]; then
      echo "  Warning: no .txt files found in $extracted_dir"
    else
      for txt in "${txt_files[@]}"; do
        mv "$txt" "$parent_dir/"
      done
      echo "  Moved ${#txt_files[@]} txt file(s) to $parent_dir"
    fi

    # Remove extracted logs folder
    rm -rf "$extracted_dir"

    # Optional cleanup of archive
    [[ "$CLEAN_ARCHIVES" == "true" ]] && rm -f "$archive"
  done

  echo "Decompression complete."
}



# ------------------- Main script execution -------------------

# Parse args
DECOMPRESS=false
CLEAN_ARCHIVES=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--decompress) DECOMPRESS=true ;;
    --clean-archives) CLEAN_ARCHIVES=true ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--decompress|-d]
Environment variables (can be exported before running):
  API_TOKEN, SERVER_URL, PERSISTENT_ID, METADATA_FORMAT, VERSION, DATA_JSON, FOLDER
Options:
  -d, --decompress    After downloading, decompress archives (tar.xz and .zip)
                      and collect all .txt files from any logs* folders into
                      $FOLDER/logs_extracted/
  --clean-archives    Remove archives after successful decompression.
EOF
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 2 ;;
  esac
  shift
done

# Basic sanity
if [[ -z "${API_TOKEN:-}" ]]; then
  echo "ERROR: API_TOKEN is empty. Export your Dataverse API token before running." >&2
  exit 2
fi

# 1) Fetch dataset metadata if not present
if [[ ! -s "$DATA_JSON" ]]; then
  echo "Fetching dataset metadata into $DATA_JSON ..."
  curl -fsS -H "X-Dataverse-key: $API_TOKEN" \
    "${SERVER_URL%/}/api/datasets/export?exporter=${METADATA_FORMAT}&persistentId=${PERSISTENT_ID}&version=${VERSION}" \
    -o "$DATA_JSON"
fi

if [[ ! -s "$DATA_JSON" ]]; then
  echo "Metadata export failed or $DATA_JSON is empty." >&2
  exit 1
fi

# 2) Extract file list (handle both structures like .files or .datasetVersion.files)
echo "Extracting file list from $DATA_JSON ..."
tmp_list=$(mktemp)
jq -r '((.files) // .datasetVersion.files)[] | [.dataFile.id, .dataFile.filename, (.dataFile.filesize // 0), (.directoryLabel // "")] | @tsv' "$DATA_JSON" \
  > "$tmp_list" || {
    echo "Failed to parse $DATA_JSON with jq. Inspect the file." >&2
    rm -f "$tmp_list"
    exit 1
  }

if [[ ! -s "$tmp_list" ]]; then
  echo "No files found in metadata." >&2
  rm -f "$tmp_list"
  exit 1
fi

expected_count=$(wc -l < "$tmp_list" | tr -d ' ')
echo "Found ${expected_count} files to consider."

mkdir -p "${FOLDER}"

# Logging and counters
LOG_FILE="dataset_downloader.log"
echo "=== Download run: $(date -u +'%Y-%m-%dT%H:%M:%SZ') ===" >> "$LOG_FILE"
downloaded=0
skipped=0
failed=0

# 3) Download loop (preserve directoryLabel)
echo "Starting download of files ..."
while IFS=$'\t' read -r file_id filename filesize dirlabel; do
  # sanitize dirlabel trailing slash
  if [[ -n "$dirlabel" ]]; then
    dest_dir="$FOLDER/${dirlabel%/}"
  else
    dest_dir="$FOLDER"
  fi
  mkdir -p "$dest_dir"

  dest_path="$dest_dir/$filename"

  # If file already exists and filesize matches => skip
  if [[ -f "$dest_path" ]]; then
    if [[ "$filesize" -gt 0 ]]; then
      existing_size=$(stat -c%s "$dest_path" 2>/dev/null || stat -f%z "$dest_path" 2>/dev/null || echo "0")
      if [[ "$existing_size" -eq "$filesize" ]]; then
        echo "Skipping existing up-to-date file: $dest_path"
        echo -e "SKIP\t$filename\t$dest_path" >> "$LOG_FILE"
        ((skipped+=1))
        continue
      else
        echo "File exists but size differs; will re-download: $dest_path"
      fi
    else
      echo "File exists; skipping (no filesize in metadata to compare): $dest_path"
      echo -e "SKIP (NO SIZE COMPARED)\t$filename\t$dest_path" >> "$LOG_FILE"
      ((skipped+=1))
      continue
    fi
  fi

  url="${SERVER_URL%/}/api/access/datafile/${file_id}"
  echo "Downloading ${filename} → ${dest_path}"
  # allow curl to follow redirects and fail on HTTP errors
  if curl -L -f -H "X-Dataverse-key: ${API_TOKEN}" -o "$dest_path" "$url"; then
    echo -e "OK\t$filename\t$dest_path" >> "$LOG_FILE"
    ((downloaded+=1))
  else
    echo "Failed to download ${filename} (id=${file_id})" >&2
    rm -f "$dest_path"
    echo -e "FAILED\t$filename\tid=${file_id}" >> "$LOG_FILE"
    ((failed+=1))
  fi
done < "$tmp_list"

rm -f "$tmp_list"

echo "Download summary: expected=${expected_count}, downloaded=${downloaded}, skipped=${skipped}, failed=${failed}"
echo "Download summary: expected=${expected_count}, downloaded=${downloaded}, skipped=${skipped}, failed=${failed}" >> "$LOG_FILE"

if [[ $failed -gt 0 ]]; then
  echo "One or more downloads failed. See $LOG_FILE for details." >&2
  # continue to decompression step optionally, but return non-zero at the end
fi

# 4) Optional: decompress archives found under $FOLDER
if [[ "$DECOMPRESS" == "true" ]]; then
  decompress_archives
fi

# Final exit status
if [[ $failed -gt 0 ]]; then
  exit 1
else
  echo "All done!"
  exit 0
fi


