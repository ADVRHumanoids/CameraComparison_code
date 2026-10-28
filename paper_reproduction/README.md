# Reproduce the Paper Results

This directory contains the code needed to reproduce the numerical analyses, figures, and tables reported in the paper.

The reproduction pipeline is self-contained and runs independently of the rest of the repository. **ROS, camera SDKs, and acquisition hardware are not required.**

The main entry point is `main.py`. It can download the dataset, extract measurements, perform the analysis, and generate the paper's figures and tables.

## 1. Requirements and Setup

You will need:

- **Python 3.12**
- An internet connection to download the dataset
- Sufficient disk space for your chosen workflow (see below)

### Choose a reproduction workflow

There are two ways to reproduce the results:

| | Low-disk workflow (recommended) | Full-dataset workflow |
|---|---|---|
| Disk space | Approximately 30 GB | Approximately 420 GB, plus working space |
| Downloads | One recording at a time | All 288 recordings |
| Raw dataset retained | No | Yes |
| Numerical results | Complete | Complete |
| Figures and tables | Complete | Complete |
| Best for | Reproducing the paper | Reusing or inspecting raw data |

**Recommendation:** Use the low-disk workflow unless you specifically need to retain the complete raw dataset.

Both workflows compute the same paper results. The difference is how the raw recordings are downloaded, stored, and processed.

### Create a Python environment

Open a terminal in this directory and run:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate the environment using:

```powershell
.venv\Scripts\Activate.ps1
```

All subsequent commands assume the environment is activated and your terminal is in this directory.

**Fonts:** Figure rendering uses Liberation Serif from the included `fonts/` directory and DejaVu Sans provided by Matplotlib. No additional system font installation is necessary. Keep `fonts/` alongside the code.

## 2. Dataset Access

The dataset is hosted on [IIT Dataverse](https://dataverse.iit.it/).

Public files can be downloaded without authentication. If Dataverse requires authentication, obtain an API token:

1. Sign in to IIT Dataverse.
2. Open the menu under your account name.
3. Select **API Token**.
4. Select **Create Token**, or copy an existing token.

For details, consult the [Dataverse API token guide](https://guides.dataverse.org/en/6.6/user/account.html#api-token).

Set the token in the terminal before running the pipeline:

```bash
export DATAVERSE_TOKEN='PASTE_YOUR_OWN_TOKEN_HERE'
```

Replace the placeholder with your actual token.

The `download`, `incremental_download`, and `incremental_all` commands read this environment variable automatically.

**Security notes:**

- Never commit an API token to the repository.
- The token applies only to the current shell session.
- Activating a Python environment does not automatically configure the token.
- Public downloads do not require a token.

When finished, you can remove it with:

```bash
unset DATAVERSE_TOKEN
```

## 3. Option A — Reproduce Results with Limited Disk Space (Recommended)

This workflow reproduces the complete analysis without storing the full extracted dataset.

**Required disk space:** approximately 30 GB, including compact results and working space.

Run:

```bash
OPENBLAS_NUM_THREADS=1 python main.py incremental_all
```

### What this command does

The pipeline automatically:

1. Downloads a recording from Dataverse.
2. Extracts its measurements.
3. Computes the corresponding analysis.
4. Saves and verifies the analysis results.
5. Removes the raw recording downloaded into its dedicated cache.
6. Continues with the remaining recordings.
7. Exports the complete numerical tables.
8. Renders the paper figures and tables.

Recordings are processed incrementally, grouped by illumination and distance.

### Output directories

| Directory | Contents |
|---|---|
| `results/` | Saved analysis, exported tables, and rendered results |
| `incremental_cache/` | Download progress and temporary raw data |

**Important:**

- The largest individual raw recording is approximately 2.3 GB.
- Failed or incomplete downloads are preserved and may occupy additional disk space.
- The pipeline only deletes raw files downloaded into its dedicated incremental cache.
- It refuses to operate on an existing dataset to avoid unintended deletion.

### Resume an interrupted run

Run the same command again:

```bash
OPENBLAS_NUM_THREADS=1 python main.py incremental_all
```

Completed, validated work is reused automatically.

**Do not delete `results/` or `incremental_cache/` between runs.** Both directories are needed to resume safely.

### Generate numerical results without rendering

If you only need the measurements and numerical analysis, run:

```bash
OPENBLAS_NUM_THREADS=1 python main.py incremental_download
```

This downloads and processes recordings, cleans up raw files, and exports numerical results without generating the final figures and tables.

You can render them later with:

```bash
OPENBLAS_NUM_THREADS=1 python main.py incremental_all
```

Using the same paths allows the pipeline to reuse the completed analysis rather than processing the recordings again.

## 4. Option B — Download the Complete Dataset

Choose this workflow if you want to keep the raw recordings for inspection, additional experiments, or repeated analysis. The `all` command downloads the dataset automatically when the target folder does not exist, then runs extraction, analysis, and rendering.

**Disk requirements:**

- Approximately **420 GB** for the extracted dataset
- Additional space for analysis outputs and temporary files (with working-space overhead of up to approximately 1 GB)
- Approximately **144 GB of additional storage** if compressed archives are retained instead of streamed

### Run the complete pipeline

```bash
OPENBLAS_NUM_THREADS=1 python main.py all \
  --dataset dataset \
  --output results/analysis \
  --destination results
```

1. Extracts measurements from the recordings.
2. Computes the complete analysis.
3. Generates the paper figures and tables.

If the dataset is alredy present, it reads the dataset in place and does not download any additional files.

A complete run requires all 288 recordings and may take considerable time, depending on your hardware and storage performance.

### Generated outputs

| Directory | Contents |
|---|---|
| `results/analysis/recordings/` | Measurements extracted from individual recordings |
| `results/analysis/derived/` | Per-recording analyses and complete CSV/NPZ data tables |
| `results/figures/` | 43 figures, each exported as PDF and PNG |
| `results/tables/` | Seven tables, each exported as CSV and LaTeX |

The LaTeX tables are manuscript-ready fragments rather than standalone LaTeX documents.

**Not generated:** Hardware photographs, experimental setup diagrams, and fixed specification tables are not produced by this pipeline.

## 5. Advanced Usage

The following commands are useful for debugging, partial reproduction, or working with existing analysis results.

### Run individual processing stages

Instead of executing the complete pipeline with `all`, run each stage separately:

**Extract measurements:**

```bash
python main.py extract \
  --dataset dataset \
  --output results/analysis
```

**Compute analysis:**

```bash
OPENBLAS_NUM_THREADS=1 python main.py analyze \
  --dataset dataset \
  --output results/analysis
```

**Render figures and tables:**

```bash
python main.py render \
  --output results/analysis \
  --destination results
```

Use the same dataset and analysis directories throughout.

### Process a single recording

To inspect or test the pipeline without processing the complete dataset:

```bash
python main.py extract \
  --dataset dataset \
  --output example/analysis \
  --recording rsf_0400_sd_artificial
```

Then run:

```bash
OPENBLAS_NUM_THREADS=1 python main.py analyze \
  --dataset dataset \
  --output example/analysis \
  --recording rsf_0400_sd_artificial
```

This produces the measurements and analysis for the selected recording.

**Limitation:** Figures and tables that combine information from multiple recordings cannot be reproduced from a single-recording analysis.

### Render selected figures

If the required analysis results already exist, you can render specific figures:

```bash
python main.py render \
  --output results/analysis \
  --destination selected \
  --figure revision/temporal_maps revision/plane_residual_frame150_1800_hd_natural
```

Each selected figure requires the analysis results for all recordings on which it depends.

## 6. Paths, Checkpoints, and Reruns

### Default directories

Unless explicitly specified, paths are relative to the directory containing `main.py`.

| Path | Purpose |
|---|---|
| `dataset/` | Downloaded and extracted raw recordings |
| `analysis/` | Extracted measurements and numerical analysis |
| `figures/` | Rendered figures |
| `tables/` | Exported tables |

When using explicit relative paths, they are interpreted relative to the terminal's current working directory.

The full-dataset examples above place outputs in `results/` to keep generated files separate from the input data.

### Resuming and reusing results

The pipeline supports checkpoint-based execution.

When a command is repeated, completed and unchanged work can be reused after validation.

To preserve reproducibility:

- Keep generated manifests alongside their associated outputs.
- Do not manually modify intermediate results.
- Preserve checkpoint directories when resuming interrupted runs.
- Follow the error message if validation indicates that a fresh analysis or output directory is required.

Changes to the code, installed dependencies, input recordings, or generated outputs may invalidate existing checkpoints.

Interrupted staging files and existing outputs are preserved rather than silently overwritten or deleted.

## 7. Known Dataset Limitation

Full extraction reserves 2 MiB per recording plus 512 MiB for working space; this
is based on the verified full output size rather than the raw dataset size.

One recording in the dataset is known to be damaged.

It contains **155 recoverable pairs instead of the expected 300**.

The pipeline handles this condition and reports the missing data.

## 8. Help and Command Reference

To inspect the available commands:

```bash
python main.py --help
```

For detailed help on a specific command:

```bash
python main.py download --help
python main.py all --help
python main.py incremental_all --help
```

The complete command-line reference, including all arguments and options, is available in [scripts/README.md](scripts/README.md).

---

## Quick Reference

For most users, the following commands are sufficient.

**Reproduce the entire paper with approximately 30 GB of disk space:**

```bash
OPENBLAS_NUM_THREADS=1 python main.py incremental_all
```

**Reproduce the entire paper from an existing extracted dataset:**

```bash
OPENBLAS_NUM_THREADS=1 python main.py all \
  --dataset dataset \
  --output results/analysis \
  --destination results
```

Both workflows generate the numerical analyses, computed tables, and figures required to reproduce the paper's computational results.
