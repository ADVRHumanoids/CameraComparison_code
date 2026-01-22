# Dataset Overview

This dataset is part of an ongoing research project focused on camera performance comparison and depth estimation.
It contains recordings and logs collected across multiple environments, distances, and camera configurations.

This README provides a high-level description of the dataset structure and instructions for downloading and restoring the data from Dataverse.  
Scientific details, benchmarks, and experimental context will be added later.

---

## Dataset Size Warning ⚠️

Before downloading or extracting the dataset, please ensure you have sufficient disk space.

- **Compressed size**: approximately **140 GB**
- **Uncompressed size**: approximately **380 GB**

Extraction will temporarily require additional space.  
Running out of disk space during decompression may result in corrupted or incomplete data.

---

## 1. Top-Level Directory Structure

The root of the dataset contains two main folders:

```
root/
├── README.md
├── artificial/
└── natural/
```

These represent two types of environments:

- **artificial**: controlled lighting conditions
- **natural**: real-world lighting conditions

Both folders follow **exactly the same internal structure**.

---

## 2. Distance-Based Subdirectories

Inside each environment folder, data is organized by distance.
Folder names correspond to distances in millimeters (e.g. `0400` = 400 mm):

```
artificial/
├── 0400
├── 0600
├── 0800
├── 1000
├── 1400
├── 1800
├── 2200
├── 2600
└── 3000
```

The `natural/` directory contains the same set of distance folders.

Each distance directory represents a complete capture set for that environment-distance combination.

---

## 3. Dataset Structure (Uncompressed Form)

After full restoration, each distance folder (e.g. `artificial/0400/`) contains:

### A. Log Files

Exactly **16 `.txt` files**, one per camera or configuration.

Examples:
```
rsf_0400_hd_artificial.txt
rsi_0400_sd_artificial.txt
zedx_0400_hd_neural_artificial.txt
...
zedxm_0400_sd_neural_plus_artificial.txt
```

These files contain metadata, calibration outputs, runtime logs, or capture notes depending on the pipeline.

When fully restored, all log files are located **directly inside the distance folder**.

---

### B. Data Folders

Exactly **16 data folders**, one per camera configuration.

Example:

```
rsf_0400_hd_artificial/
├── metadata.yaml
└── rsf_0400_hd_artificial_0.mcap
```


Each data folder contains:

- ROS 2 bag metadata
- MCAP recordings

This represents the fully expanded, analysis-ready form of the dataset.

---

## 4. Compressed Dataset Layout (Dataverse)

To reduce storage requirements, the dataset is distributed in compressed form.

Inside each distance directory, you will find:

### A. Logs Archive

All `.txt` files are bundled into a single archive _logs_<distance>_<environment>.tar.xz_.
Example: ```logs_0400_artificial.tar.xz```


This archive contains a single folder with all log files.

---

### B. ROS 2 Bag Archives

Each recorded bag is compressed and distributed as an archive `.tar.xz`.

These archives must be decompressed to restore the original folder structure. This can be automatically done using the downloading script at [https://github.com/ADVRHumanoids/CameraComparison_code/dataset_downloader.sh](https://github.com/ADVRHumanoids/CameraComparison_code/dataset_downloader.sh).

---

## 5. Downloading the Dataset

The dataset is hosted on **IIT Dataverse** and must be downloaded via its API.

### Prerequisites

- Bash shell
- `curl`
- `jq`
- `tar`
- `unzip`

### Environment Variables

Before running the downloader, set the following variables:

```bash
export API_TOKEN=your_api_token_here
export SERVER_URL=https://dataverse.iit.it/
export PERSISTENT_ID=doi:10.48557/LUONQB
```

### Download the Downloader Script
1. Download the dataset downloader
```bash
git clone https://https://github.com/ADVRHumanoids/CameraComparison_code.git
cd CameraComparison_code
chmod +x dataverse_downloader.sh
./dataverse_downloader.sh
```

## 6. Using the downloader
There are several option to use  the downloader:

1. Full Dataset Download
```bash
./dataverse_downloader.sh
```

2. Log File download
```bash
./dataverse_downloader.sh --log-only
```
This will:
 - Download only the archives containing the log files used by the [plot result script](../plot_results.py).

2. Download and Decompress all archives
```bash
./dataverse_downloader.sh --decompress
```
This will:
 - Extract all data archives in place
 - Extract log archives
 - Move all .txt log files into their parent distance folder

3. Download, Decompress, and Remove Archives
```bash
./dataverse_downloader.sh --decompress --clean-archives
```
This will:
 - Fully restore the dataset structure
 - Remove all .zip and .tar.xz files after successful extraction

> ⚠️ Use this option only if you are sure you no longer need the compressed files.

## 7. Requirements
- Bash terminal (linux)
- curl
- jq
- tar
- unzip
- Sufficient disk space (see size warning above)