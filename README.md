# CameraComparison_code

> **Paper**: _Depth Estimation Comparison Between Realsense D435i, D435f, Stereolabs ZED X and ZED X Mini_ (link will be added upon publication).

This repository contains the code and scripts used to compare depth sensing performance across multiple cameras (e.g., Intel RealSense and Stereolabs ZED) using a reproducible ROS 2 pipeline on **NVIDIA Jetson AGX Orin**.

The core of the project is a **ROS 2 Humble workspace** (the `src/` folder in this repo) plus a **Dockerfile** that builds a container environment intended to reproduce the software stack on Jetson devices running:

- **Linux for Tegra (L4T) 36.4** / JetPack **r36.4** (base image: `nvcr.io/nvidia/l4t-jetpack:r36.4.0`)

## Repository layout

At the top level:

- `Dockerfile` — container recipe used to build a Jetson-compatible environment with ROS 2 Humble, PCL, ZED SDK installer, and RealSense dependencies.
- `run_docker.sh` — convenience script to run the built image with NVIDIA runtime, host networking and X11 forwarding.
- `dataset_downloader.sh` — utility script to download the dataset from Dataverse given an API token, and optionally decompress archives.
- `src/` — **ROS 2 workspace source folder** (to be built with `colcon`).
  - `depth_estimation/` — main pipeline: mask generation + masked depth estimation + masked point cloud + plane detection.
  - `mask_interfaces/` — custom messages (`Mask.msg`, `Pixel.msg`) used to transmit masks.
  - `rosbag_service/` — service-based rosbag start/stop utilities used for automated acquisition.
  - `zed-ros2-wrapper-humble-v5.0.0/` — vendored ZED ROS 2 wrapper used to run ZED cameras.

## What’s in the ROS 2 workspace (`src/`)

The folder `src/` in this repository is **not** a generic “source folder”: it is the `src/` directory of a standard ROS 2 workspace.

Inside the Docker image, this repository’s `src/` is copied to:

- `/home/humble/humble_ws/src`

and must be built with `colcon` before running the launch files.

### Package overview

#### `depth_estimation`

ROS 2 package providing:

- `MaskPublisher` component: generates a pixel mask (ROI) from an RGB image.
- `DepthEstimation` component: consumes synchronized RGB + depth + camera info + mask (and optionally point cloud) to:
  - visualize the ROI,
  - compute depth statistics inside the ROI,
  - publish a masked `PointCloud2`,
  - detect a plane from masked points and publish the plane point cloud + TF.

Key launch files:

- `launch/camera.launch.py`: selects and launches a camera stack (RealSense or ZED wrapper depending on arguments).
- `launch/depth_estimation.launch.py`: runs the end-to-end pipeline.
- `launch/mask_publisher.launch.py`: runs the mask publisher (multiple mask types supported).

Automation:

- `scripts/camera_test_runner.sh` runs repeatable tests across distances, cameras and modes. **Note:** it modifies certain launch/config files in-place (see the package README for details).

More details: see `src/depth_estimation/README.md`.

#### `mask_interfaces`

Interface-only package containing message definitions:

- `mask_interfaces/msg/Pixel.msg`
- `mask_interfaces/msg/Mask.msg`

This message is used by `MaskPublisher` to publish the ROI pixels to `DepthEstimation`.

More details: see `src/mask_interfaces/README.md`.

#### `rosbag_service`

ROS 2 package providing services and small CLI clients to start/stop rosbag recordings programmatically. This is mainly used by the automated acquisition script.

More details: see `src/rosbag_service/README.md`.

#### `zed-ros2-wrapper-humble-v5.0.0`

Vendored Stereolabs ZED ROS 2 wrapper (Humble). It is included so the exact wrapper version used for the experiments is preserved.

## Reproducibility with Docker (Jetson AGX Orin)

This repository includes a `Dockerfile` designed for **Jetson AGX Orin** on **L4T 36.4**.

### Host prerequisites

1. **Jetson platform**: Jetson AGX Orin with JetPack / L4T 36.4.
2. **Docker + NVIDIA Container Runtime** installed and working on the Jetson.
3. **ZED SDK installed on the host**.

Why ZED SDK on the host?

- The container installs the ZED SDK *inside* the image as well, but in practice ZED cameras often require host-level components (drivers/udev rules) and access to device nodes. Installing the ZED SDK on the host helps ensure the camera is detected properly and simplifies permissions.

### Install ZED SDK
Run the following code. To exit EULA press `q`, accept it and follow the installation instruction provided byt the script. Be aware that models' download will take a long time.
```bash
wget https://stereolabs.sfo2.cdn.digitaloceanspaces.com/zedsdk/5.0/ZED_SDK_Tegra_L4T36.4_v5.0.6.zstd.run
sudo chmod +x ZED_SDK_Tegra_L4T36.4_v5.0.6.zstd.run
./ZED_SDK_Tegra_L4T36.4_v5.0.6.zstd.run
rm ZED_SDK_Tegra_L4T36.4_v5.0.6.zstd.run
```

### Build the Docker image

Build from the repository root (this matters because `COPY ./src ...` is relative to the build context):

```bash
cd /home/orin/CameraComparison_code
docker build -t humble_zed:latest -f Dockerfile .
```

### Run the container

A convenience script exists:

```bash
./run_docker.sh
```

What it does (high level):

- enables NVIDIA runtime,
- uses host networking (`--network host`) so ROS 2 discovery works easily,
- mounts X11 socket for GUI tools.

### Build the ROS 2 workspace inside the container

The Dockerfile copies the workspace sources but (by design) does **not** run `colcon build` during image build.

Inside the container shell:

```bash
source /opt/ros/humble/setup.bash
cd ~/humble_ws
colcon build --symlink-install
source install/setup.bash
```

Then you can launch nodes, for example:

```bash
ros2 launch depth_estimation depth_estimation.launch.py camera:=rsi ground_truth:=0.6
```

> `ground_truth` must be **> 0** for `DepthEstimation` (see `src/depth_estimation/README.md`).

## ⚠️ Important: ZED models + calibration setup inside the container

This Docker image uses a **non-root user** by default (see `ARG USERNAME=humble` in the `Dockerfile`).
Because of that, the first time you use ZED cameras inside the container you may **not** be able to automatically install:

- ZED **neural depth models**, and
- camera **calibration / configuration** files

These assets are typically installed by the ZED tools and require elevated privileges to write under `/usr/local/zed/`.

### One-time setup procedure (do this once per Jetson + camera family)

1. Connect the camera(s) **before powering on** the Jetson AGX Orin.
2. Start the container (e.g., `./run_docker.sh`).
3. Inside the container, become root:

```bash
sudo su
```

4. Launch the ZED utilities:
  - `ZED_Explorer` (for Calibration files)
  - `ZED_Depth_Viewer` (for Neural depth models)

  Use their GUI to **toggle/select each connected camera**. This triggers the download/installation of the required models and calibration files.

  Notes:
  - You don’t need to restart the applications for each camera: just switch the active camera in the GUI.
  - Repeat the toggle process for **each camera** you plan to use.

5. Exit the root shell and go back to the normal user:

```bash
exit
```

After the setup is completed, you can use the cameras normally as the non-root user.

### Persist the configuration (recommended)

If you don’t persist the container filesystem changes, you may have to repeat the installation procedure.
To save the installed models/calibration into a reusable image, **commit the container** after completing the root-setup step.

Example workflow:

1. Run the container **without** `--rm` (so it remains available to commit).
2. After installing the models/calibration, from the host run:

```bash
docker ps   # find the container id/name
docker commit <container_id_or_name> humble_zed_configured:latest
```

Then run `humble_zed_configured:latest` for subsequent experiments.

### Notes about RealSense installation

The Dockerfile attempts to add the RealSense APT repository and install `librealsense2-*`.

On some Jetson base images, the Ubuntu codename used for the repo line may be missing or non-standard, which can produce an error like:

- `Malformed entry ... librealsense.list (Component)`

If you hit this, the fix is to generate the codename from `/etc/os-release` (or hardcode the correct Ubuntu codename for your JetPack base). See the discussion in the repository issues / notes, or update the Dockerfile accordingly.

## Dataset download (`dataset_downloader.sh`)

`dataset_downloader.sh` downloads all files listed in a Dataverse metadata export.
More information are available in this [README](CameraComparisonDataset/README.md)

It requires an API token:

```bash
export API_TOKEN="<your_dataverse_token>"
./dataset_downloader.sh
```

Optional decompression:

```bash
./dataset_downloader.sh --decompress
```

The script supports preserving `directoryLabel` from Dataverse, skipping already-downloaded files if sizes match, optional archive cleanup, and collects logs from `logs_*.tar.xz` archives.

## Plotting and statistics (`plot_results.py`)

The file `plot_results.py` parses the experiment log files produced by the ROS 2 pipeline (and/or the provided dataset logs) and generates:

- comparison plots (saved under `plots/` when `--output-folder` is provided), and
- a LaTeX table summarizing outlier statistics (e.g., `outliers_table_filtered.tex`).

### Expected inputs

The script expects log files named like:

- `<camera>_<distance_mm>_<mode>.txt`

For example:

- `rsi_0600_hd_natural.txt`

It scans the dataset folders by default:

- `dataset/natural`
- `dataset/artificial`

and parses depth/RMSE lines from the logs (e.g., average depth, RMS, RMSE).

### Outputs

Depending on options, it produces:

- violin plots of average depth error vs distance,
- violin plots of RMSE vs distance,
- scatter plots (average error vs RMSE),
- `outliers_table_filtered.tex` (LaTeX longtable).

When `--output-folder plots` is used, plot images are saved under subfolders like `plots/depth/`, `plots/rmse/`, and `plots/scatter/`.

### Common usage

Create plots (and filter outliers with a threshold, in meters):

```bash
python3 plot_results.py --output-folder plots --outlier-threshold 0.3
```

Filter by camera and/or mode:

```bash
python3 plot_results.py --camera rsi rsf --mode hd sd --output-folder plots
python3 plot_results.py --camera zedx zedxm --mode all --output-folder plots
```

Restrict the plotted distance range:

```bash
python3 plot_results.py --min-dist 0.4 --max-dist 1.0 --output-folder plots
```

Plot all the available options:
```bash
python3 plot_results.py --help
```

### Python dependencies

The plotting script uses standard Python scientific libraries pinned in `requirements.txt`:

- `matplotlib`
- `numpy`
- `pandas`
- `seaborn`

Install them in a virtual environment (recommended):

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Mask vs valid-depth consistency (`get_depth_image_outlier.py`)

The script `get_depth_image_outlier.py` provides a quick sanity check on how well the depth stream “covers” the selected ROI mask.
It parses `.txt` log files and looks for lines like:

- `Number of pixels in the mask: <N> Valid depth points: <M>`

For each file, it computes the percentage difference between valid depth points and mask pixels:

$$
	ext{diff}(\%) = \frac{|M - N|}{N} \cdot 100
$$

and reports (per test and distance) the **mean / min / max** of that value across all occurrences in the log.

### Inputs

- One or more root folders passed via `--root-dir`.
- The script recursively scans for `*.txt` files.
- It assumes filenames contain the distance as the second underscore-separated token, e.g. `rsi_0600_hd_natural.txt` (distance = `0600`).

### Outputs

- A matrix printed to stdout where rows are tests (filename without the distance token) and columns are distances.
- Optional LaTeX export (`--tex out.tex`) to include the matrix in the paper.

### Usage

Run on both dataset folders and print the matrix:

```bash
python3 get_depth_image_outlier.py --root-dir dataset/natural dataset/artificial
```

Filter out rows where all mean values are 0:

```bash
python3 get_depth_image_outlier.py --root-dir dataset/natural dataset/artificial --filter
```

Export the table to LaTeX:

```bash
python3 get_depth_image_outlier.py --root-dir dataset/natural dataset/artificial --filter --tex depth_mask_outliers.tex
```

## Citing / attribution

If you use this repository, please cite the paper once available. A BibTeX entry and DOI will be added here.

## License

See the `LICENSE` files in each package/folder.
