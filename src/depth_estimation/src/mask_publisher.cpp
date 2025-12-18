/**
 * @file mask_publisher.cpp
 * @brief This file contains the implementation of the MaskPublisher class.
 * @details The MaskPublisher class publish a topic containing all the pixels contained in the mask.
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

#include "mask_publisher.hpp"

MaskPublisher::MaskPublisher(const rclcpp::NodeOptions & options)
: Node("mask_publisher", options)
{
    // Declare the parameters
    auto param_desc = rcl_interfaces::msg::ParameterDescriptor{};
    param_desc.description = "Type of mask to be used. 0: NONE, 1: RECTANGLE, 2: CIRCLE, 3:STAR, 4:COLOR";
    this->declare_parameter("mask_type", 1, param_desc);
    param_desc.description = "Topic to listen to for the image. Default: /camera/color/image_raw";
    this->declare_parameter("image_topic", "/camera/color/image_raw", param_desc);
    param_desc.description = "Radius of the mask. Default: 100";
    this->declare_parameter("mask_size", 100, param_desc);
    param_desc.description = "X position [in pixels] of the mask";
    this->declare_parameter("x", 0, param_desc);
    param_desc.description = "Y position [in pixels] of the mask";
    this->declare_parameter("y", 0, param_desc);

    // Check if the parameter is correct
    int mask = this->get_parameter("mask_type").as_int();
    if (mask < 0 || mask > 6)
    {
        RCLCPP_WARN(this->get_logger(), "Invalid mask type. Defaulting to RECTANGLE.");
        mask_type_ = MaskType::RECTANGLE;
    } else
    {
        mask_type_ = static_cast<MaskType>(mask);
        RCLCPP_INFO(this->get_logger(), "Mask type set to %d", mask);
    }
    mask_size_ = this->get_parameter("mask_size").as_int();
    if (mask_size_ <= 0)
    {
        RCLCPP_WARN(this->get_logger(), "Invalid mask size. Defaulting to 100.");
        mask_size_ = 100;
    } else
    {
        RCLCPP_INFO(this->get_logger(), "Mask size set to %d", mask_size_);
    }

    // Create the image subscriber
    sub_image_ = this->create_subscription<sensor_msgs::msg::Image>(
        this->get_parameter("image_topic").as_string(), 10, 
        std::bind(&MaskPublisher::imageCallback, this, std::placeholders::_1));

    // Create the mask publisher
    pub_mask_ = this->create_publisher<mask_interfaces::msg::Mask>("/mask", 10);
    // Create the image publisher
    pub_image_ = this->create_publisher<sensor_msgs::msg::Image>("/mask_image_test", 10);
}

void MaskPublisher::imageCallback(const sensor_msgs::msg::Image::SharedPtr msg)
{
    // Create a mask message
    auto mask_msg = mask_interfaces::msg::Mask();
    mask_msg.header = msg->header;

    // Generate the mask
    std::vector<cv::Point> points{};
    if (mask_type_ == MaskType::COLOR)
        points = mask_from_color(msg, hsv_color(0, 83, 141), hsv_color(5, 244, 205));
    else if (mask_type_ == MaskType::ARUCO)
        points = mask_aruco(msg);
    else if (mask_type_ == MaskType::CHESSBOARD)
        points = mask_chessboard(msg);
    else
        points = generate_fake_mask(msg->width, msg->height);
    

    // Populate the mask message with the points
    for (const auto & point : points)
    {
        auto pixel = mask_interfaces::msg::Pixel();
        pixel.x = point.x;
        pixel.y = point.y;
        mask_msg.pixels.push_back(pixel);
    }
    mask_msg.size = points.size();

    // Publish the mask message
    pub_mask_->publish(mask_msg);
}

std::vector<cv::Point> MaskPublisher::generate_fake_mask(const uint32_t width, const uint32_t height) const
{
    // Create a image
    cv::Mat image(height, width, CV_8UC3, cv::Scalar(0, 0, 0));

    cv::Point center(width/2 + this->get_parameter("x").as_int(),
                     height/2 - this->get_parameter("y").as_int()); // Y axis is inverted
    cv::Scalar color(255, 255, 255); // white

    switch (mask_type_)
    {
        case MaskType::CIRCLE:
            cv::circle(image, center, mask_size_, color, -1);
            break;
        case MaskType::RECTANGLE:
            cv::rectangle(image, cv::Rect(center.x - mask_size_, center.y - mask_size_, mask_size_, mask_size_), color, -1);
            break;
        case MaskType::STAR:
            cv::drawMarker(image, center, color, cv::MARKER_STAR, height - height/4, mask_size_);
            break;
        case MaskType::NONE:
            // Mask same as the image
            cv::rectangle(image, cv::Rect(0, 0, width, height), color, -1);
            break;
        default:
            RCLCPP_ERROR(this->get_logger(), "Invalid mask type.");
            return {};
    }

    // Convert the image to grayscale
    cv::Mat gray_image;
    cv::cvtColor(image, gray_image, cv::COLOR_BGR2GRAY);

    // Get the list of points in the binary mask
    std::vector<cv::Point> pixels;
    cv::findNonZero(gray_image, pixels);

    publish_mask_image(gray_image);

    return pixels;
}

std::vector<cv::Point> MaskPublisher::mask_from_color(const sensor_msgs::msg::Image::SharedPtr image_msg, const hsv_color &low_color,
                                         const hsv_color &high_color) const {
    // Convert the image from ROS to OpenCv
    cv_bridge::CvImageConstPtr cv_image_ptr = cv_bridge::toCvShare(image_msg);
    cv::Mat cv_image = cv_image_ptr->image;
    // Convert to hsv
    cv::Mat hsv_img;

    if (image_msg->encoding == sensor_msgs::image_encodings::RGB8 ||
        image_msg->encoding == sensor_msgs::image_encodings::RGBA8) {
      cv::cvtColor(cv_image, hsv_img, cv::COLOR_RGB2HSV);
    } else if (image_msg->encoding == sensor_msgs::image_encodings::BGR8 ||
               image_msg->encoding == sensor_msgs::image_encodings::BGRA8) {
      cv::cvtColor(cv_image, hsv_img, cv::COLOR_BGR2HSV);
    } else {
        return std::vector<cv::Point>();
    }

    cv::Scalar low(low_color.h, low_color.s, low_color.v);
    cv::Scalar high(high_color.h, high_color.s, high_color.v);
    // B&W mask
    cv::Mat mask;
    cv::inRange(hsv_img, low, high, mask);

    // Get the list of points in the binary mask
    std::vector<cv::Point> pixels;
    cv::findNonZero(mask, pixels);

    publish_mask_image(mask);

    return pixels;
}

std::vector<cv::Point> MaskPublisher::mask_aruco(const sensor_msgs::msg::Image::SharedPtr msg) const {
    // Convert the image from ROS to OpenCv
    cv_bridge::CvImageConstPtr cv_image_ptr = cv_bridge::toCvCopy(msg);
    cv::Mat cv_image = cv_image_ptr->image;

    // Check image format and convert to bgr
    if (msg->encoding == sensor_msgs::image_encodings::RGB8)
        cv::cvtColor(cv_image, cv_image, cv::COLOR_RGB2BGR);
    else if (msg->encoding == sensor_msgs::image_encodings::RGBA8)
        cv::cvtColor(cv_image, cv_image, cv::COLOR_RGBA2BGR);
    else if (msg->encoding == sensor_msgs::image_encodings::BGRA8)
        cv::cvtColor(cv_image, cv_image, cv::COLOR_BGRA2BGR);
    else if (msg->encoding != sensor_msgs::image_encodings::BGR8)
        return std::vector<cv::Point>();

    // Detect markers
    std::vector<int> markerIds;
    std::vector<std::vector<cv::Point2f>> markerCorners, rejectedCandidates;
    cv::aruco::Dictionary dictionary = 
            cv::aruco::getPredefinedDictionary(cv::aruco::DICT_4X4_250);
    cv::aruco::DetectorParameters detectorParams = cv::aruco::DetectorParameters();
    cv::aruco::ArucoDetector detector(dictionary, detectorParams);
    detector.detectMarkers(cv_image, markerCorners, markerIds, rejectedCandidates);

    std::vector<cv::Point> mask;
    cv::Mat mask_image = cv::Mat::zeros(cv_image.size(), CV_8UC1);

    if (!markerIds.empty()) {
        // Convert vector of cv::Point2f to vector of cv::Point
        std::vector<std::vector<cv::Point>> mask_corners{
            std::vector<cv::Point>(markerCorners[0].begin(), markerCorners[0].end())
        };
        cv::fillPoly(mask_image, mask_corners, cv::Scalar(255, 255, 255));

        // Get the list of points in the binary mask
        cv::findNonZero(mask_image, mask);
    }
    
    publish_mask_image(mask_image);

    return mask;
}

std::vector<cv::Point> MaskPublisher::mask_chessboard(const sensor_msgs::msg::Image::SharedPtr msg) const {
    // Convert the image from ROS to OpenCv
    cv_bridge::CvImageConstPtr cv_image_ptr = cv_bridge::toCvCopy(msg);
    cv::Mat cv_image = cv_image_ptr->image;

    // Convert the image in B&W
    if (msg->encoding == sensor_msgs::image_encodings::RGB8 ||
        msg->encoding == sensor_msgs::image_encodings::RGBA8) {
      cv::cvtColor(cv_image, cv_image, cv::COLOR_RGB2GRAY);
    } else if (msg->encoding == sensor_msgs::image_encodings::BGR8 ||
               msg->encoding == sensor_msgs::image_encodings::BGRA8) {
        cv::cvtColor(cv_image, cv_image, cv::COLOR_BGR2GRAY);
    } else{
        return std::vector<cv::Point>();
    }

    // Define the checkerboard dimensions (number of inner corners per row and column)
    cv::Size patternSize(10, 7); // 10x7 inner corners (not squares!)
    std::vector<cv::Point2f> corners;

    // Try to find the checkerboard corners
    bool found = cv::findChessboardCorners(cv_image, patternSize, corners,
                                           cv::CALIB_CB_ADAPTIVE_THRESH + cv::CALIB_CB_NORMALIZE_IMAGE);

    std::vector<cv::Point> mask;
    cv::Mat mask_image = cv::Mat::zeros(cv_image.size(), CV_8UC1);

    // Draw corners if found
    if (found) {
        std::vector<cv::Point> mask_corners;
        mask_corners.push_back(corners[0]);
        mask_corners.push_back(corners[patternSize.width - 1]);
        mask_corners.push_back(corners.back());
        mask_corners.push_back(corners[corners.size() - patternSize.width]);

        // Draw filled white polygon on the mask image
        cv::fillPoly(mask_image, mask_corners, cv::Scalar(255, 255, 255));

        // Get the list of points in the binary mask
        std::vector<cv::Point> pixels;
        cv::findNonZero(mask_image, mask);
    }

    publish_mask_image(mask_image);

    return mask;
}


void MaskPublisher::publish_mask_image(const cv::Mat &mask_image) const {
     // Publish the image for testing
    sensor_msgs::msg::Image pub_msg;
    pub_msg.header.stamp = this->now();
    pub_msg.height = mask_image.rows;
    pub_msg.width = mask_image.cols;
    pub_msg.encoding = "mono8";
    pub_msg.is_bigendian = false;
    pub_msg.step = pub_msg.width;
    pub_msg.data.resize(pub_msg.height * pub_msg.width);
    std::memcpy(pub_msg.data.data(), mask_image.data, pub_msg.data.size());
    pub_image_->publish(pub_msg);
}