# Step 6 five-DOF detailed acceptance checklist

## 1 October 2026 — operator workflow recovery contract (latest supersession)

**Status correction:** source/host evidence below remains valid, but requested6.1/6.2 workflow/UX completion is reopened after operator dissatisfaction and manual blockers. Do not treat the remaining work as only user confirmation. Follow [the latest bounded recovery contract](STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md): read-only diagnosis first, no new runtime implied, observable setup-to6.3 demonstration required before UX completion.


## 1 October 2026 — implementation closure and engineer handoff (operator-approved supersession)

The operator stopped the autonomous successful-planner/whole-run goal and approved **source/host checks followed by Tarun's engineering trials**. This supersedes earlier automatic campaign sequencing, not the guard policy or outstanding runtime acceptance. Do not launch a new Slicer/ROS/MoveIt/planner/preview trial for this pass. A no-solution planner result is a valid diagnostic outcome only when sufficient exact evidence is retained and state remains safe; it is not proof of infeasibility.

Existing owners remain S6-LIVE-01, S6-WORKSPACE-PURPOSE, S6-LIVE-03/04, S6-REUSABLE-CASE-SETUP and S6-P2-03. Close concrete source gaps: non-finite diagnostic metrics, explicit failed-pose read-only FK/static inspection, diagnostic display cleanup, existing-layout clipping and actionable disabled-state explanations. Reuse five-joint state/guard, Base/Home, historical recording/persistence and preview owners; no new robotics framework or parameter tuning. Implementation closure is source/host verified: 469 combined checks passed on 1 October; Python compilation and git diff --check passed. Failed-pose inspection, finite metrics, diagnostic ownership/cleanup, layout wrapping and blocked-action guidance are corrected at this boundary. Rendered GUI and native robotics acceptance remain pending; exact commands and evidence are in the handoff index and dated logbook.

Reuse bounded r22 TCP, r26 uncertainty/reconciliation, r29 offline-to-connected setup and r30 fresh-reopen evidence at their actual scopes. R31 ended 16 PASS / 1 FAIL / 12 NOT_RUN: all14 PreEntry searches reached iteration_limit, exact target/failed-pose evidence retained; P1/complete-plan/preview NotRun, inferior exit1 with signal null, partial video preserved. Earlier campaign verdicts are unchanged. Native positive full-chain/preview/interruption/Return Home/repeat, final post-campaign save/reopen, normal-window responsiveness and Tarun's robotics/usability verdict remain **PENDING**. The conditional ±20mm in-plane Base note awaits reviewed plane basis and budget; performance integration remains deferred.

Feature/evidence handoff: [STEP6_IMPLEMENTATION_HANDOFF_2026-10-01.md](STEP6_IMPLEMENTATION_HANDOFF_2026-10-01.md). Backlog remains the sole pending queue; this amendment creates no task IDs or parallel implementation plan.


**Date:** 2026-09-28
**Owner:** `S6-LIVE-01`, with `S6-LIVE-03/04` for interruption, Return Home and replay
**Source:** `/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-renovation`
**Branch:** `feature/step6-workflow-renovation-20260925`
**Pre-refactor checkpoint:** `84234a6`
**Authority:** simulation and research evidence only; no hardware, powered drill,
patient-facing action or route authority from a manual or partial path.

This checklist is the **latest implementation and execution plan** for the
automated headed GUI simulation campaign under the existing `S6-LIVE-01`
backlog item. It supersedes older campaign sequencing where they conflict; it
does not create a second pending-work queue. Update `Workspace/docs/backlog.md`,
`TASKS.md` and the dated logbook with resulting evidence. Do not infer Tarun's
robotics or usability verdict from an automated run.

**30 September checkpoint:** Recorded r6 passed the bounded Base/Home,
workspace, one guarded J1, history and save slice, creating
`sept30_fdi11_step6_3_demo_ready.dentocase` (SHA-256
`539ee7948bd97434ab4ef8b675e1540f065219a7e5250c3a422d2cfb481c371a`)
with complete zero-exit video. Fresh-process r7 strictly reopened that case
and seven robot models with exit 0. Neither run exercised case-bound TCP,
planner or preview. The subsequent r8 campaign stopped before those checks;
instrumented r9/r10 recorded intermittent native Slicer SIGSEGV 11. Their
partial videos and diagnostics are retained. The three-failure ceiling stops
further autonomous case-bearing runtime retries pending a specific native
debugging strategy and Tarun's direction. The checkboxes below remain the
representative final-campaign acceptance list; the r6/r7 slice does not mark
unreached items complete. Source-only mouse delivery and failed-probe report
accounting pass 64 focused host tests. Tarun's normal-window verdict remains
PENDING. See the [30 September logbook](../logbook/2026-09-30.md).

## 0. Orchestration for this campaign

**R18/r19 continuation:** R18 captured the asynchronous Python traceback-dump crash; the watchdog scheduling owner was removed and 84 host checks passed. R19 completed workspace and ordinary Base/Home without SIGSEGV, then passed real case-bound TCP drag, ten Cartesian buttons and three key nudges. Its first failure was the text-editor focus fixture; cleanup also misclassified the preexisting passive target. The partial recording/diagnostics remain evidence. Valid/invalid IK, complete TCP cleanup/reentry and full-chain gates remain unaccepted until the corrected bounded run passes.

**30 September approved continuation:** One GDB-instrumented workspace-only r15 passed, with Slicer exit 0 and validated whole-process recording. The earlier SIGSEGV was not reproduced or fixed. Proceed through the approved focused case-bound workbench gate and then full-chain gate only as prerequisites pass. Remaining checkboxes retain their evidence requirements; the original diagnostic report's unfinished top-level status is documented separately and does not imply a full checklist pass.

- Sol owns requirements, architecture, task splitting, runtime strategy,
  controlled records, integration, diff review, serialized Slicer/ROS/MoveIt
  execution and acceptance.
- Tarun authorizes up to **four GPT-6 Luna Max workers simultaneously** for
  this task when bounded implementation or host-test work benefits from them.
  Use the smallest useful number; do not create workers merely to reach four.
- Every Luna assignment must have disjoint file ownership, a complete interface
  contract, invariants, forbidden changes and the smallest meaningful check.
- Luna workers preserve all unrelated edits, do not recursively delegate, do
  not edit controlled project records and do not declare acceptance.
- Luna workers may run assigned source/host tests on stable files. They do not
  own headed Slicer, ROS, MoveIt, case mutation or other exclusive runtime
  resources; Sol serializes those gates.
- The current agent platform exposes four total concurrent slots including Sol,
  so at most three Luna workers can actually run beside Sol in this session.
  A fourth permitted worker may be used after another finishes. If capacity or
  Luna Max availability is lower, report it rather than substituting a model.

## 1. Current evidence that does not need repetition

- [x] The current URDF has exactly five movable positioning joints, J1–J5.
- [x] Spindle housing, burr geometry, collisions and `dentobot_drill_tcp` are
  retained through a fixed burr attachment.
- [x] Home, task limits, guard, FK/IK, joint-state publication, workflow state,
  UI and new persistence records use exactly J1–J5.
- [x] Extra joint values fail exact-shape validation instead of being silently
  truncated.
- [x] The indexed five-DOF host selection passed 394 tests.
- [x] `dentobot_description` and `dentobot_moveit_config` built in an isolated
  overlay; installed and source URDF SHA-256 values matched.
- [x] A private-domain runtime passed five-value guard acceptance, exact J1–J5
  state, collision-valid state, TCP TF and five-joint IK.
- [x] The no-case 6.3B headed gate proved default-off TCP probe activation,
  mouse dragging, Cartesian button nudges, five-joint position-axis solve,
  draft staging, accepted-state separation, disable cleanup and no
  route/preview authority.
- [x] Earlier case runs proved one accepted guarded J1 jog, detached Base
  stage/cancel/zero-displacement accept, current-pose Task Home accept, invalid
  draft inspection and historical export/reopen.
- [x] Connected no-case Slicer shutdown is verified clean. Older partial videos
  remain failure evidence and must not be overwritten.

### 1.1 Current exact-case load status

- [x] The saved/current profile difference is identified as the exact two-URDF
  six-to-five-DOF transition; all other 19 component records match.
- [x] Exact hash-bound migration, fresh restored parameter-node routing and
  post-hydration-audit migration ordering pass 73 focused host tests plus
  compile and diff checks.
- [x] The operator's later explicit resume authorized a new, bounded headed
  attempt. r15 passed strict load and the final ordering correction; preserve
  the earlier failed directories ending `T122153Z-r1`, `T131742Z-r2` and
  `T132323Z-r3` as failure evidence.
- [x] r15 created the planned five-DOF case through production save. r16
  qualified it by strict fresh-process reopen. See their run-local diagnostics
  and the 29 September logbook. Offline reopen deliberately clears live task
  confirmation and marks saved Home `Unreviewed` pending new-session validation.

## 2. New five-DOF DentoCase to create

### 2.1 Planned output

Save a **new package**, without overwriting the supplied or previously tested
cases:

`/home/light-tarun/dentobot/data/Slicer_Saved/SampleStudy1/SEPT24/sept28_fdi11_step6_five_dof_acceptance.dentocase`

This file was saved through the current workflow after five-DOF robot, Base
and Task Home review, then reopened in a fresh Slicer process. Its SHA-256 is
`d5a0e7bb13ebeda00e5cf9702ce1657f63c074359c833868678805dd854ff090`.
It is a qualified **offline starting fixture**; it does not carry live ROS,
current task confirmation, validated Home or preview authority across reopen.

### 2.2 Source and identity requirements

- [x] Start from the operator-reviewed FDI11 case family; preserve the original
  `.dentocase` byte-for-byte.
- [x] Record the source case absolute path and SHA-256 before opening it.
- [x] Record checkout path, branch, HEAD, dirty-diff identity, container/image,
  ROS domain, native source SHA, guard binary SHA and package prefixes.
- [x] Confirm the selected tooth/target is FDI11 and the active PreparedBranch
  belongs to the same target.
- [ ] Confirm Case Foundation, jaw opening, PreparedBranch, Step 5C/final
  template and selected trajectory are `Current`/verified under their owning
  contracts.
- [x] Confirm the displayed anatomy is the opened planning view: the closed
  source segmentation is hidden and opened proxies are visible.
- [x] Confirm the task is explicitly selected and confirmed before saving. A filename or old
  saved confirmation is insufficient.
- [ ] If an older six-value Home or robot record is reported incompatible,
  preserve that failure as migration evidence, then create a fresh current
  J1–J5 Home through the UI. Do not edit the archive or truncate the record.

### 2.3 Create the current robot state before saving

- [x] Load the production robot and confirm only J1–J5 appear as arm controls.
- [x] Import the planning context and connect the simulation-only ROS/MoveIt
  stack.
- [x] Confirm the robot description, native guard and monitored state all
  report the same ordered five joint names.
- [x] Review the current Base as a detached candidate; verify staging does not
  change the accepted Base or ROS scene.
- [x] Accept Base through the production owner only after native scene
  acknowledgement. Record matrix, fingerprint, revision and lock state.
- [x] Set the desired current J1–J5 draft and run **Check Draft State**.
- [x] If the desired Home differs from the accepted robot, use **Guarded Jog**
  and require an exact acknowledged five-value accepted-state echo first.
- [x] Review the exact accepted current pose as Task Home. Verify the candidate
  remains detached until **Accept Task Home**.
- [x] Accept Task Home through the production owner; record revision, Base
  fingerprint, robot-profile fingerprint, guard policy and validation status.
- [x] Reconfirm the selected task after any Base/Home invalidation.
- [x] Save to the planned new path. Record output SHA-256 and size.

### 2.4 Fresh-process qualification of the new package

- [x] Close the creating Slicer process cleanly and verify owned-process
  cleanup.
- [x] Reopen the new package in a fresh Slicer process from the exact checkout.
- [x] Verify strict post-hydration validation passes without archive repair.
- [x] Verify the case lands at the saved Step 6 stage. The exact 6.x substep
  remains for the representative campaign.
- [x] Verify FDI11, active branch, opened anatomy, reviewed simulation Base,
  five reviewed limits and saved task/Home provenance match the bundle. Verify
  separately that offline reopen clears live task confirmation and changes Home
  from saved `Validated` to live `Unreviewed`; new-session validation is required.
- [x] Verify no sixth arm field/control/value is hydrated.
- [x] Verify ROS remains disconnected until explicitly connected.
- [ ] Verify historical/manual records reopen as display-only and cannot alter
  the live accepted robot, Home, route or preview state.
- [x] Record the qualified offline case path and SHA-256 in run-local diagnostics,
  logbook and `S6-LIVE-01` records.

## 3. Detailed headed campaign on the new case

Run one serialized campaign with whole-process recording. Stop on the first
causal failure or unknown safety result. Preserve the saved package and every
failed attempt.

### 3.1 Preflight and recording

- [ ] No operator-owned Slicer, ROS, MoveIt, guard, build or recorder process is
  active.
- [ ] Exact source, native binary, package prefix and case SHA-256 provenance is
  captured before launch.
- [ ] Use a fresh evidence directory and the indexed screen recorder; do not
  reuse an output directory.
- [ ] Start one ROS simulation stack and one headed Slicer process only.
- [ ] Record the entire application window, including startup, case reopen,
  checks and clean shutdown.
- [ ] Create itemized JSON, state-matched screenshots, complete logs, cleanup
  JSON, video manifest and a SHA-256 manifest.

### 3.2 Case, scene and five-DOF model

- [ ] Strict case reopen passes with current Case Foundation, branch, task and
  final-template identity.
- [ ] Opened anatomy is visible and the closed source model is hidden.
- [ ] The robot and collision scene load through production controls.
- [ ] The scene acknowledgement reports expected objects and current identity.
- [ ] UI, monitored joint state, guard request/status and IK results contain
  exactly J1–J5 in canonical order.
- [ ] Spindle/burr geometry and canonical TCP are visible and transform
  correctly, but no drill-speed or sixth arm control appears.

### 3.3 Draft, accepted and monitored state separation

- [ ] Move one slider and verify only the draft/ghost changes.
- [ ] Enter a numeric value and verify the same draft updates without advancing
  accepted or monitored state.
- [ ] Use each J1–J5 slider/numeric row at least once within reviewed limits.
- [ ] Verify mechanical and reviewed limits are displayed with correct units.
- [ ] Run **Check Draft State** and capture limits, static validity, FK/TCP and
  drill-axis evidence.
- [ ] Verify Check Draft State sends no jog and grants no route/preview
  authority.
- [ ] Reset draft to the exact accepted state and verify equality.

### 3.4 Physical keyboard interaction

- [x] Explicitly enable keyboard joint controls.
- [x] Exercise the documented positive and negative key for each J1–J5 control.
- [x] Verify step-size selection changes the draft by the displayed amount.
- [ ] Verify focused text/numeric controls suppress shortcuts. The r19 headed check
  passed numeric-editor focus and normal arrow editing; text-editor focus is
  still source checked only.
- [x] Verify auto-repeat does not cause uncontrolled repeated requests. The
  r19 headed check observed all ten shortcuts with `autoRepeat=False` and zero
  guard requests; a sustained held-key responsiveness trial remains separate.
- [x] Verify disabling keyboard controls immediately stops shortcut handling.
- [x] Confirm keyboard changes remain draft-only until Guarded Jog.

The recorded r19 draft-only runner item passed after r17/r18 test-script
canonical-name failures were fixed. See each run-local `diagnostics.md`, video,
JSON and SHA-256 manifest. Accepted/monitored state, guard requests, planner
calls and preview stayed unchanged; this does not accept the full workflow.

### 3.5 Guarded jog outcome matrix

#### Accepted

- [ ] Submit one small in-limit J1–J5 draft.
- [ ] Correlate request ID, session ID, exact requested vector, task/scene
  identity and native policy fingerprint.
- [ ] Require authoritative guard acknowledgement before accepted state changes.
- [ ] Verify accepted, monitored, displayed and echoed states converge exactly.
- [ ] Record interpolation samples, clearance evidence and TCP/drill-axis sample.

#### Rejected

- [ ] Select a deterministic in-mechanical-range candidate known to fail the
  authoritative native guard for the current scene. Do not tune geometry or
  safety margins to manufacture it.
- [ ] Verify the requested and evaluated candidate, named collision/limit
  evidence and rejection reason remain visible.
- [ ] Verify accepted, monitored and displayed live state do not advance.
- [ ] Verify the rejected event is appended to the ordered record and starts no
  route or preview.

#### Invalid before submission

- [ ] Select a reviewed-limit overstep that remains within mechanical display
  bounds.
- [ ] Verify it is inspectable as an invalid draft, Guarded Jog is disabled and
  no raw request is published.
- [ ] Restore the draft to accepted state before continuing.

#### Unknown or stale acknowledgement

- [ ] Use a dedicated simulation test hook or runner-controlled stale/mismatched
  response. Do not create this condition by killing shared ROS processes during
  an operator command.
- [ ] Verify the UI preserves requested vector, request/session identity,
  failure evidence and the previous confirmed accepted state.
- [ ] Verify further jogs are blocked while reconciliation is required.
- [ ] Verify no rollback/teleport command is guessed.
- [ ] Run **Reconcile State** and require exact monitored/native/current scene
  identity before clearing the latch.
- [ ] If reconciliation cannot prove the state, retain `unknown` and stop this
  campaign path. A runtime unknown-test hook is still an implementation task if
  no safe indexed hook exists when the campaign begins.

### 3.6 Detached Base review and reconciliation

- [ ] Stage a translated/rotated Base candidate as a detached ghost.
- [ ] Verify accepted Base, live robot and ROS collision scene remain unchanged.
- [ ] Cancel review and verify only the candidate is removed.
- [ ] Repeat with the exact current Base and accept through the production
  owner; require scene resynchronization acknowledgement.
- [ ] Verify dependent Home/task/plan evidence invalidates only as specified.
- [ ] Exercise a runner-controlled uncertain Base acknowledgement and verify
  repeat accept/cancel is blocked pending **Reconcile Base State**.
- [ ] Reconciliation may clear only after exact matrix, scene and fingerprint
  agreement; otherwise retain unknown evidence.

### 3.7 Detached Task Home review and reconciliation

- [ ] Stage the accepted current J1–J5 pose as a detached Home candidate.
- [ ] Verify stage/cancel changes neither accepted Home nor robot state.
- [ ] Accept through the production owner and require live/static/guard
  validation plus current Base identity.
- [ ] Verify the saved Home has exactly five ordered values and a new revision.
- [ ] Exercise a runner-controlled uncertain Home acknowledgement and verify
  repeat accept/cancel is blocked pending **Reconcile Task Home State**.
- [ ] Reconciliation may clear only after exact Home, monitored state, Base,
  scene and policy identity agreement.

### 3.8 TCP exploration and viewport dragging

- [ ] On entry to 6.3B, **Enable TCP Drag** is off and no draggable goal probe
  exists.
- [ ] Enable it explicitly and require synchronous native acknowledgement.
- [ ] Drag the TCP goal sphere in the viewport and verify the ghost robot updates
  responsively without moving the accepted robot.
- [ ] Exercise world-RAS X/Y/Z translation buttons in both directions.
- [ ] Exercise local drill-axis pitch and yaw buttons in both directions.
- [ ] Confirm axial roll is identified as unconstrained by the five-DOF arm and
  no roll or drill-speed control is presented as an arm joint.
- [ ] Enable TCP keyboard nudges and exercise translation, pitch and yaw keys,
  including focus and auto-repeat suppression.
- [ ] Verify failed/unreachable/colliding IK remains an inspectable ghost with
  diagnostics and cannot stage or advance accepted state.
- [ ] Run explicit collision-aware **Solve IK** on a valid goal; require exactly
  five finite joints before staging the draft.
- [ ] Verify Solve IK remains draft-only; use Guarded Jog separately if an
  accepted move is desired.
- [ ] Disable TCP Drag and verify probe, goal robot and observer are removed.
- [ ] Leave and re-enter 6.3B; verify the probe remains default-off.

### 3.9 Ordered recording, export and historical reopen

- [ ] The live ledger contains requested, accepted, rejected and unknown events
  in request order with distinct identities.
- [ ] Each available event retains native guard evidence, accepted/monitored
  state, TCP point and drill-axis sample; unavailable fields are explicit.
- [ ] Accepted path segments break at rejected or unknown events.
- [ ] Export the production JSON/report and record both hashes.
- [ ] Open the exported record through the historical display-only owner.
- [ ] Step through every event and verify only historical ghost/path display
  changes.
- [ ] Verify import/replay cannot change live joints, Base, Home, guard session,
  task confirmation, route authority or preview state.
- [ ] Save and reopen the `.dentocase`; verify the record persists with the same
  order and remains display-only.

### 3.10 Two-area UI and responsiveness

- [ ] Planning & Diagnostics contains Home review, workbench, workspace,
  P1/P2/P3 and automatic planning owners.
- [ ] Preview & Control contains the single guarded Preview/Stop/Return set.
- [ ] Both navigation paths expose the same action owners and locked reasons.
- [ ] At 1920×1080 normal-window size, all primary controls can be reached
  without horizontal clipping; record scroll ranges and control rectangles.
- [ ] Capture readable screenshots of joint controls, Base/Home review, TCP
  controls, invalid/rejected/unknown evidence and Preview controls.
- [ ] Measure separately: slider-to-ghost latency, TCP drag/FK latency, ROS
  acknowledgement latency, guard latency and viewport frame behavior.
- [ ] Record median, p95 and worst observed latency. Compare ordinary direct-
  display interaction against the 60 FPS target without claiming a hard safety
  guarantee from frame rate.
- [ ] Confirm long operations show progress and do not leave controls falsely
  enabled or the UI permanently frozen.

### 3.11 Full-chain authority and interruption

- [ ] Reconfirm exact current case, branch, task, Base, Home, tool/TCP,
  orientation and guard-policy identity immediately before planning.
- [ ] Run P1/P2/P3 diagnostics and confirm they remain display-only.
- [ ] Verify a partial Home→PreEntry, PreEntry→Entry or Entry→Target path cannot
  enable Preview.
- [ ] Produce one fresh complete Home→PreEntry→Entry→Target chain with endpoint
  FK and independent full-chain guard evidence.
- [ ] Verify only that complete current chain enables Approach/Drill preview.
- [ ] Start guarded Approach preview and verify ordered accepted acknowledgements.
- [ ] Interrupt after at least one accepted motion sample. Verify the accepted
  prefix and any rejected/unknown request remain visible.
- [ ] Verify normal Return Home is blocked after interruption and no teleport or
  guessed rollback occurs.
- [ ] In a separate fresh run, complete Approach, drilling preview, axial
  withdrawal and guarded Return Home.
- [ ] Repeat the complete guarded cycle from fresh current evidence as required
  by `S6-LIVE-03/04`.
- [ ] Verify Preview never exposes a controller, hardware execution or powered
  drill path.

### 3.12 Final save/reopen and shutdown

- [ ] Save a new post-campaign copy; never overwrite the qualified input case.
- [ ] Record its path, SHA-256, size and relationship to the qualified input.
- [ ] Freshly reopen it and verify case/task/Base/Home/five-DOF/record identity.
- [ ] Verify no transient preview-active, pending guard or unknown acceptance is
  silently promoted during save/reopen.
- [ ] Exit Slicer normally; require process exit 0 and recorder/FFmpeg exit 0.
- [ ] Verify no owned Slicer, ROS, MoveIt, guard, recorder or Xvfb process remains.

## 4. Automated checks to run around the campaign

Use `Testing/verification_matrix.json`; do not invent an alternate suite.

### Before creating the case

- [ ] `static.git_diff_check`
- [ ] `static.step6_pycompile`
- [ ] `pure.five_dof_robot_contract`
- [ ] `pure.step6_manual_tcp_workbench`
- [ ] `pure.screen_recorder`
- [ ] `build.five_dof_robot_model` only if the owning source/build identity has
  changed since the recorded isolated build.

### Bounded headed happy-path and evidence check

- [ ] `runtime.step6_headed_review` with exact renovation provenance, the newly
  qualified case SHA-256, invalid-draft opt-in, one accepted jog,
  export/reopen and Base/Home acceptance opt-ins.
- [ ] Reuse its already implemented checks; do not make it own planner or
  preview authority.

### Additional runner work required before the complete campaign

- [ ] Add or index one safe native rejected-jog scenario if a deterministic
  current-scene fixture is not already available.
- [ ] Add or index one controlled stale/unknown acknowledgement and
  reconciliation scenario for jog, Base and Home. This must be simulation-only
  fault injection and must not kill shared ROS mid-command.
- [x] Add physical keyboard-event coverage. The opt-in r19 runner delivered
  physical Qt key events and passed the bounded J1–J5 draft-only gate.
- [ ] Add itemized responsiveness measurements and screenshot framing to the
  final campaign runner.
- [ ] Add a case-bound full-chain preview/interruption section or use the
  existing exact-case runner only after its case and five-DOF assumptions are
  reviewed against this fixture.

## 5. Required evidence package

- [ ] `result.json` with every checklist item `PASS`, `FAIL`, `BLOCKED` or
  `NOT_RUN` and the first causal failure.
- [ ] Whole-process video with a `complete` manifest.
- [ ] State-matched screenshots for each materially different state.
- [ ] Full Slicer, ROS/MoveIt, guard, recorder and cleanup logs.
- [ ] Input and output case hashes and exact source/native/package provenance.
- [ ] Exported manual-motion JSON/report and hashes.
- [ ] Responsiveness measurements with definitions and units.
- [ ] `diagnostics.md` comparing planned checks with observed results.
- [ ] SHA-256 manifest covering every retained evidence file and successful
  verification of that manifest.
- [ ] Exact commands/results and evidence boundaries in the dated logbook.

## 6. Stop and verdict rules

- [ ] Stop the dependent path on the first unknown acceptance state, identity
  mismatch, stale case/branch/task/Home/Base, missing guard policy, non-current
  native provenance or cleanup failure.
- [ ] Preserve draft, accepted state and failure evidence; do not retry blindly,
  tune geometry or relax collision policy.
- [ ] Respect the three-failure ceiling and diagnose the first causal failure.
- [ ] Report source/unit, runtime, integration, full-cycle and operator evidence
  as separate levels.
- [ ] Agent completion requires all applicable itemized gates plus a complete
  evidence package. Tarun's later normal-window robotics/usability verdict
  remains **PENDING** until explicitly supplied.

## 7. Immediate next actions

1. Create and fresh-reopen the planned five-DOF FDI11 `.dentocase` through the
   current workflow.
2. Extend the headed runner only for the four uncovered boundaries: native
   rejection, controlled unknown/reconciliation, physical keys/responsiveness,
   and case-bound full-chain interruption.
3. Run the smallest host checks for those runner changes.
4. Run one serialized recorded campaign on the qualified case.
5. Diagnose only the first causal failure, or finalize the evidence package and
   controlled records if every gate passes.

## 30 September r21 bounded interaction and precision checkpoint

Recorded case-bound r21 passed completed viewport drag, ten Cartesian position/orientation buttons, TCP physical keys, numeric/text editor suppression and opt-out/default-off cleanup. Accepted/monitored/displayed state remained unchanged. Exact IK staging failed; full-precision draft backing correction is host-verified (130 focused tests), headed confirmation pending GUI-compaction source freeze. No full planner/preview/new-case/reopen acceptance. R21 diagnostics and partial recording retained; Tarun verdict PENDING.

## 30 September r22 runtime precision confirmation

Exact native five-joint IK draft staging and all selected TCP interaction checks now pass in the recorded case-bearing run:19PASS/0FAIL/6NOT_RUN, Slicer/recorder0, complete bounded video+MP4. Acceptedrobotunchanged, no full taskplan/preview or final newpackage. r22 diagnostics/106-file manifest retained. NegativeIK/native rejected fixture/uncertainBaseHome/fullchain/previewrepeat/finalcase and Tarun verdict remain open.


## 30 September — connected recovery evidence and two-path setup amendment

R26 closes only controlled current-case unknown Base/Home acknowledgement recovery:16PASS/0FAIL/11NOTRUN, exactnativequeryOnlyHome reconciliation and31-objectBase scene acknowledgement, no repeatedcommit/jog, failure retained, allruntime/recorderexits0, complete654.3svideo with107-fileverifiedmanifest. [Run diagnostics](/home/light-tarun/dentobot/data/dentobot-runs/s6-live-01-base-home-uncertainty-20260930-r26/diagnostics.md). Translated/rotatedBase representative checks, fullplanner/preview/newcase andTarunverdict are notinferred.

Latestoperator extends6.1Base/6.2Home tooffline andconnectedsetup; canonicalrenovationplan owns design. Add toexistingcampaign beforefullplanning (allPENDING):

- [ ] Offline localrobot/Base review+accept, exact sharedStep3B/6.1 owner preserved.
- [ ] Offline6.2fivejointdraft review/save asUnreviewed Home boundtoexactBase/profile; noROS/nativepublish/acceptedlive mutation.
- [ ] Invalidmechanical/staleidentity/busy/unknownwrites retainfailure/candidate and blockpromotion.
- [ ] Savea separatelynamedcase andfreshreopen offlineconfiguredHome/Base withnoliveauthority.
- [ ] Connectsameconfiguration: unchangedBase/Home, exactcollisionack/currentprofile, visibleconfiguredversusacceptedstate, explicitHomevalidation.
- [ ] DifferentconfiguredHome neverteleports onconnect; separatelyguardedmove/Plan+Apply gate or clearblockedreason.
- [ ] Disconnect/reconnect/modechange preserveconfiguration andstaleoldreview; revalidationrequired.
- [ ] Shared6.2/6.3draftwidgets haveoneowner, no duplicatecallbacks; connectedreview/unknownreconciliation unchanged.
- [ ] AfterHomeacceptance, refreshworkspace/limits/confirmedtask BEFOREplanner and provecurrentfullchain authority.

This amendment is implemented/verified onlywhen actualsource/host/headedevidence exists; noofflinecollision/IK/trajectoryclaim. Full6.3goal scope remains intact.
