# Step 6 recorded headed automation workflow

**Owner:** `S6-LIVE-01`; case restore overlaps `S6-REUSABLE-CASE-SETUP`.

**Use:** repeatable agent runbook and source for a later README/operator manual.

**Last exercised:** 2026-09-27 on `feature/step6-workflow-renovation-20260925`.

**Canonical gates:** [verification protocol](../AGENTIC_VERIFICATION_PROTOCOL.md),
[verification matrix](../../../Testing/verification_matrix.json) profile
`step6-headed-review`, [renovation plan](STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md),
and the active backlog/TASKS contracts. A matrix entry or this runbook does not
grant a future Slicer/ROS execution. Use the currently authorized scope and
serialize the container, ROS domain, Slicer process and display.

This is a **simulation-only, Xvfb-headed** check of the production DENTO Workflow
widgets. The video records the whole display; the runner writes itemized JSON
and state-matched UI/viewport screenshots. It can connect ROS/MoveIt and submit
at most one in-limit 0.1° J1 guarded jog when `DENTOBOT_HEADED_ALLOW_JOG=1` and
native provenance passes. It never saves the source case, plans, previews or
controls hardware. An explicit `DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT=1`
opt-in adds a zero-displacement Base acceptance and current-pose Task Home
acceptance through production owners. An Xvfb recording is not
Tarun's normal-window usability verdict.

**28 September integration checkpoint:** The same bounded runner also accepts
`DENTOBOT_HEADED_PROVENANCE_MODE=integration` only for the exact reviewed
`DentoBot-step6-5.10-integration` host/container roots and branch
`integration/step6-5.10-reviewed-20260927`. The default remains the original
renovation checkout. `DENTOBOT_HEADED_DRAFT_ONLY=1` requires an unconfirmed
task, exact native preflight, and no jog or Base/Home acceptance opt-in; it
connects, captures Check Draft State, then intentionally reports `PARTIAL`
with later actions `NOT_RUN`. Set those two variables explicitly in the
wrapper/container environment when selecting this indexed
`runtime.step6_integration_taskless_draft` checkpoint. Each invocation needs
a new run directory so earlier raw logs are never overwritten. The final
full-campaign runner and positive-chain fixture are still pending; this
extension does not add planner or preview calls.

The same bounded run can opt into
`DENTOBOT_HEADED_INVALID_DRAFT_REVIEW=1`. It selects a single overstep from
the *currently displayed* reviewed J1–J5 limit only when the mechanical
numeric control can represent it. It checks invalid-state evidence,
disabled Guarded Jog, unchanged accepted state and no route authority, then
restores the draft before any later valid jog. If no such gap exists it
records `NOT_RUN` and stops without motion; it never substitutes a hardcoded
joint value. `DENTOBOT_HEADED_RECORD_REOPEN=1` requires the accepted-jog opt-in
and then calls `Testing/step6_historical_record_probe.py` through the production
export/import/event-step owners. It verifies the event-bearing JSON/report,
accepted J1–J5 and unchanged route/preview authority. The 28 September bounded
headed retry passed those functional items with a current taskless case; its
video remains partial because Slicer exited 1 at shutdown under `S6-U-01`.
The positive full-chain fixture and final complete campaign remain pending.
The headed screenshot helper now resets horizontal scrolling before each
capture and records control/viewport dimensions and scroll positions. A
control wider than the viewport is flagged as a limitation; intersection
alone is not a responsive-layout acceptance. The Manual Jog actions were
split into two shorter rows in source, pending headed visual measurement.

## 1. Freeze the run contract

Record the chat session name, date/time zone, task/plan gate, exact checkout,
branch/HEAD/dirty status, current reviewed `.dentocase` and its SHA-256, and
whether this run includes the guarded jog. Do not use the parallel
`DentoBot-performance-5.12` checkout or reuse an old case merely for a green
result. Stop if another Slicer/ROS owner is active in `dentobot-slicerros2`.
The commands below show the original renovation checkout profile. The
integration checkpoint uses the exact alternate roots and branch stated
above and must pass `DENTOBOT_HEADED_PROVENANCE_MODE=integration` into Slicer.
The runner does not read Git inside the container because a worktree's `.git`
pointer resolves to a host-only path.

From the host, set the **new run's** inputs:

```bash
CHECKOUT=/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-renovation
CASE_REL=Slicer_Saved/SampleStudy1/SEPT24/REVIEWED_CURRENT_CASE.dentocase
CASE_HOST=/home/light-tarun/dentobot/data/$CASE_REL
DISPLAY_ID=:98
JOG_GATE=0  # change to 1 only for the separately authorized one-jog check
BASE_HOME_ACCEPT_GATE=0  # change to 1 only for the bounded Base/Home trial
cd "$CHECKOUT"
git branch --show-current
git rev-parse HEAD
git status --short
sha256sum "$CASE_HOST"
```

The `CASE_REL` line is a placeholder, **not** a selected fixture. Verify the
package is current, reviewed and loadable before spending a full runtime. Keep
the source `.dentocase` read-only and preserve the first integrity failure.

## 2. Run the smallest source checks

Use the matrix dependencies that apply to the changed source, then the focused
recorder/runner checks. Luna verification workers are read-only on stable files;
Sol reviews the results and controls runtime/acceptance.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider \
  Testing/test_record_slicer_screen.py Testing/test_step6_headed_review_source.py
PYTHONPYCACHEPREFIX=/tmp/dentobot-step6-headed-pycache python3 -m py_compile \
  Testing/record_slicer_screen.py Testing/run_dentobot_step6_headed_review.py \
  Testing/test_record_slicer_screen.py Testing/test_step6_headed_review_source.py
python3 -m json.tool Testing/verification_matrix.json > /dev/null
git diff --check
```

These checks prove only source and manifest behavior. The 27 September stable
readback passed 12 focused tests, compilation, JSON parse and diff check.

## 3. Build and bind the exact native guard

If the native package changed or binary provenance cannot be established,
build **only** `dentobot_moveit_config` into an isolated overlay. Do not use the
shared workspace install as evidence for this checkout. The container must
mount `/home/light-tarun/dentobot/ros2_ws` at `/workspace/ros2_ws` and data
at `/workspace/data`.

```bash
docker exec dentobot-slicerros2 bash -lc '
  source /opt/ros/jazzy/setup.bash
  source /workspace/ros2_ws/install/setup.bash
  cd /workspace/ros2_ws
  colcon --log-base /tmp/dentobot-step6-renovation-log build \
    --base-paths src/DentoBot-step6-renovation/dentobot_moveit_config \
    --packages-select dentobot_moveit_config \
    --build-base /tmp/dentobot-step6-renovation-build \
    --install-base /tmp/dentobot-step6-renovation-install --symlink-install
'
NATIVE_SOURCE_SHA=$(sha256sum "$CHECKOUT/dentobot_moveit_config/src/collision_guard.cpp" | awk '{print $1}')
NATIVE_BINARY_SHA=$(docker exec dentobot-slicerros2 sha256sum \
  /tmp/dentobot-step6-renovation-install/dentobot_moveit_config/lib/dentobot_moveit_config/collision_guard | awk '{print $1}')
```

The runner independently checks both hashes and that ament selected
`/tmp/dentobot-step6-renovation-install/dentobot_moveit_config`. The exact
27 September build completed one package; its hashes belong only to that run.

## 4. Launch one recorded headed run

Create a fresh private directory under `data/dentobot-runs`. Start one
isolated Xvfb display. The host recorder starts **before** the runtime command
and finalizes after it exits. Its `--command` exit status is the checklist
exit status; a partial video may still be valuable evidence. The following
wrapper is the reproducible form of the 27 September temporary launcher.
Save it outside the checkout so it does not change the reviewed source hash.

```bash
cat > /tmp/dentobot-step6-headed-run.sh <<'HOST'
#!/usr/bin/env bash
set -euo pipefail
checkout=/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-renovation
test "$(git -C "$checkout" rev-parse --show-toplevel)" = "$checkout"
test "$(git -C "$checkout" branch --show-current)" = feature/step6-workflow-renovation-20260925
head_commit=$(git -C "$checkout" rev-parse HEAD)
status_hash=$(git -C "$checkout" status --porcelain=v1 | sha256sum | awk '{print $1}')
case_hash=$(sha256sum "$CASE_HOST" | awk '{print $1}')
run_name=$(basename "$RUN_DIR")
docker exec -i \
  -e DISPLAY="$DISPLAY_ID" \
  -e DENTOBOT_HEADED_CASE_SOURCE="/workspace/data/$CASE_REL" \
  -e DENTOBOT_HEADED_CASE_SHA256="$case_hash" \
  -e DENTOBOT_HEADED_EVIDENCE_DIR="/workspace/data/dentobot-runs/$run_name/evidence" \
  -e DENTOBOT_HEADED_ALLOW_JOG="$JOG_GATE" \
  -e DENTOBOT_HEADED_ALLOW_BASE_HOME_ACCEPT="$BASE_HOME_ACCEPT_GATE" \
  -e DENTOBOT_HEADED_NATIVE_SOURCE_SHA256="$NATIVE_SOURCE_SHA" \
  -e DENTOBOT_HEADED_NATIVE_BINARY_SHA256="$NATIVE_BINARY_SHA" \
  -e DENTOBOT_HEADED_NATIVE_PACKAGE_PREFIX=/tmp/dentobot-step6-renovation-install/dentobot_moveit_config \
  -e DENTOBOT_HEADED_GIT_HEAD="$head_commit" \
  -e DENTOBOT_HEADED_GIT_BRANCH=feature/step6-workflow-renovation-20260925 \
  -e DENTOBOT_HEADED_GIT_STATUS_SHA256="$status_hash" \
  -e DENTOBOT_HEADED_HOST_CHECKOUT_ROOT="$checkout" \
dentobot-slicerros2 bash -s <<'CONTAINER'
set -eo pipefail
source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash
source /tmp/dentobot-step6-renovation-install/setup.bash
set -u
export ROS_DOMAIN_ID=73 ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET QT_X11_NO_MITSHM=1
export LD_LIBRARY_PATH="/workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-loadable-modules:/workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="/workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules:${PYTHONPATH:-}"
evidence_dir=$DENTOBOT_HEADED_EVIDENCE_DIR
mkdir -p "$evidence_dir"
chmod 700 "$evidence_dir"
test "$(sha256sum "$DENTOBOT_HEADED_CASE_SOURCE" | awk '{print $1}')" = "$DENTOBOT_HEADED_CASE_SHA256"
active=$(ps -eo stat=,comm=,args= | awk '$1 !~ /^Z/ && $2 != "awk" && ($2 == "Slicer" || $2 == "SlicerApp-real" || $2 == "move_group" || $2 == "collision_guard" || $0 ~ /ros2 launch dentobot_moveit_config simulation.launch.py/) {print}')
if [[ -n "$active" ]]; then printf 'Other runtime owner active:\n%s\n' "$active" >&2; exit 2; fi
test "$(ros2 pkg prefix dentobot_moveit_config)" = /tmp/dentobot-step6-renovation-install/dentobot_moveit_config
stack_pid=''
cleanup() {
  if [[ -n "$stack_pid" ]]; then
    kill -TERM -- "-$stack_pid" 2>/dev/null || true
    wait "$stack_pid" 2>/dev/null || true
    if kill -0 -- "-$stack_pid" 2>/dev/null; then kill -KILL -- "-$stack_pid" 2>/dev/null || true; fi
  fi
}
trap cleanup EXIT
setsid ros2 launch dentobot_moveit_config simulation.launch.py >"$evidence_dir/simulation-stack.log" 2>&1 &
stack_pid=$!
printf '%s\n' "$stack_pid" >"$evidence_dir/stack-process-group.txt"
ready=false
for attempt in $(seq 1 60); do
  status=$(timeout 2s ros2 topic echo /dentobot/simulation_status std_msgs/msg/String --once --field data 2>/dev/null || true)
  printf 'attempt=%s status=%s\n' "$attempt" "$status" >>"$evidence_dir/readiness.log"
  if [[ "$status" == *'"ready":true'* ]]; then ready=true; break; fi
  sleep 0.5
done
if [[ "$ready" != true ]]; then printf 'Simulation stack not ready\n' >&2; exit 2; fi
timeout 600s /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer --no-splash \
  --additional-module-paths /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-loadable-modules \
  --additional-module-paths /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules \
  --additional-module-paths /workspace/ros2_ws/src/DentoBot-step6-renovation/DENTOWorkflow \
  --python-script /workspace/ros2_ws/src/DentoBot-step6-renovation/Testing/run_dentobot_step6_headed_review.py \
  >"$evidence_dir/slicer.log" 2>&1
CONTAINER
HOST
chmod 700 /tmp/dentobot-step6-headed-run.sh
```

Then run the following block in a dedicated host shell, with the variables
from steps 1 and 3 still set:

```bash
set -eo pipefail
mkdir -p /home/light-tarun/dentobot/data/dentobot-runs
RUN_DIR=$(mktemp -d /home/light-tarun/dentobot/data/dentobot-runs/step6-headed-XXXXXXXX)
chmod 700 "$RUN_DIR"
export CASE_REL CASE_HOST DISPLAY_ID JOG_GATE BASE_HOME_ACCEPT_GATE NATIVE_SOURCE_SHA NATIVE_BINARY_SHA RUN_DIR
Xvfb "$DISPLAY_ID" -screen 0 1600x900x24 -nolisten tcp -ac &
XVFB_PID=$!
trap 'kill "$XVFB_PID" 2>/dev/null || true; wait "$XVFB_PID" 2>/dev/null || true' EXIT
DISPLAY="$DISPLAY_ID" xdpyinfo >/dev/null
set +e
python3 Testing/record_slicer_screen.py --display "$DISPLAY_ID" \
  --output "$RUN_DIR/video/whole-run.mkv" --command -- \
  /tmp/dentobot-step6-headed-run.sh
RUN_STATUS=$?
set -e
kill "$XVFB_PID" 2>/dev/null || true
wait "$XVFB_PID" 2>/dev/null || true
trap - EXIT
printf 'checklist/recording exit status: %s\n' "$RUN_STATUS"
exit "$RUN_STATUS"
```

Use the required host/container permissions for Docker and Xvfb. If Xvfb,
case-hash comparison, native prefix or another-owner check fails, stop before
Slicer. After the command, verify the wrapper's owned stack and Xvfb have
exited; never kill an unrelated checkout's process.

## 5. Read the checklist before interpreting the video

The runner writes `evidence/step6_headed_review_*.json` with per-item
`PASS`/`FAIL`/`NOT_RUN`, source/case/native identities, screenshot paths and
first failure. `video/whole-run.manifest.json` records video hash, dimensions,
timestamps, FFmpeg and command exits, and `complete`/`partial`/`failed`.
Check the Slicer and simulation-stack logs against that JSON. A successful
recording does not imply a successful checklist. A brief rendered scene during
import does not imply transactional case validation succeeded.

Checklist order: exact checkout/case; case open and Step 6 UI; saved ROS state
not restored; accepted Base controls; Check Draft State control; exact native
preflight; explicit simulation Connect and scene acknowledgement; read-only
draft; one correlated guarded J1 jog (only when enabled); Base stage/cancel.
Base and Task Home acceptance remain `NOT_RUN` unless both the guarded-jog
gate and the exact Base/Home opt-in are `1`.
The opt-in stages the unchanged accepted Base, clicks the production Accept
Base owner, checks the locked matrix and resynchronized scene, then stages the
current accepted J1–J5 pose and clicks the production Accept Task Home owner.
It checks the saved, runtime-validated Home and retains no route or preview
authority. A failure stops the run before the next action. The runner captures state-matched UI
and viewport screenshots only after a checkpoint is reached; do not relabel
frames extracted from video as those screenshots.

For a diagnostic illustration when the runner stopped before screenshot
capture, extract selected frames and label each by time and limitation:

```bash
ffmpeg -n -ss 15 -i "$RUN_DIR/video/whole-run.mkv" -frames:v 1 "$RUN_DIR/evidence/recording-t15s.png"
ffmpeg -n -ss 21 -i "$RUN_DIR/video/whole-run.mkv" -frames:v 1 "$RUN_DIR/evidence/recording-t21s.png"
```

Choose times based on the **new** video's actual content. Keep the run
directory private and inspect frames/video for patient identifiers before
sharing. Do not infer accepted joints, collision freedom or route authority
from pixels; the correlated guard and state JSON are required.

## 6. Write one run-local diagnostics report and update records

Put `diagnostics.md` beside `video/` and `evidence/`. Include:

1. Date in UTC/local time, chat session name, task/plan gate, run ID,
   checkout/HEAD/dirty state, case and native hashes.
2. Relative links to video and manifest, itemized JSON, logs and selected
   screenshots; label extracted frames as video frames.
3. A compact planned-versus-observed table for each reached and skipped gate.
4. First causal failure, what its evidence establishes, what remains
   `NOT_RUN`, and the next bounded action. Mark operator verdict `PENDING`
   until Tarun supplies it.

The host-only `Testing/summarize_step6_evidence.py` can generate this report
from the runner JSON, recorder manifest and an outer-wrapper `cleanup.json`.
The wrapper must write `owned_process_cleanup: true` and
`remaining_owned_processes: []` only after checking its exact owned PIDs and
process groups; the summarizer never infers process absence. Pass the run
directory, session and plan gate explicitly. It returns 1 and marks the
report incomplete for any `PARTIAL`/`NOT_RUN` item, a partial video, a
nonzero command exit, absent process evidence, or a runner without a
substantiated `full_workflow_claimed: true`. It refuses to overwrite an
existing report. Keep the independent process-exit and functional outcomes
visible even when the short checklist functionally passes.

The [27 September example report](/home/light-tarun/dentobot/data/dentobot-runs/step6-headed-20260927T-GycmaP/diagnostics.md)
links a 27.033-second **partial** video and transient import frames. Its newer
case failed strict post-hydration `DENTOBOT.GeometryState` validation before
Base, Connect or jog. Do not copy its case/hash/result as a future input. Log
exact commands, results and evidence boundary in the current dated logbook;
update `S6-LIVE-01` and overlapping case-restore records without creating a
second backlog queue. Preserve strict package validation.

## Optional manual screen recording

For an already authorized, visible simulation session on an existing X11
display, the operator can start and stop recording independently:

```bash
python3 Testing/record_slicer_screen.py --display :0 \
  --output /absolute/private/new-run/video/manual-session.mkv --until-enter
```

Press Enter to finalize. This records pixels only. The Step 6 manual JSON
record remains the authoritative requested/guarded/accepted motion evidence;
the video is its optional companion and never restores live state on reopen.
