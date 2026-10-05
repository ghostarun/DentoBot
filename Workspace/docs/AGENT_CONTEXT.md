# DENTOBOT agent context

## Testing output storage — 6 October 2026 (`RUN-ARCHIVE-01`)

For every future agent-run test/diagnostic campaign, save durable output under
`data/dentobot-runs/YYYY-MM-DD/<task-id>-<UTC-start-timestamp>/` in the Ubuntu
overlay, not the source checkout. Use the **UTC run-start date** and timestamp
(e.g. `2026-10-06/S6-LIVE-01-20261006T213000Z`); keep that directory for the whole
run even across midnight. Container path: `/workspace/data/dentobot-runs/...`;
this station's host root: `/home/tarun/dentobot/data/dentobot-runs`.

Keep scripts, logs, screenshots, videos, JSON/results, reports and session
inbox/outbox beneath that run; use subfolders for attempts/cases. Never overwrite
another run or create a new flat top-level run folder. If a tool requires a
scratch path (including `/tmp/dentobot-verification/<run-id>/`), retain its full
logs/result.json there and copy the completed evidence into the dated durable
run folder before reporting completion; record both paths. Set the existing
output-directory option/environment override before execution and verify the
resolved path. Do not silently assume a producer follows this scheme; if it
cannot be configured, record the exception and move completed output only after
its writers/session have stopped. No live-session moves or alias reuse for new
runs. A shared watchdog output, when required by existing tooling, belongs at
`YYYY-MM-DD/ui-watchdog/` with unique timestamp/PID filenames using the same
UTC start date. Prefer run-local watchdog evidence when configurable.

Runtime approvals, privacy rules and acceptance gates remain unchanged. Keep
payloads outside Git; commit only appropriate controlled records/manifests.
Historical dates/path strings stay as recorded; the
[archive layout](diagnostics/RUN_ARCHIVE_LAYOUT_2026-10-06.md) and move manifest
locate older evidence. This policy directs agent output selection; it does not
claim all existing producers have been changed automatically.

## Current 4 October 30-second isolated planner result (`S6-LIVE-01`, P0)

The explicitly approved one-factor domain-74 copy request is complete. With
OMPL sampling fraction `0.0005`, one RRTConnect attempt exhausted the 30-second
budget in 30.003 s and returned error `99999` with zero trajectory points. The
copy and original matched on all 34 objects, ACM, padding, scale and fixed
transform; the retained burr/template canary matched at 0.286936408 mm and the
original scene hashes were unchanged. This rules out the 5-second budget alone
as a sufficient explanation but does not prove disconnection, infeasibility or
a physical minimum. No motion, GUI Plan, route authority or deployment occurred.
Evidence: `planner-resolution-20261004T071413Z`.

A later `planner-resolution-20261004T080424Z` directory contains broader branch,
planner, Base and spindle-scale experiments without a matching approval record
in the controlled task files. It is preserved as unaccepted diagnostic material
and must not drive a geometry or policy decision until Tarun supplies its
disposition. Its idle domain-74 MoveGroup copy was stopped during continuation;
the operator's domain-73 Slicer PID 3122 and MoveGroup PID 3022 were preserved.
No further planner or geometry trial is authorized by this handoff. Tarun's
verdict remains PENDING.

## Current 4 October live planner stop (`S6-LIVE-01`, P0)

Bounded native plan-only investigation approved by “Yes proceed” is complete: one rawservice request retains112points despite99999; authoritativechecks reproduceburr/template invalid104–108, dense41/51invalid peak0.286936408mm. Full34-objectscenegeometry/ACMunchanged, Home/PreEntryvalid, no motion/GUIplan/routeauthoritychange. Originalpre-TOTGverticesunknown; samplingversuspostprocessingnotproven. Proposed isolatedSIMULATION-ONLYOMPLfraction0.005→0.0005trial notloaded; collision-policy approvalneeded peroperatorsection3. Evidenceplanner-resolution-20261004T025825Z; prior109/121/124historyretained; neitherA/B, physicalminimumunknown, TarunverdictPENDING.

## Step 6 GUI reliability — patches only (4 October, `S6-LIVE-01`)

Operator: the recent button/state fixes (6.2 Home actions, Plan + Apply Home
Draft endpoint/no-op, 6.3 planner frozen after the spindle-contact toggle) are
case-specific patchwork, not verified; many similar greyed controls, errors and
ordering issues remain and prior headed/headless runs did not surface them.
Do not call Step 6 GUI behaviour verified from one passing run. Pending work:
`S6-GUI-STATE-AUDIT`, `S6-GUI-HARNESS-GAP`, `S6-HOME-REPEAT` (backlog, TASKS top
section, DECISIONS 4 Oct later). Apply the never-silent rule to any control touched.

## Later 4 October steering — new Home draft application (`S6-LIVE-01`)

Operator reports “cannot plan and apply new home”. The 6.2 action now plans and
applies the exact current/currently reviewed draft without requiring saved Home;
separate Accept & Validate still saves Home. The actual button reached MoveIt
in unchanged PID2071, then stopped at CheckStartStateCollision: mouth-barrier
lip slab versus spindle housing in the accepted all-zero start. No waypoint
applied; original draft/case/Home/accepted state preserved. The collision/start
blocker, positive route/application and Tarun verdict remain in backlog. This
later scope supersedes the earlier agent-selected no-plan/apply boundary only
for this Home action. See the 4October logbook; NVIDIA acceptance remains open.


## Local Task Home recovery — 4 October 2026

Latest operator scope: diagnose/fix the Oct4 DentoCase Home revalidation defect,
reload Python and test in the already open headed Slicer. Existing `S6-LIVE-01`
Priority0 owns this bounded correction. Cancel after definitive collision
rejection now permits a fresh review when identity is current and acceptance
is certain. Host242 PASS and the actual button sequence PASS in unchanged
Slicer PID2071; ROS connection, accepted joints, original draft and saved case
are preserved. The zero-joint pose still fails the strict mouth-barrier/spindle
collision guard; no valid Home or full-cycle acceptance is claimed. See
[4October evidence](logbook/2026-10-04.md) and the retained backlog gate.
This narrow authorization does not restart the old repeatability campaign or
authorize a new planner/preview/geometry trial. NVIDIA acceptance remains open.

## Local source handoff — 3 October 2026

This destination now uses `/home/tarun/dentobot/ros2_ws/src/DentoBot`,
branch `main`, published checkpoint `3997458`; native SlicerROS2 source is
`ece3c42`, matching `Workspace/LAB_RELEASE` (`lab/2026-10-03-4`).
The operator explicitly requested the latest published progress as-is. This
source handoff supersedes older checkout-selection instructions for this local
station only. Retain the current upstream workflow contracts and open gates.
Description, MoveIt and native packages were rebuilt; preflight and ordinary
Mesa-mode Slicer startup passed. Case/image parity, shutdown and operator
acceptance remain open. NVIDIA renderer/FPS testing is pending under
`S6-P2-03`; use the [acceptance checklist](diagnostics/NVIDIA_WORKSTATION_ACCEPTANCE_2026-10-03.md).
Local September-30 migration notes are preserved separately; see today's
logbook and `PLAT-U-07`. No runtime continuation follows from this pull.


## Current Step 6 chat handoff — 1 October 2026

Operator confirms the checkout is now `DentoBot-step6-5.10-integration` and asks
this chat to update progress and prepare for subsequent changes. Use this checkout
and `integration/step6-5.10-reviewed-20260927` for future implementation; current
HEAD is `baeee90`, with integrated source checkpoint `50ce208`. Older renovation
paths, transfer-pending statements and performance-integration deferrals below
are dated evidence, superseded for development routing.

The recent Base notification, compact labelled joint controls, strict bounds
diagnostics and native cache-lifetime corrections are present in this source.
The native source SHA matches the approved renovation build; this read-only
handoff does not establish the currently loaded binary or connected authority.
Existing `S6-LIVE-01` Priority 0 remains open for offline/connected Base recovery,
rendered controls and Tarun's verdict. DentoCase software gates retain recorded
558 host passes and synthetic offline attempt4 PASS; browser/independent
continuation verdict remains open under `DCP-09..10`. Responsiveness stays with
`S6-P2-03` and the permanent performance-monitoring chat. No new runtime/build
is authorized by this readiness update; 5.12 remains held.

## Performance environment scope — operator direction 2026-10-01

Current container/DENTOBOT performance diagnosis, watchdog improvements and acceptance target **native Ubuntu** on the consolidated integration checkout. Attribute host RAM, swap, disk/I/O, CPU and graphics measurements to that Ubuntu workstation and record its hardware/runtime identity. Do not generalize native Ubuntu results to Windows/WSL/WSLg.

Windows/WSL performance verification is a separate later environment-specific campaign under existing platform owners. Adapt collection and checks to Windows host resources, WSL VM memory/swap limits, filesystem boundaries and WSLg/GPU presentation; retain separate baselines and acceptance evidence. Cross-platform support remains intended, but it does not expand the current Ubuntu investigation. Reuse existing tasks and monitoring infrastructure; no new queue, runtime authorization or change to the indefinite 5.12 hold.


## Permanent performance and reliability monitoring

For every workflow/container quality investigation and authorized representative
runtime, follow [PERFORMANCE_MONITORING.md](PERFORMANCE_MONITORING.md). Keep
watchdog evidence, bug triage, performance comparisons and cleanup checks
under existing `S6-P2-03`/`S6-U-01` and affected workflow tasks. `backlog.md`
remains the sole pending queue; TASKS/logbooks retain contracts/results.
Preserve the r18 correction: no scheduled Python traceback dumping. Read-only
monitor review grants no runtime approval; current Step 6 and 5.12 holds apply.

Last reconciled: 2026-09-28. `S6-LIVE-01` remains Priority 0.

**Current execution order:** Checkpoint commit `84234a6` records the preceding
Step 6 engineering-workbench gates. The subsequent exact five-DOF refactor is
source/build/runtime verified: URDF, MoveIt/native guard and current workflow
state expose exactly J1–J5, while the fixed spindle/burr geometry and canonical
TCP remain. The drill is a separate future speed-controlled device outside
joint state and IK; no hardware/RPM command is authorized. Resume the remaining
case-bound rejected/unknown/reconciliation, physical-key/responsiveness and
positive full-chain preview/interruption gates on a newly saved five-DOF case.
The [detailed acceptance checklist](diagnostics/STEP6_FIVE_DOF_DETAILED_ACCEPTANCE_CHECKLIST_2026-09-28.md)
is now the latest implementation plan for that case creation and automated
headed GUI simulation campaign; do not create a parallel test plan. This task
permits up to four simultaneous GPT-6 Luna Max workers where independent
disjoint implementation/host-test work warrants them. Sol retains reasoning,
controlled records, serialized runtime and acceptance. The present platform
allows only three workers beside Sol concurrently, so a fourth is sequential.
**30 September operator supersession:** Prepare the reviewed integration branch now from frozen renovation checkpoint `e7cd29f` and accepted Slicer 5.10 fixes. Actual 5.12 promotion remains deferred. Final Step 6 acceptance and normal-window verdict remain PENDING; early source integration does not accept the unfinished renovation. See [integration preparation](diagnostics/STEP6_INTEGRATION_PREPARATION_2026-09-30.md).

**Newest headed Base/Home result:** The unchanged reviewed case and isolated
native guard passed all 14 bounded in-app checklist items: case/scene,
guarded J1, Base stage/cancel and zero-displacement Accept Base, then review/
accept of the current J1–J5 as runtime-validated Task Home revision 13→14.
The first opt-in run exposed a runner evidence-check defect; a Luna Max
source/test pair corrected it and 23 focused host tests passed before the
successful second run. Both whole-process videos are `partial` because Slicer
exited 1 on shutdown. [Run-local diagnostics](/home/light-tarun/dentobot/data/dentobot-runs/s6-live-01-base-home-accept-20260927T131832Z-r2/diagnostics.md)
link JSON, screenshots and video. This is bounded happy-path simulation
evidence, not full workbench/recording/preview or Tarun's normal-window
verdict; the latter remains PENDING. The dated paragraph below records the
earlier stage/cancel checkpoint.

**Earlier Step 6 renovation checkpoint (27 September):** The unchanged current
FDI11 package now reopens; exact native double status echo and accepted-state
UI mirror defects are fixed in the dirty renovation checkout. A bounded
headed checklist passed case/robot/31-object scene, production read-only
static/FK draft, one correlated native-accepted J1 +0.1° jog with later
accepted/monitored/displayed convergence, and detached Base stage/cancel with
no accepted-matrix change. Slicer exited 1 during shutdown, so that run's
video manifest remains `partial` even though checklist JSON says PASS.
Detached Task Home review/accept source and UI subsequently passed 166 host
pure tests; headed Home acceptance, Base Accept/reconciliation, invalid-state
and ordered-record/export/reopen gates remain open. Tarun's normal-window
robotics/usability verdict is **PENDING**. See today's logbook, backlog and
active renovation plan; earlier paragraphs below are dated checkpoints.

**27 September source continuation:** Unknown/stale submitted manual jogs now
latch the facade and block later publishes; UI wording shows possible native
advancement and displays attributed guard distances with correct threshold vs
measurement labels. Focused host pure checks passed (6 facade, 5 UI). At that
checkpoint, request/policy correlation and reconciliation were still open;
their later source completion is recorded below. Runtime/operator acceptance
remains open. See the 27 September logbook and active renovation plan.
The same date's read-only Check Draft State source gate passed focused checks
(6 facade, 4 UI): it evaluates a captured J1–J5 candidate without jogging,
and labels static validity separately from task-target match. Arbitrary
out-of-range review, named collision evidence and runtime usability remain open.
Later 27 September source work added a separate simulation-only manual
request/status pair with request/session and actual raw ACM policy identity;
the combined host pure check passed 106 tests. At that checkpoint, native
build/runtime, reconciliation, screenshots and operator verdict remained open.
The later two-worker retry implemented the read-only native accepted-state
query and explicit UI reconciliation source path; 118 combined host pure tests
passed. Native C++ build, current-case ROS/Slicer exchange, screenshots and
Tarun's verdict remain pending. Detached Base/Home exploration is next source
work under the same Step 6 plan.
Commit `c1bfba0` captured that manual attribution/reconciliation checkpoint.
The subsequent uncommitted source slice implements detached **numeric** Base
review and passed 86 combined host pure/UI tests. No Base ghost, native/Qt
runtime proof or operator verdict exists. Detached Home and the broader
engineering solver remain open under `S6-LIVE-01`.
The 27 September authorized recorded headed run used the exact renovation
checkout, isolated native package and a newer FDI11 case. Its first partial
recording stopped at strict post-hydration final-template validation. Audited
restore-order and landmark-roundoff corrections now reopen the unchanged case
with Case Foundation pose, Base and PreparedBranch all `VALID` in fresh Slicer;
21 focused host tests passed. A second partial recording opened the case and
captured UI/viewport PNGs but stopped at disabled Connect: the runner omitted
production Load Robot and Import Planning Context actions. The saved/current
task-limits fingerprint still differs. Both partial videos, itemized JSON,
screenshots and logs have run-local diagnostics indexed in today's logbook.
Preserve strict validation, finish the runner's production prerequisites and
visual scroll framing, then repeat the serialized recorded trial. No guarded
jog was submitted; Tarun's visible verdict remains pending.
Later same-day runs passed production robot load, planning-context import,
simulation Connect, 31-object scene readback and the corrected J2 display
roundoff comparison. The latest partial recording stopped at the production
Check Draft State action because the newer case has no confirmed task;
static validity and guarded jog were not reached. The active next source gate
is task-independent manual static review and exact raw guarded-jog identity
under current branch/Base/limits/profile/scene/ROS, with absent or stale Home
marked unconfirmed and target evidence
unavailable until confirmation. See today's logbook and run-local diagnostics.
For a future approved repeat, use the separate
[recorded headed automation workflow](diagnostics/STEP6_RECORDED_HEADED_AUTOMATION_WORKFLOW.md)
with the matrix and protocol; do not reuse the prior case, hashes or result.

**2026-09-26 engineering-outcome review (supersedes intermediate status summaries):**
Baseline `40ad290` contains ROI-first sampling, shared endpoint evaluation,
separate diagnostic P1/P2/P3, draft/guarded J1–J5 controls and schema-1.0 JSON
recording. Prior host pure checks passed 193 tests. The full engineering solver
is partial: detached Base/Home candidates, arbitrary invalid-draft evaluation,
complete motion evidence/path/replay, final two-area integration and full-chain
promotion remain open. Native/runtime behavior and measured responsiveness are
unverified; the last headless fixture failed before any jog (scenarios NOT_RUN).
Tarun is remote: user simulation trial and visible verdict remain PENDING.
The [revised existing plan](diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md)
prioritizes engineer-led state/motion exploration before case-specific planner
solving. It specifies finite closure slices and reuse of indexed automation.
Headless and scripted headed Slicer checks are technically available, subject to
runtime authorization, provenance and the current fresh-case deferral. The
parallel performance/5.12 checkout is outside this task.

The standalone FDI11 PreEntry IK source gate passed pure checks and a native
package build. Tarun's first visible IK-only report shows collision-checked
endpoints for a changed base/Home/scene, with P1/P2/P3/guard NotRun; its
original saved-case identity differs and his verdict is pending. Source now
shares a versioned exact-TCP evaluator across Goal-1, PreEntry and explicit
Check Current State, and exposes separate P1/P2/P3 diagnostics through the
existing planning panel. The later combined Step 6 host pure checkpoint passed 193 tests.
These are plan-only source checks, not full workbench, route, runtime or case
acceptance. Tarun places the Step 6 **workflow renovation before case-specific
planner solving**.
Agent-run planner runtime and manual acceptance remain separately gated. The
[renovation plan](diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md)
records the current order under existing IDs; the
[active base-pose technical reference](diagnostics/DENTOBOT_Base_Pose_Feasibility_Explorer_Diagnostic_Plan_2026-09-25.md)
defines shared diagnostic metrics for the ROS-connected manual engineering
workbench and automatic planner; its automated sweep is later work. The
[later-reference index](diagnostics/STEP6_LATER_WORK_AND_ADJACENT_IDEAS_2026-09-25.md)
routes deferred case and adjacent ideas. The sole canonical milestone contract is
[FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md](diagnostics/FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md).
Tarun's later 2026-09-24 direction supersedes the seven-card Step 6 planner
presentation: merge 6.3 workspace diagnostics, 6.4 confirmation and 6.5
planning under Planning & Diagnostics; put simulation preview/return/repeat
under Preview & Control. `S6-WORKSPACE-PURPOSE` is the prerequisite for the
workspace-gate change. The FDI11 IK-only verdict remains open while
source-level workflow renovation proceeds; agent runtime and milestone verdicts
remain gated. The editable ROI now feeds the source-level live workspace action,
but its yield, latency and scene behavior await serialized simulation review.
See the latest TASKS, DEVELOPMENT_PLAN, DECISIONS and logbook entries.
The 23 September [decision report](diagnostics/DENTOBOT_Step6_Decision_Report_2026-09-23.pdf)
is review evidence, not a parallel plan. Tarun has supplied source direction;
do not infer runtime or hardware authorization from the report.
The Sep-22 FDI31 baseline is `data/Slicer_Saved/SampleStudy1/FDI31/dentobot-case-sep22-step6.dentocase`
(SHA-256 `eb48a805...e7adb`). `M1-DIAG / HOUSING-OFF PASS` completed diagnostic
P1 with 150 waypoints. An operator-repositioned base at an altered 45.96-mm
mouth gap later completed a housing-on P1/P2/P3 chain, but its exact adjusted
scene has not been saved for an independent run and canonical M1/M2 remain open.
Do not run the prepared FDI21 plan-only automation against the older saved base;
obtain a separately named adjusted-state package and serialize runtime first.
Pending order is in [backlog.md](backlog.md);
task state and acceptance evidence are in [TASKS.md](TASKS.md). Campaign-1
r4/P3/P4/P5 is historical diagnostic evidence, not current instruction.

The Step 6 planner chooser now exposes RRTConnect, RRT and optional RRT*;
approximate IK is disabled, planner guidance and reopenable failure text are
source-verified, and the installed OMPL configuration passes. Tarun's visible
RRTConnect trial passed Stages 1/2 and stopped at the existing Stage-3
tooth↔spindle guard. Same-scene RRT/RRT* trials and the subsequent exact-pose
sequential-IK Cartesian-off implementation remain open. A configured MoveGroup
ID is not proof of the executed algorithm.

The Step 5B target-switch repair under `S6-REUSABLE-CASE-SETUP` / `W5-U-03`
was operator-confirmed in `FDI21-and-32-working#1-dentobot-case-sep22-step6.dentocase`.
The Step 5C PreparedBranch work remains active under `S6-REUSABLE-CASE-SETUP`.
The repaired two-target GUI sequence passed headlessly through FDI21 Step 6A;
a new package `FDI21-31-headless-verified-sep22-step6a.dentocase` (SHA-256
`c16e0406...d1c1d`) passed fresh-process reopen with both trajectory slots
Current. Tarun's normal-window alternating-branch verdict remains pending.
The subsequent FDI21 screenshot shows a stale FDI31 motion-diagnostic session,
not independent proof of a fresh FDI21 planner pass. Do not weaken stale
evidence or implement the 96-trajectory batch proposal.

**2026-09-24 FDI11 continuation:** `SEPT24/pulp-testing-fdi11.dentocase` now opens in Tarun's normal window after the stale-pose UI refresh repair; the same screenshot shows one generated Step 4A FDI11 assisted line. The 52-voxel derived candidate still needs normal-window anatomy review, and the line needs trajectory-aligned MPR review. The separate automated crown-cap Entry missed the smoothed candidate surface; do not infer that it matches Tarun's successful Entry or change the endpoint gate from this comparison. Details remain under `S3-P0-DENTAL-SEMANTICS`, `S4A-PULP-ENDPOINT`, `S6-REUSABLE-CASE-SETUP`, and today's logbook.

## Start here

1. Read repository AGENTS.md. Read/search all of backlog.md for the request,
   synonyms, workflow step, IDs and overlap mappings before source or planning.
2. Follow every match into TASKS.md and its linked DEVELOPMENT_PLAN / DECISIONS
   sections and relevant dated evidence. Reuse its ID, priority, dependencies,
   ownership and boundaries. Do not load whole logbooks or old checkpoints.
3. For source work use the internal
   [package routing map](../../DENTOWorkflow/Resources/Python/dentobot_workflow/README.md).
4. For checks follow [AGENTIC_VERIFICATION_PROTOCOL.md](AGENTIC_VERIFICATION_PROTOCOL.md)
   and checkout-relative `Testing/verification_matrix.json`.

## Active P0 routing

- **Current state:** the Sep-19 Home→PreEntry P1 blocker (13 failed GUI legs)
  remains historical baseline evidence. The Sep-22 housing-off P1 diagnostic
  and alternate-base housing-on full chain are separate, non-canonical
  observations. Canonical M1/M2 and a fresh FDI21 planner result remain open;
  follow the canonical plan and today's logbook before another runtime action.
- **Before Step 6 source work:** read the [working renovation plan](diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md),
  then the matching backlog/TASKS contract and the [FDI31 P0 milestone
  contract](diagnostics/FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md) if its gate is
  involved. The [archived September 20 diagnosis](diagnostics/archive/step6/STEP6_PLANNER_MANUAL_DIAGNOSIS_CONTEXT_2026-09-20.md)
  is optional dated context, not a mandatory current restart instruction.

## Preserved routing context and evidence

- **2026-09-20 — archived Step 6 manual diagnosis:** The
  [diagnosis](diagnostics/archive/step6/STEP6_PLANNER_MANUAL_DIAGNOSIS_CONTEXT_2026-09-20.md)
  and [implementation map](diagnostics/archive/step6/PLANNER_IMPLEMENTATION_MAP_2026-09-20.md)
  explain the September 19 FDI31 P1 session. Their experiment order and
  “current failure” claim are superseded by later case-specific evidence and
  the working renovation plan. Consult them only for historical attribution.

- **2026-09-19 — Ordinary GUI path reaches Step 6.5; planner stalls at PreEntry:**
  The operator confirmed the Cursor debug-branch workflow through Step 6.5 on
  saved FDI31
  `data/Slicer_Saved/SampleStudy1/FDI31/dentobot-case-sep19-step6.dentocase`
  (filename corrected 2026-09-21).
  Motion diagnostics listed **13 planner legs**, all failing at **P1 /
  PreEntry** (Home→PreEntry). **P2 (PreEntry→Entry) and P3 (Entry→Target)
  preflight never ran.** This live GUI result contradicts earlier Codex
  headless verification trials (Campaign 1 P3/P4/P5 diagnostic witnesses on
  locked r4). Do not treat those trials as operator-verified Goal 1. Immediate
  work for the **Tuesday weekly meeting** (2026-09-22) is to solve Goal 1
  PreEntry or produce a bounded issue packet for professor discussion. Owner:
  `S6-LIVE-01` (planner). Branch
  `cursor-agent/dentoworkflow-debug-20260918` is source-successful through
  6.5 and may merge to `main` only after further testing **and** planner
  completion. No robot hardware motion.

- **2026-09-19 — Step 3B offline robot placement (6.1 mirror):** After AUTO
  open-mouth, Confirm goes to **3B** on the same Step 3 combo row. 3B reparents
  the existing 6.1A + Placement Context widgets onto one MRML robot/base/forehead.
  Step 6.1 shows PASS/green when `VirtualForeheadPriorV1` matches the Case
  Foundation fingerprint; manual nudge is still allowed. Same-day regressions
  fixed: 3A layout orphaning, robot hidden after lock/propose, full **New Empty
  Case** reset, Step 4A target-tooth combo scroll (safe `ui_scroll_support` v2).
  **Accepted 2026-09-19** (`S3B-ROBOT-PLACEMENT-MIRROR` closed). Operator also
  closed `S6-U-02` at simulation scope (not hardware metrology).

- **2026-09-19 — New Empty Case full workflow reset:** Step 0 **New Empty Case**
  clears MRML only, then `_resetWorkflowStateForFreshCase()` wipes transient UI
  (views, substeps, placement reparent, foundation snapshot) and always opens
  Step 0. No session/foundation carry-over.

- **2026-09-18 — Virtual forehead prior (simulation only):** After AUTO
  open-mouth, Step 6 **Propose virtual forehead + base** seats
  `T_world_forehead @ T_rel` from the operator dump
  (`-176.5538/-83.1910/86.5294 deg`, `1.3063/8.8267/56.5915 mm`, q=0).
  Not `S6-U-02` closure; no robot hardware motion.

- **2026-09-18 — Case Foundation AUTO-primary GUI (source-complete):** Default
  operator path is **Open mouth (AUTO)** → visual confirm → **Confirm and
  continue to Step 4A**. Manual landmarks are fallback only. Headless
  `runtime.auto_open_mouth_test1_post` PASS. This does not resume the P5/gate
  campaign or authorize robot motion.

- **Quota-constrained recovery checkpoint — stop analysis and implement P0 next
  (2026-09-17):** The operator ended the extended read-only audit because the
  USD 20 plan quota was nearly exhausted. Do not restart the audit or spawn a
  replacement review. Existing worker outputs and direct reconciliation support
  four immediate findings: the 15Sept fixture restores two visible FDI31
  representations (closed-source plus opened moving-lower proxy); assisted-entry
  activation fails when Slicer's post-`StartPlaceMode(0)` active-node or
  placement-valid state does not match the expected markup, but the saved run
  lacks the discriminator identifying which postcondition failed; the FDI21
  ownership warning is valid stale-target protection; and P5 has a duplicated
  request ID despite distinct sequence/vector correlation. Preserve corrected
  P3/P4/P5 as diagnostic evidence, keep P5 operator verification blocked, and
  begin future implementation at the shared restore/display-state transition,
  followed by one bounded native placement-state discriminator. No P3–P5 rerun
  or P6/P7 follows from this checkpoint. Full evidence and interrupted-work
  accounting are in the recovery report Section AW and the 2026-09-17 logbook.

- **Active operator route — pause after P5 for GUI verification
  (2026-09-17):** Do not continue the gate/P-series. Preserve locked r4 and all
  P3/P4/P5 artifacts. Route work through `VERIFY-LEARN-01`: inspect r4 without
  mutation, then exercise Assisted Trajectory Generation only in a fresh or
  disposable-copy case and walk the ordinary 4A→4B→4C→5A→5B→5C→6 GUI path to
  its first truthful PASS/failure. r4 already contains the saved 15 September
  trajectory, so its assisted controls are expected to block overwrite. P5
  programmatically reused that trajectory/PreparedBranch and bypassed normal
  Connect/Task Home/workspace/task-confirmation; it is not Operator Verified.
  Record status text, screenshots, save/reopen result and owner mapping. Resume
  only after a controlled-record reconciliation explicitly names the next gate
  after P5; P3–P5 rerun and P6/P7 are not defaults.

- **Preserved Campaign-1 execution record (2026-09-15; superseded for current
  sequencing on 2026-09-21):** The operator superseded the former
  Astra/design-only/P4 limit and started implementation in the existing
  `S6-REUSABLE-CASE-SETUP` / `S6-LIVE-01..04` lane. One bounded Luna Max worker
  may implement exact work orders; the main orchestrator owns diagnosis, runtime
  and acceptance. The new FDI31 case preserves r7/r13 and uses the 15Sept
  foundation, supports FDI42/41/32/33, 1.0 mm dock bores, >=2.0 mm
  trajectory-guide/channel values, and the locked Step-4A 15Sept FDI31 markup
  (`5.239400689721231 mm`, member SHA `61dac396...`) as its trajectory input.
  The runner's opt-in parser/import and 1.0-mm dock default are source/unit
  verified (29 focused tests). Revised runtime `c1-gatea-fdi31-20260915-r4`
  then produced and reopened a new corrected FDI31 package with a PASS
  diagnostic, the immutable 5.239400689721231-mm trajectory, and all four
  reviewed supports. Gate A is complete for construction/save/reopen only;
  Gates B-D, physical/clinical review and every hardware path remain NOT RUN.
  The Slicer process returned nonzero during shutdown after emitting PASS, so
  preserve that process-health warning separately; see Campaign 1 and today's
  logbook for hashes and evidence boundaries.
- **P3 corrected static revalidation (2026-09-16):** The operator's explicit
  fourth ceiling exception evaluated only the immutable old-r4 21-vector input
  (input SHA `8853f520...`) with drilling `validate_only` `static_state`
  requests. The fresh raw batch
  `c1-p3-fdi31-20260916-r4-static-revalidation-r4/endpoint_candidates.json`
  (SHA `d5a3ef...`) retained all replies but initially marked them
  inconclusive because native `collision_guard` serializes status vectors with
  `std::setprecision(12)`. The repaired bounded echo check and companion
  evidence `endpoint_candidates.corrected_static_attribution.json` (SHA
  `ec6ad4...`) establish **21 accepted, 0 rejected, 0 unknown and 21
  admissible**; 80 focused checks pass. Generic static rejects all 21 only as
  diagnostic Template↔visual-spindle / target-tooth↔burr contacts. The
  authoritative guard accepts all 21 with its configured non-rotating
  template/spindle warning; no candidate is strictly guide/housing-clear, but
  native self/unrelated/corridor checks pass. P3 conditionally admitted P4;
  no fifth static batch is authorized.
- **P4/P5 bounded diagnostic completion (2026-09-16):** Under later explicit
  operator authority, P4 wrote `c1-p4-fdi31-20260916-r4/insertion_branches.json`
  (SHA `3cc1759d...`) with six complete bounded insertion witnesses. P5 then
  wrote `c1-p5-fdi31-20260916-r4/approach_branches.json` (SHA
  `6455a52e...`), a `SAMPLED_PASS` from a fresh zero-vector monitored
  simulation start through one P4 source-6 witness: 208 Phase-`approach`
  Stage-1 edges, 12 Phase-`terminal_contact` Stage-2 edges and one P4 join,
  all uniquely sequenced `validate_only` requests. The Stage-2 endpoint has
  native FK residual `0.000429 mm / 0.000202°`; native positions and the raw
  joint stream stayed unchanged/off, and the owned stack was torn down. The
  existing Stage-2 Cartesian request first returned no native points and its
  existing bounded position-axis continuity fallback supplied the complete
  diagnostic witness; this is evidence, not a planner/configuration change.
  P5 is not a physical fit, housing-clear, executable-motion, P6/P7,
  withdrawal/Home, repeat, hardware, spindle or patient result. See today's
  logbook and recovery report Sections AU–AV.
- **Preserved FDI31 override (2026-09-14; historical):** The operator accepted the causal review
  and requested Astra architecture / Luna Max implementation orchestration.
  Read [Campaign 1](diagnostics/archive/step6/FDI31_PLANNER_RECOVERY_CAMPAIGN_1.md) and its
  TASKS/DECISIONS supersession before following older geometry-only/one-packet
  next-action text below. Design issued; execution not authorized. P0 baseline,
  P1 scene/operator review with P2 diagnostics, P3 endpoint, conditional P4
  insertion, then R1/Astra; no automatic next tooth or full-flow retry.
- Active P0 owners: `S3-P0-DENTAL-SEMANTICS`, `W5-U-04`,
  `S6-REUSABLE-CASE-SETUP` and `S6-LIVE-01..04`.
  Run central incisors FDI31 → FDI41 → FDI11 → FDI21 independently from the
  unchanged `data/Slicer_Saved/SampleStudy1/dentobot-case-13sept.dentocase`.
  The full gate and failure policy are in
  [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md#2026-09-14-four-central-incisor-exact-case-campaign);
  pending status is in [backlog.md](backlog.md), contract in [TASKS.md](TASKS.md),
  decision in [DECISIONS.md](DECISIONS.md), evidence in
  [2026-09-14 logbook](logbook/2026-09-14.md).
- For each tooth: clean process → 4A–5C → verified STL → production save →
  **new-process** reload → exact Stage 6. Store package, STL, SHA-linked JSON
  and screenshots under `data/Slicer_Saved/SampleStudy1/FDI<nn>/<run-id>/`.
  Record tooth-specific first-invalid results and propose the next tooth only
  after operator approval; stop on shared
  source/package/fingerprint/runtime failures. The source has all four tooth
  masks, pulp for FDI31/41 and no labeled FDI11/21 pulp. The later
  `S3-P0-DENTAL-SEMANTICS` decision permits a separate reviewable candidate
  from a dominant enclosed void; it is not an automatic planning endpoint.
- Existing FDI31 has one current eligible PreparedBranch, current STL and
  save/reopen evidence. The approved current-source exact check reached the
  requested target endpoint but stopped at the first native Stage-3 guard
  collision between the selected tooth and `pneumatic_spindle-Copy`.
  Goal 2/Return Home, repeat/playback and ten normal-window observations are
  not accepted. Preserve the first-invalid evidence; do not relax the guard,
  shorten depth, move the base or start another tooth automatically.
- The operator manually selects Luna Max for this campaign. Continue the fixed
  path for classified failures; stop before an ambiguous or unplanned
  higher-reasoning fix and give the evidence/reasoning-type packet specified in
  DEVELOPMENT_PLAN.md. Never switch models or delegate automatically.
- **One packet only:** The generator STL/folder/diagnostic edit is implemented.
  The operator explicitly approved the bounded offline Slicer/ROS/MoveIt check
  for the current FDI31 semantic implementation, with no robot motion or
  patient-facing action. That current-source check ended at the target-specific
  Stage-3 first-invalid collision; preserve its r13 artifacts and wait for a
  compliant guide/tool/base geometry correction and explicit recheck approval.
  Do not start FDI41, FDI11 or FDI21 automatically.
- `Testing/run_dentobot_stage6_target_generation.py` already generates/saves
  and reopens in-process; it lacks STL export and fresh-process verification.
  Reuse the exact-case Stage 6 runner separately. Six-target matrix, optional
  32 × 3, Studio, database and platform migration stay downstream.
- `S3-P0-DENTAL-SEMANTICS` owns pulp identity, automatic per-run inventory on
  new segmentation completion, manual checking of older loaded runs, and
  explicit Step 2 single/bulk candidate preparation. The usual FDI11 package
  lacks a pulp label but has a dominant enclosed 52-voxel void. Focused
  Slicer verified its creation through bulk. After Tarun's approved bounded
  continuation, the corrected report and candidate passed MRB and dentocase
  save/reopen; archive schema 2.0 and workflow-state schema 3.0 are hydrated
  separately. Full-batch throughput and operator anatomy acceptance remain
  open. Step 4A generation
  does not create masks. Keep `S4A-PULP-ENDPOINT` as endpoint owner and
  `S6-REUSABLE-CASE-SETUP` as package/campaign owner.
  A later operator-saved `SEPT24/pulp-testing-fdi11.dentocase` exposed a
  Step 4A parent-FDI persistence lookup bug for the reviewed FDI11 derived
  candidate; the one-line pure correction passes, while exact-case Slicer
  verification waits for the active operator GUI to release the runtime.

## Durable Step-4A–5B testing baseline (operator-supplied, 2026-09-15)

Use this as the default new-case/automated-test fixture unless a newer explicit
operator decision supersedes it. It is a research/testing baseline, not
operator acceptance of the inputs, scene, geometry, clinical intent, contact
interpretation or P1/P2. The five screenshot files and the detailed
operator/source separation are retained in
[logbook/2026-09-15.md](logbook/2026-09-15.md) and
`data/dentobot-runs/fdi31-operator-steps4a-5b-20260915/`. Do not rewrite
the frozen 13Sept/r7 evidence to make it match these defaults.

| Step | Selection or derived test output | Default value(s) / expected fixture | Authority and evidence boundary |
|---|---|---|---|
| 4A | Target tooth; optional assisted-entry count | `FDI31`; assisted trajectory count `2` | Target and duplicate closed/opened FDI31 appearance are operator screenshot observations. The duplicate is a defect to investigate, not a second target and not a default. Count is the source/UI default. |
| 4B | Same-jaw support package | Four immediate arch positions: for FDI31, `FDI42`, `FDI41`, `FDI32`, `FDI33` (two on each side). Missing/edge positions do not silently substitute farther teeth; the suggestion is incomplete and requires review. | Canonical helper: `DENTOWorkflow/Resources/Python/dentobot_workflow/logic_guide_support.py`; pure regression: `Testing/test_step4b_support_auto.py`. The four IDs are the operator-confirmed example and the automated expected fixture, not operator acceptance of all scene geometry. |
| 4C | Target reference; dock assembly | Target-crown occlusal dock plane; four independent robot docks | Operator screenshot/source-aligned fixture. The plane's oblique appearance remains a review issue; it is not certified by the parameter table. |
| 4C | Dock dimensions and draft screen | Pattern radius `10.0 mm`; dock outer diameter `3.0 mm`; **robot-dock bore `1.0 mm`**; connector/branch width `3.5 mm`; endpoint overlap/thickness `2.0 mm`; shared depth `5.0 mm`; obstacle clearance `0.5 mm`; yaw `35.0°`; individual depths disabled with each depth `5.0 mm`; measurements visible | New parameter/UI defaults in `parameter_state.py` and `DENTOWorkflow.ui`. The 1.0-mm value is only the registration/robot-dock bore; it is not the drilling trajectory bore. |
| 5A | Visible support and automatic plane | Visible support preview; insertion-aligned support plane; plane depth from Entry `4.0 mm`; crown-cap tilt fit `10%`; boundary sampling `0.5 mm`; terminal support coverage `50%`; polarity reversal off | The 4.0/10/0.5/50 values are source/UI defaults; some lower-crop values were not visible in the supplied screenshot. The oblique plane is an unresolved display/world-frame review item, not accepted geometry. |
| 5B | Undercut/blockout inputs | Undercut angle tolerance `5°`; interproximal relief `1.0 mm`; blockout safety `0.1 mm`; voxel closing `0.3 mm` | Source/UI defaults; these controls were visible in the supplied 5B view. The grey derived-output controls and `Unified template=None` are output/state observations, not defaults. |
| 5B | Shell/guide construction inputs | Shell clearance `0.3 mm`; shell thickness `1.5 mm`; geometry sampling `0.3 mm`; shell channel `2.0 mm`; trajectory-guide outer diameter `4.4 mm`; trajectory-guide hole/bore **`2.1 mm`**; guide height `2.5 mm`; guide/dock clearance `0.3 mm`; collar radial width `1.0 mm`; collar depth `2.0 mm` | These are source/UI defaults; several are not visible in the supplied screenshot crop. The direct UI field is `templateSleeveInnerDiameterMm` (“Trajectory guide hole diameter”). Operator 2026-09-19: live default `2.1 mm`. |

### Non-negotiable trajectory-guide bore rule

The drill-burr/trajectory-guide hole must be **at least 2.0 mm in diameter**;
values below 2.0 mm are invalid and must fail closed. The persisted live
default `templateSleeveInnerDiameterMm` is **`2.1 mm`** (operator 2026-09-19).
The UI minimum remains `2.0` (the burr floor). `DENTOGuideGeometry.py` keeps
`MINIMUM_TRAJECTORY_BORE_DIAMETER_MM = 2.0` and
`DEFAULT_TRAJECTORY_BORE_DIAMETER_MM = 2.1`. The related shell channel
`templateChannelDiameterMm` still defaults to and is UI-bounded at `2.0 mm`.
This rule does not raise the separate Step-4C `targetDockingBoreDiameterMm`
default of `1.0 mm`.

Entering Step 5B lifts an in-memory hole **below 2.0 mm** to the live `2.1 mm`
default so section-2 spinboxes stay in range and editable. Frozen 13Sept/r7
files on disk are not rewritten. A hole of `2.0 mm` or larger is left unchanged.

### Baseline change-control rule

When the operator changes one of these defaults or the 2.0-mm minimum, update
the applicable source and documentation together in the same change:

1. `DENTOWorkflow/Resources/Python/dentobot_workflow/parameter_state.py`
   for the persisted parameter default;
2. `DENTOWorkflow/Resources/UI/DENTOWorkflow.ui` for the visible default and
   UI minimum;
3. the owning normalization/preflight/generator path, including
   `DENTOWorkflow/Resources/Python/DENTOGuideGeometry.py`,
   `dentobot_workflow/widget_template_build.py`,
   `dentobot_workflow/logic_guide_support.py` or the Step-4C docking module as
   applicable;
4. the focused automated fixture/test and
   `Testing/verification_matrix.json` when the selected check changes; and
5. this baseline, the linked `DECISIONS.md`/`TASKS.md` contract and the dated
   logbook evidence.

Never change only workflow code and leave the static context or UI stale.
Verify source/UI parity and the hard-bound test before using a changed value;
do not mutate frozen MRBs, cases, collision policy or retained evidence unless
the operator explicitly authorizes that separate action.

## Active modular verification rule (2026-09-15)

Routine `dentobot_workflow` implementation modules have an active **1,600-line
context ceiling**. `Testing/test_modular_structure.py` owns this check; the
public entrypoint remains capped at 500 lines, and the existing import,
CMake-install and process/network-boundary checks remain in force. The
intentional `runtime.py`/`slicer_tests.py` exemptions remain unchanged.
`widget_template_build.py` is currently 1,520 lines and therefore passes the
relaxed bounded rule; this is not a blanket exemption or permission to grow
without limit. The API contract remains checked against
`Testing/contracts/dentoworkflow_api.json`.

## Where facts belong

| Need | Authority |
|---|---|
| Pending work / order / next acceptance / overlaps | backlog.md |
| Detailed task contract / completion record | TASKS.md |
| Behavior and acceptance plan | DEVELOPMENT_PLAN.md |
| Decision and explicit supersession | DECISIONS.md |
| Implemented component ownership | ARCHITECTURE.md |
| Environment / release setup | SETUP.md; Workspace/LAB_RELEASE |
| Evidence procedure / exact traces | REPRODUCIBILITY_AND_TRACEABILITY.md; dated logbook |
| Agent/model/permission rules | AGENTS.md; AGENTIC_VERIFICATION_PROTOCOL.md |

Checkout: `/home/light-tarun/dentobot/ros2_ws/src/DentoBot`.
The Ubuntu overlay root is not the development Git checkout.
Preserve all uncommitted work. MRML is geometry authority; source CBCT and
world-RAS/mm conventions remain unchanged. Never infer live validity from
saved evidence. Engineer-owned records are excluded unless specifically named
and authorized. No commit, push, external sync or runtime action follows merely
from reading a roadmap.

A concise daily entry records operator observation, decision delta, changes,
commands/results, evidence limits and next action. Repeated histories belong
neither here nor in the active work order.


## 1 October — checkout correction and consolidation direction (supersedes preceding routing)

Operator corrected his earlier recollection: reviewed performance integration happened in DentoBot-step6-5.10-integration, while he continued newer development in DentoBot-step6-renovation. He now directs future implementation onto the integration branch, with Step6 development retaining the accepted performance changes. Earlier same-day assertions that integration completed into renovation, or that the newest manual watchdog session proved failure of the combined integration code, are withdrawn. The measured stalls remain valid observations; deployed-checkout attribution is unconfirmed.

Read-only Git evidence: integration/step6-5.10-reviewed-20260927 HEAD a795f89 includes immutable renovation checkpoint e7cd29f plus 14 subsequent integration commits. Renovation HEAD remains e7cd29f with substantial tracked and untracked later Step6 and DentoCase work. Integration has separate dirty documentation. Project DentoCase contract currently routes implementation to renovation; its production code is there. Neither tree may be overwritten, reset or blindly copied.

Direction: integration is the intended consolidated development target. First let the active DentoCase operation reach a stable checkpoint, preserve both complete development deltas, then reconcile renovation changes relative to e7cd29f against the existing integration corrections. Retain source-only/unaccepted states and focus verification on actual overlaps; no main promotion, runtime, 5.12 work or acceptance is inferred. The existing integration preparation contract governs transfer mechanics, superseded only as to future development target; backlog remains the sole pending queue. Performance upgrades requested the active DentoCase chat to hold further writes after its current bounded operation and report ownership/evidence before transfer. Actual transfer has not yet occurred.

## 1 October — approved consolidation and DentoCase completion

Tarun agrees to and approves the proposed consolidation and complete DentoCase goal, with up to four GPT-6 Luna Max workers apart from the orchestrator. Available concurrency remains three workers plus coordinator; four disjoint worker scopes are scheduled with the fourth following a released slot. This supersedes the earlier transfer hold for this bounded consolidation and moves future development to DentoBot-step6-5.10-integration, branch integration/step6-5.10-reviewed-20260927. Main promotion/publication, 5.12 and robot/hardware actions are excluded. Offline full/partial persistence verification is approved by the agreed plan; runtime resources remain serialized and existing operator processes preserved.

Git evidence: integration a795f89 already contains renovation e7cd29f; no renovation commits are missing. Later source/test changes are uncommitted. Both development deltas preserved in /tmp/dentocase-consolidation-20261001 with binary patches, development-only archives and SHA manifests; engineer-owned records/generated output excluded. Forty-two clean candidate source files applied and five conflicts resolved under coordinator dispositions. Accepted performance ports, strict restoration and method splits retained. No branch/HEAD change, stage, commit, main merge or rebuild performed during parallel work.

Owned worker scopes: robot-shell/manual method reconciliation; headed runner/source/planning tests; new case inventory ownership adapter/test; DentoCase catalog fixture correction. Coordinator owns remaining DentoCase persistence/projection/bootstrap/lifecycle/semantic inventory changes, verification matrix, source review, runtime and controlled records. No worker executes Slicer/ROS/build/runtime or edits controlled records. Current pending states remain under DCP-09..10, S6-REUSABLE-CASE-SETUP, S6-P2-01, S6-LIVE-01 and S6-P2-03. Source consolidation does not close native or operator acceptance.


## 1 October — permanent performance-monitoring chat ownership

Operator confirms consolidation completed and assigns Performance upgrades chat permanently to container/DENTOBOT runtime performance monitoring and periodic bounded corrections. Current development target is DentoBot-step6-5.10-integration / integration/step6-5.10-reviewed-20260927. Use existing S6-P2-03 and S6-U-01, backlog as sole queue, and PERFORMANCE_MONITORING.md as standing policy. This supersedes older renovation-routing/transfer-pending summaries; source consolidation does not imply runtime acceptance. Existing daily reviewer remains; do not create duplicate monitoring jobs.

Collector capability verified by reading Workspace/scripts/dentobot-resource-watchdog.py: default five-second sampling, container-visible process RSS/CPU/threads/FDs and zombies, host/Linux-kernel MemAvailable/SwapFree/load/CPU-memory-I/O PSI, cgroup memory/OOM/CPU-throttle/PID/pressure, and free capacity on the log filesystem. It does not collect disk byte throughput/device latency/utilization, paging/swap-in/out rates, all-host process attribution, GPU/VRAM, or Windows host resources outside the WSL kernel. Shorter-than-sample spikes can be missed. Resource correlation supports investigation but does not alone prove the blocking call or leak. Preserve this evidence boundary in future reviews.


## 1 October — bounded Ubuntu performance implementation plan

Operator requests an elaborate implementation plan. Existing S6-P2-03, S6-U-01 and platform-transfer owners retain scope/priority. Contract appended to diagnostics/PERFORMANCE_INTEGRATION_AUDIT_2026-10-01.md: three finite increments—action/runtime identity plus low-cost paging/disk counters; one responsive explicit-start workspace planning path with frozen native ownership/correlation interface; nativeUbuntu NVIDIA profile port. Exact files, two disjoint LunaMax implementation lanes per qualifying increment, cheapest checks, proposed measurable acceptance and stop conditions recorded. No code/test/build/runtime/main/5.12 execution authorized by this planning turn. Prior native synchronous-call exposure is not universal freeze attribution. Windows/WSL remains a distinct later campaign.


## Performance increment 1 checkpoint — 1 October 2026

Shared UI action attribution, sanitized paired session provenance and Ubuntu paging/per-device I/O counters are implemented on the integration checkout; 26 host/fake-Qt/shell-stub tests passed. Source helpers frozen/reviewed and DentoCase chat notified that cooperative runtime hold is released within its own existing approval. Actual Slicer identity/collector overhead/clean-exit gate remains pending; no real runtime or native build in this increment. Continue existing S6-P2-03 three-increment contract, not a new plan; 5.12 indefinitely held and Windows/WSL separate. See PERFORMANCE_MONITORING.md and diagnostics/PERFORMANCE_INTEGRATION_AUDIT_2026-10-01.md.


## S6-P2-03 increment2 native source checkpoint — 1 October 2026

Four async native methods now implemented in verified isolated5.10 motion-control pair and matching canonical SlicerROS2 source; previous interrupted/unwritten status superseded. Python242host checks passed, scoped whitespace checks passed. Native compilation/wrapper/lifetime/runtime/deployment pending separate approval; installed library still lacks new API. Cancelled local authority is revoked with best-effort backend cancellation and node-recreation requirement. Source-complete does not accept responsiveness or change5.12 hold. See today logbook/performance audit for hashes/ownership/commands. NativeUbuntu NVIDIA item3 unstarted.


## S6-P2-03 increment2 deployed checkpoint — 1 October 2026

Supersedes earlier unbuilt status: isolated single-job5.10 compile/wrapper/install passed; focused empty-scene explicit-start plan SUCCESS12points,0.108s/maxQtgap56ms, consumed reply/disconnect and Slicerexit0. Reviewed native library and identical wrapper installed into normal shared checkout package after backup; independent shared-package API probe loaded all four methods and exited0. Details/hashes/commands in today logbook and PERFORMANCE_INTEGRATION_AUDIT_2026-10-01.md. This is bounded API/software integration evidence. Representative long-wait/cancellation/ordinary-window responsiveness remains open; backend MoveIt shutdown-11 reproduced separately under S6-U-01. Watchdog paired overhead and NVIDIA increment3 pending;5.12 held.


## S6-P2-03 increment3 source/test completion — 1 October 2026

Native Ubuntu NVIDIA profile now implemented on the integration checkout. Explicit nvidia rendering uses GPU reservation independently of cpu/cuda inference and clears Mesa DRM device mapping. Bounded10s host driver/Docker-runtime and container device-visibility checks provide actionable errors; device enumeration does not establish OpenGL acceleration. Existing auto/Mesa/WSL behavior, selected checkout routing and watchdog metadata preserved. Imported native profile/probe portions only from137a56e; CUDA graphics/display capabilities were already equivalent; WSL changes excluded.

Verification: pure.ubuntu_graphics_profiles,13host/mock tests passed in0.08s exit0; shell syntax, owned Python syntax, scoped whitespace and frame-probe --self-check passed. Tests cover MesaCPU/CUDA, NVIDIACPU/CUDA, WSL baseline selection, missing command/driver/runtime, container visibility, invalid mode, DRM reset/capabilities and source routing. Evidence /tmp/dentobot-verification/perf-increment3-20261001/{host.log,frame-selfcheck.log,summary.json,launcher-port.diff}. No actual GPU/Docker/container/Slicer/ROS runtime, image/native rebuild, case save or hardware action. Operator explicitly excludes GPU verification on this workstation; >=60FPS and renderer verification remain deferred to approved NVIDIA hardware.

All three finite increments now have source implementations. Item1 paired watchdog overhead/identity evidence and item2 representative long-wait/cancel/normal-window responsiveness remain open under existing S6-P2-03; item3 hardware acceptance deferred. Backend MoveIt cleanup-11 remains S6-U-01. No new increment, no5.12 restart, no main merge/push/commit.


### 4 October UTC07:11 — S6-LIVE-01 approved isolated sampling trial result
Operator “approved” authorized one domain74 SIMULATION-ONLY request at OMPL fraction0.0005 (original0.005), stop first valid result. Corrected geometry-verified copy TIMED_OUT5s, error99999/zero points; original scene unchanged and final PID3122/Home3/Base/snapshot/options unchanged, no motion. Earlier missing-overlay copy result134 excluded; known burr/template collision canary0.286936408427mm matched original. Copy stopped/domain74 empty (SIGINT cleanup crash139 retained). Evidence planner-resolution-20261004T070243Z,135/136 and logbook. NeitherA/B nor physical minimum certified. Next reviewable hypothesis is one30s plan-only copy request with all other settings identical; not executed or deployed. Original109/121/124 ceiling persists. Tarun verdict PENDING.
