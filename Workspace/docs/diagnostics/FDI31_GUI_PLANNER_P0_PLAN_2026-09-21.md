# FDI31 GUI planner P0 recovery contract

Date: 2026-09-21  
Owner: `S6-LIVE-01`, continuing through `S6-LIVE-02..05` only after the
operator accepts each preceding milestone  
Status: active operator-superseding plan; implementation/runtime not authorized
merely by this document

## Outcome and authority

Recover the saved FDI31 case through the ordinary visible Step 6 workflow by
using native MoveIt planning as the primary planner and changing one causal
variable at a time. Every visible or demonstrable success or failure stops for
Tarun's manual trial, interpretation and explicit decision before the next
milestone. Routine non-visible implementation findings stay with the
orchestrator and do not interrupt the operator minute by minute.

The sole active case is:

`data/Slicer_Saved/SampleStudy1/FDI31/dentobot-case-sep19-step6.dentocase`

SHA-256:
`b0b38bd7679294da0eead0f4d8a3a2877391847c8e984bb137e93575f456d262`

The earlier controlled-record spelling `step19` was a filename error. The
operator reopened and verified the `sep19` package on 2026-09-21.

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
