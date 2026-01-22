# Use stereolab imaga with ZED SDK and NVIDIA JetPack installed
FROM nvcr.io/nvidia/l4t-jetpack:r36.4.0
##########################################################################################
#######################  USERS SETUP  ####################################################
##########################################################################################

ARG USERNAME=humble
ARG USER_UID=1001
ARG USER_GID=$USER_UID

# Delete user if it exists in container (e.g Ubuntu Noble: ubuntu)
RUN if id -u $USER_UID ; then userdel `id -un $USER_UID` ; fi

# Create the user
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && usermod -aG sudo,video,i2c "$USERNAME" \ 
    # Solves the problem of video buffer: https://forums.developer.nvidia.com/t/nvrmmeminitnvmap-failed-with-permission-denied/270716/3
    #
    # [Optional] Add sudo support. Omit if you don't need to install software after connecting.
    && apt-get update \
    && apt-get install -y sudo \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Set the default user
USER $USERNAME

##########################################################################################
#######################  PACKAGES INSTALLATION ###########################################
##########################################################################################

# Install dependencies
RUN sudo apt update &&  sudo apt-get install -y -f zstd \
apt-utils \
python3-pip \
nano \
wget \
build-essential \
cmake \
git \
libeigen3-dev \
libgeographic-dev \
libflann-dev \
clang \
libboost-filesystem-dev \
libboost-date-time-dev \
libboost-iostreams-dev \
libboost-python-dev \
libbenchmark-dev \
libbullet-dev \
cppcheck \
python3.8-dev

RUN sudo apt remove -y python2.7
RUN sudo pip3 install pybind11 protobuf

WORKDIR /home/$USERNAME

# PCL library version 12.1
RUN wget https://github.com/PointCloudLibrary/pcl/archive/refs/tags/pcl-1.12.1.tar.gz && \
    tar xvf pcl-1.12.1.tar.gz && mkdir -p pcl-pcl-1.12.1/build

WORKDIR /home/$USERNAME/pcl-pcl-1.12.1/build
RUN cmake -DCMAKE_BUILD_TYPE=Release -DWITH_VTK=OFF ..
RUN sudo make -j12 install

WORKDIR /home/$USERNAME
RUN sudo rm -rf /home/$USERNAME/pcl-pcl-1.12.1/
RUN sudo rm pcl-1.12.1.tar.gz


##########################################################################################
##############################  ZED SDK AND REALSENSE INSTALLATION #######################
##########################################################################################

WORKDIR /home/$USERNAME
# Copy ZED SKD to user home, make it executable and run it
RUN sudo chmod -R a+rx /usr/local/lib/python3.10/
RUN wget https://stereolabs.sfo2.cdn.digitaloceanspaces.com/zedsdk/5.0/ZED_SDK_Tegra_L4T36.4_v5.0.6.zstd.run
RUN sudo chmod +x ZED_SDK_Tegra_L4T36.4_v5.0.6.zstd.run
RUN sudo ./ZED_SDK_Tegra_L4T36.4_v5.0.6.zstd.run -- silent
USER $USERNAME

# # Copy camera calibration files
# # COPY /tmp/settings /usr/local/zed/settings
RUN sudo chmod -R a+rx /usr/local/zed/

# Realsense sdk
RUN sudo apt-get install -y apt-transport-https curl lsb-release
RUN sudo mkdir -p /etc/apt/keyrings
RUN curl -sSf https://librealsense.realsenseai.com/Debian/librealsense.pgp | sudo tee /etc/apt/keyrings/librealsense.pgp > /dev/null
RUN echo "deb [signed-by=/etc/apt/keyrings/librealsense.pgp] https://librealsense.realsenseai.com/Debian/apt-repo `lsb_release -cs` main" | \
    sudo tee /etc/apt/sources.list.d/librealsense.list
RUN sudo apt-get update && sudo apt install -y librealsense2-*

##########################################################################################
#######################  ROS 2 HUMBLE INSTALLATION AND SETUP #############################
##########################################################################################

RUN sudo sh -c '\
  DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt-get update && \
  DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt-get install -y --no-install-recommends locales software-properties-common curl tzdata && \
  ln -fs /usr/share/zoneinfo/Etc/UTC /etc/localtime && echo "Etc/UTC" > /etc/timezone && dpkg-reconfigure -f noninteractive tzdata && \
  locale-gen en_US.UTF-8 && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 && \
  add-apt-repository -y universe || true && apt-get update && \
  curl -L -o /tmp/ros2-apt-source.deb "https://github.com/ros-infrastructure/ros-apt-source/releases/download/1.1.0/ros2-apt-source_1.1.0.$(. /etc/os-release && echo ${UBUNTU_CODENAME:-${VERSION_CODENAME}})_all.deb" && \
  dpkg -i /tmp/ros2-apt-source.deb && apt-get update && \
  apt-get install -y --no-install-recommends ros-humble-desktop && \
  rm -f /tmp/ros2-apt-source.deb && apt-get clean && rm -rf /var/lib/apt/lists/* \
'

# Build ROS WS
COPY ./src /home/$USERNAME/humble_ws/src
WORKDIR /home/$USERNAME/humble_ws
RUN sudo chown -R $USERNAME /home/$USERNAME/humble_ws

# Run rosdep and install dependencies
RUN /bin/bash -lc "source /opt/ros/humble/setup.bash \
    && sudo apt update && sudo apt-get install -y \
    python3-rosdep \
    python3-colcon-common-extensions \
    python3-colcon-core \
    ros-humble-zed-msgs \
    ros-humble-rosbag2-storage-mcap \
    && sudo rosdep init \
    && sudo chmod -R a+rx /usr/local/lib/python3.10/ \
    && rosdep update \
    && rosdep install --from-paths src --ignore-src -r -y"

# ##########################################################################################
# #######################  ENTRYPOINT AND SHELL ############################################
# ##########################################################################################

# Set the default shell to bash
ENV SHELL=/bin/bash

# Set up entrypoint and default command
#ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
CMD ["/bin/bash"]
