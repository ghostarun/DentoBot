# Step 6 GUI automation SOP — diagnostic planner runs

Scope: simulation-only automated checks under `S6-LIVE-01`. The canonical
[planner contract](FDI31_GUI_PLANNER_P0_PLAN_2026-09-21.md) and
[verification protocol](../AGENTIC_VERIFICATION_PROTOCOL.md) govern approval,
retry limits, safety, and acceptance. This checklist constrains test scripts;
it does not authorize a runtime or change the clinical/simulation guard policy.

## Before writing or running a script

- [ ] Use an approved, SHA-identified source DentoCase and a fresh output
  directory. Never overwrite the source or infer target identity from a filename.
- [ ] Confirm the exact FDI target, trajectory, PreparedBranch, robot profile,
  base/world transform, Task Home joints, collision audit, workspace review,
  and task snapshot. Save those identities with the result.
- [ ] Use the production GUI/facade sequence and its ordinary gates. A saved
  case does not restore ROS, Task Home, collision-scene, workspace, or guard
  validity. Revalidate in the current process before planning.
- [ ] Run one Slicer/ROS/MoveIt stack at a time; use the existing handoff and
  clean up owned processes. No hardware, robot command, geometry edits,
  guard bypass, allowed-collision exception, or automatic base/Home change.

## Trial and evidence sequence

- [ ] Freeze target/trajectory/branch, base, Home, scene, and settings for a
  comparison. Keep attempts/time equal; run the configured planners in the
  recorded order. Stop remaining trials on changed identity or unsafe/fatal
  state; mark them `NotRun`, not failed planners.
- [ ] After each trial retain its requested/configured planner IDs, exact
  error, stage and first-invalid waypoint, full diagnostic session, and
  full-precision J1–J5 representative complete/last-valid path. A configured
  ID is not proof of the OMPL algorithm actually executed.
- [ ] Write and flush a timestamped progress record at setup, each trial
  start/end, each major IK/MoveIt/Cartesian/guard phase, screenshot, save, and
  stop/timeout. Include UTC wall time for cross-process log correlation and a
  monotonic elapsed duration; retain the active planner/candidate/stage and
  source identity. A timeout must leave its last completed checkpoint and
  active phase inspectable, not only a stack log.
- [ ] Capture one screenshot per planner row with that row and its blocker
  selected, plus a base/Task Home context screenshot. For any collision blocker,
  also capture the selected first-invalid state and named offending pair from
  inferior, apical, and oblique views before the next planner trial. Retain
  pair IDs, exact joints, camera-view labels, and image paths; distinguish
  display-only model reconstruction from native collision geometry. If the
  first-invalid state or pair cannot be shown, record why and stop remaining
  trials for operator review. Never substitute a table screenshot for these
  views or infer contact depth from pixels. Native guard/numeric evidence is
  authoritative; the images exist so Tarun can judge the geometry.
- [ ] For each failure, explicitly assess whether base-mount placement and/or
  Task Home *could* be relevant: separate no-IK-endpoint, Home→PreEntry
  connectivity, and later collision/phase-guard failures. Compare exact base,
  Home, joint limits, and first blocker with a controlled prior run. Label an
  untested adjustment a hypothesis, never a demonstrated fix. Do not move the
  base or Home inside a comparison or infer physical clearance from planner
  fractions alone.
- [ ] A failed prerequisite or missing diagnostic session makes the batch
  incomplete; do not count it as a planner comparison. Preserve screenshots
  and first error, then stop for diagnosis and operator verdict.

## Save, reopen, and stop

- [ ] Save each target's comparison under its PreparedBranch in a new DentoCase.
  On fresh-process, ROS-disconnected reopen, verify all reports and display-only
  paths are inspectable while guarded preview remains unavailable.
- [ ] Keep FDI21 and FDI31 reports separate. Do not feed the next target from
  an incomplete or identity-stale comparison case.
- [ ] Present every visible GUI success/failure, collision views, and screenshots
  for Tarun's manual verdict before proposing a geometry/base/Home/planner fix
  or another expensive trial. A request for mere approval without the visual
  evidence and a concrete operator question is not an adequate handoff. Do not
  rank a planner “better” when an insertion envelope, collision, or guard
  independently blocks the task.
