// Copyright (c) 2008, Willow Garage, Inc.
// All rights reserved.
//
// Software License Agreement (BSD License 2.0)
//
// Redistribution and use in source and binary forms, with or without
// modification, are permitted provided that the following conditions
// are met:
//
//  * Redistributions of source code must retain the above copyright
//    notice, this list of conditions and the following disclaimer.
//  * Redistributions in binary form must reproduce the above
//    copyright notice, this list of conditions and the following
//    disclaimer in the documentation and/or other materials provided
//    with the distribution.
//  * Neither the name of the Willow Garage nor the names of its
//    contributors may be used to endorse or promote products derived
//    from this software without specific prior written permission.
//
// THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
// "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
// LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
// FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
// COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
// INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
// BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
// LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
// CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
// LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
// ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
// POSSIBILITY OF SUCH DAMAGE.

#ifndef DEPTH_IMAGE_PROC__POINT_CLOUD_XYZRGB_HPP_
#define DEPTH_IMAGE_PROC__POINT_CLOUD_XYZRGB_HPP_

#include <memory>
#include <mutex>

#include "depth_image_proc/visibility.h"
#include "image_geometry/pinhole_camera_model.h"
#include "message_filters/subscriber.h"
#include "message_filters/synchronizer.h"
#include "message_filters/sync_policies/exact_time.h"
#include "message_filters/sync_policies/approximate_time.h"

#include <image_transport/image_transport.hpp>
#include <image_transport/subscriber_filter.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <tf2_ros/transform_broadcaster.h>


// Custom includes
#include "../utils.hpp"
#include "mask_interfaces/msg/mask.hpp"
#include "mask_interfaces/msg/pixel.hpp"


namespace depth_image_proc
{
  
/**
 * @class PointCloudXyzrgbNode
 * @brief ROS 2 node for processing synchronized depth, RGB, camera info, and mask messages to generate and publish XYZRGB point clouds.
 *
 * This node subscribes to depth images, RGB images, camera info, and mask messages, synchronizes them, and generates a colored point cloud.
 * It also provides functionality to detect and publish the largest plane in the point cloud, along with the TF of the centroid and various debug and ROI images.
 *
 * Subscriptions:
 * - Depth image (sensor_msgs::msg::Image)
 * - RGB image (sensor_msgs::msg::Image)
 * - Camera info (sensor_msgs::msg::CameraInfo)
 * - Mask (mask_interfaces::msg::Mask)
 *
 * Publications:
 * - Point cloud (sensor_msgs::msg::PointCloud2)
 * - ROI image (sensor_msgs::msg::Image)
 * - Debug ROI image (sensor_msgs::msg::Image)
 * - ROI depth image (sensor_msgs::msg::Image)
 * - Plane point cloud (sensor_msgs::msg::PointCloud2)
 * - TF transforms (tf2_ros::TransformBroadcaster)
 *
 * Parameters:
 * @param queue_size (int, default: 5): Queue size for message synchronization.
 * @param exact_sync (bool, default: true): Whether to use exact time synchronization for input messages.
 * @param publish_plane (bool, default: true): Publish the detected plane and its TF.
 * @param raw_tf (bool, default: false): Publish the TF of the detected plane without modifications.
 * @param z_up (bool, default: true): Publish the normal of the detected plane on the same half-space of the parent frame-id (exiting from the plane).
 *
 * Custom Features:
 * - Optionally publishes the detected plane in the point cloud.
 * - Publishes debug and ROI images for visualization and analysis.
 *
 * Thread Safety:
 * - Uses a mutex to protect publisher connections.
 *
 * @note This class is part of the depth_image_proc namespace.
 */
class PointCloudXyzrgbNode : public rclcpp::Node
{
public:
  DEPTH_IMAGE_PROC_PUBLIC PointCloudXyzrgbNode(const rclcpp::NodeOptions & options);

private:
  using PointCloud2 = sensor_msgs::msg::PointCloud2;
  using Image = sensor_msgs::msg::Image;
  using CameraInfo = sensor_msgs::msg::CameraInfo;
  using Mask = mask_interfaces::msg::Mask;

  // Subscriptions
  image_transport::SubscriberFilter sub_depth_, sub_rgb_;
  message_filters::Subscriber<CameraInfo> sub_info_;
  message_filters::Subscriber<Mask> sub_mask_;
  using SyncPolicy =
    message_filters::sync_policies::ApproximateTime<Image, Image, CameraInfo, Mask>;
  using ExactSyncPolicy =
    message_filters::sync_policies::ExactTime<Image, Image, CameraInfo, Mask>;
  using Synchronizer = message_filters::Synchronizer<SyncPolicy>;
  using ExactSynchronizer = message_filters::Synchronizer<ExactSyncPolicy>;
  std::shared_ptr<Synchronizer> sync_;
  std::shared_ptr<ExactSynchronizer> exact_sync_;

  // Publications
  std::mutex connect_mutex_;
  rclcpp::Publisher<PointCloud2>::SharedPtr pub_point_cloud_;

  image_geometry::PinholeCameraModel model_;

  void connectCb();

  void imageCb(
    const Image::ConstSharedPtr & depth_msg,
    const Image::ConstSharedPtr & rgb_msg,
    const CameraInfo::ConstSharedPtr & info_msg,
    const Mask::ConstSharedPtr & mask_msg);

  // Custom variables
  bool publish_plane_; // Flag to publish the detected plane

  // Custom publications
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr img_pub_;             // ROI image
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr debug_roi_;         // RGB image
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr depth_map_pub_;       // ROI depth image
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr plane_pcl_pub_; // Plane pointcloud
  std::unique_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster_;             // TF broadcaster
  
  // Custom functions
  
  /**
   * @brief Detect the biggest plane in the pointcloud and publish it
   * @param cloud_msg The pointcloud message
   */
  void publish_biggest_plane(const sensor_msgs::msg::PointCloud2::SharedPtr & cloud_msg);
};

}  // namespace depth_image_proc

#include "rclcpp_components/register_node_macro.hpp"

// Register the component with class_loader.
RCLCPP_COMPONENTS_REGISTER_NODE(depth_image_proc::PointCloudXyzrgbNode)

#endif  // DEPTH_IMAGE_PROC__POINT_CLOUD_XYZRGB_HPP_