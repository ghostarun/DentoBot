# DENTOBOT Development Plan

Last reconciled: 2026-09-10.

TASKS.md owns the one active work order. The current P0 is main-workflow
recovery and PreparedBranch integrity. The audit was accepted on 2026-09-10 and
the three-deliverable product patch is implemented in the dirty checkout.
Static, pure and focused headless Slicer evidence pass; normal-window operator
review remains pending.

The main workflow has one target tooth and one trajectory, or an explicitly
paired two. The optional 32 × 3 testing foundation is an alternative workflow,
not a replacement for or expansion of routine case preparation.

Stage 3 / Track A remains incomplete and follows this integrity correction.
The remaining P1 Case Platform/Studio roadmap stays behind Track-A acceptance.
Slicer 5.12 migration remains the separate `PLAT-U-06` plan in
[SLICERROS2_5_12_UPGRADE.md](SLICERROS2_5_12_UPGRADE.md); it is not an action
for this task. Reviewed clean/post-surgery anatomy is the acceptance baseline;
retired pre-surgery/x4 cases remain negative diagnostics.

## Immediate gate and next implementation package

The live blocker state and work order are in
[TASKS.md](TASKS.md#immediate-blockers-and-next-task). The implementation now
stores one authoritative selected-branch ID, routes Step 5C/selection/load/Step
6 through one eligibility result, and atomically activates trajectory/pairing,
matching 4C/insertion, shell, template, guide references and Step 5C revision.
The first acceptance path remains 4A→4B→4C→5A→5B→5C→6 with one target and one
trajectory.

This package stops when the reviewable diff and focused single-target runtime
evidence exist. Both now exist: `runtime.s6_reusable_case` exited 0 with
`DENTOBOT_REUSABLE_CASE_PASS`; normal-window operator review remains separate.
Explicit pairing follows; optional 32 × 3 testing follows that. Stage 3,
collision-policy or geometry-algorithm changes, Studio, database, batch and
platform work are outside this package.

## S6-REUSABLE-CASE-SETUP correction plan

### 2026-09-11 Case Foundation workflow amendment

The former post-import 6.0A mouth-opening gate is superseded. Establish one
source-fingerprinted Case Foundation immediately before Step 4A, then author
one or more PreparedBranches against that planning pose. Step 6.0 activates an
already-present verified branch; Step 6.1A reconstructs the local robot and
reviews the world/head-fixed Manual Simulation Base offline; Step 6.1B exposes
the explicit ROS + MoveIt gate. Steps 6.2 onward remain unchanged.

The source-complete implementation uses the existing parameter node,
PreparedBranch registry and environment snapshot only. It adds no registry,
runtime service or external base file. Foundation-only packages are valid
partial cases; package load never restores live ROS, planning, guard,
acknowledgement or validity state. Gap/source changes retain inspectable branch
geometry but apply the recorded Step 5C/base/runtime staleness scopes.

Targeted static and pure-state evidence passes. The next automated gate is only
`runtime.s6_reusable_case`; the final gate is the recorded ten-observation
normal-window review. No SlicerROS2 rebuild is required because no compiled C++
or interface changed.

**2026-09-10 — audit accepted; implementation and focused runtime pass, operator review pending.**
This is the existing P0 task, not a new roadmap. The previous source-complete
claim is withdrawn: operator reports show unified-template and Step 6 import
regressions. TASKS.md alone owns current work order and status.

### Immediate FDI31 restore delta before mouth-opening rework

The normal-window review of
`run2-dentobot-case-step6x5.dentocase` found two bounded restore defects under
this existing task. An otherwise manifest/lineage-valid package was rolled back
because its redundant derived Step 6 environment snapshot differed from the
environment rebuilt from authoritative MRML. The opened Step 5C proxy followed
the TMJ transform, while the source Step 4C docking assembly remained visible
at the closed-jaw pose and looked like duplicate bores.

Recover this case without redesigning the transform: retain hard rejection for
package, node, registry, lineage and actual MRML geometry/matrix mismatches;
rebuild only the redundant environment snapshot, keep the load offline and
migration-pending, and reuse the existing target-attached proxy refresh to hide
the Step 4C plane/docks until reset. Verify the exact package once in isolated
Slicer, then stop. Moving/reworking the mouth-opening transform and its longer-
term Step 6 object ownership belongs to the next dedicated plan update.

### 1. Separate the main workflow from optional testing

- Main workflow defaults to one target tooth and one trajectory. An explicit
  paired-canal action may select two trajectories of that same tooth. A third
  trajectory or another target is never implicitly included by scene inventory.
- Multi-trajectory testing is an explicit opt-in presentation using the same
  MRML geometry, registry and branch preparation service. Its capacity remains
  32 teeth × three explicit slots; it does not alter routine main-workflow
  selection, preparation or default UI. Preserve existing inactive records when
  entering/leaving this mode; never delete them to make a single-target view.
- First restore the normal single-target 4A→4B→4C→5A→5B→5C→6 path.
  Optional testing controls follow only after that regression gate passes.
  No batch runner, Results UI, SQLite, platform upgrade or full Studio redesign
  belongs to this correction.

### 2. Audit and correct one PreparedBranch ownership boundary

Inspection of the current dirty source found raw-trajectory activation in
`logic_case_bundle.py`, copied per-slot guide dictionaries without pairing
intent in `DENTOStep6State.py`, and Step 5C checks tied to model state/update
metadata rather than a complete branch identity. These are audit findings;
they do not establish the cause of every reported geometry defect.

The 2026-09-10 read-only audit traced the production routes. No product source
was changed and no runtime check was run.

| Operation | Existing route | Audit result |
|---|---|---|
| Build | Step 5B handlers → `_createOrUpdateFinalPrintableTemplate` | Checkbox selection is persisted, but the builder consumes only `trajectoryLine`; explicit pairing intent is therefore not authoritative. |
| Save / registry | `_createCaseBundle` → `prepareDentoCaseSchema2ForSave` → `syncDentoCaseTrajectoryRegistry` | Scene inventory rebuilds copied per-slot guide dictionaries, infers pairing from model references and derives selection from the raw trajectory pointer. |
| Load | `_openCaseBundle` → schema-2 hydration / registry comparison | Offline load is correctly preserved, but hydration does not activate one validated selected PreparedBranch. |
| Select | target/trajectory/Step 5B UI handlers → `activateDentoCaseTrajectory` | Selection partially swaps global pointers, permits a same-target docking fallback and has no prevalidated all-or-nothing branch transaction. Independent selectors can still split branch state. |
| Import | `importStep6PlanningContext` → `validate_planning_context` plus freshness checks | Import validates raw global node presence and scattered state tokens, not one centralized branch identity and matching Step 5C revision. |
| Delete / invalidate | `deleteTrajectoryNode`, `_activePlanningDownstreamEntries`, dependency impact and node observers | Traversal is rooted in active global pointers; inactive branch records and all of their revisions are not one centralized invalidation domain. |
| Step 4C / insertion | `targetDockingTrajectoriesForTarget`, `createOrUpdateTargetDockingAssembly`, insertion-direction builders | Step 4C can consume all complete same-target trajectories, up to three. Both docking and insertion depend on exact branch inputs and must not be classified as shared merely because active storage is global. |

This ownership table is the coding contract:

| State | Authoritative owner / reuse rule |
|---|---|
| CBCT / anatomy | Case-shared. |
| Target tooth | Case-target identity referenced by each PreparedBranch; active target switches with the branch. |
| Trajectory / trajectories | PreparedBranch. |
| Pairing intent | PreparedBranch and explicit; never inferred from scene inventory alone. |
| Step 4B support / Step 5A visible surface | Case-target-derived upstream state; reusable only when exact source, target, support and dependency fingerprints match. |
| Insertion direction / Step 4C docking | Branch-dependent upstream state. Reuse only for the exact branch dependencies; never treat it as case-shared because the current pointer is global. |
| Patient shell | PreparedBranch. |
| Unified template | PreparedBranch. |
| Guide geometry / references | PreparedBranch. |
| Step 5C evidence | PreparedBranch revision. |
| Jaw opening | Shared runtime setup only while its inputs are unchanged. |
| Landmarks / base transform / Home | Shared runtime setup only while their inputs are unchanged; saved configuration never restores live validity. |
| Collision acknowledgement / plans / previews / guards / diagnostics | Branch-runtime state; invalidate on branch switch. |

Before changing code, review this audit against the current source and accept or
correct its boundary. Retain the serializer and mask-display repairs; do not
broadly revert collision/planner/diagnostic work.

- Define PreparedBranch by extending the existing guide-set record and stable
  guide ID. Each branch has one owner tooth, one trajectory ID or an explicitly
  approved pair, exact patient-shell/template/guide MRML references, source
  fingerprints and a Step 5C verification identity.
- Store each branch once in the existing registry; slots reference branch IDs.
  A paired branch references T1 and T2 explicitly, with no copied mutable branch
  records. Independent A/B/C branches may coexist with AB without silently
  overwriting any association. No second registry or persistence file.
- Use a persisted selected branch ID as the Step 6 selection authority.
  `trajectoryLine` remains the primary trajectory compatibility pointer;
  the existing repeated trajectory references carry the whole selection.
  A pair's primary trajectory is selected explicitly for a planning attempt;
  this does not authorize a two-trajectory drilling cycle or change the planner.
- Keep the shell and unified-template geometry authoritative in MRML. Branch
  identity is stable across rebuilds; geometry/evidence fingerprints change.
  Names, UI selection order, timestamps alone and scene enumeration cannot
  determine ownership or establish current verification.

### 3. Enforce upstream and downstream gates

- Step 5B shows the selected target/trajectory with an optional explicit
  pairing action. Validate complete locked lines, source segmentation/target,
  current support/visible surface, insertion direction, confirmed docking,
  dimensions and dependency fingerprints before any geometry generation.
- Step 4B/5A anatomy preparation may be reused when its dependencies match.
  Audit Step 4C and insertion-direction dependencies instead of assuming they
  are trajectory-independent. Reuse only a matching compatible result; otherwise
  fail with the precise upstream action needed. Do not silently relax docking
  provenance checks or rebuild unrelated geometry when selecting a slot.
- Build outputs are staged until all existing geometry checks succeed, then
  published together to the selected branch. Failure leaves the prior valid
  branch intact and reports the first failing prerequisite/stage. No partially
  swapped shell/template pointers and no overwrite of another branch's models.
- Step 5C evidence binds the exact branch, trajectories, shell/template geometry,
  relevant source/parameter fingerprints and verification policy identity.
  Preserve existing PASS/WARNING/FAIL semantics and warning approvals.
  Missing/mismatched evidence blocks Step 6 eligibility; an STL is not authority.
- Centralize branch eligibility so 5C, Step 6 import, branch selection and load
  call one result, conceptually `evaluatePreparedBranchEligibility(branchId)`.
  Its minimum stable reason vocabulary is `VALID`, `MISSING_TRAJECTORY`,
  `PAIRING_NOT_CONFIRMED`, `STALE_4C`, `MISSING_TEMPLATE`, `STEP5C_MISMATCH`,
  `UPSTREAM_CHANGED` and `LEGACY_UNVERIFIED`; add another reason only for an
  observed state that cannot be represented by these. Saving may retain drafts
  or stale evidence for repair, but never promote them to eligible branches.
- Any template with three trajectories is ineligible. Existing safe-to-load
  packages retain such geometry as historical/requires repair; they do not
  become active branches, get silently split, or prevent unrelated valid
  branches from being inspected. Structural archive corruption still fails
  integrity validation. Legacy two-trajectory geometry requires explicit
  pairing confirmation if intent cannot be proven, followed by current 5C checks.

### 4. Switch a complete branch and invalidate actual dependencies

Resolve and validate the entire destination before changing the active state.
One transaction swaps the exact trajectory set/primary pointer, explicit
pairing intent, matching branch-dependent 4C/insertion references, patient
shell, unified template, guide references and matching 5C evidence. This stays
inside the one atomic-activation deliverable; it is not a fourth workstream.
Re-entrant UI observers must not see or invalidate a half-selected branch. On
validation or publication failure, switch nothing. Selecting the already active
branch is a no-op.

| Trigger | Preserve | Invalidate / refresh |
|---|---|---|
| Select another eligible branch with unchanged environment | Accepted jaw transform/gap, landmarks, anatomy, base matrix/lock, Task Home configuration, all stored branch geometry and evidence | Branch task confirmation, collision acknowledgement, plans, previews, guards, diagnostics; replace/hide only outgoing branch display proxies |
| Edit T1 | T2/T3 and branches not referencing T1; shared setup | T1 evidence and A/AB dependents; 5C must reverify after rebuild |
| Edit support, docking, shell or template | Unreferenced branches; unrelated shared state | Every branch that actually references the changed input and its 5C/runtime evidence |
| Change source jaw/anatomy frame, opening landmarks or mouth-gap configuration | Recoverable stored values | Affected shared opening/base/Home and branch/runtime dependents, with explicit reason |
| Change robot/tool identity or base | Source anatomy and independent branch geometry | Existing robot/base/Home/runtime dependencies as appropriate; guide/tool verification when actual fit dependencies change |
| Load/reopen or reconnect | Valid saved geometry/configuration and historical evidence | All live runtime validity; load remains offline |

Branch switching cannot move the robot or erase a pending Return Home/recovery
obligation. Block switching while an action/preview is active or recovery is
required; use existing stop/recovery handling. Home configuration is preserved,
but validity against the newly selected guide scene must be freshly established.
This is runtime validation, not a reason to stale the accepted shared setup.

### 5. Migration, verification and stopping gates

1. Pure/state checks: single, explicit pair, reject implicit pair/three-way merge;
   32 × 3 capacity/fourth rejection only in testing; stable branch IDs,
   correct ownership, unrelated branch preservation and transaction rollback.
2. Package checks: schema-1 deterministic migration, existing schema-2 input,
   newer save round trip, A/B/C and AB preservation, missing/mismatched 5C
   identity, inspectable but ineligible legacy three-trajectory geometry.
   No package rewrite until explicit save; no ROS/live-plan restoration.
3. Focused Slicer checks under the existing protocol: default single-target
   build→5C→6 import first; explicit pair next; optional T1/A→T2/B→T3/C
   switching and save/reopen last. Assert unchanged jaw/base/lock/Home values,
   exact reference/evidence swaps and no visible outgoing proxies.
4. Exercise real dependency edits, failed builds, incomplete branches and
   repeated selection/import. A build passing alone does not prove 5C/import
   acceptance. Preserve existing geometry/connectivity/bore checks, including
   the FDI11 terminal-collar regression, without tuning geometry algorithms.
5. Normal-window operator review closes usability and stale-state acceptance.
   Report implementation, unit/package, Slicer runtime and operator evidence
   separately. Keep retry history and exclusive-runtime rules from the protocol.
   Then update TASKS.md and refresh Graphify after code changes.

Stop after this correction's reviewable diff and focused acceptance evidence.
Do not proceed into Stage 3 planning during this milestone. After workflow
integrity, resume `S6-LIVE-01..05` against a current reviewed branch and its
recorded case constraints; exact Target, axial withdrawal, guarded Home and a
fresh repeat remain required. Major Studio work stays behind that acceptance.


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

### Existing physical and collision prerequisites

The recorded insertion, anatomy, tool/guide fit, exact-endpoint and independent
guard checks remain in force. Use the current case-specific TASKS.md entry and
dated evidence; do not transplant old x4 parameters or diagnoses into another
case. Historical `S6-P0-DEPTH`, `S6-P0-CLEARANCE` and anatomy-review
attempts are retained in the 2026-09-04–09 logbooks.

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

### Established model and evidence boundary

J1–J5 plan to the canonical non-spinning TCP. Exact position and tool axis are
the task constraints; housing roll is not a commanded degree of freedom.
Existing FK, joint-limit, corridor, endpoint and full-path promotion checks
remain mandatory. Historical x4 fractions and J2 limit diagnoses live in dated
evidence; the latest FDI11/FDI21 result is summarized once in TASKS.md.

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
- guarded axial withdrawal, then Return Home and monitored Home confirmation;
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

The P0 reusable-case foundation emits the schema-2 fixed members above with an
empty validated study index/NDJSON ledger; dynamic attempt/replay inventory is
deferred to the separately scoped study runner. The complete 32 × 3 registry,
shared environment, landmarks/transforms, base lock and Task Home live in the
authoritative MRB parameter state and node graph. Schema-1 packages migrate
deterministically in memory and retain schema 1 until a later explicit user
save. Package load clears runtime validity, plans, guards and callbacks and
does not auto-connect ROS/MoveIt.

### Trajectory and planning identity

The current P0 PreparedBranch contract above owns trajectory/guide selection.
The 32 × 3 capacity applies to optional testing; normal preparation stays
single-target. Do not rebuild this foundation during P1.

`RobotEnvironmentSnapshotV1` identifies shared case/anatomy, jaw, robot/tool,
base, Home and other actual shared dependencies. `AttemptContextV1` binds
that environment to the selected prepared branch, active member trajectory,
planner/start-state and phase/contact policy. Geometry stays in existing MRML.

Future non-moving research studies and fresh guarded previews retain distinct
eligibility/collision modes. Study results never authorize a guarded preview;
the exact matching current branch and independently accepted plan are required.

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
| 3 | `DCP-02..08` | 1 | Remaining domain/session work and cross-session proof; reuse the accepted P0 registry/environment/persistence subset |
| 4 | `DCP-09..10` | 1 | SQLite DentoLibrary backend and case browser |
| 5 | `DSS-01..05` | 1 | Studio shell, Robot/Environment, Workspace, Trajectories, and frozen guarded-preview migration |
| 6 | `DSS-06..12` | 1 | Studies, results, replay, and Procedure/Research separation |
| 7 | `DHW-01..02` | 1 | Hardware-session data boundary and digital-twin interface preparation only |

P1 is blocked until the reviewed clean-case Track-A loop and repeat pass.
Only the specifically promoted P0 PreparedBranch/shared-environment correction
precedes that gate. Database, batch studies and GUI rearchitecture remain P1.

## Verification and evidence

For each item: implement only that feature; summarize the changed behavior;
state the smallest check and what it proves; obtain approval for Slicer, ROS,
MoveIt, build, or runtime execution; record the exact command/revision/result
and first failure; and proceed only after acceptance. No synthetic result is a
clinical, manufacturing, physical-placement, or hardware-safety claim.

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

## Work-order ownership

Use TASKS.md. The former `S6-P0-01` planner queue is continued under
`S6-LIVE-01..05`; the `S6-P0-02` restore queue is continued under
`S6-RESTORE-ROBOT-ROS` and the P0 PreparedBranch acceptance checks.
No parallel queue or automatic checkpoint-reconnect sequence remains active.

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

## Saved-case continuation

Case load is an atomic, offline geometry/configuration transaction. All stages
remain navigable for inspection; actions require current local prerequisites.
Explicit runtime activation later reconstructs runtime objects and validates
the selected PreparedBranch, current scene and Home. It does not restore
plans, guards or live validity from package contents. The former best-effort
automatic ROS reconnect/task reconfirmation sequence is superseded.

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

## Immediate Step 4A P0 correction — displayed pulp contact and smooth masks

The 2026-09-10 operator report promotes `S4A-PULP-ENDPOINT` and `W4-U-02`
ahead of the unprioritized roadmap. This correction is deliberately contained
within Step 4A presentation and assisted creation:

**Automated status:** Final static/pure checks and focused Slicer display plus
single/dual assisted-generation integration passed 2026-09-10. Exact FDI31 and
smooth/native normal-window observations remain operator acceptance.

- keep the existing selected-tooth, reviewed-segmentation and one/two-entry
  gates;
- require the inferred finite Entry→root ray to hit both the FDI-matched native
  binary pulp mask and that same segment's displayed closed surface; use the
  farther of their entry boundaries as the first point contained by both;
- record both boundary points, the shared Target, and their offset; fail before
  node creation if either intersection or their shared interval is absent;
- do not rewrite existing/manual lines, infer their provenance from the
  Placement menu, or change Step 6, robot, clearance, or approval policy;
- suppress off-slice markup projection so a point is not painted over a mask
  in a slice it does not occupy; and
- make the existing smooth-display switch apply in both ordinary Step 4A and
  oblique verification, reflect the actual CBCT/mask modes, and restore the
  captured modes when oblique verification ends.

Acceptance requires the focused pure/static checks, the existing Slicer
single/dual assisted-generation and segmentation-display check, and a
normal-window FDI31 regeneration after deliberate deletion of the legacy
three-line set. The new Target must lie on the displayed pulp surface, remain
collinear with Entry and the inferred root target, and not appear in an
unrelated slice through projection. Smooth on/off must visibly change both the
CBCT and masks without changing source data and must restore prior modes on
verification exit. These checks require explicit execution approval and must
not overlap the operator's current Slicer process.

## Immediate Step 5B P0 correction — open bores without detached attachments

Continue canonical tasks `W5-U-04` and `W5-U-03`. Preserve the extended final
through-bore subtraction, conservative 0.1 mm³ artifact threshold and one-solid
gate. Replace nearest-point connector routing with one straight bore-tangent
branch per dock: its cylinder surface remains one processing voxel outside the
bore and overlaps the reinforced annulus by at least one voxel. Do not change
the configured dock, bore, connector or trajectory dimensions.

Fail before final fusion when the reinforced annulus is too thin, no tangent
shell route exists or the safe route exceeds the current gap limit. Messages
must identify the Step 5B inspection view and the relevant Step 4C radius, yaw
and dock/bore/connector controls. On connectivity failure, report region sizes,
approximate extra-region volumes and the cleanup ceiling; never recommend
raising that ceiling as the default repair.

Acceptance is one focused synthetic geometry scenario plus the existing FDI11
saved-case fusion and an evidence-backed FDI31 comparison. Each representative
case must retain four open bores, zero occupied protected-channel samples, one
watertight occupied solid and Step 5C verification, followed by normal-window
inspection. The current FDI31 rebuild is blocked by a retained 5-voxel
component; classify its shell/guide/reinforcement/dock contributor before
selecting one construction correction. Do not treat its RAS distance from the
docks as proof of source membership or tune the dock route from that inference.

## Unprioritized and future roadmap

| ID / track | Planned outcome | Entry condition |
|---|---|---|
| `W4-U-01` | Snap assisted trajectory Entry to a reviewed selected-tooth crown surface with MPR evidence | Crown-region contract exists |
| `W5-U-01` | Optional Step 5C STL checksum/revision evidence for manufacturing handoff | Export traceability policy agreed; never gate Step 6 simulation |
| `IMG-U-01` | Representative clinical visualization and segmentation-display acceptance | Governed CBCT and clinician review protocol available |
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
