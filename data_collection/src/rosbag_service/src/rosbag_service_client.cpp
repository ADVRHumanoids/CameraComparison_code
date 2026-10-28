/**
 * @file rosbag_service_client.cpp
 * @brief ROS 2 node that calls the `start_rosbag` service to start a rosbag2 recording.
 *
 * This executable is meant to be used from the command line:
 * `ros2 run rosbag_service rosbag_service_client <bag_name>`
 *
 * @author Lovato Alessio
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

#include <chrono>
#include <memory>

#include "rclcpp/rclcpp.hpp"
#include "rosbag_service/srv/start_rosbag.hpp"

using namespace std::chrono_literals;
using StartRosbag = rosbag_service::srv::StartRosbag;

/**
 * @brief Client node for requesting a rosbag recording start.
 */
class RosbagServiceClient : public rclcpp::Node
{
public:
  /**
   * @brief Construct the node and create the `start_rosbag` service client.
   */
  RosbagServiceClient() : Node("rosbag_service_client")
  {
    client_ = this->create_client<StartRosbag>("start_rosbag");
  }

  /**
   * @brief Call the `start_rosbag` service.
   *
   * The call blocks until the service is available and until a response is received.
   *
   * @param bag_name Desired recording name (used by the server to build the output path).
   * @return True if the service reported success, false otherwise.
   */
  bool call_service(const std::string& bag_name)
  {
    // Wait for the service to be available.
    while (!client_->wait_for_service(1s)) {
      if (!rclcpp::ok()) {
        RCLCPP_ERROR(this->get_logger(), "Interrupted while waiting for the service.");
        return false;
      }
      RCLCPP_INFO(this->get_logger(), "Service 'start_rosbag' not available, waiting...");
    }

    // Create request.
    auto request = std::make_shared<StartRosbag::Request>();
    request->bag_name = bag_name;

    RCLCPP_INFO(this->get_logger(), "Calling service with bag_name: %s", bag_name.c_str());

  // Send request asynchronously.
    auto result_future = client_->async_send_request(request);

  // Wait for result.
    if (rclcpp::spin_until_future_complete(this->get_node_base_interface(), result_future) ==
        rclcpp::FutureReturnCode::SUCCESS)
    {
      auto result = result_future.get();
      
      if (result->success) {
        RCLCPP_INFO(this->get_logger(), "Service call successful: %s", result->message.c_str());
      } else {
        RCLCPP_WARN(this->get_logger(), "Service call failed: %s", result->message.c_str());
      }
      
      return result->success;
    } else {
      RCLCPP_ERROR(this->get_logger(), "Failed to call service 'start_rosbag'");
      return false;
    }
  }

private:
  /// Client for the `start_rosbag` service.
  rclcpp::Client<StartRosbag>::SharedPtr client_;
};

int main(int argc, char **argv)
{
  rclcpp::init(argc, argv);

  if (argc != 2) {
    std::cout << "Usage: ros2 run rosbag_service rosbag_service_client <bag_name>" << std::endl;
    std::cout << "Example: ros2 run rosbag_service rosbag_service_client my_recording" << std::endl;
    return 1;
  }

  auto client_node = std::make_shared<RosbagServiceClient>();
  
  std::string bag_name = argv[1];
  
  RCLCPP_INFO(client_node->get_logger(), "Starting rosbag service client...");
  
  bool success = client_node->call_service(bag_name);
  
  if (success) {
    RCLCPP_INFO(client_node->get_logger(), "Rosbag recording request completed successfully");
  } else {
    RCLCPP_ERROR(client_node->get_logger(), "Rosbag recording request failed");
  }

  rclcpp::shutdown();
  return success ? 0 : 1;
}
