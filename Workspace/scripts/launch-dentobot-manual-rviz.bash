#!/usr/bin/env bash

set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
workflow_launcher="${script_directory}/launch-dentoworkflow.bash"
container_name="dentobot-slicerros2"
x11_access_granted=false

if [[ -z ${DISPLAY:-} ]]; then
  printf '%s\n' \
    'DISPLAY is empty. Run this launcher from the Ubuntu graphical desktop.' >&2
  exit 2
fi
if ! command -v xhost >/dev/null 2>&1; then
  printf 'Required GUI command is unavailable: xhost\n' >&2
  exit 2
fi

"${workflow_launcher}" --check-only

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
         $0 ~ /dentobot_(manual|neutral)_joint_state_publisher/ ||
         $0 ~ /ros2 launch dentobot_description/) {
          print
        }
      '
)"
if [[ -n ${active_description_processes} ]]; then
  printf '%s\n' \
    'A DENTOBOT description/manual-articulation process is already running.' \
    'Close its launch terminal normally before starting another:' >&2
  printf '%s\n' "${active_description_processes}" >&2
  exit 2
fi

cleanup_x11() {
  if [[ ${x11_access_granted} == true ]]; then
    xhost -SI:localuser:root >/dev/null 2>&1 || true
  fi
}
trap cleanup_x11 EXIT INT TERM

printf 'Granting container root temporary access to DISPLAY=%s...\n' "${DISPLAY}"
xhost +SI:localuser:root >/dev/null
x11_access_granted=true

docker_exec_flags=(-i)
if [[ -t 0 && -t 1 ]]; then
  docker_exec_flags+=(-t)
fi

printf '%s\n' \
  'Opening RViz and DENTOBOT manual joint sliders.' \
  'This is an uncalibrated simulation-only model with no hardware command path.' \
  'Close the slider/RViz windows or press Ctrl+C here to stop the launch.'
docker exec "${docker_exec_flags[@]}" \
  -e DISPLAY="${DISPLAY}" \
  "${container_name}" \
  bash -lc '
    source /opt/ros/jazzy/setup.bash
    source /workspace/ros2_ws/install/setup.bash
    exec ros2 launch dentobot_description manual.launch.py
  '
