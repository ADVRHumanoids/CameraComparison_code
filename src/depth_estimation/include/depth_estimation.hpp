/**
 * @brief Contains the declaration of the DepthEstimation node
 *
 * This node receives an RGB image, depth image and an ordered pointcloud (when possible) from the camera. Listening on the /mask topic
 * receives the pixels of the RGB image that have to be used as reference. At this point, the depth average is estimated using the selected
 * pixels both using the pointcloud and depth image data. Furthermore, from the selected depth image and RGB image, a pointcloud is created and published.
 * This pointcloud is latter used to estimate the equation of the plane and thus its position in respect of the base link.
 *
 * @author Alessio Lovato
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

#ifndef DEPTH_ESTIMATION
#define DEPTH_ESTIMATION

#include <vector>
#include <algorithm>

#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>
#include <sensor_msgs/point_cloud2_iterator.hpp>
#include <sensor_msgs/msg/camera_info.hpp>
#include "mask_interfaces/msg/mask.hpp"

#include <message_filters/subscriber.h>
#include <message_filters/synchronizer.h>
#include <message_filters/sync_policies/exact_time.h>
#include <image_transport/image_transport.hpp>
#include <image_transport/subscriber_filter.hpp>
#include <tf2_ros/transform_listener.h>
#include <tf2_ros/buffer.h>
#include <tf2/exceptions.h>
#include <tf2_eigen/tf2_eigen.hpp>
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp> // To convert geometry_msgs::rotation into tf2::quaternion
#include <tf2/LinearMath/Matrix3x3.hpp> // To obtain conversion Quaternion to RPY
#include <eigen3/Eigen/Geometry>

#include <opencv2/core/types.hpp>   // For cv::Point
#include <opencv2/core/mat.hpp>     // For cv::Mat

#include "depth_image_proc/visibility.h"
#include "depth_image_proc/conversions.hpp"
#include "image_geometry/pinhole_camera_model.h"

#include "depth_estimation_utils.hpp"


 /** @brief ROS2 Node for synchronized processing of RGB, depth, mask, and point cloud data streams.
 *
 * The DepthEstimation node subscribes to multiple sensor topics (RGB image, depth image, mask, point cloud, and camera info),
 * synchronizes them using message_filters, and provides advanced processing such as:
 *   - Drawing bounding boxes and visual feedback on images based on mask data.
 *   - Calculating average depth of masked objects using either depth maps or point clouds.
 *   - Creating colored point clouds from depth and RGB images, filtered by mask and camera calibration.
 *   - Detecting planes in point clouds and publishing the results.
 *   - Transforming 3D points between coordinate frames using TF2.
 *
 * Publishers are provided for processed images, depth maps, masks, and point clouds.
 * The node supports both depth map and point cloud processing, configurable via a flag.
 *
 * @note This class requires ROS2, OpenCV, PCL, and TF2 dependencies.
 */
class DepthEstimation : public rclcpp::Node {

    public: 

    DepthEstimation(const rclcpp::NodeOptions &options);

    private:
    using PointCloud2 = sensor_msgs::msg::PointCloud2;
	using Image = sensor_msgs::msg::Image;
	using Mask = mask_interfaces::msg::Mask;
    using CameraInfo = sensor_msgs::msg::CameraInfo;

    // SYNCHRONIZATION
	using SyncPolicy =
    	message_filters::sync_policies::ExactTime<Image, Image, CameraInfo, Mask>;
	using PointcloudSyncPolicy =
		message_filters::sync_policies::ExactTime<Image, Image, CameraInfo, PointCloud2, Mask>;
	using Synchronizer = message_filters::Synchronizer<SyncPolicy>;
	using PointcloudSynchronizer = message_filters::Synchronizer<PointcloudSyncPolicy>;
	// Synchronizers
	std::shared_ptr<Synchronizer> sync_;
	std::shared_ptr<PointcloudSynchronizer> sync_pointcloud_;

    // LISTENERS
	image_transport::SubscriberFilter sub_depth_, sub_rgb_;
	message_filters::Subscriber<PointCloud2> sub_pcl_;
    message_filters::Subscriber<CameraInfo> sub_info_;
  	message_filters::Subscriber<Mask> sub_mask_;
  
	// PUBLISHERS
	// Image publishers
	rclcpp::Publisher<Image>::SharedPtr img_pub_, depth_map_pub_, mask_img_pub_;
	// Pointcloud publisher
	rclcpp::Publisher<PointCloud2>::SharedPtr pcl_pub_, plane_pub_;
	// Frame processing counter publisher
	rclcpp::Publisher<std_msgs::msg::String>::SharedPtr counter_pub_;
	// Image republishers
	rclcpp::Publisher<Image>::SharedPtr img_repub_, depth_map_repub_;
	// Camera info republisher
	rclcpp::Publisher<CameraInfo>::SharedPtr info_repub_;

	// TF2 LISTENER
	std::shared_ptr<tf2_ros::TransformListener> tf_listener_{nullptr};
	std::unique_ptr<tf2_ros::Buffer> tf_buffer_;

    // TF2 BROADCASTER
    std::unique_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster_;


    // CALLBACKS

	/**
	 * @brief Callback for the subscription of the image and mask topics
	 * @param depth_msg The depth map received
	 * @param rgb_msg The RGB image received
     * @param info_msg The RGB camera info msg
	 * @param mask_msg The mask received
	 * @details The callback will draw a bounding box around the object and publish the image with the target,
	 * calculate the average depth of the object and publish the images cropped to the bounding box of the mask.
	 */
	void SyncCallback(
		const Image::ConstSharedPtr & depth_msg,
		const Image::ConstSharedPtr & rgb_msg,
        const CameraInfo::ConstSharedPtr & info_msg,
		const Mask::ConstSharedPtr & mask_msg);

	/**
	 * @brief Callback for the subscription of the image, pointcloud and mask topics
	 * @param depth_msg The depth map received
	 * @param rgb_msg The RGB image received
     * @param info_msg The RGB camera info msg
	 * @param pointcloud_msg The pointcloud received
	 * @param mask_msg The mask received
	 * @details The callback will draw a bounding box around the object and publish the image with the target,
	 * calculate the average depth of the object (both depth map and pointcloud) and publish the images cropped to the bounding box of the mask.
	 */
	void SyncPointCloudCallback(
		const Image::ConstSharedPtr & depth_msg,
		const Image::ConstSharedPtr & rgb_msg,
        const CameraInfo::ConstSharedPtr & info_msg,
		const PointCloud2::ConstSharedPtr & pointcloud_msg,
		const Mask::ConstSharedPtr & mask_msg);

	// VARIABLES
	bool use_pointcloud_; // Flag to use pointcloud instead of depth map
    image_geometry::PinholeCameraModel model_; // Model of the camera
    float min_percentage_{0.3}; // Minimum percentage of point remaining in the pointcloud before quit plane recognition
	std::string reference_frame_{}; // Frame of the origin of the measurements
	double ground_truth_{0.0}; // Ground truth distance of the object from the camera
	int counter_max_{300}; // Maximum number of iterations
	int counter_{0}; // Current iteration

    // PRIVATE FUNCTIONS

    /**
     * @brief Uses the image publishers to create a visual feedback of the ROI in the RGB and depth images
     * @param depth_msg the depth msg
     * @param rgb_msg the rgb message
     * @param mask the mask
     */
    void images_feedback(const sensor_msgs::msg::Image::ConstSharedPtr &depth_msg,
                         const sensor_msgs::msg::Image::ConstSharedPtr &rgb_msg,
                         const std::vector<cv::Point> &mask);

    /**
     * @brief Creates a point cloud from depth and RGB images using camera calibration info and a mask.
     *
     * This function generates a PointCloud2 message by projecting the depth image into 3D space using a provided mask,
     * and coloring the points using the corresponding RGB image. The camera calibration information is used to accurately reconstruct
     * the 3D points.
     *
     * @param depth_msg Shared pointer to the input depth image message.
     * @param rgb_msg Shared pointer to the input RGB image message.
     * @param info_msg Shared pointer to the camera calibration information message.
     * @param mask Vector of cv::Point specifying the mask to filter points (only points within the mask are included).
     * @return A shared pointer to the generated PointCloud2 message.
     */
    PointCloud2::ConstSharedPtr create_pcl(const Image::ConstSharedPtr &depth_msg,
                                           const Image::ConstSharedPtr &rgb_msg,
                                           const CameraInfo::ConstSharedPtr &info_msg,
                                           const std::vector<cv::Point> &mask);

    /**
     * @brief Given a Pointcloud2 msg, uses PCL library to detect the plane and publishes it along 
     * with its position and orinetation in the INFO log.
     * @param cloud_msg Shared pointer to the input PointCloud2 message.
     */
    void publish_plane(const sensor_msgs::msg::PointCloud2::ConstSharedPtr &cloud_msg);


	/**
	 * @brief Returns the distance of the reference frame from a specific frame
	 * @param actual_frame the frame to be used to calculate the distance
	 * @return a Vector3 message containing the 3 distances
	*/
	geometry_msgs::msg::Vector3 distance_from_reference(const std::string &actual_frame);


    /**
	 * @brief Converts a series of points between two frames looking up to the tf2 transforms
	 * @param from_frame The original frame whose points are associated
	 * @param to_point The new frame to reference the points
	 * @param points The vector points [x, y, z] to move
	 * @return A vector of points [x,y,z] referenced to the 'to_frame' frame
	 * @note If the TF cannot be found, an empty vector is returned
	 */
	std::vector<Eigen::Vector3d> frame_conversion(const std::string from_frame, const std::string to_frame, const std::vector<Eigen::Vector3d> &points);

	/**
	 * @brief Increments the counter and publishes it on a dedicated topic.
	 * @details This function is used to keep track of the number of processed 
	 * frames and publish the count on the '/frame_counter' topic.
	 * @note The counter is incremented each time this function is called.
	 */
	void IncrementAndPublishCounter();
};

#include "rclcpp_components/register_node_macro.hpp"

// Register the component with class_loader.
RCLCPP_COMPONENTS_REGISTER_NODE(DepthEstimation)

#endif // End of file
