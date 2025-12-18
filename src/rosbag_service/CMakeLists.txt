cmake_minimum_required(VERSION 3.8)
project(rosbag_service)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rosidl_default_generators REQUIRED)

# Generate interfaces
rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/StartRosbag.srv"
  "srv/StopRosbag.srv"
)

# This is crucial - it ensures the interfaces are available to the same package
rosidl_get_typesupport_target(cpp_typesupport_target
  ${PROJECT_NAME} rosidl_typesupport_cpp)

# Add executables
add_executable(rosbag_service_server src/rosbag_service_server.cpp)
ament_target_dependencies(rosbag_service_server rclcpp)
target_link_libraries(rosbag_service_server "${cpp_typesupport_target}")

add_executable(rosbag_service_client src/rosbag_service_client.cpp)
ament_target_dependencies(rosbag_service_client rclcpp)
target_link_libraries(rosbag_service_client "${cpp_typesupport_target}")

add_executable(rosbag_stop_client src/rosbag_stop_client.cpp)
ament_target_dependencies(rosbag_stop_client rclcpp)
target_link_libraries(rosbag_stop_client "${cpp_typesupport_target}")

# Install executables
install(TARGETS
  rosbag_service_server
  rosbag_service_client
  rosbag_stop_client
  DESTINATION lib/${PROJECT_NAME})

# Install directories
install(DIRECTORY
  launch
  srv
  DESTINATION share/${PROJECT_NAME}/
)

# Export dependencies
ament_export_dependencies(rosidl_default_runtime)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()