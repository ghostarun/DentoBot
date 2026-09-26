# Step 6 renovation — working implementation plan

**Date:** 2026-09-25. **Priority:** renovate Step 6 before case-specific planner solving. Owners are S6-WORKSPACE-PURPOSE, S6-LIVE-01, S6-LIVE-03/04 and S6-P2-03. [Backlog](../backlog.md) is the sole pending queue; [TASKS](../TASKS.md) holds task contracts; the [FDI31 P0 contract](FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md) retains its milestone and safety gates. The [base-pose feasibility plan](DENTOBOT_Base_Pose_Feasibility_Explorer_Diagnostic_Plan_2026-09-25.md) is an **active technical reference for shared diagnostic metrics**. Its automated sweep and robot-design comparisons remain later work in the [reference index](STEP6_LATER_WORK_AND_ADJACENT_IDEAS_2026-09-25.md).

## Operator-facing substeps and authority

| Substep | Capability | Authority boundary |
|---|---|---|
| 6.0 Case and branch | Select case, PreparedBranch, target and exact task identity. | Existing case ownership. |
| 6.1 Base and ROS scene | Connect simulation ROS/MoveIt, audit the collision scene and maintain the accepted base. | A workbench base candidate remains under review until **Accept Base** commits through the existing placement owner and invalidates dependent evidence. |
| 6.2 Task Home | Maintain accepted, monitored Task Home. | A workbench Home candidate remains under review until **Accept Task Home** passes the existing live-state and collision gates. |
| 6.3A Task-space ROI | Default 200 × 200 × 200 mm cube centered at the midpoint of the current Case Foundation incisor-gap line's upper and **opened lower** world-RAS points; edit center XYZ and dimensions XYZ. | Bounds TCP sample generation, never the route, robot links, joint limits or guard. Missing/stale landmarks require explicit center review. |
| 6.3B Manual Robot Simulation Solver / Engineering Workbench | ROS-connected base pose and J1–J5 manipulation, Task Home exploration, viewport/sliders/numeric/keyboard controls, manual reachability and drilling exploration, diagnostics, trajectory/path visualization and recording/export. | Valid joint jogs advance the simulated robot **after guard acknowledgement**. Rejected requests remain visible as review states with the reason and do not advance the accepted robot. Simulation-only; no hardware command. |
| 6.3C Planning and diagnostics | Shared PreEntry/Entry/Target IK evidence, separate P1/P2/P3, full-chain validation and one-click automatic planning. | Manual paths, ROI samples, saved reports and partial stages are display-only; only a fresh complete route passing the independent full-chain guard can authorize preview. |
| 6.4 Preview and control | Guarded Approach/Drill preview, Stop, status, normal reverse-history Return Home from a completed phase endpoint. | Interrupted preview retains accepted/rejected history and **Blocks Return**. Future partial-prefix recovery and reset need separate gates. Expert ROS status is read-only. |

Both navigators must share the same action ownership and locked-action reasons. 6.3 merges the old workspace, task-confirmation and planning cards; 6.4 owns preview and control. Accept Base and Accept Task Home delegate to 6.1/6.2 owners even when initiated from the workbench. J6 remains an external spindle and is fixed at zero in arm-planning display.

### What the engineering workbench must actually do

This is an **interactive robot simulation solver** for an engineer to discover feasible motion by direct trial and error. It is not a static ghost viewer, a screenshot tool, a renamed planner button, or merely an offline proposal form. The operator can adjust the robot's world base pose and inspect the change against CBCT, forehead mount, target tooth and scene; jog each of J1–J5 individually; adjust and compare a prospective Task Home; guide TCP position/orientation and explore the approach and axial drilling direction; inspect both valid and invalid states; and manually assemble a time-ordered candidate motion. The same URDF/SRDF, TCP transform, robot limits, scene objects and phase contact policy used by the automatic planner must explain each result. A review representation may show rejected or speculative poses, but the accepted simulated robot is a distinct, monitored state.

The GUI needs viewport transform handles for base and review poses, per-axis base translation/rotation controls, J1–J5 sliders and numeric values, keyboard increments with selectable step sizes, clear current/review/accepted pose labels, and an obvious way to select the next manually inspected state. Existing SlicerROS2 goal robot, joint sliders and path display are starting points, subject to measured latency and ownership checks. The workbench must keep the relevant tooth, trajectory line, tool axis, collision pair and accepted/rejected path visible while exploring, so a numerical failure can be understood spatially. It must show when the authoritative ROS/MoveIt/guard answer is pending, current, stale or unavailable. No `valid` badge may come solely from a fast display update or empty collision-pair list.

For joint jogging, render a requested review pose promptly, then issue the exact requested J1–J5 state to the existing simulation guard in order. Only an acknowledged accepted state updates the live simulated robot and accepted history; a rejected state stays in the review layer with its request, evaluated state and native reason. This does not silently turn a rejected step into a smaller or different move. Base and Home exploration are review operations until the operator invokes **Accept Base** or **Accept Task Home**. Accept Base uses the existing base placement/scene resynchronization and invalidates dependent Home, task, workspace and route evidence. Accept Task Home uses the existing monitored-state, limit, static collision and scene checks and invalidates dependent task/route evidence. Neither acceptance can be inferred from merely dragging a transform or saving a recording.

Simulation-only means no actuator, spindle, drilling or patient command endpoint is exposed in this workbench. Manual exploration and its recordings do not establish a guarded executable route. The normal 6.4 preview remains a separate phase with fresh plan/guard authority; an eventual decision about promoting manually discovered paths must be made from recorded evidence after the workbench is mature.

## Shared diagnostic evaluator and recording

Build **one structured Step 6 evaluator** through DENTORobotWorkflowFacade and DENTOROS2Bridge, reusing the robot profile, FK/IK, MoveIt scene, independent guard, phase policy and exact case/branch/base/Home/tool/trajectory/scene identities. The manual workbench, automatic planner and later Base-Pose Feasibility Explorer consume it; do not create a second IK engine, collision world or transform authority. A cheap local FK/review update may precede a heavier authoritative check, but it must never be labelled collision-valid before that check completes.

For every available check, report passed, failed, not_reached or unknown. Retain PreEntry/Entry/Target IK status, best failed J1–J5 state and position/axis residuals, mechanical and reviewed-limit margins, insertion continuity, collision status and named forbidden pair/clearance, task-Jacobian conditioning, solver termination, first-invalid **requested and evaluated** states, timing and exact fingerprints. Unknown clearance or conditioning is not a pass. Do not invent a hard singularity threshold or alter solver/guard tolerances. Preserve the existing IK-only FDI11 action; it cannot invoke OMPL or promote a route.

The evaluator is one **capability shared by manual and automated callers**, not a second persistent planner. It accepts an exact state or short ordered state/pose sequence plus task/phase and frozen identity, and emits one structured report. The user can request a cheap current-state check, a canonical PreEntry/Entry/Target endpoint check, or insertion-continuity/phase checks; the automatic planner calls the corresponding evaluator after creating candidates. The later automated base-pose sweep varies only candidate base transforms and invokes the same routines. The initial implementation may compose existing façade/bridge/native calls instead of adding a ROS action. Do not silently reinterpret a candidate-base result as current accepted-base validity.

The [base-pose technical reference](DENTOBOT_Base_Pose_Feasibility_Explorer_Diagnostic_Plan_2026-09-25.md) defines the diagnostic quantities to preserve now: per-seed IK best state and residuals; selected-branch continuity from PreEntry through Entry to Target; minimum joint margin; forbidden collision clearance from the same PlanningScene and allowed-collision policy as the guard; and a dimensionless, unit-normalized task-Jacobian conditioning measure for TCP position plus drill-axis control. Keep intended burr-to-task contact separate from forbidden spindle/anatomy or robot/anatomy proximity. If an exact native measurement is absent, expose its status as unavailable and add it through the authoritative bridge/native path in a bounded slice. Do not replace it with visual overlap, coarse AABB clearance, a new collision world or an arbitrary singularity cutoff.

The workbench records requested, accepted and rejected joint/TCP samples, base/Home review and acceptance events, validity transitions, diagnostic and collision evidence, identities and timestamps in a versioned export. Show a path and display-only replay. Assess existing Slicer screen-capture support for optional viewport video without blocking interaction. Reopened recordings are historical evidence; choose any later planner-precursor promotion with Tarun after representative records exist. Recording never substitutes for a fresh complete guard.

Recording is **required**, not a future nice-to-have. A session stores the chronological requested state, guard acknowledgement or rejection, monitored/accepted state, TCP pose and drill-axis pose, base and Home candidate/accepted identities, phase and target identity, scene/robot/collision-policy fingerprints, evaluator outputs, collision pair/clearance where available, and monotonic timing. Preserve exact samples rather than compressing away motion evidence. Export a human-inspectable diagnostic report plus machine-readable motion samples; keep viewport screen recording as an optional companion artifact, not the only record. Path visualization distinguishes requested, accepted and rejected segments. On reopen, recordings are labelled historical/display-only and cannot restore live Home/scene/guard or unlock preview. Review with Tarun which subset can later seed planning; do not decide that promotion merely by adding export.

## ROI generation and interaction performance

Generate deterministic TCP candidates **inside** the editable cube first, using the confirmed task drill axis for the first diagnostic. Then run IK, validity and optional bounded Home-connectivity checks on those candidates. Report attempted count, IK/valid/Home-connected yields and elapsed time by phase. The existing joint-space Halton sampler plus early ROI rejection may serve as a measured interim bridge, but post-filtering a finished whole-robot cloud is not the target algorithm. An unsampled point is not proven unreachable. Preserve FK reach, static validity, Home connectivity and exact oriented task feasibility as distinct labels. Reviewed task limits start from URDF mechanical bounds; a suggested window excluding a validated Home requires review.

The default cube center is calculated from the **current** Case Foundation upper-incisor point and opened-lower-incisor point in world RAS; do not mix a closed-jaw lower point with the opened scene. Show the source line and its case/opening revision, plus editable world-RAS center X/Y/Z and X/Y/Z side dimensions. A user edit creates a reviewed ROI revision and invalidates ROI samples and dependent workspace evidence. Missing, ambiguous or stale landmarks must not silently use a zero origin or old center. The cube constrains where TCP target candidates are *generated* for the task; it is neither a workspace-proof volume nor a prohibition on any connecting robot motion outside it. The initially confirmed task drill axis limits orientation work for the first sampler; later orientation enumeration needs a measured reason and its own scope.

The current fixed-count five-joint Halton sampler computes FK and coarse checks over broad joint space, so final-cloud clipping cannot satisfy the compute goal. The target implementation uses deterministic cube-space TCP candidates and existing position-axis IK, then evaluates limits, scene validity and bounded connectivity. Record failure/yield counts and timing at each stage, including IK seeds and termination. If the old joint sampler is retained temporarily, reject out-of-ROI TCPs before expensive static and connectivity checks, explicitly label it interim, and measure whether FK remains dominant before changing candidate generation. Never use its coarse AABB filter as an authoritative collision verdict.

Keep review rendering responsive while authoritative guard requests are serialized and acknowledged. Render local model/FK changes promptly; coalesce only superseded display updates, never accepted or rejected motion evidence. Run collision, ROS synchronization and full-task diagnostics separately from mouse/render updates. Discard responses whose candidate or scene identity is stale. Measure input-to-visible-frame, FK/MRML/render, guard/collision, ROS round-trip, full diagnostic and recording costs separately on one frozen scene and direct display. The **first interaction target is 60 FPS** during ordinary manipulation; retain frame-time and stall distributions and Tarun's usability verdict. Existing case-load/Connect/Disconnect gaps are separate measurements. Reuse checked-out SlicerROS2 sliders, interactive IK goal and path display; select one measured bottleneck correction at a time. A new physics engine is not implied by the experience target.

The 60 FPS target concerns the local interaction/render loop, not a promise that full MoveIt IK, collision and guard checks complete every 16.7 ms. Show the most recent authoritative diagnostic identity and age while a new result is pending; do not hide lag behind an apparently current badge. Capture input event → pose update → visible frame, local FK, MRML transform propagation, viewport frame time, guard transport/decision, ROS scene synchronization, endpoint/continuity evaluation and recording overhead separately. Measure both ordinary continuous manipulation and a bounded sequence of individual guarded jogs. Investigate current SlicerROS2 fork controls, rendering/event-loop behavior and upstream developments, but select changes from measured local bottlenecks; preserve strict acceptance ordering. An RViz/Gazebo/PyBullet-like experience is an interaction/usability target, not authorization to replace the physics or collision authority.

## Reconciled implementation review — 26 September 2026

**Reviewed baseline:** `40ad29089be3431735790c4592dd09d5a380bdfd`,
`feature/step6-workflow-renovation-20260925`, in
`/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-renovation`.
The parallel performance/5.12 checkout is outside this plan. Earlier source
checkpoints and exact commands remain in the [26 September logbook](../logbook/2026-09-26.md).
This section supersedes their intermediate completion summaries, not their evidence.

### Intended outcome and assessment

Tarun's latest clarification makes the engineering purpose explicit: use his
robotics expertise to explore configurations, base placement, valid and invalid
states and intuitive motion before asking an automatic planner to solve the
case. UI improvement supports that work. The manual workbench is optional to
use in the workflow but required to deliver in this renovation.

The direction is sound and substantial foundations exist; the engineer-facing
solver is **partially implemented, not ready for acceptance**. Repeated source
checks and launcher repair have outpaced the central interactive capability.
Operator checks are pending because Tarun is remote; that does not prevent
bounded source completion or meaningful automation. A failed planner/IK search
or manual attempt cannot prove mechanical impossibility. A successfully guarded
manual motion is a feasibility witness only for its exact simulated robot,
base, Home, scene, tool, phase policy and sampled motion. Physical feasibility
and design interpretation remain separate engineering judgments.

| Capability | Actual source at reviewed baseline | Remaining evidence or implementation |
|---|---|---|
| ROI-first sampling and Home-inclusive limits | Implemented, pure checked | Current-scene yield, freshness and visible review |
| Shared endpoint diagnostics | Goal-1, PreEntry and current-state callers share evaluator | Arbitrary draft input, full phase/continuity evidence, native clearance and conditioning |
| P1/P2/P3 diagnostics | Exact predecessor handoff and independent Home-prefix guard | Complete-chain promotion and final UI; partial stages have no route authority |
| J1–J5 workbench | Draft sliders/numeric/keyboard, ghost, explicit Guarded Jog, accept/reject/unknown handling | Native runtime verification, acknowledgement correlation and monitored convergence; invalid-draft inspection |
| Base/Home | Existing lock/save owners relabelled with candidate/Accept UI and terminal record events | Detached review candidates and controls; cancellation, explicit commit and invalidation integration |
| Recording | Schema 1.0, in-session events and current/latest JSON export | Complete motion/diagnostic samples, session selection, path display, historical reopen/replay and readable report |
| Presentation/performance | Controls added to old cards; existing preview machinery retained | Two-area migration in both navigators and measured local interaction |
| Preview interruption | Source latch retains incomplete-prefix evidence and blocks Return | Runtime Stop/reject/repeat verification and operator verdict |

**Evidence ceiling:** 193 host pure tests passed in the prior checkpoint (157
state/facade/planning + 36 UI/bridge); compilation, shell syntax, matrix parsing
and source diff checks passed. These include mocks/stubs and do not prove Qt
signals, native guard or rendered interaction. The six headless attempts were
launcher/fixture failures. The final manifest has all jog scenarios `NOT_RUN`:
no manual-jog runtime verdict or screenshot exists. User simulation trial and
Tarun's verdict are **PENDING**. Do not describe this as a failed robot jog.

### Concrete review findings to resolve first

- **Incorrect unknown-state message:** `widget_robot_shell.py:411–425` says the
  accepted robot is unchanged on unknown/exception, while the façade at
  `2589–2590` and `2643–2648` explicitly reports that it may have advanced.
  This is a source defect, not merely absent runtime evidence. Preserve the
  last confirmed state as historical, show uncertainty and reconcile before
  accepting another jog. Do not promise no motion after a lost/stale reply.
- **Raw acknowledgement attribution:** `DENTORobotWorkflowFacade.py:2562–2564`
  uses Python object freshness; `2620–2629` matches vector/world IDs and requires
  an absent policy fingerprint. The bridge status has no request ID/sequence.
  This cannot establish correlation of a delayed identical request or its policy.
- **Base review mutates the current transform:** façade `setBasePose` at `2712`
  writes `robotBaseTransform`; production Base nudge uses `logic.nudgeRobotBase`
  directly. The new façade recording method has no production caller. Candidate
  labels therefore do not establish detached review or per-edit Base history.
- **Evidence is retained but not fully usable:** panel `_manualJogEvidence`
  stores native details without showing collision bodies/distances as structured
  workbench feedback. The record writer at façade `2245–2343` does not populate
  evaluated joint samples, TCP/axis or full evaluator reports. Schema identity
  omits explicit limits and mandatory policy provenance. These are material gaps
  for comparing configurations, not reasons to build a separate recording system.

Line references describe baseline `40ad290`; inspect callers before implementing.
These findings remain under `S6-LIVE-01`, with workspace/preview overlap as above.

**27 September source continuation:** The first uncertainty boundary is now
implemented in the existing facade and panel. A submitted jog ending unknown
or stale latches the facade, blocks another publish, and leaves the draft and
last confirmed state visible. The UI no longer promises that the simulated
robot is unchanged; it shows named native bodies, the *required* clearance and
separate measured self/world distances when available. Focused host pure tests
passed (6 facade, 5 UI); compilation and diff checks passed. This is source
evidence only. The raw command still lacks unique request and policy identity,
so correlation and a supported reconciliation path remain the next part of
closure slice 1. Current-scene runtime, screenshots and Tarun's verdict remain
pending. See the [27 September logbook](../logbook/2026-09-27.md).

**27 September read-only draft diagnostic:** The workbench now has an explicit
Check Draft State action. It passes the captured J1–J5 review vector through
the shared static/endpoint evaluator, retains task and scene identity checks,
and never commands or mirrors the accepted robot. Static validity is separate
from Target position/axis match; a safe off-target pose may pass the static
check. A changed draft or identity marks the result stale/unknown. Focused host
pure checks passed (6 facade, 4 UI) with compilation and scoped diff checks.
The combined two-module host regression subsequently passed 73 tests.
The control still uses the existing reviewed-limit draft range, and the
authoritative static API currently returns text rather than structured named
collision pairs for arbitrary draft failures. Those engineering feedback gaps,
native runtime and operator judgment remain open under closure slices 1–2.

### Required closure sequence within existing gates

These are implementation slices under the original five gates and existing
backlog owners, not a second pending queue. Complete each bounded source slice
with the smallest relevant tests, then reuse it; do not repeatedly rerun the
entire workflow while the same prerequisite is unresolved.

1. **Finish the manual state boundary (gate 3, shared evaluator gate 1).**
   Use separate draft/review, last acknowledged accepted, and monitored states.
   Base exploration must not mutate the accepted base transform or synchronized
   scene until Accept Base; cancellation restores only the review representation.
   Home candidates must not overwrite accepted Home. Route all controls through
   those owners. The explicit read-only Check Draft State action is source-implemented
   for captured J1–J5 on the current accepted Base and scene; finish candidate Base
   review, phase evidence and native collision attribution. Mechanical and
   reviewed limits remain command gates; out-of-envelope review, if supported,
   is visibly invalid and cannot be jogged. J6 is never an arm control.
   Address raw guard attribution before trusting live acceptance: the current
   raw status lacks request ID and policy fingerprint. Correlate request/session,
   exact vector, policy and scene through the existing native protocol; a fresh
   matching vector alone is insufficient evidence for repeated identical requests.
   Retain ambiguous/stale outcomes as unknown, reconcile monitored state and block
   further commands until the accepted state is known. No guessed rollback command.
   **Exit:** pure checks cover no accepted mutation on draft/cancel/reject/unknown,
   stale response, same-vector repeated request, identity change and limit/J6 edges.

2. **Deliver one useful engineer exploration loop (gate 3).**
   Show accepted and review robot together with TCP, drill axis, target trajectory,
   Base/Home labels, joint margins and named collision evidence. Keep invalid poses
   inspectable without accepting them. Let the engineer choose and retain ordered
   waypoints and inspect the connecting motion. Reuse existing goal robot/path
   primitives and the shared evaluator. A valid endpoint does not validate the
   segment to it. Initial live exploration remains explicit individual guarded
   jogs with ordered acknowledgements. Automatically traversing a composed manual
   sequence requires a separately specified simulation segment/phase-guard gate
   before implementation; historical replay never issues commands or promotes a
   planned route. This preserves the engineer's ability to demonstrate intuitive
   motion without silently granting saved paths preview authority.
   **Exit:** requested/accepted/rejected paths are distinguishable; rejected motion
   never draws a continuous accepted segment across the rejection; no planner is
   needed to draft, inspect or perform an individually guarded jog.

3. **Complete durable engineering evidence (gates 1 and 3).**
   Reuse schema 1.0 and extend it only where an actual field is missing. Bind each
   request/outcome to its identity and retain actual native acknowledgement,
   monitored joints, FK TCP/axis, phase, available diagnostics and timing. Check
   that failed identity preparation cannot append a new Base/Home event to an
   older case ledger. Export all selected session records, not just whichever
   current/latest record the accessor returns. Provide readable report plus
   machine-readable samples and display-only reopen/replay. Unknown measurements
   remain unknown; no fabricated clearance/conditioning. Add native metrics through
   the same scene/guard authority, with unit normalization and no invented threshold.
   **Exit:** round trip retains successes, failures, unknowns, transitions and exact
   values; reopened data cannot restore live acceptance or enable preview.

4. **Finish the two-area integration and full-chain boundary (gates 4 and 5).**
   Keep 6.0–6.2 ownership. Merge exploration/task confirmation/manual solver and
   stage diagnostics into Planning & Diagnostics; put preview/Stop/Return under
   Preview & Control in both navigators. Reuse actions rather than duplicate state.
   Complete-chain promotion requires fresh exact stage handoffs, frozen identities
   and the independent complete guard. Exercise stale-input invalidation and the
   interrupted-preview Block Return latch. Recovery, teleport and manual-path
   promotion remain outside this gate.
   **Exit:** both navigators agree on every action/lock reason; partial/historical
   paths cannot enable preview; complete and interrupted paths have explicit states.

5. **Close runtime, responsiveness and operator acceptance (all gates).**
   Prepare the automation lane during source work, then run the focused production
   sequence on a current representative case when its fixture/runtime gate is met.
   Include ROI candidate containment, generation yield/timing, edited ROI display
   and saved/reopened freshness under S6-WORKSPACE-PURPOSE.
   Measure input→visible frame, local FK/MRML/render, native guard/ROS and recording
   separately; 60 FPS is an interaction target, not a guard-rate promise. Fix one
   measured bottleneck at a time in this checkout; do not import the parallel
   upgrade task. Obtain Tarun's visible verdict on exploration, invalid-state
   explanation, manual motion, export/reopen and repeat/Stop behavior. Retain pending
   operator acceptance while he is remote. Case-specific FDI11/21/31 solving,
   planner comparisons, automated base sweeps and robot redesign stay downstream.

### Automation is part of completion

Headless checks are within Codex's capability and relevant to this work. Model
roles are execution policy, not a technical inability of Sol. Reuse the
[script index](TESTING_VERIFICATION_SCRIPT_INDEX_2026-09-24.md),
[verification matrix](../../../Testing/verification_matrix.json) and
[GUI SOP](STEP6_GUI_AUTOMATION_SOP_2026-09-23.md). Existing scripts span preparation,
case save/reopen, views, scene lifecycle, phase guard and Step 6; their existence
is coverage potential, not a current-revision end-to-end pass.

| Check layer | Smallest useful reuse | What it establishes |
|---|---|---|
| Host pure | Existing state/facade/planning/UI/bridge tests | State transitions, identities, records and stubbed UI contracts |
| Headless Slicer/ROS | Existing manual-jog runner; scene lifecycle/phase-guard checks only for changed boundaries | Production Qt/MRML/ROS/native behavior on the frozen fixture; save JSON and screenshots |
| Headed Slicer | Adapt the same production actions to a reviewed real DISPLAY and capture the normal window | Real layout, visibility, event delivery and render timing; script-driven UI checks are possible |
| Operator review | Tarun's representative normal-window exploration | Robotics interpretation, controllability and usability acceptance |

In this Codex session native desktop CUA is disabled. Headed Slicer Python/Qt
scripts and screenshot capture remain technically possible through the configured
runtime. Do not claim generic mouse/keyboard desktop control or infer usability
from an offscreen screenshot. A headed script that calls only facade methods
also does not prove every widget connection; exercise real controls where needed.

Before another runtime, repair the existing harness provenance: its launcher pins
`45a38d9` although the reviewed commit is `40ad290`; the matrix's generic container
command points to `DentoBot`, not this worktree; the shared native install points
to the parallel `DentoBot` build. Record the selected full revision, dirty diff,
Python hashes, native build/source provenance, fixture hash and display mode in
one result manifest. Do not simply remove revision checks or claim matching source
hashes attest a binary. Reuse the runner instead of building another harness.

Tarun deferred more runs on the September 22 saved package after its lineage
failure. Preserve that failure as legacy compatibility evidence. Use pure or
synthetic checks for isolated contracts now; those cannot replace representative
anatomy/native checks. Prepare a newly saved case via the existing production
save/reopen path after substantial source progress. Do not weaken lineage or
spend the remaining renovation on legacy migration. No case is selected or loaded
by this review, and it grants no new runtime/retry authorization.

For the next approved runtime, first gate import/identity, then run the bounded
manual scenarios: valid jog, rejected draft, stale/unknown result, Base/Home
review/accept/cancel, record/export/reopen and action authority. Stop on the first
causal blocker, preserve evidence and observe the retry ceiling. Capture accepted
and invalid-state context and named collision views, exact joints, identity,
timestamp and screenshot paths. If capture fails, record why; never substitute a
synthetic image for runtime evidence. Full planned preview/Stop/Return is a later
check requiring its complete-route prerequisites. GUI results stop for Tarun's
verdict as the canonical contract requires; independent source work may continue.

### Ownership and completion rule

Sol owns reasoning, review, controlled records and acceptance. Exactly two GPT-6
Luna Max workers execute qualifying bounded grunt work in parallel with disjoint
files, no recursive delegation and no controlled-doc edits. Tarun's request that
Luna write and perform tests remains active: use read-only Luna verification on
stable files for host checks. The standing worker restriction excludes GUI/ROS
runtime; a future concrete runtime plan must explicitly assign its sole executor
under the applicable operator authorization. Neither Sol's coordination role nor
a matrix entry automatically authorizes a runtime. Do not silently substitute a
model, silently move tests to Sol, or conflate that role restriction with capability.

Completion means the engineer can inspect a speculative or invalid pose, understand
its attributed limits/contact/axis evidence, build and perform an ordered
sequence of individually guarded jogs, vary Base/Home through explicit acceptance, and retain
and reopen that evidence without unintended state or route authority. The final
UI, full-chain preview boundary, required measurements and operator verdict must
also close. A passing test count alone never closes this plan. No additional
planner algorithm, physics engine, Studio framework, legacy-case campaign or
5.12 upgrade is required to deliver it.
