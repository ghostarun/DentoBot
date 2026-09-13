# DENTOBOT agent context

Last reconciled: 2026-09-14. Routing only; all pending work and current order
live in [backlog.md](backlog.md). Detailed task contracts and completion records
live in [TASKS.md](TASKS.md). Historical attempts are not instructions.

## Start here

1. Read repository AGENTS.md. Read/search all of backlog.md for the request,
   synonyms, workflow step, IDs and overlap mappings before source or planning.
2. Follow every match into TASKS.md and its linked DEVELOPMENT_PLAN / DECISIONS
   sections and relevant dated evidence. Reuse its ID, priority, dependencies,
   ownership and boundaries. Do not load whole logbooks or old checkpoints.
3. For source work use the internal
   [package routing map](../../DENTOWorkflow/Resources/Python/dentobot_workflow/README.md).
4. For checks follow [AGENTIC_VERIFICATION_PROTOCOL.md](AGENTIC_VERIFICATION_PROTOCOL.md)
   and checkout-relative `Testing/verification_matrix.json`.

## Current handoff

- Active P0 owners: `W5-U-04`, `S6-REUSABLE-CASE-SETUP` and `S6-LIVE-01..04`.
  Run central incisors FDI31 → FDI41 → FDI11 → FDI21 independently from the
  unchanged `data/Slicer_Saved/SampleStudy1/dentobot-case-13sept.dentocase`.
  The full gate and failure policy are in
  [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md#2026-09-14-four-central-incisor-exact-case-campaign);
  pending status is in [backlog.md](backlog.md), contract in [TASKS.md](TASKS.md),
  decision in [DECISIONS.md](DECISIONS.md), evidence in
  [2026-09-14 logbook](logbook/2026-09-14.md).
- For each tooth: clean process → 4A–5C → verified STL → production save →
  **new-process** reload → exact Stage 6. Store package, STL, SHA-linked JSON
  and screenshots under `data/Slicer_Saved/SampleStudy1/FDI<nn>/<run-id>/`.
  Advance past tooth-specific first-invalid results; stop on shared
  source/package/fingerprint/runtime failures. The source has all four tooth
  masks, pulp for FDI31/41 and no FDI11/21 pulp; never synthesize missing pulp.
- Existing FDI31 has one current eligible PreparedBranch and automated reopen;
  selected-route planning reached the requested depth. Guarded runtime, clean
  process campaign reload, STL, ten normal-window observations and operator
  acceptance remain open. A manually opened package produced an unlocalized
  fingerprint mismatch; identify its path and expected/actual values first.
- `Testing/run_dentobot_stage6_target_generation.py` already generates/saves
  and reopens in-process; it lacks STL export and fresh-process verification.
  Reuse the exact-case Stage 6 runner separately. Six-target matrix, optional
  32 × 3, Studio, database and platform migration stay downstream.

## Where facts belong

| Need | Authority |
|---|---|
| Pending work / order / next acceptance / overlaps | backlog.md |
| Detailed task contract / completion record | TASKS.md |
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
