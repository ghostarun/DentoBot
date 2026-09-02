#!/usr/bin/env bash
# First-time WSL2 lab layout: DentoBot at a lab/* tag, pinned slicer_ros2_module,
# overlay symlinks, and the GHCR SlicerROS2 image. Does not zip the overlay,
# copy ros2_ws/build|install|log, or download TotalSegmentator weights.

set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
# shellcheck source=lab-release-lib.bash
source "${script_directory}/lab-release-lib.bash"

workspace_root="${DENTOBOT_WORKSPACE_ROOT:-${HOME}/dentobot}"
check_only=false
skip_docker=false

usage() {
  printf '%s\n' \
    "Usage: install-lab-wsl.bash [--workspace-root DIR] [--check-only] [--skip-docker]" \
    "" \
    "Creates ${workspace_root} with ros2_ws/src/DentoBot at the LAB_RELEASE tag," \
    "pins slicer_ros2_module, runs bootstrap-workspace.bash, and pulls the image." \
    "Does not install Conda or copy model caches. Simulation/preview only."
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
if [[ ${workspace_root} == ~* ]]; then
  workspace_root="${HOME}${workspace_root:1}"
fi

printf 'Lab pin: tag=%s image=%s slicer_ros2=%s\n' \
  "${DENTOBOT_TAG}" "${IMAGE}" "${SLICERROS2_SHA:0:12}"

for required in git docker; do
  if ! command -v "${required}" >/dev/null 2>&1; then
    printf 'Required command is unavailable: %s\n' "${required}" >&2
    exit 2
  fi
done

if [[ -z ${DISPLAY:-} ]]; then
  printf '%s\n' \
    'DISPLAY is unset. WSLg on Windows 11 normally provides :0.' \
    'Install can continue; launch-dentoworkflow.bash needs a graphical session.'
fi

if [[ ${check_only} == true ]]; then
  printf 'LAB_RELEASE parsed. Check-only: no clone, checkout, or docker pull.\n'
  printf 'Workspace root would be: %s\n' "${workspace_root}"
  exit 0
fi

mkdir -p "${workspace_root}"
workspace_root="$(cd -- "${workspace_root}" && pwd -P)"
dentobot_repo="${workspace_root}/ros2_ws/src/DentoBot"
slicer_repo="${workspace_root}/ros2_ws/src/slicer_ros2_module"

mkdir -p "${workspace_root}/ros2_ws/src" \
  "${workspace_root}/data/model-cache/totalsegmentator" \
  "${workspace_root}/data/dentobot-runs" \
  "${workspace_root}/slicer-user"

if [[ -d ${dentobot_repo}/.git ]]; then
  if [[ ${DENTOBOT_LAB_ALLOW_MAINTAINER:-} != 1 ]]; then
    refuse_maintainer_worktree "${dentobot_repo}"
  fi
  require_clean_git_worktree "${dentobot_repo}"
else
  printf 'Cloning DentoBot into %s\n' "${dentobot_repo}"
  git clone "${DENTOBOT_GIT_URL}" "${dentobot_repo}"
fi

git -C "${dentobot_repo}" fetch --tags origin
if ! git -C "${dentobot_repo}" fetch origin \
  "refs/tags/${DENTOBOT_TAG}:refs/tags/${DENTOBOT_TAG}" 2>/dev/null \
  && ! git -C "${dentobot_repo}" show-ref --verify --quiet "refs/tags/${DENTOBOT_TAG}"; then
  lab_unpublished_tag_message
  exit 2
fi
git -C "${dentobot_repo}" checkout --detach "refs/tags/${DENTOBOT_TAG}"

if [[ -d ${slicer_repo}/.git ]]; then
  require_clean_git_worktree "${slicer_repo}"
  git -C "${slicer_repo}" fetch origin
else
  printf 'Cloning slicer_ros2_module into %s\n' "${slicer_repo}"
  git clone "${SLICERROS2_GIT_URL}" "${slicer_repo}"
fi
if ! git -C "${slicer_repo}" cat-file -e "${SLICERROS2_SHA}^{commit}" 2>/dev/null; then
  git -C "${slicer_repo}" fetch origin "${SLICERROS2_SHA}" \
    || git -C "${slicer_repo}" fetch origin
fi
git -C "${slicer_repo}" cat-file -e "${SLICERROS2_SHA}^{commit}"
git -C "${slicer_repo}" checkout --detach "${SLICERROS2_SHA}"

export DENTOBOT_WORKSPACE_ROOT="${workspace_root}"
bash "${dentobot_repo}/Workspace/bootstrap-workspace.bash"

if [[ ${skip_docker} == true ]]; then
  printf 'Skipping docker pull (--skip-docker).\n'
else
  if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
    if ! docker pull "${IMAGE}"; then
      printf '%s\n' \
        "Could not pull ${IMAGE}." \
        'Log in to GHCR with the same GitHub account that is a collaborator:' \
        '  gh auth login' \
        '  gh auth token | docker login ghcr.io -u YOUR_GITHUB_USER --password-stdin' \
        'Then rerun this installer.' >&2
      exit 2
    fi
  fi
  docker tag "${IMAGE}" "${COMPOSE_IMAGE}"
  printf 'Tagged %s as %s for compose.yaml\n' "${IMAGE}" "${COMPOSE_IMAGE}"
fi

printf '%s\n' \
  '' \
  "Overlay is ready at ${workspace_root}." \
  'Do not copy ros2_ws/build, ros2_ws/install, ros2_ws/log, data/ cases, or graphify-out.' \
  '' \
  'Next (once per machine, not on every update):' \
  "  1. Edit ${workspace_root}/.dentobot.env (CPU Conda interpreter path)." \
  "  2. Create the Ubuntu CPU backend from Inference/ (see docs/SETUP.md)." \
  '  3. Copy TotalSegmentator tasks 113, 115, and 298 into' \
  "     ${workspace_root}/data/model-cache/totalsegmentator" \
  '     (USB/rsync; never a Slicer launch side effect; no patient identifiers).' \
  '  4. From Windows: Workspace\\scripts\\launch-lab-workflow.bat' \
  '     or in WSL: scripts/launch-dentoworkflow.bash' \
  '' \
  'Step 6 remains simulation/preview. No hardware motion or drilling.'
