/** 
 * @brief Contains the definition of the depth estimation utility functions
 *
 * @see depth_estimation_utils.hpp
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

#include "depth_estimation_utils.hpp"

/* #region Plane class */

Plane::Plane(const pcl::PointCloud<pcl::PointXYZRGB>::Ptr cloud,
    const std::string &frame_id,
    const pcl::PointIndices::Ptr indices)
    : indices_{indices}
{
    // Check there is a reference for the pointcloud
    if (frame_id.empty())
        throw std::invalid_argument("Frame id cannot be empty");

    // Allocate memory for indices if not required externally
    if (indices_ == nullptr)
        indices_ = std::make_shared<pcl::PointIndices>();

    // Extract the biggest plane from the pointcloud
    extract_plane(cloud);

    // Free the memory of the indices if not required outside
    if (indices == nullptr)
        indices_ = nullptr;

    // If the plane is not valid, clear the pointcloud and coefficients
    if (!valid_) {
        clear();
        return;
    }
    // Compute the centroid of the plane
    pcl::CentroidPoint<pcl::PointXYZRGB> centroid;
    for (const auto &point : plane_->points)
    {
        centroid.add(point);
    }
    // Get the centroid point
    centroid.get(centroid_point_);

}

void Plane::clear()
{
    // Clear the pointcloud and coefficients
    plane_ = nullptr;
    coefficients_ = nullptr;
    indices_ = nullptr;
    valid_ = false;
}

geometry_msgs::msg::Transform Plane::get_tf(bool raw = false, bool z_up = true) const
{
    // Convert the centroid to a Pose message
    geometry_msgs::msg::Transform tf;
    tf.translation.x = centroid_point_.x;
    tf.translation.y = centroid_point_.y;
    tf.translation.z = centroid_point_.z;
    // Set the orientation (the normal vectors are the coefficients a,b,c of the plane model ax + by + cz + d = 0)
    Eigen::Vector3f normal(coefficients_->values[0], coefficients_->values[1], coefficients_->values[2]);
    Eigen::Quaternionf q;
    q.setFromTwoVectors(Eigen::Vector3f::UnitZ(), normal);
    q.normalize();
    tf.rotation.x = q.x();
    tf.rotation.y = q.y();
    tf.rotation.z = q.z();
    tf.rotation.w = q.w();

    // Determine if the origin in in the same half-space of the normal
    // Since p = (d/sqrt(a^2 + b^2 + c^2)), thus the sign of p is the same as the sign of d
    // If the sign of d is positive, the origin is in the same half-space of the normal, 
    // thus there is the need to invert the normal

    // Return the correct TF based on the aligned and z_up parameters
    if(!raw &&
       ((coefficients_->values[3] > 0 && !z_up) || (coefficients_->values[3] < 0 && z_up))) 
    {
        Eigen::Vector3f normal(coefficients_->values[0], coefficients_->values[1], coefficients_->values[2]);
        Eigen::Quaternionf q, rotation;
        q.setFromTwoVectors(Eigen::Vector3f::UnitZ(), normal);
        rotation = Eigen::Quaternionf(0,0,1,0); // Rotation of 180 degrees around the Y axis
        q = q*rotation;
        q.normalize();
        tf.rotation.x = q.x();
        tf.rotation.y = q.y();
        tf.rotation.z = q.z();
        tf.rotation.w = q.w();
    }
    return tf;
}

void Plane::extract_plane(const pcl::PointCloud<pcl::PointXYZRGB>::Ptr cloud) {
    // Create the segmentation object
    pcl::SACSegmentation<pcl::PointXYZRGB> seg;
    seg.setOptimizeCoefficients (true);
    seg.setModelType (pcl::SACMODEL_PLANE);
    seg.setMethodType (pcl::SAC_RANSAC);
    seg.setMaxIterations (100);
    seg.setDistanceThreshold (0.01);
    seg.setInputCloud (cloud);
    seg.segment (*indices_, *coefficients_);
    if (indices_->indices.size () == 0) {
        clear();
        throw std::runtime_error("Could not estimate a planar model for the given dataset.");
    }
    // Extract the inliers
    pcl::ExtractIndices<pcl::PointXYZRGB> extract;
    extract.setInputCloud (cloud);
    extract.setIndices (indices_);
    extract.setNegative (false);
    extract.filter (*plane_);
}


sensor_msgs::msg::PointCloud2::SharedPtr Plane::get_plane_msg() const
{
    if (!valid_)
        throw std::runtime_error("Plane is not valid");
    sensor_msgs::msg::PointCloud2::SharedPtr output(new sensor_msgs::msg::PointCloud2());
    pcl::toROSMsg(*plane_, *output);
    return output;
}

/* #endregion */

/* #region Helper functions*/

std::vector<Plane> extract_planes(
    const sensor_msgs::msg::PointCloud2::ConstSharedPtr &pointcloud_msg,
    const float min_percentage)
{
    // Convert the pointcloud to PCL format
    pcl::PointCloud<pcl::PointXYZRGB>::Ptr cloud {convert_to_pcl(pointcloud_msg)};

    // Downsample the cloud
    auto downsampled{std::make_shared<pcl::PointCloud<pcl::PointXYZRGB>>()};
    pcl::VoxelGrid<pcl::PointXYZRGB> filter;
    filter.setInputCloud(cloud);
    filter.setLeafSize(0.01f, 0.01f, 0.01f);
    filter.filter(*downsampled);

    // Initialize storage vector
    auto nr_point{min_percentage * downsampled->size()};
    std::vector<Plane> planes{};
    //std::cout << " Original pcl size: " << cloud->size() << " Downsampled: " << downsampled->size() << std::endl;
    while (downsampled->size() > nr_point)
    {
        try {   
            //std::cout << "New number of points: " << downsampled->size() << std::endl;
            // Get the plane
            pcl::PointIndices::Ptr inliers{std::make_shared<pcl::PointIndices>()};
            Plane plane(downsampled, pointcloud_msg->header.frame_id, inliers);
            // If plane is not valid or there are not enough point, exit the search
            if (!plane.is_valid() || (inliers->indices.size() < 0.1 * downsampled->size())) {
                break;
            }
            // Remove the inliers before next execution
            pcl::ExtractIndices<pcl::PointXYZRGB> extract;
            extract.setInputCloud(downsampled);
            extract.setIndices(inliers);
            extract.setNegative(true);
            pcl::PointCloud<pcl::PointXYZRGB>::Ptr tmp{std::make_shared<pcl::PointCloud<pcl::PointXYZRGB>>()};
            extract.filter(*tmp);
            downsampled.swap(tmp);

            // Store the plane
            planes.push_back(plane);

        } catch (const std::runtime_error &e) {
            std::cerr << e.what() << std::endl;
            break;
        }
    }
    return planes;
}

cv::Mat draw_target(const sensor_msgs::msg::Image::ConstSharedPtr image, const std::vector<cv::Point> &mask)
{
    // Convert the image from ROS to OpenCv
    cv_bridge::CvImageConstPtr cv_image_ptr = cv_bridge::toCvShare(image);
    cv::Mat cv_image = cv_image_ptr->image;
    // Create a bounding box of the mask
    cv::Rect bounding_box = cv::boundingRect(mask);
    // Draw a rectangle around the mask
    cv::rectangle(cv_image, bounding_box, cv::Scalar(0, 255, 0), 2);
    return cv_image;
}


std::vector<uint8_t> pointcloud_from_mask(const sensor_msgs::msg::PointCloud2::ConstSharedPtr msg, const std::vector<cv::Point> &mask) {

    // Map to store the data
    std::vector<uint8_t> data{};

    for (const auto &point : mask) {
        // Save the data into the vector
        uint pixel_position_index{(point.y * msg->width + point.x) * msg->point_step};
        for (uint k{0}; k < msg->point_step; k++)
          data.push_back(msg->data[pixel_position_index + k]);
    }
  
    return data;
}


std::vector<float> depth_points_from_depth_map(const sensor_msgs::msg::Image::ConstSharedPtr msg, const std::vector<cv::Point> &mask)
{
    // Ensure the image is of type 16-bit unsigned single channel
    if ((msg->encoding != sensor_msgs::image_encodings::TYPE_16UC1) && 
        (msg->encoding != sensor_msgs::image_encodings::TYPE_32FC1))
    {
        throw std::runtime_error("Expected depth image type 16UC1 or 32FC1, but got " + std::string(msg->encoding));
    }
    // Vector to store depth values
    std::vector<float> depth_values;

    // Iterate over the mask to extract depth values
    if (msg->encoding == sensor_msgs::image_encodings::TYPE_16UC1) {
        // Access the depth value as unsigned short (CV_16UC1) in millimeters (ROS convention)
        ushort depth{0};
        for (const auto &point : mask) {
            // Access the depth value at the point
            memcpy(&depth, &msg->data[(point.y * msg->width + point.x) * sizeof(ushort)], sizeof(ushort));
            float depth_mm{depth * 0.001f};// Convert mm to m
            if (is_valid_depth(depth_mm))
                depth_values.push_back(depth_mm);
        }
    } else {
        // Access the depth value as float (CV_32FC1) already in meters (ROS convention)
        float depth{0};
        for (const auto &point : mask) {
            // Access the depth value at the point
            memcpy(&depth, &msg->data[(point.y * msg->width + point.x) * sizeof(float)], sizeof(float));
            if (is_valid_depth(depth))
                depth_values.push_back(depth);
        }
    }

    return depth_values;
}


bool is_valid_depth(const float depth) {
    return (std::isfinite(depth) && (depth > 0.0f));
}



cv::Mat extract_ROI(const sensor_msgs::msg::Image::ConstSharedPtr msg, const std::vector<cv::Point> &mask)
{
    // Convert the image from ROS to OpenCV
    cv_bridge::CvImageConstPtr cv_image_ptr;
    try
    {
        cv_image_ptr = cv_bridge::toCvCopy(msg);
    }
    catch (const cv_bridge::Exception &e)
    {
        throw std::runtime_error("cv_bridge exception: " + std::string(e.what()));
    }
    // Extract the image
    cv::Mat cv_image = cv_image_ptr->image;

    // Create the bounding box of the mask
    cv::Rect bounding_box = cv::boundingRect(mask);

    // Crop the image to the bounding box
    return cv_image(bounding_box);
}


pcl::PointCloud<pcl::PointXYZRGB>::Ptr convert_to_pcl(const sensor_msgs::msg::PointCloud2::ConstSharedPtr pointcloud) {
    // Convert the pointcloud msg in the PCL library format
    pcl::PointCloud<pcl::PointXYZRGB>::Ptr cloud(new pcl::PointCloud<pcl::PointXYZRGB>());
    pcl::fromROSMsg(*pointcloud, *cloud);
    return cloud;
}


sensor_msgs::msg::Image::ConstSharedPtr cv_mat_to_msg(const cv::Mat &image, const std::string encoding) {
    try
    {
      auto msg = cv_bridge::CvImage(std_msgs::msg::Header(), encoding, image).toImageMsg();
      return msg;
    }
    catch (const cv_bridge::Exception &e)
    {
        throw std::runtime_error("cv_bridge exception: " + std::string(e.what()));
    }
}


void publish_image(const cv::Mat& image, const std::string encoding, rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr publisher) {
    // Create the message
    try
    {
      auto msg = cv_bridge::CvImage(std_msgs::msg::Header(), encoding, image).toImageMsg();
      publisher->publish(*msg.get());
    }
    catch (const cv_bridge::Exception &e)
    {
        throw std::runtime_error("cv_bridge exception: " + std::string(e.what()));
    }
  }

std::vector<cv::Point> mask_from_msg(const mask_interfaces::msg::Mask::ConstSharedPtr msg)
{
    // Convert the mask from ROS to OpenCV
    std::vector<cv::Point> mask;
    for (const auto &pixel : msg->pixels)
    {
        mask.push_back(cv::Point(pixel.x, pixel.y));
    }
    return mask;
}


float orientation(const coordinates &a, const coordinates &b, const coordinates &c) {
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}


std::vector<coordinates> convex_hull(const std::vector<coordinates> &points) {
    if (points.size() < 3) return points;
    std::vector<coordinates> hull;
    // Find leftmost point
    size_t leftmost = 0;
    for (size_t i = 1; i < points.size(); ++i) {
        if (points[i].x < points[leftmost].x ||
            (points[i].x == points[leftmost].x && points[i].y < points[leftmost].y)) {
            leftmost = i;
        }
    }
    size_t p = leftmost;
    do {
        hull.push_back(points[p]);
        size_t q = (p + 1) % points.size();
        for (size_t r = 0; r < points.size(); ++r) {
            if (orientation(points[p], points[q], points[r]) < 0) {
                q = r;
            }
        }
        p = q;
    } while (p != leftmost);
    return hull;
}


double calculate_area(std::vector<coordinates> &points) {
    // First, find the convex hull of the points
    std::vector<coordinates> hull = convex_hull(points);
    double area = 0.0;
    size_t n = hull.size();
    for (size_t i = 0; i < n; ++i) {
        size_t j = (i + 1) % n;
        area += hull[i].x * hull[j].y;
        area -= hull[i].y * hull[j].x;
    }
    return std::abs(area / 2.0);
}
  
/* #endregion */