# DENTOBOT agent context

Last reconciled: 2026-09-11. Routing only; current task status lives in
[TASKS.md](TASKS.md). Historical attempts are not instructions.

## Start here

1. Read repository AGENTS.md. Search TASKS.md for the request and read the
   matching entry before source or planning. Reuse its ID and boundaries.
2. Read only its linked DEVELOPMENT_PLAN / DECISIONS sections and relevant
   dated evidence. Do not load whole logbooks or old checkpoint summaries.
3. For source work use the internal
   [package routing map](../../DENTOWorkflow/Resources/Python/dentobot_workflow/README.md).
4. For checks follow [AGENTIC_VERIFICATION_PROTOCOL.md](AGENTIC_VERIFICATION_PROTOCOL.md)
   and checkout-relative `Testing/verification_matrix.json`.

## Current handoff

- Immediate P0: `S4A-PULP-ENDPOINT` and `W4-U-02`. The FDI31 screenshot was
  matched to a legacy three-line saved set with no current assisted provenance;
  off-slice point projection and native-mask versus displayed-surface divergence
  explain the contradictory 2D/3D presentation. Source now requires an
  overlapping FDI-matched binary/displayed-surface interval for new assisted
  lines, targets its first shared point, records both boundaries and their
  offset, disables projection, and makes the Step 4A smooth CBCT/mask switch
  operative and state-truthful. Final static/pure and focused Slicer checks
  passed, including display and assisted-pulp markers; no Slicer process
  remained. Next reload and deliberately regenerate the legacy FDI31 set for
  operator normal-window/anatomical review. The combined legacy runner's later
  Step 5B fusion failure is recorded under `W5-U-03`, not this accepted Step 4A
  automated result.
- Active P0: `S6-REUSABLE-CASE-SETUP`. The audit was accepted and its three
  deliverables are implemented in the dirty checkout. Static/pure evidence and
  the focused single-target Slicer target pass; normal-window operator review
  remains the final P0 usability/stale-state gate.
- Required contract: main workflow uses one target tooth, one trajectory
  normally or an explicitly paired two. Step 5B/C prepares a branch containing
  exact trajectory selection, pairing intent, branch-dependent docking/
  insertion inputs, patient shell, unified template, guide references and
  matching verification identity. Step 6 selects that persisted branch ID;
  a raw trajectory pointer is compatibility/UI state only.
- Optional multi-trajectory testing is a separate opt-in workflow using the
  existing 32 × 3 registry and same geometry backend. It must not introduce
  three-trajectory fusion or multi-target preparation into the main workflow.
- Branch switching preserves unchanged shared jaw/landmarks/base/Home/anatomy,
  atomically swaps trajectory selection, pairing intent, matching branch-
  dependent 4C/insertion references, shell, template, guide references and Step
  5C evidence, and invalidates runtime branch state. Step 4C/insertion is not
  case-shared. Package load stays offline.
- Next: record one normal-window operator review of the corrected single-target
  preparation/import and stale-state presentation. No 32 × 3, Stage 3,
  ROS/planner/collision/geometry-policy or Studio work during this patch.
- Stage 3 / `S6-LIVE-01..05` remains pending after workflow integrity.
  Latest recorded FDI11/FDI21 blocker is in TASKS.md; older x4 fractions are
  historical. Full guarded loop and repeat remain unaccepted.
- Major Studio, batch runner, Results, SQLite and platform migration are
  separate queued work, not implicit follow-ups to this task.

## Where facts belong

| Need | Authority |
|---|---|
| Current work order / status / next action | TASKS.md |
| Behavior and acceptance plan | DEVELOPMENT_PLAN.md |
| Decision and explicit supersession | DECISIONS.md |
| Implemented component ownership | ARCHITECTURE.md |
| Environment / release setup | SETUP.md; Workspace/LAB_RELEASE |
| Evidence procedure / exact traces | REPRODUCIBILITY_AND_TRACEABILITY.md; dated logbook |
| Agent/model/permission rules | AGENTS.md; AGENTIC_VERIFICATION_PROTOCOL.md |

Checkout: `/home/light-tarun/dentobot/ros2_ws/src/DentoBot`.
The Ubuntu overlay root is not the development Git checkout.
Preserve all uncommitted work. MRML is geometry authority; source CBCT and
world-RAS/mm conventions remain unchanged. Never infer live validity from
saved evidence. Engineer-owned records are excluded unless specifically named
and authorized. No commit, push, external sync or runtime action follows merely
from reading a roadmap.

A concise daily entry records operator observation, decision delta, changes,
commands/results, evidence limits and next action. Repeated histories belong
neither here nor in the active work order.
