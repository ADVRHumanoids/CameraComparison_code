# Camera Comparison Dataset

## Overview

This dataset was collected as part of a research project investigating camera performance and depth estimation across different acquisition conditions.

It contains recordings from multiple camera configurations, captured under artificial and natural lighting conditions at different target distances.

The dataset includes:

- **ROS 2 bag recordings** containing the acquired sensor data, stored in MCAP format.
- **Acquisition logs** containing information recorded during the experiments.
- **Recording metadata** describing the corresponding ROS 2 bags.

The dataset is organized consistently by lighting condition, acquisition distance, and camera configuration.

This README describes the dataset structure, file naming conventions, and procedures for downloading and extracting the data from [IIT Dataverse](https://dataverse.iit.it/).

**Dataset DOI:** [10.48557/LUONQB](https://doi.org/10.48557/LUONQB)

## 1. Dataset Size and Storage Requirements

The complete dataset is large. Check the available disk space before downloading or extracting the recordings.

| Format | Approximate size |
|---|---|
| Compressed archives | 140 GB |
| Fully extracted dataset | 380 GB |

**Important:** Downloading and extracting the dataset while retaining the compressed archives requires space for both formats, plus temporary working files.

The downloader supports multiple operating modes, including extraction and removal of compressed archives after successful decompression.

For users who only need the experimental logs, a separate download option avoids transferring the full recording dataset.

Ensure sufficient free disk space before starting. Interrupted downloads or failed extractions may leave incomplete files that require additional space.

## 2. Dataset Organization

The dataset contains recordings acquired under two lighting conditions:

- `artificial/` — Controlled artificial illumination.
- `natural/` — Natural illumination.

Both environments follow the same directory structure.

### 2.1 Top-Level Structure

```text
root/
├── README.md
├── artificial/
└── natural/
```

### 2.2 Acquisition Distances

Within each environment, recordings are grouped by acquisition distance.

Directory names represent distances in millimeters, using four digits.

For example, `0400` corresponds to 400 mm.

```text
artificial/
├── 0400/
├── 0600/
├── 0800/
├── 1000/
├── 1400/
├── 1800/
├── 2200/
├── 2600/
└── 3000/
```

The `natural/` directory contains the same distance subdirectories.

The dataset therefore includes:

| Property | Value |
|---|---|
| Lighting conditions | 2 |
| Acquisition distances | 9 |
| Camera configurations per condition and distance | 16 |
| Total recording configurations | 288 |

Each environment-distance combination contains a complete set of recordings for the 16 camera configurations.

### 2.3 Recording Naming Convention

Recording names encode the camera, acquisition distance, resolution or operating mode, and lighting condition.

The general convention is:

```text
<camera>_<distance>_<configuration>_<environment>
```

For Intel RealSense cameras, the configuration identifies the resolution mode (`hd` or `sd`).

For ZED cameras, the configuration additionally identifies the neural depth mode when applicable.

Examples:

```text
rsf_0400_hd_artificial
rsi_0400_sd_artificial
zedx_0400_hd_neural_artificial
zedxm_0400_sd_neural_plus_artificial
```

Here:

- `rsf`, `rsi`, `zedx`, and `zedxm` identify the camera models.
- `0400` identifies the acquisition distance in millimeters.
- `hd` and `sd` identify the recording resolution modes.
- `neural` and `neural_plus` identify depth-processing modes where applicable.
- `artificial` and `natural` identify the lighting condition.

This convention is used consistently for recording directories, archives, and associated log files.

## 3. Extracted Dataset Structure

After downloading and fully extracting the archives, each distance directory contains:

- 16 acquisition log files (`.txt`).
- 16 recording directories, one per camera configuration.

For example, part of the structure under `artificial/0400/` is:

```text
artificial/
└── 0400/
    ├── rsf_0400_hd_artificial.txt
    ├── rsf_0400_sd_artificial.txt
    ├── rsi_0400_hd_artificial.txt
    ├── ...
    ├── rsf_0400_hd_artificial/
    │   ├── metadata.yaml
    │   └── rsf_0400_hd_artificial_0.mcap
    ├── rsf_0400_sd_artificial/
    │   ├── metadata.yaml
    │   └── rsf_0400_sd_artificial_0.mcap
    └── ...
```

### 3.1 Acquisition Logs

Each distance directory contains 16 `.txt` files, corresponding to the camera configurations used during acquisition.

Examples:

```text
rsf_0400_hd_artificial.txt
rsi_0400_sd_artificial.txt
zedx_0400_hd_neural_artificial.txt
zedxm_0400_sd_neural_plus_artificial.txt
```

Depending on the acquisition pipeline, these files contain acquisition metadata, calibration output, runtime information, or capture notes.

After extraction, the log files are located directly within their corresponding distance directory.

**The logs do not replace the recorded sensor data.** The analyses reported in the paper were performed using the ROS 2 bag recordings.

### 3.2 ROS 2 Bag Recordings

Each recording is stored in a separate directory containing ROS 2 bag metadata and the corresponding MCAP recording.

Example:

```text
rsf_0400_hd_artificial/
├── metadata.yaml
└── rsf_0400_hd_artificial_0.mcap
```

The `metadata.yaml` file describes the ROS 2 bag, while the `.mcap` file contains the recorded data.

This is the extracted dataset layout intended for subsequent processing and analysis.

## 4. Dataset Distribution Format

To reduce download size, the dataset is distributed through IIT Dataverse as compressed archives.

### 4.1 Acquisition Log Archives

The 16 log files associated with an environment-distance combination are grouped into a single `.tar.xz` archive.

The naming convention is:

```text
logs_<distance>_<environment>.tar.xz
```

For example:

```text
logs_0400_artificial.tar.xz
```

Each archive contains a directory holding the associated acquisition logs.

During restoration, the log files are extracted and placed directly within the corresponding distance directory.

### 4.2 Recording Archives

Each ROS 2 bag directory is distributed as a separate `.tar.xz` archive.

The archives must be extracted to restore the original recording directories, including their metadata and MCAP files.

This can be performed automatically using the dataset downloader described below.

## 5. Downloading the Dataset

The dataset is hosted on [IIT Dataverse](https://dataverse.iit.it/) and can be accessed using the provided downloader.

Please refer to the [Paper Reproduction README](paper_reproduction/README.md) for detailed instruction.

## 6. Known Dataset Limitation

One recording is known to be partially corrupted:

**ZED X HD Neural, natural illumination, 3000 mm.**

This recording cannot be used in its entirety. Only the recoverable portion should be considered in analyses involving this configuration.

The issue affects the recorded ROS 2 bag and should not be interpreted as a general failure of the other recordings.

Researchers reproducing the paper results should account for this limitation when comparing the number of valid frames or measurements across recordings.

## 7. Relationship to the Paper Results

The acquisition logs and ROS 2 bag recordings serve different purposes.

**Acquisition logs** document information produced during the data collection process. They may be useful for examining experimental conditions, calibration information, and acquisition behavior.

**ROS 2 bag recordings** contain the sensor data used in the numerical analyses reported in the paper.

Consequently, downloading only the log archives is not sufficient to independently reproduce the paper's depth measurements, statistical analysis, figures, or derived tables.

For reproducible analysis, use the ROS 2 bag recordings and the corresponding analysis code.

## 8. Citation and Reuse

When using this dataset in research, please cite the associated dataset and paper record:

[Camera Comparison Dataset — IIT Dataverse](https://doi.org/10.48557/LUONQB)

Consult the Dataverse record for the complete citation metadata, dataset version, licensing information, and conditions of reuse.