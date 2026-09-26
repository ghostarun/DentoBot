#!/usr/bin/env bash
set -euo pipefail

readonly container_name="dentobot-slicerros2"
readonly checkout_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly expected_branch="feature/step6-workflow-renovation-20260925"
readonly expected_head="45a38d9"
readonly case_source="${DENTOBOT_MANUAL_JOG_CASE_SOURCE:-}"
readonly rejection_plan="${DENTOBOT_MANUAL_JOG_REJECTION_PLAN_JSON:-}"
readonly evidence_root="${DENTOBOT_VERIFICATION_ROOT:-/tmp/dentobot-verification}"

test "$(git -C "$checkout_root" branch --show-current)" = "$expected_branch"
test "$(git -C "$checkout_root" rev-parse --short HEAD)" = "$expected_head"
host_runtime_processes="$(ps -eo pid=,comm= | awk '$2 == "Slicer" || $2 == "SlicerApp-real" || $2 == "ros2" || $2 == "move_group" || $2 == "robot_state_pub" {print}')"
if [[ -n $host_runtime_processes ]]; then
  printf 'Existing host Slicer/ROS process found; refusing to compete with it:\n%s\n' "$host_runtime_processes" >&2
  exit 2
fi

if [[ -z $case_source ]]; then
  printf '%s\n' \
    'Set DENTOBOT_MANUAL_JOG_CASE_SOURCE to a container-visible fixture path.' >&2
  exit 64
fi

if [[ "$(docker inspect --format '{{.State.Status}}' "$container_name")" != running ]]; then
  printf 'Container %s is not running.\n' "$container_name" >&2
  exit 2
fi
container_metadata="$(docker inspect --format '{{.Id}}|{{.Image}}|{{.Config.Image}}' "$container_name")"
IFS='|' read -r container_id image_id image_reference <<<"$container_metadata"

mount_table="$(docker inspect --format '{{range .Mounts}}{{.Source}}|{{.Destination}}{{"\n"}}{{end}}' "$container_name")"
container_root=""
best_mount_length=-1
while IFS='|' read -r mount_source mount_destination; do
  [[ -n $mount_source && -n $mount_destination ]] || continue
  mount_source="$(realpath -e -- "$mount_source" 2>/dev/null)" || continue
  if [[ $checkout_root == "$mount_source" || $checkout_root == "$mount_source/"* ]]; then
    if (( ${#mount_source} > best_mount_length )); then
      relative_root="$(realpath --relative-to="$mount_source" "$checkout_root")"
      container_root="$mount_destination/$relative_root"
      best_mount_length=${#mount_source}
    fi
  fi
done <<<"$mount_table"

if [[ -z $container_root ]]; then
  printf 'The running container does not bind-mount this renovation checkout: %s\n' "$checkout_root" >&2
  exit 2
fi
container_root="$(docker exec "$container_name" realpath -e -- "$container_root")"

run_id="manual-jog-$(date -u +%Y%m%dT%H%M%SZ)-$$"
host_evidence="$evidence_root/$run_id"
container_evidence="/tmp/dentobot-verification/$run_id"
mkdir -p -- "$host_evidence"
: >"$host_evidence/source-sha256.txt"

source_files=(
  DENTOWorkflow/Resources/Python/DENTOROS2Bridge.py
  DENTOWorkflow/Resources/Python/DENTORobotSimulationPanel.py
  DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py
  DENTOWorkflow/Resources/Python/dentobot_workflow/logic_robot.py
  DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot.py
  DENTOWorkflow/Resources/Python/dentobot_workflow/widget_robot_shell.py
  Testing/run_dentobot_manual_jog_headless.bash
  Testing/run_dentobot_manual_jog_headless.py
)
for relative_path in "${source_files[@]}"; do
  host_hash="$(sha256sum "$checkout_root/$relative_path" | cut -d ' ' -f 1)"
  container_hash="$(docker exec "$container_name" sha256sum "$container_root/$relative_path" | awk '{print $1}')"
  if [[ $host_hash != "$container_hash" ]]; then
    printf 'Mounted source differs from this checkout: %s\n' "$relative_path" >&2
    exit 2
  fi
  printf '%s  %s\n' "$host_hash" "$relative_path" >>"$host_evidence/source-sha256.txt"
done
case_sha256="$(docker exec "$container_name" sha256sum "$case_source" | awk '{print $1}')"
guard_binary="/workspace/ros2_ws/install/dentobot_moveit_config/lib/dentobot_moveit_config/collision_guard"
build_identity="$(docker exec "$container_name" sha256sum "$guard_binary" /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer)"
printf '%s\n' "$build_identity" >"$host_evidence/build-identity.txt"
rejection_plan_sha256=""
if [[ -n $rejection_plan ]]; then
  rejection_plan_sha256="$(docker exec "$container_name" sha256sum "$rejection_plan" | awk '{print $1}')"
fi
runtime_started_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

host_log="$host_evidence/runtime.log"
rejection_planned=0
[[ -z $rejection_plan ]] || rejection_planned=1
docker_exec_args=(
  exec -i
  -e "DENTOBOT_MANUAL_JOG_CASE_SOURCE=$case_source"
  -e "DENTOBOT_MANUAL_JOG_EVIDENCE_DIR=$container_evidence"
)
if [[ -n $rejection_plan ]]; then
  docker_exec_args+=(-e "DENTOBOT_MANUAL_JOG_REJECTION_PLAN_JSON=$rejection_plan")
fi
set +e
docker "${docker_exec_args[@]}" \
  "$container_name" bash -s -- "$container_root" "$container_evidence" <<'REMOTE' 2>&1 | tee "$host_log"
set -eo pipefail
source_root="$1"
evidence_dir="$2"
slicer="/opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer"
stack_pid=""

cleanup() {
  [[ -n $stack_pid ]] || return 0
  kill -TERM -- "-$stack_pid" >/dev/null 2>&1 || true
  wait "$stack_pid" >/dev/null 2>&1 || true
  for _ in {1..20}; do
    if ! kill -0 -- "-$stack_pid" 2>/dev/null; then
      printf 'DENTOBOT_MANUAL_JOG_STACK_TEARDOWN_PASS\n'
      stack_pid=""
      return 0
    fi
    sleep 0.25
  done
  kill -KILL -- "-$stack_pid" >/dev/null 2>&1 || true
  sleep 0.2
  if kill -0 -- "-$stack_pid" 2>/dev/null; then
    printf 'DENTOBOT_MANUAL_JOG_STACK_TEARDOWN_FAIL group=%s\n' "$stack_pid" >&2
    return 1
  fi
  printf 'DENTOBOT_MANUAL_JOG_STACK_TEARDOWN_PASS forced=true\n'
  stack_pid=""
}
trap 'cleanup || exit 70' EXIT

test -x "$slicer"
test -d /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10
test -f "$source_root/Testing/run_dentobot_manual_jog_headless.py"
test -f "$DENTOBOT_MANUAL_JOG_CASE_SOURCE"
if [[ -n ${DENTOBOT_MANUAL_JOG_REJECTION_PLAN_JSON:-} ]]; then
  test -f "$DENTOBOT_MANUAL_JOG_REJECTION_PLAN_JSON"
fi

active_processes="$(ps -eo stat=,comm=,args= | awk '$1 !~ /^Z/ && $2 != "awk" && ($2 == "Slicer" || $2 == "SlicerApp-real" || $2 == "move_group" || $2 == "robot_state_pub" || $0 ~ /ros2 launch dentobot_moveit_config simulation.launch.py/) {print}')"
if [[ -n $active_processes ]]; then
  printf 'Existing simulation process found; refusing to replace it:\n%s\n' "$active_processes" >&2
  exit 2
fi

test ! -e "$evidence_dir"
mkdir -p -- /tmp/dentobot-verification
mkdir -- "$evidence_dir"
source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash
set -u
export ROS_DOMAIN_ID=73 ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
export LD_LIBRARY_PATH="/workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-loadable-modules:/workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="/workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules:${PYTHONPATH:-}"
set -e

printf 'ROS stack command: setsid ros2 launch dentobot_moveit_config simulation.launch.py\n'
setsid ros2 launch dentobot_moveit_config simulation.launch.py >"$evidence_dir/simulation-stack.log" 2>&1 &
stack_pid=$!
printf '%s\n' "$stack_pid" >"$evidence_dir/stack-process-group.txt"

ready=false
for attempt in $(seq 1 60); do
  status="$(timeout 2s ros2 topic echo /dentobot/simulation_status std_msgs/msg/String --once --field data 2>/dev/null || true)"
  printf 'attempt=%s status=%s\n' "$attempt" "$status" >>"$evidence_dir/readiness.log"
  if [[ $status == *'"ready":true'* ]]; then
    ready=true
    break
  fi
  sleep 0.5
done
if [[ $ready != true ]]; then
  tail -n 100 "$evidence_dir/simulation-stack.log"
  printf 'DENTOBOT_MANUAL_JOG_STACK_READINESS_FAIL\n' >&2
  exit 2
fi
printf 'DENTOBOT_MANUAL_JOG_STACK_READINESS_PASS\n'

slicer_command=(
  timeout 300s xvfb-run -a "$slicer"
  --no-splash
  --additional-module-paths /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-loadable-modules
  --additional-module-paths /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules
  --additional-module-paths "$source_root/DENTOWorkflow"
  --python-script "$source_root/Testing/run_dentobot_manual_jog_headless.py"
)
printf 'Slicer command:'
printf ' %q' "${slicer_command[@]}"
printf '\n'
"${slicer_command[@]}" 2>&1 | tee "$evidence_dir/slicer.log"
REMOTE
runtime_exit=$?
set -e

set +e
docker cp "$container_name:$container_evidence" "$host_evidence/container-artifacts" >/dev/null 2>&1
copy_exit=$?
set -e

set +e
python3 - "$host_evidence" "$runtime_exit" "$copy_exit" "$rejection_planned" "$case_source" "$container_root" "$container_evidence" "$case_sha256" "$rejection_plan" "$rejection_plan_sha256" "$container_id" "$image_id" "$image_reference" "$runtime_started_utc" <<'PY'
import json
import pathlib
import sys

directory = pathlib.Path(sys.argv[1])
runtime_exit, copy_exit, rejection_planned = map(int, sys.argv[2:5])
case_source, container_root, container_evidence = sys.argv[5:8]
case_sha256, rejection_plan, rejection_plan_sha256 = sys.argv[8:11]
container_id, image_id, image_reference = sys.argv[11:14]
runtime_started_utc = sys.argv[14]
log_path = directory / "runtime.log"
log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
source_hashes = {}
for line in (directory / "source-sha256.txt").read_text(encoding="utf-8").splitlines():
    digest, relative = line.split(None, 1)
    source_hashes[relative] = digest
build_hashes = {}
for line in (directory / "build-identity.txt").read_text(encoding="utf-8").splitlines():
    digest, path = line.split(None, 1)
    build_hashes[path] = digest
teardown = "DENTOBOT_MANUAL_JOG_STACK_TEARDOWN_PASS" in log
artifact_root = directory / "container-artifacts"
report_path = artifact_root / "manual_jog_headless.json"
try:
    manifest = json.loads(report_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    manifest = None

def image_paths(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from image_paths(child)
    elif isinstance(value, list):
        for child in value:
            yield from image_paths(child)
    elif isinstance(value, str) and value.lower().endswith(".png"):
        yield value

required_screenshots = {
    "pre-jog-context-ui.png",
    "pre-jog-context-viewport.png",
    "accepted-result-ui.png",
    "accepted-result-viewport.png",
    "unknown-result-ui.png",
    "unknown-result-viewport.png",
}
if rejection_planned:
    required_screenshots.update({"rejected-result-ui.png", "rejected-result-viewport.png"})

referenced_screenshots = []
existing_references = set()
if manifest is not None:
    for value in image_paths(manifest.get("screenshots", {})):
        relative = pathlib.PurePosixPath(value)
        if relative.is_absolute() or ".." in relative.parts:
            continue
        image = (artifact_root / pathlib.Path(*relative.parts)).resolve()
        try:
            image.relative_to(artifact_root.resolve())
        except ValueError:
            continue
        if image.is_file():
            referenced_screenshots.append(image)
            existing_references.add(image.name)

missing_screenshots = sorted(required_screenshots - existing_references)
all_pngs = sorted(
    str(path.resolve())
    for path in artifact_root.rglob("*.png")
) if artifact_root.is_dir() else []
all_json = sorted(
    str(path.resolve())
    for path in artifact_root.rglob("*.json")
) if artifact_root.is_dir() else []

scenarios = manifest.get("scenarios", {}) if manifest is not None else {}
scenario_status = {
    name: value.get("status", "MISSING") if isinstance(value, dict) else "MISSING"
    for name, value in scenarios.items()
}
accepted_ok = scenario_status.get("accepted") == "PASS"
unavailable_ok = scenario_status.get("unavailable") == "PASS"
rejected_ok = scenario_status.get("rejected") == "PASS"
rejected_not_run = scenario_status.get("rejected") == "NOT_RUN"
runner_status = manifest.get("status") if manifest is not None else None
pass_marker = "DENTOBOT_MANUAL_JOG_HEADLESS_PASS"
partial_marker = "DENTOBOT_MANUAL_JOG_HEADLESS_PARTIAL"
marker = pass_marker if pass_marker in log else partial_marker if partial_marker in log else None
common_ok = (
    runtime_exit == 0
    and copy_exit == 0
    and teardown
    and manifest is not None
    and accepted_ok
    and unavailable_ok
    and not missing_screenshots
)
if common_ok and rejection_planned and rejected_ok and runner_status == "PASS" and marker == pass_marker:
    status = "PASS"
    final_exit = 0
elif common_ok and not rejection_planned and rejected_not_run and runner_status == "PARTIAL" and marker == partial_marker:
    status = "PARTIAL"
    final_exit = 2
else:
    status = "FAIL"
    final_exit = 1

logged_failure = next(
    (
        line
        for line in log.splitlines()
        if line.lstrip().lower().startswith(("fatal:", "mkdir:", "bash:", "sh:", "existing simulation process found", "existing host slicer/ros process found"))
        or "_FAIL" in line
        or "traceback" in line.lower()
        or "error:" in line.lower()
    ),
    None,
)
slicer_command = next(
    (line.partition(": ")[2] for line in log.splitlines() if line.startswith("Slicer command:")),
    None,
)
if logged_failure:
    first_failure = logged_failure
elif missing_screenshots:
    first_failure = "Missing required runner screenshots: " + ", ".join(missing_screenshots)
elif rejection_planned and not rejected_ok:
    first_failure = "The requested rejected scenario did not pass."
elif not rejection_planned and not rejected_not_run:
    first_failure = "The runner did not mark the unconfigured rejected scenario NOT_RUN."
elif status == "PARTIAL":
    first_failure = "Raw rejection NOT_RUN because no reviewed in-limit rejection plan was supplied."
elif status == "FAIL":
    first_failure = "Runner manifest, accepted/unavailable scenario, runtime, or teardown gate failed."
else:
    first_failure = None

result = {
    "check_id": "runtime.manual_jog_headless",
    "status": status,
    "launcher": "Testing/run_dentobot_manual_jog_headless.bash",
    "command": slicer_command,
    "simulation_stack_command": "setsid ros2 launch dentobot_moveit_config simulation.launch.py",
    "runtime_started_utc": runtime_started_utc,
    "container_name": "dentobot-slicerros2",
    "container_id": container_id,
    "image_id": image_id,
    "image_reference": image_reference,
    "ros_domain_id": 73,
    "case_source": case_source,
    "case_sha256": case_sha256,
    "rejection_plan": rejection_plan or None,
    "rejection_plan_sha256": rejection_plan_sha256 or None,
    "source_sha256_manifest": str((directory / "source-sha256.txt").resolve()),
    "source_sha256": source_hashes,
    "build_identity_file": str((directory / "build-identity.txt").resolve()),
    "build_identity_sha256": build_hashes,
    "container_source_root": container_root,
    "source_branch": "feature/step6-workflow-renovation-20260925",
    "source_head": "45a38d9",
    "container_evidence_directory": container_evidence,
    "runtime_exit_code": runtime_exit,
    "artifact_copy_exit_code": copy_exit,
    "runner_status": runner_status,
    "scenario_status": scenario_status,
    "runner_marker": marker,
    "first_failure": first_failure,
    "evidence_directory": str(directory),
    "runner_report": str(report_path.resolve()),
    "json_artifacts": all_json,
    "screenshot_artifacts": all_pngs,
    "required_screenshots": sorted(required_screenshots),
    "missing_screenshots": missing_screenshots,
    "stack_teardown": "verified" if teardown else "not_verified",
    "final_exit_code": final_exit,
}
(directory / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
raise SystemExit(final_exit)
PY
result_exit=$?
set -e

printf 'Evidence: %s\n' "$host_evidence"
exit "$result_exit"
