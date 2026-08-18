#!/usr/bin/env bash
# Start dentobot_description for SlicerROS2 (no RViz). Use with DENTOWorkflow
# Step 6 "Start Stack & Connect Motion Control" or the ROS2 module Load Robot
# workflow. Joint states are driven by Motion Control sliders, not a neutral pose.

set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
container_name="dentobot-slicerros2"

usage() {
  printf '%s\n' \
    "Usage: scripts/launch-dentobot-description-for-slicer.bash [--check-only]" \
    "" \
    "Start robot_state_publisher and the Slicer-driven joint_states bridge." \
    "Does not open RViz or the manual PyQt slider window." \
    "" \
    "--check-only  Verify the container and package build without launching."
}

check_only=false
while (( $# > 0 )); do
  case "$1" in
    --check-only)
      check_only=true
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if ! docker ps --format '{{.Names}}' | grep -qx "${container_name}"; then
  printf '%s\n' \
    "Container ${container_name} is not running." \
    "Start the dentobot workspace container first." >&2
  exit 2
fi

docker exec "${container_name}" bash -lc '
  source /opt/ros/jazzy/setup.bash
  cd /workspace/ros2_ws
  colcon build --symlink-install --packages-select dentobot_description
'

active_description_processes="$(
  docker exec "${container_name}" ps -eo pid=,stat=,comm=,args= \
    | awk '
        $2 !~ /^Z/ &&
        ($3 == "robot_state_pub" ||
         $0 ~ /dentobot_(manual|neutral|slicer)_joint_state_publisher/ ||
         $0 ~ /ros2 launch dentobot_description/) {
          print
        }
      '
)"
if [[ -n ${active_description_processes} ]]; then
  printf '%s\n' \
    'A DENTOBOT description launch is already running:' \
    "${active_description_processes}"
  if [[ ${check_only} == true ]]; then
    exit 0
  fi
  printf '%s\n' \
    'Close the existing launch before starting another.' >&2
  exit 2
fi

if [[ ${check_only} == true ]]; then
  printf 'DENTOBOT description-for-Slicer check passed.\n'
  exit 0
fi

printf '%s\n' \
  'Starting dentobot_description (no RViz, Slicer-driven joint_states).' \
  'Press Ctrl+C in this terminal to stop the stack.' \
  'Then in Slicer: DENTO Workflow Step 6 → Start Stack & Connect Motion Control.'

docker exec -it "${container_name}" bash -lc '
  source /opt/ros/jazzy/setup.bash
  source /workspace/ros2_ws/install/setup.bash
  exec ros2 launch dentobot_description description.launch.py \
    use_rviz:=false joint_state_mode:=slicer
'
