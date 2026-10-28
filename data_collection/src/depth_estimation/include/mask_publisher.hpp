/**
 * @brief This file contains the definition of the MaskPublisher class.
 * @details The MaskPublisher class publish a topic containing all the pixels contained in a mask.
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

#ifndef MASK_PUBLISHER_HPP
#define MASK_PUBLISHER_HPP

 // cpp dependencies
 #include <vector>
 #include <stdexcept>

 // ros dependencies
#include <rclcpp/rclcpp.hpp>
#include "mask_interfaces/msg/mask.hpp"
#include "mask_interfaces/msg/pixel.hpp"
#include "sensor_msgs/msg/image.hpp"

// OpenCV
#include "cv_bridge/cv_bridge.h"
#include <opencv2/imgproc/imgproc.hpp>
#include <opencv2/opencv.hpp>
#include <opencv2/objdetect/aruco_detector.hpp>

/** 
 * @brief Enum class to define the type of mask to be used.
 * @details The enum class contains three types of masks: CIRCLE, RECTANGLE, STAR, COLOR, ARUCO and CHESSBOARD.
 */
enum class MaskType
{
    NONE = 0,
    RECTANGLE = 1,
    CIRCLE = 2,
    STAR = 3,
    COLOR = 4,
    ARUCO = 5,
    CHESSBOARD = 6
};


/**
 * @brief Stores the values of a hsv color
 */
struct hsv_color {
    uint8_t h, s, v;
    hsv_color(const uint8_t h_, const uint8_t s_, const uint8_t v_) : h(h_), s(s_), v(v_) {
        if (h > 180) {
            // OpenCV goes only up to 180
            throw std::invalid_argument("Hue can't be over 180");
        }
    }
};

/**
 * @class MaskPublisher
 * @brief A ROS2 node for generating and publishing masks based on incoming images.
 *
 * The MaskPublisher class subscribes to image topics, generates masks using various methods
 * (such as geometric shapes, color ranges, ArUco markers, or chessboard patterns), and publishes
 * both the mask and the masked image. The mask generates as a list of pixel coordinates.
 * The generated mask image is published for visualization on "/mask_image_test".
 *
 * @section Subscriptions
 * - sensor_msgs::msg::Image: Receives input images to process.
 *
 * @section Publications
 * - mask_interfaces::msg::Mask: Publishes the generated mask as a list of pixel coordinates.
 * - sensor_msgs::msg::Image: Publishes the mask as an image.
 *
 * @section Mask Types
 * The mask can be of various types, such as NONE, RECTANGLE, CIRCLE, or STAR, as specified by MaskType.
 *
 * @section Methods
 * - imageCallback: Handles incoming images, generates the mask, and publishes results.
 * - generate_fake_mask: Generates a geometric mask (rectangle, circle, star) for a given image size.
 * - mask_from_color: Generates a mask by thresholding the image within a specified HSV color range.
 * - MaskAruco: Generates a mask based on detected ArUco markers in the image.
 * - MaskChessboard: Generates a mask based on detected chessboard patterns in the image.
 *
 * @note For color-based masking, refer to the OpenCV tutorial: https://docs.opencv.org/3.4/da/d97/tutorial_threshold_inRange.html
 */

class MaskPublisher : public rclcpp::Node
{
    public:

    MaskPublisher(const rclcpp::NodeOptions & options);

    private:
    // Subscribers
    rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr sub_image_;

    // Publishers
    rclcpp::Publisher<mask_interfaces::msg::Mask>::SharedPtr pub_mask_;
    rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr pub_image_;

    // Variables
    MaskType mask_type_; ///< Type of mask to be used (NONE, RECTANGLE, CIRCLE, STAR)
    int mask_size_;      ///< Size (radius or half-side) of the mask

    /**
     * @brief Callback for incoming images.
     * @param msg The received image message.
     *
     * Generates a mask for the input image and publishes the mask as a list of pixels.
     */
    void imageCallback(const sensor_msgs::msg::Image::SharedPtr msg);

    /**
     * @brief Generate a mask as a vector of pixel coordinates.
     * @param width Width of the input image.
     * @param height Height of the input image.
     * @return std::vector<cv::Point> List of points inside the mask.
     *
     * Draws the mask using OpenCV, extracts nonzero pixels, and publishes the mask image.
     */
    std::vector<cv::Point> generate_fake_mask(const uint32_t width, const uint32_t height) const;

    /**
     * @brief Generates a mask looking between a fixed range of HSV colors
     * @param low_color The lowest color in the range of Opencv
     * @param high_color The higher color in the range od Opencv
     * @return std::vector<cv::Point> List of points inside the mask.
     * 
     * @note To easily get the range, follow the tutorial at https://docs.opencv.org/3.4/da/d97/tutorial_threshold_inRange.html
     */
    std::vector<cv::Point> mask_from_color(const sensor_msgs::msg::Image::SharedPtr image_msg, const hsv_color &low_color, const hsv_color &high_color) const;

    /**
     * @brief Generates a mask detecting an Aruco 4x4, 100 marker in the image using Opencv
     * @param msg The image message
     * @return std::vector<cv::Point> List of points inside the mask.
     * 
     * @note The mask corresponds to the pixels of the square of the marker
     */
    std::vector<cv::Point> mask_aruco(const sensor_msgs::msg::Image::SharedPtr msg) const;

    /**
     * @brief Generates a mask detecting a chessboard corners using OpenCV
     * @param msg The image message
     * @return std::vector<cv::Point> List of points inside the mask.
     * 
     * @note The mask corresponds to the pixels of the innner portion (not the edge squares) of the chessboard
     */
    std::vector<cv::Point> mask_chessboard(const sensor_msgs::msg::Image::SharedPtr msg) const;

    /**
     * @brief Publish the mask image on the topic /mask_image_test
     */
    void publish_mask_image(const cv::Mat &mask_image) const;
};

#include "rclcpp_components/register_node_macro.hpp"

// Register the component with class_loader.
RCLCPP_COMPONENTS_REGISTER_NODE(MaskPublisher)

#endif // MASK_PUBLISHER_HPP