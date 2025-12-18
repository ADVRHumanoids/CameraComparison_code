# depth_estimation

ROS 2 package to:

* generate simple or feature-based masks (`MaskPublisher`), and
* estimate depth / build a masked point cloud / detect a plane from a masked ROI (`DepthEstimation`).

This repository also vendors (and lightly customizes) a subset of `depth_image_proc` used to convert depth+RGB into an XYZRGB point cloud.

## Nodes

### `DepthEstimation` (component)

* **C++ class:** `DepthEstimation` (see `include/depth_estimation.hpp`)
* **Component name / node name:** `depth_estimation`
* **What it does**
   * Receives synchronized **depth image**, **RGB image**, **RGB camera info**, and **mask**.
   * Optionally also synchronizes an **ordered point cloud** when `use_pointcloud=true`.
   * Uses the incoming mask pixels as ROI to:
      * publish ROI feedback images (RGB + depth),
      * compute average depth in the ROI (from depth image and/or point cloud),
      * build and publish a masked XYZRGB point cloud,
      * detect planes and publish the detected plane point cloud and a TF for the plane.

#### Subscriptions (configurable via parameters)

* `image_topic` (RGB image)
* `depth_map_topic` (aligned depth image)
* `rgb_camera_info_topic` (camera info)
* `mask_topic` (mask pixel list)
* `pointcloud_topic` (only if `use_pointcloud=true`)

#### Published topics

* `/target_image` (`sensor_msgs/msg/Image`): RGB image with target/ROI annotation
* `/masked_RGB` (`sensor_msgs/msg/Image`): RGB ROI
* `/masked_depth` (`sensor_msgs/msg/Image`): Depth ROI
* `/masked_pcl` (`sensor_msgs/msg/PointCloud2`): XYZRGB point cloud built from depth+RGB over the mask
* `/detected_plane` (`sensor_msgs/msg/PointCloud2`): extracted plane point cloud (from `/masked_pcl`)
* `/frame_counter` (`std_msgs/msg/String`): processed frame counter
* `/camera_info` (`sensor_msgs/msg/CameraInfo`): republished camera info
* `/rgb_image` (`sensor_msgs/msg/Image`): republished RGB
* `/depth_image` (`sensor_msgs/msg/Image`): republished depth

#### Parameters

Defaults shown are from `src/depth_estimation.cpp`.

* `image_topic` (string, default: `/camera/camera/color/image_raw`)
* `rgb_camera_info_topic` (string, default: `/camera/camera/color/camera_info`)
* `pointcloud_topic` (string, default: `/camera/camera/depth/color/points`)
* `depth_map_topic` (string, default: `/camera/camera/aligned_depth_to_color/image_raw`)
* `mask_topic` (string, default: `/mask`)
* `use_pointcloud` (bool, default: `true`)
* `min_percentage` (double, default: `0.3`): stop plane extraction when remaining points fall below this fraction
* `raw_tf` (bool, default: `false`): publish plane TF directly from plane coefficients
* `z_up` (bool, default: `false`): orient plane TF normal consistently (see code)
* `reference_frame` (string, default: `table_frame`)
* `ground_truth` (double, default: `0.0`) **must be > 0** (node errors out otherwise)
* `counter_max` (int, default: `300`) **must be > 0**

### `MaskPublisher` (component)

* **C++ class:** `MaskPublisher` (see `include/mask_publisher.hpp`)
* **Component name / node name:** `mask_publisher`
* **What it does**
   * Subscribes to an image and produces a `mask_interfaces/msg/Mask` containing the ROI pixels.
   * Can generate geometric masks or detect features.
   * Publishes a debug mono mask image.

#### Published topics

* `/mask` (`mask_interfaces/msg/Mask`): list of pixels in the mask
* `/mask_image_test` (`sensor_msgs/msg/Image`): debug mask image (`mono8`)

#### Parameters

Defaults shown are from `src/mask_publisher.cpp`.

* `mask_type` (int, default: `1`)
   * `0`: NONE (full image)
   * `1`: RECTANGLE
   * `2`: CIRCLE
   * `3`: STAR
   * `4`: COLOR (HSV threshold; ranges are currently hard-coded in source)
   * `5`: ARUCO
   * `6`: CHESSBOARD
* `image_topic` (string, default: `/camera/color/image_raw`)
* `mask_size` (int, default: `100`)
* `x` (int, default: `0`): x offset in pixels
* `y` (int, default: `0`): y offset in pixels (note: y-axis is inverted in code)

### `depth_image_proc::PointCloudXyzrgbNode` (component, vendored)

* **C++ class:** `depth_image_proc::PointCloudXyzrgbNode` (see `include/depth_image_proc/point_cloud_xyzrgb.hpp`)
* **What it does:** synchronizes depth + RGB + camera info + mask and publishes an XYZRGB point cloud.
* This is included mainly as a dependency/utility; `DepthEstimation` also generates a masked point cloud internally.

## Launch files

Launch files present in this package:

* `launch/camera.launch.py`
   * Argument: `camera` (default: `rsi`, choices: `rsi`, `rsf`, `zedm`, `zedx`, `zedxm`)
   * Launches either ZED wrapper nodes (for `zedx` / `zedxm`) or RealSense (for `rsi` / `rsf`).

* `launch/depth_estimation.launch.py`
   * Arguments:
      * `camera` (default: `rsi`, choices: `rsi`, `rsf`, `zedm`, `zedx`, `zedxm`)
      * `ground_truth` (default: `0.0`) — **must be set to > 0** for `DepthEstimation`
   * Starts the selected camera (via `camera.launch.py`), publishes some static transforms, then runs `depth_estimation_node` with camera-specific remaps/params.

* `launch/mask_publisher.launch.py`
   * Arguments:
      * `mask` (default: `aruco`, choices: `rect`, `circle`, `star`, `color`, `aruco`, `chessboard`, `none`)
      * `size` (default: `200`)
      * `x` (default: `0`)
      * `y` (default: `0`)
      * `camera` (default: `rsi`, choices: `rsi`, `rsf`, `zedm`, `zedx`, `zedxm`)
      * `marker_id` (default: `0`)
   * Launches `mask_publisher_node` and selects input image topic based on `camera`.
   * Note: `camera.launch.py` inclusion is currently commented out in this launch file.

* `launch/rs_sd.launch.py` / `launch/rs_hd.launch.py`
   * RealSense presets (848x480 vs 1280x720) used as standalone camera launchers.

## Test automation script

The script `scripts/camera_test_runner.sh` runs repeatable acquisition/test cycles across multiple cameras, modes, and ground-truth distances.

### What it does

For each distance and for each camera+mode combination, it:

1. **Reconfigures the camera launch** used by `depth_estimation.launch.py`:
    * For RealSense (`rsi`, `rsf`): it copies `launch/rs_<mode>.launch.py` over `launch/camera.launch.py`.
    * For ZED (`zedx`, `zedxm`): it overwrites YAML files in the external `zed_wrapper` config folder.
2. Starts the main pipeline launch (in the script this is `ros2 launch depth_estimation complete_test.launch.py ...`).
3. Starts the mask publisher (`ros2 launch depth_estimation mask_publisher.launch.py camera:=... mask:=aruco`).
4. Monitors `/frame_counter` until a threshold (default 300 frames) or a timeout, then stops recording and kills launched processes.
5. Saves logs under a results folder (default `natural/<distance_mm>/...`).
6. Optionally copies logs (and potentially bags) to a remote host via `ssh/scp`.

### Important notes / assumptions

* The script **modifies files in-place** (it overwrites `launch/camera.launch.py` for RealSense runs).
* It assumes a **workspace layout** where `depth_estimation` lives under `./src` (see `WS_BASE=./src`).
* It assumes external tooling/packages exist:
   * `rosbag_service_pkg` (`rosbag_service_client` and `rosbag_stop_client`),
   * a ZED wrapper checkout at `./src/zed-ros2-wrapper-humble-v5.0.0/zed_wrapper/` (for ZED runs),
   * valid SSH configuration for the `username@hostname` copy step.

### Usage

Run it from the package directory (or adjust `WS_BASE` inside the script):

```bash
./scripts/camera_test_runner.sh
```

The script is interactive: it waits for ENTER before each distance iteration and before each camera.

## Required packages / dependencies

This package depends on standard ROS 2 Humble (or later) libraries plus image/pointcloud processing libraries.

### Build dependencies (from `package.xml` / `CMakeLists.txt`)

* ROS 2 / build:
   * `rclcpp`, `rclcpp_components`, `ament_cmake`
* Messages / TF:
   * `sensor_msgs`, `geometry_msgs`, `tf2`, `tf2_ros`, `tf2_geometry_msgs`, `tf2_eigen`
* Image pipeline:
   * `image_transport`, `image_geometry`, `message_filters`, `cv_bridge`, `OpenCV`
* Point cloud pipeline:
   * `PCL` (>= 1.12), `pcl_conversions`, `Eigen3`
* Custom messages:
   * `mask_interfaces`

### Runtime dependencies (depending on your setup)

* One of the supported camera stacks:
   * RealSense: `realsense2_camera`
   * ZED: `zed_wrapper`
* If you use the automated acquisition script:
   * `rosbag_service_pkg`
   * `bc` (used for simple arithmetic in bash)

## License

* The **`depth_estimation` package** (everything outside the `include/depth_image_proc/` + `src/depth_image_proc/` trees) is licensed under the **Apache License 2.0** (see per-file headers and `LICENSE`).
* The vendored **`depth_image_proc`** code under `include/depth_image_proc/` and `src/depth_image_proc/` is a **fork/derivative** of the upstream ROS package:
   * Upstream: https://index.ros.org/p/depth_image_proc/
   * License: **BSD 2-Clause** (see the headers in those files).
