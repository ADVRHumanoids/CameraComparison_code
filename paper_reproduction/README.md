# Standalone paper reproduction

Reproduce the computed results in `MainSensors.tex` and its active appendices,
using the recorded ROS 2 bags without camera hardware. This folder is being
delivered incrementally and is intended to work when copied outside the repository.

**Current delivery: all five increments completed and verified.** All 288 bags
were downloaded and the full pipeline passed from a copy outside the repository.
This run preserves every existing file, failed transfer and staging directory; it performs no cleanup or deletion.

The new data is downloaded into `dataset/`; analysis reads it in place. Acquisition
logs, historical checks, fixed specification tables, photographs, setup diagrams,
and bundled copies of reference figures are outside the reproduction outputs.

## Layout

| Path | Responsibility |
| --- | --- |
| `main.py` | User entry point; provides `download`, `extract`, `analyze`, `render`, and `all` |
| `scripts/` | Internal implementation, with no imports from the surrounding repository |
| `tests/` | Downloader, extraction, analysis and rendering tests |
| `dataset/` | Downloaded bags, preserving illumination/distance directories |
| `analysis/` | Generated CSV/NPZ measurements and extraction provenance |
| `figures/` | Computed PDF/PNG figures matching manuscript paths |
| `tables/` | Computed CSV/LaTeX result tables |
| `validation/` | Labelled render-validation outputs and comparison report |
| `full_run/` | Fresh full-dataset analysis and rendering; earlier outputs are preserved |

Every directory has its own README. Generated data and artifacts are ignored by Git.

## Requirements

Use **Python 3.12** for bag extraction, with the numerical versions pinned in
`requirements.txt`. ROS and camera SDKs are not required. The downloader uses only
the Python 3.12+ standard library, including `lzma`; it does not require `curl` or
`jq`. Rendering requires Matplotlib 3.10.8 and the other pinned dependencies,
Liberation Serif and DejaVu Sans fonts.

For a new analysis environment (no dataset download):

```bash
python3.12 -m venv /path/to/reproduction-env
/path/to/reproduction-env/bin/python -m pip install -r /path/to/paper_reproduction/requirements.txt
```

## Extract measurements from the existing dataset

For a focused run, from any working directory:

```bash
/path/to/reproduction-env/bin/python /path/to/paper_reproduction/main.py extract \
  --dataset /path/to/CameraComparisonDataset \
  --recording rsf_0400_sd_artificial
```

Omit `--recording` to process all 288 recordings. Full extraction reads approximately
386 GB sequentially; it does not copy bags. Outputs default to `analysis/` beside
`main.py`. Use `--output /path/to/new-analysis` for a separate extraction.
Always supply `--dataset` while using the repository's existing recordings.

The extractor inventories all recordings even during a focused run. It reads only
bag manifests and recorded RGB/depth, calibration, and TF messages. No `.txt`
acquisition logs, historical comparisons, prior result caches, network services,
or code outside this folder are used.

Each recording is published as a complete artifact directory. Rerunning reuses it
only when code/dependency identities, input metadata hash, raw sizes/mtimes, and
output checksums agree. Changed inputs/code or modified outputs produce an error
and require a fresh `--output` directory. It never silently overwrites results.
Raw bags are not hashed in a second pass; same-size changes that preserve raw
modification times are outside this identity check.

The preflight budget is 16 MiB per selected recording plus a 1 GiB free-space
margin, checked again before publishing each recording. No full image sequences
or per-frame snapshot collections are retained. A focused run is marked
`focused_complete`, never as a complete dataset analysis.

See [analysis/README.md](analysis/README.md) for artifact schemas and selection
rules, and [tests/README.md](tests/README.md) for validation commands/results.

## Derive the paper measurements

After extracting a recording, analyze it with:

```bash
OPENBLAS_NUM_THREADS=1 /path/to/reproduction-env/bin/python /path/to/paper_reproduction/main.py analyze \
  --dataset /path/to/CameraComparisonDataset \
  --recording rsf_0400_sd_artificial
```

`--output` has the same meaning as for `extract`: the extraction root, defaulting
to `analysis/` beside `main.py`. Derived artifacts go into its `derived/` subfolder.
The command checks extraction fingerprints and rereads recorded depth once per
analyzed recording to fit planes and native image profiles. No new marker detection,
log parsing, historical comparison, reference-asset copying, or plotting occurs.

Omit `--recording` only after all 288 recordings have been extracted. That run
reuses valid per-recording analysis checkpoints and also exports complete global
CSV/NPZ tables. A focused run writes only its recording artifacts and coverage
inventory; it never publishes or overwrites full-dataset tables. Missing extraction
outputs stop a full run before it starts numerical work.

`derived/coverage.json` links inputs and generating scripts for the 43 computed
figure files, seven result tables, and numerical text results. It contains asset
names and data paths, not copies of the paper assets. Plane fits, profiles,
boundary statistics, comparison tables, and retained example pixels will supply
step 4's renderer without reopening raw bags.

Moving-block bootstrap arrays use 2,000 resamples and a deterministic seed per
recording, with half/double block-length sensitivity and reliability flags. These
intervals characterize within-recording variability and do not estimate independent
setup or device repeatability. Matched modes/cameras are independent acquisitions;
their unrelated frame indices are never treated as paired samples.

## Render figures and tables

After completing extraction and analysis for all recordings:

```bash
python /path/to/paper_reproduction/main.py render
```

`--output PATH` selects an existing analysis root. `--destination PATH` selects
the parent of generated `figures/` and `tables/` folders, defaulting beside
`main.py`. Rendering uses only cached artifacts, with no raw-bag or network access.
Full rendering requires complete 288-recording tables and emits 43 PDF/PNG figure
pairs and seven CSV/LaTeX table pairs.

To render explicitly selected examples before processing the complete dataset:

```bash
python /path/to/paper_reproduction/main.py render \
  --figure revision/temporal_maps revision/plane_residual_frame150_1800_hd_natural
```

Identifiers are manuscript paths below `figures/`, optionally ending in `.pdf`.
Each selected figure still requires every input: all four cameras for temporal or
residual maps, both point clouds for shared axes, and Mini LIGHT/PLUS for the
boundary example. Distribution/condition-summary figures need global tables.
Selected runs create no partial paper figures or tables. Missing or changed inputs
stop the run before plotting. Output is staged; existing unowned files and edited
previous outputs are preserved with an error. Use a new `--destination` in that case.

`render_manifest.json` records the latest selection/input/source/font hashes and
cumulative output checksums. PDF metadata dates may vary; visual comparisons use
decoded PNGs and rasterized PDFs.

During increment 4, all 43 PNGs matched active manuscript images pixel for pixel,
and all 43 PDFs matched when rasterized at 72 dpi. All seven generated LaTeX tables matched active
table content/formatting ignoring whitespace, and the manuscript-width Palatino
preview compiled. Seven example figures in `figures/` use new standalone outputs
from 15 processed recordings. Full renderer validation used an isolated adapter of
existing revision numerical data plus these standalone example caches. That increment tested
rendering; the subsequent full downloaded-dataset verification is documented below. Generated validation outputs
and the measured report are labelled under [validation/](validation/README.md).
No reference figure/table files are bundled.

The original boundary RGB crop is now retained during analysis as
`boundary_reference.npz` with 25%-of-marker-span padding (minimum 12 px). Earlier
derived checkpoints were preserved in `analysis/derived_before_render/` and
`analysis/derived_crop20/` while verifying the crop. Runtime never reads those
directories; older analysis checkpoints require regeneration under the updated code.

## Download the dataset

The code targets [IIT Dataverse release 1.0](https://doi.org/10.48557/LUONQB).
It selects exactly the 288 expected recording archives and the dataset README;
acquisition log archives are never selected. By default compressed archives are
retained. The `--stream` mode verifies and extracts directly from the network
without storing compressed archives. The published README is saved as
`dataset/DATASET_README.md`, preserving this folder's usage documentation.

For a download that fits storage for extracted bags but not both bags and archives:

```bash
python3 /path/to/paper_reproduction/main.py download --stream --workers 4
```

The default destination is `dataset/` beside `main.py`, independently of the
working directory. A separate destination can be supplied:

```bash
python3 /path/to/paper_reproduction/main.py download --dataset /large-disk/camera-dataset
```

The worker count defaults to one. Concurrent transfers have independent staging
directories and checksums; failed transfers are reported and preserved while
other transfers finish. Rerunning skips completed, verified extractions.
Public access is attempted without credentials. If Dataverse requires a token,
set `API_TOKEN` in the environment; the script does not print or save it.

Retained-archive mode needs approximately **144 GB of archives plus 380–410 GB of
extracted bags**, with filesystem headroom. Streaming needs space for extracted
bags only; it does not create and delete archive files. Interrupted staging also
occupies space and is deliberately preserved. The code reserves 1 GiB and checks each extraction's
space needs, but it does not reserve space against other processes.

## Integrity and recovery behavior

- Downloaded archives are accepted only after checking their published size and
  checksum. Existing matching archives are checked and skipped.
- Interrupted archive downloads stay in uniquely named `.part-*` files. A retry
  starts a new file and preserves previous partial work. Completed archives remain.
- Streaming hashes every compressed byte and checks the published size/checksum
  before publishing an extraction. Failed or interrupted streams stay in hidden
  `.stream-*` directories and are never treated as complete recordings.
- Existing final files that fail verification are preserved and cause an error.
  Inspect or relocate them before retrying; the code does not delete them.
- Archive extraction accepts regular files/directories only, rejects unsafe
  paths and links, and uses Python's `data` extraction filter.
- A recording is extracted into a temporary sibling directory, checked for
  `metadata.yaml` and MCAP files, then renamed into place. Failed extraction
  staging is preserved on failure; any retained source archive is also preserved.
- A completion marker records the archive checksum and extracted file sizes.
  Repeat runs check these before skipping an extraction. Extracted MCAP contents
  are not rehashed; archive checksums verify the downloaded source bytes.
- Existing recording directories without this tool's completion marker are
  preserved and cause an error. This prevents merging into existing datasets.
- `release_metadata.json` records the release response, which may list logs;
  this is dataset metadata, not acquisition log content. No log archive is fetched.

## Delivered increments

2. **Delivered:** bag extraction from `--dataset PATH`, per-recording validation,
   checkpoints, and explicit partial-bag recovery.
3. **Delivered:** derived CSV/NPZ analysis, plane geometry, profiles, boundaries,
   matched comparisons, complete-design export, and coverage inventory.
4. **Delivered:** figure/table rendering, source/input/font hashes, active-manuscript
   visual comparisons.
5. **Delivered:** checksum-verified download of all 288 recordings and a successful
   standalone `all` run, with full comparisons against the paper and revision data.

The `all` command runs extraction → analysis → rendering without implicitly
downloading data. To preserve the earlier incremental outputs, the full run uses:

```bash
OPENBLAS_NUM_THREADS=1 python /path/to/paper_reproduction/main.py all \
  --dataset /path/to/paper_reproduction/dataset \
  --output /path/to/paper_reproduction/full_run/verified_analysis \
  --destination /path/to/paper_reproduction/full_run
```

Recordings can be extracted/analyzed as downloads arrive: hidden transfer staging
is ignored and bootstrap seeds use the canonical full design, independent of
arrival order. All pipeline staging is retained. Earlier incremental and render
validation outputs remain separate from the new full run.

## Full downloaded-dataset verification

The completed production run is in [full_run/](full_run/README.md), separate from
all earlier incremental and reference-adapter validation outputs. Its input was
413,770,683,740 bytes of freshly downloaded bags; the 288 compressed streams were
checked against published checksums before publication. No acquisition logs or
compressed archives were saved. A repeat download command verified/reused all
recordings and exited successfully.

The standalone `all` command exited successfully from a code-only copy outside the
repository. New results include 86,255 available image pairs, 86,228 accepted pairs,
27 exclusions and 264 boundary-eligible recordings. All 288 bootstrap, temporal
pixel, profile and plane arrays match `revision_analysis` exactly; summary CSV
rounding differences are below 4e-15. All 43 PNGs match active paper images pixel
for pixel, all 43 PDFs match after rasterization at 72 dpi, and all seven computed
LaTeX tables match ignoring whitespace. The suite passes
36 tests; test fixtures were also preserved during this no-deletion run.

See [verification.json](full_run/verification.json) for measured results. The production measurement root
is `full_run/verified_analysis/`. Reference data was read only for comparison,
never as input to this production analysis or rendering.

Full-dataset testing exposed RGB bursts longer than eight messages in a published
bag. Exact-time pairing now permits up to the 300-frame recording limit, with a
regression test for delayed depth and overflow. Earlier outputs remain in
`full_run/analysis/`; current outputs have fresh code/dependency fingerprints.
The known damaged `zedx_3000_hd_neural_natural` bag yields 155 CRC-checked pairs;
its 145 unavailable pairs are reported, never imputed. PDF byte identity was not
required: PDF visual comparisons were performed at 72 dpi.
