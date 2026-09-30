# Step 6 renovation — weekly update for 29 September 2026

> **Later 29 September correction for the meeting:** The initial status and
> linked PDF below were prepared before Tarun resumed runtime. They remain
> dated history. Recorded r15 created the five-DOF FDI11 case and passed 21
> enabled case/workbench checks; r16 strictly reopened it offline; r19 passed
> the physical J1–J5 draft-only keyboard gate, all with complete recordings
> and clean exits. The current demonstration order and exact evidence are in
> [the meeting checklist](STEP6_MEETING_DEMO_CHECKLIST_2026-09-29.md). Fresh
> case record persistence, case-bound rejected jog, full-chain preview and
> Tarun's normal-window verdict remain open. Do not present the older PDF's
> “runtime halted” or “case not created” wording as current status.

**Meeting-ready PDF:**
[DENTOBOT_STEP6_WEEKLY_REPORT_SEPT29_2026.pdf](../../../output/pdf/DENTOBOT_STEP6_WEEKLY_REPORT_SEPT29_2026.pdf)

**Checkout:** `/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-renovation`
**Branch:** `feature/step6-workflow-renovation-20260925`
**Current HEAD:** `84234a684f026498a5bc28a425b97d13646e7001`
**Scope:** Step 6 workflow renovation and the simulation-only Manual Robot
Simulation Solver / Engineering Workbench.
**Runtime status:** **HALTED by operator.** No Slicer, ROS/MoveIt, Docker
runtime or recorder launch is permitted until a later explicit resume.
**Operator verdict:** Tarun's normal-window robotics/usability verdict remains
**PENDING**.

## Executive summary

The renovation is materially further along than the original planner-first
baseline, but it is not a complete Step 6 acceptance. The current checkout has
an exact five-DOF robot/workflow model, separated draft/accepted/monitored
state, guarded manual J1–J5 actions, detached Base/Home review paths, ordered
manual records, a display-only historical replay path, a two-area workbench,
and an explicit-enable Cartesian TCP workbench. The no-case TCP workbench and
the isolated no-case S6-U-01 shutdown correction have headed evidence.

The current case-bearing campaign reached the corrected restore, workspace,
scene and accepted/invalid manual-jog gates. It then found a real UI ordering
defect before the controlled unknown-result scenario. That defect is fixed and
host-tested. The one prepared retry was blocked before launch by the account
usage/approval limit. It is now preserved as a pre-launch boundary, not treated
as a pass. The named newly saved five-DOF acceptance case does not exist.

The remaining work is therefore clearly bounded: case-bearing runtime
verification of native rejected/unknown/reconciliation paths, physical-key and
measured responsiveness checks, a valid confirmed-task positive preview and
interruption campaign, and Tarun's normal-window engineering verdict. These
runtime items are intentionally paused by the latest operator instruction.

Before the renovation pivot, the same `S6-LIVE-01` work also delivered and
exercised a three-planner comparison workflow for RRTConnect, RRT and RRT*.
That campaign produced useful frozen-identity, timing and first-blocker
diagnostics, but it did not complete a fair three-planner performance
comparison. The detailed evidence and limitations are recorded below.

## Operator decisions and prompts captured this week

1. Renovate the Step 6 engineering workflow before case-specific FDI11/FDI21/
   FDI31 planner solving.
2. Keep the optional 6.3B workbench simulation-only; retain review state,
   accepted robot state, monitored state and route/preview authority as separate
   concepts.
3. Use exactly two GPT-6 Luna Max workers for qualifying bounded grunt work,
   with disjoint files and no recursive delegation. The cap was later raised to
   four workers, but the platform has four total slots including Sol.
4. Remove J6 from the current robot workflow entirely. The pneumatic spindle
   is separate and has no arm joint/IK/planner/Home/guard slot.
5. Test the headed GUI with screenshots and a complete recording, while
   preserving every partial recording as failure evidence.
6. Keep the performance/5.12 checkout separate. It was inspected read-only for
   relevant fixes and was not merged, switched to, committed or pushed.
7. On 28 September, halt runtime testing after the r14 launch was blocked by
   the account usage limit. This report records the halt as the current gate.

## Three-planner comparison workflow and diagnostics

The pre-renovation Step 6.5 workflow added one **Compare Three Planners** action
that runs configured RRTConnect, RRT and RRT* sequentially against one frozen
PreparedBranch, task, Base, Task Home, collision scene and common planning
settings. Ordinary planning or guard failures are retained so the next planner
can run; identity/fatal failures stop the batch. Requested and effective
planner IDs, per-stage diagnostics, checkpoints and display-only saved paths
are retained. Reopened comparison records cannot restore ROS validity,
authorize preview or substitute for a fresh guarded plan.

The associated automation was strengthened during the FDI21 campaign:

- `timeline.jsonl` records UTC and monotonic timestamps, planner/call IDs,
  phase boundaries and durations.
- `checkpoint.json` freezes case, branch, task, trajectory, robot profile,
  Base, Home and collision-audit identity after each completed planner row.
- Planning-server logs provided algorithm-configuration evidence for
  `geometric::RRTConnect`, `geometric::RRT` and `geometric::RRTstar`; the
  configured-ID echo alone was explicitly rejected as proof of execution.
- The comparison identity was corrected to use stable scene-content identity
  instead of treating a new acknowledgement timestamp as a scene change.
- Per-row screenshot/checkpoint capture was added so a later timeout cannot
  erase completed diagnostic evidence.

The bounded FDI21 r6 run reached a complete RRTConnect row. Approach and
PreEntry-to-Entry succeeded, then Stage 3 was rejected at composed waypoint
459 for a non-approved target-tooth-to-pneumatic-spindle collision. It also
reported requested combined insertion of 8.071 mm against a provisional
6.500 mm envelope. RRTConnect consumed about 874 seconds; eight waypoint-guard
calls accounted for 813.39 seconds, while 14 joint-plan calls totaled 4.6
seconds and 14 Cartesian calls 21.97 seconds. This isolated repeated native
guard evaluation as the dominant campaign cost rather than the OMPL joint-plan
call itself.

RRT began, but the 20-minute campaign cap interrupted its second waypoint
guard. RRT* did not run. Therefore r6 is an incomplete diagnostic campaign,
not a relative planner-speed result and not evidence that RRT or RRT* failed.
No combined result package or accepted route was produced. The frozen
checkpoint, timing stream, stack log and Base/Home/selected-row screenshots are
preserved under
`data/dentobot-runs/step65-three-planner-fdi21-31-20260923/fdi21-r6/`.

The follow-on display-only collision recapture generated inferior, apical and
oblique images, but Tarun correctly rejected them as collision evidence. The
recapture had applied the lower-jaw opening transform to an upper-jaw target
that production keeps fixed, displacing the displayed tooth by about 13.54 mm
from the spindle reconstruction. A fail-closed overlap check was added so
separated reconstructed models cannot be labelled as collision images. These
screenshots remain diagnostic evidence of a native/display attribution defect;
they do not invalidate the native guard or justify collision-policy changes.

Tarun's separate 24 September FDI11 normal-window trial also ran all three
configured rows after changing Base/orientation. All three rows stopped before
path search because the shared PreEntry IK candidate stage found no endpoint
within tolerance; the tables showed `full task: NotRun` and zero waypoints.
That is evidence about the common IK prerequisite, not a comparison of
RRTConnect, RRT and RRT* planning performance. The eight operator screenshots
are retained under
`Workspace/docs/diagnostics/evidence/fdi11-step6-2026-09-24/`.

This work is ready to present as a completed diagnostic workflow and a useful
failure analysis. The actual controlled three-planner benchmark remains
incomplete and is downstream of the current engineer-led workbench renovation.

## What succeeded

### Source and architecture

- The renovation plan, five-DOF acceptance checklist, backlog, task contracts,
  decisions and dated logbook were kept under the existing `S6-LIVE-01`
  contract; no parallel pending queue was created.
- The exact five-DOF refactor is present in the URDF, MoveIt/workflow
  definitions, state, limits, Home, bridge, façade, UI, persistence and
  publishers. Current state accepts exactly J1–J5. J6 is not silently
  truncated; extra current values fail shape validation.
- The former movable spindle/burr attachment is fixed at its existing neutral
  transform. Spindle and burr geometry, collision bodies and canonical
  `dentobot_drill_tcp` remain available. Axial roll is labelled unconstrained
  by the five-DOF arm.
- The five-DOF model/build/runtime contract was source and runtime checked:
  exact five-value guard/state, static validity, TCP TF and five-joint IK were
  observed in the isolated simulation package. The generic fixed-orientation
  Cartesian interpolation request is recorded as unsupported for this arm;
  Step 6 uses position plus drill-axis continuity instead.
- Commit `84234a6` captured the requested pre-refactor checkpoint. The current
  post-checkpoint work remains uncommitted and must be preserved.

### Manual workbench source gates

- `guardManualRobotJog` carries current case/branch/Base/Home/limits/scene
  identity and exact J1–J5 values, applies mechanical and reviewed limits, and
  uses simulation-only raw native guard evidence.
- Accepted requests update the accepted simulation only after authoritative
  guard acknowledgement and exact identity correlation. Rejected and unknown
  requests retain the draft and failure evidence without advancing accepted
  state. Unknown or stale outcomes latch reconciliation and block another
  publish until a read-only proof clears them.
- Re-entrancy protection, stale responses, request/session/policy correlation,
  J6 exclusion, accepted/monitored/displayed mirroring and no route/preview
  authority are covered by host tests.
- Base and Task Home have detached review/stage/cancel/accept paths with
  explicit uncertainty handling. A candidate is not accepted by dragging,
  saving a recording or merely changing a draft.
- The version 1.0 manual simulation record schema is reused for ordered
  requested/accepted/rejected/unknown events, identities, diagnostics, TCP and
  drill-axis samples. Historical import/replay is display-only and cannot
  restore live state or authorize preview.
- The two-area UI separates Planning & Diagnostics from Preview & Control.
  Partial/manual paths cannot become route or preview authority.

### Cartesian TCP workbench (6.3B)

- The headed no-case package
  `data/dentobot-runs/step6-tcp-workbench-headed-20260928-9/` passed explicit
  default-off TCP Drag gating, live mouse drag, X/Y/Z and pitch/yaw nudges,
  position-axis J1–J5 Solve IK staging, accepted-state separation, disable
  cleanup and zero route/preview authority.
- The 1600x900 recording completed with Slicer exit 0 and no owned-process
  residue. Video SHA-256:
  `3860799981e8952b410e2239193cf874d3e8b4006c5ee707c705c37dd96af834`.
- This does not prove case-bearing TCP drag, physical keyboard delivery or
  measured normal-window responsiveness.

### Case display/save correction

- The operator reported a closed-mouth source appearing after saving
  `sept28_fdi11_step6.dentocase`. Source inspection distinguished the original
  source segmentation from opened jaw proxies and did not alter the original
  case.
- The bounded headed display/save/reopen probe created a separate copy and
  verified source-hidden/opened-proxy-visible state after reopen. The original
  case remained unchanged. Tarun's visual verdict is still pending.

### S6-U-01 shutdown condition

- A separate isolated 5.10 native teardown correction was built and verified
  without replacing the installed package. The final no-case headed run
  `data/dentobot-runs/s6-u01-final-headed-20260928-0hCREB/` recorded connected
  robot/publisher release and widget cleanup, exited Slicer 0, emitted no
  class-loader or fatal-signal marker, and left no owned process.
- This closes the reproduced no-case connected shutdown condition only. It is
  not proof that the case-bearing whole-run campaign is complete.

## What was attempted and what happened

| Attempt | Purpose | Result | Evidence/status |
|---|---|---|---|
| Three current-case migration runs r1–r3 | Reopen the saved six-to-five-DOF case with strict provenance | Failed at three distinct restore boundaries: exact profile mismatch, stale cached parameter node, then compatibility mutation before strict post-hydration audit | Preserved under `data/dentobot-runs/s6-live-01-five-dof-campaign-20260928T122153Z-r1/`, `...T131742Z-r2/`, `...T132323Z-r3/`; source ordering correction passed host checks |
| FDI21 three-planner attempts 1–5 | Establish exact current-profile Home, stable comparison identity and durable per-row evidence | Exposed robot-load setup, resource-profile, ephemeral audit-identity and evidence-capture defects; each was retained and corrected without relaxing validation | `data/dentobot-runs/step65-three-planner-fdi21-31-20260923/` (`fdi21/`, then `fdi21-r2/` through `fdi21-r5/`); none is a valid three-planner comparison |
| FDI21 three-planner r6 | Compare RRTConnect, RRT and RRT* under frozen inputs with timing/checkpoint evidence | RRTConnect completed and failed at Stage 3 target-tooth↔spindle guard; RRT was interrupted by the 20-minute cap and RRT* was not run | `.../fdi21-r6/`; diagnostic success, benchmark incomplete, no route/preview authority |
| FDI21 collision recapture | Supply multi-angle geometric context for the r6 first blocker without replanning | Recapture exposed an upper/lower-jaw transform attribution defect; Tarun rejected the images as collision evidence | `.../fdi21-r6-collision-recapture-r3/`; retained as invalid-reconstruction diagnostics only |
| FDI11 operator three-planner trial | Inspect all three configured rows after manual Base/orientation changes | All rows stopped at the shared PreEntry IK prerequisite before planner path search | Eight screenshots in `Workspace/docs/diagnostics/evidence/fdi11-step6-2026-09-24/`; no relative planner verdict |
| Earlier current-case Base/Home headed run | Verify case/scene, one jog, detached Base, Accept Base and current-pose Task Home | Bounded 16/16 functional checklist passed; Slicer exited 1 after the functional pass, so video remained partial | Run-local diagnostics and 28 September logbook; no full-chain authority |
| r13 five-DOF recorded run | Verify corrected restore, 31-object scene, workspace, accepted jog, invalid draft, then rejected/unknown paths | Passed restore/workspace/native boundary, accepted 0.1-degree J1 guard and invalid reviewed-limit draft. Stopped at first new causal failure: `Production Guarded Jog is disabled before unknown-result injection.` | `data/dentobot-runs/s6-live-01-five-dof-campaign-20260928T164300Z-r13/`; partial video SHA `4b70307c9e5a1fd3d68ed651f96d20bbc9c388d724bec99df2e77d7de61f5d09` |
| Shell completion source correction | Fix cached jog availability after a busy robot-state refresh | Host-verified: busy is cleared before final availability refresh in Guarded Jog and Reconcile State paths | 35 Manual Jog UI tests, 44 headed-runner source tests, combined 79 tests; compile and diff checks pass |
| r14 prepared retry | Re-run r13 from the corrected source with full recording | Not launched. Automatic approval rejected the escalated Docker/runtime command because account usage was exhausted | `data/dentobot-runs/s6-live-01-five-dof-campaign-20260928T165722Z-r14/diagnostics.md`; wrapper SHA `ad504a3f9569a926d1e43dce9be377131783c1e2b4a010e505fb3eb223c8398f` |

## Native-result release slice

Two Luna Max workers completed disjoint source/test scopes before the later
usage exhaustion. `DENTOROS2Bridge.py` now releases caller-owned MoveIt VTK
trajectory and FK-matrix results exactly once in `finally` paths, including
malformed and exceptional conversion paths. The focused release selection
passed 8 tests; the full `Testing/test_ros2_bridge.py` suite passed 70 tests in
0.16 seconds; scoped compilation and diff checks passed. This correction does
not create route or preview authority, and it has not been revalidated in a
new headed case run because runtime testing is halted.

## Verification record

The following are source/host results, not a claim that the full GUI workflow
has passed:

- The five-DOF source/build/runtime slice passed the indexed 394-test host
  selection and built `dentobot_description` and `dentobot_moveit_config` in
  an isolated overlay.
- The 6.3B/UI/bridge/facade/application-shell host selection passed 238 tests.
- The latest manual-jog plus headed-runner source command passed 79 tests:
  `python3 -m pytest -q Testing/test_robot_manual_jog_ui.py
  Testing/test_step6_headed_review_source.py`.
- `python3 -m json.tool Testing/verification_matrix.json` and repository
  `git diff --check` pass after the current documentation/source updates.
- Earlier source slices passed the indexed 181, 225 and 251-test gates for
  the diagnostic/workbench and reviewed-integration checkpoints. Those counts
  remain historical evidence and do not replace current case-bearing runtime
  checks.

## Current evidence boundary

The source case remains:

`/home/light-tarun/dentobot/data/Slicer_Saved/SampleStudy1/SEPT24/sept28_fdi11_step6.dentocase`

with SHA-256
`e21fee7f850aa3517ce26e7920bf7dde7c06d3dda7dd6de7e360e7fc69a32786`.
The intended output
`sept28_fdi11_step6_five_dof_acceptance.dentocase` is absent. The current
checkout is dirty by design; no new changes were committed or pushed.

The following remain open or pending:

- Runtime-native accepted/rejected/unknown guarded J1–J5 outcomes and
  reconciliation on a current five-DOF case.
- Fresh case save and fresh-process reopen of the named five-DOF acceptance
  package.
- Physical keyboard event delivery and measured two-area responsiveness.
- Case-bearing TCP drag/ghost review and exact collision-aware staging.
- A reviewed current task with validated Home for positive full-chain
  Home→PreEntry→Entry→Target preview authority and interruption/Stop/Return.
- A controlled, complete same-input RRTConnect/RRT/RRT* comparison remains
  downstream. Existing FDI21 and FDI11 evidence must not be presented as a
  relative planner benchmark.
- Complete whole-process recording with zero exits and owned-process cleanup for
  the case-bearing campaign.
- Tarun's normal-window robotics/usability verdict.
- Later curation of proven 5.10 performance/integrity changes into a reviewed
  integration worktree. The separate performance/5.12 checkout remains
  untouched and is not a source of current acceptance.

## Halt and resumption rule

Runtime testing is **halted**. Preserve these artifacts as evidence:

- r13 partial recording, JSON and state-matched screenshots:
  `data/dentobot-runs/s6-live-01-five-dof-campaign-20260928T164300Z-r13/`
- r14 prepared wrapper and pre-launch diagnostics:
  `data/dentobot-runs/s6-live-01-five-dof-campaign-20260928T165722Z-r14/`
- the no-case TCP package and the no-case S6-U-01 shutdown package.

No one should launch Slicer, ROS/MoveIt, Docker runtime or the recorder from
this plan until Tarun explicitly resumes runtime work. Source-only review and
documentation may continue under the existing contracts, but a host test count
must not be promoted to headed, native, planner, preview or operator
acceptance.

## Evidence links

- [Current dated logbook](../logbook/2026-09-28.md)
- [Detailed five-DOF acceptance checklist](STEP6_FIVE_DOF_DETAILED_ACCEPTANCE_CHECKLIST_2026-09-28.md)
- [Step 6 renovation implementation plan](STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md)
- [Canonical planner comparison contract](FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md)
- [23 September FDI21 planner campaign log](../logbook/2026-09-23.md)
- [24 September FDI11 operator comparison log](../logbook/2026-09-24.md)
- [FDI21 r6 timing/checkpoint evidence](/home/light-tarun/dentobot/data/dentobot-runs/step65-three-planner-fdi21-31-20260923/fdi21-r6/)
- [FDI11 comparison screenshots](evidence/fdi11-step6-2026-09-24/)
- [r13 run diagnostics](/home/light-tarun/dentobot/data/dentobot-runs/s6-live-01-five-dof-campaign-20260928T164300Z-r13/)
- [r14 blocked-run diagnostics](/home/light-tarun/dentobot/data/dentobot-runs/s6-live-01-five-dof-campaign-20260928T165722Z-r14/diagnostics.md)
- [r13 accepted-jog screenshot](/home/light-tarun/dentobot/data/dentobot-runs/s6-live-01-five-dof-campaign-20260928T164300Z-r13/evidence/20260928T160706211473Z-guarded-j1-jog-result-ui.png)

This report is a development-controlled weekly status record. It does not
replace the canonical task contract, does not close `S6-LIVE-01`, and does not
invent the pending operator verdict.
