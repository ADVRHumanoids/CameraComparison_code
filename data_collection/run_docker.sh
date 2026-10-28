#!/usr/bin/env bash
set -e

############################
# CONFIG
############################
IMAGE_NAME="humble_new:latest"

############################
# X11 DISPLAY SETUP
############################
# Allow local docker containers to access X server
xhost +si:localuser:root > /dev/null

############################
# RUN CONTAINER
############################
docker run -it --rm \
  --runtime nvidia \
  --gpus all \
  --privileged \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  --network=host --ipc=host \
  -v /var/nvidia/nvcam/settings/:/var/nvidia/nvcam/settings/ \
  -v /tmp/argus_socket:/tmp/argus_socket \
  -v /etc/systemd/system/zed_x_daemon.service:/etc/systemd/system/zed_x_daemon.service \
  "${IMAGE_NAME}"
