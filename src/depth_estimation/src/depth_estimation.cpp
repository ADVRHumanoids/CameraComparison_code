/**
 * @brief Contains the definition of the DepthEstimation node
 *
 * @see depth_estimation.hpp
 * @author Alessio Lovato
 * 
 * 
 * Copyright 2025 Lovato Alessio
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *       http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "depth_estimation.hpp"

DepthEstimation::DepthEstimation(const rclcpp::NodeOptions &options)
    : Node("depth_estimation", options)
{
	// Parameters
	auto param_desc = rcl_interfaces::msg::ParameterDescriptor{};
	param_desc.description = "Topic to listen for the RGB image";
	this->declare_parameter("image_topic", "/camera/camera/color/image_raw", param_desc);
	param_desc.description = "Topic to listen for the RGB camera_info";
	this->declare_parameter("rgb_camera_info_topic", "/camera/camera/color/camera_info", param_desc);
	param_desc.description = "Topic to listen for the poitcloud";
	this->declare_parameter("pointcloud_topic", "/camera/camera/depth/color/points", param_desc);
	param_desc.description = "Topic to listen for the depth map";
	this->declare_parameter("depth_map_topic", "/camera/camera/aligned_depth_to_color/image_raw", param_desc);
	param_desc.description = "Topic to listen for the mask";
	this->declare_parameter("mask_topic", "/mask",param_desc);
	param_desc.description = "Analyze also pointcloud";
	this->declare_parameter("use_pointcloud", true, param_desc);
	param_desc.description = "Percentage of the points remaining before stopping the search for another plane";
	this->declare_parameter("min_percentage", 0.3, param_desc);
	param_desc.description = "Publish the TF of the detected plane without modifications";
	this->declare_parameter("raw_tf", false, param_desc);
	param_desc.description = "Publish the normal of the detected plane on the same half-space of the parent frame-id (exiting from the plane)";
	this->declare_parameter("z_up", false, param_desc);
	param_desc.description = "Origin frame of the measurement";
	this->declare_parameter("reference_frame", "table_frame", param_desc);
  param_desc.description = "Ground truth distance from the object";
  this->declare_parameter("ground_truth", 0.0f, param_desc);
  param_desc.description = "Maximum number of iterations to log";
  this->declare_parameter("counter_max", 300, param_desc);

	// Read parameters
	use_pointcloud_ = this->get_parameter("use_pointcloud").as_bool();
	RCLCPP_INFO_STREAM(this->get_logger(), "Use_pointcloud: " << std::boolalpha << use_pointcloud_ << std::noboolalpha);
	min_percentage_ = this->get_parameter("min_percentage").as_double();
	if (min_percentage_ <= 0.0f)
	{
		RCLCPP_ERROR(this->get_logger(), "Min percentage of point can't be 0 or negative!");
		return;
	}
	reference_frame_ = this->get_parameter("reference_frame").as_string();
  if (reference_frame_.empty()) {
      RCLCPP_ERROR(this->get_logger(), "Reference frame can't be null!");
      return;
  }
  ground_truth_ = this->get_parameter("ground_truth").as_double();
  if (ground_truth_ == 0.0) {
      RCLCPP_ERROR(this->get_logger(), "Ground truth must be inserted or has to be greater than 0");
      return;
  }
  counter_max_ = this->get_parameter("counter_max").as_int();
  if (counter_max_ <= 0) {
      RCLCPP_ERROR(this->get_logger(), "Counter max must be greater than 0");
      return;
  }


    // parameter for depth_image_transport hint
    std::string depth_image_transport_param = "depth_image_transport";
    image_transport::TransportHints depth_hints(this, "raw", depth_image_transport_param);

    rclcpp::SubscriptionOptions sub_opts;
    // Update the subscription options to allow reconfigurable qos settings.
    sub_opts.qos_overriding_options = rclcpp::QosOverridingOptions{
        {
            // Here all policies that are desired to be reconfigurable are listed.
            rclcpp::QosPolicyKind::Depth,
            rclcpp::QosPolicyKind::Durability,
            rclcpp::QosPolicyKind::History,
            rclcpp::QosPolicyKind::Reliability,
        }};

    // depth image can use different transport.(e.g. compressedDepth)
    sub_depth_.subscribe(
        this, this->get_parameter("depth_map_topic").as_string(),
        depth_hints.getTransport(), rmw_qos_profile_default, sub_opts);

    // rgb uses normal ros transport hints.
    image_transport::TransportHints hints(this, "raw");
    sub_rgb_.subscribe(
        this, this->get_parameter("image_topic").as_string(),
        hints.getTransport(), rmw_qos_profile_default, sub_opts);

    // Other subscribers
    if (use_pointcloud_)
        sub_pcl_.subscribe(this, this->get_parameter("pointcloud_topic").as_string());
    sub_mask_.subscribe(this, this->get_parameter("mask_topic").as_string());
    sub_info_.subscribe(this, this->get_parameter("rgb_camera_info_topic").as_string());

    // Synchronize inputs. Topic subscriptions happen on demand in the connection callback.
    if (!use_pointcloud_)
    {
        sync_ = std::make_shared<Synchronizer>(
            SyncPolicy(10),
            sub_depth_,
            sub_rgb_,
			sub_info_,
            sub_mask_);
        sync_->registerCallback(
            std::bind(
                &DepthEstimation::SyncCallback,
                this,
                std::placeholders::_1,
                std::placeholders::_2,
                std::placeholders::_3,
                std::placeholders::_4));
    }
    else
    {
        sync_pointcloud_ = std::make_shared<PointcloudSynchronizer>(
            PointcloudSyncPolicy(10),
            sub_depth_,
            sub_rgb_,
			sub_info_,
            sub_pcl_,
            sub_mask_);
        sync_pointcloud_->registerCallback(
            std::bind(
                &DepthEstimation::SyncPointCloudCallback,
                this,
                std::placeholders::_1,
                std::placeholders::_2,
                std::placeholders::_3,
                std::placeholders::_4,
                std::placeholders::_5));
    }

    // Publishers
    img_pub_ = this->create_publisher<Image>("/target_image", 10);
    mask_img_pub_ = this->create_publisher<Image>("/masked_RGB", 10);
    depth_map_pub_ = this->create_publisher<Image>("/masked_depth", 10);
    counter_pub_ = this->create_publisher<std_msgs::msg::String>("/frame_counter", 10);
    info_repub_ = this->create_publisher<CameraInfo>("/camera_info", 10);
    img_repub_ = this->create_publisher<Image>("/rgb_image", 10);
    depth_map_repub_ = this->create_publisher<Image>("/depth_image", 10);

    rclcpp::QoS qos_reliable(10);
    qos_reliable.reliable();

    pcl_pub_ = this->create_publisher<PointCloud2>("/masked_pcl", qos_reliable);
    plane_pub_ = this->create_publisher<PointCloud2>("/detected_plane", qos_reliable);

    // TF Listener
    tf_buffer_ = std::make_unique<tf2_ros::Buffer>(this->get_clock());
    tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_);

    // TF Broadcaster
    tf_broadcaster_ =
        std::make_unique<tf2_ros::TransformBroadcaster>(*this);

    RCLCPP_INFO_STREAM(this->get_logger(), "Node started");
}

geometry_msgs::msg::Vector3 DepthEstimation::distance_from_reference(const std::string &actual_frame){
	if (actual_frame.empty())
		throw std::runtime_error("Invalid frame passed to distance_from_reference()");

	geometry_msgs::msg::TransformStamped t;

	try {
		t = tf_buffer_->lookupTransform(
			reference_frame_, actual_frame,
			tf2::TimePointZero);
		
	} catch (const tf2::TransformException &ex) {
		RCLCPP_ERROR(
			this->get_logger(), "Could not transform %s to %s: %s",
			reference_frame_.c_str(), actual_frame.c_str(), ex.what());
		throw std::runtime_error("Transform not available");
	}
	return t.transform.translation;
}


std::vector<Eigen::Vector3d> DepthEstimation::frame_conversion(const std::string from_frame, const std::string to_frame, const std::vector<Eigen::Vector3d> &points) {
    // If frames match, do not convert
    if (from_frame == to_frame)
       return points;

    geometry_msgs::msg::TransformStamped t;

	try {
		t = tf_buffer_->lookupTransform(
			to_frame, from_frame,
			tf2::TimePointZero);
	} catch (const tf2::TransformException &ex) {
		RCLCPP_ERROR(
			this->get_logger(), "Could not transform %s to %s: %s",
			from_frame.c_str(), to_frame.c_str(), ex.what());
		return {};
	}
	// Convert the transform to eigen
    auto tf_eigen{tf2::transformToEigen(t)};

    std::vector<Eigen::Vector3d> tf_points;

    for (auto &point : points)
        tf_points.push_back((tf_eigen * point));
    
    return tf_points;
}

void DepthEstimation::images_feedback(const Image::ConstSharedPtr &depth_msg,
                                  const Image::ConstSharedPtr &rgb_msg,
                                  const std::vector<cv::Point> &mask) {

  // Publish the masked image
  const cv::Mat masked{extract_ROI(rgb_msg, mask)};
  publish_image(masked, rgb_msg->encoding, mask_img_pub_);

  // Draw the target on the image and publish it
  const cv::Mat target{draw_target(rgb_msg, mask)};
  publish_image(target, rgb_msg->encoding, img_pub_);

  // Publish the depth map
  const cv::Mat depth_roi{extract_ROI(depth_msg, mask)};
  publish_image(depth_roi, depth_msg->encoding, depth_map_pub_);
  
}

void DepthEstimation::IncrementAndPublishCounter() {
    counter_++;
    auto msg = std::make_shared<std_msgs::msg::String>();
    msg->data = "Frame count: " + std::to_string(counter_);
    counter_pub_->publish(*msg);
}


sensor_msgs::msg::PointCloud2::ConstSharedPtr DepthEstimation::create_pcl(const Image::ConstSharedPtr &depth_msg,
                                                                       const Image::ConstSharedPtr &rgb_msg,
                                                                       const CameraInfo::ConstSharedPtr &info_msg,
                                                                       const std::vector<cv::Point> &mask)
{
     // Check for bad inputs
  if (depth_msg->header.frame_id != rgb_msg->header.frame_id) {
    RCLCPP_WARN_THROTTLE(
      get_logger(),
      *get_clock(),
      10000,  // 10 seconds
      "Depth image frame id [%s] doesn't match RGB image frame id [%s]",
      depth_msg->header.frame_id.c_str(), rgb_msg->header.frame_id.c_str());
  }

  // Update camera model
  model_.fromCameraInfo(info_msg);

  // Assume the depth image is the same size as the RGB image
  auto cloud_msg = std::make_shared<PointCloud2>();
  cloud_msg->header = depth_msg->header; // Use depth image time stamp
  cloud_msg->height = 1;                 // Use unorganized point cloud
  cloud_msg->width = mask.size();
  cloud_msg->is_dense = false;
  cloud_msg->is_bigendian = false;
  sensor_msgs::PointCloud2Modifier pcd_modifier(*cloud_msg);
  pcd_modifier.setPointCloud2FieldsByString(2, "xyz", "rgb"); // The color will be set to RGB

  try {
    // Supported color encodings: RGB8, BGR8
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
        RCLCPP_ERROR(get_logger(), "Unsupported encoding [%s]", rgb_msg->encoding.c_str());
        return nullptr;
    }
  

    // Convert Depth Image to Pointcloud
    if (depth_msg->encoding == sensor_msgs::image_encodings::TYPE_16UC1) {
      depth_image_proc::convertDepth<uint16_t>(depth_msg, mask, cloud_msg, model_);
    } else if (depth_msg->encoding == sensor_msgs::image_encodings::TYPE_32FC1) {
      depth_image_proc::convertDepth<float>(depth_msg, mask, cloud_msg, model_);
    } else {
      RCLCPP_ERROR(
        get_logger(), "Depth image has unsupported encoding [%s]", depth_msg->encoding.c_str());
      return nullptr;
    }

    // Convert RGB
    if (rgb_msg->encoding == sensor_msgs::image_encodings::RGB8) {
      depth_image_proc::convertRgb(rgb_msg, cloud_msg, mask, red_offset,  green_offset, blue_offset, color_step);
    } else if (rgb_msg->encoding == sensor_msgs::image_encodings::BGR8) {
      depth_image_proc::convertRgb(rgb_msg, cloud_msg, mask, red_offset,  green_offset, blue_offset, color_step);
    } else if (rgb_msg->encoding == sensor_msgs::image_encodings::BGRA8) {
      depth_image_proc::convertRgb(rgb_msg, cloud_msg, mask, red_offset,  green_offset, blue_offset, color_step);
    } else if (rgb_msg->encoding == sensor_msgs::image_encodings::RGBA8) {
      depth_image_proc::convertRgb(rgb_msg, cloud_msg, mask, red_offset,  green_offset, blue_offset, color_step);
    } else if (rgb_msg->encoding == sensor_msgs::image_encodings::MONO8) {
      depth_image_proc::convertRgb(rgb_msg, cloud_msg, mask, red_offset,  green_offset, blue_offset, color_step);
    } else {
      RCLCPP_ERROR(
        get_logger(), "RGB image has unsupported encoding [%s]", rgb_msg->encoding.c_str());
      return nullptr;
    }

	// Publish pcl
	pcl_pub_->publish(*cloud_msg);

    return cloud_msg;
  }
  catch(const std::exception& e)
  {
    RCLCPP_ERROR(get_logger(), "%s", e.what());
    return nullptr;
  }

}


void DepthEstimation::publish_plane(const sensor_msgs::msg::PointCloud2::ConstSharedPtr &cloud_msg) {
    // Get the all available planes in the pointcloud
    std::vector<Plane> planes{extract_planes(cloud_msg, min_percentage_)};
    if (planes.empty()) {
        RCLCPP_ERROR_STREAM(this->get_logger(), "No plane found in the pointcloud at timestamp: "
            << cloud_msg->header.stamp.sec << " s " << cloud_msg->header.stamp.nanosec << " ns");
        return;
    }
    // Publish the first plane detected
    sensor_msgs::msg::PointCloud2::SharedPtr output{planes[0].get_plane_msg()};
    output->header = cloud_msg->header;
    plane_pub_->publish(*output);

    // Publish TF of the centroid
    geometry_msgs::msg::TransformStamped msg;
    msg.header = cloud_msg->header;
    msg.transform = planes[0].get_tf(this->get_parameter("raw_tf").as_bool(),
                                     this->get_parameter("z_up").as_bool());
    msg.child_frame_id = "detected_plane";
    tf_broadcaster_->sendTransform(msg);

	// Get the tf from the reference frame
	geometry_msgs::msg::TransformStamped t_reference;

	try {
		t_reference = tf_buffer_->lookupTransform(
			reference_frame_, "detected_plane",
			tf2::TimePointZero, tf2::Duration(std::chrono::milliseconds(1000)));
	} catch (const tf2::TransformException &ex) {
		RCLCPP_ERROR(
			this->get_logger(), "Could not transform %s to %s: %s",
			"detected_plane", reference_frame_.c_str(), ex.what());
		return;
	}
	
	// Get the quaternion using Eigen
	tf2::Quaternion tf2_q{};
  tf2::fromMsg(t_reference.transform.rotation, tf2_q);
	tf2::Matrix3x3 m{tf2_q};
  double roll, pitch, yaw;
  m.getRPY(roll, pitch, yaw);

  // Convert from radiant to degrees
    auto rad_to_deg = [](double &rad) { return 180.0 * rad / M_PI; };
    RCLCPP_INFO_STREAM(this->get_logger(), "Centroid position [m] of the detected plane: x "
              << t_reference.transform.translation.x << " y " << t_reference.transform.translation.y << " z " << t_reference.transform.translation.z);
    RCLCPP_INFO_STREAM(this->get_logger(), "Angles [deg] of the detected plane: roll "
              << rad_to_deg(roll) << " pitch " << rad_to_deg(pitch) << " yaw " << rad_to_deg(yaw));
    RCLCPP_INFO_STREAM(this->get_logger(), "Pointcloud points: " << cloud_msg->data.size() << " Plane points: " << output->data.size());
    // Calculate the area of the plane
    std::vector<coordinates> points;
    for (const auto &point : planes[0].get_plane()->points)
      points.emplace_back(point.x, point.y);
    double area{calculate_area(points)};
    RCLCPP_INFO_STREAM(this->get_logger(), "Area of the plane: " << area << " m^2");
}

void DepthEstimation::SyncCallback(const Image::ConstSharedPtr &depth_msg,
                                const Image::ConstSharedPtr &rgb_msg,
                                const CameraInfo::ConstSharedPtr &info_msg,
                                const Mask::ConstSharedPtr &mask_msg)
{
  // Check the maximum number of iterations
  if (counter_ >= counter_max_)
    return;

	// Check there is at least 1 pixel in the mask
	if (mask_msg->size == 0)
		return;

    // Create a log barrier
    RCLCPP_INFO_STREAM(this->get_logger(), "New message at " << depth_msg->header.stamp.sec << " s "
                        << depth_msg->header.stamp.nanosec << " ns");
    // Update the selection mask
    std::vector<cv::Point> mask{mask_from_msg(mask_msg)};

    // Compute the average of the masked depth map
    std::vector<float> depth{depth_points_from_depth_map(depth_msg, mask)};
    
    // Add the distance from the optical frame to the reference frame
  	geometry_msgs::msg::Vector3 distance;
    try
    {
      distance = distance_from_reference(depth_msg->header.frame_id);
    }
    catch(const std::exception& e)
    {
      std::cerr << e.what() << '\n';
      return;
    }
    
    // Get depth average
    double depth_average{(std::accumulate(depth.begin(), depth.end(), 0.0f) / depth.size()) + distance.z};

    // Get RMSE value of the depth values
    double sum_sq_error = 0.0;
    for (float value : depth) {
        float error = value + distance.z - ground_truth_;
        sum_sq_error += error * error;
    }
    float rmse = std::sqrt(sum_sq_error / depth.size());

    // Get RMS value of the depth values
    double sum_sq_values = 0.0;
    for (float value : depth)
    {
      sum_sq_values += ((value + distance.z) * (value + distance.z));
    }
    float rms = std::sqrt(sum_sq_values / depth.size());

    RCLCPP_INFO_STREAM(this->get_logger(), "Depth map Average z [m]: " << depth_average);
    RCLCPP_INFO_STREAM(this->get_logger(), "RMSE of the depth map [m]: " << rmse);
    RCLCPP_INFO_STREAM(this->get_logger(), "Depth map RMS z [m]: " << rms);


    // Provide visual feedback
    images_feedback(depth_msg, rgb_msg, mask);

    // Create the pointcloud from the depth map
    PointCloud2::ConstSharedPtr pcl{create_pcl(depth_msg, rgb_msg, info_msg, mask)};

    // Detect and publish the plane
    publish_plane(pcl);

    // Republish the images and camera info
    img_repub_->publish(*rgb_msg);
    depth_map_repub_->publish(*depth_msg);
    info_repub_->publish(*info_msg);

    IncrementAndPublishCounter();
}

void DepthEstimation::SyncPointCloudCallback(const Image::ConstSharedPtr &depth_msg,
							const Image::ConstSharedPtr &rgb_msg,
							const CameraInfo::ConstSharedPtr &info_msg,
							const PointCloud2::ConstSharedPtr &pointcloud_msg,
							const Mask::ConstSharedPtr &mask_msg)
{
	// Check the maximum number of iterations
	if (counter_ >= counter_max_)
		return;

	// Check there is at least 1 pixel in the mask
	if (mask_msg->size == 0)
		return;

	// Create a log barrier
	RCLCPP_INFO_STREAM(this->get_logger(), "New message at " << depth_msg->header.stamp.sec << " s"
															 << depth_msg->header.stamp.nanosec << " ns");
	// Update the selection mask
	std::vector<cv::Point> mask{mask_from_msg(mask_msg)};

	// Compute the average of the masked depth map
	std::vector<float> depth{depth_points_from_depth_map(depth_msg, mask)};

	// Add the distance from the optical frame to the reference frame
	auto distance{distance_from_reference(depth_msg->header.frame_id)};

	// Get depth average
	double depth_average{(std::accumulate(depth.begin(), depth.end(), 0.0f) / depth.size()) + distance.z};
	// Get RMSE value of the depth values
	double sum_sq_error = 0.0;
	for (float value : depth)
	{
		float error = value - ground_truth_ + distance.z;
		sum_sq_error += error * error;
	}
	float rmse = std::sqrt(sum_sq_error / depth.size());

	// Get RMS value of the depth values
	double sum_sq_values = 0.0;
	for (float value : depth)
	{
		sum_sq_values += ((value + distance.z) * (value + distance.z));
	}
	float rms = std::sqrt(sum_sq_values / depth.size());

	// Crop the pointcloud using the mask
	sensor_msgs::msg::PointCloud2 copy{*pointcloud_msg};
	copy.height = 1; // Unordered pointcloud
	copy.width = mask.size();
	copy.row_step = mask.size() * pointcloud_msg->point_step;
	copy.data = pointcloud_from_mask(pointcloud_msg, mask);

	// Store the points of the pointcloud
	std::vector<Eigen::Vector3d> points;

	// TODO: Optimize this point picking (maybe insterting it in the pointcloud_from_mask() function)
	for (size_t pos{0}; pos < mask.size(); pos++)
	{
		float x_pcl, y_pcl, z_pcl;
		memcpy(&x_pcl, &copy.data[pos * copy.point_step + copy.fields[0].offset], sizeof(float));
		memcpy(&y_pcl, &copy.data[pos * copy.point_step + copy.fields[1].offset], sizeof(float));
		memcpy(&z_pcl, &copy.data[pos * copy.point_step + copy.fields[2].offset], sizeof(float));
		if (std::isfinite(x_pcl) && std::isfinite(y_pcl) && std::isfinite(z_pcl))
		{
			points.push_back(Eigen::Vector3d(x_pcl, y_pcl, z_pcl));
		}
	}

	// Check if the two frame ids correspond or convert the points from the pointcloud
	auto tf_points = frame_conversion(pointcloud_msg->header.frame_id, "table_frame", points);
	if (tf_points.empty())
	{
		RCLCPP_DEBUG_STREAM(this->get_logger(), "DepthComparator::SyncPointCloudCallback points transformation not possible");
		return; // No conversion can be done, so the points cannot be compared
	}

	// Extract z values
	// TODO: After optimization of the point extraction, maybe tf_points won't be available if the frame_ids are the same
	float sum = std::accumulate(tf_points.begin(), tf_points.end(), 0.0f,
								[](float acc, const Eigen::Vector3d &point)
								{
									return acc + point.z();
								});

	RCLCPP_INFO_STREAM(this->get_logger(), "Depth map Average z [m]: " << depth_average << "  Pointcloud Average z: " << sum / tf_points.size());
	RCLCPP_INFO_STREAM(this->get_logger(), "RMSE of the depth map [m]: " << rmse);
	RCLCPP_INFO_STREAM(this->get_logger(), "Depth map RMS z [m]: " << rms);

	// Provide visual feedback
	images_feedback(depth_msg, rgb_msg, mask);

	// Create the pointcloud from the depth map
	PointCloud2::ConstSharedPtr pcl{create_pcl(depth_msg, rgb_msg, info_msg, mask)};

	// Detect and publish the plane
	publish_plane(pcl);
	
	// Republish the images and camera info
	img_repub_->publish(*rgb_msg);
	depth_map_repub_->publish(*depth_msg);
	info_repub_->publish(*info_msg);

  IncrementAndPublishCounter();
}
