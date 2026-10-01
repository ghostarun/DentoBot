# Step 6 renovation — working implementation plan

## 1 October — joint-editor UX revision: All joints visible iteration1 selected

**Current operator supersession:** Tarun selects All joints visible iteration1 and
requests implementation. The design-selection hold in the original proposal below
is superseded for source implementation and its focused host checks. Rendered
Slicer/ROS acceptance remains separate; see the implementation authorization record.

**Operator observation:** Tarun says the revamped joint-slider fix still looks ugly
and requests proper UI/UX planning before the next implementation. This is a
negative usability verdict for the existing spacing correction, not evidence of
a new numeric/ROS failure. Owner remains `S6-LIVE-01` Priority 0; broad GUI/Studio
redesign remains deferred. Current target is the consolidated integration checkout.
No production implementation or Slicer/ROS/build execution is authorized by this
design request. The revised rendered GUI has not been supplied in this turn;
source findings explain a concrete layout defect but do not establish its exact
appearance in Tarun's latest window.

### Source finding and intended outcome

Construction creates short J1–J5/unit labels, but `setManualJogLimits` later
replaces those labels with long mechanical/slider/command/reviewed-limit paragraphs.
The fixed-height, word-wrapped identity column therefore carries information it
cannot present reliably. The prior size-policy patch did not address that refresh
path. Draft values are additionally repeated in summary text while accepted values
are separated from the controls. One existing editor is reparented between Home
and manual-jog groups by `widget_robot_shell.py`; preserve that ownership.

Outcome: identify each joint instantly, adjust a precise draft while watching the
viewport, see how it differs from the accepted robot, and understand the next
allowed action without searching large paragraphs or scrolling among five joints.

### Recommended proposal: all five joints visible

Use five quiet, aligned two-line rows in fixed J1–J5 order. Each first line contains
a permanent short ID/unit, accepted comparison and right-aligned editable numeric
value. The second contains a horizontal slider with concise lower/upper range
labels. J1/J3/J5 use angular units; J2/J4 use mm. Numeric entry and native spinbox
arrows provide precise adjustment; slider dragging provides coarse exploration.
No extra per-row reset/nudge/tool button is proposed. Keep one Reset Draft action.

At wider widths, accepted value and signed delta appear inline. At narrow widths,
the comparison moves to a short secondary line; ID and value remain visible.
Prefer this to a dense multi-column table or horizontal scrolling. Initial targets
for desktop review are 360/480/640 logical-pixel panel widths and approximately
300–380 logical pixels for the five-row editor at normal font scale. These are
layout review targets, not fixed height caps; native style/font size hints and
accessibility enlargement take precedence. Put excess vertical stretch after the
editor, never between joint rows. Avoid nested frames and decorative colors.

The alternative precision-table proposal shows all five numeric drafts and accepted
values with one slider for a selected joint. It is denser, but adds joint selection
before dragging and weakens simultaneous spatial adjustment. Keep it as a design
comparison, not a second runtime mode or a new setting. Recommended choice is the
all-joints layout unless Tarun prefers the table after visual review.

### State, limits and interaction contract

- Keep short ID/unit labels unchanged through all refreshes. Show active slider
  endpoint values below the track. Expose mechanical bounds and reviewed limits
  distinctly in a collapsed Limits and state details area, plus accessible
  tooltips. Essential blocking reasons stay visible beside the editor/action.
- Label the editable state Draft. Comparison uses the existing accepted-state
  source, never the display ghost or unacknowledged observed state. If accepted
  state is unavailable/stale, say so and omit delta; do not synthesize zero values.
  Do not imply that Home configuration equals current accepted robot state.
- Preserve existing range policy: offline Home sliders use mechanical ranges;
  connected sliders use their current allowed range; numeric drafts retain their
  existing mechanical range. A numeric draft outside the slider/guard range must
  remain numerically visible with an explicit warning; a saturated slider must
  not make it look equivalent to its endpoint. Do not silently clamp it or expand
  reviewed limits. Do not introduce wrapping or reinterpret continuous J5 bounds.
- Editing remains display-only. Draft changes invalidate prior review/guard results
  through existing handlers. Mechanical/task-limit status is distinct from native
  collision validation. Short status example: Draft edited; not guard checked.
- No automatic request on slider release, numeric Enter, focus loss or keyboard
  nudge. Preserve existing explicit Check Draft State, Guarded Jog, Home review,
  save/accept, uncertainty/reconcile and Plan + Apply actions and eligibility.
- Give Home and manual-jog contexts appropriate editor titles. Home shows the
  offline configuration/save or connected review/validation actions; manual mode
  shows static Check Draft State and explicit Guarded Jog. Keep movement-producing
  Plan + Apply visually separate from configuration actions. Reuse the same editor
  and state; do not duplicate widgets, signals, ROS adapters or parameter state.
- Keep one concise state/recovery line above the action group. Longer explanations,
  limit inventories and request diagnostics are expandable. Unknown/stale/busy
  states retain their blocking reason and reconciliation path. Color supplements
  text; it does not imply safety or replace a verdict.
- Preserve keyboard focus, native Tab/arrow entry and opt-in global nudge scope;
  wheel scrolling must not unintentionally edit an unfocused joint. Any change to
  input commit timing, keyboard tracking or preview-update cadence is a separate
  behavior/performance scope, not part of this layout revision.

### Implementation and acceptance boundary

After design selection, implement the smallest native Qt presentation change in
`DENTORobotSimulationPanel.py`, including construction and dynamic refreshes. Touch
`widget_robot_shell.py` only if contextual title/reparent presentation needs it;
retain public control dictionaries, callbacks and exact SI conversion. Existing
facade/ROS/native/geometry/planner/persistence policy is out of scope. No custom
widget framework, new dependencies, graphics theme overhaul or robot-diagram
feature is needed. For qualifying implementation use the operator's two disjoint
Luna Max scopes (presentation source; existing UI regression assertions); the
coordinator owns design, actual diff review, documentation and acceptance. No
checks against files still being edited.

Verification question: does the stable compact editor survive current-state/limit
refreshes and Home/manual reparenting while preserving draft-only behavior?
Use the matrix's `pure.step6_manual_tcp_workbench` host selection after confirming its current
ID/command, with regressions covering short labels after limits refresh, unit/value
agreement, preserved drafts and no implicit command. Then, only under separately
bounded runtime scope, inspect actual Qt rendering at narrow/default/wide widths,
large-font scale, offline Home and connected/manual modes, unavailable/busy/stale
states and an out-of-reviewed-range numeric draft. Do not run a planner or motion
trial to verify layout. Stop on the first demonstrable GUI success/failure for
Tarun's verdict. A mockup or host pass does not accept the rendered Slicer UI.

The inline alternatives are illustrative design previews using screenshot example
values and schematic tracks; they are not runtime evidence or verified joint limits.
Design selection remains open; no production change is made in this planning pass.

**Date:** 2026-09-25. **Priority:** renovate Step 6 before case-specific planner solving. Owners are S6-WORKSPACE-PURPOSE, S6-LIVE-01, S6-LIVE-03/04 and S6-P2-03. [Backlog](../backlog.md) is the sole pending queue; [TASKS](../TASKS.md) holds task contracts; the [FDI31 P0 contract](FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md) retains its milestone and safety gates. The [base-pose feasibility plan](DENTOBOT_Base_Pose_Feasibility_Explorer_Diagnostic_Plan_2026-09-25.md) is an **active technical reference for shared diagnostic metrics**. The 30 September DENTO-NOTE below adds a conditional ±20 mm translation diagnostic after IK failure; broader automated sweeps and robot-design comparisons remain later work in the [reference index](STEP6_LATER_WORK_AND_ADJACENT_IDEAS_2026-09-25.md).

**29 September execution checkpoint:** Tarun explicitly resumed bounded
simulation runtime. A new recorded headed production run passed the case
migration and 21 enabled Step 6 checks, then saved the current five-DOF FDI11
case. A separate fresh-process read-only run strictly reopened it and passed
12 saved/offline checks; both videos and normal exits are complete. Saved
Task Home is five joints and `Validated` in lineage, but offline reopen
intentionally clears active task confirmation and changes Home to
`Unreviewed`. Reconnect, revalidate Home and confirm the task before any
new planner/preview authority. The case-bound native rejection remains
unrun, while controlled unknown/reconciliation passed. Joint keyboard
source/host checks and the r19 recorded physical J1–J5 draft-only key gate
passed; case-bound TCP interaction,
responsiveness at normal-window size, historical record persistence and
positive full-chain preview/interruption remain pending. The [detailed
five-DOF checklist](STEP6_FIVE_DOF_DETAILED_ACCEPTANCE_CHECKLIST_2026-09-28.md)
is the current execution order; older checkpoints below are dated evidence,
not current halt instructions. Tarun's robotics/usability verdict is PENDING.

## 27 September execution order after the operator's testing review

**30 September DENTO-NOTE — conditional bounded base-placement diagnostic (`S6-LIVE-01`):** Tarun requests iterative translation around the existing forehead-plane-center Base placement if planner testing fails due to IK unreachability: offsets up to ±20 mm on each of two in-plane axes only. His “XY” denotes an oblique anatomical plane parallel to the upper-teeth root↔crown direction, not an assumed world-RAS XY plane. Triage: planned conditional investigation under the existing planner/base-feasibility contract; the note itself is Unprioritized and does not change the parent Priority0. It supersedes blanket deferral only for this bounded failure-triggered diagnostic; broader sweeps, orientation search, heatmaps and robot redesign remain deferred. Prerequisites: complete the current workbench gate, capture exact current-task IK failure, and establish a reviewed plane origin/orthonormal basis and sampling budget. Root↔crown direction alone does not uniquely define a plane; do not invent its second axis or equate it to the forehead plane without review. Keep Base orientation and normal offset fixed, retain the zero-offset baseline, and freeze anatomy, task/TCP, limits and collision/phase policy. Reuse the shared five-joint evaluator, preserve each candidate transform, requested endpoint, IK/FK residuals, limit/collision evidence and identity in diagnostic records/screenshots. Candidates remain detached/display-only; no automatic Base acceptance, Home reuse, route promotion or preview. A selected candidate requires normal explicit Base review/acceptance, scene acknowledgement, fresh Home/workspace/task checks and full-chain guard before motion authority. No successful IK result or infeasibility proof is implied by this note; empty bounded search remains inconclusive beyond its evaluated coverage.

**30 September debugger continuation:** The operator-approved r15 workspace-only GDB trial passed strict restore and current workspace validation with inferior exit 0 and a validated 348.9 s recording. The intermittent native SIGSEGV is not declared fixed. Continue through the focused case-bound workbench gate before the complete planner/preview campaign; stop and retain diagnostics at the first causal failure. The detailed five-DOF checklist remains the execution plan. R15 diagnostics document its original report-finalizer limitation; the subsequent source correction passes 67 focused host tests. No commit or push is authorized.

The 14-item exact-case headed trial has already checked case restore, one
correlated guarded J1 jog, Base stage/cancel/accept and Task Home accept. Do
not repeat that broad sequence after each source edit. Its in-app checklist
passed; the video manifest remains partial because Slicer exited 1 during
shutdown. The result is bounded happy-path evidence, not full workbench or
operator acceptance.

**28 September operator-case checkpoint:** Tarun's saved Sep28 FDI11 package
exposed a closed-source segmentation displayed beside the current opened
proxies, already serialized that way in the preceding Sep27 package. The
shared opened-view normalizer now runs at final scene-save and active-view
refresh boundaries. A narrow headed open, separate save and reopen passed
source-hidden/opened-proxy-visible readbacks and screenshots on the unchanged
operator case. A serialized replay of the bounded 16-item Step 6 GUI runner
also passed invalid draft, acknowledged J1 jog, historical export/reopen,
Base and current-pose Task Home acceptance. This is **not** the final full
campaign: no native rejected/unknown event, direct real-time TCP dragging,
confirmed-task full-chain preview/interruption or measured responsiveness was
proved. The video remains partial on the repeated `S6-U-01` non-clean Slicer
shutdown. Stop unchanged full-case shutdown retries at the recorded ceiling;
fix the teardown path before a complete recording attempt. Tarun's normal-
window robotics/usability verdict remains PENDING.

**28 September Cartesian TCP workbench checkpoint:** 6.3B now presents a
separate Cartesian TCP Exploration area alongside the existing J1–J5 joint
controls. The native MoveIt probe/viewport handles are default-off and can be
created only by an explicit **Enable TCP Drag** toggle after synchronous native
acknowledgement; failed enable reverts off, and disable or leaving 6.3 removes
the probe, goal robot and observer. Mouse drag, buttons and opt-in keyboard
shortcuts review X/Y/Z plus drill-axis pitch/yaw through the canonical J1–J5
position-axis IK; axial tool roll is explicitly unconstrained because J6 is
excluded. Live interaction is kinematic ghost review. Only explicit
collision-aware **Solve IK** can stage an exact finite J1–J5 draft, and only a
later Guarded Jog acknowledgement can advance accepted simulated state. The
focused four-file host suite passed 238 tests. A no-case headed run proved
default-off, acknowledged enable, mouse dragging, translation/orientation
nudge, authoritative solve and draft staging, unchanged accepted state,
disable cleanup, zero route/preview authority, Slicer exit 0 and owned-process
cleanup. Its complete recording and evidence package are in
`data/dentobot-runs/step6-tcp-workbench-headed-20260928-9/`. Physical keyboard
events, a case-bound guarded accepted/rejected/unknown sequence, normal-window
responsiveness/usability and positive full-chain preview/interruption remain
open; Tarun's verdict remains PENDING.

**28 September five-DOF model refactor — source/build/runtime verified:** Tarun directed
that J6 cease to exist anywhere in the current robotics workflow. Commit
`84234a6` checkpoints the preceding renovation before this change. Supersede
the old visual/saved six-slot compatibility policy: the arm has exactly five
movable joints, J1–J5. Convert the burr attachment's former spindle revolute
joint to a fixed joint at the exact neutral transform, while retaining spindle
housing/burr meshes, collisions and the canonical fixed planning TCP. Remove
sixth-joint fields and logic from state, Home, limits, sampling, FK/IK, guard,
joint publishers, serialization, UI and current tests. New robot evidence is
strictly five-joint; historical six-value evidence is not silently promoted.
Describe axial roll positively as unconstrained by the five-DOF arm. Treat the
drill as a separate future speed-controlled device and do not invent an RPM,
pressure or hardware command in this source gate.

The acceptance ladder is complete for this bounded refactor: static audit;
exact five-joint URDF with unchanged neutral geometry/TCP; 394 focused host
tests and Python/JSON/XML/YAML checks; isolated builds of both changed ROS
packages; and one serialized simulation-only runtime proving exact J1–J5
through robot load, guard, joint-state publication, static validity, TCP TF and
five-joint IK. The generic six-dimensional fixed-orientation Cartesian
diagnostic remains unsupported and is recorded as such; Step 6 uses its
separate position-plus-drill-axis continuity path. Case restore and
normal-window operator review use a newly saved five-DOF case later; older
six-value cases are not acceptance fixtures.

The latest implementation and execution plan for creating that new case and
running the automated headed GUI simulation campaign is the
[detailed five-DOF acceptance checklist](STEP6_FIVE_DOF_DETAILED_ACCEPTANCE_CHECKLIST_2026-09-28.md).
It governs current campaign sequencing under `S6-LIVE-01`, not a second task queue. Its
planned fixture path is
`data/Slicer_Saved/SampleStudy1/SEPT24/sept28_fdi11_step6_five_dof_acceptance.dentocase`;
the fixture remains PENDING until it is saved through the current workflow and
qualified by a fresh-process reopen.

For this campaign, Tarun raised the task-specific worker cap from two to four
simultaneous GPT-6 Luna Max workers. Sol still owns reasoning, controlled
records, integration, serialized runtime and acceptance. Use only the number
needed for independent disjoint implementation/host-test scopes; Luna workers
do not own GUI/ROS/runtime. The current platform has four total concurrency
slots including Sol, so the effective concurrent worker count in this session
is at most three beside Sol, with any fourth worker used sequentially.

1. Finish the remaining workbench source slices below: inspectable invalid
   drafts, accepted/rejected/unknown state and reconciliation, ordered motion
   evidence/export/reopen, the two-area interface, and full-chain preview
   authority. Use focused pure/source tests for each changed safety boundary;
   use a narrow runtime check only when its behavior cannot be verified at
   source level or when a first causal failure demands it. No automatic
   case-wide GUI replay per slice.
2. **Latest operator order, 28 September:** finish the Step 6 renovation in
   this checkout before starting integration-branch work. Do not inspect,
   curate or merge the parallel performance/5.12 checkout while the remaining
   Step 6 source/runtime gates below are open. Preserve the already recorded
   integration worktree as historical unaccepted evidence only.
3. After Step 6 source completion and its checkout-specific gates, separately
   review whether a fresh integration branch is still needed and curate only
   proven relevant 5.10 integrity/performance changes. Then run one
   representative integrated headed workflow campaign: valid and invalid manual review,
   guarded acceptance/rejection/unknown handling, ordered export/reopen,
   two-area UI, full-chain authority and interruption, with state-matched
   screenshots, itemized JSON, logs and video. Treat Slicer shutdown/recording
   completeness as its own `S6-U-01` gate. Measure responsiveness on the
   integrated source. Tarun's normal-window robotics/usability verdict stays
   PENDING until he supplies it.

This sequence avoids spending repeated full-runtime cycles on an unfinished
workbench while retaining mandatory guard, stale-identity, exact five-joint
shape and preview checks. A passed source test never substitutes for the final
native/GUI check.

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

**28 September shutdown correction limit:** A detached installed-era 5.10
publisher-release port built, and normal widget cleanup now calls the existing
robot disconnect and adapter shutdown. Tarun approved an instrumented no-case
run which proved both cleanup paths complete but still exited 1 with exactly
two class-loader warnings and no captured fatal signal. Robot-local MoveIt
resource release alone also rebuilt and reproduced the failure once. That run
showed scripted cleanup occurs after ROS2 module de-instantiation; native source
then showed the module logic destroyed ROS nodes before removing its owned
robot nodes. The isolated source now removes every logic-owned robot before
subscription, publisher, ROS-node and ROS shutdown. Its two source-contract
tests and compile pass, but no further Slicer run is allowed in this correction
cycle. The partial whole-run video and final native ordering fix remain runtime
unaccepted. Next acceptance is one separately bounded no-case zero-exit check,
then one final recorded campaign only after the narrow lifecycle passes.

**28 September narrow shutdown acceptance:** The separately authorized headed
connected-robot lifecycle passed on the final isolated 5.10 build. Slicer,
recorder and FFmpeg exited 0; no class-loader warning, fatal signal or owned
process remained. The 26.033-second 1600×900 recording and matching screenshot
are retained under `s6-u01-final-headed-20260928-0hCREB`. Treat `S6-U-01` as
closed for this reproduced no-case condition. The final case-bearing Step 6
campaign still has to demonstrate its own clean shutdown and complete workflow;
the narrow pass does not accept planner, preview, responsiveness or operator
usability.

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

Both navigators must share the same action ownership and locked-action reasons. 6.3 merges the old workspace, task-confirmation and planning cards; 6.4 owns preview and control. Accept Base and Accept Task Home delegate to 6.1/6.2 owners even when initiated from the workbench. The arm-planning display and every current robot-state interface contain exactly J1–J5; drill speed belongs to a separate future device contract.

### What the engineering workbench must actually do

This is an **interactive robot simulation solver** for an engineer to discover feasible motion by direct trial and error. It is not a static ghost viewer, a screenshot tool, a renamed planner button, or merely an offline proposal form. The operator can adjust the robot's world base pose and inspect the change against CBCT, forehead mount, target tooth and scene; jog each of J1–J5 individually; adjust and compare a prospective Task Home; guide TCP position/orientation and explore the approach and axial drilling direction; inspect both valid and invalid states; and manually assemble a time-ordered candidate motion. The same URDF/SRDF, TCP transform, robot limits, scene objects and phase contact policy used by the automatic planner must explain each result. A review representation may show rejected or speculative poses, but the accepted simulated robot is a distinct, monitored state.

The GUI needs viewport transform handles for base and review poses, per-axis base translation/rotation controls, J1–J5 sliders and numeric values, keyboard increments with selectable step sizes, clear current/review/accepted pose labels, and an obvious way to select the next manually inspected state. Existing SlicerROS2 goal robot, joint sliders and path display are starting points, subject to measured latency and ownership checks. The workbench must keep the relevant tooth, trajectory line, tool axis, collision pair and accepted/rejected path visible while exploring, so a numerical failure can be understood spatially. It must show when the authoritative ROS/MoveIt/guard answer is pending, current, stale or unavailable. No `valid` badge may come solely from a fast display update or empty collision-pair list.

**29 September operator visualization requirement:** When PreEntry IK blocks a guarded approach, show the exact diagnostic-snapshot PreEntry, Entry and Target world-RAS coordinates and standoff prominently, mark these points in the viewport, and let the engineer inspect each available best failed J1–J5 pose on the translucent goal robot. Show numerical residuals beside the pose and distinguish solver failure, static validity and collision-check status. A saved or stale report remains text-only until a fresh exact-current diagnostic is run. These markers and failed poses are display-only snapshots; they never change accepted robot state, satisfy a collision check or grant route/preview authority. The headed acceptance gate must verify marker placement, visibility, cleanup and its relation to the selected tooth/trajectory, not just the text or a host mock.

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
   is visibly invalid and cannot be jogged. Arm state contains exactly J1–J5.
   The dedicated manual status now has request/session and actual raw policy
   identity at source level; verify it in the native runtime before trusting
   live acceptance. Correlate request/session,
   exact vector, policy and scene through the existing native protocol; a fresh
   matching vector alone is insufficient evidence for repeated identical requests.
   Retain ambiguous/stale outcomes as unknown, reconcile monitored state and block
   further commands until the accepted state is known. No guessed rollback command.
   **Exit:** pure checks cover no accepted mutation on draft/cancel/reject/unknown,
   stale response, same-vector repeated request, identity change, limit edges and
   extra-value shape rejection.

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

### 28 September completion-order checkpoint

The first five-DOF headed campaign after the case-restore/native-result fixes
reached the accepted and invalid-draft gates, then stopped at the first new
unknown-result boundary because a valid follow-up Guarded Jog was disabled. The
cause was an ordering race in the shell completion path: robot-state refreshes
while `_workflowActionBusy` was true cached jog availability as false, and the
completion path cleared busy without a final authoritative refresh. The
production shell now clears busy, completes the panel request, and refreshes
Step 6 availability in that order. The full Manual Jog UI suite (35 tests) and
headed-runner source suite (44 tests) pass, with compile and diff checks clean.

The next serialized runtime is run-local package r14 under
`data/dentobot-runs/s6-live-01-five-dof-campaign-20260928T165722Z-r14/`.
Its exact `:10` recording command was prepared but automatic approval rejected
the escalated Docker/runtime action before launch because the account usage
limit was reached. This leaves the source fix **headed-runtime pending**; r13
remains partial failure evidence. Do not promote this source result to native
unknown/reconciliation acceptance, a whole-run recording, a new case, full
chain preview, or Tarun's verdict. **Operator halt, 28 September:** do not
launch r14, Slicer, ROS/MoveIt or the recorder until a later explicit resume
instruction. Preserve the itemized source/runtime evidence and keep the next
runtime gate pending.

### 30 September demonstration-blocker checkpoint

The operator demonstration exposed two user-visible source defects under
`S6-LIVE-01`: uncertain Base acceptance left the primary visible action greyed
although reconciliation existed elsewhere, and exact reuse of the saved
incisor-derived ROI invalidated workspace evidence and returned the planner UI
to a stale loop. The Step 6 Base action now invokes the existing reconciliation
owner while uncertain; normal Step 3B placement/lock is unchanged. Exact saved
ROI/source reuse preserves evidence, changed ROI still invalidates it, and the
primary Approach/Compare actions require runtime workspace validation plus
reviewed limits. Facade planning enforces the same prerequisite before guard or
planner invocation. The final combined host check passes 250 tests; compilation
and diff checks pass.

Recorded headed recovery r1 proved strict fresh restore of
`sept30_fdi11_step6_manual_record_persistence.dentocase`, five-joint robot,
ROS/MoveIt, 31-object scene, detached Task Home accept and exact ROI display.
It then exposed a separate precision bug: the UI no-op helper had been reused
for runtime workspace identity, comparing a six-decimal editable ROI with the
full-precision default midpoint. Runtime identity is corrected to use current
source identity and the saved proposal's own ROI fingerprint. The public
comparison helper remains only for UI no-op detection.

The next two early retries r2/r3 exited `SlicerApp-real` before planner
execution. An isolated native child diagnostic showed that the generic
launcher wording was insufficient to assign a signal. Recorded r6 subsequently
completed the Base/Home/workspace/J1/history/save campaign with Slicer and
FFmpeg exit 0; its new `sept30_fdi11_step6_3_demo_ready.dentocase` SHA-256
is `539ee7948bd97434ab4ef8b675e1540f065219a7e5250c3a422d2cfb481c371a`.
Fresh-process r7 strictly reopened the case and seven robot models with exit 0.
R6 made no planner call and started no preview.

The next case-bound TCP/full-chain campaign r8 stopped before those probes.
Direct-child r9/r10 captured native `SlicerApp-real` **SIGSEGV 11** during
post-hydration validation and Task Home connectivity 12/13 respectively.
Neither cgroup OOM nor a native backtrace was found; Python faulthandler
remained empty. The three-failure retry ceiling is reached on this distinct
case-bearing `S6-U-01` condition. Retain r8–r10 videos as partial/failure
evidence. The isolated no-case shutdown result remains accepted for its
narrow condition; the successful r6/r7 case checks do not establish native
reliability across repeated loads. The case-bound TCP, rejected/unknown guard,
full-chain preview/interruption and operator verdict remain open.

Resume only after a specific native-debugging strategy and Tarun's direction
under the retry-stop rule:

1. Capture a native crashing-thread backtrace on a narrow case-bearing
   simulation trial without changing robot geometry, tolerance or policy.
2. Correct the demonstrated native cause, then use one isolated fresh
   case-load/robot check as the cheapest sufficient regression.
3. Run one recorded complete campaign covering valid/invalid manual review,
   accepted/rejected/unknown and reconciliation, case-bound TCP mouse/keys/
   Cartesian/IK, record export/reopen, two-area authority, full-chain
   interruption and responsiveness. Use the saved demonstration case only
   after rechecking exact case/native provenance.
4. Require zero native/recorder exits, complete hashes/screenshots/JSON/logs,
   owned-process cleanup and a run-local planned/observed diagnostic.
   Tarun's normal-window robotics/usability verdict stays **PENDING**.

### Ownership and completion rule

Sol owns reasoning, review, controlled records, serialized runtime and
acceptance. For this campaign, use up to four GPT-6 Luna Max workers when
qualifying bounded grunt work has genuinely independent scopes, with disjoint
files, no recursive delegation and no controlled-doc edits. The current
platform permits at most three workers beside Sol concurrently; an additional
permitted worker is sequential. Tarun's request that Luna write and perform
tests remains active: use read-only Luna verification on
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


## 1 October — All joints visible iteration1 implementation authorized

Operator selects “all joints visible iteration #1” and directs implementation. This supersedes the design-selection hold for that bounded joint-editor change under S6-LIVE-01 Priority0. Implement in the integration checkout, preserving shared Home/manual ownership, draft-only editing, exact callbacks/SI conversion/range policy and explicit acceptance/guard actions. No Slicer/ROS/planner/motion trial or native build is inferred. Rendered usability verdict remains required after source/host closure.

Exactly two GPT-6 Luna Max workers: joint_editor_source owns only DENTORobotSimulationPanel.py; joint_editor_tests owns only Testing/test_robot_manual_jog_ui.py. Coordinator owns specifications, integration review, checks and controlled records. Source scope is native Qt stable ID/unit rows, numeric drafts, accepted comparison/delta, range endpoints and explicit outside-slider notice, collapsible detailed limits/state, contextual editor title. Test scope is focused regression/harness changes after source freezes. No worker checks against changing files. Performance watchdog/progress/resource/launcher reservation and concurrent DentoCase files are excluded and preserved. Existing input timing/wheel behavior is not altered in this presentation pass.

Smallest acceptance check: matrix pure.step6_manual_tcp_workbench (four-file host selection), compile changed source/test, diff review and whitespace checks. Question: do presentation refreshes preserve short labels and honest accepted/draft/range displays with no implicit commands? Stop after applicable passing source checks; rendered Qt acceptance is a separate bounded manual verdict. No new task or priority change.


## 1 October — All joints visible iteration1 source/host closure

Selected UI implemented in DENTORobotSimulationPanel.py: five unframed native Qt rows with permanent J1–J5/unit labels, numeric draft fields, full-width sliders, compact range endpoints, accepted-state/signed-delta comparison, full-row conditional warning and collapsed Limits and state details. Shared Home/manual editor and context title retained. Dynamic limit refresh no longer replaces IDs with prose. Comparison suppresses deltas for offline/unknown/pending/reconciliation-required/uninitialized/invalid states. Detailed numerical draft summary moves into the expandable area; actionable limit/guard reasons stay visible. Existing slider/numeric callbacks, draft updates, SI conversion, reset and request bodies are AST-identical to pre-edit snapshot. No range/policy/input timing/persistence/native change.

The two originally authorized Luna Max scopes were dispatched under the then-current delegation rule. Source worker froze its file; test worker stopped on usage limit. Tarun then supplied replacement AGENTS instructions permitting solo work and said continue. Coordinator finished the interrupted test file directly, preserving parallel edits; no replacement worker/model was substituted. Review corrections included compact unavailable messages/endpoints, full-width warning, explicit IDs in details and no synthetic zero-draft delta.

Matrix-derived pure.step6_manual_tcp_workbench command, from integration checkout:
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider Testing/test_robot_manual_jog_ui.py Testing/test_ros2_bridge.py Testing/test_robot_workflow_facade.py Testing/test_application_shell.py -k 'not test_new_empty_case_resets_entire_workflow_to_step_zero and not test_saved_case_navigation_keeps_every_workspace_selectable'`
Final **312 passed, 2 deselected in1.64s, exit0**. Two unrelated case-backend tests excluded because that file is concurrently edited under DentoCase ownership; no claim of a complete four-file suite. First run310passed/2failed/2deselected: incomplete extracted Home-review harnesses omitted the new helper; coordinator added it and repeated the same selection. Regression coverage includes accepted conversion/delta, uncertainty/offline/pending/uninitialized no-delta display, stale range clearing, preserved out-of-range numeric draft, short IDs after limit refresh, reconciliation transition and existing no-implicit-command behavior.

Changed panel and test compile passed with PYTHONPYCACHEPREFIX under /tmp/dentobot-joint-editor-iteration1-20261001/pycache; git diff --check exit0. Logs and pre-edit snapshots: /tmp/dentobot-joint-editor-iteration1-20261001/. No Slicer/ROS trial, planner/motion, native build, commit/stage/push or reset. Performance and DentoCase reserved files remain untouched. Source/host scope is complete; rendered narrow/default/wide/large-font and Home/manual usability verdict remains OPEN under S6-LIVE-01. No runtime owned by this chat.


## 2026-10-01 — proposed 6.1–6.3 presentation consolidation

**Operator request:** plan duplicate/redundant items across 6.1–6.3 from a smooth UI/UX perspective. This is a planning-only continuation of S6-LIVE-01 Priority 0, not implementation or runtime approval. Existing all-joints-visible iteration1 source/host closure and outstanding rendered verdict remain unchanged. Current integration source inspected; no new task or queue.

**Observed source:** `widget_robot_shell._setStep6Substep` visibility mapping shows visualization/Base/runtime/collision cards in 6.1; Home in 6.2; and Home plus joint limits, workspace generation, assisted review, task confirmation, TCP exploration, manual joints, approach and drilling cards in 6.3. One joint editor is already reparented, not duplicated. Legacy ROS motion controls and trajectory-planning group are hidden and are not evidence of visible duplication. Base recovery is both a dedicated panel action and the context-dependent primary Base action. Home displays current/configured/staged/review/saved status separately; the full Home card also appears in 6.3. A live-joint card retains a 6.2 title while visible in 6.3. Numeric TCP goal and nudge controls are complementary inputs to inspect before any consolidation of bindings.

**Proposed outcome:** retain existing substeps and state machine; reduce simultaneous cards, repeated actions and technical text. One persistent compact context summary uses existing authoritative projections: Base, Home, runtime/scene and task readiness. Values are independent (offline saved is not live validated; unknown is never Ready). One local blocker states what is missing and links to its existing owner. The context summary is read-only; it creates no new readiness or authority calculation.

| Surface | Routine presentation | Details / less frequent actions |
|---|---|---|
| 6.1 Base & Connection | One Base editor/review section and one ROS + collision-scene section. Base edit → Review → Accept uses existing gates. Recovery replaces the primary action when uncertain, with one visible Reconcile control. Connection and scene state remain separately labelled. | Appearance/CBCT, full pose matrix/fingerprints/rollback evidence, object audit table, explicit repeat scene synchronization, accepted-state check, reset/unlock/delete. Destructive actions remain explicit. |
| 6.2 Task Home | One five-joint editor, concise Home status, Review then Save Configuration offline / Accept & Validate connected, Cancel during known review. Current accepted robot and saved Home comparison remain distinguishable. | Full vectors/limits/evidence; conditional reconciliation; separate Plan + Apply Task Home control with motion meaning explicit, not part of saving. |
| 6.3 Workbench & Planning | Read-only Base/Home summaries with Edit Base / Review Home links to existing owners and return context. Native focused views: Manual and Planning. Manual groups Joint and TCP inputs with the same existing draft; Planning groups Workspace & Limits followed by immutable Task Confirmation and phase diagnostics. | Joint increments/keyboard settings, historical records/import/export, workspace sampling configuration, planner comparison/settings, raw evidence. Active faults/results remain visible even when their details are folded. |

**Consolidation mapping:** remove repeated visible Base reconcile placement; show full Home editor at its 6.2 owner rather than a second full card in 6.3; replace 6.3 Home controls with an explicit Review as Home handoff that preserves the existing candidate and returns to workbench. This is presentation/navigation only: existing delegated 6.2 acceptance semantics remain. Integrate task-limit display, ROI/sampling configuration and assisted-limit review under one Workspace & Limits container without treating their operations as equivalent. Combine numeric TCP and axis nudge presentation into one TCP section after confirming shared goal state and coordinate frame; preserve IK result authority. Show accepted/draft five-joint values in the editor comparison/details rather than repeated prose dumps. Rename incorrect 6.2-labelled live-state card in 6.3. Retain one persistent research/simulation notice and contextual actionable warnings.

**Meaningful distinctions to retain:** Refresh reads status; Audit + Sync writes/reconciles the scene. Check Accepted Robot and Check Joint Draft target different states. Save/accept Home does not move the robot; Plan + Apply does. TCP exploration IK and task PreEntry IK target different goals. Workspace generation and assisted-limit acceptance differ. Task confirmation freezes identity; planning computes paths. P1/P2/P3 retain individual results and failure evidence. None of these are merged into a generic Validate/Apply button. Recovery may resolve only one authority domain: Base, Home and jog uncertainty remain separately attributed.

**Interaction rules:** one primary action per local workflow state, not one global button that silently changes domains. Keep Cancel and disabled-action reason adjacent. On stale/unknown state show the reason and recovery/navigation action immediately; never hide the blocking fault in Details. Navigation/folding must preserve typed values, staged candidates, accepted state, imported records and results. Moving away disables keyboard/viewport capture as existing substep rules require. Returning must not publish, accept, resync or regenerate automatically. Readiness summaries must not imply offline validation or auto-promote a candidate. Preserve separate robot, joint draft, TCP goal and historical path meanings in viewport legends.

**Bounded delivery proposal (not execution authorization):**
1. Establish a source-derived control/action map and static before/after layout for offline ready, connected ready, staged review and unknown/stale states. Review those layouts before changing source; no new custom widget framework or dependencies.
2. Consolidate 6.1 duplicate recovery/status and 6.2 Home text/actions using existing widgets, callbacks and projections. Keep iteration1 five rows unchanged except agreed surrounding hierarchy. Stop for operator visual verdict after an authorized representative render.
3. Consolidate 6.3 containers and Home handoff, using native Qt focused views and existing editor/state. Preserve workspace sampling, assisted-limit review, task confirmation, manual joint/TCP/record controls and all phase diagnostics. Do not change planner, tolerances, collision policy or runtime APIs.

**Owned implementation files if authorized:** panel, robot-shell presentation/visibility/navigation and existing UI resource only where necessary; narrowly scoped existing presentation tests. Coordinator owns controlled records. Bridge/facade/native planner/performance and DentoCase files are outside scope. If safe Home handoff needs state-owner changes, stop and specify that interface rather than invent a second draft or authority owner.

**Acceptance:** source map proves one visible presentation per duplicate action and no lost capability; existing action-owner/disabled-reason/identity rules remain; navigating 6.2↔6.3 preserves exact J1–J5 draft and staged Home without publishing. Check offline, connected, stale, unknown and failed states. At default and narrow/wide/large-font layouts, five joints stay grouped with IDs/units/values, routine controls are discoverable, primary action and reason are local, critical errors remain visible, and 6.3 does not stack every card. Select cheapest relevant matrix host checks under verification protocol; GUI/ROS resources stay serialized and require explicit scope, with every demonstrable GUI result stopping for Tarun's verdict. No backend fix or UX success claimed by this plan. Performance increment2 missing native async API remains separately tracked and is not repaired by layout work.


### 2026-10-01 — narrow-module sketch constraint (S6-LIVE-01)

Operator requests sketches for all three steps including button placement, explicitly avoiding long scrollable windows in Slicer's narrow module GUI. This supersedes expandable main-page detail stacks in the preceding UX proposal: switch content in place, with focused dialogs for secondary controls/evidence. Sketch uses approx 320–360px module widths, compact common context and a bottom Previous/Next row; 6.1 Base / Runtime & Scene switch, 6.2 single five-joint Home editor, 6.3 compact view selector for Manual Joints / Manual TCP / Workspace & Limits / Task & Planning. Review/Accept remains two explicit operations: Review opens exact-candidate evidence with Cancel left and Accept right. Main-page local action rows retain Check Draft vs Guarded Jog, offline-save vs connected-validation, and separate Plan + Apply. View selection must preserve drafts/results; faults remain visible and direct reconciliation replaces the local primary action when needed. Secondary settings/records/audits appear in dialogs rather than increasing module height. No hard no-scroll guarantee at arbitrarily short windows or enlarged fonts: implementation must measure available height, keep controls readable, and reserve minimal fallback scrolling only when physically necessary. Native runtime/large-font verdict is open.

Sketch: /home/light-tarun/.codex/visualizations/2026/09/30/01a0f451-f099-7fa1-bf5e-35cc1c642257/step6-narrow-panel-sketch.html. Example values and readiness states are illustrative, not runtime evidence. Three screens are shown together for comparison; Slicer shows one step at a time. Interactive view switches, sliders and dialog locations are local mock interactions only. No application source changes or runtime execution authorized by this sketch request.


## 2026-10-01 — essential-function preservation correction (supersedes compressed sketch)

**Exact operator delta:** the sketch looks neat but removes important steps; retain Connect ROS, Propose Virtual Forehead + automatic Base placement, and automatically enable Base viewport dragging when unlocked with GUI status text. Replan to remove only nonessential/redundant items. Treat this as design correction under S6-LIVE-01 Priority0; it does not approve source/runtime changes or reopen closed S6-U-02 simulation work.

**Correction to prior agent interpretation:** Connect was technically on an alternate view, but hiding that required setup action was poor discoverability. The sketch omitted the existing combined forehead/Base proposal and the required drag/lock presentation. A compact form is not accepted when capabilities vanish. Replace arbitrary minimization with a control-preservation ledger. Every active capability must have a named same-step destination before implementation; only demonstrably repeated presentations and obsolete/quarantined routine chrome may disappear. Moving a control into a named view/dialog is relocation, not deletion.

### Revised placement and button contract

| Owner | Direct surface / named view | Preserved controls and semantics |
|---|---|---|
| 6.1 common header | Always visible across Placement / Scene / Display | ROS connection status and explicit Connect ROS + MoveIt or Disconnect; remain the existing single owner. Offline robot loading never substitutes for connection. |
| 6.1 Placement | Default view | Load / Reuse Local Robot; **Propose Virtual Forehead + Auto Base** (existing combined handler, one unreviewed proposal); Robot + CBCT Placement View; current virtual-forehead prior/freshness; Base lock state; Unlock Base; viewport translation/rotation status; local XYZ/RxRyRz nudges, translation/rotation steps, optional keyboard; Review Base, explicit Accept Base, Cancel Review and conditional Reconcile. No automatic Base acceptance. |
| 6.1 Scene | One-click tab | Refresh Status, Audit + Sync Collision Surfaces, Check Accepted Robot, collision acknowledgement/failure, named Object Audit and Runtime Diagnostics. Connection stays visible above the view. |
| 6.1 Display | One-click tab | Enable CBCT 3D Context and preset; Frame Case + Robot; named Visibility / Opacity dialog retains all CBCT/anatomy/accepted robot/goal robot/guides/mount/trajectory/forehead/collision-audit elements. |
| 6.1 Base details/tools | Named dialog | Full accepted/candidate matrices/identities, Reset Base to World and Delete Robot Setup with existing explicit boundaries; critical recovery is on Placement when needed, not buried here. |
| 6.2 Home | Default editor | Exact shared J1–J5 draft, slider/numeric, bounds and accepted comparison; Reset Draft to Current; current robot vs saved configuration vs staged Home labels; Review, Cancel and explicit offline Save Configuration / connected Accept & Validate; conditional Home Reconcile visible beside fault. Separate Plan + Apply Saved Home retained. |
| 6.2 Details | Named dialog | Full current/configured/candidate vectors, limits, identity and validation evidence. No removal of states merely because a short summary replaces full prose. |
| 6.3 common controls | Above active view | Explicit Edit Base (6.1) and Review Home (6.2) handoffs to the same owners; preserve draft and return context. No second Base/Home authority. |
| 6.3 Manual Joints | Named view | Shared five-row editor, exact typed state, Reset Draft, Check Draft, Guarded Jog, accepted/guard/fault reason and conditional Jog Reconcile; keyboard enable and increment selector stay visible, full keys in named increment settings. |
| 6.3 Manual TCP | Named view | World-RAS XYZ and pitch/yaw numeric target, axis translation/angular nudges, steps/keyboard, explicit TCP drag toggle, Solve Goal IK and result/staging. TCP drag remains separately opt-in; automatic Base handles do not auto-enable TCP. |
| 6.3 Workspace & Limits | Named view | Incisor-centered editable ROI XYZ/dimensions, Use Incisor Midpoint, sample count, Generate / Refresh, Clear Workspace, Revalidate, Review Assisted Limits and evidence; named Joint Task Limits dialog retains five task min/max values, Apply, Reset to URDF and existing reset-joints operation. Manual and assisted limits remain distinct. |
| 6.3 Task & Planning | Named view | Actual task prerequisites, immutable Confirm Task and identity; Check PreEntry IK and separate P1/P2/P3; Plan Guarded Approach and **Plan Drill Phase** remain distinct existing operations; insertion/preflight and full-chain result/blocker; Planner Settings and Inspect Motion Diagnostics. Do not replace them with a fictional single backend Plan Complete Route operation. |
| 6.3 Diagnostics & Anatomy | Named view | Compare Three Planners, Cancel Comparison, Show Results; non-target tooth selection, Create Copy, Open Segment Editor, explicit artifact confirmation, Use Reviewed Proxy and Discard with policy/identity status. Historical template override remains expert/retired according to its existing gate, not routine baseline. |
| 6.3 Records & Replay | Named view | Ordered requested/accepted/rejected/unknown history, Export, Import, Show, Clear, imported-event selection and Previous/Next, historical path/provenance/fault. Preserve exact existing clear/reset semantics; never treat replay as motion. |

### Automatic Base viewport interaction requirement

Source evidence: `logic_robot._applyRobotBaseMountInteractionState` sets translation/rotation/editor handles to `not locked`; `widget_robot_placement._setRobotTransformInteractionVisible` additionally requires `not robotStageActive`, suppressing handles in Step6. This conflicts with the desired 6.1 unlock behavior and means the new active status cannot be claimed as already verified in the integration checkout. Treat the operator's “as is rn” as an observation, retain it separately from this source finding. No runtime was inspected.

Desired behavior: on an allowed 6.1 unlock/edit transition, show translation and rotation handles automatically and refresh the visible GUI text. Reuse the existing Base review owner/candidate matrix for both viewport and numeric/local-axis controls. Do not turn a raw transform edit into accepted Base authority. Confirm the interaction target before enabling: if current handles target the accepted transform rather than the detached candidate, first bind them to the existing review representation or specify the smallest owner change; do not bypass this by blindly removing `not robotStageActive`. No scale handles. On acceptance/lock, leaving placement, missing target, busy or uncertainty, disable handles as appropriate and explain the actual state.

Visible text follows actual enabled interaction and permission, not lock bit alone:
- `Base unlocked · viewport drag active` when permitted and target handles are active.
- `Base locked · viewport drag off` after accepted locking.
- `Base unlocked · drag unavailable: <reason>` if initialization/target is missing.
- `Base outcome uncertain · drag blocked · Reconcile Base State` for an uncertain outcome.
Keyboard nudge retains its existing explicit enable/focus rules. Editing/proposing never auto-connects, accepts, validates Home, synchronizes scene, confirms task or plans motion. The independent VirtualForeheadPriorV1/Case Foundation path is retained; circular legacy plane/snap remains quarantined.

### What may actually be removed

Repeated Base reconcile presentation; repeated full-pose/vector/status paragraphs whose facts remain in a compact state and Details; duplicate wrapper headings and stale step-number labels; disabled routine Legacy Plane/Flip/Snap rows (quarantine evidence remains in diagnostics); second visible robot-load entry only after checking both callers and establishing equivalent behavior. No removal of a unique action, readiness distinction, warning/fault, acceptance/recovery gate or existing engineering capability. In particular, shared Step3B/6.1 widgets are reuse, not redundant functionality to delete. Match every old active control to this ledger and its callback before a source diff.

### Bounded implementation/acceptance proposal

First review corrected sketch/control destinations. If authorized, reorganize existing widgets/native Qt views and dialogs, keeping indices and owners. Handle-status/target binding is a separately explicit interaction slice within S6-LIVE-01, not a cosmetic relabel. No planner/native/performance/geometry/tolerance policy changes. Static ledger and existing owner/navigation host checks first; then authorized serialized narrow render/interaction checks. Required cases: no robot, offline robot, connected, current/stale prior, locked, unlocked, staged/accepted/unknown Base, Home modes, all five joints, TCP draft, workspace/manual/assisted limits, task/phase diagnostics, records and return navigation. Verify automatic unlock handle activation/lock deactivation against actual target and accepted-state invariants, status correctness and cleanup. Tarun's verdict remains mandatory. Narrow-panel no-long-scroll goal remains: fixed common header/navigation with one replaced content view; avoid full-card stacks and nested scroll areas. No UI source change, ROS run, build or motion trial in this planning turn.

Corrected inline sketch: /home/light-tarun/.codex/visualizations/2026/09/30/01a0f451-f099-7fa1-bf5e-35cc1c642257/step6-narrow-panel-sketch.html. Illustrative states/values and local interactions only; it does not establish native fit or interaction success. It replaces the preceding incomplete sketch as the current proposal, not a separate queue.

## 2026-10-01 — continuity review of the corrected sketch (current design recommendation)

Operator asks for a review/improvement focused on UI/UX, flow, continuity and appropriate distribution across all three steps. This refines the preceding preservation ledger; it does not authorize implementation or remove any retained capability. The existing HTML remains an earlier illustrative sketch and is not yet an executable specification of this recommendation.

### Concrete review findings

1. Review/Accept is duplicated between page buttons and the generic modal; the mock acceptance does not update the disabled page Accept button or context summary. Use one inline review mode in the existing editor region. Review freezes/displays the exact candidate and replaces the local action row with Back to Edit / Accept; retain Cancel Review. Returning to edit invalidates the staged review using existing semantics. Uncertain state replaces acceptance with attributed reconciliation. Details may open separately, but never supplies a second acceptance control.
2. Top back arrows duplicate bottom navigation. Reuse one existing stage navigator and one labelled bottom Back / Next pair; omit the extra local back arrow. Navigation never silently accepts, publishes or changes runtime state. Screen access and operation readiness remain distinct under existing navigation policy; do not invent navigation locks from planner readiness.
3. The six-option 6.3 dropdown hides tools and mixes frequent control, setup, diagnostics and history. Recommend three stable primary native tabs: Manual / Workspace / Plan. Manual contains Joints / TCP input selection. Records is a named tool available from Manual; Plan exposes named Diagnostics, Planner Comparison and Anatomy Review tools. Those tools replace the content in place with a labelled return, preserving their full existing controls. Display/appearance is a named modeless tool; it must remain usable while interacting with the viewport.
4. Always-visible Base and Home edit buttons consume a full row even when unused. Use compact clickable Base/Home context summaries; show explicit Review Draft as Home beside the manual candidate actions when relevant. A status link names its destination and carries return context. Every preserved capability still has a visible named entry point; do not relegate it to an anonymous More menu.
5. The sketch is a minimum-height composition, not evidence of fitting Slicer's actual usable module height. Use one content region bounded by available space, keep all five joint rows together, avoid growing accordion stacks and nested scroll areas, and measure actual Qt font/scale. Proposed design target320–360px wide and about600–680px usable high is provisional. A short-window/accessibility fallback must remain usable rather than clip or shrink essential text.
6. Existing numerical demo ranges and zero ROI center are illustrative and must never be copied as robot defaults. Fixed connected/accepted labels conflict between screens and do not model a single session. The next mockup must drive visible status and actions from a coherent local example state with missing/offline/connected/edit/review/accepted/stale/unknown cases, and must show blocked reasons. No test count proves native usability.
7. Misleading composite labels need correction: Clear Display / Record combines different scopes; map its exact existing handler and label one specific effect. Increments descriptions must match actual global vs per-joint implementation. Task & Planning must retain separate approach/drill operations. Workspace requirement must be projected from the current contract/capability result, not imposed by the mockup because a cloud is absent.

### Recommended three-step flow

**6.1 Robot Setup:** shared compact case/target/runtime context; Connect ROS + MoveIt remains a direct visible action, Disconnect a lower-emphasis explicit connected-state action. Default Placement view shows Load/Reuse Robot when needed, Propose Virtual Forehead + Auto Base, Frame Robot + CBCT, virtual-prior freshness, Base lock/actual drag state, precision controls and one inline review/accept/recovery area. Completed setup condenses to its result with labelled Modify/Re-propose access, not deleted functionality. Scene tab contains audit/sync/current-state check. Named Display tool contains full opacity/preset controls and remains modeless for viewport use. Existing Step3B mirror shares the same widgets/allocation. Connect availability follows existing prerequisites; this layout does not mandate a new connect-before-placement order.

**6.2 Task Home:** saved Home/live validation summary plus exact five-joint editor, accepted comparison and Reset Draft. Inline Edit→Review→explicit Save Configuration offline or Accept & Validate connected→result, with Cancel/reconcile as required. Plan + Apply remains a distinct labelled simulation operation. Bottom navigation says Workbench; no automatic apply on acceptance or continuation.

**6.3 Workbench & Planning:** three visible tabs Manual / Workspace / Plan. Manual has Joints / TCP controls; preserve separate joint draft and TCP goal and explicit existing IK staging rather than treating tabs as automatic conversion. Records/Replay stays one named click away and shows ordered history; an active historical display or proxy is announced in common context. Workspace retains all ROI, sample, generate/clear, revalidate and manual/assisted-limit controls. Plan starts with an actual prerequisite summary and explicit immutable task confirmation, then separate approach/drill actions and phase result rows. P1/P2/P3/IK diagnostic requests, settings/comparison/cancel/results and anatomy review remain available through named diagnostic views. Full-chain result controls preview eligibility. Do not make manual experimentation a mandatory prerequisite for planning or impose new workspace policy.

### Continuity and button rules

- On normal entry show the next unmet setup requirement; within the same session remember the user's selected tab/tool. Do not steal focus or switch tab on every status refresh.
- Edit Base/Home from 6.3 records origin view, exact draft/TCP goal and displayed results. Show Return to Manual / Return to Plan after the edit. Do not create a second state database; reuse existing state and a small navigation return marker.
- Base/Home/scene edits expose actual invalidation results: e.g. Home requires validation, workspace stale, task needs reconfirmation, previous plan stale. Retain evidence for inspection; no automatic replay/revalidation/replanning. Proposed destructive invalidation warning appears before the relevant explicit action, not on every harmless tab change.
- Review mode must keep candidate and scene simultaneously inspectable. In-place candidate summary and action row; full matrices/details separate. Auto-place, viewport drag, precision nudge and numeric edits converge on the same existing Base candidate. Required drag state/target correction remains separately scoped from layout.
- Local action row has stable positions: secondary/cancel/back-to-edit left, primary review/accept/jog/plan right. This is per active task, not a universal morphing button spanning unrelated authority domains. Navigation row is separate and visually quieter. The connection control stays distinguishable from motion actions.
- One concise result/blocker is adjacent to affected actions; full evidence is reachable. Cross-view blocking faults also appear in common context with their owner link. Do not truncate the only failure explanation into a tooltip. Keep ROS disconnected, Base unlocked, saved Home unvalidated and uncertain outcomes distinguishable.
- Long-running operations keep progress and supported cancellation visible; disable only conflicting actions and label cancellation according to actual backend guarantee. Do not add cancellation to handlers that do not support it.

### Next design acceptance gate

Before source implementation, replace the older static happy-path mock with a single coherent walkthrough: new/offline setup→load/propose→unlock/drag/nudge→review/accept→connect/audit per existing readiness→Home review/accept→manual or workspace/planning. Include a return-to-Base edit with truthful downstream staleness and an unknown-outcome recovery example. Check each existing ledger action has a visible named destination. Review at320/360px, normal/large font and constrained height. These are proposed mock/GUI acceptance cases, not authorization to execute Slicer/ROS/motion. Preserve all existing state, policy and runtime gates; stop for Tarun's verdict at authorized native demonstrations.

## 2026-10-01 — coherent three-step interaction sketch

The requested replacement sketch is `/home/light-tarun/dentobot/data/visualizations/step6-continuity-sketch.html`. It is one narrow Slicer-style module beside a shared viewport, with one active step at a time and a scenario selector for offline, connected-ready, Base review, Base uncertainty, Home review, downstream staleness and plan-blocked conditions. It is a design artifact, not runtime evidence.

The sketch implements the complete destination ledger above rather than a minimal subset. 6.1 retains direct ROS connection, robot load/reuse, virtual-forehead plus automatic-Base proposal, Robot+CBCT framing, prior freshness, actual Base drag/lock status, precision/keyboard editing, inline review/accept/reconcile, Scene actions and the full modeless Display inventory. 6.2 keeps all five named joint rows visible, separates offline Save from connected Accept & Validate, retains comparison/reconcile and keeps Plan+Apply distinct. 6.3 exposes Manual/Workspace/Plan together, Joints/TCP beneath Manual, Records as a named tool, complete ROI/sampling/manual/assisted-limit controls, immutable task confirmation, separate endpoint checks and separate approach/drill plans, plus named settings/diagnostics/comparison/anatomy tools.

Cross-step handoffs preserve an explicit return target. Accepting a changed Base demonstrates downstream Home/workspace/task/route staleness without automatic replay. Base uncertainty blocks viewport editing and exposes Reconcile. The routine surface omits only duplicate acceptance/navigation, repeated prose and quarantined Legacy Plane/Flip/Snap controls. Reset/Delete remain in named Setup Tools; full evidence remains reachable beside the owning fault. All displayed values are illustrative.

Structural verification parsed the embedded JavaScript, found 48 unique element IDs, checked 17 required labels/conditions, and confirmed fragment-only/no-fetch constraints (`fragment_ok`, 46,847 bytes). This does not establish Qt sizing, large-font accessibility, candidate-handle targeting, native rendering or operator acceptance. Those remain the next gate before source implementation.

## 2026-10-01 — approved 6.1–6.3 continuity implementation

Tarun approved implementation of 6.1 and 6.2, then explicitly approved 6.3 after review. The integrated source now implements the accepted ownership and continuity model without changing robot, planner, collision, tolerance or command policy:

- 6.1 uses Placement and Scene views, keeps direct ROS/MoveIt access and the virtual-forehead/automatic-Base flow, exposes named Display and Setup tools, and binds viewport manipulation to the detached Base candidate while reporting the actual drag/lock state.
- 6.2 presents one compact five-row J1–J5 Home editor with stable IDs/units, accepted comparisons, explicit review/cancel/accept/reconcile and separate Plan + Apply behavior.
- 6.3 presents visible Manual, Workspace and Plan tabs. Manual contains Joints/TCP plus Records & Replay; Workspace contains Samples, ROI & Assisted Limits and Joint Limits; Plan contains confirmation, separate Approach/Drill and named Planner Comparison/Anatomy Review tools. Secondary complete groups are removed from the main layout until their modeless tool opens. Base/Home owner handoffs preserve and restore the originating 6.3 tab.

Existing callbacks and state records remain authoritative. Tool dialogs close outside 6.3; TCP drag disables when its active view is left. Quarantined Legacy Plane/Flip/Snap rows remain absent from routine operation.

Source and host acceptance: the focused tab/handoff/UI suite passed 411 tests; the final Step 6 selection passed 565 tests; changed Python sources compile; scoped `git diff --check` passes. A real Slicer Qt headless encapsulation sequence passed 6.1→6.2→6.3→Base return→6.3→Home return→6.3 with preserved draft and unchanged authority fields. No robot hardware or physical motion ran.

The case-bound changed-Base/Home repeatability verdict remains open. Three serialized attempts exposed headed-runner assumptions rather than a demonstrated product-state failure: r1 used the removed legacy load control, r2 required mutually exclusive Base actions simultaneously, and r3 reached connected collision-scene acknowledgement before trying a Workspace ROI control while Manual remained selected. The source runner now selects the owning 6.3 tab before each action and has a focused regression test, but the verification protocol's three-attempt ceiling prevents a fourth campaign in this turn. The next fresh authorized campaign must complete changed Base and Home adjustment, acceptance/reconfirmation and a second repetition without stale state; Tarun's manual rendered verdict remains mandatory.
