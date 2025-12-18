/**
 * @brief Utility functions for point cloud processing from depth map and RGB image.
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

#ifndef DEPTH_ESTIMATION_UTILS_HPP
#define DEPTH_ESTIMATION_UTILS_HPP

// SYSTEM
#include <Eigen/Dense>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <vector>
#include <limits>

// ROS
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/image.hpp"
#include "tf2_ros/transform_broadcaster.h"
#include "geometry_msgs/msg/transform.hpp"
#include "mask_interfaces/msg/mask.hpp"
#include "mask_interfaces/msg/pixel.hpp"

// OpenCV
#include "cv_bridge/cv_bridge.h"
#include <opencv2/imgproc/imgproc.hpp>

// PCL library
#include <pcl/point_types.h>
#include <pcl_conversions/pcl_conversions.h>
#include <pcl/ModelCoefficients.h>
#include <pcl/sample_consensus/method_types.h>
#include <pcl/sample_consensus/model_types.h>
#include <pcl/segmentation/sac_segmentation.h>
#include <pcl/filters/voxel_grid.h>
#include <pcl/filters/extract_indices.h>
#include <pcl/common/centroid.h>


/**
 * @brief struct to store planar coordinates of a point
 * @param x The x position
 * @param y The y position
 */
struct coordinates {
    
    float x, y;

    /**
     * @brief Constructor of the struct
     * @param x The x coordinate
     * @param y The y coordinate
     */
    coordinates(float x, float y) : x{x}, y{y} {}
};


/**
 * @brief Class to store the biggest plane detected in a RGB pointcloud
 * @param cloud: The pointcloud to be searched
 * @param frame_id The reference of the points position
 * @param indices A shared pointer to a pcl::PointIndices to store the indices of the inliers
 * @note If indices is not provided, the memory will be allocated internally but will be released after 
 * the creation of the plane and the indices won't be available anymore.
 * @note The class uses the RANSAC algorithm to detect the plane and downsampling
 */
class Plane
{
public:

    Plane(const pcl::PointCloud<pcl::PointXYZRGB>::Ptr cloud,
            const std::string &frame_id, 
            const pcl::PointIndices::Ptr indices = nullptr);
    
    /**
     * @brief Return if the object contains a valid plane
     * @return true if the object contains a valid plane
     */
    bool is_valid() const { return valid_; }

    /**
     * @brief Return the centroid of the plane
     * @return The centroid of the plane
     */
    const pcl::PointXYZ get_centroid() const
    {
        if (!valid_)
            throw std::runtime_error("Plane is not valid");
        return centroid_point_;
    }

    /**
     * @brief Return the coefficients of the plane
     * @return The coefficients of the plane
     */
    pcl::ModelCoefficients::Ptr get_coefficients() const
    {
        if (!valid_)
            throw std::runtime_error("Plane is not valid");
        return coefficients_;
    }

    /**
     * @brief Return the pointcloud of the plane
     * @return The pointcloud of the plane
     */
    pcl::PointCloud<pcl::PointXYZRGB>::Ptr get_plane() const
    {
        if (!valid_)
            throw std::runtime_error("Plane is not valid");
        return plane_;
    }

    /**
     * @brief Return the TF of the plane
     * @param raw If true, the TF returned is based on the plane coefficients. Otherwise the z axis
     * is aligned basing on the z_up parameter
     * @param z_up If true, the normal of the TF is published  in the half space with the origin
     * @note For origin is intended the frame ID which the pointcloud is published from
     * @return The TF of the plane centroid
     */
    geometry_msgs::msg::Transform get_tf(bool raw, bool z_up) const;

    /**
     * @brief Return the frame id of the plane
     * @return The frame id of the plane
     */
    std::string get_frame_id() const
    {
        if (!valid_)
            throw std::runtime_error("Plane is not valid");
        return frame_id_;
    }

    /**
     * @brief Return the plane as ROS 2 message
     * @return The plane as ROS 2 message
     */
    sensor_msgs::msg::PointCloud2::SharedPtr get_plane_msg() const;



private:
    // The pointcloud of the plane
    pcl::PointCloud<pcl::PointXYZRGB>::Ptr plane_ {new pcl::PointCloud<pcl::PointXYZRGB>()};
    // Coefficients of the plane (ax + by + cz + d = 0)
    pcl::ModelCoefficients::Ptr coefficients_ {new pcl::ModelCoefficients()};
    // Indices of the points in the original pointcloud
    pcl::PointIndices::Ptr indices_{nullptr};
    // The centroid of the plane
    pcl::PointXYZ centroid_point_;
    // The pointcloud of the original image
    bool valid_{true};
    // Frame id of the origin
    std::string frame_id_;

    /**
     * @brief Extract the biggest plane from a pointcloud
     * @param cloud The pointcloud
     * @return The biggest plane
     * @note The function uses the RANSAC algorithm to detect the plane
     */
    void extract_plane(const pcl::PointCloud<pcl::PointXYZRGB>::Ptr cloud);

    /**
     * @brief Clear the pointcloud and coefficients
     * @note The function sets the valid_ flag to false
     */
    void clear();

};


/**
 * @brief Extract all the available planes inside a pointcloud before reaching the minimum percentage of points
 * @param pointcloud_msg The pointcloud message to analyze
 * @param min_percentage Accept values (0,1]. The minimum percentage of points from the original pointcloud that have to be left
 * to look for another plane. Default 0.3.
 * @return A vector of planes. If no plane have been found, returns an empty vector.
 */
std::vector<Plane> extract_planes(
    const sensor_msgs::msg::PointCloud2::ConstSharedPtr &pointcloud_msg,
    const float min_percentage = 0.3);


/**
 * @brief Apply a rectangle to the image using OpenCv
 * @param image The shared pointer to the image to be changed
 * @param mask The mask to be drawn
 * @return An OpenCv Image
*/
cv::Mat draw_target(const sensor_msgs::msg::Image::ConstSharedPtr image, const std::vector<cv::Point> &mask);


/**
 * @brief Function to obtain the values inside the data vector of a pointcloud_msg using a mask
 * @param msg The pointcloud message to be parsed
 * @param mask The mask to be used to extract the values
 * @return a vector containng all the values extracted from the image
 * 
 * @note The msg passed must be associated with the image which the mask is applied and the pointcloud must be ordered.
 */
std::vector<uint8_t> pointcloud_from_mask(const sensor_msgs::msg::PointCloud2::ConstSharedPtr msg, const std::vector<cv::Point> &mask);


/**
 * @brief Obtain the depth values from a depth map
 * @param msg The depth map to be parsed
 * @param mask The mask to be used to extract the depth values
 * @return a vector containng all the depth values extracted from the image
 * 
 * @note The function only accepts depth maps in the format of 32FC1 or 16UC1.
 * @note The msg passed to the function must be a depth map associated to the mask.
*/
std::vector<float> depth_points_from_depth_map(const sensor_msgs::msg::Image::ConstSharedPtr msg, const std::vector<cv::Point> &mask);


/**
 * @brief Check if the depth value is valid
 * @param depth The depth value to be checked
 * @return true if the depth value is valid
 * @note The function checks if the depth value is not NaN or infinite
 */
bool is_valid_depth(const float depth);


/**
 * @brief Extract the Region of Interest from an Image topic
 * @param msg The received message
 * @param mask The mask to be used to extract the ROI
 * @return A bounding box of the mask
*/
cv::Mat extract_ROI(const sensor_msgs::msg::Image::ConstSharedPtr msg, const std::vector<cv::Point> &mask);


/**
 * @brief Convert a ROS 2 pointcloud message to a PCL pointcloud
 * @param pointcloud The pointcloud message
 * @return The PCL pointcloud
 */
pcl::PointCloud<pcl::PointXYZRGB>::Ptr convert_to_pcl(const sensor_msgs::msg::PointCloud2::ConstSharedPtr pointcloud);


/**
 * @brief Convert a Cv::Mat to a ROS 2 image message
 * @param image The image to be converted
 * @param encoding The encoding of the image
 */
sensor_msgs::msg::Image::ConstSharedPtr cv_mat_to_msg(const cv::Mat &image, const std::string encoding);


/**
 * @brief Publish an image (cv::MAt) to the selected publisher
 * @param image The image to be published
 * @param encoding The desired encoding for the image
 * @param publisher The publisher to use
*/
void publish_image(const cv::Mat &image, const std::string encoding, rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr publisher);

/**
 * @brief Convert a mask message to a vector of points
 * @param msg The mask message
 * @return A vector of points representing the mask
 * @note The mask is a vector of points in the image coordinates
 */
std::vector<cv::Point> mask_from_msg(const mask_interfaces::msg::Mask::ConstSharedPtr msg);


/**
 * @brief Calculates the area of a set of points using the AFAIK (also known as 'Shoelace') algorithm
 * @param points The vector containing all the points in the area
 * @return The area
 */
double calculate_area(std::vector<coordinates> &points);


/**
 * @brief Helper function to determine orientation
 * @param a Coordinates of the point a
 * @param b Coordinates of the point b
 * @param c Coordinates of the point c
 * @return >0 if c is to the left of ab, <0 if to the right, 0 if colinear
 */
float orientation(const coordinates &a, const coordinates &b, const coordinates &c);


/**
 * @brief Determine the convex hull using the Gift Wrapping algorithm
 * @param points The points to be considered in the convex hull
 * @return A vector containing the coordinates of the convex hull
 */
std::vector<coordinates> convex_hull(const std::vector<coordinates> &points);

#endif // UTILS_HPP