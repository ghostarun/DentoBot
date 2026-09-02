#!/usr/bin/env bash
# Update a lab WSL checkout to the pinned LAB_RELEASE tag and GHCR image.
# Leaves .dentobot.env, slicer-user/, and data/ untouched.

set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
repository_root="$(cd -- "${script_directory}/../.." && pwd -P)"
default_workspace_root="$(cd -- "${repository_root}/../../.." && pwd -P)"
# shellcheck source=lab-release-lib.bash
source "${script_directory}/lab-release-lib.bash"

workspace_root="${DENTOBOT_WORKSPACE_ROOT:-${default_workspace_root}}"
check_only=false
skip_docker=false
skip_colcon=false

usage() {
  printf '%s\n' \
    "Usage: update-lab-release.bash [--workspace-root DIR] [--check-only]" \
    "                               [--skip-docker] [--skip-colcon]" \
    "" \
    "Fetches tags, checks out DENTOBOT_TAG, syncs slicer_ros2_module," \
    "pulls the GHCR image, and colcon-builds DentoBot ROS packages in the container."
}

while (( $# > 0 )); do
  case "$1" in
    --workspace-root)
      workspace_root="${2:?--workspace-root requires a directory}"
      shift 2
      ;;
    --check-only)
      check_only=true
      shift
      ;;
    --skip-docker)
      skip_docker=true
      shift
      ;;
    --skip-colcon)
      skip_colcon=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

load_lab_release "$(lab_release_default_path)"
workspace_root="$(cd -- "${workspace_root}" && pwd -P)"
dentobot_repo="${workspace_root}/ros2_ws/src/DentoBot"
slicer_repo="${workspace_root}/ros2_ws/src/slicer_ros2_module"
compose_file="${dentobot_repo}/Workspace/compose.yaml"
container_name="dentobot-slicerros2"

if [[ ! -d ${dentobot_repo}/.git ]]; then
  printf 'DentoBot clone is missing. Run install-lab-wsl.bash first: %s\n' \
    "${dentobot_repo}" >&2
  exit 2
fi
if [[ "$(readlink -f -- "${dentobot_repo}")" != "$(readlink -f -- "${repository_root}")" \
  && ${DENTOBOT_LAB_ALLOW_MAINTAINER:-} != 1 ]]; then
  printf 'This script is not running from %s\n' "${dentobot_repo}" >&2
  exit 2
fi

printf 'Lab pin: tag=%s image=%s slicer_ros2=%s\n' \
  "${DENTOBOT_TAG}" "${IMAGE}" "${SLICERROS2_SHA:0:12}"

if [[ ${DENTOBOT_LAB_ALLOW_MAINTAINER:-} != 1 ]]; then
  refuse_maintainer_worktree "${dentobot_repo}"
fi
require_clean_git_worktree "${dentobot_repo}"
if [[ -d ${slicer_repo}/.git ]]; then
  require_clean_git_worktree "${slicer_repo}"
fi

if [[ ${check_only} == true ]]; then
  printf 'Worktree is clean enough to update. Check-only: no fetch or docker pull.\n'
  exit 0
fi

git -C "${dentobot_repo}" fetch --tags origin
if ! git -C "${dentobot_repo}" fetch origin \
  "refs/tags/${DENTOBOT_TAG}:refs/tags/${DENTOBOT_TAG}" 2>/dev/null \
  && ! git -C "${dentobot_repo}" show-ref --verify --quiet "refs/tags/${DENTOBOT_TAG}"; then
  lab_unpublished_tag_message
  exit 2
fi
git -C "${dentobot_repo}" checkout --detach "refs/tags/${DENTOBOT_TAG}"

if [[ ! -d ${slicer_repo}/.git ]]; then
  git clone "${SLICERROS2_GIT_URL}" "${slicer_repo}"
else
  git -C "${slicer_repo}" fetch origin
fi
if ! git -C "${slicer_repo}" cat-file -e "${SLICERROS2_SHA}^{commit}" 2>/dev/null; then
  git -C "${slicer_repo}" fetch origin "${SLICERROS2_SHA}" \
    || git -C "${slicer_repo}" fetch origin
fi
git -C "${slicer_repo}" checkout --detach "${SLICERROS2_SHA}"

export DENTOBOT_WORKSPACE_ROOT="${workspace_root}"
bash "${dentobot_repo}/Workspace/bootstrap-workspace.bash"

previous_image_id=""
if docker image inspect "${COMPOSE_IMAGE}" >/dev/null 2>&1; then
  previous_image_id="$(docker image inspect --format '{{.Id}}' "${COMPOSE_IMAGE}")"
fi

if [[ ${skip_docker} != true ]]; then
  if ! docker pull "${IMAGE}"; then
    printf '%s\n' \
      "Could not pull ${IMAGE}." \
      'Log in to GHCR with a collaborator GitHub account, then rerun.' >&2
    exit 2
  fi
  docker tag "${IMAGE}" "${COMPOSE_IMAGE}"
fi

new_image_id=""
if docker image inspect "${COMPOSE_IMAGE}" >/dev/null 2>&1; then
  new_image_id="$(docker image inspect --format '{{.Id}}' "${COMPOSE_IMAGE}")"
fi

workspace_config="${workspace_root}/.dentobot.env"
if [[ -f ${workspace_config} ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${workspace_config}"
  set +a
fi
export DENTOBOT_WORKSPACE_ROOT="${workspace_root}"
if [[ -n ${DENTOBOT_BACKEND_PYTHON:-} ]]; then
  export DENTOBOT_BACKEND_ENV_DIR
  DENTOBOT_BACKEND_ENV_DIR="$(dirname -- "$(dirname -- "${DENTOBOT_BACKEND_PYTHON}")")"
fi

image_changed=false
if [[ -n ${previous_image_id} && -n ${new_image_id} && ${previous_image_id} != "${new_image_id}" ]]; then
  image_changed=true
fi

if [[ ${skip_docker} != true && -f ${workspace_config} && -n ${DENTOBOT_BACKEND_PYTHON:-} ]]; then
  compose_command=(
    docker compose
    --project-directory "${workspace_root}"
    -f "${compose_file}"
  )
  if [[ ${image_changed} == true ]]; then
    printf 'Image digest changed; recreating %s\n' "${container_name}"
    "${compose_command[@]}" up -d --force-recreate
  elif docker inspect "${container_name}" >/dev/null 2>&1; then
    printf 'Container %s already exists; leaving it running.\n' "${container_name}"
  else
    "${compose_command[@]}" up -d
  fi
else
  printf '%s\n' \
    'Skipping compose up (need .dentobot.env and DENTOBOT_BACKEND_PYTHON).' \
    'After the CPU backend exists, run scripts/launch-dentoworkflow.bash.'
fi

if [[ ${skip_colcon} != true ]] && docker inspect -f '{{.State.Running}}' "${container_name}" 2>/dev/null | grep -qx true; then
  printf 'Building DentoBot ROS packages inside %s\n' "${container_name}"
  docker exec "${container_name}" bash -lc '
    set -euo pipefail
    set +u
    source /opt/ros/jazzy/setup.bash
    set -u
    cd /workspace/ros2_ws
    colcon build --symlink-install \
      --packages-select dentobot_description dentobot_moveit_config slicer_ros2_module
  '
else
  printf 'Skipping colcon (container not running or --skip-colcon).\n'
fi

printf '%s\n' \
  '' \
  "Checked out ${DENTOBOT_TAG}. .dentobot.env, slicer-user/, and data/ were not modified." \
  'Launch with scripts/launch-dentoworkflow.bash or launch-lab-workflow.bat.' \
  'Step 6 remains simulation/preview. No hardware motion or drilling.'
