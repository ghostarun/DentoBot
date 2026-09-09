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
host_uid="$(id -u)"
host_gid="$(id -g)"
host_x11_user="$(id -un)"
slicer_home_dir="${workspace_root}/slicer-home"
legacy_slicer_user_dir="${workspace_root}/slicer-user"

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
if [[ ! -e ${render_device} ]]; then
  printf 'Render device is unavailable: %s\n' "${render_device}" >&2
  exit 2
fi
render_gid="$(stat -c '%g' "${render_device}")"
if [[ -z ${render_gid} || ${render_gid} == "0" ]]; then
  printf '%s\n' \
    "Could not resolve a non-root group owner for ${render_device}." \
    'Non-root SlicerROS2 needs the DRM render group for Mesa access.' >&2
  exit 2
fi

export DENTOBOT_BACKEND_ENV_DIR="${backend_environment_directory}"
export DENTOBOT_BACKEND_EXECUTION_MODE="${backend_execution_mode}"
export DENTOBOT_BACKEND_PYTHON="${backend_python}"
export DENTOBOT_BACKEND_DEVICE="${backend_device}"
export DENTOBOT_RENDER_DEVICE="${render_device}"
export DENTOBOT_RENDER_GID="${render_gid}"
export DENTOBOT_HOST_UID="${host_uid}"
export DENTOBOT_HOST_GID="${host_gid}"
export DENTOBOT_RUN_ARTIFACT_ROOT="${run_artifact_root}"
export DENTOBOT_TOTALSEG_HOME_DIR="${totalseg_home_dir}"
export DENTOBOT_WORKSPACE_ROOT="${workspace_root}"

ensure_slicer_home_layout() {
  local config_slicer="${slicer_home_dir}/.config/slicer.org"
  mkdir -p "${config_slicer}"

  if [[ -L ${legacy_slicer_user_dir} ]]; then
    ln -sfn slicer-home/.config/slicer.org "${legacy_slicer_user_dir}"
    return 0
  fi

  if [[ -d ${legacy_slicer_user_dir} ]]; then
    # Legacy layout mounted flat settings as /root/.config/slicer.org.
    # Move those files under the host-owned HOME/.config/slicer.org tree.
    if compgen -G "${legacy_slicer_user_dir}/*" >/dev/null; then
      printf 'Migrating legacy slicer-user/ into slicer-home/.config/slicer.org/\n'
      # Older root-container sessions may have left root-owned settings here.
      if [[ "$(docker inspect --format '{{.State.Status}}' "${container_name}" 2>/dev/null || true)" == "running" ]]; then
        docker exec -u 0 "${container_name}" bash -lc "
          chown -R ${host_uid}:${host_gid} /root/.config/slicer.org
        " >/dev/null || true
      fi
      if ! mv "${legacy_slicer_user_dir}"/* "${config_slicer}/"; then
        printf '%s\n' \
          "Failed to migrate ${legacy_slicer_user_dir} into ${config_slicer}." \
          'Fix ownership of slicer-user/ (it may still be root-owned) and retry.' >&2
        exit 2
      fi
    fi
    rmdir "${legacy_slicer_user_dir}" 2>/dev/null || true
    if [[ -e ${legacy_slicer_user_dir} && ! -L ${legacy_slicer_user_dir} ]]; then
      printf '%s\n' \
        "Could not replace ${legacy_slicer_user_dir} with a compatibility symlink." \
        'Move leftover files aside, then rerun the launcher.' >&2
      exit 2
    fi
  fi

  ln -sfn slicer-home/.config/slicer.org "${legacy_slicer_user_dir}"
}

prepare_host_uid_runtime() {
  local needs_legacy_migration=false
  if [[ -d ${legacy_slicer_user_dir} && ! -L ${legacy_slicer_user_dir} ]]; then
    needs_legacy_migration=true
  fi

  if [[ ${needs_legacy_migration} == true ]]; then
    # chown while the old root/.config mount is still attached, then recreate.
    if [[ "$(docker inspect --format '{{.State.Status}}' "${container_name}" 2>/dev/null || true)" == "running" ]]; then
      docker exec -u 0 "${container_name}" bash -lc "
        chown -R ${host_uid}:${host_gid} /workspace/data /root/.config/slicer.org
      " >/dev/null || true
    fi
    stop_container_for_bind_migration
  fi

  ensure_slicer_home_layout
}

stop_container_for_bind_migration() {
  if ! docker inspect "${container_name}" >/dev/null 2>&1; then
    return 0
  fi
  printf 'Stopping %s so bind-mount ownership layout can be updated...\n' \
    "${container_name}"
  docker stop --time 30 "${container_name}" >/dev/null 2>&1 || true
  docker rm -f "${container_name}" >/dev/null 2>&1 || true
}

reclaim_bind_mount_ownership() {
  if ! docker inspect "${container_name}" >/dev/null 2>&1; then
    return 0
  fi
  if [[ "$(docker inspect --format '{{.State.Status}}' "${container_name}")" != "running" ]]; then
    return 0
  fi
  # Root exec is intentional: only root can repair leftover root-owned files
  # from older container sessions or `docker exec -u 0` tooling.
  docker exec -u 0 "${container_name}" bash -lc "
    mkdir -p /workspace/ros2_ws/build /workspace/ros2_ws/install /workspace/ros2_ws/log
    chown -R ${host_uid}:${host_gid} \
      /workspace/data \
      /home/dentobot \
      /workspace/ros2_ws/build \
      /workspace/ros2_ws/install \
      /workspace/ros2_ws/log
  " >/dev/null
}

docker_daemon_ready() {
  docker info >/dev/null 2>&1
}

docker_units_enabled_on_boot() {
  command -v systemctl >/dev/null 2>&1 || return 1
  systemctl is-enabled --quiet docker.socket 2>/dev/null \
    && systemctl is-enabled --quiet docker.service 2>/dev/null
}

try_systemctl() {
  local action="$1"
  shift
  if [[ -z ${action} ]] || (( $# < 1 )); then
    return 1
  fi
  if ! command -v systemctl >/dev/null 2>&1; then
    return 1
  fi
  if systemctl "${action}" "$@" >/dev/null 2>&1; then
    return 0
  fi
  if command -v sudo >/dev/null 2>&1 \
    && sudo -n systemctl "${action}" "$@" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

start_docker_daemon() {
  try_systemctl start docker.socket docker.service
}

enable_docker_daemon_on_boot() {
  docker_units_enabled_on_boot && return 0
  try_systemctl enable docker.socket docker.service
}

ensure_docker_daemon() {
  local started_now=false
  local attempt

  if ! docker_daemon_ready; then
    printf 'Docker daemon is not reachable; attempting to start docker.socket/docker.service...\n'
    if ! start_docker_daemon; then
      printf '%s\n' \
        'Could not start the Docker daemon.' \
        'Start it once with: systemctl start docker' \
        'Enable on boot (may need your password) with: systemctl enable --now docker' >&2
      exit 2
    fi
    started_now=true
    for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
      if docker_daemon_ready; then
        break
      fi
      sleep 0.25
    done
    if ! docker_daemon_ready; then
      printf '%s\n' \
        'Docker start was requested, but the API socket is still unavailable.' \
        'Check: systemctl status docker' >&2
      exit 2
    fi
    printf 'Docker daemon is ready.\n'
  fi

  if docker_units_enabled_on_boot; then
    return 0
  fi
  if enable_docker_daemon_on_boot; then
    printf 'Enabled docker.socket and docker.service to start on boot.\n'
    return 0
  fi
  if [[ ${started_now} == true ]]; then
    printf '%s\n' \
      'Docker started for this launch, but enabling on boot needs elevated rights.' \
      'Run once (password may be required): systemctl enable --now docker' >&2
  fi
}

if ! command -v docker >/dev/null 2>&1; then
  printf 'Required command is unavailable: docker\n' >&2
  exit 2
fi
ensure_docker_daemon
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
prepare_host_uid_runtime

if docker inspect "${container_name}" >/dev/null 2>&1; then
  container_status="$(docker inspect --format '{{.State.Status}}' "${container_name}")"
  if [[ ${container_status} == "paused" ]]; then
    printf 'Unpausing %s...\n' "${container_name}"
    docker unpause "${container_name}" >/dev/null
    container_status="running"
  fi
  if [[ ${check_only} == false ]]; then
    if [[ ${container_status} == "running" ]]; then
      printf '%s\n' \
        "Restarting the dedicated ${container_name} container for a clean GUI session..." \
        'Existing DENTOBOT Slicer, ROS, MoveIt, and test processes will be stopped.' \
        'Save open Slicer scenes first; unsaved in-container UI state cannot be recovered.'
      docker restart --timeout 30 "${container_name}" >/dev/null
      container_status="running"
    fi
  elif [[ ${container_status} == "running" ]]; then
    active_slicer_processes="$(
      docker exec "${container_name}" ps -eo pid=,stat=,comm=,args= 2>/dev/null \
        | awk '
            $2 !~ /^Z/ &&
            ($3 == "SlicerApp-real" ||
             $3 == "Slicer" ||
             ($3 == "ros2" &&
              ($0 ~ /launch slicer_ros2_module slicer\.launch\.py/ ||
               $0 ~ /launch dentobot_moveit_config simulation\.launch\.py/))) {
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
container_needs_recreate=false
if docker inspect "${container_name}" >/dev/null 2>&1; then
  container_runtime_user="$(
    docker inspect --format '{{.Config.User}}' "${container_name}"
  )"
  if [[ ${container_runtime_user} != "${host_uid}:${host_gid}" ]]; then
    container_needs_recreate=true
  fi
  if ! docker inspect --format '{{json .Mounts}}' "${container_name}" \
    | grep -Fq '"Destination":"/home/dentobot"'; then
    container_needs_recreate=true
  fi
else
  container_needs_recreate=true
fi
if [[ ${container_needs_recreate} == true ]]; then
  "${compose_command[@]}" up -d --force-recreate
else
  "${compose_command[@]}" up -d
fi
reclaim_bind_mount_ownership

container_runtime_user="$(
  docker inspect --format '{{.Config.User}}' "${container_name}"
)"
if [[ ${container_runtime_user} != "${host_uid}:${host_gid}" ]]; then
  printf '%s\n' \
    'The container is not running as the host workstation user.' \
    "Observed user: ${container_runtime_user:-<empty>}" \
    "Expected: ${host_uid}:${host_gid}." >&2
  exit 2
fi

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
docker exec "${container_name}" bash -lc '
  source /opt/ros/jazzy/setup.bash
  python3 -c "import moveit_configs_utils"
  command -v xacro >/dev/null
  cd /workspace/ros2_ws
  colcon build --symlink-install \
    --base-paths \
      /workspace/ros2_ws/src/DentoBot/dentobot_description \
      /workspace/ros2_ws/src/DentoBot/dentobot_moveit_config \
    --packages-select dentobot_description dentobot_moveit_config
'
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
  "Container user: ${host_uid}:${host_gid} (render gid ${render_gid})" \
  "Slicer home: ${slicer_home_dir}" \
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

x11_access_available() {
  xhost >/dev/null 2>&1
}

resolve_x11_authority() {
  local mutter_auth uid

  if x11_access_available; then
    return 0
  fi

  uid="$(id -u)"
  for mutter_auth in /run/user/"${uid}"/.mutter-Xwaylandauth.*; do
    if [[ -f ${mutter_auth} ]]; then
      XAUTHORITY="${mutter_auth}" x11_access_available && {
        export XAUTHORITY="${mutter_auth}"
        printf 'Using GNOME XWayland authority: %s\n' "${XAUTHORITY}"
        return 0
      }
    fi
  done

  printf '%s\n' \
    "Cannot open DISPLAY=${DISPLAY} for scoped xhost access." \
    'Run this launcher from the desktop session that owns that display.' \
    'On GNOME Wayland, use a terminal on the physical desktop or Chrome Remote Desktop.' \
    'If you are on CRD, open a terminal inside the CRD desktop and retry without exporting DISPLAY manually.' >&2
  return 1
}

if ! resolve_x11_authority; then
  exit 2
fi

cleanup_x11() {
  reclaim_bind_mount_ownership || true
  if [[ ${x11_access_granted} == true ]]; then
    xhost -SI:localuser:"${host_x11_user}" >/dev/null 2>&1 || true
  fi
}
trap cleanup_x11 EXIT INT TERM

printf 'Granting local user %s temporary access to DISPLAY=%s...\n' \
  "${host_x11_user}" "${DISPLAY}"
xhost +SI:localuser:"${host_x11_user}" >/dev/null
x11_access_granted=true

printf 'Opening 3D Slicer directly on DENTO Workflow.\n'
docker_exec_options=()
if [[ -t 0 && -t 1 ]]; then
  docker_exec_options=(-it)
fi
docker exec "${docker_exec_options[@]}" \
  -e DISPLAY="${DISPLAY}" \
  -e DENTOBOT_SLICER_MODULE_PATHS="${slicer_module_paths}" \
  "${container_name}" \
  bash -lc '
    set -euo pipefail
    # ROS/ament setup files are designed to tolerate unset tracing variables,
    # but Bash nounset turns their compatibility checks into fatal errors.
    # Disable nounset only while sourcing trusted ROS-generated overlays, then
    # restore strict mode for all DENTOBOT launcher logic below.
    set +u
    source /opt/ros/jazzy/setup.bash
    source /workspace/ros2_ws/install/setup.bash
    set -u
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

    stack_log=/tmp/dentobot-simulation-stack.log
    setsid ros2 launch dentobot_moveit_config simulation.launch.py >"${stack_log}" 2>&1 &
    stack_pid=$!
    stack_group_alive() {
      kill -0 -- "-${stack_pid}" >/dev/null 2>&1
    }
    cleanup_stack() {
      trap - EXIT INT TERM
      if stack_group_alive; then
        kill -INT -- "-${stack_pid}" >/dev/null 2>&1 || true
        for _attempt in $(seq 1 20); do
          stack_group_alive || break
          sleep 0.25
        done
      fi
      if stack_group_alive; then
        kill -TERM -- "-${stack_pid}" >/dev/null 2>&1 || true
        for _attempt in $(seq 1 20); do
          stack_group_alive || break
          sleep 0.25
        done
      fi
      if stack_group_alive; then
        kill -KILL -- "-${stack_pid}" >/dev/null 2>&1 || true
      fi
      wait "${stack_pid}" >/dev/null 2>&1 || true
    }
    trap cleanup_stack EXIT INT TERM

    stack_ready=false
    for _attempt in $(seq 1 60); do
      if ! kill -0 "${stack_pid}" >/dev/null 2>&1; then
        printf "%s\n" "DENTOBOT simulation stack exited during startup:" >&2
        tail -n 80 "${stack_log}" >&2 || true
        exit 2
      fi
      status="$(timeout 2s ros2 topic echo \
        /dentobot/simulation_status std_msgs/msg/String \
        --once --field data 2>/dev/null || true)"
      if [[ ${status} == *'"'"'"ready":true'"'"'* ]]; then
        stack_ready=true
        break
      fi
      sleep 0.5
    done
    if [[ ${stack_ready} != true ]]; then
      printf "%s\n" "DENTOBOT simulation stack was not ready within 30 seconds:" >&2
      tail -n 80 "${stack_log}" >&2 || true
      exit 2
    fi

    printf "%s\n" \
      "DENTOBOT simulation stack ready (description + one joint-state source + MoveIt)." \
      "Stack log: ${stack_log}"
    ros2 launch slicer_ros2_module slicer.launch.py \
      "slicer_args:=--no-splash --python-code '"'"'slicer.util.selectModule(\"DENTOWorkflow\")'"'"'"
  '
