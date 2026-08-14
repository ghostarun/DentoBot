#!/usr/bin/env bash

set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
repository_root="$(cd -- "${script_directory}/../.." && pwd -P)"
default_workspace_root="$(cd -- "${repository_root}/../../.." && pwd -P)"
workspace_root="${DENTOBOT_WORKSPACE_ROOT:-${default_workspace_root}}"
backend_python="${DENTOBOT_BACKEND_PYTHON:-$(
  "${script_directory}/launch-dentoworkflow.bash" --print-backend-python
)}"
artifact_root="${workspace_root}/data/test-artifacts"
inference_source="/workspace/ros2_ws/src/DentoBot/Inference/src"
test_timeout_seconds="${DENTOBOT_SLICER_TEST_TIMEOUT_SECONDS:-180}"
active_xvfb_pid=""
active_xvfb_directory=""

if [[ ! ${test_timeout_seconds} =~ ^[1-9][0-9]*$ ]]; then
  printf 'DENTOBOT_SLICER_TEST_TIMEOUT_SECONDS must be a positive integer: %s\n' \
    "${test_timeout_seconds}" >&2
  exit 2
fi

cleanup_xvfb() {
  if [[ -n ${active_xvfb_pid} ]]; then
    kill "${active_xvfb_pid}" >/dev/null 2>&1 || true
    wait "${active_xvfb_pid}" >/dev/null 2>&1 || true
    active_xvfb_pid=""
  fi
  if [[ -n ${active_xvfb_directory} && -d ${active_xvfb_directory} ]]; then
    rm -f -- \
      "${active_xvfb_directory}/display" \
      "${active_xvfb_directory}/xvfb.log"
    rmdir -- "${active_xvfb_directory}" 2>/dev/null || true
    active_xvfb_directory=""
  fi
}
trap cleanup_xvfb EXIT INT TERM

container_backend_python="$(
  docker exec dentobot-slicerros2 printenv DENTOBOT_BACKEND_PYTHON 2>/dev/null || true
)"
if [[ ${container_backend_python} != "${backend_python}" ]]; then
  printf '%s\n' \
    'The running container does not match the launcher backend configuration.' \
    'Save and close Slicer, then recreate it with scripts/launch-dentoworkflow.bash.' >&2
  exit 2
fi

if ! docker exec dentobot-slicerros2 test -x "${backend_python}"; then
  printf '%s\n' \
    "Prepare the dentobot Conda backend at ${backend_python} with NumPy 2.2.6 and NiBabel 5.4.2." >&2
  exit 2
fi

mkdir -p "${artifact_root}"
host_artifact_directory="$(mktemp -d "${artifact_root}/bridge-b-XXXXXX")"
artifact_name="$(basename "${host_artifact_directory}")"
container_artifact_directory="/workspace/data/test-artifacts/${artifact_name}"

run_slicer_phase() {
  local mode="$1"
  local display_number=""
  local phase_status=0

  active_xvfb_directory="$(mktemp -d /tmp/dentobot-xvfb-XXXXXX)"
  Xvfb \
    -displayfd 3 \
    -screen 0 1280x1024x24 \
    -nolisten tcp \
    3>"${active_xvfb_directory}/display" \
    2>"${active_xvfb_directory}/xvfb.log" &
  active_xvfb_pid=$!

  for _ in {1..50}; do
    if [[ -s ${active_xvfb_directory}/display ]]; then
      display_number="$(<"${active_xvfb_directory}/display")"
      break
    fi
    if ! kill -0 "${active_xvfb_pid}" 2>/dev/null; then
      break
    fi
    sleep 0.1
  done
  if [[ -z ${display_number} ]]; then
    printf 'Xvfb failed to allocate a display for the %s phase.\n' "${mode}" >&2
    sed -n '1,80p' "${active_xvfb_directory}/xvfb.log" >&2 || true
    cleanup_xvfb
    return 2
  fi

  set +e
  DISPLAY=":${display_number}" timeout \
    --signal=TERM \
    --kill-after=30s \
    "$((test_timeout_seconds + 45))s" \
    docker exec \
    -e DISPLAY=":${display_number}" \
    -e DENTOBOT_BRIDGE_B_MODE="${mode}" \
    -e DENTOBOT_BRIDGE_B_DIR="${container_artifact_directory}" \
    -e DENTOBOT_SLICER_TEST_TIMEOUT_SECONDS="${test_timeout_seconds}" \
    dentobot-slicerros2 \
    bash -lc \
    'source /opt/ros/jazzy/setup.bash
     source /workspace/ros2_ws/install/setup.bash
     exec timeout --signal=TERM --kill-after=30s \
       "${DENTOBOT_SLICER_TEST_TIMEOUT_SECONDS}s" \
       /usr/bin/python3 \
       /workspace/ros2_ws/src/DentoBot/Testing/run_mrml_nifti_roundtrip_test.py'
  phase_status=$?
  set -e

  cleanup_xvfb
  if (( phase_status == 124 )); then
    printf 'Slicer %s phase exceeded the %s-second timeout.\n' \
      "${mode}" "${test_timeout_seconds}" >&2
  fi
  return "${phase_status}"
}

run_slicer_phase export

docker exec \
  -e PYTHONPATH="${inference_source}" \
  dentobot-slicerros2 \
  "${backend_python}" \
  -m dentobot_inference roundtrip \
  --input "${container_artifact_directory}/input.nii.gz" \
  --output "${container_artifact_directory}/roundtrip.nii.gz" \
  --result-json "${container_artifact_directory}/result.json" \
  --run-id "${artifact_name}"

run_slicer_phase validate

printf 'DENTOBOT_BRIDGE_B_ARTIFACT_DIR=%s\n' "${host_artifact_directory}"
