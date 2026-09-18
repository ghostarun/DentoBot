# DENTOBOT agent context

Last reconciled: 2026-09-18 (Case Foundation AUTO-primary GUI recorded; P5/gate
campaign handoff from 2026-09-17 is unchanged). Routing plus the durable
Step-4A–5B testing
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

- **2026-09-18 — Case Foundation AUTO-primary GUI (source-complete):** Default
  operator path is **Open mouth (AUTO)** → visual confirm → **Confirm and
  continue to Step 4A**. Manual landmarks are fallback only. Headless
  `runtime.auto_open_mouth_test1_post` PASS. This does not resume the P5/gate
  campaign or authorize robot motion.

- **Quota-constrained recovery checkpoint — stop analysis and implement P0 next
  (2026-09-17):** The operator ended the extended read-only audit because the
  USD 20 plan quota was nearly exhausted. Do not restart the audit or spawn a
  replacement review. Existing worker outputs and direct reconciliation support
  four immediate findings: the 15Sept fixture restores two visible FDI31
  representations (closed-source plus opened moving-lower proxy); assisted-entry
  activation fails when Slicer's post-`StartPlaceMode(0)` active-node or
  placement-valid state does not match the expected markup, but the saved run
  lacks the discriminator identifying which postcondition failed; the FDI21
  ownership warning is valid stale-target protection; and P5 has a duplicated
  request ID despite distinct sequence/vector correlation. Preserve corrected
  P3/P4/P5 as diagnostic evidence, keep P5 operator verification blocked, and
  begin future implementation at the shared restore/display-state transition,
  followed by one bounded native placement-state discriminator. No P3–P5 rerun
  or P6/P7 follows from this checkpoint. Full evidence and interrupted-work
  accounting are in the recovery report Section AW and the 2026-09-17 logbook.

- **Active operator route — pause after P5 for GUI verification
  (2026-09-17):** Do not continue the gate/P-series. Preserve locked r4 and all
  P3/P4/P5 artifacts. Route work through `VERIFY-LEARN-01`: inspect r4 without
  mutation, then exercise Assisted Trajectory Generation only in a fresh or
  disposable-copy case and walk the ordinary 4A→4B→4C→5A→5B→5C→6 GUI path to
  its first truthful PASS/failure. r4 already contains the saved 15 September
  trajectory, so its assisted controls are expected to block overwrite. P5
  programmatically reused that trajectory/PreparedBranch and bypassed normal
  Connect/Task Home/workspace/task-confirmation; it is not Operator Verified.
  Record status text, screenshots, save/reopen result and owner mapping. Resume
  only after a controlled-record reconciliation explicitly names the next gate
  after P5; P3–P5 rerun and P6/P7 are not defaults.

- **Campaign 1 is active (2026-09-15):** The operator superseded the former
  Astra/design-only/P4 limit and started implementation in the existing
  `S6-REUSABLE-CASE-SETUP` / `S6-LIVE-01..04` lane. One bounded Luna Max worker
  may implement exact work orders; the main orchestrator owns diagnosis, runtime
  and acceptance. The new FDI31 case preserves r7/r13 and uses the 15Sept
  foundation, supports FDI42/41/32/33, 1.0 mm dock bores, >=2.0 mm
  trajectory-guide/channel values, and the locked Step-4A 15Sept FDI31 markup
  (`5.239400689721231 mm`, member SHA `61dac396...`) as its trajectory input.
  The runner's opt-in parser/import and 1.0-mm dock default are source/unit
  verified (29 focused tests). Revised runtime `c1-gatea-fdi31-20260915-r4`
  then produced and reopened a new corrected FDI31 package with a PASS
  diagnostic, the immutable 5.239400689721231-mm trajectory, and all four
  reviewed supports. Gate A is complete for construction/save/reopen only;
  Gates B-D, physical/clinical review and every hardware path remain NOT RUN.
  The Slicer process returned nonzero during shutdown after emitting PASS, so
  preserve that process-health warning separately; see Campaign 1 and today's
  logbook for hashes and evidence boundaries.
- **P3 corrected static revalidation (2026-09-16):** The operator's explicit
  fourth ceiling exception evaluated only the immutable old-r4 21-vector input
  (input SHA `8853f520...`) with drilling `validate_only` `static_state`
  requests. The fresh raw batch
  `c1-p3-fdi31-20260916-r4-static-revalidation-r4/endpoint_candidates.json`
  (SHA `d5a3ef...`) retained all replies but initially marked them
  inconclusive because native `collision_guard` serializes status vectors with
  `std::setprecision(12)`. The repaired bounded echo check and companion
  evidence `endpoint_candidates.corrected_static_attribution.json` (SHA
  `ec6ad4...`) establish **21 accepted, 0 rejected, 0 unknown and 21
  admissible**; 80 focused checks pass. Generic static rejects all 21 only as
  diagnostic Template↔visual-spindle / target-tooth↔burr contacts. The
  authoritative guard accepts all 21 with its configured non-rotating
  template/spindle warning; no candidate is strictly guide/housing-clear, but
  native self/unrelated/corridor checks pass. P3 conditionally admitted P4;
  no fifth static batch is authorized.
- **P4/P5 bounded diagnostic completion (2026-09-16):** Under later explicit
  operator authority, P4 wrote `c1-p4-fdi31-20260916-r4/insertion_branches.json`
  (SHA `3cc1759d...`) with six complete bounded insertion witnesses. P5 then
  wrote `c1-p5-fdi31-20260916-r4/approach_branches.json` (SHA
  `6455a52e...`), a `SAMPLED_PASS` from a fresh zero-vector monitored
  simulation start through one P4 source-6 witness: 208 Phase-`approach`
  Stage-1 edges, 12 Phase-`terminal_contact` Stage-2 edges and one P4 join,
  all uniquely sequenced `validate_only` requests. The Stage-2 endpoint has
  native FK residual `0.000429 mm / 0.000202°`; native positions and the raw
  joint stream stayed unchanged/off, and the owned stack was torn down. The
  existing Stage-2 Cartesian request first returned no native points and its
  existing bounded position-axis continuity fallback supplied the complete
  diagnostic witness; this is evidence, not a planner/configuration change.
  P5 is not a physical fit, housing-clear, executable-motion, P6/P7,
  withdrawal/Home, repeat, hardware, spindle or patient result. See today's
  logbook and recovery report Sections AU–AV.
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

## Active modular verification rule (2026-09-15)

Routine `dentobot_workflow` implementation modules have an active **1,600-line
context ceiling**. `Testing/test_modular_structure.py` owns this check; the
public entrypoint remains capped at 500 lines, and the existing import,
CMake-install and process/network-boundary checks remain in force. The
intentional `runtime.py`/`slicer_tests.py` exemptions remain unchanged.
`widget_template_build.py` is currently 1,520 lines and therefore passes the
relaxed bounded rule; this is not a blanket exemption or permission to grow
without limit. The API contract remains checked against
`Testing/contracts/dentoworkflow_api.json`.

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
