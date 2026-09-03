# DENTOBOT Development Plan

Last replaced: 2026-09-04

This is the authoritative implementation order. The former incremental Step 6
wizard renovation and the separate `.dentostudy` proposal are superseded by two
tracks: first finish one complete guarded live-simulation loop on the retained
x4 case; only then build the case-centric Robot Planning & Simulation Studio.

## Non-negotiable boundary

- Step 6 remains simulation/preview only. It exposes no hardware controller,
  physical homing, powered spindle, drilling command, or patient-facing path.
- MoveIt owns IK and path generation. MoveIt PlanningScene/FCL plus the
  independent DENTOBOT phase guard own collision and task-phase acceptance.
- J6 remains in the six-joint visual/collision compatibility tree but is not a
  MoveIt planning DOF; any visual compatibility slot is fixed at `0 rad`.
  It represents an externally pressure-driven spindle, not a robot positioner.
- Stage 1 commits one fixed tool rotation and Entry-to-Target axis. Stages 2
  and 3 reuse that exact frame.
- A partial path is diagnostic evidence only. It never enables drilling
  preview or becomes an executable plan.
- The reviewed Manual Simulation Base is unregistered research placement.
  The robot-derived forehead plane stays quarantined and is not anatomy,
  registration, fit, collision, or safety evidence.
- Each bounded phase is implemented first, then its proposed verification is
  explained and requires operator approval under
  `AGENTIC_VERIFICATION_PROTOCOL.md`.

## Track A — Priority 0 guarded live simulation

Track B cannot start until `S6-LIVE-05` is operator/runtime accepted.

### `S6-LIVE-00` — documentation and source checkpoint

Record this replacement roadmap, preserve the previous decisions as historical
evidence, and absorb unfinished `S6-P0-01` work into Track A. The clean source
baseline before Track A changes is
`ea504349f99f7604318130024b224aebd2e57170`.

### `S6-LIVE-01` — complete Stage 3 planning

Retain the current planner architecture:

1. strict MoveIt Task Home to PreEntry;
2. fixed-frame PreEntry to Entry;
3. fixed-frame Entry to Target using the non-spinning canonical TCP (the
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

### `S6-LIVE-05` — x4 acceptance gate

An approved normal-window trial with
`dentobot-case-step6x4.dentocase` must prove:

- current ROS/MoveIt runtime and acknowledged collision scene;
- applied and monitored Task Home;
- 100% Stage 1 to PreEntry, Stage 2 to Entry, and Stage 3 to Target;
- one identical fixed-frame fingerprint across the chain;
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

One complete x4 loop gates Track B. Multi-case coverage belongs to the Studio
study implementation.

## Track B — Robot Planning & Simulation Studio

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

## Track B implementation order

| Order | ID | Priority | Complete feature |
|---:|---|---:|---|
| 1 | `S6R-00` | 0 | Post-Track-A baseline and documentation checkpoint |
| 2 | `S6R-01` | 0 | Atomic DentoCase schema 2 and schema-1 migration |
| 3 | `S6R-02` | 0 | Three-slot trajectory registry and isolated invalidation |
| 4 | `S6R-03` | 1 prerequisite | Crown snapping and anatomical jaw constraints |
| 5 | `S6R-04` | 2 | Cached display-only incisor-gap preview plus explicit accept |
| 6 | `S6R-05` | 0 | Environment/attempt contexts, evidence, and failure taxonomy |
| 7 | `S6R-06` | 0 dependency | Façade expansion and shared action runner |
| 8 | `S6R-07` | 0 | Responsive Studio shell and viewer integrity |
| 9 | `S6R-08` | 0 | Robot & Environment workspace |
| 10 | `S6R-09` | 0 | Home, workspace explorer/connectivity evidence, and envelope |
| 11 | `S6R-10` | 0 | Track A guarded loop migrated without behavior drift |
| 12 | `S6R-11` | 0 | One persistent non-moving study attempt |
| 13 | `S6R-12` | 0 | Repeated/resumable single-trajectory study |
| 14 | `S6R-13` | 0 | Multi-tooth/multi-trajectory study |
| 15 | `S6R-14` | 0 | Statistics, results, diagnostics, and retained replay |
| 16 | `S6R-15` | 2 | Progressive Steps 1-6 integrity review |
| 17 | `S6R-16` | 0 | Parity acceptance and Studio-default cutover |

Priority 1 anatomical correctness is sequenced before evidence generation
because it stabilizes its required fingerprint. The former Priority 2 progress
work is promoted as the `S6R-06` dependency. Visual-only polish remains
`UI-P3-01` after functional acceptance.

## Verification and evidence

For each item: implement only that feature; summarize the changed behavior;
state the smallest check and what it proves; obtain approval for Slicer, ROS,
MoveIt, build, or runtime execution; record the exact command/revision/result
and first failure; and proceed only after acceptance. No synthetic result is a
clinical, manufacturing, physical-placement, or hardware-safety claim.
