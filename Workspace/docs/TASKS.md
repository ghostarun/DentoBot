# DENTOBOT Tasks

Last reconciled: 2026-09-15

## Record ownership

[backlog.md](backlog.md) is the sole pending queue and mandatory first planning
lookup. This file retains task contracts, evidence boundaries, historical
aliases and closure records. The sections below are the 2026-09-11 migration
baseline, not a second scheduling authority. Read current state/next action in
backlog.md before using these contracts; update substantive contract/acceptance
changes here and keep execution chronology in the dated logbook.

## Immediate P0 — bore-safe Step 5B dock attachments

- **ID:** `W5-U-04`; **Priority:** 0 (operator-promoted 2026-09-10);
  **State:** Synthetic and FDI11 runtime verified, including clean
  final-fusion bore-axis screenshots. The current regenerated FDI31 package
  passes the explicit four-open-bore, zero-channel-occupancy, one-solid and
  no-duplicate-dock gate; the historical 5-voxel fragment is not reproduced
  in that current artifact. Source-contributor classification and normal-window
  operator review remain open.
- **Failure evidence:** Extended 9.6 mm through-bore subtraction preserved the
  bore but split FDI11 into `[60677, 9, 4, 3, 1, 1, 1, 1, 1, 1]` occupied
  regions. The corrected FDI11 rebuild now has one region `[62258]`, zero
  residual channel occupancy and open-bore visual evidence. A prior diagnostic
  FDI31 rebuild retained `[45966, 5, 2, 2, 1, 1, 1, 1]`; its largest remnant
  was at least 7.66 mm from any dock-bore axis, so it was not evidence to tune
  a dock branch without contributor classification. The current regenerated
  FDI31 artifact does not reproduce that fragment. The 0.1 mm³ cleanup ceiling
  and one-solid gate remain authoritative.
- **Corrected contract:** Route each cylindrical shell attachment tangent to a
  protected bore radius equal to `bore radius + connector radius + one voxel`.
  Land it on the reinforced outer annulus with at least one voxel of ligament,
  retain configured endpoint overlap, extended final channel subtraction and
  four independent branches. Fail early with Step 4C/5B control guidance when
  the annulus, route or allowed gap cannot support that construction.
- **Diagnostics:** A disconnected final fusion now reports voxel counts,
  approximate extra-region volumes, the cleanup ceiling, the Step 5B
  **Shell + Guides** inspection view and the Step 4C radius/yaw/dimension
  controls to review. It explicitly warns against increasing the artifact
  threshold to hide a mechanical fragment.
- **Boundaries:** No patient shell, trajectory, bore/connector numeric value,
  artifact threshold, collision policy, robot plan or clinical/physical-fit
  acceptance changes. `W5-U-03` retains broader Step 5B/5C acceptance and
  `W4C-U-01` retains future mechanical/rail design.
- **Acceptance:** Focused synthetic geometry proves four bore-tangent branches,
  one-voxel minimum annular/bore clearance, zero protected-channel occupancy,
  four open bore axes, one watertight occupied solid and schema-1 invalidation.
  FDI11 passes this acceptance. The current FDI31 regeneration also passes the
  required geometry gate and reopens with one current PreparedBranch; the
  remaining acceptance is contributor/normal-window review, not a permission
  to relax the one-solid or channel checks. The bounded automated sequence is
  registered as verification profile `w5u04-bore-safe-template`.

## Step 6 offline restore — existing related backlog

- **ID:** `S6-RESTORE-ROBOT-ROS`; **Priority:** Unprioritized.
- **Observation:** Package load connected ROS before a usable local robot.
- **Current contract:** Offline geometry/configuration hydration, then explicit
  runtime activation. The former automatic checkpoint reconnect sequence is
  superseded, including for schema-1 migration.
- **Disposition:** Audit load/callback ordering under the current P0 correction;
  retain this ID for remaining robot reconstruction acceptance. Fresh and warm
  loads must not auto-connect or duplicate runtime objects. Saved Home is
  configuration, not restored live validation.
- **Evidence:** 2026-09-09 logbook; representative normal-window acceptance pending.

## Step 6.3 workspace purpose and clearance review before Studio — 2026-09-09

- **ID:** `S6-WORKSPACE-PURPOSE`; **Priority:** Unprioritized; **Recommended priority:** 0 for purpose/clearance review and any demonstrated current-workflow defect; **Triage:** Backlog, discussion/design prerequisite for Studio workspace migration. Broader Studio presentation remains P1.
- **Affected workflow:** Step 6.3 Generate Workspace, reviewed exploration limits, retained joint/TCP samples and Home-connectivity evidence; downstream planning seeds and future Studio workspace/study eligibility.
- **Operator observation and request:** The 5 mm clearance leaves no TCP workspace in the intraoral space. Step 6.3 needs updating for the latest developments, and its purpose must be discussed and revamped before the Simulation Studio revamp.
- **Evidence available:** Operator observation; the exact 5 mm parameter, its geometric reference and rejection path have not been inspected or reproduced in this turn. Existing context describes 6.3 as retained static-valid MoveIt-FK TCP/joint samples plus a bounded Home-connectivity classification; reviewed min/max limits are an exploration envelope, not a collision-free box.
- **Risk/impact:** An unsuitable exclusion may discard useful intraoral candidates or present misleading feasibility evidence. Conversely, removing clearance without distinguishing TCP location, complete tool/robot geometry and phase-specific contact could admit invalid states. An empty sampled set is not proof that no task path exists.
- **Discussion deliverable:** Agree whether 6.3 supplies an exploratory reachability display, reusable Home-connected planner seeds, task-specific feasibility evidence, or separately labelled combinations; specify what is mandatory for a single trajectory and what is reusable across the 96-record registry. Separate joint/FK reach, whole-robot static collision validity, Home connectivity and full oriented task-path acceptance.
- **Bounded follow-up:** Locate every consumer of the reported 5 mm setting and determine whether it is an ROI inset, TCP exclusion, tool-envelope allowance or collision policy. Compare it with the current five-DOF canonical TCP, actual tool/guide geometry and phase-specific rules. Propose the smallest justified 6.3 behavior/UI/invalidation change after discussion; no replacement clearance value is selected here.
- **Dependencies:** This purpose/ownership decision precedes Studio Workspace migration and workspace-related shared-environment fingerprints. Current restore readiness and freshly validated Home are prerequisites for live generation checks; existing `S6-LIVE-05` still gates the wider Studio implementation.
- **Next verification action:** First perform a scoped source/settings audit and document the contract. Then, under the prescribed approval, use a reviewed intraoral case to attribute sample rejection to the exact filter, distinguish static-valid/Home-connected/untested samples, and check reconnect/target-change invalidation. Full-task guards remain authoritative; no collision margin, joint limit, anatomy authority or live-validity requirement is relaxed by this note.

## P0 reusable Step 6 setup and PreparedBranches

- **ID:** `S6-REUSABLE-CASE-SETUP`; **Priority:** 0.
- **Current state (2026-09-14):** **Blocked pending external guide/tool/base
  geometry correction.** Case Foundation and reusable offline-base
  implementation is source-complete in the current checkout. The authoritative
  source was preserved; the reviewed production foundation save/reopen passed;
  current FDI31 Step 5C produced one eligible schema-3 PreparedBranch and its
  saved package reopened current. The approved current-source exact FDI31 run
  reached the requested target endpoint kinematically, but both bounded
  candidates were stopped by the authoritative guard at Stage 3: candidate 0
  at composed waypoint 255 / Stage 3 waypoint 27 and candidate 1 at its
  corresponding final Stage-3 boundary, on the selected-tooth ↔
  `pneumatic_spindle-Copy` collision. Goal 2, Return Home, repeatability,
  playback and ten normal-window observations remain `NOT_RUN`/open. No
  planner-success claim is made.
- **Opened-jaw display correction (2026-09-14):** The source segmentation is
  now treated as closed-pose inspection anatomy while the Case Foundation is
  current: every source segment is hidden per-segment in 3D, and the fixed /
  moving derived proxies are the only opened planning displays. A pre-hide
  visibility baseline is shared by both restore snapshots, including legacy
  packages missing the all-source record. The focused Slicer save/reload/reset
  regression passed; the exact FDI31 reopen audit recorded `0/54` visible
  source segments and 54/54 snapshot IDs. This is display/restore evidence,
  not collision acceptance or a replacement for the remaining production
  save/reopen audit of this migrated display state.
- **Scene-sync correction (2026-09-14):** Collision-scene acknowledgement now
  reads the complete live `/joint_states` vector before sending the unchanged
  state through the guard; it falls back to saved display values only when no
  complete live vector exists for offline/fake tests. This removes the traced
  stale-slider path that republished `J2=0.00202 mm` after Task Home had been
  verified. The focused pure suite remained `88 passed`; the current exact run
  reached active planning without reproducing that Home mismatch. Guard policy,
  base, target depth and collision rules were unchanged.
- **Current-source exact guard result (2026-09-14):** The native
  `collision_guard` was rebuilt from the current checkout and the approved
  exact run used that binary. The run produced a target-specific
  `FIRST_INVALID` sidecar: Stage 1 and Stage 2 completed; Stage 3 reached the
  requested target endpoint but the final waypoint was rejected because the
  selected tooth collided with `pneumatic_spindle-Copy`. The exact runner did
  not modify the r7 package, and the immutable source package remains
  separate as documented. This is a
  guide/tool/base geometry ownership question, not permission to add an
  exemption, shorten depth, move the base or tune dimensions.
- **Endpoint branch probe (2026-09-14):** A temporary read-only diagnostic
  tried 22 deterministic endpoint position-axis seeds against the same exact
  package; 8 met the native IK tolerances and all eight remained on the same
  J5 branch with the same template↔spindle, burr↔selected-tooth and
  selected-tooth↔spindle contacts. The hook was removed after the probe. No
  alternate branch or compliant planner change was evidenced, so the strict
  Stage-3 blocker remains open and downstream Goal 2/Return Home/repeatability
  and playback remain `NOT_RUN`.
- **Visual contact attribution gate (2026-09-14):** The operator reports that
  they cannot select a geometry correction without seeing why the spindle
  collides. The existing Step 5C reopen viewport is blank and the r13 sidecar
  retains the rejected joint state but no nearest/contact point. Reconstruct
  that saved Stage-3 terminal pose in an isolated offline Slicer scene using
  the exact r7 package and robot/scene resources; show target tooth, spindle,
  burr, guide and trajectory with context and close-up images, and mark any
  mesh intersection. The sidecar's solver `last_valid` vector equals the
  guard-rejected vector, so it is not an accepted guard state. Label onset
  depth `unknown` until a bounded static scene query resolves it.
  Reconcile the displayed meshes/frames against the native guard before a
  geometry-owner choice. No preview, physical motion or policy change is part
  of this evidence gate.
- **Superseding workflow:** Reviewed segmentation now leads to one Case
  Foundation before Step 4A: four reviewed landmarks, one committed hinge/gap,
  fixed-upper and moving-lower planning displays, then Steps 4A–5C. Step 6
  permits branchless offline robot/base review and foundation-only persistence.
  ROS + MoveIt requires the current pose, one explicitly activated eligible
  PreparedBranch, the compatible reviewed locked base and matching robot profile.
- **Persistent contract:** Outer `.dentocase` stays 2.0 and MRB remains geometry
  authority. DentoCase state is 3.0, Case Foundation/environment is 2.0 and the
  PreparedBranch registry is 3.0; legacy readers migrate in memory and write
  only on explicit save. `step6CaseJaw*` remains a compatibility alias.
- **Prior accepted evidence:** Operator approved the audited correction and its focused automated
  single-target acceptance passed. The narrow FDI31 recovery now loads the
  package offline without the former environment-mismatch rollback; static and
  exact-package headless checks passed for that boundary. The package's legacy
  Step 5C final-guide schema 1.0 is deliberately stale under current schema 2.0,
  so the planning context is deactivated and transient mouth-open proxy is not
  retained. Duplicate source-dock hiding is implemented for eligible schema-2
  branch restoration, but cannot be accepted against this legacy package until
  the planned rework chooses an inspection-only migration or regeneration path.
- **Main workflow:** One target tooth; one trajectory normally or an explicitly
  paired two for a real two-canal case. Never auto-merge three trajectories.
- **Optional testing:** Separate opt-in workflow over the existing 32-tooth ×
  three-slot registry. T1→A, T2→B, T3→C are independent PreparedBranches;
  T1+T2→AB is allowed only through deliberate pairing. Registry capacity is
  neither template multiplicity nor a main-workflow requirement.
- **PreparedBranch:** Exact trajectory selection and pairing intent, patient
  shell, unified template, dependent guide references and Step 5C verification
  identity. Step 6 selects this complete branch, not a raw trajectory.
- **Switch:** Preserve unchanged jaw opening, landmarks, base matrix/lock,
  Task Home and shared anatomy/environment. Swap the full branch and Step 5C
  evidence atomically. Invalidate branch confirmation/collision acknowledgement,
  plans, previews, guards and diagnostics; never stale shared setup solely
  because selection changed. Real dependency edits still invalidate dependents.
- **Legacy:** Three-trajectory templates remain inspectable but cannot become
  eligible prepared branches. Do not silently split geometry or discard case
  content. Load stays offline; migration writes only on explicit later save.
- **Plan:** [PreparedBranch correction plan](DEVELOPMENT_PLAN.md#s6-reusable-case-setup-correction-plan).
  The 2026-09-10 decision supersedes tooth-owned/per-slot-copy and raw-selector
  interpretations. Existing MRML, registry and .dentocase remain authority.
- **Evidence:** Registry schema/pure tests now cover one canonical branch record,
  selected-branch authority, explicit pairing, scoped staleness and fail-closed
  legacy migration. Static compilation and `git diff --check` pass; host pure
  suite is 85/85, container planning set 67/67 and container restore set 39/39.
  The focused runner invoked only the single-target current workflow, asserted
  eligibility, failed-activation preservation and Step 6 import, and exited 0
  with `DENTOBOT_REUSABLE_CASE_PASS`. Evidence is under
  `/tmp/dentobot-verification/prepared-branch-single-20260910/`.
  The exact failing package is
  `data/Slicer_Saved/SampleStudy1/FDI31/run2-dentobot-case-step6x5.dentocase`.
  Static MRML inspection shows the transformed Step 5C proxy plus a separately
  visible, untransformed `[Step 4C] DENTO Four Independent Robot Docks` model.
  The 2026-09-10 exact headless load reached `_openCaseBundle` successfully with
  `step6SchemaMigrationPending=True`; it then correctly classified the saved
  `DENTOBOT.FinalGuideSchemaVersion=1.0` as stale against required schema 2.0.
- **Prior evidence (2026-09-11; superseded 2026-09-15):** The targeted pass
  compiled every changed Python file using `/tmp/dentobot-case-foundation-pycache`;
  `Testing/test_step6_state.py` passed 23/23; the four task-relevant modular
  API/CMake/import checks passed; and the production module/UI contains no
  active draft-phantom import, control, callback or target-jaw fallback action.
  The aggregate modular test then reported the now-resolved 1,511-line
  `widget_template_build.py` failure against the former 1,500-line ceiling.
- **Current modular-gate evidence (2026-09-15):** The stale API manifest entries
  were reconciled to the intentional current signatures, including
  `baselineVisibility` and the correlated `syncStep6MoveItPlanningScene`
  options. The active routine-module ceiling is now 1,600 lines, with the
  public entrypoint still capped at 500 and all API/CMake/import/process-boundary
  checks retained. The complete `Testing/test_modular_structure.py` gate passes
  5/5; the current `widget_template_build.py` count is 1,520 lines.
- **Next:** Keep this one P0 lane. First capture and resolve the exact
  fingerprint-mismatch package identity reported from the manually opened
  Slicer case, then run one bounded exact runtime packet that writes its
  first-invalid/complete JSON before attempting the full repeat loop. After a
  complete guarded route, perform the ten-point normal-window review. Legacy
  branches remain inspection-only; do not infer operator acceptance from
  automated planning or continue whole-flow retries without a diagnostic
  artifact.

### Four-central-incisor exact-case campaign — superseding scope (2026-09-14)

Run FDI31 → FDI41 → FDI11 → FDI21 from the immutable open-mouth/base source,
one tooth per clean Slicer process, through 4A→4B→4C→5A→5B→5C, verified STL
export, production `.dentocase` save, fresh-process reload and exact Stage 6.
Store each target's package, STL, SHA-linked JSON and screenshots under
`data/Slicer_Saved/SampleStudy1/FDI<nn>/<run-id>/`; store the comparison under
`SampleStudy1/central-incisors/<run-id>/`. Current segmentation evidence has
all four tooth masks, pulp for FDI31/41 and no FDI11/21 pulp. Preflight
required pulp before Step 4A; absent pulp is an input-data result, not a
license to synthesize anatomy or change target depth. The preceding target's
scene is never the next target's input.

One first-causal failure per tooth marks downstream stages `NOT_RUN`. Preserve
target-specific anatomy/geometry/planner/guard failures for comparison and
propose the next tooth only after operator approval; stop on a shared source,
serializer, fingerprint or runtime
failure for a bounded root-cause correction. No base, depth, dimensions or
collision/guard policy workaround. The previous FDI31-success prerequisite and
FDI32 inclusion are superseded. The optional six-target matrix remains
downstream. See [the campaign gate](DEVELOPMENT_PLAN.md#2026-09-14-four-central-incisor-exact-case-campaign).

The operator selects Luna Max manually. On a novel ambiguous or higher-reasoning
decision, Luna stops the affected path and returns the evidence/reasoning-type
packet defined in the campaign gate; it does not silently change models,
delegate or improvise a fix. This is campaign-specific, not a global model
default.

**Execution is packet-gated:** A is the generator's STL/folder/diagnostic edit;
for each tooth, B input/fingerprint preflight, C one 4A–5C/STL/save, D
new-process reload, E exact Stage 6 route and F repeat/playback only after a
Complete E. One verified artifact or first-causal failure ends each packet.
Even a classified tooth-specific failure requires operator approval before
the next tooth; no compound instruction or automatic next packet. See the
campaign plan for exit evidence and `NOT_RUN` disposition.

**2026-09-14 operator approval and result:** After the first launch-only
failure, the operator explicitly approved the offline Slicer runtime check for
the current FDI31 semantic implementation and stated that no robot motion or
patient-facing action was authorized. The corrected current-source run used
the documented Jazzy/workspace/module-path setup and reached the exact
requested target endpoint, then stopped at the first native Stage-3 guard
failure: selected FDI31 tooth ↔ `pneumatic_spindle-Copy` at composed waypoint
255 / Stage-3 waypoint 27. The full FDI31 Step 4→Step 6 simulation remains
open; later packets and other teeth remain separately gated.

### 2026-09-14 FDI31 planner recovery — Campaign 1 supersession (historical status)

**2026-09-15 revised execution delta:** The operator has activated this same
`S6-REUSABLE-CASE-SETUP` / `S6-LIVE-01..04` task lane. The preceding Astra,
design-only and P4-end language is historical. The active task constructs and
reviews a new corrected FDI31 case from the 15 September opening/landmark/base
foundation, with FDI42/41/32/33 supports, 1.0 mm dock bores and >=2.0 mm
trajectory-guide/channel dimensions. It preserves r7/r13 unchanged and binds
the operator-specified approximately 5.2394 mm trajectory to exact saved
artifact identity before construction. Gates A–D cover scene, endpoint/
insertion, approach, and guarded withdrawal/Home/fresh-process reproduction.
One Luna Max worker may edit only explicitly assigned implementation files;
the main orchestrator owns diagnosis, runtime and acceptance. Frozen geometry,
task, policy and safety invariants remain unchanged.

**2026-09-15 source result:** `Testing/run_dentobot_stage6_target_generation.py`
now accepts the explicit `DENTOBOT_STAGE6_FDI31_TRAJECTORY_MRB` opt-in input,
strictly parses the retained Step-4A archive member, converts its LPS points
to RAS exactly once through the existing trajectory APIs, records
`SavedStep4A15Sept` provenance and does not generate an assisted duplicate.
The same correction sets the runner's FDI31 dock-bore default to `1.0 mm`.
`Testing/test_fdi31_saved_trajectory.py` exercises valid conversion and two
invalid input cases; the focused set passed 29/29, changed files compiled, and
`git diff --check` passed. This is **Implemented / Unit Verified** only. The
first corrected case, actual MRML lifecycle, geometry review and all Gates A–D
remain open.

**2026-09-15 Gate-A first-failure result:** The explicitly authorized, single
offline Slicer run `c1-gatea-fdi31-20260915-r1` passed its isolated-container,
no-competing-process, source/archive-hash and fresh-output preflight. It loaded
the 15-September source but then stopped at runner line 868 because
`logic.getTrajectorySummary(trajectory)["isValid"]` was false for the imported
line. The runner emitted `STAGE6_TARGET_FAIL FDI31 {"error": "FDI31 trajectory
is invalid"}` and a `passed: 0` generation report. No STL, saved case or reopen
acceptance exists; no planner, insertion, guard, ROS motion, controller,
hardware or patient path ran. The retained log hash is
`ea00448978da1b09b2c47577fd9f4bb77c1bb86d5325173d3f7d0be81f738270`; the FAIL
diagnostic and both Slicer screenshots are preserved under the run directory.
This closes the authorized Gate-A attempt as **FAIL / shared construction
blocker**. Do not retry or enter Gates B–D. Diagnose the exact MRML-state cause
and add a minimal source regression before seeking a new, separately authorized
runtime run.

**2026-09-15 source correction after Gate-A failure:** The line lock now occurs
only after the shared `getTrajectorySummary()` validity check, matching the
existing assisted-generation lifecycle; invalid output includes that summary.
The focused 29-test source set, `py_compile` and `git diff --check` pass. A
fresh r2 container/process/hash preflight passed, but the requested Slicer
launch was rejected before execution because the current operator message did
not explicitly authorize the separate second state-changing construction/reopen
attempt. No r2 artifact or runtime evidence exists. The remaining next action
is one explicitly authorized, isolated offline Gate-A r2 attempt only.

**2026-09-15 r2 result / conditional r3:** Explicitly authorized r2 ran once
after a clean preflight and failed before template generation. Its enriched
runner summary proves `definedPointCount: 0`, with null Entry/Target/length;
therefore r2 disproves the lock-after-validation hypothesis and localizes the
defect to point acceptance. The runner now explicitly unlocks the new saved
line before adding points and requires exactly two accepted points immediately.
The focused 29-test source set, compile and whitespace checks pass. r1/r2 are
the first two causal attempts. One explicit r3 attempt may test this distinct
live-lock hypothesis; any third failure stops autonomous runtime retry and
returns a three-attempt evidence packet. Gates B–D remain NOT RUN.

**2026-09-15 final r3 / source root cause:** r3 is the third and final
autonomous runtime attempt; it failed with zero points after the immediate
insertion assertion had already passed. Source trace attributes later removal
to the existing Step-4A bounds handler: the saved points were supplied in the
closed RAS frame while the FDI31 lower target is evaluated in the opened Case
Foundation frame. The runner now applies the existing frozen jaw matrix once to
both saved points and records those planning-frame values. Focused source checks
pass, but the retry ceiling prevents a fourth runtime attempt. Gate A remains
FAIL; any exception requires a new operator-approved verification plan. Gates
B–D and other teeth remain NOT RUN.

**2026-09-15 revised Gate-A r4 completion:** The operator then explicitly
authorized an r4 exception plan that checked the final Case Foundation mapping
before UI bounds enforcement. The single serialized offline run
`c1-gatea-fdi31-20260915-r4` emitted the runner's FDI31 PASS and all-targets
complete markers, wrote a new 84-MB `FDI31-step5c.dentocase`, verified STL and
save/reopen diagnostic, and captured post-reopen UI/viewport images. The
diagnostic status is PASS: two bounded planning-frame points retain the exact
5.239400689721231-mm saved trajectory, FDI42/41/32/33 are the four supports,
and the reopened PreparedBranch is current/verified. The outer Slicer process
returned exit 1 only during shutdown after those PASS markers, with leak
warnings; keep that process-health outcome distinct from Gate-A functionality.
Gate A is complete for corrected-case construction/save/reopen. It does not
accept Gates B-D, other teeth, physical/clinical fit, motion or hardware.

**2026-09-15 r4-only Gate-B preparation:** The operator selected the r4 saved
case as the only active execution baseline. The historical r7 endpoint runner
is not reusable because it hard-codes a different 6.6719049312-mm trajectory.
`run_dentobot_step65_exact_case_smoke.py` now offers an opt-in
`DENTOBOT_ENDPOINT_ONLY=1` branch that requires an explicit case path, loads
only that case, evaluates direct native position-axis IK at its exact saved
Target from no more than Task Home plus 13 Home-connected workspace seeds, and
records generic plus phase-aware static validity. It returns before any
approach/drilling planner, preview, insertion or route-locking call. Focused
static coverage passed 29/29; the separate serialized runtime check remains
the pending Gate-B evidence.

**2026-09-15 r4-only Gate-B runtime disposition:** That separate runtime
check is **NOT EXECUTED**, not a case or IK result. Its checksum/process
preflight passed, but three SlicerROS2 environment-initialization failures
stopped before r4 or the runner opened: unsupported `sh` option, ROS2 module
registration, then missing `librclcpp.so` for the ROS2 Slicer module. The
three-failure retry ceiling closed this runtime lane; no planner, preview,
insertion, motion, hardware or historical case path ran. The implementation
now emits `DENTOBOT_ENDPOINT_ONLY_COMPLETE` to distinguish successful runner
completion from its diagnostic result. Focused static coverage remains 29/29,
`py_compile` and `git diff --check` pass. A further runtime attempt requires a
new explicit operator-approved exception limited to this environment blocker.

**2026-09-15 P3 r4-only execution authorization:** The operator supplied that
exception and authorized the plan's P3 experiment. This supersedes the former
14-seed endpoint-only preparation as an acceptance path: the implemented
diagnostic must instead run one premanifested deterministic batch of at most
128 J1–J5 seeds using r4 current-state data and active runtime limits only.
Historical outputs are excluded completely. The prior loader error has a
specific environment correction—source Jazzy and the workspace install before
Slicer—but no P3 result exists until the serialized native batch completes.
P4 is conditional on a P3-valid endpoint; P3 excludes planner, preview,
insertion, route locking, motion, hardware and patient operations.

**2026-09-15 P3 runtime status:** Implementation and the matrix-routed runtime
contract are ready; focused checks pass. Exact r4 checksum/fresh-output/process
preflight passed. The attempted runtime dispatch was rejected before launch,
not failed, because it would be the fourth Slicer/ROS initialization attempt
after the three recorded initialization failures and the authorization did not
explicitly identify that retry risk. No case or output changed. A single,
explicitly named fourth-attempt authorization is required before executing the
already prepared offline r4 P3 batch; its no-planner/no-motion/no-hardware and
no-historical-input boundaries remain fixed.

**2026-09-15 P3 interrupted batch and minimal repair:** The authorized fourth
initialization batch was started and opened r4, but no P3 candidate result is
valid: its log exposed MoveIt planning requests before candidate evaluation.
The coordinator stopped the owned Slicer process, and the launcher/guard cleanup
was verified. No preview, execution, hardware, historical input or diagnostic
JSON occurred. The cause was the runner's automatic workspace regeneration
before its endpoint branch. P3 now returns before that production helper and a
focused source assertion enforces the ordering; the relevant static checks pass
29/29. The run is **INTERRUPTED / no endpoint verdict**. A future authorized
rerun must use a fresh evidence directory and explicitly preserve the
no-planning boundary; P4 remains NOT RUN.

**2026-09-15 P3 r2/r3 dispatch boundary:** The first replacement wrapper
started its temporary stack but exited before Slicer, `runtime.log` or any P3
candidate; the identified launcher and guard PIDs were cleaned up. The direct
P3 native IK call now disables only its generic collision prefilter so the
existing phase-aware predicate, rather than a generic ACM, determines every
converged candidate's admissibility. Focused checks remain 29/29. A subsequent
fresh r3 dispatch was rejected before launch: it exceeds the previously
authorized one replacement, and cleanup must not target all matching guard
processes by pattern. P3 remains INTERRUPTED/NOT TESTED and needs a new
explicit r3 authorization with PID-validated owned-process cleanup.

**2026-09-15 P3 r3 closure:** r3 started only its temporary stack and did not
reach Slicer, runtime logging or native candidate evaluation. The exact r3
launcher PID 3775 and guard PID 3800 were recorded from that run's evidence
before being terminated and verified absent. With r1's no-planning stop and the
r2/r3 pre-Slicer interruptions, P3 has reached its three-attempt runtime/setup
ceiling. P3 remains **NOT TESTED / INCONCLUSIVE**; P4 remains NOT RUN. A new
authorization alone does not reopen this lane: the next proposal must be a
revised, evidence-backed launcher/readiness plan using the cheapest
non-Slicer check and preserving all r4/no-planning/no-historical boundaries.

**2026-09-15 launcher/readiness repair complete:** The non-Slicer diagnostic
found that prior temporary stack launchers had left twelve log-attributed ROS
children, yielding four `/joint_states` publishers and blocking readiness.
Those exact PIDs were terminated after validation. The new dedicated P3 driver
starts `ros2 launch` in its own session/process group and terminates that group
on every exit; it sources ROS before enabling `set -u`. A fresh readiness-only
run passed immediately with one publisher and `ready:true`; teardown left zero
publishers and no stack process. Its syntax/matrix/static checks pass 29/29.
This is a verified launcher repair, not P3 endpoint evidence. P3 remains
NOT TESTED/INCONCLUSIVE at the prior retry ceiling and needs a revised explicit
runtime authorization before the repaired driver may open r4.

**2026-09-16 P3 r4 runtime interruption and source repair:** The explicitly
authorized fresh run `c1-p3-fdi31-20260916-r4` passed the exact r4 checksum and
stack readiness, then loaded r4 into Slicer. It stopped before any native IK
candidate, candidate JSON, endpoint marker, planner request, preview,
insertion, motion or hardware action. The terminal cause was the generic
post-restore `confirmTask()` call: it demands workspace-assisted limits, while
P3 must not generate that workspace because the helper submits planning
requests. The process-group trap removed the owned stack and post-run inventory
found no matching Slicer/ROS/MoveIt process. The P3 branch now uses the
restored r4 snapshot directly and fails closed if absent; it does not call
`confirmTask()` or workspace generation. Its source-order regression plus the
focused suite passed 29/29, compilation, syntax/matrix checks and Graphify
refresh passed. This is a runtime setup interruption, not endpoint evidence;
P3 remains NOT TESTED/INCONCLUSIVE and needs a new explicit one-batch r4-only
authorization before any rerun. P4 remains NOT RUN.

**2026-09-16 P3 r4 second setup interruption and ephemeral-snapshot repair:**
The separately authorized fresh run `c1-p3-fdi31-20260916-r4-r2` again passed
the r4 checksum and stack readiness and loaded r4, but produced no candidate,
candidate JSON, endpoint marker, planner request, preview, insertion or motion.
It failed closed because the offline r4 package intentionally has no persisted
confirmed-task snapshot. Endpoint-only mode now permits only that exact absence:
it constructs a non-persisted P3 snapshot with the existing pure constructor
from unchanged r4 trajectory, live Task Home, current base/task-limit/robot
fingerprints and established simulation-tool provenance. It records
`ephemeral_r4_p3_snapshot` in its output and rejects any other freshness issue.
It neither confirms a normal task nor generates workspace. Focused checks pass
29/29 with syntax/matrix/compile/diff checks and Graphify refresh. This is
still a setup interruption, not P3 endpoint evidence. A fresh explicit
one-batch r4-only authorization is required before runtime; P4 remains NOT RUN.

**2026-09-16 P3 r4 third setup interruption and native-joint mapping repair:**
The separately authorized fresh run `c1-p3-fdi31-20260916-r4-r3` passed the
locked r4 checksum, temporary-stack readiness and Slicer load, but stopped
before a native solve, candidate JSON, endpoint marker, planner request,
preview, insertion or motion. The runner had required its native joint-limit
API to equal the five planning joints; the live Slicer ROS node exposes the
complete KDL chain, J1–J5 plus the known external visual spindle. Endpoint-only
code now requires exactly that known six-joint API, reads native joint types,
maps only J1–J5 to `ROS2_JOINT_SI_ORDER`, rejects any missing/duplicate/
unexpected joint or invalid type/range, and wraps comparisons only for native
continuous J5. The external spindle remains outside all seed, IK and guard
inputs. Focused source checks passed 29/29 with syntax/matrix/compile/diff
checks and Graphify refresh. This does not establish endpoint feasibility;
P3 remains NOT TESTED/INCONCLUSIVE, a new explicit one-batch r4-only
authorization is required before runtime, and P4 remains NOT RUN.

**2026-09-16 P3 r4 completed bounded-negative endpoint gate:** The next
explicitly authorized fresh batch, `c1-p3-fdi31-20260916-r4-r4`, executed the
repaired r4-only diagnostic to completion. The direct non-executable driver
call failed before any runtime resource; the unchanged driver was then invoked
through `bash`, produced one stack/readiness pass and no second batch. It wrote
`endpoint_candidates.json` SHA-256
`8853f5208a87368d2611fd9c0a9737fe6b73b4da43de6851f4a428adee3f734c` and
`DENTOBOT_ENDPOINT_ONLY_COMPLETE`. Its complete premanifested set has 128
J1–J5 seeds, 21 converged native position-axis IK candidates, six deduplicated
clusters, zero generic-static-valid candidates, zero phase-static-valid
candidates and zero retained P4 representatives. The result is
`NO_VALID_TARGET_SOLUTION_FOUND_IN_BOUNDED_SEARCH`; all converged candidates
failed the existing phase guard because their provisional drill tip left the
approved Entry-to-Target corridor. Generic static records also list
Template↔visual-spindle and target-tooth↔burr contacts. `Planning request=0`;
the run did not use preview, joint/controller/hardware motion, spindle/patient
action or historical data. Cleanup left zero matching runtime processes. This
is a completed bounded negative, not a global feasibility claim. Per the P3
contract, do not add seeds, tune the solver, alter geometry/policy or run P4.
Campaign 1 is stopped at P3 pending architectural review; P4 remains NOT RUN.

### 2026-09-16 P3 diagnostic-correctness repair and saved-candidate revalidation

The operator directed a correction of the preceding classification, not a new
IK experiment. The old evidence JSON remains immutable input (SHA-256
`8853f5208a87368d2611fd9c0a9737fe6b73b4da43de6851f4a428adee3f734c`) and
supplies exactly its 21 converged canonical J1–J5 vectors. Review confirmed
two defects: `endpoint_only_diagnostic()` labelled a Home-to-endpoint transition
as phase-static, and generic-static collision diagnostics independently vetoed
contact that the authoritative phase-aware guard may permit. Its bounded-negative
result is therefore **superseded as a phase-static endpoint verdict**; historical
generic contact evidence and causal history are retained, not erased.

The repaired runner sends one unique, increasing-sequence,
`validate_only=true`, `validation_kind="static_state"`, `phase="drilling"`
request per saved vector. It retains exact request/guard identity, one-state
joint/sample attribution, corridor/contact/warning fields and native FK.
Admissibility is unchanged residual/bounds plus a trustworthy authoritative
phase-static acceptance only. Generic contacts and native FK are diagnostic;
missing, stale or mismatched replies fail closed as `INCONCLUSIVE`. Static
setup avoids the raw joint stream and Task Home transition; normal transition
callers retain their existing behavior.

Corrective runtime r1 stopped before a candidate after legacy ordinary
scene-acknowledgement issued an unchanged-current-state raw **simulation**
request and failed 31-versus-zero readback; no hardware or candidate action
followed. r2 stopped before a candidate because r4 has no persisted Task Home.
r3 stopped before a candidate because the normal guide-ID lookup rejected the
intentionally deferred static audit. The narrow final repair permits only that
exact `RuntimeAcknowledgementDeferred`/`Deferred` audit when `static_only=True`,
while still requiring the same approved, successfully published guide records.
Focused checks (compile, launcher/matrix syntax, focused P3/bridge/config/
recovery/trajectory tests and diff hygiene) pass: **79 passed**; Graphify is
refreshed.

All three corrective attempts cleaned up but emitted no new endpoint JSON or
candidate response. Corrected phase-static accepted/rejected/unknown counts,
rejection reasons, policy-warning versus housing-clear status, native evidence
and attributable screenshots are **not measured**. Corrected P3 is
**INCONCLUSIVE**. The static-runtime causal retry ceiling is exhausted: do not
launch a fourth r4-only batch without an explicit operator ceiling exception.
P4 remains not authorized.

**2026-09-16 completion update — fourth r4-only static batch and retained-evidence
correction:** The operator then expressly granted the one fourth fresh
revalidation batch after the deferred-audit guide-ID repair. It evaluated no
new seeds or IK: only the same 21 saved J1–J5 vectors from immutable input SHA
`8853f5208a87368d2611fd9c0a9737fe6b73b4da43de6851f4a428adee3f734c` against
locked Gate-A r4 SHA
`6235772e2d14d74b5417d42ed8a5e0cc160df82c77efd3014f589dd264113d83`.
The fresh raw artifact is
`c1-p3-fdi31-20260916-r4-static-revalidation-r4/endpoint_candidates.json`
(SHA `d5a3ef8857b518a293d1ed7c8a9c750d0bfe0922110150242c4a4107729acd4f`).
It contains 21 command-successful, unique/increasing (1–21), drilling,
`validate_only`, `static_state` replies with matching task/policy/session IDs,
31/31 scene objects and one requested/starting/evaluated state each.

The raw native guard accepted all 21, but the original runner treated all as
inconclusive because C++ `collision_guard` writes status doubles with
`std::setprecision(12)` and the Python attribution check required bit-exact
joint echoes. The source now accepts only that formatter-bounded echo
(`rel_tol=1e-12`, `abs_tol=5e-13`) while retaining all identity, policy, scene
and single-sample checks. The maximum observed echo delta is
`4.875266856885219e-13`. The new companion evidence
`endpoint_candidates.corrected_static_attribution.json` (SHA
`ec6ad4febcf202de3469303f53ceb4d8056f14d2d6e03272a467ba5938fce362`)
preserves every raw request, response, native FK and generic diagnostic and
records zero new native queries/IK calls. It correctly classifies **21
accepted, 0 rejected, 0 inconclusive and 21 admissible**.

Every generic-static diagnostic still rejects the explicit configuration for
`[Step 5C] DENTO Final Printable Template`↔`pneumatic_spindle-Copy` and
target-tooth↔`burr`; those contacts are evidence, not phase-static vetoes. The
authoritative guard accepts all 21 with an explicit configured, non-rotating
template/spindle contact warning at `0.326643468686`–`0.406108573858 mm`, below
its `0.500000 mm` simulation limit; burr-to-task contact is explicitly
suppressed for exploratory simulation. Thus no candidate is literally
guide/housing-clear relative to the final template, while native self,
unrelated-world and corridor checks pass for all 21. Residuals remain
`0.0003391622610791675`–`0.14985054830164712 mm`; axis residuals remain
`0.00000845192788808014`–`0.048384536734871954°`; bounds and native FK pass
for all 21. No image is claimed because the static-only run applied or displayed
no candidate state.

Focused compilation/pytest/diff checks pass **80 tests**, and the required
Graphify overlay refresh completed. The owned fourth stack is torn down; a
final container process inventory found no P3 launcher, Slicer, launch or
guard process. This establishes the corrected static endpoint **PASS** and
conditionally admits P4 only. P4 is still NOT RUN and needs separate operator
authorization; no fifth static batch, planning, motion/hardware action or
invariant/policy change is authorized.

**2026-09-16 P4/P5 completion update:** The operator later gave explicit
authority for bounded P4 and P5 diagnostic work while retaining the frozen
r4/case/task/tool/base/limit/tolerance/collision policy and prohibitions on
applied motion, hardware, powered spindle and patient action. P4's new
`c1-p4-fdi31-20260916-r4/insertion_branches.json` (SHA-256
`3cc1759d1dc5042748d729d5e2a1ae784a94a60d33cb7c8350695b321492bc72`)
records six complete, diagnostic-only Entry-to-Target witnesses. P5's new
`c1-p5-fdi31-20260916-r4/approach_branches.json` (SHA-256
`6455a52eb170ca304f33bf1b4e76bcb583bc552cc5991971fa3e9593546b7f9b`)
is `SAMPLED_PASS`: one fresh monitored simulation start, P4 source candidate
6, one five-second current-RRTConnect Stage-1 request, a complete Stage 2 and
one P4 Entry join. It retains 222 strictly increasing, unique,
`validate_only` requests (one static, 208 Stage-1, 12 Stage-2 and one join),
all accepted with correlated task/scene/policy/session evidence. Stage 2's
native FK endpoint residual is `0.0004285879962906579 mm` and
`0.0002018339679783406°`; the raw stream was false before/after and native
positions stayed unchanged. Its existing Cartesian request returned no native
points, then the existing bounded position-axis continuity fallback completed
the fixed-axis diagnostic line; no OMPL/configuration change was made.

This reaches P5 only. It does not override the retained P3 guide-warning
interpretation, prove physical seating or housing clearance, or authorize P6,
P7, insertion preview, withdrawal/Home, repeat/full cycle, another tooth,
hardware, spindle or patient work. The next action is a separately authorized
integration/physical-review decision, not an automatic follow-on.

**2026-09-17 operator pause and GUI-verification handoff:** The operator has
now explicitly paused Campaign 1 at P5 and redirected the active work to
normal-window operator workflow verification before any further gate work.
This supersedes only the previous generic “next integration decision” routing;
it preserves every Gate-A/P3/P4/P5 result and hash at its recorded evidence
level.

The key distinction is now part of acceptance: locked r4 did not exercise the
Assisted Trajectory Generation button. Its construction runner inserted the
saved Step-4A 15 September Entry/Target coordinates and tagged the resulting
line `SavedStep4A15Sept`. The P5 runner opened that prepared case, activated the
existing verified `PreparedBranch` by production logic, loaded the robot, then
entered a diagnostic-only runtime branch before the ordinary Connect/Task
Home/workspace path. It intentionally created an ephemeral task identity from
the fresh monitored simulation start and never saved/applied Task Home,
generated workspace, previewed, or applied motion. Consequently the automated
record is not operator evidence that the normal GUI works.

**Operator-intent clarification:** By “planner fix,” the operator expected a
headless Slicer run of the same production sequence an operator follows—not a
special branch that starts from a prepared case and calls internal services
around failed GUI gates. The P3/P4/P5 computations are real native
IK/FK/MoveIt/guard work, not mocked façade returns, but their demonstrated
integration is exact-r4 and diagnostic-harness-specific. P5 itself ends at the
P4 Entry witness; P4 separately supplies the Entry-to-Target witnesses. Their
compatibility is useful bounded evidence, but it is not one uninterrupted
GUI-created, executable start-to-Target plan and must not be reported as
“Step 6.5 reached Target.”

The guided task reuses `VERIFY-LEARN-01` and has two non-interchangeable
tracks:

- **Locked-r4 inspection:** open only
  `c1-gatea-fdi31-20260915-r4/FDI31-step5c.dentocase`; do not delete,
  regenerate, unlock or move its trajectory/base/guide. Verify the saved FDI31
  Entry/Target line in oblique MPR, opened-mouth Case Foundation, support and
  guide/template registration, active registry slot, `PreparedBranch`
  activation, offline robot display and Manual Simulation Base state. Assisted
  generation is expected to be disabled because the target already has a
  trajectory and existing plans are never overwritten.
- **Assisted-generation/operator workflow:** use a fresh or disposable-copy
  case with no trajectory for the selected target. Require Reviewed
  segmentation, selected target, current Case Foundation, a unique non-empty
  `HIGH`-confidence tooth↔pulp association, the requested one/two crown Entry
  points and explicit oblique-MPR correction/approval of every generated line.
  Continue 4B→4C→5A→5B→5C→6 only while the preceding geometry is visibly
  registered and current. A detached trajectory/guide, stale status, ambiguous
  pulp association or save/reopen mismatch is the first failure and stops the
  lane.

Acceptance for this pause is an operator-readable record containing the exact
case/copy identity, GUI mode, visible status text at each checkpoint,
screenshots, first failure or completed boundary, save/reopen result, and a
mapping to the responsible existing task owner. Automated checks may be used
only as focused discriminators under the verification protocol; they cannot
substitute for the normal-window observation. Return to the P-series requires
a coordinator reconciliation that explicitly states whether P5 remains the
resume anchor and which next gate is authorized. There is no automatic P3–P5
rerun or P6 entry.

**2026-09-17 bounded recovery closeout:** The operator stopped the extended
analysis because the available account quota was nearly exhausted and directed
the next session to implement the preserved findings rather than repeat the
audit. Read-only reconciliation classified the current work as follows:

- **Confirmed from saved package state:** `dentobot-case-15sept.dentocase`
  retains both the untransformed closed-source FDI31 display and the
  jaw-transform-parented moving-lower FDI31 display as visible. The resulting
  detached tooth is a restore/display-ownership defect. Preserve both data
  sources; the correction belongs at the shared visibility transition, not in
  ad-hoc target-selection cleanup.
- **Mechanism confirmed; runtime discriminator missing:** assisted placement
  reaches `startAssistedTrajectoryEntryPlacement`, calls `StartPlaceMode(0)`,
  and raises when the active markup ID or placement-valid state is wrong. No
  retained traceback/telemetry distinguishes those two postconditions. The
  first implementation increment must add that bounded evidence and fix the
  demonstrated shared native-state failure only.
- **Validation working but recovery unproved:** the FDI21 warning correctly
  rejects reuse of an FDI31-owned assisted-entry node. Target switching must
  leave placement mode and replace/rebind stale target-owned state while
  retaining this provenance guard.
- **Diagnostic traceability defect:** P5 Stage-2 edge 1 and its final P4 Entry
  join reuse one request ID. Distinct sequence numbers, vectors and responses
  preserve the saved result, but future IDs must be globally unique.
- **Acceptance boundary:** corrected P3, P4 and P5 remain useful diagnostic
  evidence. P5 does not prove normal Task Home/workspace/task confirmation,
  continuous swept-volume collision checking, literal housing clearance,
  physical fit, or operator-visible robot/anatomy parity. P5 operator
  verification therefore remains blocked.

Three earlier read-only evidence workers completed useful manual-workflow,
technical P3–P5 and artifact-inventory summaries. A fresh independent Sol
reviewer then terminated before substantive review at the account usage limit.
No worker was resumed, no missing review was recreated, and no worker output is
promoted to acceptance without coordinator reconciliation. The canonical
detail is Recovery Report Section AW and the 2026-09-17 logbook.

The operator accepted the causal review and assigned Astra architecture and Luna
Max implementation/evidence/documentation ownership. Reuse
`S6-REUSABLE-CASE-SETUP`, `S6-LIVE-01..04` and their existing upstream P0
dependencies. The complete bounded contract, write allowlist, gate acceptance,
runtime-approval boundary, exact Luna prompts and R1 report specification are in
[FDI31 Campaign 1](diagnostics/FDI31_PLANNER_RECOVERY_CAMPAIGN_1.md).

This supersedes earlier assertions that external geometry correction is the only
next path. The r13/r14 evidence establishes tested collisions, not exhaustive
infeasibility. Campaign 1 is P0 baseline, P1 input/scene audit with P2 supporting
instrumentation, P3 bounded endpoint and conditional P4 insertion, then Astra
review. P5–P7 are provisional later phases. On 2026-09-14 the operator
approved P1/P2 only. P1's saved-input/machine checks are PASS, but P1 overall
scene correctness and operator review are INCOMPLETE. P2 remains
`INCONCLUSIVE`: the initial missing-runtime condition was recovered once under
the later explicit cleanup authorization, and the final bounded packet now
contains two native diagnostic reconstructions with separate static and
transition records. The final scene acknowledgement reconciles 31/31 IDs,
poses/bounds and policy; the earlier `expected 31, observed 0` result remains
preserved historical evidence. The exact seven conflicting DentoBot simulation
processes were verified and stopped with SIGINT, one coherent simulation-only
stack reached ready on domain 73, and that launch-owned stack was then cleaned
up. The canonical final evidence is `c1-p1p2-recheck-20260914-r6`, with the
earlier attempts retained; no P3/P4 or motion was started. The three-failure
ceiling and all frozen case/task/tool/policy invariants remain. The corrected
handoff is now proven through Slicer entry, TCP/spindle FK pairing passes, and
burr-transform alias repair is now source-repaired and unit-verified. Native
verification of that repair was not completed because the shared container
exited 143 during a malformed continuation command and the standing boundary
excludes a restart. Do not infer operator review, input/geometry acceptance or
full-cycle acceptance from diagnostics, runner/test PASS markers, generated
flags or execution approval.

**2026-09-14 source-only handoff diagnosis:** The approved final2 stack log
proves simulation services initialized, but does not preserve the wrapper's
readiness return code/parser result or a Slicer-launch request. The cause is
therefore unproven. The existing launcher now delegates its unchanged
simulation/readiness/cleanup flow to
`Workspace/scripts/dentobot-simulation-slicer-handoff.bash`, which records
stage/reason markers and preserves the initiating diagnostic status. Local
stub tests pass for ready handoff, readiness failure and diagnostic-failure
cleanup. This historical source-only boundary was followed by the later
explicitly authorized bounded recheck: the first corrected invocation exposed
the `--no-main-window` Slicer-entry defect, and the final two attempts reached
Slicer and produced the current native packet. A subsequent source-only alias
repair passed focused tests, but native verification was blocked when the
shared container exited 143 during a malformed continuation command. This
source-only/native-launch history is superseded by the retained final packet
below; keep all P1 review and downstream gates open.

**2026-09-15 current disposition:** The retained final packet is the bounded
native P2 diagnostic/evidence result: P1 saved-input/machine checks are PASS
for completed checks, P1 overall scene correctness and operator review are
INCOMPLETE, and P2 bounded diagnostic evidence is PASS with campaign gate
`USER_REVIEW_REQUIRED`. It separates phase-aware static rejection of both
endpoints (final printable template ↔ spindle), generic static contacts
(including FDI31 tooth ↔ spindle and tooth ↔ burr), and Home-to-endpoint
corridor rejection. It also records trusted 31/31 scene acknowledgement and
TCP/spindle/burr FK evidence. The earlier zero-object, launcher and
container-exit results remain historical attempts; they do not make the
retained packet inconclusive. Operator acceptance of the 15 selections,
scene, geometry and contact interpretation remains unrecorded, and no P3/P4
or full-cycle acceptance follows.

**2026-09-15 Section-W source-only recapture correction:** The rejected
display recaptures remain historical and are not faithful state/geometry
evidence. The retained review driver now separates the endpoint from the
Home-to-endpoint sample, reconstructs prepared world-RAS display copies,
checks geometry fingerprints/bounds, compares displayed TCP/burr/spindle link
frames with saved endpoint native FK, and verifies the same review robot nodes
and transforms across save/reopen. Production transient robot persistence and
all collision/native policy remain unchanged. Ten focused pure tests pass.
One approved endpoint-only Slicer session loaded the retained MRB but stopped
before capture because this runtime lacks
`vtkMRMLModelDisplayNode.SetPropertiesLabelVisibility`; its error manifest is
preserved separately and contains no image or review MRB. Endpoint parity was
not reached, so this is a runtime compatibility stop rather than an endpoint
geometry/FK parity failure. The driver consumes a future explicitly saved
evaluated-sample FK record but does not substitute endpoint/offline FK. The
transition image remains `NOT_RUN` until the saved packet contains native FK
matrices for evaluated sample 1/134. No second display runtime is authorized
without a new explicit approval.
Operator scene review and acceptance remain open.

**2026-09-15 endpoint-only repair continuation:** The operator later
authorized a bounded rerun and source fixes for Slicer-session blockers. Two
minimal compatibility repairs were pure-verified (`12 focused tests`): an
optional display-label API guard and a model parent-transform world-matrix
fallback. The third and final scoped display attempt reached the parity gate
and failed closed. The final printable template matched exactly, but the
prepared FDI31 target fingerprint differed and its maximum bound error was
`40.74010467529297 mm` versus the `0.05 mm` tolerance. Robot mesh/link
transforms matched; native-vs-offline FK matched for TCP, burr and spindle;
displayed burr/spindle matched native FK; displayed TCP remained unavailable
because the seven displayed models contain no TCP model. Save/reopen was not
reached. The repair2 manifest and prior compatibility-error manifests are
preserved. Endpoint review is `BLOCKED`, transition is `NOT_RUN`, no geometry
or policy was changed, and the display-runtime retry ceiling is reached.
P1/P2 campaign acceptance and operator scene review remain open.

**2026-09-15 revised endpoint parity repair:** The operator explicitly
authorized source-only correction and focused testing for the two evidenced
repair2 defects, followed by at most three targeted endpoint-only offline
Slicer attempts. The driver now reuses the native Case Foundation jaw-opening
transform exactly once and the native triangle-filter semantics for the
display-only target copy; it also derives the meshless canonical
`dentobot_drill_tcp` from the actual displayed `pneumatic_spindle-Copy` mesh,
its visual-origin offset and the retained URDF fixed relation, with loaded
robot-profile identity matching. The focused suite passes 18 tests and the
container-mounted source hash matches the host. The repair3 pre-execution
command/output location is recorded in report Section AE. This remains an
endpoint-review evidence task only: transition is NOT_RUN, operator/P1/P2
acceptance is open, and P3/P4 plus geometry/policy/hardware actions remain
unauthorized.

**2026-09-15 endpoint parity repair result:** The final authorized repair5
attempt passed the endpoint machine parity gate. It verified native target and
template fingerprints/bounds, exactly one Case Foundation jaw preparation,
robot-description identity, displayed seven-link/model transforms, derived
meshless TCP/burr/spindle FK, and unchanged pose across save/reopen. The
separate review MRB, JSON packet and two nonblank endpoint images are recorded
in recovery report Section AH. The transition image remains `NOT_RUN` because
saved native sample-1/134 FK is unavailable. Visual label/scale review and
operator acceptance remain open; this does not close P1 overall scene review,
change the retained native P2 status, or authorize P3/P4.

**2026-09-15 operator visual review:** The operator accepts the repair5 endpoint
screenshots and requests a next-phase Luna prompt. The visual-review blocker
is closed for this retained endpoint only. Reconcile remaining P1 input/scene
decisions before conditional P3 under the existing Campaign-1 contract;
historical transition imagery is not a static-endpoint prerequisite. No blanket
input acceptance, runtime execution, or P4 approval is recorded. See report AI.

**2026-09-15 Step-4A–5B current-session delta:** Under
`S6-REUSABLE-CASE-SETUP`, the operator now specifically confirms FDI42/41 and
FDI33/32 as the four Step-4B support neighbours but reports a duplicate
closed/opened FDI31 display, oblique-looking Step-4C/5A planes and a legacy
1.5-mm Step-5B guide-hole failure. Report AK records read-only source/package
and r7 plane metrics. New-case dock/5A defaults and the Step-5B preflight/status
defect are corrected source-only with 24 focused pure tests passing; frozen
source/r7 geometry and policy remain unchanged. The live plane/display state
is not numerically captured, so P1 overall remains INCOMPLETE and conditional
P3 is not entered. `W4B-P2-SUPPORT-AUTO`, `W5-U-01`, `W5-U-05` retain their
separate priority/physical/UX acceptance slices; this manual support review
does not close those tasks.

**2026-09-15 separate test-case readback:** The operator deleted a perceived
FDI31 artifact and saved `dentobot-case-15sept.dentocase` for testing. Report
AL records its checksum and integrity: the active FDI31 registry has no target
or trajectory, but the MRML Step-4A target ID/ROI remain and FDI31 is saved
3D-visible in both the closed source and opened moving-lower segmentation.
The source mask and derived segment-file bytes match the immutable 13Sept
case; repeated Subject Hierarchy virtual entries increased across segments,
not just FDI31. This is a separate partial test fixture without 4C/5A planes,
final template or PreparedBranch. It neither replaces the frozen Campaign-1
input nor closes P1 scene review; no app/runtime test or P3/P4 was run.

**2026-09-15 clarified fixture and saved Step-5B scene:** The operator intends
15Sept as a reusable open-mouth + placed-base foundation to avoid repeating
landmarks/base placement and identifies `FDI31/2026-09-15-Scene.mrb` as the
separate Step-5B snapshot. Report AM verifies identical source segmentation,
jaw-opening and base matrices between the two; the base placement is saved but
`robotBaseMountLocked=False`, so 15Sept is not an eligible `FoundationOnly`
case. The Step-5B MRB has all four confirmed supports, four 1.0-mm robot-dock
bores, a 4-mm Step-5A plane, current shell, no final template, and the saved
1.5-mm trajectory-guide hole. Its source FDI31 is hidden in 3D and opened
moving-lower FDI31 visible, unlike the separate 15Sept bundle. The Step-5A
plane origin agrees with Entry+4 mm, but its displayed world normal is
42.454° from its saved crown-cap fit normal; the difference is the jaw-opening
rotation. Shared `CaseFoundationLogicMixin` reparenting preserved markup
positions but not plane normals. A minimal source-only repair restores the
plane world normal across reparent; an old-source focused stub regression
failed, then passed, and the focused file passed 25/25. The saved MRB was not
rewritten or reopened in Slicer, so runtime/world-frame parity and operator
scene correctness remain open. P1 overall INCOMPLETE; P2 retained PASS with
USER_REVIEW_REQUIRED; P3/P4 paused.

## FDI11 / Stage 3 — paused pending workflow integrity

- **ID:** `S6-FDI11-DEPTH`; **Priority:** Unprioritized; related P0
  acceptance stays under `S6-LIVE-01..05`.
- **Latest evidence:** The recorded -4 mm in-memory local-Z trial reaches the
  6 mm Stage-3 endpoint kinematically and records configured housing/template
  warnings, then rejects non-rotating spindle housing contact with adjacent
  FDI21 at the final drilling waypoint. Complete preview, axial withdrawal,
  monitored Home and the fresh repeat cycle have not passed.
- **Case:** The reviewed source package remains unchanged:
  `data/Slicer_Saved/SampleStudy1/FDI11/dentobot-case-step6x4x2.dentocase`.
  Its source trajectory is 7.977207292891484 mm; the recorded simulation cap
  is 6 mm, with no claim that the capped endpoint is pulp.
- **Policy evidence:** Bounded configured housing/guide contact and 0.1 mm
  burr/guide clearance are case-specific recorded authorizations, not defaults.
  Adjacent-anatomy contact remains forbidden. This cleanup does not change
  dimensions, base, depth, margins, guards or endpoint rules.
- **References:** `logbook/2026-09-08.md` hard-constraint checkpoint;
  `logbook/2026-09-09.md` exact-case evidence; retained views/state at
  `data/dentobot-runs/fdi21-blocker-20260909/`. Older fractions and former
  2 mm burr/x4 results remain historical evidence only.
- **Next:** After PreparedBranch/main-workflow integrity acceptance, reconcile
  current reviewed case/tool/guide identity against the retained blocker and
  propose the smallest applicable Stage-3 check. Do not automatically rerun,
  relocate the base or relax collision rules from this entry.

## Assisted access endpoint — 2026-09-07

- **ID:** `S4A-PULP-ENDPOINT`; **Priority:** 0; **State:** Source and focused automated verification passed (2026-09-10); exact FDI31 normal-window anatomical review remains pending.
- **Operator observation:** The displayed FDI31 assisted target appears inside the pulp mask in 2D but does not contact the displayed pulp surface in 3D. The operator requires the mismatch fixed now, not deferred.
- **Exact-case finding:** The 4.23 mm line in `FDI31-step5c.mrb` belongs to a saved three-line set and has no current assisted-generation provenance; the Placement menu describes the creation action, not an existing line's origin. Slice projection also rendered off-slice Entry/Target glyphs over the mask. The saved Target is at the native voxel boundary, while the smoothed closed surface can diverge from that boundary.
- **Corrected contract:** New single/dual assisted generation must prove a shared interval between the selected tooth's FDI-matched binary pulp mask and its displayed 3D surface, preserve Entry and direction, and atomically set Target to the first point contained by both (the farther entry boundary). Record both boundary points and their offset. Reject a native/display miss or non-overlap. Off-slice trajectory projection is disabled. Existing/manual trajectories and Step 6 policy remain unchanged.
- **Verification:** Final diff check and scoped pycompile passed; pure endpoint test passed 1/1; focused Slicer target emitted `DENTOBOT_ASSISTED_PULP_PASS` and `DENTOBOT_STEP4A_P0_PASS`, exited 0, and left no Slicer process. Evidence: `/tmp/dentobot-verification/step4a-p0-20260910/result.json`.
- **Next:** Reload the module, deliberately delete the legacy FDI31 set, generate one current assisted line, and record normal-window 3D surface contact plus non-projecting 2D slice behavior before anatomical approval.

## P0 dental semantic normalization and pulp-to-tooth association — 2026-09-14

- **ID:** `S3-P0-DENTAL-SEMANTICS`; **Priority:** 0.
- **State:** Active implementation/integration. The source trace, bounded
  implementation plan, pure A-H semantic core, MRML registry integration and
  target-specific planning gate are implemented; integrated Slicer runtime,
  geometry, save/reopen and downstream full-workflow evidence remain open.
- **Operator note:** The attached `dentonote` requests a reliable semantic
  bridge between TotalSegmentator output and DentoWorkflow target/planning
  logic. The operator specifically asked for inspection and a detailed plan
  before any large refactor.
- **Triage:** Active investigation/design pending implementation. Keep this
  as one P0 owner. Do not create an FDI11-only special case or a second case
  database. Existing `S4A-PULP-ENDPOINT` retains displayed/native endpoint
  geometry; `S6-REUSABLE-CASE-SETUP` retains case/campaign sequencing and
  save/reopen acceptance.

### Source trace and current evidence

1. `Inference/src/dentobot_inference/segmentation.py` invokes
   `totalsegmentator(..., task="teeth", ml=True)` and reads the installed
   `class_map["teeth"]`. It preserves the actual raw `{id, name}` pairs in
   `result["labels"]`; `validate_segmentation_output()` checks geometry,
   integer labels, unknown IDs and per-label counts. Source inspection found
   no `label_value == 111` or `pulp_label_id - 100` assumption in the
   inference backend.
2. `widget_case_backend.py` imports the returned multilabel NIfTI into one
   Slicer segmentation. It validates label IDs/counts and builds a color table
   whose segment names come directly from the backend report. The importer
   does not independently validate that imported names are semantically
   equivalent to the report, and it does not create tooth/pulp relations.
3. `logic_segmentation.py` stores `SegmentMetricsJson` with segment ID, raw
   label ID, raw name, voxel count and volume. `describeSegmentForReview()`
   currently classifies by name substrings and parses `_fdi<digits>`; for a
   pulp suffix shaped like `1<FDI>` it strips the first digit. This is a
   presentation-compatible legacy grammar, not a verified backend semantic
   contract. `getSegmentationReviewRecords()` currently rebuilds records from
   the current Slicer display name.
4. `logic_lineage.py` treats review records with category `Teeth` as target
   teeth and validates a target by segment ID plus that derived category. It
   does not require canonical FDI provenance, non-empty geometry, or a
   validated pulp relation.
5. `logic_workflow.py` obtains assisted pulp by filtering review records for
   category `Pulp and root canals` and equal derived `fdiNumber`, then uses
   only that pulp mask/surface for the existing first-shared native/displayed
   endpoint calculation. It has no target-to-pulp spatial association gate.
6. `DENTOCaseBundle` persists the MRML scene inside `scene/case.mrb`, and the
   current segmentation node's `SegmentMetricsJson` therefore survives in the
   MRB. `workflow/lineage.json` currently records only the segmentation node
   inventory/segment count, so a semantic registry is not independently
   checked on reload.
7. Read-only inspection of
   `data/Slicer_Saved/SampleStudy1/FDI11/dentobot-case-step5b.dentocase` and
   `dentobot-case-13sept.dentocase` found 54 segment names, 18 pulp names,
   `upper_right_central_incisor_fdi11` at label 11, and no `*_pulp_fdi11*` or
   `*_pulp_fdi21*` entry. The current exact evidence therefore classifies
   FDI11/FDI21 missing pulp as an input-data failure. It does not prove that a
   different visual FDI11 report was not misclassified by TotalSegmentator,
   its class map, Slicer import, or our parser.

**Unresolved origin boundary:** The source audit rules out the suspected
hard-coded label arithmetic in the inference backend. A read-only inspection
now captures the installed 77-entry class map with fingerprint
`57c95824f888749b879511e06e4590b2029cdb35f1791b4a050ecebc35d9b328`; the
retained report, NIfTI and saved imported `.seg.nrrd` agree on the detected
54-label subset, including raw FDI31 tooth/pulp entries. A fresh current-
revision Slicer import has not yet run, so no claim about a model-level FDI11
identity error is made from the retained package.

### Smallest robust architecture

Keep `SegmentationLogicMixin` as the existing MRML-facing owner and add one
small pure helper module, `dentobot_workflow/dental_semantics.py`, only for
plain-record normalization, component association and validation math. Do not
add a generic registry service, a second database, a new case archive member,
or a new workflow façade.

The import path becomes:

```text
backend report/class map (raw source facts)
  -> canonical segment records in existing SegmentMetricsJson
  -> target-specific pulp association/validation
  -> target selection and assisted endpoint
```

The raw source name, raw label ID and terminology remain audit evidence. A
versioned backend adapter may use the report's source map to identify raw
structure kind and an optional FDI hint, but no downstream planner may parse a
Slicer display name or infer FDI from an arithmetic label relationship.
Unknown or changed backend naming becomes `UNRESOLVED`/reviewable input, not a
guess. Legacy name parsing is retained only as an explicit migration fallback
and is never sufficient by itself for pulp-dependent planning.

Each canonical record must carry, at minimum:

```text
segmentId                    MRML segment identity
sourceLabelId/sourceName     raw audit provenance only
structureType                TOOTH, PULP, or another explicit type
canonicalName                Tooth_FDI11 / Pulp_FDI11 when known
fdiNumber                    optional canonical FDI
parentToothSegmentIds       zero/one/many source segment IDs for pulp
associationMethod            source-hint, spatial, or manual-confirmed
associationConfidence        HIGH, MEDIUM, or null for failed states
validationState              VALID, AMBIGUOUS, MISSING, INVALID,
                              or MANUALLY_CONFIRMED
associationEvidence          deterministic metrics and runner-up details
```

Canonical records are stored by extending the existing
`DENTOBOT.SegmentMetricsJson`; node attributes carry the semantic schema
version, overall status and a deterministic semantic fingerprint. The
fingerprint includes segment IDs/label IDs and canonical relations, but not
display-only raw names, so a backend naming change cannot break an already
validated case. The full registry stays in MRML/MRB; `workflow/lineage.json`
adds only the semantic version/status/fingerprint to its existing segmentation
node record for save/reload integrity.

### Target-specific association algorithm

1. At import or migration, register every tooth candidate and every pulp
   candidate/component as existing geometry. Build tooth records globally, but
   defer expensive pulp-parent decisions until a target is selected.
2. For the selected canonical tooth, require a unique valid FDI, non-empty
   binary labelmap and usable closed surface. Enumerate every non-empty pulp
   segment in the segmentation and split its binary mask into deterministic
   connected components without creating a new anatomical segment.
3. Transform occupied component voxel centers and both tooth/pulp surfaces to
   the same world-RAS millimetre frame. For every component/tooth pair record
   minimum and robust central surface distances, centroid/bounds relation,
   enclosure or inside fraction against the closed tooth surface, and the
   fraction of component samples for which that tooth is the nearest
   consistent tooth. Voxel intersection is supporting evidence only.
4. Rank candidates using the combined evidence and retain the best and
   second-best candidate plus all raw metrics. Do not use nearest centroid as
   the decision by itself. A raw FDI hint may corroborate the result but cannot
   override a geometric disagreement.
5. Group fragmented components only when every component is non-empty,
   geometrically consistent with the same tooth and does not create a
   duplicate/conflicting parent. If components split their best association
   across adjacent teeth, or if the evidence disagrees without a safe margin,
   return `AMBIGUOUS`/`INVALID` and do not merge them.
6. Calibrate any numeric score/margin against the A–H fixtures before using
   it as a confidence band. Until that calibration exists, preserve raw
   metrics and fail closed rather than inventing an anatomical threshold.

Confidence and failure behavior is:

| Result | Meaning and workflow behavior |
|---|---|
| `HIGH` + `VALID` | Unique target tooth/pulp relation; eligible for the current pulp-dependent gate, still retaining ordinary manual verification. |
| `MEDIUM` | Spatially plausible but lower margin or source-hint disagreement; eligible only when all validation rules pass and the required review/confirmation transitions it to `MANUALLY_CONFIRMED`. |
| `AMBIGUOUS` | Competing adjacent candidate, inconsistent components, or unresolved top-two margin; block automatic pulp-dependent planning. |
| `MISSING` | No non-empty pulp candidate for the target; block pulp-dependent planning and preserve the target tooth for non-pulp review. |
| `INVALID` | Malformed geometry/metadata, duplicate canonical parent, non-finite metrics, or contradiction that cannot be safely resolved; block and expose diagnostics. |
| `MANUALLY_CONFIRMED` | Explicit review accepted a non-HIGH result without changing source geometry; preserve who/when/evidence and keep the trajectory's manual-verification flag. |

No state creates missing pulp. A target may proceed into the existing S4A
shared native/displayed-surface endpoint code only after the selected tooth,
one or more existing pulp components, and their spatial relation pass the
canonical validation gate. Step 6 remains downstream and unchanged.

### Implementation order and owned files

1. **Evidence adapter:** capture of the installed TotalSegmentator
   `class_map["teeth"]`, retained raw report, NIfTI IDs, imported Slicer IDs/
   names and saved `.seg.nrrd` metadata is complete as read-only evidence;
   fresh current-revision import remains pending.
2. **Pure semantics:** implemented the plain-record normalizer, deterministic
   component metrics/ranking, confidence states and A-H tests in one focused
   semantic test file. The pure layer has no Slicer dependency.
3. **MRML import/review:** `logic_segmentation.py` now builds/reads the
   canonical registry after validated import, keeps raw fields for audit,
   projects canonical records, and leaves the old name parser as a
   migration-only fallback.
4. **Target/planning gate:** `logic_lineage.py` and `logic_workflow.py` now
   call one canonical target-anatomy query. Existing S4A endpoint math, line
   creation and no-overwrite rules are preserved; the FDI/name pulp lookup is
   replaced by spatially associated source segment/component IDs and a
   semantic fingerprint.
5. **Persistence/migration:** update `logic_case_bundle.py` to include the
   semantic version/status/fingerprint in the existing segmentation node
   lineage record. On load, validate an existing registry against current
   segment IDs/label IDs/geometry; otherwise recover in memory, mark migration
   pending/needs-review, and write only on explicit user save. Never mutate
   mask voxels or silently rewrite a legacy case.
6. **Focused acceptance:** run the cheapest pure/static checks first, then one
   serialized Slicer save/reload test for the semantic registry. Only after
   those pass and a separate verification approval exists should a target
   packet exercise 4A–5C or Step 6. No broad Step 6 rerun is part of this
   task.

### Required acceptance cases

| Case | Fixture and expected result |
|---|---|
| A | Native FDI11 tooth plus raw FDI111 pulp hint: canonical `Tooth_FDI11` and `Pulp_FDI11`, unique spatial match, `HIGH`/`VALID`. |
| B | Pulp geometry is inside/consistent with FDI11 but raw identity is generic or absent: canonical FDI11 comes from spatial evidence, not the name. |
| C | Raw pulp hint says FDI11 while geometry favors FDI21: preserve disagreement, never let the hint override geometry; resolve only with a clear validated margin or block/review. |
| D | No FDI11 pulp component: `MISSING`, clear diagnostic, pulp-dependent generation blocked; no fabricated segment or endpoint. |
| E | Adjacent FDI11/FDI21 candidates are close or metrics conflict: `AMBIGUOUS`, no automatic planning. |
| F | One pulp is fragmented: same-tooth components may be grouped with component evidence; cross-tooth or duplicate assignments are `AMBIGUOUS`/`INVALID`. |
| G | Save, close, reopen and re-import a `.dentocase`: canonical records, relations, states and fingerprint remain identical; legacy recovery is migration-pending until explicit save. |
| H | Backend raw names/terminology change while source facts remain adaptable: target/pulp queries use canonical records and continue; an unadaptable source fails review rather than guessing. |

### Boundaries and completion evidence

Non-goals are TotalSegmentator retraining/fine-tuning, synthetic missing pulp,
unnecessary mask edits, FDI11-only heuristics, and a broad Step 6 rewrite.
Completion requires the source-map comparison, focused pure/static checks, A–F
semantic fixtures, G save/reload evidence, H naming-independence evidence, and
one explicit pulp-dependent planning gate check. A code change is not accepted
until its verification command/result is recorded in the dated logbook.

**Next bounded action:** run one explicitly approved serialized Slicer import
and target-association check against the current source revision, then run the
focused save/reopen evidence. The current FDI11/FDI21 missing-pulp package
remains an input-data boundary; do not relabel or synthesize it.

## Immediate P0 — restore truthful Step 4A smooth masks

- **ID:** `W4-U-02`; **Priority:** 0; **State:** Root-cause correction and focused automated verification passed (2026-09-10); normal-window visual acceptance remains pending.
- **Operator observation:** Smooth masks do not work and must be restored now as Priority 0.
- **Finding:** The checked control returned without applying anything outside the special oblique-verification state and did not synchronize itself from the actual CBCT and segmentation display modes. It could therefore present a checked no-op in ordinary Step 4A.
- **Corrected contract:** With a complete selected trajectory, the same switch operates in ordinary Step 4A and oblique verification, using Slicer's existing scalar interpolation and closed-surface 2D representation without modifying source voxels or masks. Outside oblique verification it reflects the actual joint CBCT/mask state; oblique exit restores the captured prior modes.
- **Verification:** Focused Slicer target exercised the ordinary Step 4A handler, actual CBCT interpolation, smooth/native mask representations and endpoint persistence; it emitted `DENTOBOT_STEP4A_DISPLAY_PASS` and `DENTOBOT_STEP4A_P0_PASS` and exited 0. Evidence: `/tmp/dentobot-verification/step4a-p0-20260910/result.json`.
- **Next:** Confirm in a normal Slicer window that on/off visibly changes both CBCT and masks, the checked state is truthful, and oblique disable/exit restores the prior modes. The broader representative Step 4/backtracking acceptance remains part of this task after the P0 regression check.

## Immediate P0 — terminal coverage disconnects shell collar

- **ID:** `S5B-TERMINAL-COLLAR`; **Priority:** 0; **State:** Completed: approved host regression and exact FDI11 saved-loop/fresh-auto-loop preview→shell→unified builds passed, both exit 0 (2026-09-08).
- **Operator observation:** Automatic Step 5A boundary and manual backside adjustments both leave Step 5B unable to generate the shell/unified template. Screenshot reports two remaining components; target FDI11, four support teeth, terminal coverage 50%.
- **Source finding:** The bridge previously used the full boundary, then terminal half-planes clipped the completed union. This can remove both end connections and split a collar into two rails. This is a concrete failure mechanism, not yet proof of the exact screenshot's cause.
- **Implementation:** Clip and close the boundary at the existing terminal planes before collar construction. Retain the same anatomy exclusion, final coverage clipping and one-component gate. Error text no longer implies that redrawing alone necessarily resolves the failure.
- **Verification:** Old collar produced two regions; corrected collar produced one watertight region in original and rotated frames. Combined host run: 3 passed; compilation and diff check exit 0. Evidence: `/tmp/dentobot-verification/pulp-shell-20260908/`.
- **Exact-case evidence:** FDI11 `dentobot-case-step5b.dentocase`; saved and freshly regenerated automatic boundary both have 50 points, address all five teeth, and produce 3,363-point/6,028-triangle previews. Both shells have one surface region and zero invalid edges; both unified outputs have 74,988 triangles, one occupied volume region and zero invalid edges. Source package checksum unchanged; logs in the evidence directory.
- **Next:** Operator reload and normal-window build/inspection. Development defect is verified; anatomical/manufacturing and Track A acceptance remain separate.
- **Sequencing:** Operator requested completion of pulp-endpoint and P0 prompts one after another; endpoint source work precedes this correction. Approved host checks passed; runtime resources remain serialized.

## Immediate P0 baseline cleanup — retired pre-surgery workarounds

- **ID:** `S6-P0-BASELINE-CLEANUP`; **Priority:** 0; **State:** Source cleanup, 63 focused Python tests, native guard build, and 14-check synthetic ROS phase-guard test passed. Clean-case full-loop acceptance remains pending.
- **Reason:** The retired pre-surgery/x4 fixture exposed collision and guide-fit problems. It must not drive production exceptions or planner tuning. New baseline cases must use reviewed post-surgery/clean anatomy and a finalized Step 5C guide/tool model.
- **Implemented:** The production burr-proximity helper now returns only the selected target-tooth object. Adjacent teeth, jaw anatomy, and guide/template objects remain authoritative for collision and the research clearance margin. The façade no longer sends guide/template IDs as clearance exemptions, and the ROS bridge rejects non-empty guide-clearance exemptions.
- **Quarantined:** The historical Step 5C template-collision bypass is unavailable by default and requires the explicit process variable `DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE=1`. Session anatomy-review proxies are ignored by collision publication unless `DENTOBOT_ENABLE_HISTORICAL_ANATOMY_REVIEW=1`. Neither override is saved into a case or treated as baseline evidence.
- **Preserved:** J1–J5 canonical-TCP planning, J6-outside-planning policy, strict self/world/anatomy checks, the selected-target terminal-contact policy, endpoint/guard checks, and retained diagnostics remain unchanged.
- **Next:** Review/select one clean post-surgery case and complete its guarded approach, drilling, Return Home and repeat gate. Native guard evidence: `/tmp/dentobot-verification/cleanup-guard-20260907/`. Do not revive the retired x4 override or tune tolerances/base placement to make that fixture pass.

## Active operator interruption — Step 6A changed-target geometry

- **ID:** `S6A-CHANGED-TARGET-GEOMETRY`; **Priority:** Unprioritized (operator requests immediate cleanup); **State:** Source guard implemented; focused host verification and authorized Slicer clear/save round-trip passed; clean FDI44 end-to-end rerun remains pending.
- **Observed:** Operator completed the workflow on a different target tooth and reports FD14-like remnants attached/fused after applying the open-mouth transform. Screenshot is evidence of unexpected visible geometry; its source and actual fusion are unconfirmed.
- **Impact:** Step 6A preview and any derived planning geometry need an ownership audit before acceptance. Do not remove anatomical components based on appearance alone.
- **Evidence:** Source proxy reconstruction clears prior segments, while mandibular template display is copied separately from referenced Steps 0–5 models. The readable historical FD14 MRB contains explicit FD14 Step 5C template and Step 6 obstacle lineage. The relocated FDI44 archive was read-only audited through the authorized container path and showed FDI44 text/lineage with no FD14 strings; the authorized FD14 load → New Empty Case → save regression then reported zero FD14 hits in the saved MRML and lineage.
- **Implementation:** Target changes now clear Step 6A transient jaw/target-attached geometry before downstream deletion; authoritative segmentation changes do the same. The target-attached display builder filters models by persisted target lineage and hides/marks mismatched stale models. Restore validation now rejects mismatched trajectory/ROI/docking/template target chains, clears disposable opened-jaw proxies when deactivating a stale package, keeps mismatched source visibility suppressed, refuses to let a saved trajectory silently overwrite the active target during UI hydration, and keeps Reset reachable for stale transient refs while ROS is disconnected.
- **Verification:** Temporary-cache compile and `git diff --check` passed; the focused pure Step 6 suite passed `58 tests` including the modular/context budget; Graphify refreshed. The authorized pinned-container Slicer round-trip loaded FD14, cleared it with New Empty Case, saved a validated bundle, and reported `mrml_FDI14=0` and `lineage_FDI14=0`; no motion or hardware operation was performed.
- **Next action:** Repeat the complete FDI44 workflow from a clean session and visually verify Step 6A. The clear/save regression now supports session carry-over as the cause when New Empty Case is used successfully, while the separate FDI44 archive audit remains text/lineage-only and cannot establish binary mesh identity. Regenerate FDI44 Step 4A/4C/5C if the package reports a cross-target chain; only then repeat 6.0A. See `logbook/2026-09-07.md`.

## Track A acceptance contracts — migration baseline

| Order | ID | Priority | State | Next bounded action |
|---:|---|---:|---|---|
| 1 | `S6-LIVE-00` | 0 | Documentation checkpoint recorded; source baseline `ea504349f99f` preserved; scoped static/pure checks, rebuild, runtime marker, and graph refresh recorded | Keep the checkpoint boundary explicit while reconciling the remaining Stage-3 reachability issue |
| 2 | `S6-LIVE-01` | 0 | Source implemented; current alternate-route selection/replan and lock intent are added. The exact FDI31 r13 endpoint remains `FIRST_INVALID`; the bounded r6 diagnostic reconstruction and final no-TTY recheck do not establish a complete route. Native scene acknowledgement, static/transition attribution and display FK are now reconciled; operator scene review remains open | Keep the r13 endpoint/collision evidence and final bounded P2 packet under review; resolve guide/tool/base geometry ownership without shortening depth, moving the base or adding a collision exemption. Do not infer a Complete route or request P3/P4 from the diagnostic packet |
| 3 | `S6-LIVE-02` | 0 | Implemented: independent guard remains authoritative for J1–J5; legacy six-value spindle motion is rejected; final native packet records phase-aware invalid static validity separately from the Home-to-endpoint transition rejection; correlated 31-object acknowledgement and TCP/spindle/burr FK all pass; contact fields remain unknown where not exposed | Preserve the strict result, scene/policy identity and unknown-contact boundary. Any future geometry correction must be verified across every Stage 1/2/3 waypoint, narrow burr exception, external-spindle boundary and failed locked-route preservation |
| 4 | `S6-LIVE-03` | 0 | Implemented; FDI31 repeat-loop acceptance is `NOT_RUN` because Packet E stopped at its first-invalid Stage-3 result | For a Complete route only, trial Goal 1→Goal 2→guarded Return Home→replan/route choice; retain FDI31 failure and await approval before another tooth |
| 5 | `S6-LIVE-04` | 0 | Implemented; FDI31 playback/restore acceptance is `NOT_RUN` because Packet E did not complete | Confirm speed, ordered acknowledgements, visible stage paths, route lock state and current re-plan only for an accepted Complete target package |
| 6 | `S6-LIVE-05` | 0 | Historical x4 Goal-1 evidence is retained only as a negative diagnostic; clean-case acceptance is not yet run | Select a reviewed post-surgery/clean case with finalized guide/tool geometry, then complete the full guarded loop |

### Stage 6.5/6.6 planner interaction correction (2026-09-13)

The existing bounded diagnostic candidates are now an explicit operator choice
surface. The dialog keeps last-valid/first-invalid evidence and separate
Stage 1/2/3 display paths, then permits **Use Selected Route (replan)**,
**Lock + Replan Selected Route**, and **Unlock Saved Route**. Only a candidate
with `full_chain_candidate_status=Complete` can be applied or locked. A route
choice is identified by route type, IK seed, clearance sample and committed
axial frame; if the current planner cannot regenerate that identity as a
complete full chain, the request fails without activating another route.

The saved representation is the existing current motion-diagnostic JSON's
`full_task_outcome.plan_selection` extension. It stores route intent only and
never executable waypoint arrays, ROS/MoveIt validity, guard state or live path
buffers. Reopening a case therefore restores the selection/lock label and
requires a fresh current plan before Goal 1 or Goal 2 can use it. A changed
task, base, branch, collision audit or trajectory makes the diagnostic stale;
the saved selection cannot override that invalidation. Runtime, exact-package,
Step 5C geometry and normal-window acceptance remain open and are not implied
by this source correction.

The alternate-route apply path is transactional: it preserves the prior active
transient plan and saved diagnostic identity when the requested fresh re-plan
fails. The exact-case smoke now also accepts an expected FDI, can lock the
selected complete route, writes a detailed diagnostic file, saves a valid
`.dentocase`, and optionally reopens it to verify that route intent survives
without restoring ROS runtime state. The new serialized matrix launcher remains
a downstream six-target tool. The current acceptance campaign uses the same
exact-case runner serially for FDI31, FDI41, FDI11 and FDI21, each with its
own save/reopen evidence. A target-specific first-invalid result is retained
and the next tooth awaits explicit packet approval; missing required anatomy
is reported rather than synthesized by the planner.

The exact-case save path is fail-closed beyond ZIP/checksum validity. It records
and checks the current outer bundle schema, DentoCase/Case Foundation/registry
schemas, one selected current PreparedBranch, planning-pose and Step 5C
verification revisions, final-guide schema 2.0 and verification state, empty
save-time freshness issues, and the saved trajectory FDI identity. The final
guide schema is included in workflow lineage for manual package inspection.

The planner implementation additionally hard-stops stale or missing
PreparedBranch/Step 5C evidence, preserves the exact requested target depth,
audits the package again after post-hydration event drain with recovery-scene
rollback on failure, and requires the current-frame single-dock geometry gate.
These are source constraints; they do not close the open runtime, package
integrity, geometry, PreparedBranch, or normal-window acceptance records.

### 2026-09-14 exact FDI31 campaign result — earlier r2 record

The authoritative source package
`data/Slicer_Saved/SampleStudy1/dentobot-case-13sept.dentocase` remains
untouched (`SHA-256 14ed8f0f61e0c791d31b9582af7969ce712dd80d8cfd3a33319da63d0a996a15`).
Its reviewed base-revision discrepancy was handled by a one-field diagnostic
migration followed by an explicit production save. The current foundation
package reopened with preserved source volume/segmentation, Case Foundation
pose/landmarks, base matrix and lineage identities. The generated FDI31 package
is `data/dentobot-runs/stage6-target-generation-fdi31-current-20260914-r2/FDI31/case.dentocase`
(`SHA-256 3c8acf0ea9ba701c569b5173198208912368ca87b33283987acabfcb13bc932e`),
outer schema 2.0 and workflow/registry schema 3.0.

The reopened package contains exactly one current eligible PreparedBranch
(`guide-5c0da27697aceceb8f14`), current Step 5C evidence, four open bores, zero
residual channel occupancy, one connected printable solid and no closed-jaw
duplicate dock. Atomic failed activation preserved the prior active state.
The synthetic phase-guard runtime check also passed its J1–J5, bounds,
self/world/non-target collision, burr-guide warning, overshoot, retraction and
spindle-policy checks.

The exact simulation smoke was then run against that reopened package. Both
bounded candidates reached the requested `6.671904931162032 mm` target distance;
Stage 1 and Stage 2 passed. Candidate 0 was rejected at composed waypoint 237;
the selected candidate 1 was rejected at composed waypoint 274 (Stage 3
waypoint 27) by the authoritative guard because
`dentobot_target_tooth_2.25.127809691704402484963988182477922906518` contacted
`pneumatic_spindle-Copy`. The locked spindle value remained zero, requested
depth was not shortened, no template collision exclusion was active, and no
collision policy was changed. This is the current first-invalid exact-case
diagnosis, not planner success. Goal 2 completion, guarded Return Home,
repeatability, playback and route-intent save/reopen remain gated by a complete
Stage 3 route and therefore were not claimed.

**Current-source correction check (r13):** The generated current package is
`data/Slicer_Saved/SampleStudy1/FDI31/packet-a-fdi31-20260914-r7/FDI31-step5c.dentocase`
(`SHA-256 5440961c2f1464df10adec3dfb6ab59f8a0e412c6074cae7852d8150babe4fff`);
its verified STL is
`data/Slicer_Saved/SampleStudy1/FDI31/packet-a-fdi31-20260914-r7/DENTO_Final_Printable_Template.stl`
(`SHA-256 ccee3e597b7e579b0224a31f00308ee1d65e42bc89ac17bf9c68330d5bcec425`).
The approved r13 exact check used source HEAD
`3af2d864449679ead25398899d6325aefb50595a`, current diff fingerprint
`7e4e24d6278ba8bca98eb91bdf8902c2e6a018718b666e730e9fb97d6468be1c`, the
current rebuilt `collision_guard` binary
`9667b3aa6091db70cbb32c118af68af8f1d43179f099c6344f9184e2549c9ce9`, and
the pinned local image digest
`sha256:544c5b759ccef7ce6c41157bbd7bd8b602657de367f1f6b71352de054c81b019`.
Both direct and seeded candidates reached the exact FDI31 endpoint. The
selected direct candidate passed Cartesian Stage 1 and Stage 2 and was then
rejected by the current native guard at composed waypoint 255 / Stage 3
waypoint 27; the seeded candidate reached the corresponding Stage-3 boundary
at composed waypoint 295. Both failures were the same strict collision between
the selected FDI31 tooth and `pneumatic_spindle-Copy`. The requested depth,
saved base and J6-zero policy were unchanged. The run is a target-specific
`FIRST_INVALID`; Goal 2, Return Home and repeat/playback are `NOT_RUN`.

Evidence: `data/dentobot-runs/fdi31-foundation-current-20260914-r3/`,
`data/dentobot-runs/stage6-target-generation-fdi31-current-20260914-r2/FDI31/`,
`data/Slicer_Saved/SampleStudy1/FDI31/packet-a-fdi31-r7/diagnostics/FDI31-stage6-exact-r13.json`,
`/tmp/dentobot-verification/step65-fdi31-20260914-r13/runtime.log`, and the
dated 2026-09-14 logbook. No further blind whole-flow retry is authorized
until the guide/tool/base geometry owner explains or corrects this contact
without weakening the guard.

## P1 Case Platform / Simulation Studio — blocked by `S6-LIVE-05`

| Order | ID | Priority | State | Entry condition |
|---:|---|---:|---|---|
| 1 | `DCP-00` | 1 | Planned | Track A full loop accepted; freeze façade/backend handoff |
| 2 | `DCP-01` | 1 | Complete as planning record | This 2026-09-05 supersession; no implementation work beyond controlled docs |
| 3 | `DCP-02..08` | 1 | Remaining work deferred; promoted P0 subset is under correction | `DCP-00`; reuse accepted registry/environment/persistence rather than implementing them again |
| 4 | `DCP-09..10` | 1 | Planned | Case/platform foundations accepted |
| 5 | `DSS-01..05` | 1 | Planned | Data/platform foundation accepted; migrate Track-A behavior without changes |
| 6 | `DSS-06..12` | 1 | Planned | Guarded Preview parity accepted |
| 7 | `DHW-01..02` | 1 | Planned | Explicit later safety/architecture approval |

## Legacy task aliases

`S6-P0-01` full-chain planning is continued under `S6-LIVE-01..05`.
`S6-P0-02` restore continues under `S6-RESTORE-ROBOT-ROS` and the P0
PreparedBranch checks. Their old auto-reconnect and fixed-roll instructions
are historical. `S6-P0-DEPTH`, `S6-P0-CLEARANCE` and
`S6-P0-ANATOMY-REVIEW` retain historical evidence in the 2026-09-04–09
logbooks; no retired-case override is an active recovery action.

`AGENT-ASTRA-LOW` is superseded by `AGENT-SOL-RESTORE`; model policy is
maintained only in AGENTS.md, with dated rationale in DECISIONS.md.

## Priority task contracts — migration baseline

| ID | Priority | State | Entry condition | Next acceptance action |
|---|---:|---|---|---|
| `S6-P1-01` | 1 | Partially implemented; anatomical safeguards pending | Current P0 correction accepted | Add bilateral condylar/crown regions, exact-source snapping, MPR review and representative anatomy acceptance |
| `S6-P2-01` | 2 | Planned | `S6-P0-02` checkpoint matrix understood | Implement one post-load visual integrity panel for Steps 1–6 with Current, Needs attention, Stale, Blocked upstream, and Rejected states |
| `S6-P2-02` | 2 | Planned | `S6-P1-01` accepted | Add smooth display-only incisor-gap preview and one explicit commit action |
| `S6-P2-03` | 2 | Planned | Priority-0 correctness accepted | Add shared truthful busy/progress/result/cancel behavior to long-running actions without fake percentages |
| `W4B-P2-SUPPORT-AUTO` | 2 | Source suggestion and pure boundary checks complete (2026-09-15); normal-window UI/runtime acceptance pending | Current P0 PreparedBranch correction accepted; preserve Step 4B ownership | Auto-suggest the four nearest same-jaw support teeth—two on each side in dental-arch order—then require ordinary Step 4B review/lock. Verify the current arch selector in a normal window, with manual editing for edge, missing, or unsuitable teeth; the one-row selected-jaw layout remains part of `UI-P3-01` |
| `UI-P3-01` | 3 | Planned | Studio functional acceptance and Priority 1–2 correctness | Refine the New GUI while proving Legacy parity, incorporating the `W4B-P2-SUPPORT-AUTO` single-row jaw requirement, and adding no new MRML/ROS side effects |
| `S6-U-01` | 4 | Deferred reliability DENTO-NOTE. Functional connect/reload/reconnect/New Case/reconnect/save-reopen passes after the native ownership repair; only application shutdown still reports retained SlicerROS2/MoveIt VTK objects and class-loader warnings | Priority 0–3 work or an observed runtime regression no longer blocks it | Centralize native shutdown, release robot/parameter/pub-sub/MoveIt wrappers before library unload, correct test process-group cleanup, then require a zero-exit lifecycle run with no SlicerROS2 leaks |

## Unprioritized task contracts — migration baseline

| ID | State | Next bounded action |
|---|---|---|
| `S3-U-01` | Scan/run inspection workflow implemented; focused Slicer PASS | Operator reload and visual check on the real preDental/postDental scene; confirm Step 0–3 context bar, source-paired switching, compare, rename, and Step 4 handoff |
| `S6-U-04` | Fix implemented; normal-window acceptance pending. Goal 1 diagnostics **Close** did not dismiss the window before or after evidence review, forcing use of the title-bar X | Run Goal 1, open diagnostics, verify **Close** dismisses it both before and after **Mark Current Evidence Reviewed**, then reopen it and confirm no stale callback/window state |
| `S6-U-02` | Manual Simulation Base containment accepted; physical forehead/mount relationship unresolved | Obtain mount-face CAD/contact normal and define patient-contact-to-base transform, offsets, review, persistence, and invalidation |
| `W4-U-01` | Active design | Define reviewed crown region and MPR contract, then implement source-fingerprinted Entry snapping |
| `W5-U-01` | Source gate implemented: new-case trajectory-guide channel/hole defaults and UI floor are 2.0 mm; the immutable 13-Sept source still stores 1.5 mm in both fields. Focused legacy-hole Step-5B preflight now fails before cached work; representative/physical fit acceptance and optional export manifest remain open | Only in an explicitly revised new case, regenerate dependent Step 5B/5C geometry at the 2.0 mm guide-hole floor and review guide/burr and physical fit. Do not mutate the immutable source or substitute that case into frozen Campaign-1 r7/P3. Decide optional path-independent STL manifest separately |
| `IMG-U-01` | Representative acceptance pending | Compare authoritative masks and optional display previews on governed CBCT; define acquisition/artifact/segmentation uncertainty evidence |
| `W4C-U-01` | Design and representative acceptance pending | Validate support-aware docks, collisions, channels, rail roles, tolerances, and the non-parallel-trajectory versus one robot-axis constraint |
| `W5-U-02` | Representative and physical acceptance pending | Validate the read-only Step 4B support pack in Step 5A, editable margin, undercut/removability, shell contact, seating, and terminal support on governed anatomy/phantom |
| `W5-U-03` | Representative acceptance pending. **DENTO-NOTE 2026-09-07:** Step 5B unified-template creation needs detailed operator testing beyond smoke. During 2026-09-10 Step 4A verification, the combined runner passed Step 4A display, assisted pulp and FDI11 shell stages, then failed independently at unified fusion with 10 occupied volumes `[60677, 9, 4, 3, 1, 1, 1, 1, 1, 1]`. Read-only diagnosis traces the regression boundary to the current `W5-U-04` extended through-bore subtraction: the same case passed on 2026-09-08 before dock channels grew from 5.6 mm to 9.6 mm; FDI11's 2.2 mm bore leaves 9- and 4-voxel slivers above the conservative 0.1 mm³ cleanup ceiling. The supplied FDI31 run-2 Step6x5 package is a successful comparison case (saved raw regions `[45846, 1]`, cleaned to one), not the failed artifact | Localize the FDI11 slivers and correct the shared bore/attachment construction under `W5-U-04` without relaxing the one-solid gate or blindly raising the artifact threshold; then run current Step 5B fusion and Step 5C PASS/WARNING/FAIL on both FDI11 and FDI31, reopen, stale-lineage, channel-preservation, and one-STL flow; include dock/rail visibility and printability review |
| `W5-U-05` | **DENTO-NOTE 2026-09-07 (UX / workflow).** Primary unified-template dimensions are now in expanded section 2, not the pictured grey generated undercut outputs. The legacy 1.5-mm guide-hole error is now exposed by preflight/status. A clear owned Reset, interactive view while sizing/fusing, and full upstream dimension/lineage coupling still need representative UX work | Confirm section-2 editability in a governed live scene; design owned Reset (geometry + params + stale markers) and interactive 3D inspection, then validate Step 4A/4C/5A coupling without relaxing the shared guide-hole floor or silently changing saved inputs |
| `VIEW-U-01` | Cross-workflow normal-window acceptance pending. **DENTO-NOTE 2026-09-07:** mask 2D/3D opacity sliders no longer reachable in the viewer path the operator uses — see `VIEW-U-02` | Exercise grouped anatomy, stage presets, manual toggles, frame/restore, opacity, CBCT rendering labels, save/reopen, and Legacy/New parity without renderer or geometry side effects |
| `VIEW-U-02` | **DENTO-NOTE 2026-09-07.** Viewer no longer exposes **2D / 3D opacity sliders for masks**. Legacy still wires `segmentation2DOpacitySlider` / `segmentation3DOpacitySlider` in segmentation UI; operator path (likely New GUI / View Controls) lost them. Needs a **deeper UI/UX plan**, not a one-off restore | Map Legacy vs New GUI vs View Composition ownership of mask opacity; design always-available 2D fill/outline + 3D surface opacity controls (stage-safe, display-only, scene-persistent); plan parity with CBCT opacity and group visibility; implement after written UX plan acceptance, then close with normal-window trial |
| `S6-U-03` | Experimental design; not planning authority | Derive only confidence-labelled observed oral-air surfaces when suitable open-mouth/phantom data exists; keep unobserved space occupied/unknown |
| `CASE-U-01` | Backlog | Define and implement an offline no-ROS migrator for contaminated historical MRML/MRB scenes; never load them into a live ROS process |
| `PLAT-U-01` | Blocked by clean-image acceptance | Rebuild the pinned Ubuntu inference image and accept dependency, backend, Bridge, Slicer import, and persistence behavior without mutable-container repair |
| `PLAT-U-02` | Retired as a primary install; retained as an explicit native Windows Steps 0–5 fallback. Source hides Step 6 and blocks its automatic runtime restore; real-host regression pending | On a Windows workstation, run the renamed fallback check and verify Steps 0–5 plus absence of Robot Simulation; keep native Windows ROS out of scope |
| `PLAT-U-04` | Direct Docker Engine inside WSL2 is the approved default and `WINDOWS_SETUP.md` is canonical; Docker Desktop WSL integration is an exclusive alternative. One Desktop install passed recorded WSLg/CUDA startup; the direct-Engine machine still lacks exact acceptance evidence | Capture the second machine manifest and approved check-only, GUI, segmentation, and simulation evidence; reconcile an isolated release revision, create/advance `stable/lab`, and publish a new immutable lab tag and image identity |
| `PLAT-U-05` | Ubuntu NVIDIA dual-GPU setup and launcher support integrated; laptop `--check-only` and in-container CUDA passed, while IITM CPU regression remains pending | Run the documented check-only gate on the IITM CPU workstation after updating to the integration commit; retain CPU configuration unless CUDA is intentionally adopted |
| `PLAT-U-06` | Active investigation: the fork base already includes upstream's Slicer 5.12 test commit, current upstream is only three non-runtime-code commits ahead, while the accepted derivative image still uses Slicer 5.10.0 | Preserve the 5.10 rollback; create an isolated 5.12.0 upgrade branch, merge upstream, capture/audit the uncommitted fork APIs, build from the upstream 5.12 digest, then request approval for the staged compatibility and performance gates in `SLICERROS2_5_12_UPGRADE.md` |
| `PLAT-U-07` | Data folder created; initial pilot partially synced with 7 of 17 approved `.dentocase` bundles uploaded; 10 bundles over the connector's 100 MB limit remain pending | Finish the remaining individual bundles in `IITM Dentobot/Data` through the authenticated browser, then verify metadata and checksums. Keep `active-development-ubuntu` docs-only and do not sync the whole `Slicer_Saved` tree or raw/non-anonymized case bundles |
| `PLAT-U-03` | Deferred observation | After an approved reboot, record overnight CRD/GDM availability and resource behavior before closing workstation stability |
| `QA-U-01` | Unresolved | Diagnose why the aggregate Slicer test wrapper returns nonzero although isolated members reach PASS; do not treat isolated PASS as aggregate closure |
| `ROS-U-01` | Future design | Define geometry-preserving medical-image and transform semantics before broadening ROS scope beyond current bounded simulation interfaces |
| `POC-U-01` | Strategic parallel lane | Freeze one narrow task and acceptance thresholds, then run representative software, print/seating, registration, and error-budget work |

### `PLAT-U-07` — Multi-workstation Git and saved-case exchange

- **Priority:** Unprioritized.
- **Operator request:** Keep script development in the repository while
  exchanging the saved Slicer case work needed by multiple workstations.
- **Outcome:** Each workstation reproduces the tracked source and runtime
  layout from Git; an individual approved `*.dentocase` can be materialized
  under the local `data/Slicer_Saved/` layout when needed.
- **Important payload boundary:** A `.dentocase` is not metadata-only. Its
  outer archive contains an MRB, and the embedded MRB can contain CBCT-derived
  NRRD volumes, segmentations, and anatomy. Therefore the exchange path is
  limited to synthetic or explicitly approved de-identified bundles. The
  folder itself is not a blanket privacy approval.
- **Boundaries:** Do not sync the whole `Slicer_Saved` directory, standalone
  `.mrb`, `.stl`, `.nrrd`, screenshots, run records, credentials, or
  engineer-owned records. Do not add a watcher, Drive mount, or automatic
  whole-folder mirror.
- **Acceptance:** The operator names the separate Drive location and confirms
  the permitted bundle class; one bundle is uploaded or replaced in place only
  after checking its Drive name/parent; the downloaded bytes match the source
  checksum; and the logbook records the artifact class, source revision,
  checksum result, and evidence boundary without patient identifiers.
- **Current state:** Policy and queue entry were recorded on 2026-09-12. On
  2026-09-13 the operator approved anonymous `.dentocase` exchange, the
  `IITM Dentobot/Data` folder was created, and 7 of 17 local bundles were
  uploaded into the preserved relative layout: the root bundle, FDI11, and
  FDI31. Ten FDI14/FDI44 bundles remain pending because the connector rejects
  files larger than 100 MB; the browser fallback is waiting at Google sign-in.
  No standalone `.mrb`, `.stl`, `.nrrd`, screenshot, run record, or
  engineer-owned record was uploaded.

## Future track

The former F0/F1/F2 and separate .dentostudy sequence is superseded by
`DCP-*`/`DSS-*`; it is not a second implementation queue. Physical
registration/mount/controller work retains its existing prerequisites.

## Recently closed or superseded

These are pointers only; complete evidence remains in the archive, decisions,
reproducibility record, changelog, and dated logbook.

| Item | Disposition |
|---|---|
| Cross-tool agentic verification protocol | V1 source/pure-contract complete 2026-09-02: one canonical protocol and resource-aware matrix serve Codex, Cursor, and Claude; runtime execution remains approval-gated and serialized |
| GitHub default / overlay / Windows-lab conversion docs | `main` is authoritative; the pinned lab release and private Linux/amd64 GHCR image are published. First Windows WSLg/CUDA functional startup passed on 2026-09-07; repeatability on the next clean lab PC remains `PLAT-U-04` |
| Overlay Drive/MCP temps and nested `DentoBot/graphify-out/` | Deleted 2026-09-02; live graph stays at overlay `graphify-out/`. Launch scripts kept |
| Portable overlay `arduino-pressure/` package | Superseded; live bench is `tools/arduino-pressure/` in the DentoBot git tree |
| Host Arduino pressure fs / pipeline Config tab | Source complete 2026-09-02; `py_compile` and `--no-gui` verified; live flash/Hz click pending. Sensing-only |
| Step 6 action ownership/runtime-first ordering | Accepted and moved to the Development Plan ownership contract; no longer an active task |
| Collision object identity/audit | Runtime-accepted for the exact x4 scene; recheck only when its fingerprint changes |
| Viewer showing only internal tooth anatomy | Source-fixed and exact-package verified; remaining normal-window restore/toggle acceptance is owned by `S6-P0-02`, not a duplicate Priority-0 workstream |
| Step 6 substep split/restore deadlock | Fixed; superseded by `S6-P0-02` for checkpoint reconstruction acceptance |
| Schema-v1 bundle compatibility and orientation replay | Implemented and verified; retained as migration history |
| Goal 1 world/base Cartesian conversion defect | Diagnosed/fixed; remaining full-chain work belongs only to `S6-P0-01` |
| Earlier spindle-roll candidate planning | Superseded by spindle-locked arm-route planning; old evidence is historical only |
| Economical workflow modularization | Completed; the active ROS scene-clear abort remains only under `S6-U-01` |

## Verification workflow learning session — DENTO-NOTE 2026-09-11

- **ID:** `VERIFY-LEARN-01`; **Priority:** Unprioritized; **Triage:** Backlog.
- **Operator need:** Learn the testing and verification workflow once, hands-on,
  including `py_compile`, `pytest`, `colcon build`, and how DENTOBOT decides
  what evidence is sufficient.
- **Outcome:** After one guided session, the operator can identify the changed
  subsystem, choose the cheapest sufficient matrix check, explain what
  inspection/compile/unit/build/runtime/operator evidence proves, execute or
  supervise the approved commands, find the saved logs, distinguish PASS from
  partial/nonzero-shutdown outcomes, and apply the retry/stop rule.
- **Teaching sequence:** Start at checkout root; inspect the diff and
  `Testing/verification_matrix.json`; state the question, hypothesis, inputs,
  smallest check, expected result and stop condition; create one `/tmp`
  evidence directory; run/read one `py_compile` plus `git diff --check`; run one
  focused `pytest`; explain `colcon` workspace/package/install ownership and run
  one applicable focused package build only when the stable change or explicit
  learning plan justifies it; then explain why Slicer/ROS/MoveIt and normal
  window acceptance are separate higher evidence levels. Read the first causal
  failure and evidence artifact instead of blindly rerunning.
- **Dependencies and boundary:** Wait for the active
  `S6-REUSABLE-CASE-SETUP`/Step 6 reposition handoff so the lesson uses a stable
  revision and does not verify changing files. Use existing matrix commands and
  setup instructions; create no second harness or training framework. Every
  matrix command keeps its approval class. Serialize `colcon_install` and all
  runtime resources. No robot motion, drilling, patient-facing action, guard
  relaxation, blanket rebuild/suite, commit, push or Drive write is implied.
- **Acceptance:** One bounded run record contains the selected check IDs, exact
  commands, why each was selected or skipped, exit codes/PASS markers, evidence
  paths, first failure if any, cleanup status and operator questions. Finish
  with a concise reusable checklist linked to the canonical protocol/matrix.
  This is educational completion, not proof that every DENTOBOT subsystem was
  tested.
- **2026-09-17 activation delta:** The operator explicitly selected this task
  as the active route while Campaign 1 is paused at P5. The former dependency
  on a stable reusable-case/Step-6 handoff is satisfied by the preserved P5
  result. The session must first teach and record the distinction between
  headless diagnostic evidence and GUI/operator evidence, then perform the two
  tracks above. Numeric priority remains Unprioritized; the current execution
  order comes from the explicit operator direction. Completion must end with a
  clear recommendation to resume after P5, remain paused on a named GUI defect,
  or open a decision-level blocker—never silently continue the P-series.

## DENTO-NOTE triage and maintenance rules

Use [AGENTS.md](../AGENTS.md#backlog-first-gate--mandatory) and
[backlog.md](backlog.md). Capture every open note once in that queue with its
stable ID, observed workflow/behavior, priority or Unprioritized, evidence,
impact, dependencies and next acceptance action; link a detailed contract here
when needed. Do not create another active queue in this file.

On completion, record exact acceptance evidence in the dated logbook, update
this record and DEVELOPMENT_PLAN.md where their contract/milestone changes,
then remove the accomplished backlog row in the same turn. Source completion
alone does not close required operator/physical acceptance. Superseded or
cancelled work requires its explicit disposition and alias mapping preserved
here/logbook before removal. No history is silently deleted.

## 2026-09-11 backlog migration and tracker crosswalk

The operator requested one pending-only planning entrypoint to prevent lost
backlogs, repeated plans and redundant implementation. `docs/backlog.md` now
owns that queue; `AGENT-PLAN-FIRST` is amended to check it first and then these
contracts/history, including when no pending match exists. This documentation
change is completed; it is not itself a pending backlog item.

Read-only source: Project Tracker `1W118Z6oDqfA6IOBXg3llCo6-IowoSAif1HxuTFK7NHU`,
Master Work Register rows 4–41 (38 deliverables; 30 unfinished, 8 complete),
Dashboard and Priority Focus through 3 September, and Decisions/Risks. Current
local September 10–11 case/priority decisions supersede older source status.
No tracker content was edited. The tracker is not an automatically readable
future authority; rule 16 still requires explicit current-message permission.

All 30 unfinished source IDs are either pending owners/aliases or mapped to
existing work in backlog.md. `A-019`, `A-020`, `A-021`, `A-025`, `A-030`,
`A-031` remain source-complete history. `A-033`/`A-034` implementation remains
closed; only their explicit platform/renderer follow-ups are retained.
`A-006`/`A-024` literature priorities conflict (P0/P1); `A-036` register and
dashboard conflict (P1/P2). These source values are preserved for later
selection, not silently promoted into the current development order.

`S6-LIVE-00` and `DCP-01` are completed documentation checkpoints, excluded
from pending work. `S5B-TERMINAL-COLLAR` defect remains verified; its remaining
normal-window/physical acceptance is covered by `W5-U-02`/`W5-U-03`.
The source-complete pressure Config-tab live flash/Hz follow-up is retained
under `A-037`; no new tool implementation or hardware authorization is implied.
The stale F0/F1/F2 `.dentostudy` rows in DEVELOPMENT_PLAN.md are removed in
favor of their already accepted `DCP-*`/`DSS-*` successor contract.
