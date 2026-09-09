# DENTOBOT agent context

Last reconciled: 2026-09-10. Routing only; current task status lives in
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

- Active P0: `S6-REUSABLE-CASE-SETUP`. Operator reports faulty unified-template
  creation and stale behavior after Step 6 import. Prior source-complete
  claims do not establish acceptance. The correction plan is approved for a
  read-only audit; that audit is complete, and product implementation is paused
  for audit review and final coding approval.
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
- Next: review the audit/coding gate in
  [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md#s6-reusable-case-setup-correction-plan).
  If accepted, implement exactly one selected-branch ID, one centralized
  eligibility result and one all-or-nothing activation. No 32 × 3, Stage 3,
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
