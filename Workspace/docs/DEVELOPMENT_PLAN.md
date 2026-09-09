# DENTOBOT Development Plan

## Slicer 5.12 platform migration — active investigation

Prepare Slicer 5.12.0 as an isolated candidate while current 5.10 releases stay
available. The ordered phases are source reconstruction, clean derivative-image
build, compatibility gates, representative workflow and simulation gates,
same-host performance comparison, then operator acceptance and release
promotion. The authoritative phase plan is
`Workspace/docs/SLICERROS2_5_12_UPGRADE.md`.

## 2026-09-08 — Bounded FDI11 simulation retry

Operator's latest policy caps the confirmed simulation drilling path at 6 mm,
preserving Entry, direction and shorter paths. Retain physical insertion and
collision guards. The newer FDI11 step6x4x2 package matches the manual 7.977207
mm source trajectory. Implement and verify cap/reconfirmation first, then
exercise Home→PreEntry→Entry→effective Target→axial withdrawal→Home with
explicit runtime approval. Existing strict Return Home is not proof of the
requested axial withdrawal. Full Track-A acceptance and Track B remain pending.

## 2026-09-07 — Production baseline correction after case reset/cleanup review

The pre-surgery/x4 package is retired as a development baseline. Its observed
non-target contacts, guide-bore mismatch, and provisional base placement remain
historical diagnostics only; they are not reasons to relax collision policy or
add case-specific planner branches. The next Track-A acceptance case must be a
reviewed post-surgery/clean anatomy package with a verified Step 5C tool/guide
fit.

The baseline guard now grants the narrow burr-contact policy only to the
selected target tooth. Adjacent anatomy and the guide/template remain in the
authoritative collision scene and retain the research clearance margin. The
retired template-collision bypass and session anatomy-review proxy are
quarantined behind explicit, process-only historical diagnostic environment
variables and are never package state or acceptance evidence.

This correction is intentionally bounded: the accepted five-joint canonical TCP
planner, spindle-outside-planning invariant, independent phase guard, endpoint
checks, and full-chain promotion rules are preserved. Verification and a clean
case runtime review are the next actions; Track B remains blocked by the Track-A
full-loop gate.

Last replaced: 2026-09-04
Last updated: 2026-09-07

This is the authoritative implementation order. The former incremental Step 6
wizard renovation and the separate `.dentostudy` proposal are superseded by two
tracks: first finish one complete guarded live-simulation loop on a reviewed
clean/post-surgery case; only then build the case-centric Robot Planning &
Simulation Studio. The abnormal pre-surgery/x4 package remains a negative
diagnostic fixture and is not an acceptance target.

## Non-negotiable boundary

- Step 6 remains simulation/preview only. It exposes no hardware controller,
  physical homing, powered spindle, drilling command, or patient-facing path.
- MoveIt owns IK and path generation. MoveIt PlanningScene/FCL plus the
  independent DENTOBOT phase guard own collision and task-phase acceptance.
- J6 remains in the six-joint visual/collision compatibility tree but is not a
  MoveIt planning DOF; any visual compatibility slot is fixed at `0 rad`.
  It represents an externally pressure-driven spindle, not a robot positioner.
- Stage 1 commits the exact Entry-to-Target drill axis and an authoritative
  FK frame for display/fingerprinting. Stages 2 and 3 preserve the exact
  Entry/Target points and axis; housing roll is not a commanded task
  constraint because the spindle is externally driven.
- A partial path is diagnostic evidence only. It never enables drilling
  preview or becomes an executable plan.
- The reviewed Manual Simulation Base is unregistered research placement.
  The robot-derived forehead plane stays quarantined and is not anatomy,
  registration, fit, collision, or safety evidence.
- Each bounded phase is implemented first, then its proposed verification is
  explained and requires operator approval under
  `AGENTIC_VERIFICATION_PROTOCOL.md`.

## Track 0 — Priority-unassigned Steps 0–3 scan/run inspection

The Steps 0–3 correction is a source-paired inspection workflow and does not
change downstream planning authority until the operator explicitly chooses
`Use for Planning → Step 4`. It is intentionally separate from the Track-A
robot milestone and must not silently invalidate an existing trajectory,
template, or Step 6 branch merely because another scan is being inspected.

- A persisted inspection pair (`inspectedVolume`, `inspectedSegmentation`) is
  distinct from the existing planning pair (`inputVolume`,
  `teethSegmentation`). The shared selection operation validates exact MRML
  source references, switches the actual slice background, and isolates only
  the selected DENTOBOT teeth run.
- Steps 0–3 expose one fixed Case / Scan / Result context bar and a fixed
  footer. Scan and run selectors are source-filtered, runs receive source-based
  labels and explicit rename actions, and inference completion remains attached
  to its launch scan even when the operator browses another scan.
- Step 3 owns review actions: show/hide labels in the selected run, isolate a
  label, compare same-source runs or different-source scans, and exit comparison
  with the previous display state restored. Recommended View and Restore obey
  the inspection pair while these stages are active.
- A reviewed pair becomes planning input only through the explicit handoff. If
  it replaces an existing planning pair, the normal lineage invalidation and
  impact confirmation are used. Missing or ambiguous source references remain
  non-authoritative and must not be guessed from names or scene order.

### Track 0 acceptance boundary

The focused Slicer scenario with two distinguishable scans, two runs for the
first scan, and one run for the second has passed source switching, actual slice
background IDs, run visibility isolation, planning-reference preservation, and
comparison enter/exit. The real operator preDental/postDental scene still needs
one visual reload check before this item is marked accepted. No new package
format or database is introduced.

## Track A — Priority 0 guarded live simulation

Track B cannot start until `S6-LIVE-05` is operator/runtime accepted.

### 2026-09-05 immediate P0 correction — physical insertion and anatomy review

The current x4 functional chain is not accepted merely because its five-joint
kinematics reach Target. Before the final Track-A loop, enforce a provisional
tool-only insertion constraint:

```text
requested Entry->Target depth <= effectiveToolProtrusionMm - 0.1 mm
```

The value represents the axial distance from `dentobot_drill_tcp` to the first
upstream tool/housing geometry that cannot enter the access path. A violation
is `TRAJECTORY_TOOL_INSERTION_LIMIT_EXCEEDED`; it must block preflight without
shortening the approved line, moving either endpoint, or relaxing a tolerance.
The result is explicitly *Provisional tool-only insertion limit — final guide
geometry not included* and is displayed with requested depth, protrusion,
reserved clearance, maximum depth, and remaining margin.

The present CAD/URDF provisional value is `7.0 mm`: the nearest upstream
`pneumatic_spindle-Copy` housing mesh is 7.0 mm behind the canonical tip along
the tool axis. With the `0.1 mm` reserve, maximum requested depth is `6.9 mm`.
The x4 line (`15.760533814 mm`) is therefore intentionally blocked as an
insertion-capacity failure until the physical tool/access configuration or the
approved trajectory is changed upstream.

Collision semantics remain separate. The x4 template-excluded diagnostic has
complete Stage 1/2/3 kinematic branches but presently rejects the best retained
Stage-3 point because its FCL minimum distance from
`pneumatic_spindle-Copy` to FDI15 is `0.998041065511 mm`, below the additional
`1.0 mm` research clearance margin. That inspected housing point is a margin
violation, not a reported housing mesh intersection. The completed read-only
actual-contact audit, however, establishes a separate hard blocker: every
auditable candidate reaches an actual FDI15↔`burr` contact at Stage 2 waypoint
14 and again from Stage 3 waypoint 0 (alongside the expected target↔burr
contact). Thus the complete x4 chain is neither physically collision-valid nor
eligible for a margin-only reclassification. Neither base placement nor the
margin policy changes from this evidence.

If a reviewed FDI15 region is plausibly a segmentation artifact, the only
permitted Track-A remedy is a manual, session-local derived collision proxy:
source segmentation stays untouched, the reviewed region is local, and the UI
labels it `Research simulation anatomy override`. It is never an automatic
whole-tooth exclusion or a silent `.dentocase` authority change. The approved
temporary Step-5C template/guide exclusion remains a separate, explicit,
non-default functional-simulation override and cannot support a physical-fit
claim.

Source implementation now provides this review route in Step 6.5. It creates
one disposable copy of an explicitly selected non-target whole-tooth segment,
opens that copy—not source anatomy—in Segment Editor, and requires the
operator's explicit artifact confirmation before a collision-scene re-sync can
use it. Activation discards transient plans, marks confirmation/diagnostics
stale, and requires a fresh acknowledgement and confirmation. The copy is
`SaveWithSceneOff`; it is not a DentoCase/MRML authority. This source checkpoint
does **not** establish that FDI15 is an artifact, does not add exact contact
point visualization, and has not yet received a Slicer runtime verification.

### `S6-LIVE-00` — documentation and source checkpoint

Record this replacement roadmap, preserve the previous decisions as historical
evidence, and absorb unfinished `S6-P0-01` work into Track A. The clean source
baseline before Track A changes is
`ea504349f99f7604318130024b224aebd2e57170`.

### `S6-LIVE-01` — complete Stage 3 planning

Retain the current planner architecture:

1. strict MoveIt Task Home to PreEntry;
2. fixed-axis PreEntry to Entry;
3. fixed-axis Entry to Target using the non-spinning canonical TCP (the
   visual J6 compatibility slot remains fixed at zero);
4. full-chain independent phase-guard validation.

MoveIt's collision-off Cartesian result remains the first Stage 2/3 attempt.
When it is partial, the existing bounded sequential-continuity IK fallback must
solve the same sampled poses from the preceding accepted J1-J5 state, use only
bounded deterministic perturbations, canonicalize continuous joint
representations, keep the visual-only J6 slot at zero, and verify every recovered pose with
authoritative FK. Position residual must remain at or below `0.25 mm` and
orientation residual at or below `0.5 deg`.

Failure must preserve the first unsolved requested index, RAS point,
last-valid and first-invalid joint state, collision/kinematic classification,
and MoveIt collision pairs where available. The requested depth is never
shortened. Full-chain state is `Complete` only when every stage reaches 100%.

### Track-A kinematic-model correction — 2026-09-04

The bounded spindle correction is now source-complete. The MoveIt
`dentobot_arm` group and all Step 6 planning APIs use five commandable joints
(J1–J5) and the fixed upstream `dentobot_drill_tcp`. J6 remains only in the
URDF visual/collision branch and is held at `0 rad` for six-value display
compatibility; the guard rejects six-value motion commands rather than
commanding it. The canonical TCP is a fixed sibling of
`pneumatic_spindle-Copy`, evaluated at the CAD reference spindle angle, so
orientation and position do not depend on air-rotor roll.

The correction removed production solve-with-J6-then-canonicalize behavior.
Task Home, workspace samples, IK/FK, trajectories, Goal 1/Goal 2, Return Home,
phase commands, previews, and metrics now carry J1–J5 only. Older six-value
saved records retain their first five arm values at the persistence boundary;
old roll-dependent evidence is stale under the new robot-profile/policy
fingerprint. Direct canonical FK accepts a legacy six-value vector only by
discarding its sixth slot. No residual tolerance, collision policy, corridor,
endpoint, or partial-path rule changed.

Focused source/build evidence is recorded in the 2026-09-04 logbook:
86/86 pure tests passed, the SlicerROS2 package rebuilt successfully, the ROS
MoveIt smoke passed with five planning values and explicit legacy-spindle
rejection, and the phase-guard smoke passed all listed acceptance/rejection
cases. The façade smoke emitted its functional JSON (canonical TCP, five-joint
state, native Goal/IK/Plan, expert return, and workspace assertions); its
process still exits nonzero at shutdown because pinned SlicerROS2 reports
retained VTK wrappers. The required complete x4 Home→PreEntry→Entry→Target→Home
normal-window trial remains the next gate, and Track B remains blocked.

### Track-A five-constraint IK correction — source implemented 2026-09-04

The exact x4 diagnosis showed that the fixed `dentobot_drill_tcp` transform is
correct, but the KDL MoveIt IK entrypoint still demanded XYZ plus a complete
quaternion from the five-DOF arm. A historical x4 J1–J5 endpoint evaluated
against the corrected TCP reaches PreEntry within about `0.099 mm` and the
Entry→Target axis within `0.0068 deg`, proving the required position-plus-axis
task is reachable independently of axial housing roll.

Source now adds one bounded native MoveIt-model Jacobian solve for XYZ plus
tool +Z. It uses only J1–J5, leaves axial housing roll out of the task error,
enforces existing bounds, validates endpoints against the current Planning
Scene, and retains best residual evidence on failure. Goal 1 uses the existing
Task Home/Home-connected seed set and records the authoritative FK frame as a
display/fingerprint scaffold. Stage 2 and Stage 3 preserve the exact
Entry/Target points and drill axis; the continuity fallback does not invent a
sixth roll constraint. When local continuity reaches a joint boundary it may
try only the already accepted 6.3 Home-connected arm postures, with no new
samples, tolerance changes, endpoint substitution, or partial-path promotion.
The policy is `stage1-position-axis-authoritative-fk-v3`; older full-frame
orientation evidence is stale. Every complete Stage-3 plan also receives an
independent authoritative final-target FK check.

### Track-A Stage-3 boundary diagnosis — 2026-09-04

The approved x4 focused run now reaches the exact Stage-3 line through pose
`59/64`. At pose `60/64`, all bounded J1–J5 continuity attempts retain a
finite state at the J2 lower bound with about `0.25 mm` position residual and
`0 deg` drill-axis residual; no collision pair is reported. The separate
guide-fit audit still reports the physical `2.0 mm` burr versus `1.5 mm` bore
mismatch, but that is not the kinematic cause. The source therefore tries only
verified 6.3 Home-connected branch seeds at the first local boundary, keeps the
exact line/tolerances/guard unchanged, reports the native best residual, and
keeps the full task `Blocked` until Stage 3 reaches the exact Target. The
retained Stage-1/Stage-2 preview is explicitly provisional; no partial drilling
path is promoted.

Focused FK evidence now classifies this boundary explicitly as
`sequential_position_axis_joint_limit`: the best state is pinned at
`link-2_Slider-2`'s lower mechanical limit and the exact pose is approximately
`0.2510335 mm` beyond it along the J2 axis. The diagnostic-only out-of-range
probe is not a valid plan. The next action is operator base/case-placement
correction followed by normal Task Home/workspace/task revalidation; no URDF
limit, tolerance, target, or collision-policy change is permitted.

### `S6-LIVE-02` — independent full-chain guard

- Stage 1 is fully strict.
- Stage 2 and Stage 3 may suppress only configured burr contact with the
  selected target tooth and the matching final guide/template.
- Joint bounds, self-collision, other robot/world contact, non-target anatomy,
  corridor escape, overshoot, backtracking, stale identity, and spindle motion
  remain blocking.
- Every suppressed burr contact is counted and the result is labelled
  exploratory, never collision-free.
- Task, trajectory, base, Home, robot/tool, collision-scene, guide, corridor,
  and fixed-frame fingerprints remain identical from planning through preview.
- The retained 2.0 mm burr / 1.5 mm bore case may be explored only under the
  explicit burr-guide exception. It must simultaneously show a separate
  physical-fit failure and cannot support a manufacturing-fit claim.

### `S6-LIVE-03` — repeatable preview state machine

```text
Validated Task Home
  -> plan complete three-stage chain
  -> preview Stage 1 + Stage 2 to Entry
  -> prepare Goal 2 from the accepted Stage 3 preflight
  -> preview Stage 3 to Target
  -> strict guarded Return Home
  -> replan or select another current trajectory
```

Goal 2 never independently replans Stage 3. Entry and Target completion require
monitored TCP verification within the existing FK tolerances and no overshoot.
Return Home uses MoveIt, strict guard checks, sequential waypoint application,
and monitored-state confirmation; it never teleports. Stopping mid-preview
consumes the current phase session, marks the robot away from Home, and exposes
only guarded Return Home. Replanning clears transient plans, paths, goal state,
and guard sessions while preserving case intent and historical diagnostics.

### `S6-LIVE-04` — preview performance and route visibility

- Replace fixed 250 ms pacing with acknowledgement-driven scheduling from the
  planned waypoint timestamps.
- Provide `0.25x`, `0.5x`, `1x`, `2x`, `4x`, and `8x` playback.
- Submit every waypoint and wait for its phase-guard acknowledgement; only
  visual refresh is coalesced to approximately 30 Hz.
- Report current phase and accepted/total waypoints.
- Render separate Stage 1, 2, and 3 paths and distinguish complete, partial,
  and first-invalid evidence.
- Selecting a planner leg displays its actual retained route and endpoint;
  equal waypoint counts are not presented as equal geometry.

### `S6-LIVE-05` — reviewed clean-case acceptance gate

An approved normal-window trial with a reviewed clean/post-surgery case package
must prove:

- current ROS/MoveIt runtime and acknowledged collision scene;
- applied and monitored Task Home;
- 100% Stage 1 to PreEntry, Stage 2 to Entry, and Stage 3 to Target;
- one identical drill-axis/policy fingerprint across the chain (housing roll
  is not a commanded task constraint);
- J6 equal to zero in Home and visual previews; planning and guard messages
  contain only J1–J5 and reject any attempted spindle command;
- every waypoint accepted by the independent phase guard;
- correct static paths and adjustable preview speed without skipped/reordered
  commands;
- endpoint TCP verification at Entry and Target;
- guarded Return Home and monitored Home confirmation;
- replan and second preview without restarting Slicer;
- safe stop/recovery; and
- no hardware/controller command path.

One complete clean-case loop gates Track B. The historical x4 package remains
diagnostic evidence only; multi-case coverage belongs to the Studio study
implementation.

## Track B / Priority 1 — DENTOBOT Case Platform and Simulation Studio

Track B reorganizes ownership and evidence only after Track A is accepted. It
preserves the accepted ROS/MoveIt, FK, collision, Home, workspace, guard,
preview, and Return Home implementation.

### Architecture

`DENTORobotWorkflowFacade` remains the only robot-workflow façade. It gains
runtime/environment, Home, workspace, trajectory, study, result, preview,
stop, and Return Home operations; the GUI never calls scattered legacy
callbacks. A shared action runner rejects duplicate activation, disables
conflicting controls, reports only measurable progress, supports cancellation
between opaque MoveIt calls, and guarantees cleanup and one terminal result.

The Studio uses Slicer's native central 3D, slice, table, and plot views with
persistent pages:

- Overview;
- Robot & Environment;
- Workspace;
- Trajectories;
- Study Runner;
- Results; and
- Guarded Preview.

The numbered 6.4 confirmation page disappears from the Studio. Confirmation is
an internal reviewed prerequisite built immediately before planning. Left
navigation and pinned context actions remove top-of-panel scrolling. Docks are
responsive and no longer use the current fixed-width clipping. Viewer state
has one controller so page changes, restore, and module reload cannot duplicate
observers, hide required teeth, or create a renderer merely by opening Views.

### DentoCase schema 2

```text
scene/case.mrb
manifest.json
workflow/lineage.json
robot/robot-profile.json
records/save-report.json
study/index.json
study/attempts.ndjson
study/replays/<attemptId>.json
integrity/checksums.sha256
```

- `.dentocase` is the only case/study package; no `.dentostudy` or database is
  introduced.
- MRB remains geometry authority. Schema 1 loads through an explicit migration
  and emits schema 2 only on a subsequent user save.
- Manifest/checksum inventory covers dynamic study/replay members and rejects
  unsafe paths, duplicates, malformed NDJSON, missing replay references, and
  unsupported/oversized content before scene replacement.
- A post-load MRML/registry mismatch restores the prior scene instead of
  leaving partial hydration.
- Attempts are immutable NDJSON records. Exact display-only replay is capped
  at 200 per case and 20 per trajectory, explicitly retained, and never
  silently evicted.
- Runtime ROS/MoveIt objects, plans, phase sessions, goal robots, callbacks,
  timers, and transient envelopes are not serialized.
- Loading shows historical evidence immediately and never connects ROS.
- A saved paused/running study may resume missing `(trajectoryId,
  attemptIndex)` entries only after explicit runtime, scene, Home, and exact
  environment-fingerprint revalidation. Unsaved crash-time work is not
  reconstructed.

### Trajectory and planning identity

Each tooth owns zero to three stable registry records. New candidates are
manual; existing assisted nodes migrate with `legacy-assisted` provenance.
The existing MRML line remains the geometry and the current `trajectoryLine`
reference temporarily remains the active compatibility pointer. A fourth
trajectory is rejected. Editing one trajectory stales only its dependent
evidence.

Manual Entry placement snaps to a reviewed visible crown surface of the
selected tooth and retains exact source/MPR provenance.

Planning identity is split into:

- `RobotEnvironmentSnapshotV1`: case/anatomy, accepted jaw, robot/tool, base,
  Task Home, common collision scene, limits, and workspace fingerprints;
- `AttemptContextV1`: environment plus tooth, trajectory, planner settings,
  explicit start, guide/contact mode, and phase policy.

Research studies use common jaw/all-teeth anatomy without trajectory-specific
guide/template/dock geometry. Guarded Preview requires the current matching
Step 5C guide/template and a fresh Track-A-quality plan.

### Study evidence

- Run 1-1000 sequential attempts per trajectory.
- One attempt is one top-level three-stage planning evaluation. Internal IK
  seeds/routes remain subordinate planner-leg diagnostics.
- Study execution uses explicit Task Home and does not move the monitored
  robot, publish joint commands, consume a guard session, or authorize preview.
- Persist only measurable IDs, fingerprints, timing, stage results, path/joint
  metrics, terminal error, route diagnostics, and failure evidence. Missing
  values are `null`, not estimates.
- Central failure codes cover IK, invalid goal, collision, joint limit,
  timeout, Stage 1/2/3, guard rejection, stale context, invalid runtime, and
  internal error.
- A changed environment makes the prior study historical; continuing requires
  a cloned study under the new fingerprint.

Success-rate denominators include genuine planning success and genuine
planning/kinematic/collision failure. Invalid runtime, stale context, invalid
trajectory, and other precondition failures are counted separately. Tooth
classification is `FeasibleInStudy`, `NotDemonstrated`, `Inconclusive`, or
`Untested`. Candidate ranking is research-only: success rate, successful
count, median time, normalized J1-J5 travel, then stable slot.

Historical replay animates only a translucent goal robot and display-only
paths. It never becomes a current MoveIt plan.

### Superseding implementation order

The prior `S6R-*` Studio list is historical. After `S6-LIVE-05` is accepted,
the P1 Case Platform roadmap is the sole implementation order. It keeps the
accepted Track-A backend intact rather than rebuilding it.

| Order | ID | Priority | Complete feature |
|---:|---|---:|---|
| 1 | `DCP-00` | 1 | Freeze Track A and publish its backend handoff |
| 2 | `DCP-01` | 1 | Controlled roadmap/documentation supersession |
| 3 | `DCP-02..08` | 1 | Domain objects, IDs/fingerprints, schema migration, trajectory registry, robot environment, sessions, cross-session x4 proof |
| 4 | `DCP-09..10` | 1 | SQLite DentoLibrary backend and case browser |
| 5 | `DSS-01..05` | 1 | Studio shell, Robot/Environment, Workspace, Trajectories, and frozen guarded-preview migration |
| 6 | `DSS-06..12` | 1 | Studies, results, replay, and Procedure/Research separation |
| 7 | `DHW-01..02` | 1 | Hardware-session data boundary and digital-twin interface preparation only |

P1 is blocked until the complete Track-A x4 loop passes. It has no authority
to start schema, database, multi-tooth, Studio, or GUI-rearchitecture work
early. Visual-only polish remains after functional acceptance.

## Verification and evidence

For each item: implement only that feature; summarize the changed behavior;
state the smallest check and what it proves; obtain approval for Slicer, ROS,
MoveIt, build, or runtime execution; record the exact command/revision/result
and first failure; and proceed only after acceptance. No synthetic result is a
clinical, manufacturing, physical-placement, or hardware-safety claim.
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
| `PLAT-U-02` | Regress the legacy Windows native-Slicer/WSL Steps 0–5 fallback; Step 6 and native Windows ROS remain excluded | Windows workstation available |
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
