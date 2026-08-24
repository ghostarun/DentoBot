#!/usr/bin/env bash
# Start the external DENTOBOT description + MoveIt simulation stack without
# opening Slicer. Joint states are driven by Slicer messages when it connects.

set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
container_name="dentobot-slicerros2"

usage() {
  printf '%s\n' \
    "Usage: scripts/launch-dentobot-description-for-slicer.bash [--check-only]" \
    "" \
    "Start robot_state_publisher, one Slicer joint-state source, and MoveIt." \
    "Planning is enabled; trajectory execution and hardware are disabled." \
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
  python3 -c "import moveit_configs_utils"
  command -v xacro >/dev/null
  colcon build --symlink-install \
    --base-paths \
      /workspace/ros2_ws/src/DentoBot/dentobot_description \
      /workspace/ros2_ws/src/DentoBot/dentobot_moveit_config \
    --packages-select dentobot_description dentobot_moveit_config
'

active_description_processes="$(
  docker exec "${container_name}" ps -eo pid=,stat=,comm=,args= \
    | awk '
        $2 !~ /^Z/ &&
        ($3 == "robot_state_pub" || $3 == "move_group" ||
         $0 ~ /dentobot_(manual|neutral|slicer)_joint_state_publisher/ ||
         $0 ~ /ros2 launch (dentobot_description|dentobot_moveit_config)/) {
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
  printf 'DENTOBOT simulation-stack check passed.\n'
  exit 0
fi

printf '%s\n' \
  'Starting the DENTOBOT simulation stack (description + MoveIt).' \
  'Press Ctrl+C in this terminal to stop the stack.' \
  'Then in Slicer: DENTO Workflow Step 6 → Connect Motion Control.'

docker exec -it "${container_name}" bash -lc '
  source /opt/ros/jazzy/setup.bash
  source /workspace/ros2_ws/install/setup.bash
  exec ros2 launch dentobot_moveit_config simulation.launch.py
'
