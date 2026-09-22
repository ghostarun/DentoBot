# FDI31 GUI planner P0 recovery contract

Date: 2026-09-21  
Owner: `S6-LIVE-01`, continuing through `S6-LIVE-02..05` only after the
operator accepts each preceding milestone  
Status: active operator-superseding plan; implementation/runtime not authorized
merely by this document

## Queued P0 delta after reusable-case handoff — 2026-09-22

The operator queued the professor's recommendations as the immediate next task
after `S6-REUSABLE-CASE-SETUP`: display the effective runtime planner in Motion
Diagnostics; use RRT instead of RRT*; disable approximate IK; and disable
Cartesian-path planning in the live workflow.

This remains part of `S6-LIVE-01` and does not interrupt the current run. The
checked-in profile is `RRTConnectkConfigDefault` / `geometric::RRTConnect`, so
first trace and display the effective runtime planner ID. Do not rename it or
introduce another configuration unless runtime evidence shows RRT* is selected
or an exact replacement ID is provided. Before disabling Cartesian planning,
identify its Stage-2/3 callers and specify their bounded non-Cartesian
replacement. Audit every live IK call site and disable approximate solutions
without weakening FK/residual validation. Preserve all existing safety and
collision policies. Source acceptance requires the smallest focused check;
runtime acceptance requires the visible planner/IK/Cartesian states and then a
manual-verdict stop. No hardware motion is authorized.

### Operator-superseding execution delta — planner controls and full-cycle UX

The operator now authorizes incremental source implementation in this task,
solo and without subagents. Step 6.5 and 6.6 will share one pop-out planning
policy surface. The first iteration is diagnostic-only: retain and display the
effective checked-in policy (`RRTConnectkConfigDefault` /
`geometric::RRTConnect`, one attempt, 5.0 seconds, strict/non-approximate
position-axis IK, MoveIt Cartesian Stage 2/3 enabled). Do not present a control
as editable until the runtime API consumes and reports it.

Next, extend the existing SlicerROS2 joint-plan call with an explicit planner ID
and returned effective ID; then expose only configured planner IDs plus bounded
attempt/time controls. Cartesian-off requires the existing bounded sequential
exact-pose IK recovery to become an explicit primary Stage-2/3 mode with the
same FK, residual, collision, corridor and phase-guard gates. Approximate IK
remains disabled unless a separately reviewed approximate path still fails
closed at the canonical residual gates. Run one trial at a time and retain only
the current compact diagnostic and screenshot before adding more knobs.

**Source checkpoint `06b2ffd` plus bridge pass:** the diagnostic-only first
slice is committed. The following bounded bridge slice now adds an optional
planner-ID argument and effective-ID getter to both SlicerROS2 joint-plan entry
points, carries those values through `DENTOROS2Bridge`, and submits the current
`RRTConnectkConfigDefault` ID from every Step 6 explicit-state joint plan. It
does not yet add the shared chooser or claim a runtime-effective ID. The
focused SlicerROS2 package rebuild passes; a visible trial remains required.

**Shared-dialog pass:** Step 6.5 and 6.6 now open the same planning-parameters
dialog. The configured `RRTConnectkConfigDefault` choice, attempts (`1..10`)
and planning time (`0.5..60.0 s`) feed Goal-1 joint planning and its diagnostic
fingerprint. Approximate IK remains visibly disabled, and Cartesian Stage 2/3
remains visibly enabled but locked pending its separate replacement pass. The
dialog does not manufacture unconfigured planner IDs.

**Operator goal continuation, 2026-09-23:** Interactive comparison is now
explicitly requested. Add `RRTkConfigDefault` / `geometric::RRT` as a second
configured OMPL choice while retaining RRT-Connect as default. The two IDs are
the only chooser entries. The planner response is rejected if the selected ID
is not reported back by SlicerROS2; diagnostics distinguish requested from
reported identity. This supersedes the earlier restriction against adding a
second configuration without a named replacement. The installed YAML and
focused source checks are preparation, not a visible planner-result verdict.

The adjacent workflow-completion phase uses user-facing `APPROACH`, `DRILL` and
`RETURN HOME`; P1/P2/P3 remain internal diagnostic stages. Preserve Goal 1/Goal
2 internal APIs and saved-state terms for compatibility. No global rename or
new state machine is authorized.

**Terminology source slice, 2026-09-23:** The Step 6.5/6.6 navigator,
phase panels and primary preview actions now use Approach/Drill names without
changing their callbacks or planner behavior. Facade result/error text and
stored Goal 1/Goal 2 compatibility terms remain for a separate bounded
wording pass; this slice alone is not full terminology or GUI acceptance.

**Operator-message source slice, 2026-09-23:** Facade, Step 6 logic and ROS
bridge result/error strings now direct the operator to Approach or Drill
preview. The retained Stage-3 preparation docstring/comment was aligned with
its actual preflight-reuse behavior. Internal Goal 1/Goal 2 symbols and
diagnostic schema remain unchanged. Visible confirmation is still open.

**Planner-ID attribution correction, 2026-09-23:** SlicerROS2 stores
`MoveGroupInterface.getPlannerId()` immediately after `setPlannerId()` and
before `plan()`. This is a configured-ID echo, not proof that the returned
trajectory used a particular OMPL algorithm. Motion Diagnostics must label it
as such; `joint_planner_id`/`effective_planner_id` remain compatibility keys.
The first visible comparison can report selected ID, configured echo, installed
YAML mapping and plan result, but may claim an executed algorithm only with
separate planning-server evidence. Do not infer that from matching IDs alone.

**Bounded Cartesian-off design (source audit, not enabled):** The current
Stage-2/3 callers are `_goal1_candidate_chain_preflight()` and the retained
full-line/terminal preparation in `DENTORobotWorkflowFacade`. They call
`DENTOROS2Bridge.plan_moveit_cartesian_path()`; its existing
`_position_axis_continuity_fallback()` already samples the unchanged straight
TCP line, solves each pose with non-approximate J1–J5 position-axis IK from the
last accepted state, checks FK/residuals, and retains first-invalid evidence.
For a later Cartesian-off source pass, reuse that helper as the primary line
generator behind the same bridge result contract, without invoking
`PlanMoveItCartesianTrajectoryFromPoseMarkers`. Keep explicit start-state FK
continuity, the exact requested Entry/Target points and fixed axis, bounded
sampling/seeds, canonical joint/limit checks, endpoint FK, and the existing
independent full-chain phase guard before any preview promotion. Do not replace
the line with a free-space endpoint joint plan, infer collision safety from IK,
or introduce a new route/state machine. The current helper is a fallback only;
this paragraph is a design boundary, not evidence that Cartesian-off works.
First obtain the one-at-a-time RRTConnect/RRT visible comparison and Tarun's
verdict; then implement and check this mode separately before making its
Step 6.5/6.6 control editable.

## Outcome and authority

Recover the saved FDI31 case through the ordinary visible Step 6 workflow by
using native MoveIt planning as the primary planner and changing one causal
variable at a time. Every visible or demonstrable success or failure stops for
Tarun's manual trial, interpretation and explicit decision before the next
milestone. Routine non-visible implementation findings stay with the
orchestrator and do not interrupt the operator minute by minute.

The operator superseded the original Sep-19 input on 2026-09-22 after creating
a fresh workflow against the installed diagnostic-URDF package. The sole active
case is now:

`data/Slicer_Saved/SampleStudy1/FDI31/dentobot-case-sep22-step6.dentocase`

SHA-256:
`eb48a805c81578bafcc8ca72663b6f8a98b1f9721c7f9e680d44b458558e7adb`

The Sep-19 package remains the historical GUI baseline and is not a fallback.
The first Sep-22 planner screenshot was produced by the canonical housing-on
launch because the desktop handoff did not forward Experiment A's launch
option; it is not an M1-DIAG result.

Campaign-1 r4/P3/P4/P5 artifacts remain historical diagnostic evidence. They
do not establish GUI planner success for this case and are not alternative
execution inputs. The 18–19 September AUTO opening, simulation base placement
and ordinary workflow through Step 6.5 remain the current baseline.

## Required team and escalation

- Orchestrator: **`gpt-5.6-terra` at `xhigh`**. Terra owns reasoning, task
  boundaries, experiment selection, worker specifications, integration,
  controlled records and acceptance recommendations.
- Implementation workers: **`gpt-5.6-luna` at `max`**. Use them only for
  settled, bounded changes with explicit owned files, interfaces, invariants,
  forbidden changes and one smallest meaningful check.
- At most **two subagents may be active**. Zero or one is preferred. Workers
  must not recursively delegate, overlap writes, invent policy, run GUI/ROS
  resources or declare acceptance.
- Before spawning, state the task, benefit, exact model/effort and active worker
  count. If the required preset is unavailable, report it; do not silently
  substitute another model.
- A trivial internal error, non-visible check result or obvious implementation
  correction returns to Terra for reasoning and disposition within the
  approved scope. It does not require a separate operator interruption.
- A visible milestone result, fatal runtime failure, ambiguous geometry,
  competing safety/design choice or requested scope change stops for Tarun.
- If the failure is highly algorithm-specific and requires unresolved reasoning
  about Jacobian convergence, IK branch continuity, configuration-space
  connectivity or planner correctness, pause development and give Tarun a
  bounded evidence packet. Do not spawn a stronger model, rewrite the algorithm
  or enter a retry/model loop without his instruction.

The coordinator remains responsible for inspecting every worker diff and the
actual evidence. No mandatory reviewer pipeline is introduced.

## Mandatory GUI workflow

All runtime acceptance must use the visible operator workflow:

1. Open the exact saved package.
2. Activate its current PreparedBranch.
3. Show/load the saved robot representation.
4. Check that the saved simulation base is present, current and locked.
5. Connect to ROS through the normal UI.
6. Validate or apply Task Home through the normal controls.
7. Reload/revalidate the required workspace and task state.
8. Confirm the task.
9. Enter Step 6.5 and invoke the normal planner controls.

Opening a `.dentocase` does not restore live ROS/MoveIt validity. Headless
monolithic runners, injected task snapshots and backend-only passes may provide
diagnostic evidence, but they cannot substitute for or close these milestones.
If an upstream GUI prerequisite fails, correct that exact defect under its
existing owner and return to this sequence.

## Operator-reviewed milestones

| Milestone | Demonstrable result | Stop condition |
|---|---|---|
| M0 — GUI baseline | Exact case, branch, robot/anatomy, base, Home and task are current; retain the visible native first failure. | Tarun verifies the baseline before a diagnostic model change. |
| M1-DIAG — HOUSING-OFF PASS/FAIL | With only the spindle-housing collision block absent, native OMPL attempts the same Home→PreEntry P1. | Record `M1-DIAG / HOUSING-OFF PASS` or `FAIL`, show the result, and stop for Tarun. This never closes M1. |
| M1 — Home to PreEntry | With the canonical full-collision URDF restored, native OMPL produces a complete P1 path to a verified collision-aware PreEntry endpoint. | Display the real path and native result; stop for Tarun's trial and verdict. |
| M2 — forward planner | Starting from accepted full-geometry M1, P1, P2 and P3 reach the exact saved Target; the independent phase guard accepts the chain; Goal 2 consumes the accepted Stage-3 plan. | Stop for Tarun's manual planner trial. Housing-off M2 is outside normal acceptance and requires a separate explicit operator decision. |
| M3 — forward preview | Normal Goal 1 preview reaches Entry and Goal 2 preview reaches Target with ordered guard acknowledgements and monitored endpoint verification. | Stop before withdrawal/Home for a separate operator verdict. |
| M4 — return and repeat | Guarded withdrawal and Return Home succeed, then a fresh replan/repeat succeeds; save/reopen preserves only intent and requires fresh runtime validation. | Separate operator acceptance closes the applicable loop/playback gates. |

**M4 source audit — 2026-09-23 (no runtime acceptance):**
`returnToTaskHome()` reverses every retained accepted waypoint from Target or
Entry back to captured Home. It sends `retraction` while reversing contact/
drilling waypoints, then `approach` for the remaining accepted path; each
reverse waypoint is checked by the phase guard. It then checks monitored joints
against captured Home and calls `applyTaskHome()`. It does **not** request a new
free-space OMPL Home path. This is a guarded reverse of the previously planned
route, not a fresh Home plan. A stopped, incomplete preview retains accepted
history but `stopGuardedPreview()`/`returnToTaskHome()` refuse return before
endpoint verification; the visible control cannot recover that partial state.
Before changing this fail-closed behavior, Tarun must choose whether a partial
accepted prefix may be reversed under the same guard and monitored-state match,
or must remain blocked pending a separately specified reset/recovery procedure.
No direct Target→Home shortcut or guard relaxation is permitted. This audit
does not authorize M4 runtime or close `S6-LIVE-03`.

Current result (2026-09-22): **`M1-DIAG / HOUSING-OFF PASS`**. The diagnostic
preflight completed P1 with 150 waypoints. Its internally computed P2/P3
completion is retained as diagnostic evidence only; it does not authorize
housing-off preview or M2. Canonical M1 remains open.

Later altered-geometry evidence is not a canonical milestone: at a displayed
45.96-mm incisor gap, one Home yielded no tolerance-valid PreEntry IK endpoint
with empty collision sets, while another Home at the same displayed gap yielded
31 free-space P1 samples and 12 fixed-axis P2 checkpoints before Stage 3
blocked. This supports Home/IK-seed or branch dependence at that geometry; it
does not alone establish a base-placement defect or close M1/M2.

After changing robot-base position and orientation, the operator obtained a
complete housing-on chain at the same displayed 45.96-mm gap: P1 66 waypoints,
P2 10 and P3 22, with `CompletedWithWarnings`. This is a successful
alternate-geometry feasibility result and supports physical placement /
configuration-space clearance as the leading original blocker. It is not
canonical M1/M2 acceptance because base, anatomy and Home no longer match the
Sep-22 baseline; preserve it separately and stop before preview pending review.

Goal 1 already performs a three-stage preflight. Do not add a new stage
controller merely to stop internal computation after P1. Retain what it
computes, but advance user-visible actions only through the accepted milestone.

## Three isolated experiments

### A. Spindle-housing collision envelope

Add
`dentobot_description/urdf/dentobot.diagnostic-no-spindle-collision.urdf` as a
diagnostic copy of canonical `dentobot.urdf` with exactly the named
`pneumatic_spindle-Copy_collision` `<collision>` block absent. Do not generate
or transform URDF/XML at runtime. Add one default-off simulation launch option
that selects this file instead of canonical `dentobot.urdf` before
`MoveItConfigsBuilder` loads `robot_description`. MoveIt, the independent guard,
robot-state publication and SlicerROS2 must therefore consume the same selected
description. Record the selected filename and description identity; never edit
the canonical URDF or add an allowed-collision exception.

Use one tiny exact source check: canonical mode contains the named spindle
collision; diagnostic mode does not; removing that one complete block from the
canonical bytes yields the diagnostic bytes. This establishes that every other
collision body, link, joint, visual, inertial and TCP definition is unchanged
for this experiment. Do not add a general URDF comparison or transform utility.

Keep Home, base, trajectory, anatomy, limits, IK tolerances, candidate policy,
RRTConnect, one attempt, five-second planning allowance, MoveIt padding, guard
clearance and phase policy unchanged. A P1 success is recorded only as
**`M1-DIAG / HOUSING-OFF PASS`** and supports the spindle housing as a
contributing blocker; it does not prove a feasible P1 path for the canonical
robot geometry or close M1. A failure is recorded as
**`M1-DIAG / HOUSING-OFF FAIL`**. After either visible result, stop and return
to Tarun. Do not enter P2/P3 or M2 with the housing disabled unless Tarun
explicitly authorizes that separate diagnostic continuation. Otherwise restore
the canonical URDF before any further milestone or Experiment B.

### B. Task Home connectivity

Only after Experiment A review, restore the complete housing collision model.
Tarun selects and reviews one temporary collision-valid Home nearer a known
PreEntry branch. Preserve base, trajectory, anatomy, limits and planner policy,
and compare the same endpoint where possible. The original package remains
unchanged; save an accepted alternate Home only in a separately named case.

### C. Native search allowance

Only after review, hold Home, model, scene and goal fixed and change the existing
planning allowance from five to fifteen seconds. Retain RRTConnect and one
attempt. Invalid start/goal or scene errors require correcting their cause, not
more planning time. Alternative planners, attempt sweeps, larger seed pools and
new detours require a later operator decision supported by these results.

## Simplicity and verification limits

The purpose is to expose the smallest causal correction and let native MoveIt
carry the planning load. Preserve the existing Cartesian stage planner,
bounded continuity fallback and independent phase guard unless evidence proves
a specific defect in one of them.

- Do not add route types, planner frameworks, generic harnesses, dashboards,
  schemas, databases, speculative recovery paths or duplicate state owners.
- Do not rewrite IK, clean up J6, redesign placement, tune depth/base/geometry,
  expand candidate counts or relax safety policy under this contract.
- Change one parameter class per experiment. Never combine a geometry/model
  change with a Home or planner-policy change.
- Add one smallest meaningful regression for non-trivial changed behaviour.
  Reuse the existing planning checks in `Testing/verification_matrix.json`.
- Do not add per-function tests, duplicated fixtures, broad regression suites,
  repeated agent reviews or full builds without a concrete changed dependency.
- Pure/static checks support a GUI trial; they cannot replace it. Do not rerun a
  complete workflow merely to accumulate evidence when a narrower result has
  already answered the question.
- Preserve the earliest causal error. Apply the existing three-failure ceiling
  across agents and sessions; renaming a run does not reset it.
- Record only evidence needed to compare trials: source/case/model identity,
  changed variable, Task Home and goal joints, stage reached, native result,
  first-invalid pair and a relevant context/close-up view for a new collision.

## Boundaries

This plan authorizes documentation reconciliation only until the operator
separately approves a concrete implementation/runtime milestone. It does not
authorize robot motion, powered spindle, patient work, another tooth, merge,
commit, push, Drive sync or deletion of historical evidence. Housing-off P1 is
diagnostic evidence only; normal M1/M2 and full-cycle acceptance require the
canonical housing-on description unless the operator explicitly defines a
separate diagnostic continuation.
