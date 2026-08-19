#!/usr/bin/env bash

set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
repository_root="$(cd -- "${script_directory}/../.." && pwd -P)"
default_workspace_root="$(cd -- "${repository_root}/../../.." && pwd -P)"
workspace_root="${DENTOBOT_WORKSPACE_ROOT:-${default_workspace_root}}"
workspace_config="${DENTOBOT_WORKSPACE_CONFIG:-${workspace_root}/.dentobot.env}"
compose_file="${repository_root}/Workspace/compose.yaml"
container_name="dentobot-slicerros2"

backend_source="/workspace/ros2_ws/src/DentoBot/Inference/src"
module_path="/workspace/ros2_ws/src/DentoBot/DENTOWorkflow"
endoplanner_module_path="/workspace/data/SlicerEndoPlanner-main/PulpChamberOpenPlanning"
slicer_module_paths="${module_path}"
backend_dependency_probe='import importlib.metadata as m; import sys; expected={"dentobot-inference":"0.2.0","numpy":"2.2.6","nibabel":"5.4.2","torch":"2.10.0+cpu","torchvision":"0.25.0+cpu","TotalSegmentator":"2.16.0","nnunetv2":"2.8.1","openvino":"2026.2.0","pytest":"8.4.2"}; assert sys.version_info[:2] == (3, 12); actual={name:m.version(name) for name in expected}; assert actual == expected, actual'
check_only=false
print_backend_python=false
x11_access_granted=false

usage() {
  printf '%s\n' \
    "Usage: scripts/launch-dentoworkflow.bash [--check-only]" \
    "" \
    "Without options, verify the dentobot Conda backend and open" \
    "3D Slicer with DENTO Workflow loaded from the repository source." \
    "" \
    "Machine configuration: ${workspace_config}" \
    "Template: ${repository_root}/Workspace/.dentobot.env.example" \
    "" \
    "--check-only  Verify Compose, the backend, and module files without" \
    "              opening a GUI." \
    "--print-backend-python" \
    "              Print the single configured backend interpreter path."
}

while (( $# > 0 )); do
  case "$1" in
    --check-only)
      check_only=true
      ;;
    --print-backend-python)
      print_backend_python=true
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
  shift
done

if [[ -f ${workspace_config} ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${workspace_config}"
  set +a
fi

backend_python="${DENTOBOT_BACKEND_PYTHON:-}"
backend_execution_mode="${DENTOBOT_BACKEND_EXECUTION_MODE:-local}"
backend_device="${DENTOBOT_BACKEND_DEVICE:-cpu}"
render_device="${DENTOBOT_RENDER_DEVICE:-/dev/dri/renderD128}"
run_artifact_root="${DENTOBOT_RUN_ARTIFACT_ROOT:-/workspace/data/dentobot-runs}"
totalseg_home_dir="${DENTOBOT_TOTALSEG_HOME_DIR:-/workspace/data/model-cache/totalsegmentator}"

if [[ -z ${backend_python} ]]; then
  printf '%s\n' \
    "Backend Python is not configured in ${workspace_config}." \
    "Copy ${repository_root}/Workspace/.dentobot.env.example there and edit it." >&2
  exit 2
fi

if [[ ${print_backend_python} == true ]]; then
  printf '%s\n' "${backend_python}"
  exit 0
fi

if [[ ${backend_python} != /* ]]; then
  printf 'Backend Python must be an absolute path: %s\n' "${backend_python}" >&2
  exit 2
fi
if [[ ${backend_execution_mode} != "local" ]]; then
  printf '%s\n' \
    "The Linux launcher requires DENTOBOT_BACKEND_EXECUTION_MODE=local." \
    "Use launch-dentoworkflow.ps1 for the Windows-to-WSL adapter." >&2
  exit 2
fi
if [[ ${backend_device} != "cpu" ]]; then
  printf '%s\n' \
    "The current Ubuntu environment is pinned and verified for CPU inference." \
    "Set DENTOBOT_BACKEND_DEVICE=cpu; a Linux CUDA profile requires its own pinned manifest." >&2
  exit 2
fi
backend_environment_directory="$(dirname -- "$(dirname -- "${backend_python}")")"
if [[ ! -d ${backend_environment_directory} ]]; then
  printf 'Backend environment directory is unavailable: %s\n' \
    "${backend_environment_directory}" >&2
  exit 2
fi
if [[ ${run_artifact_root} != /* ]]; then
  printf 'Run-artifact root must be an absolute container path: %s\n' \
    "${run_artifact_root}" >&2
  exit 2
fi
if [[ ${totalseg_home_dir} != /* ]]; then
  printf 'TotalSegmentator cache must be an absolute container path: %s\n' \
    "${totalseg_home_dir}" >&2
  exit 2
fi

export DENTOBOT_BACKEND_ENV_DIR="${backend_environment_directory}"
export DENTOBOT_BACKEND_EXECUTION_MODE="${backend_execution_mode}"
export DENTOBOT_BACKEND_PYTHON="${backend_python}"
export DENTOBOT_BACKEND_DEVICE="${backend_device}"
export DENTOBOT_RENDER_DEVICE="${render_device}"
export DENTOBOT_RUN_ARTIFACT_ROOT="${run_artifact_root}"
export DENTOBOT_TOTALSEG_HOME_DIR="${totalseg_home_dir}"
export DENTOBOT_WORKSPACE_ROOT="${workspace_root}"

if ! command -v docker >/dev/null 2>&1; then
  printf 'Required command is unavailable: docker\n' >&2
  exit 2
fi
if [[ ! -x ${backend_python} ]]; then
  printf '%s\n' \
    "The dentobot Conda environment has no Python: ${backend_python}" \
    'Install Python 3.12 in that environment before launching.' >&2
  exit 2
fi
if [[ ! -c ${render_device} ]]; then
  printf '%s\n' \
    "Required Intel GPU render node is unavailable: ${render_device}" \
    'DENTO Workflow is not launched with an implicit software-rendering fallback.' >&2
  exit 2
fi

if ! "${backend_python}" -c "${backend_dependency_probe}" \
  >/dev/null 2>&1; then
  printf '%s\n' \
    'The dentobot Conda environment is incomplete or has unexpected versions.' \
    'Expected the repository-pinned Python 3.12 CPU segmentation stack.' >&2
  exit 2
fi

compose_command=(
  docker compose
  --project-directory "${workspace_root}"
  -f "${compose_file}"
)
"${compose_command[@]}" config -q

if docker inspect "${container_name}" >/dev/null 2>&1; then
  container_status="$(docker inspect --format '{{.State.Status}}' "${container_name}")"
  if [[ ${container_status} == "paused" ]]; then
    printf 'Unpausing %s...\n' "${container_name}"
    docker unpause "${container_name}" >/dev/null
    container_status="running"
  fi
  if [[ ${container_status} == "running" ]]; then
    active_slicer_processes="$(
      docker exec "${container_name}" ps -eo pid=,stat=,comm=,args= 2>/dev/null \
        | awk '
            $2 !~ /^Z/ &&
            ($3 == "SlicerApp-real" ||
             $3 == "Slicer" ||
             ($3 == "ros2" &&
              $0 ~ /launch slicer_ros2_module slicer\.launch\.py/)) {
              print
            }
          ' || true
    )"
    if [[ -n ${active_slicer_processes} ]]; then
      printf '%s\n' \
        'A live Slicer session or Slicer test already exists in the container.' \
        'Close it normally before starting or reconfiguring DENTO Workflow:' >&2
      printf '%s\n' "${active_slicer_processes}" >&2
      exit 2
    fi
  fi
fi

printf 'Starting the DENTOBOT development container...\n'
"${compose_command[@]}" up -d

container_runtime_safeguards="$(
  docker inspect --format \
    '{{.HostConfig.Init}} {{.HostConfig.PidsLimit}} {{.HostConfig.CpuShares}} {{.HostConfig.OomScoreAdj}}' \
    "${container_name}"
)"
if [[ ${container_runtime_safeguards} != "true 512 512 500" ]]; then
  printf '%s\n' \
    'The container is missing the verified workstation stability safeguards.' \
    "Observed init/PID-limit/CPU-shares/OOM-score: ${container_runtime_safeguards}" \
    'Expected: true 512 512 500.' >&2
  exit 2
fi

docker exec \
  -e PYTHONPATH="${backend_source}" \
  "${container_name}" \
  "${backend_python}" -c "${backend_dependency_probe}; print('Conda CPU segmentation dependency check passed.')"
docker exec "${container_name}" mkdir -p "${run_artifact_root}"
docker exec "${container_name}" test -d "${totalseg_home_dir}"
docker exec \
  -e PYTHONPATH="${backend_source}" \
  "${container_name}" \
  "${backend_python}" -m dentobot_inference health \
  --json \
  --require-device cpu
docker exec "${container_name}" test -f "${module_path}/DENTOWorkflow.py"
docker exec "${container_name}" test -f \
  "${module_path}/Resources/UI/DENTOWorkflow.ui"
if docker exec "${container_name}" test -f \
  "${endoplanner_module_path}/PulpChamberOpenPlanning.py"; then
  slicer_module_paths+=" ${endoplanner_module_path}"
fi
docker exec "${container_name}" test -c "${render_device}"
container_slicer_priority="$(
  docker exec "${container_name}" printenv SLICER_BACKGROUND_THREAD_PRIORITY
)"
if [[ ${container_slicer_priority} != "0" ]]; then
  printf '%s\n' \
    'The container does not preserve normal Slicer process priority.' \
    'Expected SLICER_BACKGROUND_THREAD_PRIORITY=0.' >&2
  exit 2
fi

printf '%s\n' \
  "Backend Python: ${backend_python}" \
  "Backend adapter: ${backend_execution_mode}" \
  "Backend device: ${backend_device}" \
  "Backend environment: ${backend_environment_directory}" \
  "Workspace root: ${workspace_root}" \
  "Workspace configuration: ${workspace_config}" \
  "Run artifacts: ${run_artifact_root}" \
  "TotalSegmentator cache: ${totalseg_home_dir}" \
  "DENTO Workflow: ${module_path}" \
  "Slicer module paths: ${slicer_module_paths}" \
  "GPU render node: ${render_device}" \
  "Slicer background priority: ${container_slicer_priority}" \
  "Runtime safeguards (init/PIDs/CPU-shares/OOM-score): ${container_runtime_safeguards}"

if [[ ${check_only} == true ]]; then
  printf 'DENTOBOT launcher check passed. GUI launch was skipped.\n'
  exit 0
fi

if [[ -z ${DISPLAY:-} ]]; then
  printf '%s\n' \
    'DISPLAY is empty. Run this launcher from an Ubuntu desktop terminal, not SSH.' >&2
  exit 2
fi
if ! command -v xhost >/dev/null 2>&1; then
  printf 'Required GUI command is unavailable: xhost\n' >&2
  exit 2
fi

cleanup_x11() {
  if [[ ${x11_access_granted} == true ]]; then
    xhost -SI:localuser:root >/dev/null 2>&1 || true
  fi
}
trap cleanup_x11 EXIT INT TERM

printf 'Granting local container root temporary access to DISPLAY=%s...\n' "${DISPLAY}"
xhost +SI:localuser:root >/dev/null
x11_access_granted=true

printf 'Opening 3D Slicer directly on DENTO Workflow.\n'
docker exec -it \
  -e DISPLAY="${DISPLAY}" \
  -e DENTOBOT_SLICER_MODULE_PATHS="${slicer_module_paths}" \
  "${container_name}" \
  bash -lc '
    source /opt/ros/jazzy/setup.bash
    source /workspace/ros2_ws/install/setup.bash
    export PYTHONPATH=/workspace/ros2_ws/src/DentoBot/Inference/src${PYTHONPATH:+:${PYTHONPATH}}
    # Merge DENTO Workflow into the SlicerROS2 launch path list. A second
    # --additional-module-paths in slicer_args can leave ROS2 undiscovered
    # while DENTOWorkflow still loads.
    extra_module_paths=""
    for p in ${DENTOBOT_SLICER_MODULE_PATHS}; do
      extra_module_paths="${extra_module_paths:+${extra_module_paths}:}${p}"
    done
    if [[ -n ${extra_module_paths} ]]; then
      export SLICER_ROS2_MODULE_PATHS="${extra_module_paths}${SLICER_ROS2_MODULE_PATHS:+:${SLICER_ROS2_MODULE_PATHS}}"
    fi
    exec ros2 launch slicer_ros2_module slicer.launch.py \
      "slicer_args:=--no-splash --python-code '"'"'slicer.util.selectModule(\"DENTOWorkflow\")'"'"'"
  '
