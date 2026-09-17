#!/usr/bin/env bash
set -eo pipefail

readonly case_path="/workspace/data/Slicer_Saved/SampleStudy1/FDI31/c1-gatea-fdi31-20260915-r4/FDI31-step5c.dentocase"
readonly case_sha256="6235772e2d14d74b5417d42ed8a5e0cc160df82c77efd3014f589dd264113d83"
readonly p3_input="${DENTOBOT_P3_REVALIDATION_INPUT:-}"
readonly p4_input="${DENTOBOT_P4_INSERTION_INPUT:-}"
readonly p5_input="${DENTOBOT_P5_APPROACH_INPUT:-}"
readonly p3_input_sha256="8853f5208a87368d2611fd9c0a9737fe6b73b4da43de6851f4a428adee3f734c"
readonly p4_input_sha256="ec6ad4febcf202de3469303f53ceb4d8056f14d2d6e03272a467ba5938fce362"
readonly p5_input_sha256="3cc1759d1dc5042748d729d5e2a1ae784a94a60d33cb7c8350695b321492bc72"
readonly readiness_only="${DENTOBOT_P3_READINESS_ONLY:-0}"

if [[ -n ${p3_input} && ( -n ${p4_input} || -n ${p5_input} ) ]] || [[ -n ${p4_input} && -n ${p5_input} ]]; then
  echo "P3 revalidation, P4 insertion, and P5 approach modes are mutually exclusive." >&2
  exit 64
elif [[ -n ${p5_input} ]]; then
  readonly mode="p5"
  readonly diagnostic_input="${p5_input}"
  readonly diagnostic_input_sha256="${p5_input_sha256}"
  readonly run_dir="${DENTOBOT_P5_OUTPUT_DIR:?set a fresh P5 container output directory}"
elif [[ -n ${p4_input} ]]; then
  readonly mode="p4"
  readonly diagnostic_input="${p4_input}"
  readonly diagnostic_input_sha256="${p4_input_sha256}"
  readonly run_dir="${DENTOBOT_P4_OUTPUT_DIR:?set a fresh P4 container output directory}"
else
  readonly mode="p3"
  readonly diagnostic_input="${p3_input:?set the locked r4 endpoint_candidates.json input}"
  readonly diagnostic_input_sha256="${p3_input_sha256}"
  readonly run_dir="${DENTOBOT_P3_OUTPUT_DIR:?set a fresh P3 container output directory}"
fi

source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash
set -u
export ROS_DOMAIN_ID=73 ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
export LD_LIBRARY_PATH="/workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-loadable-modules:/workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="/workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules:${PYTHONPATH:-}"

test -f "${case_path}"
test "$(sha256sum "${case_path}" | cut -d ' ' -f 1)" = "${case_sha256}"
test -f "${diagnostic_input}"
test "$(sha256sum "${diagnostic_input}" | cut -d ' ' -f 1)" = "${diagnostic_input_sha256}"
test ! -e "${run_dir}"
! ps -eo args | grep -E "Slicer|ros2 launch|dentobot_moveit" | grep -v grep
mkdir -p "${run_dir}"

stack_pid=""
cleanup() {
  if [[ -n ${stack_pid} ]]; then
    kill -TERM -- "-${stack_pid}" >/dev/null 2>&1 || true
    wait "${stack_pid}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

setsid ros2 launch dentobot_moveit_config simulation.launch.py >"${run_dir}/simulation-stack.log" 2>&1 &
stack_pid=$!
printf '%s\n' "${stack_pid}" >"${run_dir}/stack-process-group.txt"

ready=false
for attempt in $(seq 1 60); do
  status="$(timeout 2s ros2 topic echo /dentobot/simulation_status std_msgs/msg/String --once --field data 2>/dev/null || true)"
  printf 'attempt=%s status=%s\n' "${attempt}" "${status}" >>"${run_dir}/readiness.log"
  if [[ ${status} == *'"ready":true'* ]]; then
    ready=true
    break
  fi
  sleep 0.5
done
if [[ ${ready} != true ]]; then
  tail -n 100 "${run_dir}/simulation-stack.log"
  exit 2
fi
printf 'C1_%s_STACK_READINESS_PASS\n' "${mode^^}"
if [[ ${mode} != p3 && ${readiness_only} != 0 ]]; then
  echo "DENTOBOT_P3_READINESS_ONLY is not valid for ${mode^^} mode." >&2
  exit 64
fi
if [[ ${mode} == p3 && ${readiness_only} == 1 ]]; then
  exit 0
fi

export DENTOBOT_EXACT_CASE="${case_path}"
export DENTOBOT_EXPECTED_FDI=31
if [[ ${mode} == p4 || ${mode} == p5 ]]; then
  readonly native_source="/workspace/ros2_ws/src/DentoBot/dentobot_moveit_config/src/collision_guard.cpp"
  readonly native_binary="/workspace/ros2_ws/install/dentobot_moveit_config/lib/dentobot_moveit_config/collision_guard"
  test -f "${native_source}"
  test -x "${native_binary}"
  if [[ ${mode} == p4 ]]; then
    export DENTOBOT_P4_INSERTION_INPUT="${diagnostic_input}"
    export DENTOBOT_P4_NATIVE_SOURCE_SHA256="$(sha256sum "${native_source}" | cut -d ' ' -f 1)"
    export DENTOBOT_P4_NATIVE_BINARY_SHA256="$(sha256sum "${native_binary}" | cut -d ' ' -f 1)"
    export DENTOBOT_DIAGNOSTIC_OUTPUT="${run_dir}/insertion_branches.json"
    unset DENTOBOT_ENDPOINT_ONLY DENTOBOT_P3_REVALIDATION_INPUT DENTOBOT_P5_APPROACH_INPUT
    readonly slicer_timeout="2700s"
  else
    export DENTOBOT_P5_APPROACH_INPUT="${diagnostic_input}"
    export DENTOBOT_P5_NATIVE_SOURCE_SHA256="$(sha256sum "${native_source}" | cut -d ' ' -f 1)"
    export DENTOBOT_P5_NATIVE_BINARY_SHA256="$(sha256sum "${native_binary}" | cut -d ' ' -f 1)"
    export DENTOBOT_DIAGNOSTIC_OUTPUT="${run_dir}/approach_branches.json"
    unset DENTOBOT_ENDPOINT_ONLY DENTOBOT_P3_REVALIDATION_INPUT DENTOBOT_P4_INSERTION_INPUT
    readonly slicer_timeout="900s"
  fi
else
  export DENTOBOT_ENDPOINT_ONLY=1 DENTOBOT_P3_REVALIDATION_INPUT="${diagnostic_input}"
  export DENTOBOT_DIAGNOSTIC_OUTPUT="${run_dir}/endpoint_candidates.json"
  unset DENTOBOT_P4_INSERTION_INPUT DENTOBOT_P5_APPROACH_INPUT
  readonly slicer_timeout="420s"
fi
timeout "${slicer_timeout}" xvfb-run -a /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer \
  --no-splash \
  --additional-module-paths /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-loadable-modules \
  --additional-module-paths /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules \
  --additional-module-paths /workspace/ros2_ws/src/DentoBot/DENTOWorkflow \
  --python-script /workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_step65_exact_case_smoke.py \
  2>&1 | tee "${run_dir}/runtime.log"
