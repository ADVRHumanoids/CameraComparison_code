"""
  Copyright 2025 Lovato Alessio
 
  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at
 
        http://www.apache.org/licenses/LICENSE-2.0
 
  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  @author Lovato Alessio
  @brief Launch file to launch rosbag service server

"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    # Declare launch arguments
    output_dir_arg = DeclareLaunchArgument(
        "output_dir",
        default_value="./rosbags",
        description="Directory where the rosbag will be saved"
    )
    
    topics_arg = DeclareLaunchArgument(
        "topics",
        default_value="['/rgb_image', '/depth_image', '/camera_info', '/tf', '/tf_static']",
        description="List of topics to record"
    )

    # Create server node
    server_node = Node(
        package="rosbag_service",
        executable="rosbag_service_server",
        name="rosbag_service_server",
        parameters=[{
            "output_dir": LaunchConfiguration("output_dir"),
            "topics": LaunchConfiguration("topics")
        }],
        output="screen"
    )

    return LaunchDescription([
        output_dir_arg,
        topics_arg,
        server_node
    ])
