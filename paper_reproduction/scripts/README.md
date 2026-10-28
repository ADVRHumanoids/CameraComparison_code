# Script Reference

This directory contains the internal Python modules used by the paper reproduction pipeline.

**All commands must be run through `main.py` in the parent `paper_reproduction/` directory.** The modules listed below are implementation components and do not provide independent command-line interfaces.

For installation instructions, dataset access, disk requirements, and the recommended reproduction workflow, see the [main README](../README.md).

## 1. Module Overview

| File | Responsibility |
|---|---|
| `__init__.py` | Defines the Python package. |
| `download_dataset.py` | Selects the dataset release, downloads recordings while excluding acquisition logs, verifies checksums, and safely extracts archives. |
| `bag_io.py` | Reads recorded images, calibration data, and transforms; pairs RGB/depth timestamps; and recovers usable data from the known damaged recording. |
| `extract.py` | Discovers recordings, selects target frames, computes depth measurements and temporal pixel statistics, and writes extraction checkpoints. |
| `analyze.py` | Performs per-recording plane fitting, image-profile analysis, bootstrap summaries, and boundary statistics. Records summaries in the analysis manifest. |
| `analysis_math.py` | Implements numerical methods for resampling, plane fitting, profiles, and marker-boundary geometry. |
| `analysis_tables.py` | Aggregates results from all 288 recordings into CSV/NPZ tables and maps numerical results to paper outputs. |
| `render.py` | Registers bundled fonts, validates analysis inputs, and generates selected or complete figures and tables with an output manifest. |
| `render_plots.py` | Produces depth distributions, condition summaries, temporal maps, boundary panels, residual maps, and point-cloud visualizations. |
| `render_tables.py` | Generates the seven computed tables in CSV and LaTeX formats using the manuscript layouts. |
| `storage.py` | Manages staging directories and preserves intermediate files on success or failure. |
| `incremental.py` | Processes recordings sequentially, validates checkpoints, removes eligible raw downloads from the dedicated cache, and exports numerical and rendered results. |

## 2. Command-Line Interface

All examples assume that:

- Your terminal is in `paper_reproduction/`, the directory containing `main.py`.
- Python dependencies are installed and the virtual environment is activated.
- Relative paths supplied explicitly are resolved from the terminal's current working directory.

Default paths are located relative to `main.py`, regardless of the working directory.

Run the following command to see all available subcommands:

```bash
python main.py --help
```

### 2.1 `download` — Download the Dataset

Downloads and verifies the dataset recordings from IIT Dataverse.

```bash
python main.py download [--dataset PATH] [--stream] [--workers N]
```

| Argument | Description | Default |
|---|---|---|
| `--dataset PATH` | Destination directory for downloaded recordings and release metadata. | `dataset/` |
| `--stream` | Verifies and extracts directly from network streams without retaining compressed archives. | Disabled |
| `--workers N` | Number of concurrent archive downloads; must be a positive integer. | `1` |

**Example:**

```bash
python main.py download --stream --workers 4
```

**Behavior and requirements:**

- Downloads all 288 recordings, excluding acquisition logs.
- Verifies checksums and safely extracts the archives.
- Reuses previously completed and verified extractions.
- Attempts public access by default; authenticated access is available through `DATAVERSE_TOKEN`.
- Retains compressed archives unless `--stream` is specified.

For disk-space requirements and authentication setup, see the [main README](../README.md).

### 2.2 `extract` — Extract Measurements

Processes raw recordings to extract the measurements required for subsequent analysis.

```bash
python main.py extract [--dataset PATH] [--output PATH] [--recording NAME]
```

| Argument | Description | Default |
|---|---|---|
| `--dataset PATH` | Root directory containing extracted recordings. | `dataset/` |
| `--output PATH` | Root directory for extracted measurements, inventory, and checkpoints. | `analysis/` |
| `--recording NAME` | Process a single recording identified by its directory name. | All discovered recordings |

**Example — extract all recordings:**

```bash
python main.py extract \
  --dataset dataset \
  --output results/analysis
```

**Example — extract one recording:**

```bash
python main.py extract \
  --dataset dataset \
  --output results/analysis \
  --recording rsf_0400_sd_artificial
```

The command generates extraction artifacts and checkpoints that are subsequently consumed by `analyze`.

### 2.3 `analyze` — Compute Numerical Results

Computes per-recording statistics and, when the complete dataset is available, aggregates the numerical results.

```bash
python main.py analyze [--dataset PATH] [--output PATH] [--recording NAME]
```

| Argument | Description | Default |
|---|---|---|
| `--dataset PATH` | Root directory containing the same recordings used during extraction. | `dataset/` |
| `--output PATH` | Existing extraction root; analysis results are written under `derived/`. | `analysis/` |
| `--recording NAME` | Analyze only the specified extracted recording. | All 288 recordings |

**Example — analyze the full dataset:**

```bash
OPENBLAS_NUM_THREADS=1 python main.py analyze \
  --dataset dataset \
  --output results/analysis
```

**Prerequisites and limitations:**

- Extraction must be completed before analysis.
- Full-dataset aggregation requires the complete 288-recording experimental design.
- A single-recording analysis does not generate aggregate tables requiring multiple recordings.
- `OPENBLAS_NUM_THREADS=1` limits numerical-library threading and is recommended for analysis commands.

The analysis stage stores derived results in the analysis directory, including per-recording summaries and associated manifest information.

### 2.4 `render` — Generate Figures and Tables

Generates paper figures and tables from previously computed analysis results.

```bash
python main.py render [--output PATH] [--destination PATH] [--figure NAME ...]
```

| Argument | Description | Default |
|---|---|---|
| `--output PATH` | Existing extraction/analysis directory containing the required computed results. | `analysis/` |
| `--destination PATH` | Parent directory for generated `figures/`, `tables/`, and `render_manifest.json`. | Directory containing `main.py` |
| `--figure NAME ...` | One or more figure paths relative to `figures/`. An optional `.pdf` suffix is accepted. | All figures and tables |

**Example — render all outputs:**

```bash
python main.py render \
  --output results/analysis \
  --destination results
```

**Example — render selected figures:**

```bash
python main.py render \
  --output results/analysis \
  --destination selected \
  --figure revision/temporal_maps revision/plane_residual_frame150_1800_hd_natural
```

**Behavior and requirements:**

- Rendering reads previously computed analysis results; it does not reopen raw recordings.
- Complete rendering requires full-dataset aggregate tables.
- Selected rendering produces only the requested figures, provided all required recording analyses are available.
- Figure and table outputs are recorded in `render_manifest.json`.

### 2.5 `all` — Run the Complete Analysis Pipeline

Executes extraction, numerical analysis, and rendering in sequence.

```bash
python main.py all [--dataset PATH] [--output PATH] [--destination PATH]
```

| Argument | Description | Default |
|---|---|---|
| `--dataset PATH` | Root directory containing all 288 extracted recordings. | `dataset/` |
| `--output PATH` | Directory for extraction and analysis artifacts, created or reused as appropriate. | `analysis/` |
| `--destination PATH` | Parent directory for generated figures, tables, and rendering manifest. | Directory containing `main.py` |

**Example:**

```bash
OPENBLAS_NUM_THREADS=1 python main.py all \
  --dataset dataset \
  --output results/analysis \
  --destination results
```

**Important:**

- The dataset must already be downloaded and extracted; `all` does not download recordings.
- All 288 recordings are required for complete reproduction.
- Dataset and analysis directories must be separate directory trees.
- The rendering destination must be outside the analysis input directory tree.

This is the recommended command when the full extracted dataset is already available.

## 3. Incremental Processing

Incremental commands reproduce the paper results without retaining the complete raw dataset.

Recordings are downloaded, processed, and cleaned up sequentially. Validated checkpoints allow interrupted executions to resume.

Both commands share the same options:

```bash
OPENBLAS_NUM_THREADS=1 python main.py incremental_download \
  [--cache PATH] [--output PATH] [--destination PATH]

OPENBLAS_NUM_THREADS=1 python main.py incremental_all \
  [--cache PATH] [--output PATH] [--destination PATH]
```

| Argument | Description | Default |
|---|---|---|
| `--cache PATH` | Dedicated download cache. Must be new or empty on first use; eligible raw files are deleted after successful processing. | `incremental_cache/` |
| `--output PATH` | Analysis directory, created on the first run and reused when resuming. | `results/analysis/` |
| `--destination PATH` | Parent directory reserved for rendering outputs. Must remain unchanged when resuming. | `results/` |

### 3.1 `incremental_download` — Numerical Results Only

Downloads and analyzes the recordings incrementally, then exports the complete numerical results.

```bash
OPENBLAS_NUM_THREADS=1 python main.py incremental_download
```

The command performs:

1. Download and extraction of individual recordings.
2. Per-recording measurement extraction and numerical analysis.
3. Checkpoint validation.
4. Safe removal of eligible raw downloads from the dedicated cache.
5. Export of complete numerical tables.

**Figures and rendered manuscript tables are not generated by this command.**

Use it when the numerical results are sufficient or when rendering will be performed later.

### 3.2 `incremental_all` — Complete Reproduction

Performs incremental downloading and analysis, exports numerical tables, and generates the paper figures and tables.

```bash
OPENBLAS_NUM_THREADS=1 python main.py incremental_all
```

This is the recommended low-disk reproduction command.

It performs the same numerical processing as `incremental_download`, followed by the rendering stage.

If `incremental_download` has already completed, `incremental_all` can reuse its validated results, provided the same paths and compatible checkpoints are retained.

### 3.3 Resuming and Data Safety

Both incremental commands support checkpoint-based resumption.

To resume, repeat the original command with the **same `--cache`, `--output`, and `--destination` paths**.

The following safeguards apply:

- Completed checkpoints are validated before reuse.
- Checkpoints are validated before raw downloads are removed.
- Failed or incomplete transfers are preserved.
- Only eligible raw files within the dedicated incremental cache are removed.
- Existing datasets are never deleted.
- The cache must be separate from the analysis and rendering output trees.
- The rendering destination is reserved by both commands, even when no rendering is requested.

Do not manually remove cache metadata, manifests, or analysis checkpoints if you intend to resume an interrupted run.

## 4. Dataset Authentication

The following commands support optional IIT Dataverse authentication:

- `download`
- `incremental_download`
- `incremental_all`

If authentication is required, set the `DATAVERSE_TOKEN` environment variable before running the command:

```bash
export DATAVERSE_TOKEN='PASTE_YOUR_OWN_TOKEN_HERE'
```

The variable is read from the invoking shell and is not automatically stored by Python virtual-environment activation.

Public downloads are attempted without credentials when the variable is unset.

**Do not commit API tokens to the repository.**

To remove the token from your current shell session:

```bash
unset DATAVERSE_TOKEN
```

For instructions on obtaining a token, see the [IIT Dataverse](https://dataverse.iit.it/) website or the [official Dataverse account guide](https://guides.dataverse.org/en/6.6/user/account.html#api-token).

## 5. Command Summary

| Command | Requires raw dataset | Downloads data | Main output |
|---|---|---|---|
| `download` | No | Yes | Extracted recordings |
| `extract` | Yes | No | Measurements and extraction checkpoints |
| `analyze` | Yes | No | Per-recording analysis and aggregate numerical tables |
| `render` | No | No | Figures and rendered tables |
| `all` | Yes | No | Complete analysis, figures, and tables |
| `incremental_download` | No | Yes | Complete numerical results, without retaining raw recordings |
| `incremental_all` | No | Yes, as needed | Complete numerical and rendered results, without retaining raw recordings |

For command-specific help, use:

```bash
python main.py <command> --help
```

For example:

```bash
python main.py incremental_all --help
```

For a step-by-step reproduction guide, return to the [main README](../README.md).
