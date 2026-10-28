cmake_minimum_required(VERSION 3.16)
project(depth_estimation)

# C++ standard
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find package only if CUDA is installed
if (EXISTS "/usr/local/cuda-12.6")
  # Append CUDA stubs to the library path
  set(CUDA_TOOLKIT_INCLUDE "/usr/local/cuda-12.6")
  find_package(zed_ros2)
else()
  message(WARNING "CUDA not found, skipping CUDA and ZED related configurations.")
endif()

# Set compiler flags
if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_components REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(tf2_eigen REQUIRED)
find_package(image_geometry REQUIRED)
find_package(image_transport REQUIRED)
find_package(message_filters REQUIRED)
find_package(cv_bridge REQUIRED)
find_package(OpenCV REQUIRED)
find_package(pcl_conversions REQUIRED)
find_package(PCL 1.12 REQUIRED)
find_package(Eigen3 REQUIRED)
find_package(mask_interfaces REQUIRED)

include_directories(${PCL_INCLUDE_DIRS})
link_directories(${PCL_LIBRARY_DIRS})
add_definitions(${PCL_DEFINITIONS})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # The following line skips copyright checks
  set(ament_cmake_copyright_FOUND TRUE)
  # Skip cpplint checks (only works in a git repo)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()


##################################################
# MaskPublisher as a component
##################################################
add_library(mask_publisher_component SHARED
  src/mask_publisher.cpp
)

target_include_directories(mask_publisher_component PUBLIC include)

ament_target_dependencies(mask_publisher_component
  rclcpp
  rclcpp_components
  sensor_msgs
  mask_interfaces
  OpenCV
  cv_bridge
)

rclcpp_components_register_node(
  mask_publisher_component
  PLUGIN "MaskPublisher"
  EXECUTABLE "mask_publisher_node"
)

install(
  TARGETS mask_publisher_component
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

##################################################
# DepthEstimation as a component
##################################################
add_library(depth_estimation_component SHARED
  src/depth_estimation.cpp
  src/depth_estimation_utils.cpp
  src/depth_image_proc/conversions.cpp
)

target_include_directories(depth_estimation_component PUBLIC include)

ament_target_dependencies(depth_estimation_component
  rclcpp
  rclcpp_components
  sensor_msgs
  geometry_msgs
  cv_bridge
  OpenCV
  pcl_conversions
  Eigen3
  tf2
  tf2_geometry_msgs
  tf2_eigen
  tf2_ros
  image_geometry
  image_transport
  message_filters
  mask_interfaces
)

rclcpp_components_register_node(
  depth_estimation_component
  PLUGIN "DepthEstimation"
  EXECUTABLE "depth_estimation_node"
)

install(
  TARGETS depth_estimation_component
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

##################################################
# Directory installation
##################################################

install(DIRECTORY
  launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
