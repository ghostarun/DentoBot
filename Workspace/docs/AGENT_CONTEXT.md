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

- **Latest FDI31 override (2026-09-14):** The operator accepted the causal review
  and requested Astra architecture / Luna Max implementation orchestration.
  Read [Campaign 1](diagnostics/FDI31_PLANNER_RECOVERY_CAMPAIGN_1.md) and its
  TASKS/DECISIONS supersession before following older geometry-only/one-packet
  next-action text below. Design issued; execution not authorized. P0 baseline,
  P1 scene/operator review with P2 diagnostics, P3 endpoint, conditional P4
  insertion, then R1/Astra; no automatic next tooth or full-flow retry.
- Active P0 owners: `S3-P0-DENTAL-SEMANTICS`, `W5-U-04`,
  `S6-REUSABLE-CASE-SETUP` and `S6-LIVE-01..04`.
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
  Record tooth-specific first-invalid results and propose the next tooth only
  after operator approval; stop on shared
  source/package/fingerprint/runtime failures. The source has all four tooth
  masks, pulp for FDI31/41 and no FDI11/21 pulp; never synthesize missing pulp.
- Existing FDI31 has one current eligible PreparedBranch, current STL and
  save/reopen evidence. The approved current-source exact check reached the
  requested target endpoint but stopped at the first native Stage-3 guard
  collision between the selected tooth and `pneumatic_spindle-Copy`.
  Goal 2/Return Home, repeat/playback and ten normal-window observations are
  not accepted. Preserve the first-invalid evidence; do not relax the guard,
  shorten depth, move the base or start another tooth automatically.
- The operator manually selects Luna Max for this campaign. Continue the fixed
  path for classified failures; stop before an ambiguous or unplanned
  higher-reasoning fix and give the evidence/reasoning-type packet specified in
  DEVELOPMENT_PLAN.md. Never switch models or delegate automatically.
- **One packet only:** The generator STL/folder/diagnostic edit is implemented.
  The operator explicitly approved the bounded offline Slicer/ROS/MoveIt check
  for the current FDI31 semantic implementation, with no robot motion or
  patient-facing action. That current-source check ended at the target-specific
  Stage-3 first-invalid collision; preserve its r13 artifacts and wait for a
  compliant guide/tool/base geometry correction and explicit recheck approval.
  Do not start FDI41, FDI11 or FDI21 automatically.
- `Testing/run_dentobot_stage6_target_generation.py` already generates/saves
  and reopens in-process; it lacks STL export and fresh-process verification.
  Reuse the exact-case Stage 6 runner separately. Six-target matrix, optional
  32 × 3, Studio, database and platform migration stay downstream.
- `S3-P0-DENTAL-SEMANTICS` owns the source-only semantic-bridge plan. The
  current parser derives category/FDI from display names and assisted
  planning matches pulp by that derived FDI; the reviewed source package has
  no FDI11/FDI21 pulp. Do not make a new pulp-dependent planning claim until
  target tooth, pulp geometry and spatial association are canonically
  validated. Keep `S4A-PULP-ENDPOINT` as the endpoint-geometry owner and
  `S6-REUSABLE-CASE-SETUP` as the package/campaign owner.

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
