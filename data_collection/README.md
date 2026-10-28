# Data collection

This folder contains the ROS 2 workspace and Jetson/Docker setup used to collect
RGB/depth camera recordings for the study.

## Contents

- `src/`: ROS 2 Humble workspace packages for depth estimation, mask messages,
  rosbag recording services, and the vendored ZED ROS 2 wrapper.
- `Dockerfile`: Jetson AGX Orin / L4T 36.4 development image.
- `run_docker.sh`: starts the built image with camera and display access.

## Build and run

Build from this folder so Docker's `COPY ./src` uses the correct context:

```bash
cd data_collection
docker build -t humble_zed:latest -f Dockerfile .
./run_docker.sh
```

Inside the container:

```bash
source /opt/ros/humble/setup.bash
cd ~/humble_ws
colcon build --symlink-install
source install/setup.bash
```

See `src/depth_estimation/README.md` and `src/rosbag_service/README.md` for
package parameters, launches, and acquisition details. The camera test runner
is at `src/depth_estimation/scripts/camera_test_runner.sh`; run it with this
folder as the working directory. It changes camera configuration files in place
and uses SSH/SCP settings described in its package README.

Host prerequisites, ZED model setup, and SDK notes are specific to Jetson AGX
Orin with JetPack/L4T 36.4. See the package guides before collection.
