# DENTOBOT agent context

Last reconciled: 2026-09-15. Routing plus the durable Step-4A–5B testing
baseline below; all pending work and current order live in
[backlog.md](backlog.md). Detailed task contracts and completion records live
in [TASKS.md](TASKS.md). Historical attempts are not instructions.

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

## Durable Step-4A–5B testing baseline (operator-supplied, 2026-09-15)

Use this as the default new-case/automated-test fixture unless a newer explicit
operator decision supersedes it. It is a research/testing baseline, not
operator acceptance of the inputs, scene, geometry, clinical intent, contact
interpretation or P1/P2. The five screenshot files and the detailed
operator/source separation are retained in
[logbook/2026-09-15.md](logbook/2026-09-15.md) and
`data/dentobot-runs/fdi31-operator-steps4a-5b-20260915/`. Do not rewrite
the frozen 13Sept/r7 evidence to make it match these defaults.

| Step | Selection or derived test output | Default value(s) / expected fixture | Authority and evidence boundary |
|---|---|---|---|
| 4A | Target tooth; optional assisted-entry count | `FDI31`; assisted trajectory count `2` | Target and duplicate closed/opened FDI31 appearance are operator screenshot observations. The duplicate is a defect to investigate, not a second target and not a default. Count is the source/UI default. |
| 4B | Same-jaw support package | Four immediate arch positions: for FDI31, `FDI42`, `FDI41`, `FDI32`, `FDI33` (two on each side). Missing/edge positions do not silently substitute farther teeth; the suggestion is incomplete and requires review. | Canonical helper: `DENTOWorkflow/Resources/Python/dentobot_workflow/logic_guide_support.py`; pure regression: `Testing/test_step4b_support_auto.py`. The four IDs are the operator-confirmed example and the automated expected fixture, not operator acceptance of all scene geometry. |
| 4C | Target reference; dock assembly | Target-crown occlusal dock plane; four independent robot docks | Operator screenshot/source-aligned fixture. The plane's oblique appearance remains a review issue; it is not certified by the parameter table. |
| 4C | Dock dimensions and draft screen | Pattern radius `10.0 mm`; dock outer diameter `3.0 mm`; **robot-dock bore `1.0 mm`**; connector/branch width `3.5 mm`; endpoint overlap/thickness `2.0 mm`; shared depth `5.0 mm`; obstacle clearance `0.5 mm`; yaw `35.0°`; individual depths disabled with each depth `5.0 mm`; measurements visible | New parameter/UI defaults in `parameter_state.py` and `DENTOWorkflow.ui`. The 1.0-mm value is only the registration/robot-dock bore; it is not the drilling trajectory bore. |
| 5A | Visible support and automatic plane | Visible support preview; insertion-aligned support plane; plane depth from Entry `4.0 mm`; crown-cap tilt fit `10%`; boundary sampling `0.5 mm`; terminal support coverage `50%`; polarity reversal off | The 4.0/10/0.5/50 values are source/UI defaults; some lower-crop values were not visible in the supplied screenshot. The oblique plane is an unresolved display/world-frame review item, not accepted geometry. |
| 5B | Undercut/blockout inputs | Undercut angle tolerance `5°`; interproximal relief `1.0 mm`; blockout safety `0.1 mm`; voxel closing `0.3 mm` | Source/UI defaults; these controls were visible in the supplied 5B view. The grey derived-output controls and `Unified template=None` are output/state observations, not defaults. |
| 5B | Shell/guide construction inputs | Shell clearance `0.3 mm`; shell thickness `1.5 mm`; geometry sampling `0.3 mm`; shell channel `2.0 mm`; trajectory-guide outer diameter `4.4 mm`; trajectory-guide hole/bore `2.0 mm`; guide height `2.5 mm`; guide/dock clearance `0.3 mm`; collar radial width `1.0 mm`; collar depth `2.0 mm` | These are source/UI defaults; several are not visible in the supplied screenshot crop. The direct UI field is `templateSleeveInnerDiameterMm` (“Trajectory guide hole diameter”). |

### Non-negotiable trajectory-guide bore rule

The drill-burr/trajectory-guide hole must be **at least 2.0 mm in diameter**;
values below 2.0 mm are invalid and must fail closed. The persisted default
`templateSleeveInnerDiameterMm` is `2.0`, the UI minimum is `2.0`, and
`DENTOGuideGeometry.py` enforces the same floor through
`MINIMUM_TRAJECTORY_BORE_DIAMETER_MM`. The related shell channel
`templateChannelDiameterMm` also defaults to and is UI-bounded at `2.0 mm`.
This rule does not raise the separate Step-4C `targetDockingBoreDiameterMm`
default of `1.0 mm`.

The immutable 13Sept/r7 package may retain a historical `1.5 mm` saved guide
value as rejected evidence. Do not clamp it, rebuild it, or call it a valid
default. A new test case must be initialized at the 2.0-mm floor before
dependent Step 5B/5C geometry is generated.

### Baseline change-control rule

When the operator changes one of these defaults or the 2.0-mm minimum, update
the applicable source and documentation together in the same change:

1. `DENTOWorkflow/Resources/Python/dentobot_workflow/parameter_state.py`
   for the persisted parameter default;
2. `DENTOWorkflow/Resources/UI/DENTOWorkflow.ui` for the visible default and
   UI minimum;
3. the owning normalization/preflight/generator path, including
   `DENTOWorkflow/Resources/Python/DENTOGuideGeometry.py`,
   `dentobot_workflow/widget_template_build.py`,
   `dentobot_workflow/logic_guide_support.py` or the Step-4C docking module as
   applicable;
4. the focused automated fixture/test and
   `Testing/verification_matrix.json` when the selected check changes; and
5. this baseline, the linked `DECISIONS.md`/`TASKS.md` contract and the dated
   logbook evidence.

Never change only workflow code and leave the static context or UI stale.
Verify source/UI parity and the hard-bound test before using a changed value;
do not mutate frozen MRBs, cases, collision policy or retained evidence unless
the operator explicitly authorizes that separate action.

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
