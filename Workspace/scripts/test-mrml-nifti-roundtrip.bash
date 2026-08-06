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
  docker exec \
    -e DENTOBOT_BRIDGE_B_MODE="${mode}" \
    -e DENTOBOT_BRIDGE_B_DIR="${container_artifact_directory}" \
    dentobot-slicerros2 \
    bash -lc \
    'source /opt/ros/jazzy/setup.bash
     source /workspace/ros2_ws/install/setup.bash
     xvfb-run -a /usr/bin/python3 \
       /workspace/ros2_ws/src/DentoBot/Testing/run_mrml_nifti_roundtrip_test.py'
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
