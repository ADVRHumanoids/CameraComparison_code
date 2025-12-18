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

#include <functional>
#include <memory>
#include <mutex>
#include <string>

#include "cv_bridge/cv_bridge.h"

#include "depth_image_proc/conversions.hpp"
#include "../../include/depth_image_proc/point_cloud_xyzrgb.hpp"
#include <image_transport/image_transport.hpp>
#include <opencv2/imgproc/imgproc.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/point_cloud2_iterator.hpp>


namespace depth_image_proc
{


PointCloudXyzrgbNode::PointCloudXyzrgbNode(const rclcpp::NodeOptions & options)
: rclcpp::Node("PointCloudXyzrgbNode", options)
{
  // Read parameters
  int queue_size = this->declare_parameter<int>("queue_size", 5);
  bool use_exact_sync = this->declare_parameter<bool>("exact_sync", true);

  auto param_desc = rcl_interfaces::msg::ParameterDescriptor{};
  param_desc.description = "Publish the detected plane and TF";
  this->declare_parameter("publish_plane", true, param_desc);
  param_desc.description = "Publish the TF of the detected plane without modifications";
  this->declare_parameter("raw_tf", false, param_desc);
  param_desc.description = "Publish the normal of the detected plane on the same half-space of the parent frame-id (exiting from the plane)";
  this->declare_parameter("z_up", true, param_desc);

  // Synchronize inputs. Topic subscriptions happen on demand in the connection callback.
  if (use_exact_sync) {
    exact_sync_ = std::make_shared<ExactSynchronizer>(
      ExactSyncPolicy(queue_size),
      sub_depth_,
      sub_rgb_,
      sub_info_,
      sub_mask_);
    exact_sync_->registerCallback(
      std::bind(
        &PointCloudXyzrgbNode::imageCb,
        this,
        std::placeholders::_1,
        std::placeholders::_2,
        std::placeholders::_3,
        std::placeholders::_4));
  } else {
    sync_ = std::make_shared<Synchronizer>(SyncPolicy(queue_size), sub_depth_, sub_rgb_, sub_info_, sub_mask_);
    sync_->registerCallback(
      std::bind(
        &PointCloudXyzrgbNode::imageCb,
        this,
        std::placeholders::_1,
        std::placeholders::_2,
        std::placeholders::_3,
        std::placeholders::_4));
  }

  // Monitor whether anyone is subscribed to the output
  // TODO(ros2) Implement when SubscriberStatusCallback is available
  // ros::SubscriberStatusCallback connect_cb = boost::bind(&PointCloudXyzrgbNode::connectCb, this);
  connectCb();
  // TODO(ros2) Implement when SubscriberStatusCallback is available
  // Make sure we don't enter connectCb() between advertising and assigning to pub_point_cloud_
  std::lock_guard<std::mutex> lock(connect_mutex_);
  // TODO(ros2) Implement connect_cb when SubscriberStatusCallback is available
  // pub_point_cloud_ = depth_nh.advertise<PointCloud>("points", 1, connect_cb, connect_cb);
  pub_point_cloud_ = create_publisher<PointCloud2>("pointcloud", rclcpp::SensorDataQoS());
  // TODO(ros2) Implement connect_cb when SubscriberStatusCallback is available

  // Create the image publishers
  img_pub_ = this->create_publisher<sensor_msgs::msg::Image>("/ROI_image", 10);
  depth_map_pub_ = this->create_publisher<sensor_msgs::msg::Image>("/ROI_depth", 10);
  debug_roi_ = this->create_publisher<sensor_msgs::msg::Image>("/debug_roi", 10);

  // Initialize the variables
  publish_plane_ = this->get_parameter("publish_plane").as_bool();
  if(publish_plane_) {
    plane_pcl_pub_ = this->create_publisher<sensor_msgs::msg::PointCloud2>("/plane_detected", 10);
    tf_broadcaster_ =  std::make_unique<tf2_ros::TransformBroadcaster>(*this);
  }

}

// Handles (un)subscribing when clients (un)subscribe
void PointCloudXyzrgbNode::connectCb()
{
  std::lock_guard<std::mutex> lock(connect_mutex_);
  // TODO(ros2) Implement getNumSubscribers when rcl/rmw support it
  // if (pub_point_cloud_->getNumSubscribers() == 0)
  if (0) {
    // TODO(ros2) Implement getNumSubscribers when rcl/rmw support it
    sub_depth_.unsubscribe();
    sub_rgb_.unsubscribe();
    sub_info_.unsubscribe();
    sub_mask_.unsubscribe();
  } else if (!sub_depth_.getSubscriber()) {
    // parameter for depth_image_transport hint
    std::string depth_image_transport_param = "depth_image_transport";
    image_transport::TransportHints depth_hints(this, "raw", depth_image_transport_param);

    rclcpp::SubscriptionOptions sub_opts;
    // Update the subscription options to allow reconfigurable qos settings.
    sub_opts.qos_overriding_options = rclcpp::QosOverridingOptions {
      {
        // Here all policies that are desired to be reconfigurable are listed.
        rclcpp::QosPolicyKind::Depth,
        rclcpp::QosPolicyKind::Durability,
        rclcpp::QosPolicyKind::History,
        rclcpp::QosPolicyKind::Reliability,
      }};

    // depth image can use different transport.(e.g. compressedDepth)
    sub_depth_.subscribe(
      this, "depth_registered/image_rect",
      depth_hints.getTransport(), rmw_qos_profile_default, sub_opts);

    // rgb uses normal ros transport hints.
    image_transport::TransportHints hints(this, "raw");
    sub_rgb_.subscribe(
      this, "rgb/image_rect_color",
      hints.getTransport(), rmw_qos_profile_default, sub_opts);
    sub_info_.subscribe(this, "rgb/camera_info");
    sub_mask_.subscribe(this, "/mask");
  }
}

void PointCloudXyzrgbNode::imageCb(
  const Image::ConstSharedPtr & depth_msg_in,
  const Image::ConstSharedPtr & rgb_msg_in,
  const CameraInfo::ConstSharedPtr & info_msg,
  const Mask::ConstSharedPtr & mask_msg)
{
  // Check for bad inputs
  if (depth_msg_in->header.frame_id != rgb_msg_in->header.frame_id) {
    RCLCPP_WARN_THROTTLE(
      get_logger(),
      *get_clock(),
      10000,  // 10 seconds
      "Depth image frame id [%s] doesn't match RGB image frame id [%s]",
      depth_msg_in->header.frame_id.c_str(), rgb_msg_in->header.frame_id.c_str());
  }

  // Update camera model
  model_.fromCameraInfo(info_msg);

  // Assume the depth image is the same size as the RGB image
  // Crop the images to the ROI
  std::vector<cv::Point> mask{mask_from_msg(mask_msg)};
  try{
    cv::Mat depth_roi = extract_ROI(depth_msg_in, mask);
    cv::Mat rgb_roi = extract_ROI(rgb_msg_in, mask);
    // Convert the images to the correct format
    Image::ConstSharedPtr rgb_msg{cv_mat_to_msg(rgb_roi, rgb_msg_in->encoding)};
    Image::ConstSharedPtr depth_msg{cv_mat_to_msg(depth_roi, depth_msg_in->encoding)};
    // Draw the target on the image and publish it
    cv::Mat target{draw_target(rgb_msg_in, mask)};
    publish_image(target, rgb_msg->encoding, img_pub_);
    publish_image(rgb_roi, rgb_msg->encoding, debug_roi_);
    // Publish the depth map
    depth_map_pub_ -> publish(*depth_msg);
    // Supported color encodings: RGB8, BGR8, MONO8
    int red_offset, green_offset, blue_offset, color_step;
    if (rgb_msg->encoding == sensor_msgs::image_encodings::RGB8) {
      red_offset = 0;
      green_offset = 1;
      blue_offset = 2;
      color_step = 3;
    } else if (rgb_msg->encoding == sensor_msgs::image_encodings::RGBA8) {
      red_offset = 0;
      green_offset = 1;
      blue_offset = 2;
      color_step = 4;
    } else if (rgb_msg->encoding == sensor_msgs::image_encodings::BGR8) {
      red_offset = 2;
      green_offset = 1;
      blue_offset = 0;
      color_step = 3;
    } else if (rgb_msg->encoding == sensor_msgs::image_encodings::BGRA8) {
      red_offset = 2;
      green_offset = 1;
      blue_offset = 0;
      color_step = 4;
    } else if (rgb_msg->encoding == sensor_msgs::image_encodings::MONO8) {
      red_offset = 0;
      green_offset = 0;
      blue_offset = 0;
      color_step = 1;
    } else {
      try {
        rgb_msg = cv_bridge::toCvCopy(rgb_msg, sensor_msgs::image_encodings::RGB8)->toImageMsg();
      } catch (cv_bridge::Exception & e) {
        RCLCPP_ERROR(
          get_logger(), "Unsupported encoding [%s]: %s", rgb_msg->encoding.c_str(), e.what());
        return;
      }
      red_offset = 0;
      blue_offset = 2;
      color_step = 3;
    }

    auto cloud_msg = std::make_shared<PointCloud2>();
    cloud_msg->header = depth_msg_in->header;  // Use depth image time stamp
    cloud_msg->height = 1;  // Use unorganized point cloud
    cloud_msg->width = mask.size();
    cloud_msg->is_dense = false;
    cloud_msg->is_bigendian = false;
  

    sensor_msgs::PointCloud2Modifier pcd_modifier(*cloud_msg);
    pcd_modifier.setPointCloud2FieldsByString(2, "xyz", "rgb");

    // Convert Depth Image to Pointcloud
    if (depth_msg_in->encoding == sensor_msgs::image_encodings::TYPE_16UC1) {
      convertDepth<uint16_t>(depth_msg_in, mask, cloud_msg, model_);
    } else if (depth_msg_in->encoding == sensor_msgs::image_encodings::TYPE_32FC1) {
      convertDepth<float>(depth_msg_in, mask, cloud_msg, model_);
    } else {
      RCLCPP_ERROR(
        get_logger(), "Depth image has unsupported encoding [%s]", depth_msg_in->encoding.c_str());
      return;
    }

    // Convert RGB
    if (rgb_msg_in->encoding == sensor_msgs::image_encodings::RGB8) {
      convertRgb(rgb_msg_in, cloud_msg, mask, red_offset,  green_offset, blue_offset, color_step);
    } else if (rgb_msg_in->encoding == sensor_msgs::image_encodings::BGR8) {
      convertRgb(rgb_msg_in, cloud_msg, mask, red_offset,  green_offset, blue_offset, color_step);
    } else if (rgb_msg_in->encoding == sensor_msgs::image_encodings::BGRA8) {
      convertRgb(rgb_msg_in, cloud_msg, mask, red_offset,  green_offset, blue_offset, color_step);
    } else if (rgb_msg_in->encoding == sensor_msgs::image_encodings::RGBA8) {
      convertRgb(rgb_msg_in, cloud_msg, mask, red_offset,  green_offset, blue_offset, color_step);
    } else if (rgb_msg_in->encoding == sensor_msgs::image_encodings::MONO8) {
      convertRgb(rgb_msg_in, cloud_msg, mask, red_offset,  green_offset, blue_offset, color_step);
    } else {
      RCLCPP_ERROR(
        get_logger(), "RGB image has unsupported encoding [%s]", rgb_msg->encoding.c_str());
      return;
    }

    // Publish the point cloud
    pub_point_cloud_->publish(*cloud_msg);
    if (publish_plane_)
    {
      // Detect and publish the biggest plane
      publish_biggest_plane(cloud_msg);
    }
  }
  catch(const std::exception& e)
  {
    RCLCPP_ERROR(get_logger(), "%s", e.what());
    return;
  }

}

void PointCloudXyzrgbNode::publish_biggest_plane(const sensor_msgs::msg::PointCloud2::SharedPtr & cloud_msg) {
  // Convert to PCL
  pcl::PointCloud<pcl::PointXYZRGB>::Ptr cloud = convert_to_pcl(cloud_msg);
  // Extract the biggest plane
  try {
  Plane plane(cloud, cloud_msg->header.frame_id);
  // Publish the detected plane
  sensor_msgs::msg::PointCloud2::SharedPtr output(plane.get_plane_msg());
  output->header = cloud_msg->header;
  plane_pcl_pub_->publish(*output);
  // Publish TF of the centroid
  geometry_msgs::msg::TransformStamped msg;
  msg.header = cloud_msg->header;
  msg.transform = plane.get_tf(this->get_parameter("raw_tf").as_bool(), 
                               this->get_parameter("z_up").as_bool());
  msg.child_frame_id = "detected_plane";
  tf_broadcaster_->sendTransform(msg);

  } catch (const std::exception & e) {
    RCLCPP_ERROR(this->get_logger(), "Error extracting plane: %s", e.what());
  }

}

}  // namespace depth_image_proc


