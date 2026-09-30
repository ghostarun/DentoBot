# Step 6 renovation — working implementation plan

**Date:** 2026-09-25. **Priority:** renovate Step 6 before case-specific planner solving. Owners are S6-WORKSPACE-PURPOSE, S6-LIVE-01, S6-LIVE-03/04 and S6-P2-03. [Backlog](../backlog.md) is the sole pending queue; [TASKS](../TASKS.md) holds task contracts; the [FDI31 P0 contract](FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md) retains its milestone and safety gates. The [base-pose feasibility plan](DENTOBOT_Base_Pose_Feasibility_Explorer_Diagnostic_Plan_2026-09-25.md) is an **active technical reference for shared diagnostic metrics**. Its automated sweep and robot-design comparisons remain later work in the [reference index](STEP6_LATER_WORK_AND_ADJACENT_IDEAS_2026-09-25.md).

## 27 September execution order after the operator's testing review

The 14-item exact-case headed trial has already checked case restore, one
correlated guarded J1 jog, Base stage/cancel/accept and Task Home accept. Do
not repeat that broad sequence after each source edit. Its in-app checklist
passed; the video manifest remains partial because Slicer exited 1 during
shutdown. The result is bounded happy-path evidence, not full workbench or
operator acceptance.

1. Finish the remaining workbench source slices below: inspectable invalid
   drafts, accepted/rejected/unknown state and reconciliation, ordered motion
   evidence/export/reopen, the two-area interface, and full-chain preview
   authority. Use focused pure/source tests for each changed safety boundary;
   use a narrow runtime check only when its behavior cannot be verified at
   source level or when a first causal failure demands it. No automatic
   case-wide GUI replay per slice.
2. Before the final broad headed campaign, prepare a fresh integration branch
   from a reviewed base and **curate only the proven 5.10 integrity and
   performance changes** from `DentoBot-performance-5.12`. Compare each
   candidate against fixes already present in this dirty Step 6 checkout;
   resolve overlaps at their shared owner, preserve case lineage/restore
   guards, and run focused regression checks. Do not merge the mixed
   `upgrade/slicerros2-5.12-performance` branch wholesale or promote its
   deferred 5.12 image/native history. No integration, branch switch,
   commit or push is authorized merely by this planning step.
3. Run one representative integrated headed workflow campaign after source
   completion and curated 5.10 integration: valid and invalid manual review,
   guarded acceptance/rejection/unknown handling, ordered export/reopen,
   two-area UI, full-chain authority and interruption, with state-matched
   screenshots, itemized JSON, logs and video. Treat Slicer shutdown/recording
   completeness as its own `S6-U-01` gate. Measure responsiveness on the
   integrated source. Tarun's normal-window robotics/usability verdict stays
   PENDING until he supplies it.

This sequence avoids spending repeated full-runtime cycles on an unfinished
workbench while retaining mandatory guard, stale-identity, J6 and preview
checks. A passed source test never substitutes for the final native/GUI check.

**27 September execution checkpoint:** The original renovation checkout now
passes 225 combined host tests for the remaining source gates, including
uncertain Base/Home reconciliation, ordered motion evidence, historical
display-only reopen, five-page/two-area ownership, complete-chain preview
authority, legacy bypass closure and a detached Base candidate ghost. These
are source/host results; native visual behavior remains open. A fresh
uncommitted `integration/step6-5.10-reviewed-20260927` worktree contains the
reviewed Step 6 source plus selected 5.10 restore, fingerprint, stage-save
and Connect render changes from the parallel checkout. Its combined host
suite passes 251 tests. The parallel performance checkout and original Step 6
checkout remain intact; no 5.12 image/native history was imported.

The first integrated stack-present case load exited abnormally during UI
refresh. A discriminating offline reopen passed; the next serialized narrow
run reopened the unchanged current FDI11 case, acknowledged 31 collision
objects, captured two state-matched Connect screenshots, and completed
Disconnect. Slicer still exited 1 during shutdown. Treat the functional
Connect/Disconnect result and process-exit failure separately under
`S6-P2-03` and `S6-U-01`. The current reviewed FDI11 package has no
confirmed task, so it cannot establish positive complete-chain preview.
The representative full-run recording, invalid/unknown GUI states, historical
visual replay, interruption, responsiveness, and Tarun's normal-window
verdict remain open. Next: diagnose shutdown without a blind retry, secure a
current reviewed confirmed-task fixture for the positive-chain gate, then
run one complete recorded campaign with exact source/native/case provenance.

**28 September campaign preparation:** The existing 14-item headed runner now
has an explicit exact-checkout integration mode and a read-only taskless-draft
checkpoint in the reviewed integration worktree. A separate run-local
diagnostics helper refuses to call that bounded runner whole-run complete:
completion requires a runner's substantiated `full_workflow_claimed` result,
all applicable checklist items passing, a complete hashed video with zero
exits, matching screenshots, and an outer-wrapper cleanup attestation from
exact owned-process checks. The three focused host test files pass 33 tests
and four subtests. **The final full-campaign runner is not yet implemented.**
Its next source gate must add the valid/invalid, reject/unknown/reconcile,
record/export/reopen, two-area, positive full-chain/interruption and
responsiveness items without reusing the bounded runner's `PARTIAL` status as
success. Use a strictly validated current confirmed-task fixture for positive
route authority; no task or trajectory may be invented to make the checklist
green. Keep S6-U-01 shutdown evidence separate from checklist outcomes.

**Further 28 September source slice:** The bounded runner has an opt-in
current-limit invalid-draft visual check; it stops safely if the displayed
reviewed/mechanical bounds have no representable gap. A separate host-tested
historical-record probe can call production export/import/event stepping and
check accepted J1–J5 and route/preview invariance, but it is not yet joined
to a whole-run Slicer runner. The focused four-file host suite passes 43
tests and four subtests. A genuine native guard rejection or unknown-after-
submit cannot be promised by the current fixture/UI; injected host tests
remain labelled source evidence, and a natural unknown must latch and stop
further motion until explicit reconciliation. The positive full-chain path
still needs a strictly current confirmed task and actual complete guard
preflight. These source checks do not replace that runtime evidence.

**28 September bounded headed result:** The historical probe is now opt-in
after an accepted jog in the reviewed integration runner. One initial
recorded attempt stopped at a runner substep mapping error; after correction
and 50 focused tests plus four subtests, a fresh attempt passed invalid
reviewed-limit inspection, native scene readback, an accepted J1 jog,
event-bearing export/reopen/display-only step, and Base stage/cancel.
The unchanged taskless FDI11 case supplied no positive full-chain fixture.
Base/Home acceptance was deliberately not repeated; the prior 14-item
happy-path evidence remains the bounded acceptance source. Both new videos
are partial because the Slicer process exited 1; the second shows native
class-loader warnings under `S6-U-01`. Next source/runtime work should use
the current strict case and exact native provenance, resolve shutdown as a
separate condition, establish a reviewed confirmed-task complete route,
then run the final full checklist once. Do not infer operator verdict.

**28 September fixture and layout follow-up:** Read-only `SEPT24` package
inventory found one older confirmed-task case, but its selected branch was
saved Stale with a Step 4C freshness issue; the other two have no confirmed
task. The older task is not a current-chain substitute. A two-worker source
slice split the oversized Manual Jog action row and made screenshot framing
report actual viewport/scroll geometry. The focused combined host suite
passed 80 tests and four subtests. Treat headed visual/responsiveness and
the positive preview/interruption fixture as open; do not repeat the same
shutdown failure without a causal change under the retry ceiling.

**Invalid-draft source continuation:** `checkManualRobotDraftState` now
reports current mechanical/reviewed-limit violations before static/FK work;
numeric J1–J5 drafts within mechanical bounds can remain visible outside a
narrower reviewed range, with Guarded Jog disabled and Check Draft State
available. The combined façade/UI host suite passed 114 tests, compilation
and diff checks passed. This is source/host verification only; the final
integrated GUI campaign must show the invalid candidate, explanation and
unchanged accepted robot. It does not reopen the already passed Base/Home
happy-path trial.

**Recording source continuation:** Failed preparation of the current manual
identity now freezes the prior event-bearing ledger before a Base/Home action
can record under an older case. A successful live acceptance still reports
recording unavailable if its new identity could not be established. Export
now includes every completed session in order plus a distinct active record,
validates each schema-1.0 fingerprint, and writes a machine JSON array with a
readable companion report. The combined façade/UI host suite passed 120 tests,
compilation and diff checks passed. Complete per-sample TCP/axis/native
diagnostics, historical reopen/replay, uncertain Base commit reconciliation
and representative GUI verification remain open. No full-case GUI replay was
run for this slice.

**Uncertain Base reconciliation source continuation:** An explicit Reconcile
Base State action now re-synchronizes the restored accepted baseline through
the existing simulation PlanningScene owner, requires a fresh acknowledged
audit with matching Base fingerprint and complete unique collision-object
IDs, then checks unchanged case/review/Base identity before clearing the
uncertainty latch. Candidate and failure evidence remain staged; reconciliation
does not accept the candidate. Unknown acceptance blocks cancel and restage.
The combined façade/UI host suite passed 128 tests, compilation and diff
checks passed. Native scene behavior, uncertain Task Home reconciliation and
the final representative GUI verdict remain open.

**Uncertain Task Home reconciliation source continuation:** A saved Home whose
owner result was ambiguous remains latched until explicit read-only proof of
the expected new revision, candidate J1–J5, current Base/profile/strict guard
and acknowledged scene. A unique request/session/policy native state query,
exact object IDs/count, fresh ROS monitored joints and displayed joints must
agree under unchanged identity before the bridge reflects the verified state.
The action does not issue a second Home save or jog; unproved results retain
the candidate, unknown latch and failure evidence. The explicit UI control
disables repeat Accept/Cancel while unknown. Two disjoint Luna Max source
workers' combined facade/UI host suite passed 132 tests, compilation and diff
check passed. The native query exposes the manual policy ID, but no comparable
collision-policy fingerprint; the saved Home's strict guard fingerprint and
current audit are checked separately. This remains source/host evidence;
live uncertain-commit behavior, complete motion records/reopen, two-area UI,
full-chain authority and the final recorded campaign remain open.

**Ordered motion evidence source continuation:** Optional schema-1.0 fields
retain monitored J1–J5, finite world-RAS TCP pose/point and normalized
drill-axis samples without invalidating old records. The jog recorder keeps
requested then outcome order and actual native guard, collision/clearance,
identity and monitoring facts. It computes FK only under unchanged exact
identity and Base matrix. Accepted geometry belongs to correlated accepted
jogs; rejected candidate geometry is explicitly labeled and cannot bridge an
accepted path; unknown or missing FK stays unavailable. Two Luna Max workers
owned disjoint schema/test and facade/test files. Combined host suite passed
186 tests, compilation and diff check passed. Visible path rendering,
historical display-only reopen/replay, native samples and final GUI evidence
remain open.

**Historical reopen/replay source continuation:** A bounded JSON open action
validates every schema-1.0 fingerprint before loading. The UI shows imported
identity and a selectable ordered event list with monotonic elapsed times,
requested/accepted/rejected/diagnostic status and preserved unknowns. Prev/Next
steps historical evidence only. The transient bridge renderer reparses the
record, draws accepted TCP runs with barriers at rejection/unknown, and uses
distinct candidate markers where TCP points exist. It owns only historical
MRML nodes, excluded from scene save, and does not touch phase paths, ROS,
robot joints, Home, route or preview. Import is capped at 16 MiB, 100 records
and 10,000 events for this synchronous viewer. The two disjoint Luna Max
workers' stable combined host suite passed 194 tests, compilation and diff
check passed. Headed visual behavior remains unverified; two-area integration,
full-chain authority and final recording are next.

**Two-area/full-chain source continuation:** Both navigators use shared titles
Planning & Diagnostics and Preview & Control at existing indices 5/6. The
former reuses Home review, workspace/limits, confirmation, manual solver and
stage diagnostics; the latter owns one canonical Preview/Stop/guarded Return
control group. Apply Task Home remains visible only at its 6.2 owner.
Blocked Stage 2/3 candidate plans remain display-only result payloads and
path models with `_motion_plan=None`. Approach preview requires the exact
complete Home→PreEntry→Entry→Target preflight, bound orientation/task/plan and
current independent guard validation status/session/policy. Drill preview
requires its plan to be derived from that current preflight. Interrupted
Block Return remains latched. Two disjoint Luna Max workers' stable
state/facade/UI/application-shell/path host suite passed 219 tests, Python
compilation and diff check passed. This is source/host verification only;
representative native preview/interruption and responsiveness remain open.

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
| Base/Home | Base now has a detached numeric candidate, stage/cancel, stale-identity checks and explicit Accept through the existing pose/lock owners; Home still uses the live save owner | Native/visual Base review and uncertain-commit reconciliation; detached Home candidate; full invalidation integration |
| Recording | Schema 1.0, in-session events and current/latest JSON export | Complete motion/diagnostic samples, session selection, path display, historical reopen/replay and readable report |
| Presentation/performance | Controls added to old cards; existing preview machinery retained | Two-area migration in both navigators and measured local interaction |
| Preview interruption | Source latch retains incomplete-prefix evidence and blocks Return | Runtime Stop/reject/repeat verification and operator verdict |

**Later 27 September Base/Home runtime result:** The exact reviewed current
case, isolated native guard and a fresh headed Slicer session passed all 14
bounded checklist items, including one correlated J1 jog, detached Base
stage/cancel, zero-displacement Accept Base with acknowledged scene resync,
and review/accept of the current J1–J5 pose as runtime-validated Task Home
revision 13→14. The Home commit is inferred from fresh accepted/current/
not-staged façade status and the advanced validated record; the transient
accept-call return was not captured. Accepted, monitored, displayed and saved
J1–J5 matched; source case hash was unchanged, and no route/preview authority
was granted. The first opt-in run failed a runner check that wrongly required
the transient return in a later status read; two Luna Max source/test workers
corrected it, and focused host checks passed 23 tests before the second run.
Both runs' whole-process videos remain `partial` because Slicer exited 1
during shutdown, despite the second in-app checklist PASS. See the
[successful checklist's run-local report](/home/light-tarun/dentobot/data/dentobot-runs/s6-live-01-base-home-accept-20260927T131832Z-r2/diagnostics.md).
This closes only the bounded happy-path Base/Home runtime slice for this
case. Continue the existing closure sequence with uncertain-commit and
invalid-state handling, complete motion records/export/reopen, two-area/
full-chain integration, responsiveness and operator review. `S6-U-01` owns
the independent shutdown defect. Tarun's normal-window verdict is PENDING.

**27 September headed execution update:** The original-case restore and
taskless manual static review now pass in a fresh headed Slicer session. A
paired native/Python fix restored exact double echo of manual J1–J5 status;
a paired UI fix restored radian-to-degree accepted-state mirroring. On the
unchanged reviewed September 27 case, the bounded runner passed exact
checkout/native/case provenance, 31-object scene readback, static/FK draft,
one correlated native-accepted J1 +0.1° jog with later accepted/monitored/
displayed match, and detached Base stage/cancel without accepted-Base change.
The runner's JSON says PASS, but Slicer returned 1 during shutdown and the
whole-process video manifest remains `partial`; retain both facts. Earlier
unknown and crash recordings are linked from the
[dated logbook](../logbook/2026-09-27.md). This is a bounded manual-motion
source/runtime gate, not a full workbench acceptance, confirmed task, Base or
Home acceptance, planner route, preview or operator verdict **at that earlier
checkpoint**. The later dated Base/Home update above supersedes the first two
acceptance items. Continue gate 3 with uncertain-commit reconciliation, then
gate 4 invalid
states and recording/export/reopen, before two-area/full-chain completion.

**Detached Home source continuation:** Stage/cancel/accept now use a separate
J1–J5 candidate under frozen current manual identity; staging never promotes
saved Home or robot state. Accept requires candidate agreement with guard-
accepted, monitored and displayed joints within `1e-12` SI, then delegates to
the existing live `saveTaskHome()` owner. Unknown post-save outcomes retain
the candidate and failure evidence, block another accept/cancel and need a
separate reconciliation gate. The UI distinguishes accepted robot, candidate
and saved Home. The five-file integration host suite passed 166 tests;
compilation, matrix parsing and `git diff --check` passed. The later dated
headed update above records the bounded runtime/visual Home acceptance; no
complete-route authority was added.

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
  labels did not establish detached review or per-edit Base history at that
  baseline. The 27 September numeric Base source slice addresses Step 6 direct
  nudge/reset/selector editing, but does not yet provide a candidate ghost or
  runtime proof of the lock/scene transaction.
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

**27 September manual acknowledgement source gate:** A dedicated simulation-only
manual command/status pair now carries unique request and facade-session IDs,
the actual ordinary PlanningScene ACM transition policy ID, J1–J5 and native
scene/guard evidence. The bridge accepts only the matching one-shot reply;
uncertain or inconsistent replies leave the compatibility stream paused and
the last confirmed app state intact. The native raw array and phase-aware task
protocols retain separate meanings. A combined 106-test host pure check passed.
Native C++ compilation, current-case ROS/Slicer behavior, monitored-state
reconciliation and Tarun's visible verdict remain open. This source result
does not make the live manual jog accepted.

**27 September reconciliation retry:** A read-only native `state_query` and
explicit Reconcile State action are now source-implemented. The query reports
the native accepted vector, static validity and world evidence without a
motion publish. The façade retains the uncertain jog's frozen identity and
clears its latch only after request/session/policy/echo, scene objects and
fresh ROS monitored state agree; the UI preserves the draft. Missing operation
is rejected before motion. The combined host pure suite passed 118 tests.
The earlier quota-interrupted half-gate is superseded at **source** level.
Native C++ build, current-case runtime exchange, screenshots and Tarun's
visible verdict remain pending; detached Base/Home review is still open.

### Required closure sequence within existing gates

These are implementation slices under the original five gates and existing
backlog owners, not a second pending queue. Complete each bounded source slice
with the smallest relevant tests, then reuse it; do not repeatedly rerun the
entire workflow while the same prerequisite is unresolved.

1. **Finish the manual state boundary (gate 3, shared evaluator gate 1).**
   Use separate draft/review, last acknowledged accepted, and monitored states.
   Base exploration must not mutate the accepted base transform or synchronized
   scene until Accept Base; cancellation restores only the review representation.
   The detached numeric Base source path is implemented; verify its actual Qt
   routing and native lock/scene outcome in the deferred runtime gate. An
   uncertain commit remains latched and requires an explicit reconciliation
   design before another Base acceptance. Add a visual candidate ghost only
   when it can remain genuinely detached from the accepted robot/ROS scene.
   Home candidates must not overwrite accepted Home. Route all controls through
   those owners. The explicit read-only Check Draft State action is source-implemented
   for captured J1–J5 on the current accepted Base and scene; finish candidate Base
   review, phase evidence and native collision attribution. Mechanical and
   reviewed limits remain command gates; out-of-envelope review, if supported,
   is visibly invalid and cannot be jogged. J6 is never an arm control.
   The dedicated manual status now has request/session and actual raw policy
   identity at source level; verify it in the native runtime before trusting
   live acceptance. Correlate request/session,
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

**2026-09-27 execution update:** Tarun subsequently authorized one recorded
headed simulation checklist. The newer `sept27_fdi11_step6.dentocase` passed
source/native provenance but initially failed strict post-hydration final
template validation; its first partial video remains failure evidence. A
restore-time UI mutation fix and post-audit landmark roundoff correction now
reopen the unchanged case in fresh Slicer with Case Foundation pose, Base and
PreparedBranch `VALID`; 21 focused host tests passed. This preserves package
validation and does not assert current task-limit identity: saved and rebuilt
limits fingerprints differ. A second recorded run opened the case and captured
UI/viewport screenshots, then stopped at disabled Connect because the runner
had not loaded the local robot or imported planning context through production
controls. Its 37.676-second video, manifest, itemized results and screenshot
limitations are in a second run-local diagnostics file. Both runs submitted no
jog. Finish the production prerequisite and screenshot-framing source checks,
then resume one serialized recorded trial. The broader manual solver, full
workflow recording and operator verdict remain pending.

**Later 27 September execution boundary and next source gate:** The headed
runner now loads the local robot, imports the same eligible PreparedBranch,
connects simulation ROS and reads back all 31 case objects. A cross-layer J2
representation correction passed host checks and the next recorded run. The
production Check Draft State stopped before its static query because this
newer case has no confirmed task. Its existing Task Home is unvalidated in
the fresh runtime. Manual state exploration must be useful before task
confirmation: permit task-independent static review and guarded raw jog only
under a frozen current branch/Base/limits/profile/scene/ROS identity; a saved
Home may be absent or stale but is marked unconfirmed and grants no authority;
keep task endpoint/Target residual `not_reached` and preserve all native
request/session/policy/vector/object-ID acknowledgement checks. A task becoming
confirmed invalidates the task-independent identity. Do not choose a new Home
or confirm a target merely for the recorded test. After focused source checks,
repeat one serialized recorded run and stop on its first new causal result.
The partial run and screenshot index are in the 27 September logbook.

The earlier next-runtime list is superseded by the 14-item headed Base/Home
result above and the execution order at the top of this plan. Valid jog and
Base/Home happy-path review/accept have bounded current-case evidence; do not
repeat them per edit. Remaining rejected/unknown drafts, uncertain commit,
record/export/reopen, action authority and full preview/Stop/Return should
first get focused source checks and then join the final representative
integrated GUI campaign, with a narrow native run only for an unresolved
safety boundary. Stop on a first causal blocker, preserve evidence and observe
the retry ceiling. Capture accepted and invalid-state context, named collision
views, exact joints, identity, timestamp and screenshot paths; never replace
missing runtime evidence with a synthetic image. GUI results stop for Tarun's
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
