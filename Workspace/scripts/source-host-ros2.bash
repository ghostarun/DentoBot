#!/usr/bin/env bash

# Source this file from an interactive Bash shell:
#   source /path/to/dentobot/scripts/source-host-ros2.bash
#
# Keep the host Lyrical environment separate from the Jazzy SlicerROS2
# container environment. Do not source this helper inside the container.
#
# Override the project defaults before sourcing when a different isolated
# test domain is needed:
#   export DENTOBOT_ROS_DOMAIN_ID=74
#   source /path/to/dentobot/scripts/source-host-ros2.bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  printf 'This file must be sourced, not executed:\n  source %s\n' "${BASH_SOURCE[0]}" >&2
  exit 2
fi

if [[ -n "${ROS_DISTRO:-}" && "${ROS_DISTRO}" != "lyrical" ]]; then
  printf 'Refusing to overlay ROS 2 Lyrical on active ROS_DISTRO=%s.\n' \
    "${ROS_DISTRO}" >&2
  return 1
fi

if [[ "${ROS_LOCALHOST_ONLY:-0}" == "1" ]]; then
  printf 'Refusing project initialization with ROS_LOCALHOST_ONLY=1; '\
'the host-network SlicerROS2 container would be undiscoverable.\n' >&2
  return 1
fi

source /opt/ros/lyrical/setup.bash

export ROS_DOMAIN_ID="${DENTOBOT_ROS_DOMAIN_ID:-73}"
export ROS_AUTOMATIC_DISCOVERY_RANGE="${ROS_AUTOMATIC_DISCOVERY_RANGE:-SUBNET}"

dentobot_source_canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
dentobot_source_script_directory="$(
  cd -- "$(dirname -- "${dentobot_source_canonical_script}")" && pwd -P
)"
dentobot_source_repository_root="$(
  cd -- "${dentobot_source_script_directory}/../.." && pwd -P
)"
dentobot_source_default_workspace_root="$(
  cd -- "${dentobot_source_repository_root}/../../.." && pwd -P
)"
dentobot_source_workspace_root="${DENTOBOT_WORKSPACE_ROOT:-${dentobot_source_default_workspace_root}}"
dentobot_host_overlay="${dentobot_source_workspace_root}/ros2_host_ws/install/setup.bash"
if [[ -f "${dentobot_host_overlay}" ]]; then
  source "${dentobot_host_overlay}"
fi
unset dentobot_host_overlay \
  dentobot_source_canonical_script \
  dentobot_source_default_workspace_root \
  dentobot_source_repository_root \
  dentobot_source_script_directory \
  dentobot_source_workspace_root

printf 'DENTOBOT host ROS 2: distro=%s domain=%s discovery=%s command=%s\n' \
  "${ROS_DISTRO}" \
  "${ROS_DOMAIN_ID}" \
  "${ROS_AUTOMATIC_DISCOVERY_RANGE}" \
  "$(command -v ros2)"
