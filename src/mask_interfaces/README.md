# mask_interfaces

ROS 2 interface package defining messages for publishing/transporting a **pixel mask** (e.g., segmentation output or region-of-interest mask).

This package contains only `.msg` definitions and generates language-specific message code via `rosidl`.

## What's inside

### Messages

#### `mask_interfaces/msg/Pixel.msg`
A single pixel location.

Fields:
- `uint32 x` — pixel x coordinate (column)
- `uint32 y` — pixel y coordinate (row)

#### `mask_interfaces/msg/Mask.msg`
A mask represented as an unordered list/array of pixels.

Fields:
- `std_msgs/Header header` — timestamp + frame information
- `mask_interfaces/Pixel[] pixels` — pixels belonging to the mask
- `uint32 size` — number of pixels in the mask (typically should match `len(pixels)`)

## Dependencies

- Build tool: `ament_cmake`
- Interface generation: `rosidl_default_generators`
- Runtime: `rosidl_default_runtime`
- Message dependency: `std_msgs`

## Build

From your ROS 2 workspace root:

```bash
colcon build --packages-select mask_interfaces
```

Then source:

```bash
source install/setup.bash
```

## Usage

### Verify the interfaces were generated

```bash
ros2 interface show mask_interfaces/msg/Pixel
ros2 interface show mask_interfaces/msg/Mask
```

### Publish a `Mask` from the CLI

Example publishing a small 3-pixel mask (adjust the topic name as needed):

```bash
ros2 topic pub --once /mask mask_interfaces/msg/Mask "{header: {frame_id: 'camera', stamp: {sec: 0, nanosec: 0}}, pixels: [{x: 10, y: 20}, {x: 11, y: 20}, {x: 12, y: 20}], size: 3}"
```

### Subscribe and echo

```bash
ros2 topic echo /mask
```

## Notes / conventions

- `size` is included explicitly; producers should set it to match the actual number of entries in `pixels`.
- Coordinates are expressed in image pixel units. By convention, `x` increases to the right and `y` increases downward.

## License

Apache-2.0 (see `LICENSE`).
