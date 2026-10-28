/**
 * @file rosbag_service_server.cpp
 * @brief ROS 2 node providing services to start/stop rosbag2 recordings.
 *
 * Services:
 * - `start_rosbag` (rosbag_service/srv/StartRosbag): starts `ros2 bag record` as a child process.
 * - `stop_rosbag`  (rosbag_service/srv/StopRosbag): stops the child process via SIGINT (then SIGKILL if needed).
 *
 * Parameters:
 * - `output_dir` (string, default: "."): directory where the bag folder will be created.
 * - `topics` (string[], default: ["/rgb_image", "/depth_image", "/camera_info", "/tf", "/tf_static"]): list of topics to record.
 *
 * @note The implementation uses `fork()` + `execl()` to obtain and track the child PID.
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

#include <cstdlib>
#include <memory>
#include <string>
#include <filesystem>
#include <map>
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>

#include "rclcpp/rclcpp.hpp"
#include "rosbag_service/srv/start_rosbag.hpp"
#include "rosbag_service/srv/stop_rosbag.hpp"

using StartRosbag = rosbag_service::srv::StartRosbag;
using StopRosbag = rosbag_service::srv::StopRosbag;

/**
 * @brief Service server node that manages rosbag record processes.
 *
 * The node keeps a map from `bag_name` to the child process PID.
 */
class RosbagServiceServer : public rclcpp::Node
{
public:
  /**
   * @brief Construct the node, declare parameters, and create start/stop services.
   */
  RosbagServiceServer() : Node("rosbag_service_server")
  {
    // Declare parameters
    this->declare_parameter<std::string>("output_dir", ".");
    this->declare_parameter<std::vector<std::string>>("topics", 
        std::vector<std::string>{"/rgb_image", "/depth_image", "/camera_info", "/tf", "/tf_static"});
    
    // Create services
    start_service_ = this->create_service<StartRosbag>(
      "start_rosbag",
      std::bind(&RosbagServiceServer::handle_start_request, this,
                std::placeholders::_1, std::placeholders::_2));
    
    stop_service_ = this->create_service<StopRosbag>(
      "stop_rosbag",
      std::bind(&RosbagServiceServer::handle_stop_request, this,
                std::placeholders::_1, std::placeholders::_2));
    
    RCLCPP_INFO(this->get_logger(), "Rosbag service server ready:");
    RCLCPP_INFO(this->get_logger(), "  - start_rosbag service available");
    RCLCPP_INFO(this->get_logger(), "  - stop_rosbag service available");
  }

private:
  /**
   * @brief Handle a request to start a rosbag recording.
   *
   * Creates the output directory if needed, spawns a `ros2 bag record` process, and stores its PID.
   *
   * Error cases handled:
   * - empty bag name
   * - duplicate bag name already active
   * - fork failure
   */
  void handle_start_request(
    const std::shared_ptr<StartRosbag::Request> request,
    std::shared_ptr<StartRosbag::Response> response)
  {
    try {
      std::string bag_name = request->bag_name;
      std::string output_dir = this->get_parameter("output_dir").as_string();
      std::vector<std::string> topics = this->get_parameter("topics").as_string_array();

      // Validate bag name
      if (bag_name.empty()) {
        response->success = false;
        response->message = "Bag name cannot be empty";
        RCLCPP_WARN(this->get_logger(), "Empty bag name provided");
        return;
      }

      // Check if recording already exists
      if (active_recordings_.find(bag_name) != active_recordings_.end()) {
        response->success = false;
        response->message = "Recording with name '" + bag_name + "' is already active";
        RCLCPP_WARN(this->get_logger(), "Recording already active: %s", bag_name.c_str());
        return;
      }

      // Create output directory if it doesn't exist
      std::filesystem::path output_path(output_dir);
      if (!std::filesystem::exists(output_path)) {
        std::filesystem::create_directories(output_path);
      }

      std::string full_path = output_dir + "/" + bag_name;

      // Build command with topics
      std::string command = "ros2 bag record -s mcap -o " + full_path;
      for (const auto& topic : topics) {
        command += " " + topic;
      }

      RCLCPP_INFO(this->get_logger(), "Starting recording: %s", command.c_str());

      // Start process using fork and exec to get a proper PID for later shutdown.
      pid_t pid = fork();
      if (pid == 0) {
        // Child process: execute the rosbag2 command via bash.
        execl("/bin/bash", "bash", "-c", command.c_str(), (char*)NULL);
        exit(1); // If exec fails
      } else if (pid > 0) {
        // Parent process - store PID
        active_recordings_[bag_name] = pid;
        response->success = true;
        response->message = "Rosbag recording started at: " + full_path + " (PID: " + std::to_string(pid) + ")";
        RCLCPP_INFO(this->get_logger(), "Successfully started recording: %s", response->message.c_str());
      } else {
        // Fork failed
        response->success = false;
        response->message = "Failed to start rosbag recording (fork failed)";
        RCLCPP_ERROR(this->get_logger(), "%s", response->message.c_str());
      }
    } catch (const std::exception& e) {
      response->success = false;
      response->message = "Exception occurred: " + std::string(e.what());
      RCLCPP_ERROR(this->get_logger(), "Exception in start service handler: %s", e.what());
    }
  }

  /**
   * @brief Handle a request to stop a rosbag recording.
   *
   * Sends SIGINT (graceful stop). If the process doesn't exit shortly, sends SIGKILL.
   */
  void handle_stop_request(
    const std::shared_ptr<StopRosbag::Request> request,
    std::shared_ptr<StopRosbag::Response> response)
  {
    try {
      std::string bag_name = request->bag_name;

      // Find the recording
      auto it = active_recordings_.find(bag_name);
      if (it == active_recordings_.end()) {
        response->success = false;
        response->message = "No active recording found with name: " + bag_name;
        RCLCPP_WARN(this->get_logger(), "No active recording found: %s", bag_name.c_str());
        return;
      }

      pid_t pid = it->second;
      
      // Send SIGINT to the process (equivalent to Ctrl+C).
      if (kill(pid, SIGINT) == 0) {
        // Wait for process to terminate.
        int status;
        int wait_result = waitpid(pid, &status, WNOHANG);
        
        if (wait_result == 0) {
          // Process is still running, give it some time
          sleep(1);
          wait_result = waitpid(pid, &status, WNOHANG);
        }

        if (wait_result > 0) {
          // Process terminated
          active_recordings_.erase(it);
          response->success = true;
          response->message = "Rosbag recording '" + bag_name + "' stopped successfully";
          RCLCPP_INFO(this->get_logger(), "Successfully stopped recording: %s", bag_name.c_str());
        } else if (wait_result == 0) {
          // Process still running, force kill.
          kill(pid, SIGKILL);
          waitpid(pid, &status, 0);
          active_recordings_.erase(it);
          response->success = true;
          response->message = "Rosbag recording '" + bag_name + "' force-stopped";
          RCLCPP_WARN(this->get_logger(), "Force-stopped recording: %s", bag_name.c_str());
        } else {
          // waitpid failed
          active_recordings_.erase(it);
          response->success = false;
          response->message = "Error waiting for process termination";
          RCLCPP_ERROR(this->get_logger(), "Error waiting for process termination");
        }
      } else {
        response->success = false;
        response->message = "Failed to send stop signal to recording process";
        RCLCPP_ERROR(this->get_logger(), "Failed to kill process %d", pid);
      }
    } catch (const std::exception& e) {
      response->success = false;
      response->message = "Exception occurred: " + std::string(e.what());
      RCLCPP_ERROR(this->get_logger(), "Exception in stop service handler: %s", e.what());
    }
  }

  /// Service for starting a recording.
  rclcpp::Service<StartRosbag>::SharedPtr start_service_;
  /// Service for stopping a recording.
  rclcpp::Service<StopRosbag>::SharedPtr stop_service_;
  /// Active recordings keyed by bag name.
  std::map<std::string, pid_t> active_recordings_;
};

int main(int argc, char **argv)
{
  rclcpp::init(argc, argv);
  
  auto node = std::make_shared<RosbagServiceServer>();
  
  RCLCPP_INFO(node->get_logger(), "Starting rosbag service server...");
  
  try {
    rclcpp::spin(node);
  } catch (const std::exception& e) {
    RCLCPP_ERROR(node->get_logger(), "Error during spinning: %s", e.what());
  }
  
  rclcpp::shutdown();
  return 0;
}
