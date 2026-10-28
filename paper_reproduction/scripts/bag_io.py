"""Read archived image/calibration/TF messages without ROS or acquisition logs.

Used by: scripts.extract, through main.py extract --dataset PATH.
Inputs: a recording directory containing metadata.yaml and MCAP data.
Outputs: timestamp-matched RGB/depth pairs, CameraInfo, and reference transforms.
Adapted from revision_analysis/analyze.py and recover_bags.py; no external imports
from that repository are required. Raw recordings are always opened read-only.
"""

from collections import deque
from pathlib import Path
import struct

import cv2
import numpy as np
from mcap.exceptions import McapError
from mcap.reader import NonSeekingReader
from mcap.stream_reader import CRCValidationError
from rosbags.highlevel import AnyReader
from rosbags.typesys import Stores, get_typestore
from scipy.spatial.transform import Rotation


PARTIAL_RECORDING = "zedx_3000_hd_neural_natural"
TOPICS = {"/rgb_image", "/depth_image", "/camera_info", "/tf", "/tf_static"}


def stamp(message):
    """Keep nanosecond timestamps as integers throughout extraction."""
    return int(message.header.stamp.sec) * 10**9 + int(message.header.stamp.nanosec)


def image_array(message):
    """Decode ROS images respecting row padding, endianness, colour order and units."""
    encodings = {"16UC1": ("u2", 1), "32FC1": ("f4", 1), "bgr8": ("u1", 3),
                 "rgb8": ("u1", 3), "bgra8": ("u1", 4), "rgba8": ("u1", 4), "mono8": ("u1", 1)}
    if message.encoding not in encodings:
        raise ValueError(f"Unsupported image encoding: {message.encoding}")
    kind, channels = encodings[message.encoding]
    dtype = np.dtype((">" if message.is_bigendian else "<") + kind)
    if (message.height <= 0 or message.width <= 0 or len(message.data) != message.height * message.step
            or message.step < message.width * channels * dtype.itemsize):
        raise ValueError("Malformed image dimensions, data length or stride")
    shape = (message.height, message.width) if channels == 1 else (message.height, message.width, channels)
    strides = (message.step, dtype.itemsize) if channels == 1 else (message.step, channels * dtype.itemsize, dtype.itemsize)
    values = np.ndarray(shape, dtype=dtype, buffer=message.data, strides=strides)
    if message.encoding == "16UC1":
        return values.astype(np.float64) * .001
    if message.encoding == "32FC1":
        return values.astype(np.float64)
    if message.encoding in ("rgb8", "rgba8"):
        return cv2.cvtColor(values, cv2.COLOR_RGB2BGR if channels == 3 else cv2.COLOR_RGBA2BGR)
    if message.encoding == "bgra8":
        return cv2.cvtColor(values, cv2.COLOR_BGRA2BGR)
    if message.encoding == "mono8":
        return cv2.cvtColor(values, cv2.COLOR_GRAY2BGR)
    return values


def transform_matrix(transform):
    """Convert recorded parent-from-child transforms into homogeneous matrices."""
    q, v = transform.transform.rotation, transform.transform.translation
    values = [q.x, q.y, q.z, q.w, v.x, v.y, v.z]
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite recorded transform")
    matrix = np.eye(4)
    matrix[:3, :3] = Rotation.from_quat(values[:4]).as_matrix()
    matrix[:3, 3] = values[4:]
    return matrix


def reference_transform(transforms, frame):
    """Traverse either direction of the recorded TF tree to table_frame."""
    queue, seen = deque([(frame, np.eye(4))]), {frame}
    while queue:
        node, matrix = queue.popleft()
        if node == "table_frame":
            return matrix
        for (parent, child), edge in transforms.items():
            if child == node:
                nxt, step = parent, edge
            elif parent == node:
                nxt, step = child, np.linalg.inv(edge)
            else:
                continue
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, step @ matrix))
    raise ValueError(f"No recorded table_frame transform for {frame}")


def read_messages(path, status):
    """Use indexed bags normally; salvage only the known damaged MCAP prefix.

    Catch read errors around next() only: decoding and analysis failures must
    propagate, and CRC failures must never be accepted as a valid prefix.
    """
    if path.name != PARTIAL_RECORDING:
        status["reader"] = "rosbags.AnyReader"
        with AnyReader([path]) as reader:
            connections = [c for c in reader.connections if c.topic in TOPICS]
            for connection, _, raw in reader.messages(connections=connections):
                yield connection.topic, reader.deserialize(raw, connection.msgtype)
        return
    files = sorted(path.glob("*.mcap"))
    if len(files) != 1:
        raise ValueError("Known partial recording must have exactly one MCAP")
    status["reader"] = "mcap.NonSeekingReader (CRC-checked)"
    store = get_typestore(Stores.ROS2_HUMBLE)
    with files[0].open("rb") as stream:
        iterator = iter(NonSeekingReader(stream, validate_crcs=True, record_size_limit=256 * 1024**2)
                        .iter_messages(topics=sorted(TOPICS), log_time_order=False))
        while True:
            try:
                schema, channel, message = next(iterator)
            except StopIteration:
                break
            except CRCValidationError:
                raise
            except (McapError, EOFError, struct.error, ValueError) as error:
                status["reader_error"] = f"{type(error).__name__}: {error}"
                break
            if schema is None:
                raise ValueError("Missing ROS message schema")
            yield channel.topic, store.deserialize_cdr(message.data, schema.name)


def paired_frames(messages, status):
    """Match exact header times with bounded buffers and checked stable calibration."""
    transforms, pending, seen = {}, {}, {"/rgb_image": set(), "/depth_image": set()}
    info, calibration = None, None
    previous = -1
    for topic, message in messages:
        if topic in ("/tf", "/tf_static"):
            for transform in message.transforms:
                transforms[transform.header.frame_id, transform.child_frame_id] = transform_matrix(transform)
        elif topic == "/camera_info":
            k = np.asarray(message.k).reshape(3, 3)
            if (not np.isfinite(k).all() or k[0, 0] <= 0 or k[1, 1] <= 0
                    or message.width <= 0 or message.height <= 0):
                raise ValueError("Missing or invalid CameraInfo calibration")
            signature = (message.width, message.height, message.header.frame_id, tuple(message.k))
            if calibration is not None and signature != calibration:
                raise ValueError("CameraInfo calibration changed within recording")
            info, calibration = message, signature
        elif topic in seen:
            timestamp = stamp(message)
            if timestamp in seen[topic]:
                raise ValueError(f"Duplicate {topic} timestamp: {timestamp}")
            seen[topic].add(timestamp)
            pending.setdefault(timestamp, {})[topic] = message
        else:
            raise ValueError(f"Unexpected extraction topic: {topic}")

        while pending and info is not None:
            timestamp = min(pending)
            pair = pending[timestamp]
            if len(pair) != 2:
                break
            rgb, depth = pair["/rgb_image"], pair["/depth_image"]
            if timestamp <= previous:
                raise ValueError("Frame timestamps are not strictly increasing")
            if (depth.width, depth.height, depth.header.frame_id) != (info.width, info.height, info.header.frame_id):
                raise ValueError("CameraInfo dimensions/frame do not match depth")
            matrix = reference_transform(transforms, depth.header.frame_id)
            del pending[timestamp]
            previous = timestamp
            yield rgb, depth, info, matrix
        # Published bags can queue many RGB messages before their matching depths.
        if len(pending) > 300:
            raise ValueError("More than 300 pending timestamps; recording exceeds the frame limit")
    status.update(rgb_messages=len(seen["/rgb_image"]), depth_messages=len(seen["/depth_image"]),
                  unmatched_rgb=sum("/rgb_image" in pair for pair in pending.values()),
                  unmatched_depth=sum("/depth_image" in pair for pair in pending.values()))
    if pending and not status.get("reader_error"):
        raise ValueError("Unpaired images or missing calibration at end of recording")
