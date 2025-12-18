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
  @brief Launch file to start mask publisher node

"""

from launch import LaunchDescription
from launch_ros.actions import Node

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution

from launch_ros.substitutions import FindPackageShare

def publisher_setup(context, *args, **kwargs):
    # Get the mask enum
    mask = LaunchConfiguration('mask').perform(context)
    mask_type = 0
    if mask == 'rect':
        mask_type = 1
    elif mask == 'circle':
        mask_type = 2
    elif mask == 'star':
        mask_type = 3
    elif mask == 'color':
        mask_type = 4
    elif mask == 'aruco':
        mask_type = 5
    elif mask == 'chessboard':
        mask_type = 6
    elif mask == 'none':
        mask_type = 0
        
    # Default camera topic for the rs camera
    image_topic = '/camera/camera/color/image_raw'
    
    camera = LaunchConfiguration('camera').perform(context)

    if camera == 'rsi' or camera == 'rsf':
        camera = 'rs'

    if camera != 'rs':
        image_topic = '/zed/zed_node/rgb/image_rect_color'
        
    #component
    mask_component = Node(
                package='depth_estimation',
                executable='mask_publisher_node',
                name='mask_publisher',
                parameters=[{'image_topic': image_topic,
                             'mask_type' : mask_type,
                             'mask_size' : LaunchConfiguration('size'),
                             'x': LaunchConfiguration('x'),
                             'y': LaunchConfiguration('y'),
                             'camera': camera,
                             'marker_id': LaunchConfiguration('marker_id')
                             }],
    )

    return [
        mask_component,
    ]

def generate_launch_description():

    mask_arg = DeclareLaunchArgument(
        'mask',
        default_value='aruco',
        description='Mask type to be used: rect, circle, star, color, aruco, chessboard or none',
        choices=['rect', 'circle', 'star', 'color', 'aruco', 'chessboard', 'none'],
    )

    size_arg = DeclareLaunchArgument(
        'size',
        default_value='200',
        description='Size of the mask in pixels',
    )

    x_arg = DeclareLaunchArgument(
        name='x',
        default_value='0'
    )

    y_arg = DeclareLaunchArgument(
        name='y',
        default_value='0'
    )
    
    camera_arg = DeclareLaunchArgument(
        name='camera',
        default_value='rsi',
        choices=['rsi', 'rsf', 'zedm', 'zedx', 'zedxm'],
        description='The camera model to be used'
    )

    marker_id_arg = DeclareLaunchArgument(
        name='marker_id',
        default_value='0',
        description='ID of the ArUco marker to be detected'
    )
    
    camera_launch_file = PathJoinSubstitution(
        [FindPackageShare('depth_estimation'), 'launch', 'camera.launch.py']
    )

    camera_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource((camera_launch_file)),
        launch_arguments={
            'camera': 'rs',
        }.items(),
    )

    return LaunchDescription([
        mask_arg,
        size_arg,
        x_arg,
        y_arg,
        camera_arg,
        marker_id_arg,
        #camera_launch,
        OpaqueFunction(function=publisher_setup),
    ])
