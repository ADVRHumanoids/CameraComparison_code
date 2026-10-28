#!/bin/bash

# === CONFIGURATION ===

# Temp file to store messages
TMP_FILE=$(mktemp)
trap "rm -f $TMP_FILE; exit" INT TERM EXIT

# Distance variables
DIST_MIN=0.4
DIST_MAX=1.0
DIST_INC=0.2

# Results folder
RESULT_DIR="natural"

# Base path for the workspace
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WS_BASE="${SCRIPT_DIR}/../../.."

# Modes for each camera
declare -A MODES
MODES[rsi]="hd sd"
MODES[rsf]="hd sd"
MODES[zedxm]="hd_neural sd_neural hd_neural_plus sd_neural_plus hd_neural_light sd_neural_light"
MODES[zedx]="hd_neural sd_neural hd_neural_plus sd_neural_plus hd_neural_light sd_neural_light"

# === CONFIGURATION FUNCTIONS ===

config_rs() {
  local mode=$1
  echo "[CONFIG] Copy Realsense config for $mode"
  cp "${WS_BASE}/depth_estimation/launch/rs_${mode}.launch.py" \
     "${WS_BASE}/depth_estimation/launch/camera.launch.py"
}

config_zed() {
  local camera=$1
  local mode=$2

  local base_config_path="${WS_BASE}/zed-ros2-wrapper-humble-v5.0.0/zed_wrapper/config"

  # Extract type (hd/sd) and profile (neural, ultra, quality, etc.)
  IFS='_' read -r type profile <<< "$mode"

  echo "[CONFIG] Copy config for ${camera} - ${type} - ${profile}"

  # Overwrite the common.yaml file
  cp "${base_config_path}/common_stereo_${profile}_${type}.yaml" "${base_config_path}/common_stereo.yaml"

  # Overwrite the camera-specific file
  cp "${base_config_path}/${camera}_${type}.yaml" "${base_config_path}/${camera}.yaml"
}


# === TEST FUNCTION ===

run_test() {
  local camera=$1
  local mode=$2
  local distance_m=$3
  local distance_mm=$(printf "%04d" $(echo "$distance_m * 1000" | bc | awk '{printf "%d", $0}'))
  local folder="$RESULT_DIR/${distance_mm}"
  local logfile="${folder}/${camera}_${distance_mm}_${mode}_$RESULT_DIR.txt"
  mkdir -p "$folder"

  echo "[INFO] Configuring camera $camera ($mode) at $distance_mm mm..."

  if [[ "$camera" == "rsi" || "$camera" == "rsf" ]]; then
    config_rs $mode
  else
    config_zed $camera $mode
  fi

  # Determine topics
  bag_topics="/tf /tf_static /rgb_image /camera_info /depth_image"

  echo "[INFO] Recording bag for $camera ($mode)..."
  bag_name="${camera}_${distance_mm}_${mode}_$RESULT_DIR"
  # ros2 bag record -s mcap -o "${folder}/${bag_name}" $bag_topics > /dev/null 2>&1 &
  # pid_bag=$!
  ros2 run rosbag_service rosbag_service_client "$bag_name"

  echo "[INFO] Starting test for $camera ($mode) at $distance_mm mm..."

  ros2 launch depth_estimation depth_estimation.launch.py camera:=$camera ground_truth:=$distance_m > "$logfile" 2>&1 &
  sleep 10

  > "$TMP_FILE"  # Clear previous frame_counter output
  stdbuf -oL ros2 topic echo /frame_counter > "$TMP_FILE" &
  pid_echo=$!
  if [ -z "$pid_echo" ]; then
    echo "[WARN] Failed to start topic echo. Retrying..."
    sleep 3
    stdbuf -oL ros2 topic echo /frame_counter > "$TMP_FILE" &
    pid_echo=$!
  fi

  ros2 launch depth_estimation mask_publisher.launch.py camera:=$camera mask:=aruco > mask.txt 2>&1 &

  # === COUNT MESSAGES ===
  echo "[INFO] Counting messages on /frame_counter .."
  message_count=0
  threshold=300

  max_elapsed=120  # seconds
  wait_time=8      # seconds
  if [[ "$camera" == "zedxm" || "$camera" == "zedx" ]] && [[ "$mode" == *"hd"* ]]; then
    max_elapsed=350
    wait_time=15
  fi

  start_time=$(date +%s)
  while true; do
    # Extract the latest counter value from the log
    last_line=$(grep "Frame count" "$TMP_FILE" | tail -n 1)
    message_count=$(echo "$last_line" | grep -oE '[0-9]+')

    if [[ -z "$message_count" ]]; then
      message_count=0
    fi

    echo -ne "\r[INFO] Frame count: $message_count"

    current_time=$(date +%s)
    elapsed=$((current_time - start_time))

    if [[ $message_count -ge $threshold || $elapsed -ge $max_elapsed ]]; then
      if [[ $elapsed -ge $max_elapsed ]]; then
        echo -e "\n[INFO] $max_elapsed seconds elapsed. Entering closing cycle."
      else
        echo -e "\n[INFO] Threshold reached!"
      fi

      kill -SIGINT "$pid_echo" 2>/dev/null
      wait "$pid_echo" 2>/dev/null
      #sleep $wait_time
      ros2 run rosbag_service rosbag_stop_client "$bag_name"
      # kill -SIGINT $pid_bag 2>/dev/null
      # wait $pid_bag 2>/dev/null
      sleep 5
      # if [ $? -eq 0 ]; then
      #   echo "[INFO] ros2 bag process terminated successfully."
      # fi

      pids=$(grep -oP 'process started with pid \[\K\d+(?=\])' $logfile)
      pid_mask=$(grep -oP 'process started with pid \[\K\d+(?=\])' mask.txt)

      # Stop other processes
      for pid in $pids $pid_mask; do
        echo "[INFO] Terminating process $pid..."
        kill -SIGTERM "$pid" 2>/dev/null
        wait "$pid" 2>/dev/null
        sleep 5
        if [ $? -eq 0 ]; then
          echo "[INFO] Process $pid terminated successfully."
        else
          echo "[WARN] Process $pid did not terminate gracefully. Forcing kill."
          kill -9 $pid 2>/dev/null
        fi
      done
      break
    fi

    sleep 0.5
  done

  echo "[INFO] Test for $camera ($mode) at $distance_mm mm completed. Log saved to $logfile"

  # Copy ros2bag output and logfile via scp to another machine for monitoring
  echo "[INFO] Copying log and bag to remote machine..."
  ssh -i ~/.ssh/id_rsa.pub username@hostname "mkdir -p /home/ubuntu/$folder/"
  scp -i ~/.ssh/id_rsa.pub "$logfile" username@hostname:/home/ubuntu/$folder/
  echo "[INFO] Logs and bags copied to remote machine."
  # rm -rf "$logfile" "${folder}/${bag_name}"
  # echo "[INFO] Local logs and bags deleted."
}


# === LOOP OVER DISTANCES ===

distance=$DIST_MIN
reverse=False
while (( $(echo "$distance <= $DIST_MAX" | bc -l) )); do
  echo -e "\nPress ENTER to start tests at ${distance} m..."
  read
  reverse=true  # Set to true to reverse the camera order, false to keep original

  # Define camera list
  cameras=(rsi zedxm zedx rsf)

  # Reverse the array if needed
  if $reverse; then
    cameras=($(echo "${cameras[@]}" | tac -s ' '))
  fi

  # Loop through cameras
  for camera in "${cameras[@]}"; do
    echo -e "\nPress ENTER to start tests for ${camera}..."
    read
    for mode in ${MODES[$camera]}; do
      run_test $camera $mode $distance
    done
  done

  # Increase distance
  distance=$(echo "$distance + $DIST_INC" | bc)
done

echo "[DONE] All tests completed."
