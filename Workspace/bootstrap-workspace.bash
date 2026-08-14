#!/usr/bin/env bash

set -euo pipefail

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository_root="$(cd -- "${script_directory}/.." && pwd -P)"
default_workspace_root="$(cd -- "${repository_root}/../../.." && pwd -P)"
workspace_root="${DENTOBOT_WORKSPACE_ROOT:-${default_workspace_root}}"

if [[ "$(readlink -f -- "${workspace_root}/ros2_ws/src/DentoBot")" != "${repository_root}" ]]; then
  printf 'Repository is not at the expected workspace path: %s\n' \
    "${workspace_root}/ros2_ws/src/DentoBot" >&2
  exit 2
fi

install_link() {
  local link_path="$1"
  local relative_target="$2"

  if [[ -L ${link_path} ]]; then
    if [[ $(readlink -- "${link_path}") == "${relative_target}" ]]; then
      return
    fi
    printf 'Refusing to replace a different symlink: %s\n' "${link_path}" >&2
    exit 2
  fi
  if [[ -e ${link_path} ]]; then
    printf 'Refusing to replace an existing path: %s\n' "${link_path}" >&2
    exit 2
  fi
  ln -s "${relative_target}" "${link_path}"
}

install_link "${workspace_root}/AGENTS.md" \
  "ros2_ws/src/DentoBot/Workspace/AGENTS.md"
install_link "${workspace_root}/compose.yaml" \
  "ros2_ws/src/DentoBot/Workspace/compose.yaml"
install_link "${workspace_root}/docs" \
  "ros2_ws/src/DentoBot/Workspace/docs"
install_link "${workspace_root}/scripts" \
  "ros2_ws/src/DentoBot/Workspace/scripts"
install_link "${workspace_root}/ros2_ws/src/dentobot_description" \
  "DentoBot/dentobot_description"

if [[ ! -e ${workspace_root}/.dentobot.env ]]; then
  cp "${script_directory}/.dentobot.env.example" \
    "${workspace_root}/.dentobot.env"
  printf 'Created %s; edit its backend interpreter before launching.\n' \
    "${workspace_root}/.dentobot.env"
fi

printf 'DENTOBOT workspace links are ready at %s\n' "${workspace_root}"
