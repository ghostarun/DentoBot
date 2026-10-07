#!/usr/bin/env bash

set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
repository_root="$(cd -- "${script_directory}/../.." && pwd -P)"
default_workspace_root="$(cd -- "${repository_root}/../../.." && pwd -P)"
workspace_root="${DENTOBOT_WORKSPACE_ROOT:-${default_workspace_root}}"
workspace_root="$(cd -- "${workspace_root}" && pwd -P)"
ros2_workspace_root="${workspace_root}/ros2_ws"
if [[ ${repository_root} != "${ros2_workspace_root}/"* ]]; then
  printf '%s\n' \
    "Repository checkout is outside the mounted ros2_ws directory: ${repository_root}" \
    "Workspace root: ${ros2_workspace_root}" >&2
  exit 2
fi
repository_relative_path="${repository_root#"${ros2_workspace_root}/"}"
container_repository_root="/workspace/ros2_ws/${repository_relative_path}"
workspace_config="${DENTOBOT_WORKSPACE_CONFIG:-${workspace_root}/.dentobot.env}"
compose_file="${repository_root}/Workspace/compose.yaml"
compose_override_file="${workspace_root}/compose.override.yaml"
container_name="dentobot-slicerros2"

backend_source="${container_repository_root}/Inference/src"
module_path="${container_repository_root}/DENTOWorkflow"
endoplanner_module_path="/workspace/data/SlicerEndoPlanner-main/PulpChamberOpenPlanning"
slicer_module_paths="${module_path}"
# Selected after DENTOBOT_BACKEND_DEVICE is resolved.
backend_dependency_probe=""
backend_dependency_label=""
check_only=false
use_installed_runtime=false
print_backend_python=false
diagnostic_no_spindle_collision=false
render_probe_case=""
choose_checkout=false
x11_access_granted=false

usage() {
  printf '%s\n' \
    "Usage: scripts/launch-dentoworkflow.bash [--check-only] [--diagnostic-no-spindle-collision]" \
    "" \
    "Without options, verify the dentobot Conda backend and open" \
    "3D Slicer with DENTO Workflow loaded from the repository source." \
    "" \
    "Machine configuration: ${workspace_config}" \
    "Template: ${repository_root}/Workspace/.dentobot.env.example" \
    "Graphics: DENTOBOT_GRAPHICS_MODE=auto|mesa|wslg|nvidia" \
    "" \
    "--use-installed-runtime" \
    "              Verify the runtime lock and reuse installed packages without rebuilding." \
    "--check-only  Verify Compose, the backend, and module files without" \
    "              opening a GUI." \
    "--print-backend-python" \
    "              Print the single configured backend interpreter path." \
    "--diagnostic-no-spindle-collision" \
    "              Experiment A only: omit the spindle-housing collision body." \
    "--render-probe CASE" \
    "              Open CASE (a DentoCase under the workspace data/ folder)," \
    "              measure 3D render throughput for 5 s, exit Slicer, and" \
    "              judge the graphics acceptance (renderer, display, >=60 FPS)." \
    "--choose-checkout" \
    "              List this repository's checkouts under ros2_ws (main first," \
    "              then newest commit first) and run the chosen one's launcher" \
    "              with the other options. Choosing main creates" \
    "              ros2_ws/src/DentoBot-main if needed and updates it from GitHub."
}

forward_args=()
for argument in "$@"; do
  if [[ ${argument} != "--choose-checkout" ]]; then
    forward_args+=("${argument}")
  fi
done

while (( $# > 0 )); do
  case "$1" in
    --use-installed-runtime)
      use_installed_runtime=true
      ;;
    --check-only)
      check_only=true
      ;;
    --print-backend-python)
      print_backend_python=true
      ;;
    --diagnostic-no-spindle-collision)
      diagnostic_no_spindle_collision=true
      ;;
    --render-probe)
      render_probe_case="${2:?--render-probe requires a DentoCase path}"
      shift
      ;;
    --choose-checkout)
      choose_checkout=true
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

if [[ ${use_installed_runtime} == true ]]; then
  python3 "${repository_root}/Workspace/scripts/workstation/runtime_sync.py" \
    --repo "${repository_root}"
  PYTHONPATH="${repository_root}/Workspace/scripts/workstation${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 - "${repository_root}" <<'PY_RUNTIME_OWNERS'
import json, os, sys
from pathlib import Path
import smoke_runtime
from runtime_preflight import parse_env_file, effective_config
repo = Path(sys.argv[1])
workspace = repo.parents[2]
lock = json.loads((repo / "Workspace/runtime-lock.json").read_text())
values, errors = parse_env_file(Path(os.environ.get("DENTOBOT_WORKSPACE_CONFIG", workspace / ".dentobot.env")))
if errors:
    raise SystemExit("Invalid workspace configuration")
config, _ = effective_config(values, dict(os.environ))
backend = Path(config["DENTOBOT_BACKEND_PYTHON"]).parent.parent.resolve()
smoke_runtime.assert_no_owners(container=False)
info = smoke_runtime.inspect_container()
if info.get("Running"):
    smoke_runtime.assert_no_owners(container=True)
smoke_runtime.validate_container(info, lock["image_id"], lock["image_name"], workspace,
                                 backend, os.getuid(), os.getgid(), allow_idle_running=True)
PY_RUNTIME_OWNERS
fi

# --- checkout selection and shared build hygiene ---
# All checkouts share ros2_ws/build and ros2_ws/install. A package build
# configured from another checkout makes CMake refuse to build and leaves that
# checkout's symlinked URDF/MoveIt files installed, so clear it first.
clear_stale_package_builds() {
  local checkout="$1" package cache source_home
  for package in dentobot_description dentobot_moveit_config; do
    cache="${ros2_workspace_root}/build/${package}/CMakeCache.txt"
    [[ -f ${cache} ]] || continue
    source_home="$(sed -n 's/^CMAKE_HOME_DIRECTORY:INTERNAL=//p' "${cache}")"
    [[ -n ${source_home} ]] || continue
    # Caches record container paths; compare them as host paths.
    source_home="${ros2_workspace_root}${source_home#/workspace/ros2_ws}"
    if [[ $(readlink -f -- "${source_home}") != "$(readlink -f -- "${checkout}/${package}")" ]]; then
      printf 'Rebuilding %s from %s (its build came from %s).\n' \
        "${package}" "${checkout}" "${source_home}"
      rm -rf -- "${ros2_workspace_root}/build/${package}" \
        "${ros2_workspace_root}/install/${package}"
    fi
  done
}

# The worktree on branch main, if one exists under ros2_ws.
main_branch_checkout() {
  git -C "${repository_root}" worktree list --porcelain | awk '
    /^worktree / { path = substr($0, 10) }
    $0 == "branch refs/heads/main" { print path; exit }'
}

print_checkout_row() {
  local index="$1" path="$2" extra="${3:-}" branch commit when subject changes markers
  branch="$(git -C "${path}" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  [[ ${branch} != "HEAD" && -n ${branch} ]] || branch="(detached)"
  IFS=$'\t' read -r commit when subject < <(
    git -C "${path}" log -1 --date=format:'%Y-%m-%d %H:%M' --format=$'%h\t%cd\t%s'
  )
  changes="$(git -C "${path}" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  markers=""
  [[ ${path} == "${repository_root}" ]] && markers+=" [current]"
  [[ -f ${path}/BRANCH_OBSOLETE.md ]] && markers+=" [retired]"
  (( changes > 0 )) && markers+=" [${changes} uncommitted]"
  printf '  %d) %s%s%s\n     %s  %s  %s\n     %s\n' \
    "${index}" "${branch}" "${markers}" "${extra}" "${when}" "${commit}" "${subject:0:72}" "${path}"
}

# Creates the main checkout on first use and fast-forwards it to origin/main
# when it is clean; otherwise it runs as it is and says why.
prepare_main_checkout() {
  local path="$1" upstream=""
  if git -C "${repository_root}" rev-parse -q --verify refs/remotes/origin/main >/dev/null; then
    upstream="origin/main"
  fi
  if [[ ! -e ${path} ]]; then
    if ! git -C "${repository_root}" rev-parse -q --verify refs/heads/main >/dev/null; then
      git -C "${repository_root}" branch -q --track main origin/main
    elif [[ -n ${upstream} ]] \
      && git -C "${repository_root}" merge-base --is-ancestor main "${upstream}"; then
      git -C "${repository_root}" branch -q -f main "${upstream}"
    fi
    printf 'Creating the main checkout at %s\n' "${path}"
    if ! git -C "${repository_root}" worktree add -q "${path}" main; then
      printf 'Could not create the main checkout (is main checked out outside ros2_ws?).\n' >&2
      exit 2
    fi
    return
  fi
  if [[ $(git -C "${path}" rev-parse --abbrev-ref HEAD 2>/dev/null) != "main" ]]; then
    printf '%s exists but is not on branch main.\n' "${path}" >&2
    exit 2
  fi
  [[ -n ${upstream} ]] || return 0
  if [[ -n $(git -C "${path}" status --porcelain) ]]; then
    printf 'main checkout has uncommitted changes; running it without updating.\n'
  elif ! git -C "${path}" merge -q --ff-only "${upstream}" 2>/dev/null; then
    printf 'main has commits not on %s; running it without updating.\n' "${upstream}"
  fi
}

# Lists this repository's runnable checkouts (git worktrees under ros2_ws,
# which is what the container mounts): main first, then newest commit first.
# Sets selected_checkout to the operator's choice (Enter keeps this checkout).
select_checkout() {
  local path stamp row index answer main_path behind extra
  local -a rows=() sorted=() choices=()
  printf 'Checking GitHub for the latest main...\n'
  if ! GIT_TERMINAL_PROMPT=0 timeout 20 \
    git -C "${repository_root}" fetch -q origin main 2>/dev/null; then
    printf '  (origin not reachable; showing the last fetched main)\n'
  fi
  main_path="$(main_branch_checkout)"
  if [[ -z ${main_path} || ${main_path} != "${ros2_workspace_root}/"* ]]; then
    main_path="${ros2_workspace_root}/src/DentoBot-main"
  fi
  while IFS= read -r path; do
    [[ ${path} == "${ros2_workspace_root}/"* && ${path} != "${main_path}" ]] || continue
    [[ -f ${path}/Workspace/scripts/launch-dentoworkflow.bash ]] || continue
    stamp="$(git -C "${path}" log -1 --format=%ct 2>/dev/null)" || continue
    rows+=("${stamp}"$'\t'"${path}")
  done < <(git -C "${repository_root}" worktree list --porcelain | sed -n 's/^worktree //p')
  if (( ${#rows[@]} > 0 )); then
    mapfile -t sorted < <(printf '%s\n' "${rows[@]}" | sort -t $'\t' -k1,1nr)
  fi
  printf 'DentoBot checkouts (main first, then newest commit first):\n'
  index=1
  choices=("${main_path}")
  if [[ -d ${main_path} ]]; then
    extra=""
    if behind="$(git -C "${main_path}" rev-list --count HEAD..origin/main 2>/dev/null)" \
      && (( behind > 0 )); then
      extra=" [${behind} behind GitHub main; updated on launch]"
    fi
    print_checkout_row 1 "${main_path}" "${extra}"
  else
    printf '  1) main [not checked out yet]\n     %s\n     will be created at %s\n' \
      "$(git -C "${repository_root}" log -1 --date=format:'%Y-%m-%d %H:%M' \
        --format='%cd  %h  %s' origin/main 2>/dev/null \
        || git -C "${repository_root}" log -1 --date=format:'%Y-%m-%d %H:%M' \
        --format='%cd  %h  %s' main)" "${main_path}"
  fi
  for row in "${sorted[@]}"; do
    path="${row#*$'\t'}"
    index=$((index + 1))
    choices+=("${path}")
    print_checkout_row "${index}" "${path}"
  done
  if ! read -r -p "Run which checkout? [1-${index}, Enter = current]: " answer; then
    printf '\nNo checkout chosen.\n' >&2
    exit 2
  fi
  if [[ -z ${answer} ]]; then
    selected_checkout="${repository_root}"
    return
  fi
  if [[ ! ${answer} =~ ^[0-9]+$ ]] || (( answer < 1 || answer > index )); then
    printf 'Not a listed checkout number: %s\n' "${answer}" >&2
    exit 2
  fi
  selected_checkout="${choices[answer - 1]}"
  if (( answer == 1 )); then
    prepare_main_checkout "${selected_checkout}"
    main_chosen=true
  fi
}
# --- end checkout selection ---

if [[ ${choose_checkout} == true ]]; then
  main_chosen=false
  select_checkout
  # Re-exec main even when it is this checkout: the update may change this script.
  if [[ ${selected_checkout} != "${repository_root}" || ${main_chosen} == true ]]; then
    printf 'Launching checkout %s\n' "${selected_checkout}"
    # Older checkouts' launchers lack the stale-build check; do it for them.
    if [[ ${use_installed_runtime} == false ]]; then
      clear_stale_package_builds "${selected_checkout}"
    fi
    exec bash "${selected_checkout}/Workspace/scripts/launch-dentoworkflow.bash" "${forward_args[@]}"
  fi
  printf 'Launching the current checkout %s\n' "${repository_root}"
fi

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
graphics_mode="${DENTOBOT_GRAPHICS_MODE:-auto}"
run_artifact_root="${DENTOBOT_RUN_ARTIFACT_ROOT:-/workspace/data/dentobot-runs}"
totalseg_home_dir="${DENTOBOT_TOTALSEG_HOME_DIR:-/workspace/data/model-cache/totalsegmentator}"
host_uid="$(id -u)"
host_gid="$(id -g)"
host_x11_user="$(id -un)"
slicer_home_dir="${workspace_root}/slicer-home"
legacy_slicer_user_dir="${workspace_root}/slicer-user"
compose_wslg_file="${repository_root}/Workspace/compose.wslg.yaml"
compose_nvidia_file="${repository_root}/Workspace/compose.nvidia.yaml"
compose_cuda_file="${repository_root}/Workspace/compose.cuda.yaml"

host_is_wsl() {
  # WSL2 kernels report "microsoft" in osrelease; WSLg adds /dev/dxg and /mnt/wslg.
  local osrelease=""
  if [[ -r /proc/sys/kernel/osrelease ]]; then
    osrelease="$(< /proc/sys/kernel/osrelease)"
  fi
  [[ ${osrelease,,} == *microsoft* || -e /dev/dxg || -d /mnt/wslg ]]
}

if [[ ${graphics_mode} == "auto" ]]; then
  if [[ -c ${render_device} ]]; then
    graphics_mode="mesa"
  elif [[ -e /dev/dxg || -d /mnt/wslg ]]; then
    graphics_mode="wslg"
  else
    graphics_mode="missing"
  fi
fi
if [[ ${graphics_mode} != "mesa" && ${graphics_mode} != "wslg" && \
      ${graphics_mode} != "nvidia" ]]; then
  printf '%s\n' \
    "Unsupported DENTOBOT_GRAPHICS_MODE=${graphics_mode}." \
    'Use mesa, wslg, nvidia (native Ubuntu NVIDIA), or auto.' >&2
  exit 2
fi
# Under WSL the NVIDIA prerequisite checks can all pass while Slicer still
# renders in software (no WSLg overlay), so refuse instead of degrading silently.
if [[ ${graphics_mode} == "nvidia" ]] && host_is_wsl; then
  printf '%s\n' \
    'DENTOBOT_GRAPHICS_MODE=nvidia is for native Ubuntu NVIDIA hosts only; this host is WSL.' \
    'Set DENTOBOT_GRAPHICS_MODE=wslg (or auto) in .dentobot.env.' \
    'For NVIDIA inference on WSL, keep wslg graphics and set DENTOBOT_BACKEND_DEVICE=cuda:0.' >&2
  exit 2
fi
render_probe_container_case=""
render_probe_dir=""
if [[ -n ${render_probe_case} ]]; then
  if [[ ${check_only} == true ]]; then
    printf '%s\n' '--render-probe opens Slicer; it cannot be combined with --check-only.' >&2
    exit 2
  fi
  if [[ ! -f ${render_probe_case} ]]; then
    printf 'Render-probe case file is missing: %s\n' "${render_probe_case}" >&2
    exit 2
  fi
  render_probe_case="$(readlink -f -- "${render_probe_case}")"
  render_probe_data_root="$(readlink -f -- "${workspace_root}/data")"
  if [[ ${render_probe_case} != "${render_probe_data_root}/"* ]]; then
    printf '%s\n' \
      "Render-probe case must be under ${render_probe_data_root}/ (mounted as /workspace/data):" \
      "${render_probe_case}" >&2
    exit 2
  fi
  render_probe_container_case="/workspace/data/${render_probe_case#"${render_probe_data_root}/"}"
  render_probe_dir="${render_probe_data_root}/dentobot-runs/render-probe-$(date -u +%Y%m%dT%H%M%SZ)"
fi
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
    "Use launch-native-windows-steps0-5.ps1 for the legacy Windows Steps 0-5 adapter." >&2
  exit 2
fi
if [[ ${backend_device} == "cpu" ]]; then
  backend_dependency_label="Python 3.12 CPU/OpenVINO segmentation stack"
  backend_dependency_probe='import importlib.metadata as m; import sys; expected={"dentobot-inference":"0.2.0","numpy":"2.2.6","nibabel":"5.4.2","torch":"2.10.0+cpu","torchvision":"0.25.0+cpu","TotalSegmentator":"2.16.0","nnunetv2":"2.8.1","openvino":"2026.2.0","pytest":"8.4.2"}; assert sys.version_info[:2] == (3, 12); actual={name:m.version(name) for name in expected}; assert actual == expected, actual'
elif [[ ${backend_device} == "cuda:0" ]]; then
  backend_dependency_label="Python 3.10 CUDA 13.0 (cu130) segmentation stack"
  backend_dependency_probe='import importlib.metadata as m; import sys; import torch; expected={"dentobot-inference":"0.2.0","numpy":"2.2.6","nibabel":"5.4.2","torch":"2.10.0+cu130","torchvision":"0.25.0+cu130","TotalSegmentator":"2.16.0","nnunetv2":"2.8.1","pytest":"8.4.2"}; assert sys.version_info[:2] == (3, 10); actual={name:m.version(name) for name in expected}; assert actual == expected, actual; assert torch.cuda.is_available(), "torch.cuda.is_available() is False"; assert torch.cuda.device_count() >= 1'
else
  printf '%s\n' \
    "DENTOBOT_BACKEND_DEVICE must be cpu or cuda:0 (got: ${backend_device})." \
    'CPU uses the Ubuntu OpenVINO pin; cuda:0 uses the Bridge C cu130 pin.' >&2
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
if [[ ${graphics_mode} == "mesa" ]]; then
  if [[ ! -c ${render_device} ]]; then
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
else
  render_gid="${host_gid}"
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

check_nvidia_graphics_prerequisites() {
  local gpu_summary docker_runtimes
  if ! command -v timeout >/dev/null 2>&1; then
    printf '%s\n' 'Native Ubuntu NVIDIA graphics checks require the timeout command.' >&2
    exit 2
  fi
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    printf '%s\n' \
      'Native Ubuntu NVIDIA graphics mode requires the host nvidia-smi command.' \
      'Install the host NVIDIA driver, or select Mesa/auto.' >&2
    exit 2
  fi
  if ! gpu_summary="$(timeout 10s nvidia-smi \
    --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null)" || \
      [[ -z ${gpu_summary//[[:space:]]/} ]]; then
    printf '%s\n' \
      'Host NVIDIA driver is unavailable or not responding.' \
      'Run nvidia-smi on the host and resolve the driver before selecting DENTOBOT_GRAPHICS_MODE=nvidia.' >&2
    exit 2
  fi
  if ! docker_runtimes="$(timeout 10s docker info \
    --format '{{range $name, $runtime := .Runtimes}}{{println $name}}{{end}}' \
    2>/dev/null)"; then
    printf '%s\n' \
      'Could not read Docker runtimes within 10 seconds.' \
      'Confirm the Docker daemon is healthy, then retry.' >&2
    exit 2
  fi
  if ! grep -Fxq 'nvidia' <<<"${docker_runtimes}"; then
    printf '%s\n' \
      'Docker does not list the NVIDIA runtime.' \
      'Configure NVIDIA Container Toolkit for this Docker daemon, then retry.' >&2
    exit 2
  fi
  printf '%s\n' 'Host NVIDIA GPUs (name, driver, memory):' "${gpu_summary}"
}

if ! command -v docker >/dev/null 2>&1; then
  printf 'Required command is unavailable: docker\n' >&2
  exit 2
fi
ensure_docker_daemon
if [[ ${graphics_mode} == "nvidia" ]]; then
  check_nvidia_graphics_prerequisites
fi
if [[ ! -x ${backend_python} ]]; then
  printf '%s\n' \
    "The dentobot Conda environment has no Python: ${backend_python}" \
    "Install the repository-pinned ${backend_dependency_label}." >&2
  exit 2
fi
if [[ ${graphics_mode} == "mesa" && ! -c ${render_device} ]]; then
  printf '%s\n' \
    "Required Intel GPU render node is unavailable: ${render_device}" \
    'DENTO Workflow is not launched with an implicit software-rendering fallback.' >&2
  exit 2
fi
if [[ ${graphics_mode} == "wslg" ]]; then
  if [[ ! -f ${compose_wslg_file} ]]; then
    printf 'WSLg Compose override is missing: %s\n' "${compose_wslg_file}" >&2
    exit 2
  fi
  printf '%s\n' \
    'Graphics mode: wslg (no /dev/dri render node).' \
    'GUI is for functional checks only; treat rendering like CRD/llvmpipe.'
fi
if [[ ${graphics_mode} == "nvidia" ]]; then
  if [[ ! -f ${compose_nvidia_file} ]]; then
    printf 'NVIDIA graphics Compose override is missing: %s\n' \
      "${compose_nvidia_file}" >&2
    exit 2
  fi
  if [[ ! -f ${compose_cuda_file} ]]; then
    printf 'NVIDIA GPU Compose override is missing: %s\n' \
      "${compose_cuda_file}" >&2
    exit 2
  fi
  printf '%s\n' \
    'Graphics mode: nvidia (explicit native Ubuntu NVIDIA OpenGL).' \
    'Container device visibility will be checked; this does not verify OpenGL acceleration.'
fi

if ! "${backend_python}" -c "${backend_dependency_probe}" \
  >/dev/null 2>&1; then
  printf '%s\n' \
    'The dentobot Conda environment is incomplete or has unexpected versions.' \
    "Expected the repository-pinned ${backend_dependency_label}." >&2
  "${backend_python}" -c "${backend_dependency_probe}" >&2 || true
  exit 2
fi

if [[ ${backend_device} == "cuda:0" && ! -f ${compose_cuda_file} ]]; then
  printf 'CUDA Compose override is missing: %s\n' "${compose_cuda_file}" >&2
  exit 2
fi

compose_command=(
  docker compose
  --project-directory "${workspace_root}"
  -f "${compose_file}"
)
# Reconcile the current named container's project, not renamed rollback
# containers that retain the old default project's Compose labels.
compose_project="$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "${container_name}" 2>/dev/null || true)"
if [[ ${compose_project} =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
  compose_command+=(--project-name "${compose_project}")
fi
if [[ ${graphics_mode} == "wslg" ]]; then
  compose_command+=(-f "${compose_wslg_file}")
fi
if [[ ${graphics_mode} == "nvidia" ]]; then
  compose_command+=(-f "${compose_nvidia_file}" -f "${compose_cuda_file}")
elif [[ ${backend_device} == "cuda:0" ]]; then
  compose_command+=(-f "${compose_cuda_file}")
fi
if [[ ${backend_device} == "cuda:0" ]]; then
  printf '%s\n' \
    'Backend device: cuda:0 (NVIDIA GPU requested for container inference).'
fi
if [[ -f ${compose_override_file} ]]; then
  compose_command+=(-f "${compose_override_file}")
fi
# compose.yaml still interpolates DENTOBOT_RENDER_DEVICE before the WSLg
# !reset clears devices; keep a concrete placeholder when the node is absent.
export DENTOBOT_RENDER_DEVICE="${render_device}"
export DENTOBOT_GRAPHICS_MODE="${graphics_mode}"
"${compose_command[@]}" config -q
if [[ ${use_installed_runtime} == false ]]; then
  prepare_host_uid_runtime
fi

if [[ ${use_installed_runtime} == false ]] && docker inspect "${container_name}" >/dev/null 2>&1; then
  container_status="$(docker inspect --format '{{.State.Status}}' "${container_name}")"
  if [[ ${container_status} == "paused" ]]; then
    printf 'Unpausing %s...\n' "${container_name}"
    docker unpause "${container_name}" >/dev/null
    container_status="running"
  fi
  if [[ ${check_only} == false && ${backend_device} != "cuda:0" ]]; then
    if [[ ${container_status} == "running" ]]; then
      printf '%s\n' \
        "Restarting the dedicated ${container_name} container for a clean GUI session..." \
        'Existing DENTOBOT Slicer, ROS, MoveIt, and test processes will be stopped.' \
        'Save open Slicer scenes first; unsaved in-container UI state cannot be recovered.'
      docker restart -t 30 "${container_name}" >/dev/null
      container_status="running"
    fi
  elif [[ ${check_only} == true && ${container_status} == "running" ]]; then
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
container_has_nvidia_gpu_request() {
  docker inspect --format '{{json .HostConfig.DeviceRequests}}' "${container_name}" \
    | grep -Fq '"Driver":"nvidia"' || return 1
  if [[ ${graphics_mode} == "nvidia" ]]; then
    docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${container_name}" \
      | grep -Eq '^NVIDIA_DRIVER_CAPABILITIES=.*graphics' || return 1
  fi
}

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
  # Compose also recreates on any service-config change; this guards a
  # container created outside this Compose project without the GPU request.
  if [[ ${backend_device} == "cuda:0" || ${graphics_mode} == "nvidia" ]] \
    && ! container_has_nvidia_gpu_request; then
    printf '%s\n' \
      'Recreating the container so NVIDIA GPU device requests are applied...'
    container_needs_recreate=true
  fi
else
  container_needs_recreate=true
fi
if [[ ${use_installed_runtime} == true ]]; then
  if [[ ${container_needs_recreate} == true ]]; then
    printf 'Pinned runtime container configuration differs; explicit setup is required.\n' >&2
    exit 2
  fi
  # Compose project labels can still belong to a renamed rollback container.
  # Use the already validated runtime by name without reconciling that project.
  if [[ "$(docker inspect --format '{{.State.Running}}' "${container_name}")" != true ]]; then
    docker start "${container_name}" >/dev/null
  fi
elif [[ ${container_needs_recreate} == true ]]; then
  "${compose_command[@]}" up -d --force-recreate
else
  "${compose_command[@]}" up -d
fi
if [[ ${use_installed_runtime} == false ]]; then
  reclaim_bind_mount_ownership
fi

if [[ ${graphics_mode} == "nvidia" ]]; then
  if ! container_nvidia_devices="$(timeout 10s docker exec \
    "${container_name}" nvidia-smi -L 2>/dev/null)" || \
      [[ -z ${container_nvidia_devices//[[:space:]]/} ]]; then
    printf '%s\n' \
      'NVIDIA graphics was selected, but the container cannot access a GPU through its NVIDIA runtime.' \
      'Review NVIDIA Container Toolkit configuration and the container device request.' >&2
    exit 2
  fi
  printf '%s\n' \
    'Container NVIDIA GPU devices are visible:' \
    "${container_nvidia_devices}" \
    'This check does not verify Slicer OpenGL acceleration.'
fi

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
  -e PYTHONNOUSERSITE=1 \
  -e TOTALSEG_HOME_DIR="${totalseg_home_dir}" \
  "${container_name}" \
  "${backend_python}" -c "${backend_dependency_probe}; print('Conda ${backend_device} segmentation dependency check passed.')"
docker exec "${container_name}" mkdir -p "${run_artifact_root}"
docker exec "${container_name}" test -d "${totalseg_home_dir}"
docker exec \
  -e PYTHONPATH="${backend_source}" \
  -e PYTHONNOUSERSITE=1 \
  -e TOTALSEG_HOME_DIR="${totalseg_home_dir}" \
  "${container_name}" \
  "${backend_python}" -m dentobot_inference health \
  --json \
  --require-device "${backend_device}"
docker exec "${container_name}" test -f "${module_path}/DENTOWorkflow.py"
docker exec "${container_name}" test -f \
  "${module_path}/Resources/UI/DENTOWorkflow.ui"
if docker exec "${container_name}" test -f \
  "${endoplanner_module_path}/PulpChamberOpenPlanning.py"; then
  slicer_module_paths+=" ${endoplanner_module_path}"
fi
if [[ ${graphics_mode} == "mesa" ]]; then
  docker exec "${container_name}" test -c "${render_device}"
fi
if [[ ${use_installed_runtime} == true ]]; then
  printf 'Using checksum-verified installed ROS/native packages; no rebuild.\n'
else
  clear_stale_package_builds "${repository_root}"
  docker exec \
    -e "DENTOBOT_CONTAINER_REPOSITORY_ROOT=${container_repository_root}" \
    "${container_name}" bash -lc '
    # A failed build must stop the launch, not run Slicer on stale packages.
    set -euo pipefail
    set +u
    source /opt/ros/jazzy/setup.bash
    set -u
    python3 -c "import moveit_configs_utils"
    command -v xacro >/dev/null
    cd /workspace/ros2_ws
    colcon build --symlink-install \
      --base-paths \
        "${DENTOBOT_CONTAINER_REPOSITORY_ROOT}/dentobot_description" \
        "${DENTOBOT_CONTAINER_REPOSITORY_ROOT}/dentobot_moveit_config" \
        /workspace/ros2_ws/src/slicer_ros2_module \
      --packages-select dentobot_description dentobot_moveit_config slicer_ros2_module \
      --cmake-args -DSLICER_ROS2_INSTALL_SCRIPTED_TESTS=OFF
    test -d /workspace/ros2_ws/install/slicer_ros2_module
    # Symlink installs do not remove modules omitted by a later configure.
    rm -f \
      /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules/ROS2Tests.py \
      /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules/ROS2Tests.pyc
  '
fi

container_slicer_priority="$(
  docker exec "${container_name}" printenv SLICER_BACKGROUND_THREAD_PRIORITY
)"
if [[ ${container_slicer_priority} != "0" ]]; then
  printf '%s\n' \
    'The container does not preserve normal Slicer process priority.' \
    'Expected SLICER_BACKGROUND_THREAD_PRIORITY=0.' >&2
  exit 2
fi

git_source_identity() {
  local repo="$1" branch commit changes
  branch="$(git -C "${repo}" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  commit="$(git -C "${repo}" rev-parse --short HEAD 2>/dev/null || true)"
  if [[ -z ${commit} ]]; then
    printf '%s (not a git checkout)' "${repo}"
    return
  fi
  changes="$(git -C "${repo}" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  printf '%s (%s @ %s, %s uncommitted)' "${repo}" "${branch:-detached}" "${commit}" "${changes}"
}

printf '%s\n' \
  "Source checkout: $(git_source_identity "${repository_root}")" \
  "SlicerROS2 source: $(git_source_identity "${ros2_workspace_root}/src/slicer_ros2_module")" \
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
  "Graphics mode: ${graphics_mode}" \
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
  if [[ ${graphics_mode} == "wslg" ]]; then
    export DISPLAY=:0
    printf 'DISPLAY was empty; defaulting to DISPLAY=:0 for WSLg.\n'
  else
    printf '%s\n' \
      'DISPLAY is empty. Run this launcher from an Ubuntu desktop terminal, not SSH.' >&2
    exit 2
  fi
fi

grant_x11_with_xhost=false
if command -v xhost >/dev/null 2>&1; then
  grant_x11_with_xhost=true
elif [[ ${graphics_mode} != "wslg" ]]; then
  printf 'Required GUI command is unavailable: xhost\n' >&2
  exit 2
else
  printf '%s\n' \
    'xhost is not installed; continuing with WSLg default X11 access.'
fi

x11_access_available() {
  if [[ ${grant_x11_with_xhost} != true ]]; then
    return 0
  fi
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

  if [[ ${graphics_mode} == "wslg" ]]; then
    printf '%s\n' \
      "xhost could not verify DISPLAY=${DISPLAY}; continuing for WSLg."
    return 0
  fi

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
  if [[ ${x11_access_granted} == true && ${grant_x11_with_xhost} == true ]]; then
    xhost -SI:localuser:"${host_x11_user}" >/dev/null 2>&1 || true
  fi
}
trap cleanup_x11 EXIT INT TERM

if [[ ${grant_x11_with_xhost} == true ]]; then
  printf 'Granting local user %s temporary access to DISPLAY=%s...\n' \
    "${host_x11_user}" "${DISPLAY}"
  xhost +SI:localuser:"${host_x11_user}" >/dev/null
  x11_access_granted=true
fi

printf 'Opening 3D Slicer directly on DENTO Workflow.\n'
docker_exec_options=()
if [[ -t 0 && -t 1 ]]; then
  docker_exec_options=(-it)
fi
watchdog_metadata_pair="$(
  python3 "${repository_root}/Workspace/scripts/dentobot-resource-watchdog.py" \
    --metadata-once --source-root "${repository_root}" --slicer-version 5.10
)"
IFS=$'\t' read -r DENTOBOT_WATCHDOG_SESSION_ID DENTOBOT_WATCHDOG_METADATA \
  <<<"${watchdog_metadata_pair}"
if [[ -z ${DENTOBOT_WATCHDOG_SESSION_ID} || -z ${DENTOBOT_WATCHDOG_METADATA} ]]; then
  printf '%s\n' 'Could not prepare the DENTO watchdog session metadata.' >&2
  exit 2
fi
docker_exec_env=(
  -e "DISPLAY=${DISPLAY}"
  -e "DENTOBOT_BACKEND_SOURCE=${backend_source}"
  -e "DENTOBOT_CONTAINER_REPOSITORY_ROOT=${container_repository_root}"
  -e "DENTOBOT_WATCHDOG_SESSION_ID=${DENTOBOT_WATCHDOG_SESSION_ID}"
  -e "DENTOBOT_WATCHDOG_METADATA=${DENTOBOT_WATCHDOG_METADATA}"
  -e "DENTOBOT_SLICER_MODULE_PATHS=${slicer_module_paths}"
  -e "DENTOBOT_DIAGNOSTIC_NO_SPINDLE_COLLISION=${diagnostic_no_spindle_collision}"
  -e "PYTHONNOUSERSITE=1"
)
if [[ ${graphics_mode} == "wslg" ]]; then
  docker_exec_env+=(
    -e "WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-0}"
    -e "XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/mnt/wslg/runtime-dir}"
    -e "PULSE_SERVER=${PULSE_SERVER:-unix:/mnt/wslg/PulseServer}"
  )
fi
if [[ -n ${XAUTHORITY:-} ]]; then
  docker_exec_env+=(-e "XAUTHORITY=${XAUTHORITY}")
fi
if [[ -n ${render_probe_case} ]]; then
  # Captured, non-interactive run: the probe exits Slicer when it finishes.
  docker_exec_options=()
  docker_exec_env+=(
    -e "DENTOBOT_PERF_CASE=${render_probe_container_case}"
    -e "DENTOBOT_RENDER_PROBE_SCRIPT=${container_repository_root}/Testing/run_dentobot_render_frame_probe.py"
  )
fi
container_launch_script='
    set -euo pipefail
    # ROS/ament setup files are designed to tolerate unset tracing variables,
    # but Bash nounset turns their compatibility checks into fatal errors.
    # Disable nounset only while sourcing trusted ROS-generated overlays, then
    # restore strict mode for all DENTOBOT launcher logic below.
    set +u
    source /opt/ros/jazzy/setup.bash
    source /workspace/ros2_ws/install/setup.bash
    set -u
    export PYTHONPATH="${DENTOBOT_BACKEND_SOURCE}${PYTHONPATH:+:${PYTHONPATH}}"
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

    if [[ -n ${DENTOBOT_RENDER_PROBE_SCRIPT:-} ]]; then
      exec bash "${DENTOBOT_CONTAINER_REPOSITORY_ROOT}/Workspace/scripts/dentobot-simulation-slicer-handoff.bash" \
        --stack-log /tmp/dentobot-simulation-stack.log \
        -- \
        ros2 launch slicer_ros2_module slicer.launch.py \
        "slicer_args:=--no-splash --python-script ${DENTOBOT_RENDER_PROBE_SCRIPT}"
    fi
    exec bash "${DENTOBOT_CONTAINER_REPOSITORY_ROOT}/Workspace/scripts/dentobot-simulation-slicer-handoff.bash" \
      --stack-log /tmp/dentobot-simulation-stack.log \
      -- \
      ros2 launch slicer_ros2_module slicer.launch.py \
      "slicer_args:=--no-splash --python-code '"'"'slicer.util.selectModule(\"DENTOWorkflow\")'"'"'"
  '
if [[ -z ${render_probe_case} ]]; then
  docker exec "${docker_exec_options[@]}" \
    "${docker_exec_env[@]}" \
    "${container_name}" \
    bash -lc "${container_launch_script}"
else
  mkdir -p "${render_probe_dir}"
  printf 'Render probe: %s (graphics %s); evidence in %s\n' \
    "${render_probe_container_case}" "${graphics_mode}" "${render_probe_dir}"
  set +e
  docker exec "${docker_exec_env[@]}" "${container_name}" \
    bash -lc "${container_launch_script}" 2>&1 \
    | tee "${render_probe_dir}/slicer-probe.log"
  render_probe_launch_status=${PIPESTATUS[0]}
  set -e
  python3 "${repository_root}/Testing/evaluate_render_probe.py" \
    --graphics-mode "${graphics_mode}" \
    --launch-status "${render_probe_launch_status}" \
    --case "${render_probe_container_case}" \
    --source-head "$(git -C "${repository_root}" rev-parse HEAD 2>/dev/null || echo unknown)" \
    --output "${render_probe_dir}/verdict.json" \
    "${render_probe_dir}/slicer-probe.log"
fi
