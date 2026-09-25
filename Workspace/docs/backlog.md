# DENTOBOT pending work and backlog

Last reconciled: 2026-09-25. **Check this file before every plan or new task.**
This is the sole pending-work queue: active, blocked, planned, deferred and
unaccepted work, including every open DENTO-NOTE. Detailed contracts live in
[TASKS.md](TASKS.md) and [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md); process and
completion rules live in [AGENTS.md](../AGENTS.md#backlog-first-gate--mandatory).
No completed-task history or execution logs belong here.

**Reading rule:** scan every section before a major plan; search IDs, synonyms,
workflow steps and overlap notes before any scoped plan. Reuse existing owners
and accepted implementation. A row marked acceptance pending requires review,
not automatic reimplementation. Table order outside the active sequence is not
new execution authority. Numeric priorities retain their recorded values;
Unprioritized stays unassigned. Dependencies and runtime/hardware gates apply.

Sources: local controlled records through 11 September and the read-only
[Project Tracker](https://docs.google.com/spreadsheets/d/1W118Z6oDqfA6IOBXg3llCo6-IowoSAif1HxuTFK7NHU/edit)
reconciled through 3 September. Tracker-only work is captured below with source
IDs and provisional status; its old dates, allocations and case diagnostics do
not override later local decisions. Tracker priorities are source metadata,
not promotions into the current development sequence.

## P0 planner recovery — source renovation active; runtime gated

**Current routing, 2026-09-25:** Follow the [Step 6 workflow renovation plan](diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md)
first: optional incisor-centered 200 mm TCP sampling ROI, manual diagnostic
ghost with explicit Base/Home acceptance, responsiveness measurement, separate
PreEntry/P1/P2/P3 diagnostics, two-area UI and Block Return. The [later-work
index](diagnostics/STEP6_LATER_WORK_AND_ADJACENT_IDEAS_2026-09-25.md)
routes case-specific FDI11/21/31 solving, comparison and adjacent ideas without
creating a second queue. The [FDI31 P0 contract](diagnostics/FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md)
retains its open milestone gates; archived historical records are mapped in
the [archive index](diagnostics/archive/step6/README.md). Earlier paragraphs
below are evidence history, not a competing execution order.

`S6-LIVE-01` — **Priority 0; first FDI11 IK-only report received, operator verdict pending; agent runtime paused.** The authoritative contract is
[FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md](diagnostics/FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md).
**2026-09-25 order change:** Tarun places the Step 6 workflow renovation ahead of case-specific planner solving. The [working plan](diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md) records the optional ROS-connected manual diagnostic ghost and the confirmed incisor-centered, editable 200 mm cubic bound on TCP sample generation. Manual-control authority, diagnostic evidence and responsiveness retain their implementation gates there. The [base-pose feasibility explorer proposal](diagnostics/archive/step6/DENTOBOT_Base_Pose_Feasibility_Explorer_Diagnostic_Plan_2026-09-25.md) is a metric source, not a runtime or geometry authorization. FDI11's visible report remains preserved; its architecture verdict and changed-setup case save are open. No planner comparison or automated base sweep follows from this reprioritization.
**Confirmed scope:** The cube is a hard *TCP sampling-domain* boundary for computation, not a route or collision constraint. Manual movement is a diagnostic ghost; explicit Accept Base/Task Home uses current ownership and invalidation, while any later preview needs a fresh full guard. Upstream SlicerROS2 and local latency research is recorded in the supplemental plan; a measured interactive viewport bottleneck is still needed before selecting a fix.
**2026-09-25 implementation direction:** [The supplemental renovation plan](diagnostics/STEP6_RENOVATION_IMPLEMENTATION_PLAN_2026-09-25.md) fixes the order: standalone FDI11 PreEntry IK source/diagnostic first, then operator-visible IK-only verdict; optional workspace and separate P1/P2/P3; corrected fixed-upper FDI21 exact-state evidence before Stage-3 review; exact FDI31 full-chain reference afterward. The first source gate passed focused/combined pure checks and a native package build. Tarun has now supplied one loaded-Slicer IK-only report: collision-checked endpoints pass for a setup whose base, Home, task and scene fingerprints differ from the unchanged 24 September saved package; its trajectory and robot profile match. His interpretation and a separately saved identity for this changed setup are pending, so the original all-zero-Home failure is not resolved. The saved FDI11 case's pose restore correction was source-checked after three failed autonomous restore attempts; the current manual report does not by itself close restore acceptance. Sol Medium coordinates up to two Luna Max implementation workers with disjoint files. Source implementation is authorized by Tarun's current request; the prior source halt below is historical. Agent-run Slicer/ROS/planner trials, geometry changes and hardware remain separately gated.
**2026-09-24 operator direction for source design:** Merge workspace exploration, task confirmation and stage diagnostics into one Planning & Diagnostics area; make simulation preview/return/repeat a second Preview & Control area. `S6-WORKSPACE-PURPOSE` is the prerequisite for removing any 6.3 mandatory gate, because its sampled FDI11 limits exclude a validated Home. This supersedes the separate 6.3–6.6 presentation target, not the M0–M4 acceptance stops or current runtime pause. Detailed contract is in TASKS/DEVELOPMENT_PLAN/DECISIONS; no hardware command path is authorized. The failed-IK joint/limit source slice and plan-only PreEntry diagnostic are now implemented; the first exact-case visible result remains the gate before UI/confirmation migration.
Tarun's 2026-09-24 manual FDI11 Step 6.4 trial on `SEPT24/fdi11_step6.dentocase` is retained under this ID: PreEntry position-axis IK fails before planner search; all three comparison rows have zero waypoints. The saved package contains the later screenshot error and exact base/Home/task identity, now extracted in the 24 September logbook and `diagnostics/evidence/fdi11-step6-2026-09-24/saved-pose-audit.json`. Matching-URDF FK puts all-zero Home 36.887 mm from PreEntry with 162.258° axis mismatch; ten additional Home-connected seeds also failed. The old facade discarded best failed joint vectors; the new diagnostic source retains them, but joint-bound versus numerical attribution remains open until a current result is reviewed. Empty collision tuples do not establish collision freedom. Agent runtime remains paused; no planner-performance or M1/M2 verdict follows from these rows. Homing/recovery scope remains `S6-LIVE-03`.
The 2026-09-24 halt is superseded for bounded source implementation by the
25 September direction, not for runtime or acceptance. Preserve cases, run
artifacts and unaccepted gates. Do not run a planner comparison, optimize the
guard, vary base/Home or claim GUI/runtime acceptance before the stated gates.
The FDI21 recapture **source repair** is scheduled after the FDI11 diagnostic;
its runtime reconstruction remains separately gated. Priority and acceptance
are unchanged.
2026-09-23 operator additions under this same ID are source-complete, with
normal-window acceptance open: optional RRT* third choice, all-control hover
guidance and reasons for locked modes, and reopenable Step 6.5 error-dialog
text in Motion Diagnostics. RRTConnect remains default; each configured
choice still needs a one-at-a-time visible result and Tarun's verdict.
The latest visible Stage-3 tooth↔spindle guard rejection is evidence, not
authorization to relax collision policy or a planner-performance verdict.
Input: `data/Slicer_Saved/SampleStudy1/FDI31/dentobot-case-sep22-step6.dentocase`
(SHA-256 `eb48a805...e7adb`). `M1-DIAG / HOUSING-OFF PASS`: with only the
spindle-housing collision block absent, the visible preflight completed P1
Home→PreEntry (150 waypoints); its internally computed P2/P3 results are retained
diagnostic evidence only. Canonical M1 remains open. Next action: stop the
housing-off session, restore canonical housing-on mode, and obtain operator
selection/review of one temporary collision-valid Home for Experiment B. A
2026-09-22 source correction now replaces stale cross-target evidence on a
zero-endpoint PreEntry IK failure and exposes the task/trajectory/base identity;
normal-window confirmation remains open and no base-pose predictor is accepted.
reported closer-Home trial followed by a mouth-gap change to approximately
45.96 mm first failed before P1 because canonical TCP IK produced no
tolerance-valid PreEntry endpoint while reporting no collisions. At the same
45.96-mm geometry, another Home then produced 31 free-space P1 samples and all
12 fixed-axis P2 checkpoints; Stage 3 became the earliest blocker. This proves
Home/IK-seed or branch dependence at that altered geometry, not by itself an
incorrect base placement. The operator then changed robot-base position and
orientation and obtained a complete housing-on chain at the same displayed
45.96-mm gap: P1 66, P2 10 and P3 22 waypoints. This establishes a feasible
alternate physical arrangement and makes placement/configuration-space
clearance the leading cause, but it is not canonical M1/M2 because base,
anatomy and Home differ from the Sep-22 baseline. The later FDI21 planner
screenshot retains a result explicitly marked `Stale` after target change;
fresh FDI21 Step 6.5 success is unverified. Save the adjusted scene separately
before any exact-case automated check; an active operator runtime must close
normally before another serialized run.
Campaign-1 r4/P3/P4/P5 remains historical evidence only. Runtime and
implementation remain separately approval-gated.

**Operator TODO — prior diagnostic-attribution task:** In one normal-window
FDI21 zero-IK trial, confirm that Motion Diagnostics shows the current FDI21
task/trajectory/base identity and `preentry_ik_unreachable`, not the retained
FDI31 66/10/22 result. Separately save the manually adjusted-base scene under a
new case name before any controlled base-placement comparison. These are
operator-owned visible evidence steps; they do not authorize another automated
runtime or overwrite either supplied case.

**Planner-policy state (`S6-LIVE-01`):** The 2026-09-22 DENTO-NOTE requested
effective planner identity, RRT-family comparison, approximate IK disabled and
Cartesian-path planning disabled. Later explicit operator direction adds RRT*
as an optional third comparison; RRTConnect remains default. The shared 6.5/6.6
dialog now exposes those three configured choices, attempts and time. Approximate
IK remains disabled. Cartesian Stage 2/3 remains enabled and locked until the
canonical exact-pose sequential-IK replacement is checked, *after* a visible
planner comparison and Tarun's verdict. The planner-ID bridge/focused build
passed, but its configured-ID echo before `plan()` does not prove the executed
algorithm. Each visible trial, screenshots and manual verdict remain open;
capture planning-server evidence before claiming an executed algorithm. Keep
collision, phase, target-contact, J1-J5/J6 and no-hardware boundaries intact.
The Step 6.5/6.6 navigation, primary preview controls and facade/bridge
operator messages have source-only Approach/Drill wording slices without
changing planner behavior. A normal-window check is still needed before
terminology acceptance.

## Preserved prior pause and return route — 2026-09-17

This route is superseded for current sequencing by the 2026-09-21 P0 reset
above; its evidence boundaries and task ownership remain valid. The operator
had paused Campaign 1 gate verification at the completed P5
diagnostic and redirected the active work to the existing `VERIFY-LEARN-01`
guided GUI/operator-verification lane. This is an explicit sequencing change,
not a retraction of Gate A or P3/P4/P5 evidence and not authority for P6, P7,
another tooth, a new IK search, motion, hardware, spindle or patient action.

The reason is an evidence-level mismatch. Locked r4 was built with the saved
15 September Step-4A Entry/Target coordinates; the construction runner inserted
that line and tagged it `SavedStep4A15Sept`. P5 then opened the prepared r4
package, programmatically activated its saved `PreparedBranch`, loaded the
robot and used a diagnostic-only runtime path that deliberately bypassed the
normal GUI Connect → Task Home → Workspace → Task Confirmation sequence.
Therefore P5 proves bounded simulation feasibility only. It does **not** prove
that an operator can use Assisted Trajectory Generation or complete the
ordinary 4A→4B→4C→5A→5B→5C→6 normal-window workflow.

The active acceptance route is now:

1. Inspect the exact locked r4 package without editing it: confirm the saved
   FDI31 trajectory, opened-mouth Case Foundation, support/template/guide
   registration, verified `PreparedBranch`, and Step-6 activation/display.
2. Treat Assisted Trajectory Generation on locked r4 as intentionally blocked:
   r4 already contains a trajectory and the UI never overwrites an existing
   plan. Test assisted generation only in a fresh or disposable-copy case with
   Reviewed segmentation, selected target, current Case Foundation, zero
   existing target trajectories, and a unique non-empty `HIGH`-confidence
   tooth↔pulp association.
3. Walk the ordinary GUI path in order and record the exact visible status,
   first failure, screenshots and save/reopen behavior. A guide or trajectory
   visibly detached from the opened-mouth anatomy is a stop condition, not a
   reason to advance to Step 6.
4. Reconcile the operator-visible result with the headless evidence and fix
   only an evidence-backed source defect under its existing owner. Do not tune
   geometry, policy or planning merely to make the GUI proceed.
5. Return to the gate/P-series only after the controlled records contain an
   operator-readable GUI verdict and the coordinator explicitly confirms which
   unmet gate is next. The default return point is **after P5**, not a rerun of
   P3/P4/P5 and not automatic entry to P6.

`VERIFY-LEARN-01` owns the guided session and evidence interpretation;
`S6-REUSABLE-CASE-SETUP` retains the r4/P3/P4/P5 artifacts and campaign
boundary. `S4A-PULP-ENDPOINT`, `W5-U-04`/`W5-U-03`, `VIEW-U-01` and
`S6-REUSABLE-CASE-SETUP` own any first failure in their respective 4A,
5B/5C, display, or Step-6 portions. Do not create a parallel GUI-verification
task.

**2026-09-17 quota-constrained recovery stop:** The operator has ended further
analysis and wants the next session to proceed with fixes from the preserved
findings. This does not close `VERIFY-LEARN-01` or constitute operator
acceptance. The active P0 correction order under the existing owners is:

1. `S6-REUSABLE-CASE-SETUP` / restore ownership: synchronize post-restore
   Step-4A references and allow only the opened moving-lower representation to
   be 3D-visible while preserving the closed source segmentation. The saved
   15Sept MRML contains both representations visible, which explains the
   detached FDI31 ghost as a display-state defect; no evidence promotes that
   ghost into the native collision scene.
2. `S4A-PULP-ENDPOINT`: capture the expected/active markup ID, interaction
   state and placement-valid state immediately around the existing
   `StartPlaceMode(0)` call, then correct only the demonstrated shared-state
   failure. The existing error proves activation failed but does not identify
   which checked postcondition failed; do not add a blind retry or forced
   success.
3. Preserve the FDI21 target-ownership warning, but make target switching exit
   stale placement and replace/rebind the prior target-owned assisted-entry
   node so the operator can recover.
4. Under `S6-LIVE-02`, make P5 diagnostic request IDs globally unique. Existing
   sequence/vector checks distinguish the saved responses, so retain P5 as
   diagnostic evidence; do not call the duplicate ID acceptable traceability.

P5 remains `SAMPLED_PASS` only at guard-policy feasibility scope. Its current
images do not contain a parity-proven robot state with full anatomy, and the
configured template↔spindle allowance means it is not literal housing-clear
evidence. Operator verification therefore remains blocked. A fresh independent
reviewer was attempted but stopped before review at the account usage limit;
completed read-only worker summaries are retained as evidence inputs, not
acceptance. Do not repeat those investigations merely because their reviewer
was unavailable.

## Pending planned work — active correction and acceptance

**Latest FDI31 scope — 2026-09-15:** The operator has activated the revised
Campaign 1 execution contract. It replaces the former Astra/design-only/P4
limit with one main orchestrator and one bounded Luna Max implementation worker.
The new corrected FDI31 case must preserve r7/r13 as historical evidence, use
the 15 September opening/landmark/base foundation, the exact saved identity for
the operator-specified approximately 5.2394 mm trajectory, FDI42/41/32/33
supports, 1.0 mm dock bores and >=2.0 mm trajectory-guide/channel dimensions.
The
[Campaign 1 contract](diagnostics/archive/step6/FDI31_PLANNER_RECOVERY_CAMPAIGN_1.md) now
governs `S6-REUSABLE-CASE-SETUP` and `S6-LIVE-01..04`: scene/input review plus
diagnostic repair, bounded endpoint/insertion search, approach reconciliation
and guarded fresh-process simulation evidence. P0 must extract the trajectory
identity before case construction; it may not infer it from rounded text. This
supersedes the geometry-correction-only prerequisite and old
stop-after-every-minor-failure interpretation for this scope. The operator
subsequently approved P1/P2 only for run `c1-p1p2-20260914-r1`; P1's
saved-input/machine checks PASS, but P1 overall scene correctness and operator
review are INCOMPLETE. The final bounded native diagnostic/evidence result is
`PASS_FOR_COMPLETED_DIAGNOSTIC_EVIDENCE`, with campaign gate
`USER_REVIEW_REQUIRED`: its packet contains separate phase-aware static,
generic-static and Home-to-endpoint transition records, trusted 31/31 scene
acknowledgement, and TCP/spindle/burr FK evidence. The earlier
`expected 31, observed 0` result and the container/launcher failures remain
historical. P3/P4, more full-planner retries, invariant changes and another
tooth remain unauthorized. The exact runtime logs, hashes and review limits
are in the canonical recovery report. Operator review and final
architectural/clinical acceptance remain separate.

**2026-09-15 Gate-A result — blocked at construction:** The one authorized,
serialized offline construction/reopen run `c1-gatea-fdi31-20260915-r1` passed
container/process/hash preflight but stopped before template construction,
export or reopen. The new runner loaded the 15-September source and rejected
the imported FDI31 line at `getTrajectorySummary(...)["isValid"]`; its emitted
first failure is `FDI31 trajectory is invalid`. This is a shared corrected-case
construction failure, not a planner, insertion, guard, hardware or motion
result. Preserve the generated FAIL diagnostic/screenshots and do not retry
Gate A, enter Gates B–D, or advance to another tooth. Next bounded action:
identify the exact MRML trajectory-state mismatch in the runner/source path,
add the smallest regression check, and seek a fresh runtime authorization only
after the source correction is reviewed.

**2026-09-15 source correction / r2 authorization state:** The runner now
validates the imported saved line before locking it, matching the established
assisted-line lifecycle, and reports a full existing trajectory summary if it
remains invalid. Focused pure checks passed 29/29. r2 runtime preflight passed,
but the runtime execution gate correctly declined to launch a second
state-changing Slicer/case run because the current authorization did not name
that new attempt. Gate A remains FAIL until the operator explicitly authorizes
one new isolated offline construction/reopen attempt; Gates B–D remain NOT RUN.

**2026-09-15 r2 point-insertion evidence / r3 limit:** Authorized r2 confirmed
that the live saved line has zero defined points, not a degenerate coordinate
pair; r2 is FAIL before template generation. The source now explicitly unlocks
the line before point insertion and fails immediately if two points are not
accepted; focused pure checks pass 29/29. This is the third and final permitted
causal hypothesis under the verification ceiling. It needs explicit r3 offline
Gate-A authorization; a third runtime failure ends autonomous retry and keeps
Gates B–D/other teeth NOT RUN.

**2026-09-15 revised Gate-A completion:** The operator approved the r4
exception plan after r1-r3. `c1-gatea-fdi31-20260915-r4` passed its serialized
container/process/hash/fresh-output preflight, then emitted
`STAGE6_TARGET_PASS FDI31` and `STAGE6_TARGET_GENERATION_COMPLETE {"passed":
1, ...}`. It produced a new 84-MB `.dentocase`, verified STL, diagnostic,
campaign report and post-reopen UI/viewport captures. The diagnostic is PASS:
the FDI31 selected branch is current/verified, its two planning-frame points
are within bounds, saved trajectory length remains `5.239400689721231 mm`, and
the support IDs are FDI42/41/32/33. The outer Slicer process returned exit 1
during shutdown with known leak warnings after those PASS markers; record this
as a process-health warning, not a functional Gate-A failure. Gate A is closed
for corrected-case construction/save/reopen. Gates B-D, other teeth,
physical/clinical fit review, motion and hardware remain NOT RUN and require
their own approved gate entry.

**2026-09-15 r4-only active baseline:** The operator explicitly directed that
the current work must use `c1-gatea-fdi31-20260915-r4/FDI31-step5c.dentocase`
only. Historical r7/r13 and other prior outputs remain retained evidence but
are not execution inputs, comparators or fallbacks. The next bounded work is a
r4-only endpoint diagnostic: direct native position-axis IK at r4's saved
Target with the existing generic and phase-aware static checks, using Task Home
plus at most 13 saved Home-connected workspace seeds. It excludes approach or
drilling planning, preview, insertion, route locking, controller/hardware
connection, motion, powered spindle and patient work. A zero-candidate outcome
is a bounded endpoint result, not an instruction to substitute a historical
case or alter r4 geometry/policy.

**2026-09-15 r4 endpoint runtime disposition:** The r4-only endpoint branch
is source-verified, but the runtime diagnostic is **NOT EXECUTED**. Preflight
confirmed the container and the exact r4 checksum. The first launch stopped
at an unsupported `sh` option; the next two stopped during SlicerROS2 module
initialization, before the r4 case or runner opened, most specifically because
`libqSlicerROS2Module.so` could not find `librclcpp.so`. The attempted
fully-configured retry was rejected at the three-failure ceiling. No planner,
preview, insertion, motion, hardware, or historical case path ran. Any further
runtime attempt requires an explicit operator-approved exception after review
of this environment-only blocker.

**2026-09-15 P3 authorization / r4-only execution delta:** The operator now
authorizes Gate-B P3 according to the Campaign 1 plan, retaining r4 as the sole
case and excluding every historical output from inputs, anchors, comparisons and
fallbacks. The prior 14-seed r4 probe is preparation only, not P3 acceptance.
P3 must manifest one deterministic batch of no more than 128 J1–J5 seeds from
current r4 Task Home/workspace evidence and active runtime limits; every
converged position-axis IK result must receive existing generic and phase-aware
static validation before post-validation deduplication. Its one offline runtime
batch is authorized after the preceding environment retry ceiling: sourcing
`/opt/ros/jazzy/setup.bash` plus `/workspace/ros2_ws/install/setup.bash` now
resolves `librclcpp.so`. P4 remains conditional on a P3-admissible Target; no
planning, preview, insertion, motion, controller/hardware, spindle or patient
action is authorized in P3.

**2026-09-15 P3 runtime approval boundary:** The r4-only P3 implementation,
matrix entry and focused source checks are ready, and checksum/process/output
preflight passed. The subsequent runtime request was rejected **before any
process started** because it is the fourth Slicer/ROS initialization attempt
after three recorded initialization failures. The operator's general direction
to proceed under the plan did not name that concrete retry risk for the runtime
safety gate. This is not a fourth execution failure and does not alter r4 or
create output. The sole pending action is a specific operator authorization for
one fourth initialization attempt: source Jazzy and the workspace setup, start
one temporary simulation stack, run the r4-only <=128-seed P3 native static
batch, write fresh evidence, and tear it down; still no planner, insertion,
motion, controller/hardware, spindle, patient or historical input.

**2026-09-15 P3 interrupted no-planning correction:** The authorized fourth
initialization attempt started, loaded r4 and its temporary simulation stack,
but was stopped before a P3 diagnostic after the log showed MoveIt planning
requests. No preview, execution, controller/hardware, spindle, patient or
historical input ran; no `endpoint_candidates.json` was written. The owned
Slicer, launcher and orphaned guard process were terminated and verified gone.
Root cause: the generic exact-case runner regenerated its workspace before its
endpoint-only return, and that helper makes planning requests. The smallest
correction moves the P3 return before `generateWorkspaceCloud()` and has a
focused ordering regression check; source checks pass 29/29. P3 is
**INTERRUPTED / no endpoint result**, not PASS or bounded negative. Preserve
the attempted logs in `c1-p3-fdi31-20260915-r4`; a replacement must use a
fresh output directory and needs new explicit authorization after this distinct
no-planning-boundary interruption.

**2026-09-15 P3 r2 harness interruption / r3 approval requirement:** The
authorized replacement's `r2` wrapper launched only its temporary simulation
stack and then exited before Slicer, runtime logging or candidate evaluation;
the stack log is retained and its known launcher and guard PIDs were cleaned up.
This is an **INTERRUPTED harness run**, not P3 evidence. The runner's direct
native position-axis call was also corrected to bypass its generic collision
prefilter so every kinematically converged candidate can be evaluated by the
authoritative existing phase predicate. Static checks remain 29/29. A proposed
fresh `r3` dispatch was rejected before launch because the original one-run
replacement authorization was consumed and broad pattern-based cleanup was too
risky. Any next authorization must explicitly cover one additional r3 attempt
after the r2 harness interruption and permit cleanup only of PIDs first proven
to be created by that exact run.

**2026-09-15 P3 r3 interruption / runtime ceiling:** The explicitly authorized
r3 attempt again started only the temporary simulation stack and never reached
Slicer, `runtime.log`, the endpoint runner or candidate evaluation. Its own
records identified launcher PID 3775 and guard PID 3800; both were first
recorded in the r3 evidence and then terminated/verified absent. Across this
P3 runtime lane, r1 stopped on the no-planning boundary and r2/r3 stopped at
the pre-Slicer harness/readiness stage. These are three recorded P3 runtime/
setup interruptions, so the verification retry ceiling closes the runtime lane.
There is no P3 PASS, FAIL or bounded-negative endpoint result. Do not launch a
r4 P3 retry from this state. The next action requires an operator-approved
revised execution plan that first resolves the launcher/readiness harness with
the smallest non-Slicer discriminating evidence; it may not substitute
historical data, relax the no-planning boundary or alter r4 geometry/policy.

**2026-09-15 launcher/readiness blocker resolved:** Read-only attribution
identified twelve orphaned ROS children from the first three P3 temporary
stacks; their PIDs and command lines matched retained stack logs, and they were
terminated. The resulting clean baseline has zero `/joint_states` publishers.
`Testing/run_c1_p3_r4_batch.bash` now sources ROS before strict-unset mode,
starts the simulation stack with `setsid`, records its process group and tears
down that entire group. Its fresh no-Slicer readiness check passed on attempt
one with `ready:true` and one publisher; post-exit verification found zero
publishers and no simulation child process. Static checks pass 29/29. This
resolves only the launcher blocker; P3 remains NOT TESTED/INCONCLUSIVE at its
prior runtime ceiling. The next pending action is an explicit revised P3
runtime authorization for this verified driver and a fresh r4 output directory.

**2026-09-16 P3 r4 runtime interruption / task-reconfirmation repair:** One
explicitly authorized fresh run, `c1-p3-fdi31-20260916-r4`, passed the r4
checksum and stack readiness, opened r4 in Slicer, and stopped before any
native candidate, `endpoint_candidates.json`, P3 marker, planner request or
motion action. The terminal error was the generic post-restore
`confirmTask()` call requiring workspace-assisted limits; P3 may not generate
that workspace because it issues planning requests. The owned stack group
cleaned up with no matching residual process. The smallest repair makes
endpoint-only mode retain the restored r4 task snapshot and fail closed when
it is absent, instead of reconfirming through workspace limits; the normal
path is unchanged and focused checks pass 29/29. P3 remains
**NOT TESTED/INCONCLUSIVE**. A future runtime requires a new explicit,
one-batch r4-only authorization for the repaired driver; P4 remains NOT RUN.

**2026-09-16 P3 r4 second setup interruption / ephemeral snapshot repair:** A
second explicitly authorized fresh run, `c1-p3-fdi31-20260916-r4-r2`, passed
checksum, readiness and r4 load, then stopped before any candidate, candidate
JSON, completion marker, planner request or motion action because r4 has no
persisted confirmed-task record after offline restore. The P3-only repair uses
the existing pure task-snapshot constructor to build a non-persisted,
evidence-labelled snapshot from unchanged r4 Entry/Target, live Task Home,
current base/limits/resource fingerprints and established tool provenance. It
rejects every freshness issue except that exact missing-confirmation state; no
workspace or normal task confirmation is invoked. Focused checks pass 29/29.
P3 remains **NOT TESTED/INCONCLUSIVE** and needs a new explicit one-batch
r4-only runtime authorization; P4 remains NOT RUN.

**2026-09-16 P3 r4 third setup interruption / native joint-topology repair:**
The explicitly authorized fresh run `c1-p3-fdi31-20260916-r4-r3` passed the
r4 checksum, readiness and Slicer load, then stopped before any native IK,
candidate JSON/completion marker, planner request, preview, insertion or motion
because the diagnostic assumed the native joint-limit API contained exactly
J1–J5. Read-only native source/API evidence established the actual complete KDL
chain as J1–J5 plus the known external visual spindle. The P3-only repair now
requires precisely that known topology, uses native joint types, selects only
J1–J5 in planning order, rejects unknown/duplicate/incomplete topology, and
wraps deduplication only for continuous J5. It does not seed, solve or guard
the spindle. Focused source checks passed 29/29 with syntax/matrix/compile/diff
checks and Graphify refresh. This is a topology/setup interruption, not
endpoint evidence; P3 remains **NOT TESTED/INCONCLUSIVE** and needs a new
explicit one-batch r4-only authorization. P4 remains NOT RUN.

**2026-09-16 P3 r4 completed bounded-negative gate:** The explicitly
authorized fresh batch `c1-p3-fdi31-20260916-r4-r4` completed after the
native-topology repair. It passed locked-r4 checksum/readiness, emitted
`DENTOBOT_ENDPOINT_ONLY_COMPLETE`, and wrote fresh candidate evidence SHA-256
`8853f5208a87368d2611fd9c0a9737fe6b73b4da43de6851f4a428adee3f734c` in its
own r4-only directory. It completed exactly 128 seeds: 21 native position-axis
IK convergences, six unique solution clusters, zero generic-static-valid,
zero phase-static-valid and zero P4-retained candidates. Result:
**NO VALID TARGET SOLUTION FOUND IN BOUNDED SEARCH**. All converged candidates
had a phase rejection for provisional-tip departure from the approved
Entry-to-Target corridor; generic static records additionally reject the
Template↔visual-spindle and target-tooth↔burr contacts. There was no `Planning
request`, preview, joint command, controller/hardware motion, spindle/patient
action or historical-data input; teardown left zero matching processes. This
is not proof of global/physical infeasibility and does not authorize changing
geometry, tool, base, limits, target, guard policy, seeds or solver. Campaign 1
stops at this unresolved P3 negative. **P4 is NOT RUN**; the sole next action
is an architectural review to choose a separately scoped later campaign.

The operator's current Step-4A–5B screenshots confirm the four Step-4B
support-neighbour IDs only; they raise a duplicate closed/opened display and
unreconciled Step-4C/5A plane state. New-case default and legacy Step-5B
preflight/status source corrections passed focused pure checks, but the frozen
r7 package/geometry were not changed. P1 overall remains INCOMPLETE, retained
P2 evidence remains PASS with USER_REVIEW_REQUIRED, and P3 is not entered.
See recovery report Section AK; Section AJ's grouped signoff questions are
superseded, not answered wholesale.

The operator separately saved `dentobot-case-15sept.dentocase` as an intended
reusable opening/robot-base test foundation after deleting the perceived FDI31
artifact. Read-only audit (report AL) found the opening, landmarks and base
matrix are saved, but the base is unlocked, Step-4A target ID/ROI and three old
supports remain, and closed/opened FDI31 are both saved 3D-visible; it is
`PartialOrInspectable`, not `FoundationOnly`. The separate current Step-5B
`2026-09-15-Scene.mrb` supplies the previously missing four-support, dock and
plane readback (report AM): its closed-source FDI31 is hidden, but its 5A
displayed plane normal is 42.45° from its recorded fit normal after jaw
reparenting. A minimal shared source repair and focused pure checks pass;
saved files/frozen Campaign-1 source/r7 are untouched. Next acceptance action
is a bounded offline Slicer plane-frame save/reopen check plus operator scene
review, not P3 or automatic reuse of the partial foundation case.

The source-only follow-up recovered the existing wrapper control flow but could
not prove the failed final2 branch because wrapper readiness/status and
Slicer-request evidence were not retained; that limitation is historical. The
focused handoff helper records those stages and preserves exit status. The
later explicit bounded recheck reached Slicer and produced the current packet;
its bounded native evidence is the current P2 result in report Section T,
while the campaign gate remains `USER_REVIEW_REQUIRED`. This does not
authorize operator acceptance or any P3/P4 action.

**2026-09-15 recapture review correction:** The operator-observed separation
is supported by read-only artifact evidence: the new FDI31 display copy omits
the mouth-opening transform, static labels use transition-sample centres,
and both exported MRBs omit the robot pose transforms referenced by their
models. See recovery report Section W. Under the existing
`S6-REUSABLE-CASE-SETUP` / `S6-LIVE-01..02` owners, the recapture now requires
technical frame/state/persistence correction before operator visual review.
The source-only correction is retained in
`Testing/run_dentobot_c1_display_only_recapture.py` with ten focused pure
tests passing; it now separates endpoint versus transition capture, uses
prepared world-frame copies, and verifies saved robot-pose persistence and
native FK before any future image. It consumes a future explicitly saved
evaluated-sample FK record but does not substitute endpoint/offline FK. No
second display runtime is authorized from that source result. The one approved
endpoint-only Slicer session loaded the retained MRB but stopped before
endpoint capture because this runtime lacks
`vtkMRMLModelDisplayNode.SetPropertiesLabelVisibility`; its manifest is
preserved separately and contains no image or review MRB. Endpoint parity was
therefore not established (this is not a geometry/FK parity failure), and the
transition remains `NOT_RUN` with missing saved native FK for sample 1/134.
Do not request blanket input acceptance or another camera-only/native retry.
The retained native P2 packet is not erased or superseded by these display
defects. No geometry/policy change, implementation or runtime authorization
is inferred from the operator's diagnostic question.

**2026-09-15 endpoint-only repair continuation:** The operator then authorized
source fixes and bounded reruns for Slicer-session blockers. The retained
driver now passes 12 focused pure tests after an optional display-label guard
and a model parent-transform world-matrix fallback. The final scoped display
attempt reached the endpoint parity gate and failed closed: final printable
template geometry matched, but the prepared FDI31 target fingerprint differed
and its maximum bound error was 40.74010467529297 mm versus the 0.05 mm
tolerance. Robot mesh/link transforms and native-vs-offline FK matched; burr
and spindle matched displayed native FK; displayed TCP remained unavailable
because no TCP model exists in the seven-model display set. Save/reopen was
not reached. Endpoint review is BLOCKED, transition is NOT_RUN, all three
runtime artifacts are preserved, and the display retry ceiling is reached.
No geometry/policy change or further runtime is authorized from this result;
the remaining next action is a new evidence/implementation decision for the
prepared-target frame and displayed-TCP contract, not operator acceptance.

**2026-09-15 revised endpoint parity repair authorization:** The operator
explicitly superseded that runtime stop for the two evidenced source defects:
reuse native one-time Case Foundation target preparation plus native
triangulation, and derive the legitimate meshless canonical TCP from the
displayed spindle mesh and fixed URDF relation with robot-profile identity
verification. The focused source suite passes 18 tests. The mounted driver
hash matches the host, the existing container is up with no matching
task-owned/native processes, and a separate repair3 output location is ready.
At most three targeted endpoint-only offline Slicer attempts are authorized;
the exact pre-execution record and command are in recovery report Section AE.
Transition remains NOT_RUN, operator acceptance remains NOT_RECORDED, and the
existing P1/P2 and P3/P4 gates are unchanged.

**2026-09-15 endpoint repair result:** The three authorized targeted
endpoint-only attempts are complete. Repair5 passed the full machine parity
gate after the driver persisted the exact retained J1-J5 vector through the
existing workflow parameter-node rehydration path: prepared target/template
fingerprints and bounds, one-time jaw preparation, robot identity, displayed
link/mesh transforms, derived meshless TCP/burr/spindle FK, save/reopen pose,
and nonblank context/close-up images all passed. The separate review MRB and
JSON packet are retained in recovery report Section AH. Transition remains
`NOT_RUN` because saved sample-1/134 native FK is unavailable; image label
placement/target scale and all operator acceptance remain for review. P1
overall scene correctness remains `INCOMPLETE`, the retained native P2 status
is unchanged, and P3/P4 plus later runtime/hardware actions remain
unauthorized.

**2026-09-15 operator review delta:** The operator accepts the corrected
repair5 endpoint screenshots and requests the next Luna prompt. That visual
review is no longer pending; all-input/clinical acceptance is not inferred.
Under the same owners, reconcile remaining P1 decision-critical inputs from
retained evidence before the proposed conditional P3 batch. Missing historical
transition imagery is deferred and does not itself block static endpoint
feasibility. See report Section AI. No P3 execution or P4 authority follows
from this prompt-preparation turn.

Current dependency sequence: `W5-U-04` → `S3-P0-DENTAL-SEMANTICS` for any
pulp-dependent target packet → `S6-REUSABLE-CASE-SETUP` per-target
4A–5C/STL/save/fresh-reopen gate → `S6-LIVE-01..04` per-target planner, guard,
repeat and playback evidence → normal-window acceptance. Run independent
central incisors FDI31 → FDI41 → FDI11 → FDI21. A target-specific failure
records `FIRST_INVALID` and proposes the next tooth only after operator
approval; shared source/package/runtime failures
stop for a bounded correction. Pairing, optional 32 × 3 testing and the
six-target batch remain downstream. Step 4A review stays in the preparation
review; Case Platform/Studio remains behind `S6-LIVE-05`.
Campaign execution uses operator-selected Luna Max; unresolved higher-reasoning
decisions return an evidence packet and pause the affected path, with no
automatic model switch or speculative workaround. See the campaign gate in
`DEVELOPMENT_PLAN.md`.
The generator STL/folder/diagnostic change is implemented. The operator then
explicitly approved the bounded offline Slicer/ROS/MoveIt check for the
current FDI31 semantic implementation (no robot motion or patient-facing
action). Its current-source run reached the exact target endpoint but stopped
at the first native Stage-3 guard collision; the full FDI31 Step 4→Step 6
simulation therefore remains open. Do not retry or advance to another tooth
under the older full-flow packet. Campaign 1 instead investigates the responsible
layer under its new diagnostic gates; execution approval remains pending.

**Reusable-case implementation handoff:** the Case Foundation/offline-base
revision and the opened-planning-frame correction are reconciled into this
checkout. The authoritative 13-September package was preserved, migrated
through the production serializer, and reopened as a current single-target
FDI31 package with one eligible PreparedBranch. The selected exact route
reaches the requested target endpoint kinematically, but the current native
guard rejects the final Stage-3 drilling waypoint because the spindle housing
contacts the selected tooth. A live-joint scene-sync correction and a native
world-evidence cache removed earlier runtime bottlenecks; the exact
current-source failure is now a diagnostic `FIRST_INVALID`, not a timeout. Do
not repeat source implementation, alter the base/depth/dimensions/guard
policy, or revive the retired phantom path.

**Current operator delta (2026-09-13; order superseded 2026-09-14):** bounded source-only Stage 6.5/6.6
planner interaction work is authorized in parallel with these open gates. The
existing diagnostics now carry selected/locked route intent and require a
fresh current re-plan after restore; this does not reorder the integrity,
geometry, PreparedBranch, normal-window or separate runtime-approval gates.
The operator additionally requires the trajectory-guide channel/hole to be at
least 2.0 mm and asks for distinct per-target diagnostics and a valid case-save
campaign. The six-target FDI31/32/11/12/13/14 matrix remains downstream. The
current 2026-09-14 acceptance delta fixes the order to
FDI31→FDI41→FDI11→FDI21. Each target gets an explicit folder under
`data/Slicer_Saved/SampleStudy1/` containing its `.dentocase`, exported STL,
diagnostics and screenshots. The source has all four tooth masks but lacks
FDI11/21 pulp masks; record missing required pulp as input-data failure and
continue. The bore-floor source gate is implemented below;
the current-case rebuild, per-target Step 5B/5C evidence, planner runtime,
Return-Home loop and saved-case reload remain acceptance work, not inferred
from the source change.

| ID | Priority | Remaining work / state | Dependency, next acceptance and overlap |
|---|---|---|---|
| `W5-U-04` | 0 | Current FDI31 regeneration passes the explicit geometry gate; the historical 5-voxel fragment is not reproduced in the current artifact. FDI11 remains the comparison pass. | Preserve the one-solid/zero-channel/four-open-bore gate and complete the normal-window Step 5B/5C review, including fragment classification evidence. Construction remains the `W5-U-03` fusion owner; do not raise the cleanup threshold. |
| `S3-P0-DENTAL-SEMANTICS` | 0 | Step 2 per-run pulp inventory, legacy manual check, bulk candidate preparation, persistent table and single-tooth action are implemented. Step 4A generation creates no mask. A legacy FDI11 audit found 28 teeth (5 associated, 14 missing, 9 needing attention); full all-tooth bulk exceeded 600 s. Focused FDI11 creation and MRB/dentocase reload passed. Tarun's `SEPT24/pulp-testing-fdi11.dentocase` exposed a persisted parent-FDI lookup error; the shared helper now reads the selected child. Tarun's subsequent normal-window screenshot shows successful FDI11 assisted generation from that case, confirming this path passed in the live UI. | Inspect the 52-voxel candidate and Step 2 report in a normal window and give the anatomy/UI verdict; Step 4A trajectory-aligned MPR review remains under `S4A-PULP-ENDPOINT`. Full all-tooth throughput and existing source-mask Case B acceptance remain open. Derived segment addition currently invalidates Step 3A by the source-segmentation fingerprint; policy change requires a separate bounded decision. |
| `S6-REUSABLE-CASE-SETUP` | 0 | **2026-09-24 stale-pose reopen confirmed in Tarun's normal window:** UI hydration had reissued the saved robot-base lock command, which throws when Case Foundation is stale and caused transactional `.dentocase` load rollback. Placement refresh now restores lock interaction state without changing lock evidence or requiring a current pose. Tarun confirms `SEPT24/pulp-testing-fdi11.dentocase` now reopens; screenshot shows subsequent Step 4A FDI11 generation. Sep-25 FDI11 Step 6 reopen exposed MRML jaw-matrix precision loss and session-only navigation; guarded exact-matrix restore plus saved stage is source/pure-package checked. Tarun now confirms the same package lands on Step 6 in his normal window, but its display combines opened anatomy and closed-source CBCT; committed-opened Step 3/6 recommended views now hide source CBCT by default, with visual verdict pending. Persisted stale Step 3A/Step 6 gate details remain unmeasured. **2026-09-22 headless save/reopen PASS:** The repaired workflow was saved as `FDI21-31-headless-verified-sep22-step6a.dentocase` (SHA `c16e0406…d1c1d`) without overwriting the supplied package. A fresh headless Slicer process reopened it successfully: selected FDI21 branch eligible/`VALID`, and both FDI21 and FDI31 trajectory slots remained `Current`. The preceding GUI sequence also passed FDI31→FDI21→FDI31 and final FDI21 Step 6A activation. This is Runtime Verified headless evidence, not an operator-visible verdict. | Tarun loads the new package in the normal window, confirms both target-guide rows remain verified/current when alternating them, and gives the visible acceptance verdict. This does not establish a fresh FDI21 planner result. |
| `S4A-PULP-ENDPOINT` | 0 | Source/focused checks pass; anatomical review pending. The earlier failed FDI11 line is reproducible with the existing automated crown-cap Entry logic: the 52-voxel candidate is intersected, but its default-smoothed (factor 0.5) surface has zero line hits; an in-memory unsmoothed surface has eight hits. Tarun’s later normal-window screenshot shows one FDI11 assisted trajectory created (9.74 mm) with a 1.14 mm native/display boundary offset; the exact operator Entry and anatomical verdict remain unmeasured. | Assess whether a persisted, candidate-specific surface correction is needed without silently changing all tooth displays; then compare against the now-successful operator Entry and obtain trajectory-aligned MPR anatomical verdict. Preserve shared native/displayed contact and source voxels. FDI31 review remains open. |
| `W4-U-02` | 0 | All-step Views smooth toggle and actual opened-mask native fallback implemented. Supplied-case off/on and the Step 4A display portion of the matrix regression passed; the combined matrix run then stopped in assisted-endpoint setup on an unrelated review gate. Normal-window acceptance remains pending. | Confirm default smooth in a fresh case, truthful on/off across steps, CBCT/mask changes, oblique exit restoration and backtracking in the normal window; distinct from missing opacity controls `VIEW-U-02`. |
| `S6-LIVE-01` | 0 | **IK-only source gate checked; first operator-visible FDI11 report received, verdict pending.** Three visible historical hints reached collision-clear/static-valid/FK-passed PreEntry endpoints in an intentionally changed base/Home/scene; the direct Home seed timed out after one iteration without reaching collision check. P1/P2/P3 and guard are NotRun. Tarun will save the changed setup separately and chose to discuss the IK evidence before advancing source gates. The original saved all-zero-Home setup has not been retested. FDI21 r6 Stage-3 attribution remains separate. | Discuss seed dependence, the one-iteration Home timeout, and historical versus live Home connectivity with Tarun. Obtain the separately named saved case or exact base matrix before claiming reproducibility. Hold dependent workspace/P1/P2/P3 migration until his first verdict. Correct FDI21 recapture before its later Stage-3 review. No autonomous planner trial, base/Home change, guard optimization or milestone claim. |
| `S6-LIVE-03` | 0 | Completed-phase reverse-history Return Home is implemented; repeat-loop acceptance is `NOT_RUN` for FDI31 because Packet E stopped at its first-invalid Stage-3 guard result. Tarun chose **Block return** for interrupted phases in this renovation. | Retain exact accepted prefix, last accepted/monitored state and first rejected state/evidence where one exists; latch Incomplete/AwayFromHome and block further preview/normal Return Home. Guarded exact-prefix reversal is a separate future feature and acceptance gate; no reset/teleport counts as Return Home. Run the complete repeat loop only after an accepted Complete route and operator verdict. |
| `S6-LIVE-04` | 0 | Implemented; playback/restore acceptance is `NOT_RUN` for FDI31 because Packet E did not complete. | Confirm speed, ordered acknowledgements, visible stage paths, saved route intent and current re-plan only for an accepted Complete route. |
| `S6-LIVE-05` | 0 | Blocked by workflow integrity and reviewed clean-case selection | Require finalized guide/tool geometry, complete guarded approach/drilling-preview/withdrawal/Home and fresh repeat. Gates P1 Studio; no hardware authorization. |
| `S6-FDI11-DEPTH` | Unprioritized | Paused: FDI21 housing contact at final drilling waypoint | After integrity acceptance, reconcile exact case/tool/guide identity and propose smallest Stage-3 check. Old 91.7%/x4 values are historical; no automatic base/depth/margin tuning. |
| `S6A-CHANGED-TARGET-GEOMETRY` | Unprioritized | Clear/save guard checks pass; clean FDI44 full workflow review pending | Verify Step 6A geometry from clean session; regenerate cross-target chains if reported. Coordinate stale-proxy ownership with reusable-case restore; do not infer mesh identity from text. |
| `S6-RESTORE-ROBOT-ROS` | Unprioritized | Offline-load contract implemented; fresh/warm reconstruction review pending. FDI11 Step 6 package carries a saved opening and offline robot data; its forehead plane/contact envelope was already stale at save. | Share load campaign with reusable-case acceptance: no auto-connect or duplicate objects; saved Home is configuration only. Check the 2026-09-25 precision-only opening restore in a fresh process and normal window without promoting stale plane evidence. Includes old `S6-P0-02` restore work. |
| `S3-U-01` | Unprioritized | Scan/run inspection implemented; real-scene visual acceptance pending | Review source-paired preDental/postDental switching, context, compare, rename and Step 4 handoff. |
| `S6-U-04` | Unprioritized | Diagnostics Close fix implemented; visual acceptance pending | Verify Close before/after evidence review, reopen and callback state in an authorized Goal 1 session. |

## Pending planned work — queued milestones

Accepted design intent does not authorize execution. Contract and detailed
acceptance references: TASKS.md and DEVELOPMENT_PLAN.md, under these same IDs.

| ID | Priority | Remaining outcome | Entry condition / overlap |
|---|---|---|---|
| `DCP-00` | 1 | Freeze accepted Track-A backend handoff and per-step headless evidence inventory. The existing-script [reuse index](diagnostics/TESTING_VERIFICATION_SCRIPT_INDEX_2026-09-24.md) is compiled; step-by-step evidence mapping remains open. | `S6-LIVE-05` complete; before any Studio implementation, every current workflow step and its save/reopen handoff must be automatable headlessly and verified against the production path. Record uncovered steps and first failures under their existing owners; no blanket pass from isolated headless checks. |
| `DCP-02..08` | 1 | Remaining domain/session and cross-session proof | `DCP-00`; audit/reuse accepted PreparedBranch, registry, shared environment and persistence. Never rebuild the promoted P0 subset. |
| `DCP-09..10` | 1 | SQLite DentoLibrary and case browser | Case/platform foundation accepted. |
| `DSS-01..05` | 1 | Studio shell, Robot/Environment, Workspace, Trajectories, guarded-preview migration; implementation on hold | `DCP-00` headless per-step gate, data foundation and frozen Track-A behavior; `S6-WORKSPACE-PURPOSE` before Workspace migration. |
| `DSS-06..12` | 1 | Studies, results, replay, Procedure/Research separation | Guarded Preview parity; replaces old F0/F1/F2 and separate `.dentostudy` proposal. |
| `DHW-01..02` | 1 | Hardware-session/digital-twin interface preparation | Explicit later architecture/safety approval; no hardware operation. Coordinate `A-004`/`A-013`. |
| `S6-P1-01` | 1 | Bilateral condylar/crown regions, source snapping, MPR/anatomical safeguards | Current P0 accepted; shared crown semantics with `W4-U-01`, not a second anatomy authority. |
| `S6-P2-01` | 2 | Post-load Steps 1–6 integrity panel | Understand restore matrix via `S6-RESTORE-ROBOT-ROS`; reuse existing eligibility/staleness backend. |
| `S6-P2-02` | 2 | Display-only incisor-gap preview and explicit commit | `S6-P1-01` accepted; reuse existing jaw transform. |
| `S6-P2-03` | 2 | Active broad responsiveness correction. Load batching, Connect refresh suppression, goal-robot render pause and collision-publish render pause passed focused headless checks. Direct opt-in timing attributed 3.023 s of Connect and 6.163 s of Disconnect to `processEvents()`, while label/watchdog/log/stdout together cost <0.03 s in each action. Rendering paused only across 31 obstacle-proxy removals retained each completed-count callback and left no proxy nodes; same-case Disconnect fell 8.421→2.757 s and `processEvents()` time 6.163→0.333 s. Connect remained about 12 s with 31 acknowledged objects/copies/proxies before Disconnect. Temporary timing hooks were removed. The broad synthetic Views smoke now passes after correcting its ineligible-pose stage-lock fixture; this does not establish normal-window Views acceptance. Native shutdown still exits 1 with leaks. Current `:0` is llvmpipe, so hardware 60 FPS remains unmeasured. | Keep task open. Preserve truthful progress and cancel checks; the shared updater is not the measured root cause. Keep native shutdown and normal-window Views acceptance separate. Verify at least 60 presented frames/s and responsive input on capable Ubuntu and Windows 11/WSLg GPU hosts, recording actual renderer, GPU/VRAM, scene, viewport and frame pacing. Software rendering is only an extreme-hardware diagnostic. No MRML/ROS worker thread or planner policy change; Step 6.4 remains under `S6-LIVE-01` pause. |
| `UI-P3-01` | 3 | Broad New GUI/UX refinement with Legacy parity; defer design until workflow and Studio functions settle | Studio functional acceptance and P1–2 correctness; consume `W4B-P2-SUPPORT-AUTO`, `W5-U-05`, `VIEW-U-02` contracts rather than duplicate them. Current-workflow usability and truthful status fixes remain with their existing owners and gates. |
| `PLAT-U-06` | Unprioritized | Isolated 5.12 five-reload and simulation scene-lifecycle gates pass, but MoveIt collision geometry is unverified. Read-only binding evidence shows `resource_retriever` curl symbols resolve to Slicer's `libRemoteIO` in the failing configuration. Historical system-curl preload trials got past the `file://` protocol error but failed positive static contact; they do not establish usable geometry or clean teardown. The 5.10 rollback and `LAB_RELEASE` remain unchanged. | Full Slicer rebuilding stays stopped under Tarun's last-attempt limit. Assess a narrowly rebuilt ROS `resource_retriever` local-file read path (or equivalently isolated retrieval) without changing URDF/meshes; first discriminate retrieval success from probe/scene contact failure using the existing focused gate. No new build or runtime until the bounded correction and execution scope are approved. Representative case and performance await verified geometry in [upgrade plan](SLICERROS2_5_12_UPGRADE.md). |
| `PLAT-U-07` | Unprioritized | Data folder created and initial pilot partially synced: 7 of 17 approved `.dentocase` bundles uploaded; 10 larger bundles remain pending browser upload | Use `IITM Dentobot/Data` with the preserved `SampleStudy1/FDI*` layout. Finish only the remaining individual synthetic or explicitly approved de-identified bundles, then verify Drive metadata and checksums. Never sync the whole `Slicer_Saved` tree, raw/non-anonymized bundles, engineer-owned records, or credentials. |

## Backlog — DENTO-NOTEs, design and remaining verification

These are retained obligations; they are not automatically the next major plan.
Source observations, risks and evidence remain under the matching TASKS.md ID.

| ID | Priority | Pending outcome / observation | Dependency / next bounded action |
|---|---|---|---|
| `W4B-P2-SUPPORT-AUTO` | 2 | DENTO-NOTE: narrow two-row support arch; four-nearest support suggestion and single-row jaw UI; source suggestion/pure checks complete 2026-09-15 | P0 integrity first; verify the current four-ID automatic suggestion in a normal window, preserve manual review/lock and edge/missing-tooth handling. UI layout integrates with `UI-P3-01`. |
| `S6-U-01` | 4 | DENTO-NOTE: isolated 5.12 simulation lifecycle now passes connect/reload/clear/reconnect/save-reopen and exits 0 without a VTK leak report after fork `1a91963`. This accepts native cleanup for that synthetic gate; representative saved-case and normal-window behavior remain unverified. | Preserve P0–3 order except the active 5.12 upgrade dependency. Retain the 5.10 rollback and monitor representative runtime teardown before closing broad hygiene. |
| `S6-WORKSPACE-PURPOSE` | Unprioritized | **2026-09-24 source audit complete:** 5 mm is draft non-adjacent-link AABB self-clearance; environment point clearance defaults to 2 mm. On the saved FDI11 robot, the draft 5 mm filter rejects a guard-validated all-zero Home while sample-derived J2 minimum excludes that Home. Tarun directs moving its useful reach/seed diagnostics into Planning & Diagnostics and confirms an editable, central-incisor-midpoint 200 mm cubic TCP sampling ROI for the Step 6 renovation. | Implement the cube as a sampling-domain boundary before expensive checks, with measured yield/time; post-filtering alone does not speed the current fixed-count joint sampler. Resolve ROI frame and landmark fallback and optional workspace/limit semantics. Sample-domain exclusion cannot prove mechanical impossibility. Preserve mechanical bounds, MoveIt/guard and reconnect freshness; representative visual/runtime acceptance open. Studio Workspace remains downstream. Priority remains Unprioritized. |
| `VERIFY-LEARN-01` | Unprioritized | **Ordinary 4A→6.5 GUI path operator-confirmed 2026-09-19** on this debug branch. First truthful live planner failure is Goal 1 P1 PreEntry (13 legs) on the verified `dentobot-case-sep19-step6.dentocase`. Teaching-session checklist remains open. | Planner diagnosis is owned by `S6-LIVE-01` under the 2026-09-21 milestone contract. Keep Campaign-1 versus GUI evidence levels distinct. |
| `W4-U-01` | Unprioritized | Reviewed crown Entry snapping/MPR contract | Define crown region, then source-fingerprinted snapping; remaining Entry subset of `A-035`. |
| `W5-U-01` | Unprioritized | Physical guide/burr fit provenance; optional export manifest | Verify actual dimensions and physical fit; decide manifest separately. Neither export nor STL becomes Step 6 authority. Includes tracker A-032 dimensional concern. |
| `IMG-U-01` | Unprioritized | Representative mask/display and uncertainty acceptance | Governed CBCT, acquisition/artifact/segmentation evidence; coordinate `VIEW-U-01` display campaign. |
| `W4C-U-01` | Unprioritized | Dock/rail mechanical design and representative acceptance | Agree registration vs load-bearing role, tolerances, channels/collisions and nonparallel trajectories vs one robot axis; overlaps `A-038` fiducial interfaces. |
| `W5-U-02` | Unprioritized | Physical/representative support, margin, undercut, shell seating/removal | Governed anatomy/phantom and criteria; includes remaining normal-window/manufacturing review after verified `S5B-TERMINAL-COLLAR`, without reopening its fixed defect. |
| `W5-U-03` | Unprioritized | DENTO-NOTE: detailed Step 5B/5C testing beyond smoke. The stale cross-target guide-selection repair and FDI21 independent template passed the bounded headless two-target GUI and fresh-reopen check; normal-window verdict remains open. | Retain the FDI11/FDI31 fusion, PASS/WARNING/FAIL, reopen, stale-lineage, channel-preservation and one-STL review. Shared construction fixes stay under `W5-U-04`; multi-target session support does not imply a multi-target fused template. |
| `W5-U-05` | Unprioritized | DENTO-NOTE: dimension coupling, missing Reset/interactive inspection; 2026-09-19 source force-enables section 2 and lifts live sub-floor holes to 2.1 mm | Confirm live section-2 editability after restart; remaining Reset/interactive sizing still open. |
| `VIEW-U-01` | 1 | **FDI11 normal-window source-CBCT overlap observed; revised recommended opened view pending Tarun's verdict.** On the supplied `FDI21-31-headless-verified-sep22-step6a.dentocase`, the first ghost transition was Step 4A's “All teeth masks — 2D + 3D” preset: 28 untransformed source segments became 2D-visible beside opened anatomy. Shared normalization now hides the closed source in both dimensions and routes copied teeth to opened displays; target highlighting and source-tree toggles invoke it. Source-only masks without opened proxies stay hidden. Serialized Slicer checks passed target switch, presets, source/derived tree controls, view restore and Legacy/New parity. A final focused temporary save/reopen on this revision emitted `VIEW_U01_REOPEN_PASS`. | Tarun reviews the supplied case in the normal window, including whether source-only mask access is sufficient, and gives the visible verdict before closure. Keep source anatomy, geometry, collision and planner state unchanged. `S6-REUSABLE-CASE-SETUP` owns restore/branch activation; `VIEW-U-02` retains opacity UX. Tarun deferred this verdict and explicitly advanced `W4-U-02` on 2026-09-24. |
| `VIEW-U-02` | Unprioritized | DENTO-NOTE: lost mask 2D/3D opacity controls | Written UX plan acceptance first: map ownership, persistent stage-safe fill/outline/surface controls and CBCT parity, then implementation and normal-window trial. |
| `S6-U-03` | Unprioritized | Experimental observed oral-air representation | Suitable open-mouth/phantom data; confidence labels, unobserved space remains occupied/unknown; never planning authority. |
| `CASE-U-01` | Unprioritized | Offline migrator for ROS-contaminated historical MRML/MRB | Define isolated no-ROS migration; distinct from normal `.dentocase` offline restore. |
| `PLAT-U-01` | Unprioritized | Clean pinned inference-image reconstruction acceptance | Rebuild and verify dependencies/backend/Bridge/Slicer/persistence; reconcile A-026 residual tests and transitive lock against current Ubuntu baseline. |
| `PLAT-U-02` | Unprioritized | Native Windows Steps 0–5 fallback real-host regression | Windows host; verify hidden Step 6/no auto-restore, no native Windows ROS. A-034 residual fallback acceptance. |
| `PLAT-U-04` | Unprioritized | Second direct-Engine WSL machine acceptance and immutable lab release | Exact manifest plus approved check-only/GUI/segmentation/simulation; record actual WSLg D3D12 adapter and presented-frame evidence under `S6-P2-03`; isolated release revision, stable/lab/tag/image publication within authorization. |
| `PLAT-U-05` | Unprioritized | IITM CPU workstation regression after NVIDIA launcher integration; native NVIDIA graphics mode is source/Compose-checked but not GPU-host accepted | Documented check-only on IITM host; keep CPU unless CUDA intentionally adopted. On a native NVIDIA host, verify renderer/device access and representative presented-frame timing under `S6-P2-03` before claiming acceleration. |
| `PLAT-U-03` | Unprioritized | CRD/GDM overnight stability observation | Approved reboot/observation; preserve work. A-033 renderer/FPS follow-up remains distinct evidence within this platform lane. |
| `QA-U-01` | Unprioritized | Aggregate Slicer wrapper exits nonzero despite isolated PASS | Diagnose first wrapper/lifecycle failure; isolated PASS is not aggregate closure. |
| `ROS-U-01` | Unprioritized | Medical-image/transform interoperability design | Frame requirements stable; geometry-preserving contract before wider ROS scope; coordinate `A-004`/`A-022`. |
| `POC-U-01` | Unprioritized | Representative software → printed Template V0 → seating/registration → error budget | Freeze narrow task/thresholds; reuse template acceptance and `A-001`/`A-003`/`A-038` metrology instead of starting separate implementations. |

## Backlog — tracker obligations missing from the local queue

All rows below are **captured pending reconciliation**, not freshly verified
status or newly authorized execution. Preserve original IDs and owners. P0/P1
values are tracker metadata; `%` suffixes were allocation, not task priority.
Obtain current inputs before scheduling; old target dates are not renewed.
Grouped alias IDs represent one deliverable owner, not parallel workstreams.

| Canonical ID / tracker aliases | Tracker priority / owner | Pending deliverable | Dependencies, acceptance and overlap |
|---|---|---|---|
| `A-001` / `A-015` | P0 / Tarun | Complete CBCT→template→robot-base→end-effector→tool/tooth frame contract | Planning coordinates and CAD frames; named transforms, RAS/LPS, units, calibration/uncertainty and landmark round-trip. Reuse bounded software transforms; remaining full physical chain links `S6-U-02`, `A-022`, `A-038`. |
| `A-002` / `A-028` | P0 / Tarun | Compare head-mounted and tooth-mounted registration/validation chains | Head/mount and bite-block geometry/FOV/compliance; option matrix, calibration, TRE/repeatability, remount/failure gates. Coordinate `A-001` and `A-038`. |
| `A-003` / `A-016` | P0 / Tarun | Measurable error budget and validation plan | Clinical tolerances, mechanics, metrology; imaging→printing→seating→docking→TCP→drilling errors, target/angular/depth/TRE metrics with justified uncertainty propagation. Error-budget owner for `POC-U-01`. |
| `A-004` / `A-017` | P0 / Tarun | Remaining planning/navigation/robot/tracker interface contract | Current planning/mechanics interfaces; data/frame/update-rate/ownership and gates. Reuse Slicer/ROS architecture; align future `ROS-U-01`/`DHW-01..02`, no new transport by default. |
| `A-005` | P0 / Tarun | Tooth/bite-block-mounted mechanism concepts | Open-mouth geometry and actuator/tool envelopes; 2–3 annotated concepts with datums, disposable split, access/removal. Coordinate `W4C-U-01`; physical design scope requires current team inputs. |
| `A-006` / `A-024` | P0 / P1 respectively; Tarun | Structured registration/dental robotics evidence matrix and referenced clinical-workflow papers | Paper access; auditable procedure, architecture, motion handling, autonomy, validation and status with lessons. One literature deliverable; source priority conflict must be resolved before scheduling. |
| `A-008` | P1 / Shared | Approved pneumatic POC procurement package | Specifications/quotes and professor approval; reviewed BOM/cost/vendor/owner/arrival. Overlaps `A-037` supplies; no order authorized. |
| `A-009` | P0 / Varun | Representative planning/open-mouth/full-head dataset handoff | Suitable permitted de-identified imaging, anatomy/bite-block/tool geometry; frame-labelled STL and entry/target handoff. Input for mechanics and `POC-U-01`; confirm what is already delivered. |
| `A-010` | P0 / Snekan | Head-mounted five-DoF mechanism down-selection | STL/tool/workspace/mass/force and registration inputs; 1–2 concepts with base frame. External dependency, not an agent coding assignment. |
| `A-011` | P1 / Tarun | Approved clinical observation and constraint notes | Clinic permission/consent and coordination; observation-only pen-and-paper access/irrigation/control/removal notes. No messaging, visit or recording authorized by capture. |
| `A-013` | P1 / Shared | Human-in-loop physical safety/enable/foot-pedal state machine | Clinical/registration/controller inputs and verified safety process; quality/alignment/drilling-enable/failure/retry/e-stop gates. Preserve existing simulation guards; coordinate `DHW-01..02`. |
| `A-018` | P0 / Shared | Confirm integrated demonstration scope | Team alignment on target tooth, imaging, template, autonomy and TRL-4 criteria; preserve settled software single-target contract. One scope decision set feeds `POC-U-01`; no new clinical threshold assumed. |
| `A-022` / `A-029` | P0 / Tarun | Remaining frame-aware planning-to-mechanics handoff | `A-001`, recipient CAD/controller needs; mesh/trajectory/transform package with frame metadata and round-trip landmark proof. Reuse existing callable modules and `.dentocase`; physical/export boundary overlaps `W5-U-01`, `ROS-U-01`. |
| `A-036` | P1 in register / P2 dashboard; Tarun | Internal sensing invention package | Team/ICSR input, prior-art questions and required experiment evidence; reviewable confidential outline. Resolve source-priority conflict before scheduling; no external disclosure. |
| `A-037` / `A-007` | P1 / Tarun | Pressure/acoustic transition POC and protocol | Existing datasets, sensor/plumbing/sample/ground-truth inputs; repeatable positive or negative transition evidence and preserved configuration. Includes pending live flash/Hz Config-tab acceptance of existing sensing tools; no duplicate tool build or automatic drilling/flash authorization. |
| `A-038` | P1 / Tarun | Registration fiducial concepts and physical TCP/base/TRE repeatability | Geometry/material/phantom/mechanical inputs; ≥3 concepts with frames/detection/seating risks, select a measurement experiment. Coordinate `W4C-U-01`, `S6-U-02`, `POC-U-01`; four registration features are not proof of load-bearing docking. |
| `PRODUCT-DEFERRED` | Unprioritized / owner to confirm | Tracker-deferred panoramic/curved views, camera/intraoral scan, NPU, full canal automation and extra sensing modalities | Capture only, no accepted implementation plan. Split a bounded item only if it is selected and no existing owner covers it; software UI goes through `UI-P3-01`, ROS through `ROS-U-01`. Core PoC and actual input need first. |

## Overlaps to resolve when selecting work

| Pending scope / source aliases | Single owner and reuse rule |
|---|---|
| Tracker `A-023`, `A-032` template automation | `W5-U-04` construction; `W5-U-03` fusion/export acceptance; `W5-U-02` shell/fit; `W5-U-01` physical dimensions; `W4C-U-01` mechanics. Treat as linked acceptance slices, not a fresh template generator. |
| Tracker `A-035` trajectory assistance | `S4A-PULP-ENDPOINT` internal target and `W4-U-01` crown Entry. Old instruction to queue all assistance is superseded by later P0 correction. |
| Tracker `A-012`, `A-014`, `A-027` software/workflow umbrella | Reuse accepted Slicer architecture and implemented Steps 0–6. Remaining integration gates belong to `S6-REUSABLE-CASE-SETUP`, `S6-LIVE-01..05`, `POC-U-01` and `A-004`/`A-022` physical handoff. No architecture restart. |
| Tracker `A-026` inference robustness | `PLAT-U-01`; confirm cancellation/descendant cleanup, five old tests and lock requirements against current evidence before scheduling residual checks. |
| Tracker `A-033`, `A-034` marked complete but containing follow-ups | Retain only renderer/FPS and platform-host acceptance under `PLAT-U-03`, `PLAT-U-02`, `PLAT-U-04`, `PLAT-U-05`; migration itself stays closed. |
| Restore, stale target geometry, integrity UI | `S6-REUSABLE-CASE-SETUP` owns branch semantics; `S6-RESTORE-ROBOT-ROS` reconstruction; `S6A-CHANGED-TARGET-GEOMETRY` target cleanup; `S6-P2-01` presentation. Reuse one eligibility/invalidation backend. |
| Closed-mouth ghost anatomy after opening | `VIEW-U-01` is the Priority-1 cross-module display-acceptance owner. `S6-REUSABLE-CASE-SETUP` owns restore/branch-activation causes and `_enforceStep6OpenedJawDisplaySeparation` is the first shared mechanism to audit. Do not create target-specific deletion fixes or classify a display ghost as duplicate anatomy/collision geometry without node/transform evidence. |
| Active reusable-case / Step 6 reposition implementation | Remains one `S6-REUSABLE-CASE-SETUP` lane. Wait for its handoff, then reconcile the actual diff and evidence before selecting residual work; do not start a second reposition, case-foundation or branch-activation implementation. |
| Track-A loop, baseline cleanup and exact FDI11 blocker | One authorized acceptance campaign can serve multiple IDs only when each gate is explicitly observed and recorded. A case-specific failure does not create another planner workstream. |
| Crown regions, jaw opening, Step 4A assistance | Agree shared source-fingerprinted anatomy semantics between `S6-P1-01` and `W4-U-01`; retain distinct workflow acceptance. |
| Step 3B / 6.1 offline placement GUI | Accepted 2026-09-19 (`S3B-ROBOT-PLACEMENT-MIRROR` closed). One shared 3B/6.1 widget reparent, one MRML robot/base/forehead. Do not fork a second robot or a second virtual-forehead proposer. Operator closed `S6-U-02` at simulation scope; hardware metrology remains under `A-001` / `A-038` if required later. |
| Studio, studies, old F0/F1/F2 | Only `DCP-*`/`DSS-*` roadmap; `.dentocase` stays package authority. No parallel `.dentostudy` store. |
| Registration, frame graph, fit and error budget | `A-001` frames, `A-002` architecture, `A-003` error budget, `A-038` metrology feed `POC-U-01`. Shared fixtures/evidence do not erase separate physical acceptance gates. |

Remove or rewrite overlap rows when their pending scope closes. Historical alias
and completion evidence belongs in TASKS.md/logbook, not as closed queue rows.
