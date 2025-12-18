from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, TimerAction

from launch.conditions import LaunchConfigurationEquals
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution

from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


"""
@brief Function to append nodes to launch description
"""
def launch_description(context, *args, **kwargs):

    # Launch camera node
    camera_launch_file = PathJoinSubstitution(
        [FindPackageShare('depth_estimation'), 'launch', 'camera.launch.py']
    )

    camera_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource((camera_launch_file)),
        launch_arguments={
            'camera': LaunchConfiguration('camera'),
        }.items(),
    )

    # Launch the mask nodes
    zed_mask_x = Node(
        package='depth_estimation',
        executable='depth_estimation_node',
        output='screen',
        parameters=[
            {
                'image_topic': '/zed/zed_node/rgb/image_rect_color',
                'rgb_camera_info_topic': '/zed/zed_node/rgb/camera_info',
                'pointcloud_topic' : '/zed/zed_node/point_cloud/cloud_registered',
                'depth_map_topic':'/zed/zed_node/depth/depth_registered',
                'use_pointcloud': False,
                'ground_truth': LaunchConfiguration('ground_truth'),
            }
        ],
        condition=LaunchConfigurationEquals('camera', 'zedx')
    )

    # Launch the mask nodes
    zed_mask_xm = Node(
        package='depth_estimation',
        executable='depth_estimation_node',
        output='screen',
        parameters=[
            {
                'image_topic': '/zed/zed_node/rgb/image_rect_color',
                'rgb_camera_info_topic': '/zed/zed_node/rgb/camera_info',
                'pointcloud_topic' : '/zed/zed_node/point_cloud/cloud_registered',
                'depth_map_topic':'/zed/zed_node/depth/depth_registered',
                'use_pointcloud': False,
                'ground_truth': LaunchConfiguration('ground_truth'),
            }
        ],
        condition=LaunchConfigurationEquals('camera', 'zedxm')
    )

    # Timer action to let the zed open properly
    wait_zed = TimerAction(
        period=8.0, #Delay in seconds
        actions=[zed_mask_x,
                 zed_mask_xm]
    )


    realsense_mask_f = Node(
        package='depth_estimation',
        executable='depth_estimation_node',
        output='screen',
        parameters=[
            {
                'image_topic': '/camera/camera/color/image_raw',
                'rgb_camera_info_topic': '/camera/camera/color/camera_info',
                'pointcloud_topic' : '/camera/camera/depth/color/points',
                'depth_map_topic':'/camera/camera/aligned_depth_to_color/image_raw',
                'use_pointcloud': False,
                'ground_truth': LaunchConfiguration('ground_truth'),
            }
        ],
        arguments=["--ros-args", "--log-level", "info"],
        condition=LaunchConfigurationEquals('camera', 'rsf')
    )

    realsense_mask_i = Node(
        package='depth_estimation',
        executable='depth_estimation_node',
        output='screen',
        parameters=[
            {
                'image_topic': '/camera/camera/color/image_raw',
                'rgb_camera_info_topic': '/camera/camera/color/camera_info',
                'pointcloud_topic' : '/camera/camera/depth/color/points',
                'depth_map_topic':'/camera/camera/aligned_depth_to_color/image_raw',
                'use_pointcloud': False,
                'ground_truth': LaunchConfiguration('ground_truth'),
            }
        ],
        arguments=["--ros-args", "--log-level", "info"],
        condition=LaunchConfigurationEquals('camera', 'rsi')
    )

    # Publish static transforms for the cameras
    static_transform_realsense_i = Node( # mimics the base frame of the zedx
        package='tf2_ros',
        executable='static_transform_publisher',
        arguments=['0.025', '0.016', '0.010', '0', '-1.571', '1.571', 'camera_color_optical_frame', 'zed_camera_link'],
        condition=LaunchConfigurationEquals('camera', 'rsi')
    )

    static_transform_realsense_f = Node( # mimics the base frame of the zedx
        package='tf2_ros',
        executable='static_transform_publisher',
        arguments=['0.025', '0.016', '0.010', '0', '-1.571', '1.571', 'camera_color_optical_frame', 'zed_camera_link'],
        condition=LaunchConfigurationEquals('camera', 'rsf')
    )

    static_transform_table = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        arguments=['-0.064339', '0.0245', '-0.032', '-1.571', '0', '-1.571', 'zed_camera_link', 'table_frame'],
    )


    # add all actions
    return [
        camera_launch,
        static_transform_table,
        static_transform_realsense_i,
        static_transform_realsense_f,
        wait_zed,
        realsense_mask_i,
        realsense_mask_f
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

    ground_truth_arg = DeclareLaunchArgument(
        name='ground_truth',
        default_value='0.0',
        description='Ground truth value for the plane detection'
    )

    return LaunchDescription([
        camera_arg,
        ground_truth_arg,
        OpaqueFunction(function=launch_description)
    ])
