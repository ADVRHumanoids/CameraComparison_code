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
  @brief Launch file to start camera nodes

  @Note This file is similar to the original camera.launch.py but configured for realsense sd

"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction

from launch.conditions import LaunchConfigurationEquals
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution

from launch_ros.substitutions import FindPackageShare


"""
@brief Function to append nodes to launch description
"""
def launch_description(context, *args, **kwargs):

    # Launch zed camera wrapper
    zed_launch_file = PathJoinSubstitution(
        [FindPackageShare('zed_wrapper'), 'launch', 'zed_camera.launch.py']
    )
    
    zedxm = IncludeLaunchDescription(
        PythonLaunchDescriptionSource((zed_launch_file)),
        launch_arguments={
            'camera_model':LaunchConfiguration('camera'),
            'serial_number': '52061328'
        }.items(),
        condition=LaunchConfigurationEquals('camera', 'zedxm')
    )

    zedx = IncludeLaunchDescription(
        PythonLaunchDescriptionSource((zed_launch_file)),
        launch_arguments={
            'camera_model':LaunchConfiguration('camera'),
            'serial_number': '42330596'
        }.items(),
        condition=LaunchConfigurationEquals('camera', 'zedx')
    )

    # Launch the realsense camera

    rs_launch_file = PathJoinSubstitution(
        [FindPackageShare('realsense2_camera'), 'launch', 'rs_launch.py']
    )


    realsense_i = IncludeLaunchDescription(
        PythonLaunchDescriptionSource((rs_launch_file)),
        launch_arguments={
            'enable_color': 'true',
                'enable_depth': 'true',
                'enable_infra': 'false',
                'enable_infra1': 'false',
                'enable_infra2': 'false',
                'enable_sync': 'false',
                'enable_gyro': 'false',
                'enable_accel': 'false',
                'rgb_camera.color_format' : 'BGR8',
                'rgb_camera.color_profile': '848,480,30',
                'depth_module.depth_profile': '848,480,30',
                'rgb_camera.enable_auto_exposure': 'false',
                'align_depth.enable': 'true',
                'pointcloud.enable': 'true',
                'pointcloud.ordered_pc': 'true'
        }.items(),
        condition=(LaunchConfigurationEquals('camera', 'rsi'))
    )

    realsense_f = IncludeLaunchDescription(
        PythonLaunchDescriptionSource((rs_launch_file)),
        launch_arguments={
            'enable_color': 'true',
                'enable_depth': 'true',
                'enable_infra': 'false',
                'enable_infra1': 'false',
                'enable_infra2': 'false',
                'enable_sync': 'false',
                'enable_gyro': 'false',
                'enable_accel': 'false',
                'rgb_camera.color_format' : 'BGR8',
                'rgb_camera.color_profile': '848,480,30',
                'depth_module.depth_profile': '848,480,30',
                'rgb_camera.enable_auto_exposure': 'false',
                'align_depth.enable': 'true',
                'pointcloud.enable': 'true',
                'pointcloud.ordered_pc': 'true'
        }.items(),
        condition=(LaunchConfigurationEquals('camera', 'rsf'))
    )
    

    # add all actions
    return [
        zedx,
        zedxm,
        realsense_i,
        realsense_f
    ]


"""
@brief Main function
"""
def generate_launch_description():
    # Declare arguments
    camera_arg = DeclareLaunchArgument(
        name='camera',
        default_value='rsi',
        choices=['rsi', 'rsf', 'zedm', 'zedx', 'zedxm'],
        description='The camera model to be used'
    )

    return LaunchDescription([
        camera_arg,
        OpaqueFunction(function=launch_description)
    ])
