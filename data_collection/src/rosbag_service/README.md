# ROS2 Rosbag Service Package

A ROS2 package that provides a service to programmatically start rosbag recording.

## Description

This package implements a ROS2 service that starts rosbag recording by specifying the bag file name and the topics to record. It’s particularly useful to automate data collection during experiments or tests.

## Package Structure

```
rosbag_service/
├── CMakeLists.txt
├── package.xml
├── README.md
├── launch/
│   └── rosbag_service_server.launch.py
├── src/
│   ├── rosbag_service_server.cpp
│   ├── rosbag_service_client.cpp
│   └── rosbag_stop_client.cpp
└── srv/
    ├── StartRosbag.srv
    └── StopRosbag.srv
```

## Usage

### Start the Server

#### Method 1: Using the launch file (recommended)
```bash
# With default parameters
ros2 launch rosbag_service rosbag_service_server.launch.py

# With a custom output directory
ros2 launch rosbag_service rosbag_service_server.launch.py output_dir:=/path/to/my/rosbags

# With custom topics
ros2 launch rosbag_service rosbag_service_server.launch.py topics:="['/camera/image_raw', '/camera/camera_info', '/odom']"
```

##### Launch file details

The launch file `launch/rosbag_service_server.launch.py` starts the node `rosbag_service_server` and exposes two launch-time arguments:

- `output_dir` (default: `./rosbags`): directory where rosbag recordings will be saved.
- `topics` (default: `['/rgb_image', '/depth_image', '/camera_info', '/tf', '/tf_static']`): list of topics to record.

Those arguments are passed as ROS parameters to the node, so you can override them at launch without changing any code.

#### Method 2: Run directly
```bash
# With default parameters
ros2 run rosbag_service rosbag_service_server

# With custom parameters
ros2 run rosbag_service rosbag_service_server --ros-args -p output_dir:=/path/to/rosbags -p topics:="['/topic1', '/topic2']"
```

### Use the Client

#### Method 1: Using the C++ client
```bash
ros2 run rosbag_service rosbag_service_client my_experiment_001
```

#### Method 2: Using the command line
```bash
ros2 service call /start_rosbag rosbag_service/srv/StartRosbag "{bag_name: 'test_recording'}"
```

### Stop a Recording

#### Method 1: Using the C++ client
```bash
ros2 run rosbag_service rosbag_stop_client my_experiment_001
```

#### Method 2: Using the command line
```bash
ros2 service call /stop_rosbag rosbag_service/srv/StopRosbag "{bag_name: 'test_recording'}"
```

## Usage Examples

### Example 1: Basic Recording
```bash
# Terminal 1: Start the server
ros2 launch rosbag_service rosbag_service_server.launch.py

# Terminal 2: Start recording
ros2 run rosbag_service rosbag_service_client experiment_001

# Terminal 3: Stop the recording when needed
ros2 run rosbag_service rosbag_stop_client experiment_001
```

### Example 2: Recording to a Specific Directory
```bash
# Terminal 1: Start the server with a custom directory
ros2 launch rosbag_service rosbag_service_server.launch.py output_dir:=/home/user/data/rosbags

# Terminal 2: Start recording
ros2 run rosbag_service rosbag_service_client camera_test_$(date +%Y%m%d_%H%M%S)
```

### Example 3: Custom Topics
```bash
# Start the server with topics specific to your setup
ros2 launch rosbag_service rosbag_service_server.launch.py \
    output_dir:=/home/user/experiments \
    topics:="['/camera/color/image_raw', '/camera/depth/image_rect_raw', '/camera/color/camera_info', '/tf', '/tf_static']"
```

## Configuration

### Server Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `output_dir` | string | `"."` | Directory where rosbag files are saved |
| `topics` | string_array | `["/rgb_image", "/depth_image", "/camera_info"]` | List of topics to record |

### Services

#### Start Recording Service

**Name:** `/start_rosbag`

**Type:** `rosbag_service/srv/StartRosbag`

**Request:**
- `string bag_name`: Rosbag name (without extension)

**Response:**
- `bool success`: True if the recording started successfully
- `string message`: Descriptive result message

#### Stop Recording Service

**Name:** `/stop_rosbag`

**Type:** `rosbag_service/srv/StopRosbag`

**Request:**
- `string bag_name`: Name of the rosbag recording to stop

**Response:**
- `bool success`: True if the recording was stopped successfully
- `string message`: Descriptive result message


## License

Apache License 2.0
