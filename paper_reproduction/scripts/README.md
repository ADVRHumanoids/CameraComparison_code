# Internal scripts

Invoke scripts through `../main.py`; paths are resolved by that entry point.

`download_dataset.py` contains the release-1.0 downloader and safe archive
extraction code. It uses Python 3.12+ standard-library modules and excludes
acquisition logs. All 288 published archives have been streamed, checksum-verified
and extracted; a repeat download command successfully reused them. See the parent
README for disk requirements and retained-archive versus streaming modes.

`extract.py` inventories recordings, validates checkpoint identities and available
space, selects accepted target frames, accumulates moments, and publishes compact
per-recording artifacts. `bag_io.py` handles image conversion, TF traversal,
calibration validation, exact timestamp pairing, and CRC-checked recovery of the
single known damaged bag. Run `main.py extract --dataset PATH`; an optional
`--recording NAME` limits work, and `--output PATH` changes the artifact destination.

The numerical methods are adapted from `revision_analysis/analyze.py` and its
recovery code, but these standalone modules import no surrounding repository code.
Acquisition logs and historical cross-checks have been removed. Marker selection
and the mean-error cutoff precede every temporal update. No image videos are saved.

`analyze.py` validates extraction inputs, rereads accepted depth frames for plane
fits and profiles, derives temporal boundary statistics, and publishes complete
per-recording numerical artifacts. `analysis_math.py` retains the existing plane,
profile, boundary, and moving-block bootstrap formulas. `analysis_tables.py`
exports complete-design aggregate tables and the computed-paper coverage inventory.

Use `main.py analyze --dataset PATH [--recording NAME] [--output PATH]`, where
`--output` identifies the existing extraction root. Focused analyses do not touch
full-dataset tables. `derived/recordings/NAME/manifest.json` fingerprints both code
and extraction inputs and hashes outputs before they can be reused. Geometry and
profile fits share one streaming bag pass; boundary analysis uses extracted moments
and the first accepted RGB crop. No dependencies were added for this stage.

The numerical methods are adapted from `revision_analysis/summarize.py`,
`analyze_plane_inclination.py`, `appendix_d/run.py`, `image_error_profiles/run.py`,
and `analyze_boundaries.py`. No imports or data dependencies on those locations
remain. Historical reconciliation and unrelated revision plots/reports are omitted.

`render.py` validates cached inputs, stages outputs and publishes selected/all
figures and tables. `render_plots.py` implements active plot families using the
original conventions. `render_tables.py` fills current layout templates from CSVs.
Use `main.py render [--output ANALYSIS]
[--destination PATH] [--figure PATH ...]`. Rendering reads no raw bags, logs,
reference assets or surrounding repository code and performs no network access.

Plotting methods are adapted from `plot_results.py`, `prepare_paper_revision.py`,
`configuration_envelope_no_bias/plot.py`, `plane_residual_heatmaps/plot.py` and
`unify_bag_analysis.py`. Table templates reflect the active appendix formatting.
Analysis additionally retains the original 25%-padding first-RGB context in
`boundary_reference.npz`; this changes analysis fingerprints, not numerical rules.

`storage.py` preserves staging directories on success, interruption and failure.
No production stage removes earlier files. `main.py all` runs extraction, analysis
and rendering; downloading is a separate explicit command. Image pairing allows
up to the recording limit of 300 pending timestamps, because some published bags
deliver long RGB bursts before matching depth messages. Exact timestamps, stable
calibration, duplicate checks and final completeness checks remain enforced.
