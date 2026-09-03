# DENTOBOT Development Plan

Last reconciled: 2026-09-03

This file defines implementation order, milestone gates, and workflow ownership.
Actionable status is tracked once in `TASKS.md`; architectural rationale belongs
in `DECISIONS.md`; verification evidence belongs in
`REPRODUCIBILITY_AND_TRACEABILITY.md` and the dated logbook. The complete
pre-cleanup plan is preserved in
`archive/2026-09-01/DEVELOPMENT_PLAN_HISTORY.md`.

## Development policy

- Implement one authorized milestone at a time and preserve dependency order.
- Prefer a bounded working vertical slice over disconnected feature fragments.
- Do not convert source-complete or synthetic evidence into operator/runtime
  acceptance.
- Current operator verification boundary permits `py_compile`, scoped pure
  `pytest`, and a SlicerROS build only when production C++ changes require it.
  Normal-window Slicer, ROS/MoveIt, exact-case smoke, GUI automation, and other
  runtime checks remain operator-led unless separately approved.
- Step 6 remains simulation/preview only. Hardware motion, powered drilling,
  patient-facing use, and clinical/safety claims are outside the current scope.
- Historical plans and callbacks cannot silently restore superseded ownership.
- Agent-delegated verification follows
  `AGENTIC_VERIFICATION_PROTOCOL.md` and
  `../../Testing/verification_matrix.json`: read-only workers, bounded evidence,
  and one serialized Slicer/ROS/MoveIt runtime lane.

## Current implementation order

| Order | Task ID | Outcome | Exit gate |
|---:|---|---|---|
| 1 | `S6-P0-01` | Complete spindle-locked, fixed-frame Home→PreEntry→Entry→Target planning | One collision-valid complete chain; identical frame fingerprint through all stages; guarded previews available; no non-tool collision relaxation |
| 2 | `S6-P0-02` | Resume valid saved Step 6 checkpoints at the highest truthful substep | Normal-window complete/partial/ROS-unavailable/repeated-load acceptance; 6.6 still requires a fresh complete plan |
| 3 | `S6-P1-01` | Finish anatomically constrained Step 6A landmarks and hinge review | Condylar/crown regions, exact-source snapping, MPR review, guide metrics, and representative anatomy acceptance |
| 4 | `S6-P2-01` | Add progressive restored-case integrity review | Steps 1–6 show one integrity state, reason, and recommended action without partial archive hydration |
| 5 | `S6-P2-02` | Add transient incisor-gap preview | Smooth preview; one explicit lock commits and invalidates descendants once |
| 6 | `S6-P2-03` | Add shared progress/completion feedback | Truthful busy/progress/result feedback without fabricated percentages or duplicate callbacks |
| 7 | `UI-P3-01` | Refine the New GUI after correctness gates close | Legacy parity, viewport-first layout, accessibility, and no new MRML/ROS side effects |
| 8 | `S6-U-01` | Finish clean native SlicerROS2 shutdown | Zero-exit lifecycle with no retained SlicerROS2/MoveIt wrappers; may advance only if the defect again disrupts normal workflow |

## Step 6 ownership contract

| Substep | Sole routine owner | Required result |
|---|---|---|
| 6.0 / 6.0A | Case/task selection and non-destructive jaw preparation | One current planning case or governed fallback; no ROS creation |
| 6.1 | Local robot, reviewed Manual Simulation Base, Connect/Disconnect ROS + MoveIt, collision-scene audit | Active compatible runtime and exact acknowledged scene |
| 6.2 | Live Task Home selection, validation, guarded application, and save | Current case/base/profile-specific Home; not physical homing |
| 6.3 | MoveIt state-valid/FK workspace, bounded Home connectivity, assisted-limit review | Current reviewed exploration evidence; not a globally collision-free box |
| 6.4 | Immutable task confirmation only | Snapshot fingerprints current case, base, runtime, Home, workspace, tool, and trajectory |
| 6.5 | Goal 1 and full-chain preflight | Stage 1 provisional preview or complete guarded three-stage chain with explicit first failure |
| 6.6 | Goal 2 drilling simulation preview | Consume only a current complete Stage-3 plan; never independently replan or promote partial output |

Disconnect returns ownership to 6.1 and invalidates live runtime evidence,
confirmation, plans, and guard sessions. ROS nodes, MoveIt plans, publishers,
subscribers, goal robots, guard sessions, and active flags are transient and
must never be stored in `.dentocase`.

## `S6-P0-01` — fixed-frame full-chain planning

The pneumatic spindle remains in the six-joint compatibility schema and visual
robot but is planning-locked at `0 rad`. Stage 1 commits one immutable drilling
frame at PreEntry: tool +Z follows Entry→Target and the remaining rotation about
that axis comes from the selected collision-aware arm solution. Stages 2 and 3
must use the identical frame.

Candidate selection evaluates distinct arm routes, not spindle-roll variants:

1. strict collision-free Task Home→PreEntry planning;
2. one fixed-axis PreEntry→Entry Cartesian path generated without MoveIt's
   coarse collision stop, then independently phase-guarded so only configured
   burr-to-task contact is suppressed and every non-tool rule remains strict;
3. fixed-frame Entry→Target Cartesian drilling preview; and
4. non-mutating independent guard validation of every returned waypoint.

Complete guarded chains rank first, then minimum normalized joints-1–5 motion
after PreEntry. A valid Stage-1 plan may remain a clearly labelled provisional
preview when a later stage blocks, but no partial Stage 2 or Stage 3 path can be
promoted. Diagnostics must retain route identity, frame fingerprint, per-stage
fraction/waypoint count, composed and stage-local first-invalid indices, guard
cause, joint margin, collision pair, and the provisional/complete/blocked
classification. A blocked attempt opens the existing bounded inspector with a
stage-specific explanation and recovery action; this feedback is evidence-only
and cannot authorize collision relaxation or execution.

The 2026-09-01 exact-x4 trial after expanding the arm seeds remained truthful
but incomplete: Stage 1 retained 55 guarded waypoints with J6 fixed while the
old guessed-split Stage 2 again stopped at 50% (11 retained waypoints). Earlier
diagnostics identified forbidden `link-3`↔tooth contact at that boundary. This
is a diagnostic fixture, not authority to relax non-tool collision.

The bounded source increment is Python/pure-test verified but has not had a
normal-window Slicer/MoveIt trial. Stage 1 now
uses every bounded 6.3 Home-connected representative, removes duplicate
joints-1–5 solutions, and rechecks each canonical J6-zero endpoint through
MoveIt validity. Planner revision v4 replaces the guessed terminal-distance
split with one full fixed-axis Stage-2 path and gives each candidate an isolated
validate-only guard session. A Stage-2 guard failure preserves only the valid
Stage-1 preview and reports its first rejected waypoint/cause. The production
inspector now reports all three stage outcomes, per-stage progress, first
invalid location, exact retained cause, and the appropriate operator next
action. A false-positive completion path was also closed: a failed Stage-3
preflight is cleared and cannot be persisted or advertised as complete. Motion
diagnostic schema 2.1 retains read-only schema-2.0 compatibility. `py_compile`
passed and the scoped state/façade suites passed `33/33`; runtime evidence is
still required before claiming a complete x4 chain.

The 2026-09-03 operator trial supersedes that pending-runtime statement for
the current x4 attempt: Stage 1 passed with 328 waypoints and Stage 2 passed
with 18, while every inspected fixed-frame candidate stopped at 91.7% of
Stage 3 with 42 retained waypoints. Because Stage 3 requested MoveIt with
collision avoidance disabled and reported no collision pair, this is presently
a Cartesian kinematic/continuity failure, not collision evidence. Source now
propagates the first invalid requested pose and classification, retains each
live candidate path for display-only static/animated inspection, and adds a
workstation preview-speed control. Compilation and restore tests pass; the new
diagnostic regression passes within a `50 passed, 1 failed` planning gate whose
sole failure is the known unrelated draft-AABB neutral-pose assertion. Goal 2
remains correctly blocked pending normal-window acceptance and a complete
Stage 3.

The current P0 source increment adds a bounded sequential continuity-IK
fallback after a partial collision-off Cartesian response. It solves the same
fixed-frame poses from the explicit previous state, verifies FK residuals, and
still requires the independent phase guard to accept every returned waypoint.
Static and pure checks now pass for this increment (with the known unrelated
draft-AABB neutral-pose planning assertion still failing); this remains source-
only until the reloaded x4 runtime proves a complete Stage 3. The fallback
cannot promote a partial or guard-rejected path.

## `S6-P0-02` — saved-checkpoint continuation

`.dentocase` restore remains one atomic geometry/lineage transaction. After it
passes integrity validation, a package saved after 6.2–6.5 may best-effort
reconstruct the local robot and transient ROS/MoveIt runtime, reapply and
revalidate Home, replay saved workspace evidence, reconfirm the immutable task,
and select the highest truthful substep. It must stop at the first missing,
stale, incompatible, or unavailable prerequisite and explain why.

All workflow steps remain freely selectable for inspection after restore;
mutation actions remain gated by current prerequisites. A complete checkpoint
may land at 6.5, while 6.6 remains blocked until a fresh complete Goal 1 plan is
generated in the new runtime. Current source/pure verification is not a
substitute for normal-window acceptance.

The same operator trial proved automatic runtime reconstruction begins, but
the workflow visibly remained at 5C until Step 6 was selected and truthful
revalidation stopped at 6.3. Source now switches to Step 6 before reconstruction
starts; it still stops at 6.3 when saved workspace evidence cannot be replayed.
This landing change passed compilation and the `28/28` pure restore gate;
normal-window behavior remains unaccepted.

## Remaining correctness work

### `S6-U-01` — Priority-4 native shutdown hygiene

The former reconnect/`mrmlScene.Clear(0)` abort no longer reproduces: warm New
Case, module reload, reconnect, and save/reopen reach the functional lifecycle
PASS marker. This item therefore no longer blocks Priority-0 workflow work.
The current native source repair replaces the ROS host's raw parameter-node
list with MRML references, makes delayed parameter callbacks weak-node safe,
removes redundant `Delete()` calls after scene-owned nodes are removed, handles
a missing default ROS node during robot scene update, and removes stale robot
names on teardown. The package rebuild passes; this is source/build evidence,
and the serialized lifecycle now completes connect/reload/reconnect/New Case/
reconnect/save-reopen with its PASS marker. Closure still requires a clean
shutdown: retained ROS2/MoveIt VTK and class-loader objects remain after the
functional pass. At Priority 4, finish one idempotent native shutdown path,
release all robot/parameter/pub-sub/MoveIt wrappers before plugin unload, and
make the lifecycle harness terminate its complete ROS process group.

### `S6-U-02` — physical mount-frame truth

The reviewed Manual Simulation Base is sufficient only for bounded simulation.
Future physical placement must separate a patient/world contact frame from a
CAD-defined robot mount-face frame and solve the explicit transform between
them. The circular robot-derived forehead plane remains quarantined and no
proxy is registration, fit, or safety evidence.

### `S6-P1-01` — Step 6A anatomical safeguards

Preserve source CBCT and masks. Derive source-fingerprinted left/right condylar
and upper/lower incisal/crown interaction regions, require exact-source surface
projection and orthogonal-MPR review, and retain patient-RAS laterality and
inferior-opening constraints. The accepted hinge remains a single rigid
world-RAS transform applied only to moving-lower anatomy and explicitly
mandibular-attached proxies. The placement-only fallback remains non-planning.

### Priority-2 interaction work

- `S6-P2-01`: present one step-by-step restored-case integrity review after the
  atomic load; do not create a second geometry package or partially hydrate it.
- `S6-P2-02`: make slider movement display-only and commit persistent geometry
  only through **Lock / Accept Opening**.
- `S6-P2-03`: use one shared long-running-action contract for truthful busy,
  progress, completion, error, cancel, and cleanup state.

## Unprioritized and future roadmap

| ID / track | Planned outcome | Entry condition |
|---|---|---|
| `W4-U-01` | Snap assisted trajectory Entry to a reviewed selected-tooth crown surface with MPR evidence | Crown-region contract exists |
| `W5-U-01` | Optional Step 5C STL checksum/revision evidence for manufacturing handoff | Export traceability policy agreed; never gate Step 6 simulation |
| `IMG-U-01` | Representative clinical visualization and segmentation-display acceptance | Governed CBCT and clinician review protocol available |
| `W4-U-02` | Representative Step 4 trajectory/MPR/backtracking acceptance | `W4-U-01` crown contract and governed anatomy available |
| `W4C-U-01` | Dock/rail geometry and multi-trajectory robot-axis closure | Registration versus load-bearing roles and mechanical thresholds agreed |
| `W5-U-02` | Step 5A support, margin, undercut, shell, and removability acceptance | Representative anatomy and physical-fit criteria available |
| `W5-U-03` | Step 5B/5C unified fusion, verification, reopen, and one-STL acceptance | Current Step 4/5 lineage and manufacturing thresholds available |
| `VIEW-U-01` | Cross-workflow Views/Elements normal-window acceptance | Representative restored cases available; no renderer or geometry creation during inventory |
| `S6-U-03` | Experimental observed oral-air/unknown-space representation | Open-mouth/phantom acquisition and validation reference available |
| `CASE-U-01` | Offline migration of legacy scenes contaminated with serialized ROS objects | Migration schema and isolated no-ROS process defined |
| `PLAT-U-01` | Rebuild and accept the clean Ubuntu inference/runtime image | Clean Docker build and governed inference data available |
| `PLAT-U-02` | Accept the Windows 11 native-Slicer/WSL launcher | Windows workstation available |
| `PLAT-U-03` | Close CRD/GDM workstation stability observation | Saved local work and an approved reboot/overnight observation window |
| `QA-U-01` | Resolve the Slicer aggregate-runner nonzero-exit discrepancy | Focused lifecycle diagnosis approved |
| `ROS-U-01` | Define the narrow medical-image/transform interoperability contract | Current Step 6 and imaging frame requirements stable |
| `POC-U-01` | Representative software case, printed Template V0, seating/reseating, dimensional evidence, and a total error budget | Clinical task and acceptance thresholds frozen |
| Track F0 | Evidence-only reviewed-result ledger in `.dentostudy` | One V2 planning attempt operator-accepted |
| Track F1 | Automatic single-case, single-base plan-only study | F0 accepted and long-running action contract available |
| Track E | Stable reviewed virtual mount/base candidates | Physical mount-frame contract defined |
| Track F2 | Trajectory × reviewed-base comparison | Track E and F1 accepted |
| Track A | Full canonical coordinate/frame contract | Bounded current transforms are stable |
| Track G | Physical registration, TCP calibration, controller and safety integration | Phantom metrology and verified safety procedure exist |

Steps 0–5 remain the established imaging, segmentation, trajectory, support,
dock, and template workflow. Their prior detailed milestone narratives and all
dated Step 6 status reports remain available in the archived plan; they are not
an alternative current queue.

## Completion and evidence rules

- `Planned`: accepted intent, no implementation claim.
- `Source complete`: implementation exists but has no verification claim.
- `Static/synthetic verified`: exact approved check recorded; no operator claim.
- `Operator/runtime accepted`: observed in the intended normal application and
  recorded with case/runtime constraints.
- `Blocked`: first truthful external or technical blocker is named.
- `Completed`: acceptance gate passed and no required work remains.

Every active item appears once in `TASKS.md` under its stable ID. This plan may
reference that ID but must not duplicate its running status narrative. Dated
implementation detail belongs in the logbook and changelog, not in a second
`Next` list.
