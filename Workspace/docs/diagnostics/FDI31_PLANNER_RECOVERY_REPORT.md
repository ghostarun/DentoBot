# FDI31 Planner Recovery Campaign 1 — Canonical R1 Recovery Report

Status: **P1 saved-input/machine checks PASS / P1 overall scene correctness and operator review INCOMPLETE / P2 bounded native diagnostic PASS with USER_REVIEW_REQUIRED / P3/P4 unauthorized**  
Campaign result: **NOT COMPLETE**  
Run: `c1-p1p2-recheck-20260914-r6` (prior execution: `c1-p1p2-20260914-r1`; readiness audit: `c1-p1p2-recovery-20260914-r1`; P0 baseline: `c1-p0-20260914-r1`)  
Captured: `2026-09-14T12:10:55Z`  
Campaign specification: `Workspace/docs/diagnostics/FDI31_PLANNER_RECOVERY_CAMPAIGN_1.md`  
Source checkout: `/home/light-tarun/dentobot/ros2_ws/src/DentoBot`  
Workspace root for durable data: `/home/light-tarun/dentobot`

This is the single canonical Campaign-1 handoff report. P0 froze the four
durable manifests and retained the decisive r13/r14 evidence. The operator
then explicitly approved P1/P2 only. P1 completed its saved-input and machine
checks and saved a rotatable inspection scene, but overall scene correctness
and operator review remain **INCOMPLETE**. The later bounded recovery found
that the shared container had not crashed: Docker recorded `Exited (143)`
with `OOMKilled=false` immediately after a task cleanup command signalled the
task-owned process group; the container runs `sleep infinity` as PID 1 and has
restart policy `no`, so it stayed down after that SIGTERM. The container was
started in place under the operator's explicit authorization, and the final
recheck used a no-TTY, single-command handoff with nested timeouts.

The final packet contains native FK, separate phase-aware static and
validate-only transition results, and a correlated 31-object scene
acknowledgement with matching IDs/poses/bounds/policy. TCP, spindle and burr
display transforms all match native FK. The corrected handoff reached Slicer,
entered the diagnostic, produced the labelled captures and rotatable MRB, and
cleaned only its helper-owned stack; the run-created ROS CLI daemon was then
stopped through its own ROS command. The packet's machine/evidence result is
**PASS**, while the Campaign-1 gate remains **USER_REVIEW_REQUIRED** and no
operator acceptance is recorded. No P3/P4, P5-P7, full-flow retry,
repeat/playback, normal-window acceptance, motion, controller, powered
spindle or patient-facing action occurred.

## A. Executive

P0 is **PASS** because the frozen source/case/task/build identities are
attributable, the essential r7 inputs are present and hash-matching, the r13
and r14 records are retained, and every unavailable or non-authoritative item
is explicit. P1's saved-input and machine-auditable checks are **PASS** for
the checks actually completed; P1 overall scene correctness and operator
review are **INCOMPLETE**. P2 bounded native diagnostic evidence is **PASS**,
not a planner or clinical acceptance result: the final packet loaded the
local seven-link native robot and obtained two native candidate
reconstructions, with separate static-state and Home-to-endpoint transition
records. The final scene acknowledgement reconciled all 31 expected objects
by IDs, poses/bounds and policy, and the displayed TCP/spindle/burr transforms
matched native FK. This is not a negative Target or contact verdict. The
campaign remains **USER DECISION REQUIRED** because operator review is open:
no Campaign-1 endpoint or insertion result has been produced. The readiness
audit and subsequent authorized replacement inventory are recorded in the recovery history; the original audit is at
`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recovery-20260914-r1/runtime_readiness.json`.

The furthest relevant prior evidence is r13 Stage 1 and Stage 2 pass, followed
by exact-target endpoint arrival for both retained candidates. The blocking
observation is the r13 Stage 3 first-invalid collision between the selected
FDI31 tooth and `pneumatic_spindle-Copy`. The current evidence does not prove
whether the decisive cause is scene construction, tool collision modeling,
IK-branch coverage, or another upstream/guard interaction. The Campaign-1
classification is therefore:

`UNKNOWN` — low confidence; leading but unproven hypotheses are
`TOOL_COLLISION_MODEL` and `SCENE_CONSTRUCTION`.

The approved envelope was executed only through P2 in
`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p0-20260914-r1/execution_envelope.json`.
It remains stopped at the required decision-critical review. The envelope
contains no motion and does not authorize P3/P4 without a new decision; it also
does not authorize P5–P7, full-flow retry, repeat/playback, or normal-window
acceptance. Required review now is: P1 automatic input/scene selections and
geometry evidence; P2 the separate static/transition records, the reconciled
native scene acknowledgement, the TCP/spindle FK evidence, and the unresolved
burr FK/display pairing; then a separate explicit decision before any P3
consideration.

## B. Baseline

All paths below are relative to `/home/light-tarun/dentobot` unless stated
otherwise. The complete machine-readable records, including schema, case/task
identities, frames/units, policy fingerprints and completeness, are:

| Artifact | SHA-256 | P0 role |
|---|---|---|
| `data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p0-20260914-r1/baseline.json` | `608bdbd7eaf0fb758c3f2d16174655ea7ede6396c298aee490e0a245d4460b33` | Baseline and decision record |
| `data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p0-20260914-r1/invariants.json` | `f0fa8284d4e125aa72c124f125a4bf4188569874d6ca3247d7106c78a1988c41` | Frozen invariants |
| `data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p0-20260914-r1/source_state_manifest.json` | `8fd85587d3f2e53dd5dbeed3549b89a7a07593c1a92eacb9e5c73cde231e1c06` | Pre-P0 source/build/diff boundary |
| `data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p0-20260914-r1/execution_envelope.json` | `866dc401248a7c015eae4e87c987650b53ecfdc12eac93542c90f1f79100e8` | Single pending P1–P4 envelope plus final r6 recovery/recheck disposition |

### Immutable case and evidence identities

| Input/evidence | Size | SHA-256 | Interpretation |
|---|---:|---|---|
| `data/Slicer_Saved/SampleStudy1/dentobot-case-13sept.dentocase` | 80,296,833 bytes | `14ed8f0f61e0c791d31b9582af7969ce712dd80d8cfd3a33319da63d0a996a15` | Immutable source case; schema 2.0; `PartialOrInspectable`; eight expected members; `testzip()` PASS |
| `data/Slicer_Saved/SampleStudy1/FDI31/packet-a-fdi31-20260914-r7/FDI31-step5c.dentocase` | 87,641,389 bytes | `5440961c2f1464df10adec3dfb6ab59f8a0e412c6074cae7852d8150babe4fff` | Current FDI31 prepared branch; schema 2.0; `PlanningPackage`; eight expected members; `testzip()` PASS |
| `data/Slicer_Saved/SampleStudy1/FDI31/packet-a-fdi31-20260914-r7/DENTO_Final_Printable_Template.stl` | 2,943,484 bytes | `ccee3e597b7e579b0224a31f00308ee1d65e42bc89ac17bf9c68330d5bcec425` | Verified r7 binary STL |
| `data/Slicer_Saved/SampleStudy1/FDI31/packet-a-fdi31-r7/diagnostics/FDI31-stage6-exact-r13.json` | 217,249 bytes | `0e4683c8def9584abddface6655c49451e1a642e41f0568c08fe342dad09c32b` | Retained r13 native diagnostic sidecar |
| `/tmp/dentobot-verification/step65-fdi31-20260914-r13/runtime.log` | 330,234 bytes | `ad123be24bba0eec318693867b5ca607d6488f5225a40ab38e8b1ae275395614` | Retained r13 runtime log; copied durably |
| `/tmp/dentobot-verification/step65-fdi31-20260914-r14-runtime.log` | 252,252 bytes | `a03a747434f3014fa725723a233cdc3c8f243a52275c56df6f5174edf6a7e02d` | Retained r14 endpoint-probe log; copied durably |

The durable retained copies are under
`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p0-20260914-r1/retained/`
and have the same hashes as their sources:

- `FDI31-stage6-exact-r13.json` — `0e4683c8def9584abddface6655c49451e1a642e41f0568c08fe342dad09c32b`
- `step65-fdi31-20260914-r13-runtime.log` — `ad123be24bba0eec318693867b5ca607d6488f5225a40ab38e8b1ae275395614`
- `step65-fdi31-20260914-r14-runtime.log` — `a03a747434f3014fa725723a233cdc3c8f243a52275c56df6f5174edf6a7e02d`

The r14 sidecar is not used as authoritative evidence: the prior probe's
sidecar was overwritten by planner fallthrough. The r14 runtime log remains
useful for its explicitly limited 22-seed/8-solution observation.

### Frozen task, frame and robot state

- Target: FDI31, segment
  `2.25.127809691704402484963988182477922906518`.
- Prepared branch: `guide-5c0da27697aceceb8f14`, state `Current`, pairing
  `Single`, one prepared branch.
- Target ID: `target-7b23d5dd81128f7e670a`; primary trajectory ID:
  `trajectory-3aa3d91ffabaec396e62`.
- Trajectory revision and fingerprint:
  `949e918bac87ba2a522662ce7b304f81007a3004988dc957609091deee4e687f`.
- Entry in SlicerRAS/mm:
  `[-95.57978088281602, -68.3080212750595, 32.524279290412125]`.
- Target in SlicerRAS/mm:
  `[-95.07911746332762, -74.1254665588325, 29.29612472144273]`.
- Requested drilling depth: `6.67190493116205 mm`.
- Target tool axis in SlicerRAS:
  `[0.07504055058548376, -0.8719316812507053, -0.48384301069576907]`.
- Task/snapshot fingerprint:
  `24fb0b6d5ae95d5130d97e411ffb3e24ef970da5f0a4f4cebc78d17a349322d3`.
- Case world/unit contract: `SlicerRAS/mm`; native robot contract:
  `base_link/metres`; no RAS/LPS conversion introduced by Campaign 1.
- Robot profile fingerprint:
  `a0a802c0969546585aa5198d9c31bfb281d969235baa2eaa857718a2f8f146aa`.
- Tool frame and identity: `dentobot_drill_tcp`; tool provenance is
  CAD-derived, provisional and uncalibrated.
- Burr diameter: `1.0 mm`; guide bore diameter/floor: `2.0/2.0 mm`.
- Spindle TCP axial extent: `-20.650002` to `-6.999999 mm`; burr extent:
  `-7.0` to `0.0 mm`; retained nominal axial margin: `0.328095 mm`.
- Base: manual-simulation, `ProvisionalLocked`, revision 2, fingerprint
  `f1f2a7f37643064fe66e8a73a62ca0634bfde4a61c1fe87688185986d834d46b`.
  The full row-major transform is in `invariants.json`.
- Jaw: saved package records PureTMJHingeRotation, target gap `40.0 mm`,
  opening revision 1, current saved opening `false`; full transform and
  source-geometry fingerprint are in `invariants.json`.
- Planning contract: J1–J5 only; J6 excluded and locked at zero for
  compatibility; position tolerance `0.25 mm`; axis tolerance `0.5°`.

### Prior pair, stage and state

r13 Stage 1 free-space and Stage 2 fixed-axis terminal passed with fraction
`1.0`. Both retained candidates reached the exact requested target endpoint.
Stage 3 drilling failed first at local stage index `27`:

- Candidate 0: composed index `255`; first-invalid RAS
  `[-95.07844530436523, -74.12553331997093, 29.29612205796616]`.
- Candidate 1: composed index `295`; first-invalid RAS
  `[-95.07844529824126, -74.12553331971363, 29.296122059962528]`.
- Guard pair in both cases:
  `dentobot_target_tooth_2.25.127809691704402484963988182477922906518` vs
  `pneumatic_spindle-Copy`.
- The sidecar's `last_valid` vector equals the rejected vector. A preceding
  guard-accepted state is therefore unknown; no missing clearance is converted
  to zero.
- r13 recorded planned/IK candidates `2`, collision-aware candidates `2`,
  Cartesian count `1`, drilling-preflight count `1`, and guide warnings `40`
  with `8` contact warnings. These are prior observations, not Campaign-1
  measurements.

## C. Changes

| File/output | P0 nature | Reason and evidence | Verification | Invariants |
|---|---|---|---|---|
| `.../c1-p0-20260914-r1/baseline.json` | Evidence manifest; diagnostics-only | Freeze attributable inputs, prior evidence and decision boundary | JSON parse and recorded package/hash checks PASS; SHA `608bdb...0b33` | Unchanged |
| `.../c1-p0-20260914-r1/invariants.json` | Evidence manifest; diagnostics-only | Freeze task, scene, robot, tool, frame, joint, guard and prohibited-change contracts | JSON parse PASS; SHA `f0fa...8c41` | Defines, does not alter |
| `.../c1-p0-20260914-r1/source_state_manifest.json` | Evidence manifest; diagnostics-only | Distinguish pre-existing dirty source/build state from P0 outputs | JSON parse PASS; SHA `8fd855...1c06` | Source is read-only |
| `.../c1-p0-20260914-r1/execution_envelope.json` | Approval/execution record; diagnostics-only | Bound P1–P4 commands, resources, outputs, stops and approvals; record the approved P1/P2 result and readiness disposition | JSON parse PASS; corrected P1/P2 status fields recorded below | Frozen invariants unchanged |
| `.../c1-p0-20260914-r1/retained/*` | Evidence copies; diagnostics-only | Preserve ephemeral r13/r14 evidence before later work | All three copy hashes equal source hashes | Source evidence untouched |
| `Testing/run_dentobot_fdi31_recovery_diagnostic.py` | P1/P2 diagnostic runner | Stop at the selected phase, audit saved inputs, reconstruct only bounded diagnostic state and save evidence | `py_compile` PASS; focused tests PASS; P1 saved-input/machine checks PASS with overall scene review INCOMPLETE; P2 INCONCLUSIVE | No production planner/guard/geometry/policy change |
| `Testing/test_fdi31_recovery_diagnostic.py` | Focused diagnostic tests | Cover phase gate, null/unknown handling, contact record and MRML-like serialization | `5 passed in 0.02s` | Test-only |
| `Testing/verification_matrix.json` | Verification routing | Add explicit P1/P2 rows with approval, serialized resources and inner timeouts | JSON/path check PASS; rows used for the two approved phases | No existing acceptance row relaxed |
| `.../c1-p1p2-20260914-r1/*` | P1/P2 evidence outputs | Preserve workflow-ordered selections, scene/state/contact records, screenshots and rotatable scenes | Output manifests and hashes below | Source/r7/r13/invariants untouched |
| `.../c1-p1p2-recovery-20260914-r1/runtime_readiness.json` | Readiness-audit evidence | Record the one bounded read-only startup/process/discovery audit and exact pre-launch stop | JSON parse and SHA recorded in Section J | No process, package, dependency or invariant change |
| `Workspace/docs/diagnostics/FDI31_PLANNER_RECOVERY_REPORT.md` | Canonical development-controlled report | Make the single A–O evidence handoff and review stop | Readback/link/hash inspection recorded below | No production behavior |
| `Workspace/docs/logbook/2026-09-14.md` | Development-controlled record | Record operator scope, commands, results, boundaries and next action | Appended in the P1/P2 execution turn | No production behavior |

No production Python, C++, URDF, SRDF, mesh, planner, IK, collision policy,
tolerance, case, geometry, target, trajectory or build-system file was edited
for P1/P2 or the readiness audit. The only source-checkout additions/edits for
this execution were the allowlisted diagnostic runner, its focused tests, and
the two explicit recovery-matrix rows. No native build was needed because no
C++ file changed; the readiness audit also did not launch or modify a native
process.

## D. Gates

`NOT_TESTED` is used for an unexecuted gate; it is not a negative result.

| Gate | Execution | Result | Decision | Exact input/test | Quantitative evidence | Artifact/hash | Interpretation |
|---|---|---|---|---|---|---|---|
| Scene | P1 technical portion completed | `INCOMPLETE` overall: saved-input/machine checks `PASS`; scene correctness and operator review pending | Operator review required; automatic selections are not accepted | Frozen source case plus r7 package scene audit in workflow order | Endpoint identity, Case Foundation and PreparedBranch checks PASS; rotatable scene saved; all 15 automatic selections remain review-required; runner 3-D captures are not decision-quality | `scene_audit.json` SHA `283ff851...7896`; P1 scene SHA `911a98ef...2d8b`; readiness audit `runtime_readiness.json` | Machine reconciliation passed; anatomy/geometry acceptance remains with operator |
| Endpoint | C1 P3 not begun | `NOT_TESTED` | P4 ineligible until P3 PASS | One future 128-seed native endpoint batch | C1 completed `0/128`; prior r14 was 22 seeds/8 solutions and non-exhaustive | r14 retained log `a03a...7e02d` | No Campaign-1 endpoint feasibility claim |
| Insertion | P4 not begun | `NOT_TESTED` | Conditional on P3 PASS and approval | Future Target→Entry and reverse Entry→Target sampled validation | Retained C1 candidates `0`; no insertion solves | No P4 artifact exists | No insertion witness or clearance claim |
| Approach | Not authorized | `NOT_TESTED` | Not eligible in Campaign 1 envelope | No Stage 1 approach rerun; no full-flow retry | Prior r13 Stage 3 first invalid only; no new approach evidence | r13 retained sidecar `0e468...c32b` | Approach/full workflow remains unproven |
| Guard consistency | P2 completed with one bounded readiness recovery and final r6 native recheck | `INCONCLUSIVE` | Diagnostic trust review required; no P3 | Frozen r13 candidate vectors plus native FK/static/`validate_only` probes; exact 31-object payload audit; read-only scene-fingerprint check | Native context ready; 2 candidates; both kinematically valid at the recorded endpoint, both static-invalid with native contacts; task guard rejected both for corridor progress about `-0.03699`; native scene acknowledgement reported expected `31`, observed `0`, while the later guard reported `world_object_count=31` | r6 `rejected_state.json` SHA `a03092a6...cdbf2`; `state_identity.json` SHA `06ca3a09...6dedb`; `contact_records.json` SHA `16d24c31...83f7`; P2 scene SHA `a19bd699...4ec2` | Native data is useful but not fully reconciled; no exact r13 preceding accepted edge or native TaskJointStatus contact pair was established |
| Full workflow | Not authorized | `NOT_TESTED` | No normal-window or full-cycle decision | No Goal 2, Return Home, repeat, playback or full-flow test | All downstream counts `0` in P0; no motion allowed | `baseline.json` `608bdb...0b33` | Campaign 1 does not establish end-to-end acceptance |

## E. Endpoint

Campaign-1 P3 has planned/completed seed counts **128/0**: up to 32 recorded
anchors followed by 96 deterministic Halton samples in J1–J5 limits. No C1 IK,
TCP, axis, limit, guard, branch-cluster or rejection counts exist yet.

The prior records are deliberately kept separate from C1:

- r13 retained two planner candidates; both reached the exact target endpoint,
  then hit the same forbidden target-to-spindle pair during Stage 3.
- r14 retained a 22-seed endpoint probe with 8 solutions within native
  tolerances. All eight stayed on the same J5 branch. This is branch evidence,
  not exhaustive IK coverage, and its sidecar was overwritten, so no
  authoritative raw-to-dedup mapping is available.

The exact retained r13 first-invalid vectors are:

```text
candidate_0
  composed_index: 255; stage_index: 27
  first_invalid_ras_mm: [-95.07844530436523, -74.12553331997093, 29.29612205796616]
  joints_si [J1..J5]: [0.11089267804897232, 0.05864749681697649,
    -0.5871859934879949, 0.06682603068607332, 0.8610525207602283]

candidate_1
  composed_index: 295; stage_index: 27
  first_invalid_ras_mm: [-95.07844529824126, -74.12553331971363, 29.296122059962528]
  joints_si [J1..J5]: [0.11089128923636037, 0.05864708713631075,
    -0.5871966867382767, 0.06682583178152643, 0.8610474214727073]

guard_pair:
  dentobot_target_tooth_2.25.127809691704402484963988182477922906518
  pneumatic_spindle-Copy
contact_point: null (not decision-quality evidence)
preceding_guard_accepted_state: null (r13 last_valid caveat)
```

The complete structured copy is
`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p0-20260914-r1/retained/FDI31-stage6-exact-r13.json`
with SHA `0e4683c8def9584abddface6655c49451e1a642e41f0568c08fe342dad09c32b`.

P3's hard limits in the pending envelope are: exactly one batch; maximum 128
IK solves; unchanged position/axis tolerances of `0.25 mm/0.5°`; J1–J5 only;
no artificial J6/housing-roll sweep; every converged candidate checked by the
unchanged native phase-aware predicate before deduplication; and at most eight
ranked representatives retained. A zero result would mean only
`NO VALID TARGET SOLUTION FOUND IN BOUNDED SEARCH`, not infeasibility.

## F. Insertion

P4 is **NOT_TESTED**. C1 retained candidates: `0`; accepted insertion
witnesses: `0`; rejected insertion states: `0`; measured continuity,
singularity, edge, contact and available-clearance values: `null` because no
P4 run occurred. The fixed Entry/Target pair is the one in Section B. No
method, axial resolution, midpoint refinement or raw-to-dedup result may be
claimed yet.

The two r13 candidates are not insertion witnesses. They reached the requested
endpoint but were rejected during the retained Stage 3 chain; the preceding
accepted guard state is unknown. All C1 candidate coverage remains uncovered
until P3 produces admissible representatives and P4 is separately authorized.

## G. Approach

**NOT_TESTED.** No Campaign-1 approach run was authorized or run. There is no
new start pose, PreEntry, Entry, pipeline, planner setting, seed, attempt,
path join or approach rejection artifact. The prior r13 first-invalid Stage 3
observation does not establish a successful approach or a full workflow.

## H. Guard consistency

C1 P2 first attempted the bounded per-state reconstruction without a usable
native comparison because the required ROS/MoveIt/guard interfaces were
absent. The later operator-authorized recovery identified and gracefully
stopped only the seven conflicting DentoBot simulation processes, then used
the existing `simulation.launch.py` components on domain 73. The launch path
was source-inspected before use: it starts description, MoveIt and the
simulation guard/status publishers; it does not start hardware or controllers,
sets `allow_trajectory_execution=false`, and logs that no controller manager
is configured, so no path can execute. MoveIt still advertises its standard
execution action endpoint; that endpoint advertisement is recorded as a
startup side effect, not as trajectory execution. The Slicer joint-state
publisher explicitly reports no robot-command or hardware interface.

The final r6 native probe reached `ready:true`, loaded the native robot,
verified all five frozen task-identity checks, and reconstructed both retained
r13 candidate vectors. MoveIt FK was finite and within the unchanged target
tolerances for both candidates (position error about `0.000675 mm`, axis error
`0.000257°` / `0.000715°`). Authoritative static validity rejected both with
the native contact set `[Step 5C] DENTO Final Printable Template` ↔
`pneumatic_spindle-Copy`, target ↔ `burr`, and target ↔
`pneumatic_spindle-Copy`. The phase-aware task guard separately rejected both
validate-only samples because the provisional tip was outside the approved
Entry-to-Target corridor (`corridor_progress` about `-0.03699`); its status
reported `world_object_count=31`, no TaskJointStatus body pair, and native
world clearances about `0.0209146 m`. These are native measurements, not
display-only reconstruction data.

P2 nevertheless remains **INCONCLUSIVE** under the campaign specification:
the exact Step-6 collision-payload acknowledgement recorded `expected 31,
observed 0` before the later guard status reported 31 objects, and the native
static collision pair was not reproduced in the TaskJointStatus pair fields.
The setup-handshake accepted state and housing-clear state are real native
setup observations but are not the preceding accepted state of r13. The
retained r13 pair, first-invalid point and display-only markers remain
historical/reconstruction evidence. No exact r13 edge or collision onset was
established; depth/onset/nearest-point/count/truncation fields remain unknown
where not exposed. Guard policy, geometry, tolerances and authorized contacts
remain unchanged.

## I. Visuals

P1/P2 produced the required saved-scene and capture set, but the evidence has
an explicit visual-quality boundary:

- P1 saved-input/machine checks: source/r7/package/foundation/PreparedBranch/
  target/line identity checks PASS. P1 overall scene correctness and operator
  review are **INCOMPLETE**; every automatic selection is still
  `operator_confirmed_in_this_run=false` and `operator_review_required=true`.
- Rotatable P1 scene: `.../inspection-scene/fdi31-p1-scene.mrb`, 87,662,026
  bytes, SHA `911a98ef...2d8b`; serialized ROS motion/runtime flags are false.
- P2 final rotatable scene: `.../c1-p1p2-recheck-20260914-r6/inspection-scene/fdi31-p2-rejected-state.mrb`,
  87,804,930 bytes, SHA `a19bd699...4ec2`; scene fingerprint was unchanged
  across the probe and serialized ROS motion/runtime flags are false. The
  earlier r1/r4/r5 scenes remain versioned retry history.
- Useful context image: `screenshots/p1-reopen-helper/reopened-ui.png` is a
  bounded existing reopen-helper capture showing the Slicer UI and rendered
  case/guide context; it is limited/crowded and not geometry acceptance.
- Final r6 P2 images are nonblank and labelled: context, target/goal robot,
  first-invalid close-up, and displayed-surfaces-versus-collision-audit
  payload. The last image uses separate display-only colours/labels; it is not
  a native collision rendering.
- Native r6 state evidence identifies `first_guard_rejected` and
  `last_kinematically_valid` at the bounded reconstructed Stage-3 sample, plus
  a setup-handshake `last_guard_accepted`/`last_housing_clear`. The setup
  states are explicitly not the preceding accepted r13 edge. The r13
  `last_valid` equals the rejected vector and is not promoted to one.
- The native static validity contact set is recorded in the r6 state JSON;
  TaskJointStatus pair, nearest points, contact count/truncation, native
  penetration and native drilling-depth fields remain null/unknown where not
  exposed. No visual, native/test PASS, or generated flag is treated as
  operator acceptance.

## J. Tests

P0 used only the cheapest read-only checks required by the campaign:

| Check | Exact command/action | Result/marker | Identity and artifact |
|---|---|---|---|
| Source inventory | `git rev-parse --show-toplevel; git rev-parse HEAD; git status --porcelain=v1; git diff --stat` in the specified checkout | PASS; `main` at `3af2d864449679ead25398899d6325aefb50595a`; 54 tracked modified, 13 untracked, 0 deleted before P0 outputs | Full lists and hashes in `source_state_manifest.json` |
| Case package structure | Python `zipfile` `testzip()` plus expected-member and manifest JSON inspection for source/r7 bundles | PASS; both `testzip()` returned `null`, eight expected members, schema 2.0 | Source/r7 hashes in `baseline.json` |
| Package checksum fields | Read `integrity/checksums.sha256` and compare recorded scene/workflow/robot members | PASS; recorded internal identities retained | `baseline.json` |
| Prior diagnostic JSON | Python `json.load()` and selected task/motion/stage/detail fields from r13 sidecar | PASS; exact target, fingerprints, stage and first-invalid fields parsed | r13 source and retained-copy SHA `0e468...c32b` |
| Evidence retention | `cp -p` r13/r14 logs and r13 sidecar into the durable run, then `sha256sum` source/copy pairs | PASS; all three retained copies equal source hashes | Durable `retained/` directory |
| P0 manifests | `jq -e .` on `baseline.json`, `invariants.json`, `source_state_manifest.json` and `execution_envelope.json` | PASS; all four parse successfully | Four hashes in Section B |
| P0 boundary | Read-only source/config/case/build inspection; no execution command | PASS; no Slicer, ROS, MoveIt, Docker/container, test runner, build or motion process started | This report and logbook |

P1/P2 used the cheapest applicable checks from the verification matrix before
the serialized runtime rows:

| Check | Exact command/action | Result/marker | Identity and artifact |
|---|---|---|---|
| Recovery syntax | `PYTHONPYCACHEPREFIX=/tmp/dentobot-c1-p1p2-pycache7 python3 -m py_compile Testing/run_dentobot_fdi31_recovery_diagnostic.py Testing/test_fdi31_recovery_diagnostic.py` | PASS, exit 0 | New diagnostic runner/test |
| Recovery pure tests | `python3 -m pytest -q -p no:cacheprovider Testing/test_fdi31_recovery_diagnostic.py` | `5 passed in 0.02s` | New diagnostic test file |
| Diff/matrix checks | `git diff --check`; JSON matrix/path inspection | PASS | `Testing/verification_matrix.json` |
| `recovery.p1_scene_audit` | Approved container Slicer command with inner `timeout 900s` | PASS, exit 0 | `scene_audit.json` and P1 scene |
| Existing reopen-helper visual fallback | Approved bounded Slicer command with inner `timeout 900s` | PASS, exit 0; limited context only | `p1-reopen-diagnostic.json`; `screenshots/p1-reopen-helper/reopened-ui.png` |
| `recovery.p2_state_contact` initial and retry history | Versioned bounded Slicer/ROS attempts; r1 was run with `ROS_DOMAIN_ID=73` but no native stack; r3 repaired capture framing; r4 used the wrong retained r13 path; r5 ran after the 900-second stack lifetime expired | Preserved as retry history; no earlier result is silently overwritten | `c1-p1p2-20260914-r1` and `c1-p1p2-recheck-20260914-r1..r5` |
| `recovery.p2_state_contact` final r6 | Bounded container Slicer/ROS command with `ROS_DOMAIN_ID=73`, correct retained r13 path and inner `timeout 150s` inside an outer `timeout 240s` | Runner `PASS`, exit 1 because the runner returns nonzero for the campaign-level inconclusive status; native context ready, 2 candidates, scene unchanged | r6 `rejected_state.json` SHA `a03092a6...cdbf2`; `state_identity.json` SHA `06ca3a09...6dedb`; `contact_records.json` SHA `16d24c31...83f7` |
| Native scene/state readback | Final r6 native audit plus read-only JSON/hash validation after the probe | Task identity 5/5; native FK/static/validate-only evidence obtained; exact payload acknowledgement `expected 31, observed 0`, later guard `world_object_count=31`; native discrepancy keeps P2 INCONCLUSIVE | r6 `state_identity.json`, `contact_records.json`, frozen input hashes |
| Cleanup | Fresh final container inventory, SIGINT sent only to the launch session owned by this task, then post-stop process/status check | PASS for process cleanup; no matching DentoBot simulation process remained; no container restart and no unrelated process stop; MoveIt emitted known shutdown-time segfault after SIGINT | Final stack log `/tmp/dentobot-c1-p1p2-recovery-final-stack.log`; launch-owned PIDs `13475,13497,13500–13504` |

The one authorized readiness-recovery audit then used only read-only checks
before the explicitly authorized selective cleanup. The subsequent final
launch used only the inspected existing simulation components:

| Check | Exact command/action | Result/marker | Interpretation/artifact |
|---|---|---|---|
| Container/process ownership | `docker ps`; container `ps -eo pid,ppid,user,lstart,stat,args`; `/proc/<pid>` environment/cwd/exe/cmdline inspection | Container stayed `Up`; required `move_group`/`collision_guard` absent; remaining description/status processes were parentless `PPID 1`, with duplicate publishers; ROS domain `73`, discovery `SUBNET` | Current ownership is unresolved; no process was terminated; `runtime_readiness.json` |
| Actual ROS graph discovery | Sourced Jazzy/workspace; `ROS_DOMAIN_ID=73 ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET ros2 node list --no-daemon`, `ros2 service list --no-daemon`, `/joint_states` topic info and one `simulation_status` sample | Existing nodes/topics/status were visible; status reported missing guard/planner interfaces | Not a daemon-cache-only failure; missing services do not prove missing API |
| Prior native launch outcome | Read-only grep of `/tmp/dentobot-simulation-stack.log` | Prior `move_group` started, loaded planning services and reached “You can start planning now!”; it later exited with shutdown-time `Segmentation fault` / code `-11`; `collision_guard` reached “Collision guard ready” and finished cleanly | Native components did launch previously and later exited; exact owner of that stack is not established |
| Package/link readiness | `ros2 pkg prefix`, `ros2 pkg executables`, launch/URDF symlink/hash inspection and `ldd` for `move_group`/`collision_guard` | Packages, launch file, guard executable and linked MoveIt libraries present; no missing shared-library result | API/architecture absence is not concluded |
| Approved launcher compatibility | `bash -n` on the dedicated description helper and top-level launcher; read-only source inspection | Syntax PASS. Dedicated helper scans active publishers and refuses normal launch; `--check-only` would build before scanning. Top-level launcher starts the full stack, not only missing P2 services | Initial audit recorded the conflict; later operator authorization permitted exact replacement of the seven verified conflicting DentoBot simulation processes |

**Authorized recovery and startup side-effect inspection:** Before stopping the
pre-existing processes, a fresh inventory identified exactly four duplicate
simulation-status publishers (PIDs `6106`, `6812`, `7738`, `8410`), two
robot-state publishers (`7734`, `8406`) and one Slicer joint-state publisher
(`8407`), all with DentoBot package paths, node remaps and `ROS_DOMAIN_ID=73`.
Only those seven PIDs were sent `SIGINT`; the ROS daemon and unrelated
processes were left untouched. The inspected `simulation.launch.py` starts
robot description, Slicer joint-state simulation, MoveIt, collision guard and
simulation-status components. Its parameters set
`allow_trajectory_execution=false`; the startup log also reports no
`moveit_controller_manager` and “No paths can be executed.” MoveIt nevertheless
advertises its standard `execute_trajectory_action` endpoint, which is a
startup interface side effect, not execution. No controller or hardware
connection, trajectory execution, powered spindle, raw
`/dentobot/slicer_joint_positions` publication or robot motion occurred. The
P2 probe used only the bounded `validate_only` task-guard request on
`/dentobot/task_joint_command`; that is recorded as simulation guard
validation, not a controller/actuator command.

The replacement stack reached the status sample
`{"description_ready":true,"planning_ready":true,"joint_state_publisher_count":1,"ready":true,"mode":"simulation_only"}`.
Its final process inventory was one launch owner plus one each of
`robot_state_publisher`, `slicer_joint_state_publisher`, `move_group`,
`collision_guard` and `simulation_status_publisher`. The final Slicer run
created a diagnostic native robot, used it for the read-only reconstruction,
and disconnected it successfully before exit; the saved MRB excludes ROS
runtime nodes and motion-active state. No operator-owned GUI/session was
present or closed; the final cleanup verification found no matching process.

P2's first attempt exposed a serializer defect while assembling the report:
`dataclasses.asdict()` attempted to deepcopy an MRML transform wrapper. The
allowlisted diagnostic runner was corrected to walk dataclass fields without
deepcopy; the focused tests, syntax check and capture-framing fixes then
completed. The final r6 P2 run reached native readiness and produced native
evidence, but its campaign-level result remains `INCONCLUSIVE` because the
native scene acknowledgement and guard/static attribution did not fully
reconcile. The SlicerROS2 startup also emitted a nonfatal permission warning
while its existing `ROS2Tests.py` attempted to install `psutil`; no dependency
installation or environment repair was performed. No C++ file changed, so no
native build was run.

The initial read-only container-status call hit the sandbox's Docker API
permission wrapper and was rerun through the approved container path. That was
a command-access error, not a planner/runtime result. A bounded Graphify query
was run from `/home/light-tarun/dentobot`; the live graph root was used. These
navigation/access corrections did not alter the experiment. After the
diagnostic code additions, the repository Graphify helper was rerun through
the approved elevated path and completed with `Code graph updated`; the overlay
reported 8,054 nodes, 12,587 edges and 702 communities. The graph extractor's
syntax warnings did not alter source or evidence files.

## K. Classification

| Candidate class | Status | Confidence/reason |
|---|---|---|
| `SCENE_CONSTRUCTION` | Competing hypothesis | Low; upstream scene semantics/transforms are not yet reconciled |
| `TRANSFORM_OR_SCALE` | Competing hypothesis | Low; frame/unit identities are frozen, but no C1 reconstruction comparison exists |
| `TOOL_COLLISION_MODEL` | Leading hypothesis | Low; r13 repeatedly reports the target-to-spindle pair, but contact geometry is not decision-quality |
| `TASK_GEOMETRY_FEASIBILITY` | Unresolved | No bounded C1 endpoint/insertion result |
| `IK_COVERAGE` | Unresolved | r14's 22 seeds/8 solutions are explicitly non-exhaustive and same-branch |
| `IK_BRANCH_SELECTION` | Unresolved | No C1 branch-cluster or admissibility comparison |
| `INSERTION_CONSTRUCTION` | Unresolved | P4 not tested |
| `FREE_SPACE_PLANNER` | Unresolved | Stage 1 prior pass does not prove the later chain |
| `COLLISION_POLICY` | Not indicated as a defect | The observed pair is forbidden by the preserved policy; no policy change is authorized |
| `PLANNER_GUARD_INCONSISTENCY` | **Observed diagnostic discrepancy; not yet classified as a production defect** | r6 native static validity reported collision pairs while the phase-aware validate-only guard rejected the same reconstructed vectors for corridor progress and reported no TaskJointStatus pair; the exact scene acknowledgement also disagreed with the later guard object count. Attribution is insufficient for a production conclusion |
| `UNKNOWN` | **Accepted current class** | Evidence is insufficient to select a causal class |

P2 does not change the accepted `UNKNOWN` classification. It narrows the
current evidence boundary: r6 adds native FK, static-collision and
validate-only guard observations, but the native scene acknowledgement and
state-attribution disagreement prevent a trusted causal classification. The
saved r13 forbidden pair remains historical/reconstructed unless separately
matched by the native static result; TaskJointStatus pair fields remain
unknown.

## L. Failed approaches

| Attempt | Hypothesis/intervention | Observation | Why rejected/limited | Evidence/retry boundary |
|---|---|---|---|---|
| r13 exact Stage-6/full-chain run | Existing frozen planner/guard should produce a complete FDI31 chain | Stage 1/2 passed; both candidates reached exact Target; Stage 3 first invalid at local 27 against `pneumatic_spindle-Copy` | No complete drilling, Goal 2, Return Home, repeat or playback acceptance; `last_valid` caveat prevents accepted-state inference | r13 sidecar/log retained; historical full-flow retry ceiling remains exhausted; P0 does not reset it |
| r14 bounded endpoint probe | More seeds might reveal a native endpoint alternative | 22 deterministic seeds, 8 endpoint solutions, all same J5 branch | Not exhaustive; sidecar overwritten by fallthrough, so raw probe mapping is not authoritative | r14 log retained; no automatic second batch |
| P0 replay or planner rerun | Replay might fill missing baseline evidence | Not attempted | Campaign P0 forbids a full-planner rerun and source/geometry changes | No new runtime retry consumed |
| P0 path/navigation lookups | Initial relative paths were assumed to be checkout-local | Data/graph were absent at those assumed locations | Corrected to workspace-root data and live root graph; no experiment affected | Read-only correction only |
| P1 headless visual capture | Main-window/viewport capture should provide reviewable anatomy context | Machine nonblank checks passed, but the P1 3-D view was visually blank under Xvfb; the existing reopen-helper produced only limited usable context | No visual acceptance or geometry interpretation was made from blank images | Retained all captures; operator review required |
| P2 native reconstruction — initial/retry history | Installed native guard/planner interfaces would support state/contact reconstruction | Initial run had no native stack; r2 stopped during Slicer startup; r3 repaired capture framing; r4 used a retained r13 file with zero candidate records; r5 launched after the finite stack lifetime had expired | These attempts are preserved and not treated as native evidence; no source/r7/r13 overwrite | Versioned `c1-p1p2-20260914-r1` and `c1-p1p2-recheck-20260914-r1..r5` outputs |
| One-time runtime-readiness recovery | Existing startup path could restore only P2-required services without touching an operator-owned session | Read-only audit found discoverable domain/setup and present binaries, but parentless duplicate description publishers blocked the dedicated helper; the operator then explicitly authorized replacement of only seven verified conflicting DentoBot simulation processes | Seven exact PIDs were stopped with SIGINT; one coherent simulation-only stack reached `ready:true`; no container restart, unrelated stop or dependency change | `runtime_readiness.json`; final stack log and cleanup inventory in J; no operator-owned GUI was closed |
| P2 native reconstruction — final r6 | Correct retained r13 input plus restored native stack would produce decision-quality diagnostics | Native ready; 2 candidates; FK within tolerance; both static-invalid with the same native contact set, while validate-only guard rejected for corridor progress and the scene acknowledgement disagreed (`31` expected vs `0` observed) | Evidence is useful but the campaign requires full reconciliation; P2 remains `INCONCLUSIVE`; no P3/P4 | r6 `rejected_state.json`, `state_identity.json`, `contact_records.json`, four labelled images and rotatable MRB |

No production intervention was made or reverted. The diagnostic runner/test and
matrix edits are retained as the minimum evidence plumbing for this campaign;
no geometry, planner, IK, guard policy, tolerance, case or build-system change
was made. The initial missing native runtime was recovered within the explicit
operator boundary after the seven verified conflicting DentoBot simulation
processes were stopped with SIGINT. The final native scene acknowledgement
discrepancy remains a shared runtime/evidence blocker under the existing
backlog/task ownership; it is not promoted to a parallel planner task.

## M. Repository

### DentoBot checkout at the P0 capture boundary

- Path: `/home/light-tarun/dentobot/ros2_ws/src/DentoBot`.
- Branch: `main`.
- HEAD: `3af2d864449679ead25398899d6325aefb50595a`.
- Parent: `511a8240486ba1239b7debaaea72e87900dd2682`.
- Commit subject: `docs(logbook): record four-incisor handoff publication`.
- Pre-P0 status: 54 tracked modified paths, 13 untracked paths, 0 deleted.
- Tracked diff: 54 files, `5428` insertions and `693` deletions.
- Tracked diff SHA: `534d9d323e0dda42fc1facb0c18f8d48671a253dbbae1b523519d1167f67d85d`.
- Cached diff SHA: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- Pre-P0 porcelain SHA: `d687b425208334f892d78f6c4b1137b5c437d82de92174a8f65e3527b16e48df`.
- The exact pre-P0 tracked and untracked path inventories are recorded in
  `source_state_manifest.json`; they are preserved as pre-existing user work.

The campaign-relevant pre-existing modified paths include the facade, bridge,
Step 6 state, case/foundation/scene-sync/Step 6 logic, exact-case runner,
`dentobot_moveit_config/src/collision_guard.cpp`, and the already modified
verification matrix. The campaign-relevant pre-existing untracked paths include
the case-reopen diagnostic, stage-6 diagnostic utilities and the campaign
specification itself. P1/P2 added only the diagnostic runner and focused test,
updated the matrix with the two recovery rows, and appended controlled
evidence records. No production implementation tool was changed and no native
build was performed.

### Relevant sibling and native build identity

- Sibling: `/home/light-tarun/dentobot/ros2_ws/src/slicer_ros2_module`.
- Sibling branch: `dentobot/slicer-ros2-step6-20260903`.
- Sibling HEAD: `49492e0dcffba1d65576a0389298e4f38a8e515f`.
- Sibling tracked diff SHA:
  `7d57e7e8262c7a31c1abb528988d258819b66e3c612eb64af633c75ca92de040`.
- Native build binary:
  `/home/light-tarun/dentobot/ros2_ws/build/dentobot_moveit_config/collision_guard`.
- Binary SHA: `9667b3aa6091db70cbb32c118af68af8f1d43179f099c6344f9184e2549c9ce9`;
  Build ID `f2bf203b50d8609858e1a45b2a972c79772b8b6f`.
- Collision-guard source SHA:
  `f2852e2bd9853f4dd2dc33ef170fbf3b46b09444ab7e279b0e54d8498f419c77`.
- Current host install candidates were not found; no current container-loaded
  binary is claimed beyond the prior r13 record. The prior r13 image record is
  `dentobot/slicerros2:jazzy-moveit-sim-20260909`, digest
  `sha256:544c5b759ccef7ce6c41157bbd7bd8b602657de367f1f6b71352de054c81b019`,
  ROS domain `73`, loaded binary SHA matching the build SHA above.

### Temporary artifacts and cleanup

The original r13/r14 temporary logs are preserved for traceability and have
durable copies. Do not automatically delete or overwrite them during a later
phase; cleanup may be proposed after operator/architect acceptance. No source,
case, report history or user-owned work was reset, checked out, reverted,
deleted or moved. Before replacement, the exact seven pre-existing DentoBot
simulation processes were verified by executable path, package, node remap and
domain; only those PIDs (`6106`, `6812`, `7734`, `7738`, `8406`, `8407`,
`8410`) received SIGINT. The ROS daemon, unrelated processes and any
operator-owned session were not targeted. The final launch-owned stack was
then stopped via its own terminal session with SIGINT; no force kill or
container restart was used. The post-stop inventory found no matching
DentoBot Slicer/ROS/MoveIt process. MoveIt's known shutdown-time segfault
(`exit -11`) occurred after the graceful SIGINT; all other stack processes
finished cleanly. The r6 scene records successful diagnostic-robot
disconnection and the MRB excludes live ROS nodes/motion-active state.

## N. Recommendation

P1/P2 recovery work is stopped and the campaign is paused. P1 saved-input and
machine checks are **PASS**, but P1 overall scene correctness and operator
review are **INCOMPLETE**. P2 bounded native diagnostic evidence is **PASS**
with **USER_REVIEW_REQUIRED**: the final no-TTY recheck reconciled the exact
native scene acknowledgement at 31/31, kept static and transition predicates
separate, and verified TCP/spindle/burr display FK. The earlier zero-object
acknowledgement remains historical evidence, not the final disposition.
Do **not** start P3 or P4 from this report. The next action is the operator's
decision-critical review of the automatic selections, saved scenes, visual
context, native-versus-display evidence and this precise
scene-acknowledgement boundary; operator acceptance remains unrecorded.

The current envelope record is:

`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p0-20260914-r1/execution_envelope.json`

Its corrected recorded status is
`P1_MACHINE_CHECKS_PASS_P1_SCENE_REVIEW_INCOMPLETE_P2_INCONCLUSIVE_P3_P4_PENDING_OPERATOR_REVIEW`.
Operator acceptance is not recorded. A later P3 request would require a new
explicit approval, completed operator review and a qualifying reconciled
native runtime; P2's `INCONCLUSIVE` result does not make P3 eligible.

No approval or generated flag in this report authorizes P3/P4, P5–P7, a
full-flow retry, repeat/playback, normal-window acceptance, controller
connection, powered spindle, robot motion, patient-facing action, or any
frozen geometry/task/policy change.

## O. P1/P2 execution record and review package

### Workflow-order automatic selections

P1 used the immutable source and r7 diagnostic package, then restored and
audited the existing workflow state in this order. These are automatic
selections, not operator acceptance; every record has
`operator_confirmed_in_this_run=false` and `operator_review_required=true`:

1. immutable source package (`DENTOBOT_RECOVERY_SOURCE`)
2. diagnostic package (`DENTOBOT_RECOVERY_PACKAGE`)
3. Case Foundation pose/base
4. whole-tooth FDI31 target segment
5. saved Entry/Target line
6. assisted entry set
7. draft support
8. visible support
9. docking assembly
10. insertion direction
11. patient-contact shell
12. final printable template
13. finalized shell
14. restored Step 6 package state
15. saved collision payload (P1 only; no native runtime)

P1 saved-input/machine results: source/r7 package identity, frozen
Entry/Target/segment and trajectory, Case Foundation and current PreparedBranch
eligibility all passed. P1 overall scene correctness and operator review are
still **INCOMPLETE**. The saved target and line were not regenerated. P1's
output is
`.../c1-p1p2-20260914-r1/scene_audit.json` (SHA
`283ff851...7896`).

### P1 scene and visual outputs

- Rotatable P1 scene:
  `.../inspection-scene/fdi31-p1-scene.mrb` — 87,662,026 bytes, SHA
  `911a98ef...2d8b`.
- Supplemental context:
  `.../screenshots/p1-reopen-helper/reopened-ui.png` — a limited but useful
  existing reopen-helper UI capture with rendered case/guide context.
- The P1 runner's `p1-context.png` and `p1-target-guide-closeup.png` are
  retained, but their 3-D region is visually blank under Xvfb; they are not
  decision-quality geometry evidence. The machine byte/nonblank check does
  not override visual review.
- P1 serialized runtime flags are
  `ros2MotionActiveSerialized=false` and `ros2RuntimeNodesSerialized=false`.
- The one-time readiness-recovery audit is
  `.../c1-p1p2-recovery-20260914-r1/runtime_readiness.json`; it stopped before
  native launch because the existing parentless publishers made ownership
  unresolved and the available launcher was not selective.

### P2 reconstruction and native-contact boundary

P2 used the two retained r13 candidate vectors and the unchanged task/frame/
tolerance contract. The initial r1/r4/r5 attempts are preserved as retry
history; r1 lacked the native stack, r4 selected a prior rejected-state file
with zero candidate records, and r5 ran after the finite recovery stack
expired. The final r6 attempt used the correct retained r13 artifact after the
authorized selective runtime recovery.

The r6 native context was ready, the seven-link native robot loaded, and all
five task-identity checks passed. Both retained candidate vectors were
reconstructed without a planner run. MoveIt FK was finite and within the
unchanged target tolerances for both (`0.000675 mm` position error; axis error
`0.000257°` and `0.000715°`). The authoritative static validity result was
`valid=false` for both with this native contact set:

`[Step 5C] DENTO Final Printable Template` ↔ `pneumatic_spindle-Copy`; target
↔ `burr`; target ↔ `pneumatic_spindle-Copy`.

The phase-aware task guard was also exercised only through `validate_only`.
Both samples were rejected with `corridor_ok=false`, corridor progress about
`-0.03699`, `checked_samples=1`, `world_object_count=31` and native world
clearance about `0.0209146 m`; its TaskJointStatus did not expose a body pair.
The native static collision pairs and the TaskJointStatus result are kept as
separate predicates, not merged into one contact claim.

P2 remains **INCONCLUSIVE** because the exact Step-6 collision-payload
acknowledgement in the same r6 run recorded `expected 31, observed 0`, even
though the later guard status reported 31 objects. The r6 diagnostic runner
reported `PASS` for its native candidate reconstruction, but that generated
flag is not the campaign gate. The setup-handshake accepted state and
housing-clear state are available native setup observations only; they are not
the preceding accepted state of the retained r13 rejection. No exact r13 edge
or collision onset was established. Native nearest points, TaskJointStatus
pair, contact count/truncation, penetration and drilling-depth fields remain
null/unknown where not exposed.

- Final r6 state record:
  `.../c1-p1p2-recheck-20260914-r6/rejected_state.json` — SHA
  `a03092a64ea1d0c5a0360db5926f2df4d562745ecd1ccf07143b9ee08a0cdbf2`.
- Final r6 identity record:
  `.../c1-p1p2-recheck-20260914-r6/state_identity.json` — SHA
  `06ca3a0993cc5cae703a3fc9423db6b07a96154d41314ac8351425b8e616dedb`.
- Final r6 contact records:
  `.../c1-p1p2-recheck-20260914-r6/contact_records.json` — SHA
  `16d24c31dfab802b317a94d27abffd035d5183cea7a35f80cb7d027eeadb83f7`;
  two native-status records with explicit unknown pair/depth fields plus
  native clearance.
- Final r6 rotatable P2 scene:
  `.../c1-p1p2-recheck-20260914-r6/inspection-scene/fdi31-p2-rejected-state.mrb`
  — 87,804,930 bytes, SHA
  `a19bd69975b8560c7113f3cd341cb1d6dab6449b431877637a5888b27ad84ec2`.
  Scene fingerprint was unchanged and serialized ROS motion/runtime flags are
  false.
- Final r6 screenshots: `p2-context.png`, `p2-target-state.png`,
  `p2-first-rejected-close-up.png` and
  `p2-visible-vs-collision-payload.png`; all are nonblank and labelled. The
  last is explicitly display-only red/cyan audit geometry, not a native
  collision rendering.

### Review decisions awaiting the operator

1. Review the 15 automatic P1 selections and confirm whether the saved FDI31
   anatomy/target/guide/scene is the intended input. Do not treat the JSON
   confirmation fields as that decision.
2. Review the P1 scene and the new nonblank P1 context/Entry→Target close-up;
   decide whether the saved anatomy, guide, target and scene are correct. The
   r4 P1 images are evidence, not geometry acceptance.
3. Review P2's `INCONCLUSIVE` native evidence boundary: native readiness was
   recovered, but the 31-object scene acknowledgement disagreed with the
   later guard count, and static collision contacts were not reproduced in the
   TaskJointStatus pair fields. Decide whether that evidence is sufficient for
   diagnostic routing or requires architectural review. Do not treat the
   native runner PASS as acceptance.
4. Decide explicitly whether to request a new, separate P3 approval after the
   runtime/scene questions are resolved. P3 is not queued or authorized by
   this handoff.

## P. Corrected P2 proposal execution — source PASS, runtime handoff blocked (2026-09-14)

**Current status (superseding the preceding pending-proposal disposition):**
P1 saved-input/machine checks are **PASS** for the checks actually completed.
P1 overall scene correctness and operator review are **INCOMPLETE**. P2 is
**INCONCLUSIVE** because the approved corrected diagnostic did not reach its
Slicer/native diagnostic phase. `operator_acceptance` remains
`NOT_RECORDED`; no input, scene, geometry or contact acceptance is inferred.
P3/P4 remain unauthorized.

### Approval, frozen inputs and source correction

The operator's `approved` response authorized the precise corrected P2
proposal for the existing `c1-p1p2-recheck-20260914-r6` run only. It did not
authorize a new retry name, a full planner, geometry/task/policy changes,
hardware/controller/spindle action, robot motion, repeat/playback or P3/P4.
The corrected diagnostic retained the frozen package, STL, Entry/Target,
candidate vectors, frame, tolerance, collision policy and ROS domain from the
execution envelope; it did not regenerate or select a new target.

The source correction was implemented in the existing diagnostic boundary:

- `Testing/run_dentobot_fdi31_recovery_diagnostic.py` now keeps static-state
  validity and phase-transition validity in separate records, preserves
  request/start/requested/evaluated sample telemetry, requires correlated
  scene acknowledgement, compares displayed goal-link transforms with native
  FK, and specifies the labelled FDI31/burr/spindle close-up.
- `DENTOWorkflow/Resources/Python/DENTOROS2Bridge.py` carries the additive
  `request_id`, `validation_kind`, starting/evaluated vectors, sample index,
  interpolation fraction and total-sample fields, and fails closed on
  mismatched collision-scene IDs, poses, bounds or policy fingerprint.
- `DENTOWorkflow/Resources/Python/dentobot_workflow/logic_robot_scene_sync.py`
  carries the explicit collision-object pose identity and supports deferred,
  correlated diagnostic acknowledgement without changing normal callers.
- `dentobot_moveit_config/src/collision_guard.cpp` implements the additive
  `validation_kind=static_state` task-guard request. It reuses the existing
  phase predicate for exactly one state, does not mutate accepted/preflight
  state, and reports the actual start/evaluated vector and sample telemetry.
  The transition path and collision policy are unchanged.

The conditional native build completed:

```text
cmake --build /workspace/ros2_ws/build/dentobot_moveit_config
  --target collision_guard -- -j2  ->  [100%] Built target collision_guard
corrected source SHA-256: 8259a062b8c314fedb7a5ac95652a53ea280cfca2b67a6f6eda57b50ff2273b3
container install binary SHA-256: f1132ea07d81c39249539c05c8900c817f39d50a95a6574ac3974f17e512fc3d
```

Focused verification after the implementation was `44 passed` across the
recovery, ROS-bridge and MoveIt-config tests; AST parsing passed for all six
scoped Python files; scoped `git diff --check` passed. The graph overlay was
refreshed successfully (`Code graph updated`). These are source/build checks,
not operator acceptance and not a P2 native-result PASS.

### Bounded runtime-readiness result

The approved startup path was inspected before launch. On `ROS_DOMAIN_ID=73`
with subnet discovery it starts the description publishers, `move_group`,
`collision_guard` and the simulation-status publisher. The launch configuration
has `allow_trajectory_execution=False`, no hardware interface, no controller
configuration and no powered-spindle path. MoveIt's advertised execution
service is not evidence that an execution request was sent. A separate bounded
read-only status trace observed `ready:true`, `planning_ready:true` and
`mode:"simulation_only"`, so the missing service observation was not treated
as proof that the API or architecture was absent.

For the final bounded corrected attempt, the launch-owned stack started in the
pinned container. The preserved log shows `collision_guard` ready and the
MoveIt planning services initialized at approximately 17:05:44, followed by
the wrapper teardown at 17:05:50 before any corrected diagnostic artifact was
created. The log also contains the expected no-controller-manager warning
under trajectory execution disabled, plus a MoveIt `exit -11` during graceful
shutdown and external-shutdown exits from the two simulation publishers. No
controller, trajectory, raw joint command, spindle or robot-motion request was
issued.

The precise remaining blocker is therefore **the approved bounded wrapper did
not complete the readiness-to-Slicer diagnostic handoff**. No Slicer process,
native static query, native transition query, corrected scene acknowledgement,
FK comparison, contact capture or saved corrected inspection scene exists.
The corrected output directory contains only the preserved launch log:

`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/runtime-readiness-final2.log`

SHA-256:
`92cdd08c9923513c93a5793825f7a5e52aefaf44fc3cb27fbfe1140719ab0dae`.
The earlier bounded wrapper failures and the final handoff failure consume the
existing diagnostic retry budget; no further runtime attempt is made in this
campaign turn. This is a harness/startup handoff blocker, not a new endpoint
verdict and not evidence that the additive native interface is absent.

### Evidence boundary and cleanup

The retained r6 packet remains unchanged and is the only available native/
visual reconstruction packet. Its saved `PASS` flag, nonblank review images,
native FK/static records and `validate_only` transition result remain historical
r6 evidence; they are not silently upgraded to corrected-P2 evidence. In
particular, r6's static collision pairs and transition corridor rejection are
still separate predicates, and native pair attribution, onset, penetration,
contact count/truncation and drilling-depth fields remain unknown where not
exposed. The r6 state, identity, contact records, MRB and screenshots retain
their previously recorded hashes. No corrected P2 contact evidence was
obtained.

The final launch group was cleaned through its own graceful signal. The only
remaining ROS CLI daemon was identified as created by the run, stopped with
`ros2 daemon stop`, and a serial post-cleanup inventory found no DentoBot,
ROS, Slicer or MoveIt process. The first cleanup shell invocation used `sh`
and failed to source ROS (`source`/`ros2` unavailable); it made no state
change and was immediately corrected with `bash`. No container restart,
operator-owned process, GUI application, dependency, source reset or user
session was touched.

### Gate disposition

The 15 automatic selections and the retained scene/geometry still await the
operator's review. The r6 images and MRB may be inspected as labelled,
display-only review evidence, but neither generated confirmation flags,
focused-test PASS results, execution approval nor the saved scene records
operator acceptance. P1 remains `PASS / INCOMPLETE` in the corrected
distinction above; P2 remains `INCONCLUSIVE` with the single runtime-handoff
blocker. Do not start P3 or P4, and do not claim full-workflow, normal-window,
clinical or patient-facing acceptance.

## Q. Source-only P2 launcher/handoff diagnosis and repair — 2026-09-14

**Scope and stop:** The operator authorized source inspection, a minimal
wrapper correction and local stub tests only. No Docker, ROS, Slicer or native
diagnostic execution was performed for this section. The run remains
`c1-p1p2-recheck-20260914-r6`; retry history, frozen inputs and all P1/P2
evidence boundaries are preserved. P1 is still saved-input/machine
`PASS_FOR_COMPLETED_CHECKS` with overall scene correctness/operator review
`INCOMPLETE`; P2 is still `INCONCLUSIVE`; `operator_acceptance` remains
`NOT_RECORDED`.

### Recovered wrapper and evidence split

The approved repository launcher is
`Workspace/scripts/launch-dentoworkflow.bash`. Its embedded container shell
uses `set -euo pipefail`, temporarily disables nounset only while sourcing the
Jazzy and workspace overlays, starts
`setsid ros2 launch dentobot_moveit_config simulation.launch.py` in the
background, saves `$!`, polls `/dentobot/simulation_status` with
`timeout 2s ros2 topic echo … --once --field data`, and allows 60 attempts at
0.5-second intervals. It then requests
`ros2 launch slicer_ros2_module slicer.launch.py` with the DENTO Workflow
selection. The original inline cleanup sends INT, waits, then TERM and KILL
to the negative process-group ID before waiting on the launch PID.

The durable final2 artifact preserves the container stack output but not the
wrapper's stdout/stderr, wrapper exit status, readiness return code, parser
boolean or a process-tree snapshot at the handoff. The final2 log is
`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/runtime-readiness-final2.log`
(SHA-256
`92cdd08c9923513c93a5793825f7a5e52aefaf44fc3cb27fbfe1140719ab0dae`). The
full shell-quoted ad-hoc invocation that produced that log is likewise not
preserved as a standalone command artifact; the recorded environment,
container, domain, stack path and diagnostic timeout remain available.

The three handoff layers therefore classify as follows:

| Layer | Evidence | Status |
|---|---|---|
| Services started and reported ready | `collision_guard` logged ready at approximately 17:05:44.496; MoveIt initialized its planning services; shutdown later logged SIGINT/SIGTERM | **PROVEN** |
| Wrapper received and parsed readiness | No wrapper stage line, captured status, parser result or return code; the `ready:true` JSON in the separate bounded status trace is not evidence from final2 | **UNKNOWN** |
| Wrapper requested Slicer | No Slicer process, Slicer log, launch marker or corrected artifact exists in final2 | **NOT EVIDENCED** |

The later MoveIt `exit -11` and simulation-publisher external-shutdown
messages occurred after teardown and are not established as the initiating
failure. The observed five-to-six-second interval does not prove that the
30-second readiness loop or a 2-second poll timed out.

### Hypotheses and minimal repair

The available evidence cannot select one root cause among a readiness-command
return failure, shell control-flow exit, parser mismatch, timeout behavior,
process-lifecycle race or an unobserved Slicer-launch failure. The installed
ROS 2 `echo --field data` behavior was source-inspected: a `std_msgs/String`
sample is emitted as the raw compact JSON followed by `---`, so the existing
`*"ready":true*` shell pattern would match the known ready payload if that
payload reached the assignment. The checked-in inline block already used
`|| true` around the readiness command, so a `set -e` exit is not proven for
that exact revision; an omitted guard in an ad-hoc variant remains only a
hypothesis. No timeout increase or parser-policy change is justified.

The smallest correction is a focused extraction of the existing handoff into
`Workspace/scripts/dentobot-simulation-slicer-handoff.bash`, called by the
existing launcher with `exec bash`. It does not alter the stack command,
readiness defaults, ROS topic/schema, planner, native guard or collision
policy. It adds only:

- safe capture of the readiness command's return code before testing the
  existing ready marker;
- lightweight `DENTOBOT_HANDOFF` markers for stack start, each readiness
  observation, readiness acceptance/failure, Slicer launch request,
  diagnostic entry/exit and cleanup reason/status; and
- explicit preservation of the diagnostic command's exit status through the
  owned process-group cleanup. No command arguments are printed or traced.

The helper retains the production defaults `timeout 2s`, 60 attempts and
0.5-second polling, and retains bounded INT → TERM → KILL cleanup of only its
own `setsid` process group. The native diagnostic interface and planner source
were not changed in this source-only increment.

### Focused source-only verification

- `bash -n Workspace/scripts/launch-dentoworkflow.bash Workspace/scripts/dentobot-simulation-slicer-handoff.bash` — **PASS**.
- `PYTHONPYCACHEPREFIX=/tmp/dentobot-c1-handoff-pycache-final python3 -B -m pytest -q Testing/test_dentobot_slicer_handoff.py` — **3 passed in 0.86s**. Local stubs covered ready → Slicer-request → diagnostic entry, readiness command `rc=7` blocking Slicer, and diagnostic `rc=23` surviving cleanup; the successful case also verified the owned process group was gone.
- `PYTHONPYCACHEPREFIX=/tmp/dentobot-c1-handoff-env-pycache-final python3 -B -m pytest -q Testing/test_ros2_cli_slicer_env.py` — **5 passed, 1 pre-existing unrelated test failed**. The failing `test_normal_gui_launch_restarts_the_dedicated_container` expects the `check_only` conditional before `container_runtime_safeguards`; the current launcher places that conditional later. The handoff-related tests passed, and this unrelated test was not changed.
- `git diff --check` — **PASS**.

These tests prove the corrected local wrapper control flow, not native runtime
readiness, Slicer startup, native scene identity or P2 contact evidence.

### One proposed bounded native P2 recheck — not executed

The following is the single proposed command for a separately approved
recheck. It reuses the same r6 run and frozen r7 package/r13 diagnostic; it
does not start the top-level launcher, restart the container or run the full
planner. The output directory already exists and all new output would be
written alongside preserved artifacts:

```bash
timeout 180s docker exec dentobot-slicerros2 bash -lc '
  set +u
  source /opt/ros/jazzy/setup.bash
  source /workspace/ros2_ws/install/setup.bash
  set -u
  export ROS_DOMAIN_ID=73 ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
  export LD_LIBRARY_PATH=/workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-loadable-modules:/workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules:${LD_LIBRARY_PATH:-}
  export PYTHONPATH=/workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules:${PYTHONPATH:-}
  export DENTOBOT_RECOVERY_PHASE=p2_state_contact
  export DENTOBOT_RECOVERY_RUN_ID=c1-p1p2-recheck-20260914-r6
  export DENTOBOT_RECOVERY_PACKAGE=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/packet-a-fdi31-20260914-r7/FDI31-step5c.dentocase
  export DENTOBOT_RECOVERY_R13=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/packet-a-fdi31-r7/diagnostics/FDI31-stage6-exact-r13.json
  export DENTOBOT_RECOVERY_OUTPUT=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/rejected_state.json
  timeout --signal=TERM --kill-after=20s 150s \
    bash /workspace/ros2_ws/src/DentoBot/Workspace/scripts/dentobot-simulation-slicer-handoff.bash \
      --stack-log /workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/runtime-readiness-wrapper.log \
      -- \
      timeout --signal=TERM --kill-after=15s 120s \
        xvfb-run -a /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer \
          --no-splash --no-main-window \
          --additional-module-paths /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-loadable-modules \
          --additional-module-paths /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules \
          --additional-module-paths /workspace/ros2_ws/src/DentoBot/DENTOWorkflow \
          --python-script /workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_fdi31_recovery_diagnostic.py \
    > /workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/runtime-handoff.log 2>&1
'
```

Before that command, perform a read-only container process inventory. If an
existing conflicting DentoBot simulation process is found, record its exact
executable/package/node/remap/domain ownership and stop for a separate
ownership decision; this helper must not stop it. During the command, the
helper owns only its newly created `setsid` simulation group; the inner
timeouts bound the diagnostic and the handoff, and the outer timeout bounds
the container invocation. Afterward, verify that the helper group, diagnostic
Slicer/Xvfb descendants and any run-created ROS CLI daemon are gone; leave
operator-owned processes untouched. The helper's cleanup log must preserve
the initiating status and reason.

The recheck can produce a machine-pass only if the Campaign-1 condition is
met: exact frozen task/scene identity; one correlated acknowledgement of all
31 collision objects with matching IDs, poses/bounds and policy; a separate
one-state static result; a separately labelled transition result with known
start/requested/evaluated sample telemetry; native FK agreement for the
displayed TCP/spindle/burr; nonblank labelled captures; and a saved rotatable
scene with no drift. Unknown contact/onset fields remain unknown. Any missing
handoff marker or required native evidence leaves P2 **INCONCLUSIVE**.

**STOP:** This recheck is proposed only. It was not run, does not mark P2
`PASS`, does not record operator acceptance, and does not authorize P3/P4.

## R. Historical bounded runtime recovery result and pre-alias P2 evidence — 2026-09-15

This section records the pre-alias bounded runtime packet and supersedes the
proposed-only disposition in Section Q for that explicit runtime-recovery
request. Section T is the later current disposition after the authorized
container restoration and burr-alias recheck. This section does not supersede the frozen
Campaign-1 invariants, the P1 review gate, the three-attempt retry ceiling, or
the prohibition on P3/P4 and hardware actions. The run remained
`c1-p1p2-recheck-20260914-r6`; no new run name or retry-history reset was
created.

### R.1 Runtime sequence and launcher result

The exact undated frozen r13 input was used:

`data/Slicer_Saved/SampleStudy1/FDI31/packet-a-fdi31-r7/diagnostics/FDI31-stage6-exact-r13.json`

with SHA-256
`0e4683c8def9584abddface6655c49451e1a642e41f0568c08fe342dad09c32b`.
The r7 package remained the frozen input with SHA-256
`5440961c2f1464df10adec3dfb6ab59f8a0e412c6074cae7852d8150babe4fff`.
The three bounded attempts used the existing `setsid` simulation-only helper,
ROS domain 73, subnet discovery, and nested diagnostic/container timeouts.

1. Attempt 1 retained the corrected input path but still passed
   `--no-main-window`. Readiness was accepted on the first observation and the
   helper emitted both `slicer_launch_request` and `diagnostic_entry`. Slicer
   then failed in `_open_case` with `RuntimeError: Could not find main window`.
   No native case evidence was produced. The wrapper preserved status 1 and
   cleaned its own stack group. The handoff, wrapper and rejected-state files
   are preserved as `corrected-p2/runtime-handoff-attempt1-no-main-window.log`,
   `corrected-p2/runtime-readiness-wrapper-attempt1-no-main-window.log` and
   `corrected-p2/rejected_state-attempt1-no-main-window.json`.

2. Attempt 2 removed only `--no-main-window`. The helper observed readiness,
   requested Slicer, entered the diagnostic, and produced a native packet,
   five labelled screenshots and a rotatable MRB. The first runner issue was
   then concrete: the live goal robot was visible, but the evidence record's
   `displayed_model_names` was empty and the burr/TCP/spindle display-to-native
   pairing was not trustworthy. The complete attempt is preserved under
   `corrected-p2/attempt2-live-goal-refresh/` and was not used as a reason to
   overwrite the final packet.

3. The runner-only source repair reacquired the live goal robot after the
   display call, catalogued `goal_model` and `goal_transform` references, and
   classified known spindle/TCP/burr display names. Focused tests and static
   checks passed. The final bounded attempt then observed one non-ready poll
   followed by a ready poll, requested Slicer, entered the diagnostic, wrote
   the current corrected packet and exited with status 1 because the
   Campaign-1 evidence gate remained incomplete. The final helper markers are:

   ```text
   stage=stack_started pid=17941
   stage=readiness_observation attempt=1 rc=0 ready=false bytes=341
   stage=readiness_observation attempt=2 rc=0 ready=true bytes=175
   stage=readiness_accepted attempt=2
   stage=slicer_launch_request argc=16
   stage=diagnostic_entry
   stage=diagnostic_exit status=1
   stage=cleanup_begin reason=diagnostic_exit initiating_status=1 stack_pid=17941
   stage=cleanup_signal signal=INT reason=graceful
   stage=cleanup_complete reason=diagnostic_exit initiating_status=1
   ```

This proves the previously unknown readiness-to-Slicer handoff branch for the
corrected wrapper. It does not prove P2 acceptance. The stack log also records
the expected simulation-only boundary: MoveIt initialized planning services,
but its controller-manager parameter was intentionally absent and it reported
that no paths can be executed. No controller, trajectory, joint command,
spindle or hardware path was used. The known `No 3D sensor plugin(s) defined
for octomap updates` warning was not on the diagnostic path. The later
MoveIt/ROS exit noise occurred during the helper's SIGINT teardown, not before
readiness or diagnostic entry.

### R.2 Native results and evidence boundary

The current corrected packet is under:

`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/`

It contains `rejected_state.json`, `state_identity.json`,
`contact_records.json`, five screenshots and
`inspection-scene/fdi31-p2-rejected-state.mrb`. The current hashes are:

| Artifact | SHA-256 | Interpretation |
|---|---|---|
| `rejected_state.json` | `f7eb06286909d979440d236b8a35696d361b1f79e0564937e95550518aa0b4dd` | Final bounded static/transition packet |
| `state_identity.json` | `fb7957580fbd0f40796cbfbaee2516b5f189ded1925f68943c69f0996aec722a` | Native/display/scene identity and FK evidence |
| `contact_records.json` | `e857dfca6ae3e2e31f44a811a89431dda36ee4cc2237db2ad8ab708d53526f60` | Phase-transition records; contact fields remain unknown |
| `inspection-scene/fdi31-p2-rejected-state.mrb` | `5f36343b8a2608fb6d98dad44cbbbaa7a4cc90de39dac192746fb41b63b4ed4c` | Saved rotatable display-only inspection scene |

The native scene acknowledgement is now reconciled in the final packet:
expected 31, observed 31, matching IDs/poses/bounds and relevant policy;
acknowledgement is trusted and the before/after scene fingerprints are equal.
This corrects the earlier r6 `expected 31, observed 0` audit/guard timing
discrepancy; the earlier discrepancy remains preserved as historical evidence
and is not silently deleted.

The two validity predicates are kept separate:

- The phase-aware static-state predicate returned `valid=false` for the
  requested candidate state, with the native non-approved pair
  `[Step 5C] DENTO Final Printable Template` ↔ `pneumatic_spindle-Copy` and
  static world-object count 31. This is the one-state predicate's result; it
  is not inferred from a transition's first sample.
- The validate-only transition began at setup Home `[0, 0, 0, 0, 0]` and
  rejected the first interpolated sample for the approved Entry-to-Target
  corridor. For candidate 0, the reported first evaluated sample is
  `[0.000827557298873, 0.000437667886694, -0.00438198502603,
  0.000498701721538, 0.0064257650803]`, sample 1 of 134 at fraction
  `0.00746268656716`. The exact requested vectors and candidate-1 telemetry
  remain in `rejected_state.json`. This is not a static Target verdict and
  not a reconstruction of the original r13 insertion edge.

Native contact count, depth, nearest points, penetration and onset remain
explicitly unknown. The guard reports first-pair/bounded-sample information,
not an exhaustive contact measurement, and the diagnostic did not invent
those fields.

### R.3 Display evidence and remaining blocker

The final `state_identity.json` proves that the display-only robot was
reacquired from the live goal handle and that the displayed spindle and TCP
transforms match native FK: both rotation errors are `0.0` degrees; spindle
translation error is approximately `4.3e-14 mm`; TCP translation error is
approximately `1.48e-5 mm`, within the `0.25 mm`/`0.5 degree` tolerances.
The marker-only path remains rejected as evidence.

The same catalog contains a matrix-bearing `burr_goal_transform`, but the
runner's classifier did not recognize the normalized name
`burr-goal-transform`, so `burr_comparison.available=false` and its match is
unknown. This is the precise remaining diagnostic-contract defect. It is not
evidence that the burr is misplaced, colliding, or accepted. The three-attempt
ceiling is now reached, so no further runtime is started in this campaign
turn and no source patch is applied speculatively after the evidence stop.

The five labelled captures and saved scene remain review evidence only:

- `corrected-p2/screenshots/p2-context.png`
- `corrected-p2/screenshots/p2-target-state.png`
- `corrected-p2/screenshots/p2-first-rejected-close-up.png`
- `corrected-p2/screenshots/p2-visible-vs-collision-payload.png`
- `corrected-p2/screenshots/p2-fdi31-burr-spindle-close-up.png`

The close-up separates display-only colours and hides surrounding anatomy for
presentation only; collision meshes remain in the native scene and payload.
The images do not constitute operator acceptance of the 15 selections or the
scene geometry.

### R.4 Source/test/cleanup record and gate disposition

The minimal source change was confined to
`Testing/run_dentobot_fdi31_recovery_diagnostic.py` and its focused test. It
did not change the native diagnostic interface, native build, guard policy,
frozen geometry/task/policy, dependencies or planner. The source runner hash
used for the final attempt is
`95ccc30e3cdd50414a9d6499c82fb20a6e610c2339a085c89afcfa8086fb2fab` and the
existing handoff helper hash is
`5659d500d8c00a9a9371dc1ef7a2017f6b3d8c36b75239e3a013199f422e8661`.

Verification completed after the source repair:

- focused diagnostic tests: `11 passed`;
- runner `py_compile`: **PASS** with an isolated temporary bytecode prefix;
- helper/launcher `bash -n`: **PASS**;
- `git diff --check`: **PASS**;
- no native rebuild or dependency change was made in this increment.

The helper's process group was the only launch group stopped. The run-created
ROS-domain-73 CLI daemon was identified by its exact command and stopped with
`ros2 daemon stop`; the post-cleanup inventory was empty for matching
DentoBot/ROS/Slicer/MoveIt processes. The container was not restarted, no GUI
application or operator-owned session was touched, and no hardware/controller
or motion path was activated.

Final disposition: P1 saved-input/machine checks remain **PASS for the checks
actually completed**; P1 overall scene correctness and operator review remain
**INCOMPLETE**; P2 is **INCONCLUSIVE** because burr FK/display pairing is
missing. `operator_acceptance` remains `NOT_RECORDED`. The corrected handoff
runtime issue is evidenced as repaired, but no generated flag, test PASS,
execution approval, image, native record or saved scene records operator
acceptance. Stop here for operator review; do not start P3/P4 or any later
campaign phase.

## S. Continued P2 source repair; native verification blocked by container stop — 2026-09-15

The operator's latest `continue to finish P1/P2 remaining items and blockers`
message was treated as a new bounded decision to repair the deterministic
diagnostic defect and attempt one same-run native verification, while keeping
all frozen inputs, the existing run name, P1 review gate and P3/P4 exclusion.

### S.1 Source repair and static evidence

The remaining source defect was confirmed exactly: the live goal transform was
named `burr_goal_transform`, normalized by the runner to
`burr-goal-transform`, while `_goal_display_node_kind` only recognized the
model-node spelling. The smallest repair adds that exact normalized alias to
the existing classifier. No native source, build, dependency, collision
policy, geometry, task, planner or input changed.

Verification after the repair:

- `PYTHONPYCACHEPREFIX=/tmp/dentobot-c1-burr-alias-pycache python3 -B -m pytest -q Testing/test_fdi31_recovery_diagnostic.py` — **11 passed**;
- isolated runner/test `py_compile` — **PASS**;
- `git diff --check` — **PASS**;
- repaired runner SHA-256:
  `adfec14b0b89774a006829c850f030a739a6b2bf12a5c7346650a0025bae0238`;
- existing handoff helper SHA-256 remains
  `5659d500d8c00a9a9371dc1ef7a2017f6b3d8c36b75239e3a013199f422e8661`.

This establishes **Implemented** and **Unit Verified** for the alias repair;
it is not yet Runtime Verified.

### S.2 Bounded recheck attempt and cleanup boundary

A fresh read-only inventory showed the container up with no matching runtime
processes. A versioned output directory was created at
`corrected-p2/burr-alias-recheck/`. The first constructed invocation was
malformed by splitting the helper's continuation arguments across shell lines;
the helper consequently received no `--stack-log`/diagnostic command, printed
usage, and the later bare Slicer command started a blank Slicer/Xvfb process
instead of the diagnostic. No native case, scene, FK or contact artifact was
written.

The exact task-owned process group was then verified as PGID `18306`, with
descendants `xvfb-run`, `Xvfb`, `Slicer` and `SlicerApp-real`. The original
task-owned terminal session was interrupted, and no matching descendants
remained afterward. The shared container subsequently reported
`Exited (143)`, `OOMKilled=false`; no container restart was performed. No
operator-owned process or GUI session was intentionally touched, and no
native result from this malformed invocation is attributable to the frozen
case.

The prior corrected packet remains the latest valid native evidence. The new
alias repair has not been promoted to a native P2 result. The shared-container
restart needed to perform the corrected native verification remains outside
the standing `do not restart the container` boundary. Until that specific
authority is supplied, P2 remains **INCONCLUSIVE** with the source defect
implemented/unit-verified but runtime-unverified. P1 operator acceptance and
the 15 automatic selections remain open; P3/P4 and all later actions remain
unauthorized.

## T. Authorized container restoration and final bounded P2 recheck — 2026-09-15

This section is the current disposition and supersedes earlier P/Q/R/S
status summaries wherever they conflict, including the Section-S blocker
disposition. The
operator explicitly authorized an in-place restart of the existing
`dentobot-slicerros2` simulation-only container and one bounded P1/P2
recheck. The frozen run name remained
`c1-p1p2-recheck-20260914-r6`; no retry-history reset, P3/P4 action,
full-flow retry, repeat/playback, geometry/task/policy change, controller,
hardware, spindle or motion path was introduced.

### T.1 Why the container stopped and the bounded repair

The stopped-container inspection was conclusive:

- Docker state was `Exited`, exit code `143`, `OOMKilled=false`, with no
  container error and no container log output.
- The configured PID 1 command is `sleep infinity`; the container has
  `tty=true`, `stdin=true` and `RestartPolicy=no`. Therefore a SIGTERM to
  the container leaves it stopped and Docker does not restart it.
- The Docker event stream records the task cleanup command
  `/bin/kill -TERM -18306`, followed immediately by the task exec returning
  `143` and the container `die` event with exit code `143`.

The evidence therefore identifies task-owned cleanup signal propagation as
the stop cause, not an OOM condition, Slicer application crash, native guard
failure or absent API. The preceding malformed attempt was also a command
construction defect: helper continuation arguments were split onto separate
shell lines, so the helper printed usage and the later bare Slicer command
was not the diagnostic. The repair was operational and minimal: start the
existing container in place with `docker start`, pass the helper and its
diagnostic command as one `bash -lc` command, use `docker exec` without a
TTY, keep outer/inner timeouts at 180/150/120 seconds, and let the helper's
own `setsid` process-group cleanup handle only its simulation stack. No
Compose dependency or restart policy was changed.

The restored container preflight was clean: no matching DentoBot, Slicer,
MoveIt or collision-guard process was present. After the recheck, the exact
helper group completed `SIGINT` cleanup; the run-created ROS-domain-73 CLI
daemon was separately identified by its command/domain and stopped through
`ros2 daemon stop`. The final inventory contained no helper, stack, Slicer,
MoveIt, guard or ROS CLI daemon process, and the container remained `Up` with
`OOMKilled=false`. No operator-owned process or GUI session was touched.

The wrapper log records readiness on attempt 2, `slicer_launch_request`,
`diagnostic_entry`, `diagnostic_exit`, and `cleanup_complete`. The Slicer
process returned status `1` after writing the packet; this return code is
preserved as evidence. The same log contains one `DENTOBOT_FDI31_RECOVERY`
record with packet status `PASS`, no traceback, and only the existing Slicer
extension-directory/class-loader/VTK shutdown warnings plus the known
no-3D-sensor warning. No blanket error suppression or exit-code rewriting
was added. The nonzero Slicer shutdown code is separate from the container
stop and did not prevent creation or validation of the bounded packet.

### T.2 Final P2 evidence

The final packet is under:

`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/`

| Artifact | SHA-256 | Result |
|---|---|---|
| `rejected_state.json` | `b185dc8caf3153c524df368c70cbf5395eada198e22d40e1763f5f29bb15a7f1` | Machine packet `PASS`; campaign gate remains review-required |
| `state_identity.json` | `05f1f2328a066b1b48878519bae299e7fce69e08658761cb714f848f5a9a9d20` | Native build/scene/display identity |
| `contact_records.json` | `e857dfca6ae3e2e31f44a811a89431dda36ee4cc2237db2ad8ab708d53526f60` | Contact count/depth/onset/penetration unknown where not exposed |
| `inspection-scene/fdi31-p2-rejected-state.mrb` | `8ded0a8237aa220ff51cb4ea733ff950fad459f5b9ae9e883e3222b1c9a9aa47` | Rotatable display-only inspection scene |

The native diagnostic loaded the corrected source/install identities
(`collision_guard.cpp` SHA-256
`8259a062b8c314fedb7a5ac95652a53ea280cfca2b67a6f6eda57b50ff2273b3`; binary
SHA-256 `f1132ea07d81c39249539c05c8900c817f39d50a95a6574ac3974f17e512fc3d`).
The correlated scene acknowledgement observed all 31 expected objects with
matching IDs, poses, bounds and policy fingerprint; the before/after scene
fingerprints were both
`f02a4251ffca8d9a3918d0ab4f2a26c2edb15233a859c426f16d66578e7b1475`.

The two predicates remain distinct, and the retained packet contains a static
endpoint result; it is not correct to summarize the packet as having no static
endpoint result:

- The phase-aware static-state predicate is authoritative and rejected both
  retained endpoint candidates. Its native non-approved pair is
  `[Step 5C] DENTO Final Printable Template` ↔
  `pneumatic_spindle-Copy`; the validation kind is `static_state`, with one
  evaluated endpoint sample and world-object count 31.
- The separate generic static predicate also rejected both explicit endpoint
  joint states and reported the contact list containing final printable
  template ↔ spindle, FDI31 target tooth ↔ burr, and FDI31 target tooth ↔
  spindle. This generic contact list is retained as generic static evidence;
  it must not be merged with the phase-aware allowance decision.
- The validate-only transition starts from setup Home
  `[0, 0, 0, 0, 0]`, not an accepted r13 preceding edge. Candidate 0 first
  rejects sample 1 of 134 at interpolation fraction
  `0.00746268656716`, evaluated at
  `[0.000827557298873, 0.000437667886694, -0.00438198502603,
  0.000498701721538, 0.0064257650803]`, because the provisional tip left
  the approved Entry-to-Target corridor. This remains a transition result,
  not a Target static verdict and not a reconstruction of the r13 insertion
  edge.

The phase-aware static check used the existing drilling-phase, validate-only
guard policy without changing the collision matrix. In particular,
`guide_clearance_warning=false` means that this endpoint query produced no
configured spindle/guide warning or admitted guide contact; it does **not**
mean that the endpoint had no collision. The active policy keeps the default
minimum clearance at `1.0 mm`, uses the bounded preferred `0.1 mm` clearance
for the configured burr-to-guide case, and permits only the exact configured
spindle-to-guide contact classification up to `0.5 mm` penetration when the
required finite contact evidence is available. Other contacts, including the
reported template ↔ spindle pair, remain non-approved. The exploratory
burr-to-target allowance does not authorize spindle-to-template or
spindle-to-tooth contact.

The original r13 record is different historical evidence from a guarded
trajectory: it contains positive spindle-tooth guide clearances and bounded
spindle ↔ final-template warning contacts, while the full chain ultimately
rejects target tooth ↔ spindle. Those r13 warnings are not the result of this
one-sample static query, are not an acceptance of the endpoint, and do not
relax the current policy.

The display-only goal robot now includes the repaired
`burr_goal_transform` alias. At the retained joint vector, native FK and
display transforms match for TCP, spindle and burr: TCP translation error is
approximately `1.48e-5 mm`, spindle `4.26e-14 mm`, burr `5.32e-14 mm`, and
all three rotation errors are `0.0°`, within `0.25 mm`/`0.5°` tolerances.
The close-up contains the FDI31 collision-audit mesh, burr and spindle in
distinct display colours; surrounding anatomy is hidden for display only.
The 31 collision-audit copies remain in the native collision payload.

Five nonblank labelled captures and the rotatable MRB are saved under the
packet's `screenshots/` and `inspection-scene/` directories. They remain
review evidence only. Native contact count, depth, onset, nearest points and
penetration are still explicitly unknown where the guard does not expose
them.

### T.3 Corrected disposition and stopping point

The corrected disposition is:

- P1 saved-input/machine checks: **PASS for the checks actually completed**.
- P1 overall scene correctness and operator review: **INCOMPLETE**.
- P2 bounded native diagnostic/evidence packet: **PASS**.
- Campaign gate: **USER_REVIEW_REQUIRED**; `operator_acceptance` remains
  **NOT_RECORDED**.

This does not accept the 15 automatic selections, scene geometry, contact
geometry or any clinical/normal-window result. The recovered container
runtime is stable after bounded cleanup, but the campaign remains stopped
for operator review. No P3/P4 or later phase is authorized.

## U. Operator-review handoff from retained final P2 packet — 2026-09-15

This is the current concise review handoff for Campaign 1. It supersedes
active summaries that still call the final packet `P2 INCONCLUSIVE`; the
earlier Q/R/S attempts, including the zero-object acknowledgement and the
container/launcher failures, remain preserved as historical attempts and are
not rewritten. This handoff performed no runtime, Slicer, ROS, Docker, native
diagnostic, geometry or policy operation.

### U.1 Corrected collision-result summary

| Evidence class | What was actually evaluated | Retained result | Attribution boundary |
|---|---|---|---|
| Phase-aware static endpoint | Both unchanged retained endpoint candidates, `validation_kind=static_state`, one endpoint sample each | Both rejected; non-approved pair was final printable template ↔ `pneumatic_spindle-Copy`; `guide_clearance_warning=false` | This is a static endpoint result. It is not “no static result,” and it is not a transition sample. |
| Generic static contacts | The same explicit endpoint joint states through the generic MoveIt static predicate | Rejected contact list includes final printable template ↔ spindle, FDI31 target tooth ↔ burr, and FDI31 target tooth ↔ spindle | Generic contacts are reported separately from phase-aware allowance classification; they do not by themselves establish which phase allowance applies. |
| Home-to-endpoint transition | Setup Home `[0,0,0,0,0]` to each requested endpoint using validate-only interpolation | Both rejected at the first interpolated sample for corridor violation; candidate 0 is sample `1/134`, fraction `0.00746268656716` | This is a transition result, not a Target static verdict and not the original r13 insertion edge. The evaluated sample is recorded separately from the requested endpoint. |

### U.2 Collision-policy mode used by the static check

The static check used the existing drilling-phase, `validate_only=true`
phase-aware guard in a one-sample static-state mode. It did not change the
collision policy or promote any contact to acceptance.

- `guide_clearance_warning=false` records that the static endpoint query
  reported no configured guide warning/admitted guide contact. It does not
  mean “no collision” and does not override the non-approved
  template ↔ spindle rejection.
- The source retains a default minimum clearance of `1.0 mm`, a preferred
  `0.1 mm` clearance for the configured burr-to-guide pair, and a bounded
  spindle-to-guide contact allowance only when the exact configured pair has
  finite evidence and penetration is at most `0.5 mm`. The exploratory
  burr-to-target allowance is separate and does not authorize spindle-to-
  template or spindle-to-tooth contact.
- The original r13 evidence came from a guarded trajectory, where positive
  spindle-tooth clearances and bounded spindle ↔ final-template warning
  contacts were recorded before the eventual target-tooth ↔ spindle
  rejection. Those warnings are historical path evidence, not this static
  endpoint result and not an acceptance license.

The relevant retained source/configuration evidence is
`dentobot_moveit_config/src/collision_guard.cpp`; the comparison record is
`data/Slicer_Saved/SampleStudy1/FDI31/packet-a-fdi31-r7/diagnostics/FDI31-stage6-exact-r13.json`.

### U.3 Automatic selections and derived outputs

All 15 rows below were automatically selected or derived. Every P1 record has
`operator_confirmed_in_this_run=false` and `operator_review_required=true`.
The machine-verified column is evidence for review, not a request that the
operator certify technical checks.

| # | Actual selected value/object | Supporting evidence / provenance | Machine-verified facts | Unresolved question | Decision required from operator |
|---:|---|---|---|---|---|
| 1 | Immutable source package `dentobot-case-13sept.dentocase`, UUID `bedc5f68-7df1-4f79-ae47-ee0a0b5608dd` | P1 immutable package manifest; SHA `14ed8f0f…a15` | Scene SHA `1a4bd617…4ab2`; Slicer 5.10; mm/SlicerRAS; serialized ROS/motion false | Is this the intended frozen source package for review? | Confirm intended source package, not its hash calculation. |
| 2 | Diagnostic package `packet-a-fdi31-20260914-r7/FDI31-step5c.dentocase`, UUID `67b12db9-669a-4ebf-b7b0-cabd1563cff5` | P1 diagnostic-package selection and saved packet | SHA `5440961c…4fff`; scene SHA `6aded01c…7b4e`; same coordinate/runtime serialization boundary | Is this the intended FDI31 Step 5C diagnostic package? | Confirm intended diagnostic package. |
| 3 | Case Foundation: Manual Simulation Base `VALID`; planning pose `VALID` | Read-only foundation/pose eligibility and fingerprints | Base, foundation, planning-pose, segmentation and source-volume fingerprints were internally recorded; base is current/eligible | Is the saved base/pose the intended planning reference? | Confirm intended foundation/base/pose. |
| 4 | Whole-tooth target `FDI31 / Tooth_FDI31`, lower-left central incisor; segment `2.25.127809691704402484963988182477922906518` | Semantic target selection from the saved segmentation | Label 27; 211.375 mm³; 1,691 voxels; source association validated; confidence field null | Is FDI31 the intended tooth and association? | Confirm intended target tooth. |
| 5 | Saved Entry/Target line: Entry `[-95.5797808828,-68.3080212751,32.5242792904]`; Target `[-95.0791174633,-74.1254665588,29.2961247214]`; length `6.6719049312 mm` | Saved two-point trajectory record | Two points; `isValid=true`; native diagnostic retained the requested endpoint separately | Is this the intended line and endpoint, independent of guard outcome? | Confirm intended Entry/Target line. |
| 6 | Assisted entry set: one point equal to saved Entry; no fallback | Saved assisted-entry record | `expected=1`; `complete=true`; no generated fallback | Is this assisted-entry object distinct from the guide bore and intended for this case? | Confirm intended assisted-entry selection. |
| 7 | Draft support: current, locked, 9,322 points/18,600 cells; four support IDs | Saved support geometry and target association | Support count 4; stale reason empty; target association matches FDI31 | Are these four supports the intended draft support geometry? | Confirm intended support set. |
| 8 | Visible support: current five-tooth support `[FDI31, FDI42, FDI41, FDI33, FDI32]` | Saved visible-support selection and trajectory-direction mode | 2,069 points/3,669 cells; reversal false; 0.5 mm spacing; terminal coverage 50%; 459 boundary/nonmanifold edges in visible support | Is this the intended displayed support/trimming state despite the recorded surface metric? | Confirm intended visible support state. |
| 9 | Docking assembly: four independent occlusal tangent docks; yaw 35°; depth 5 mm; robot bore 1.5 mm; connector 3.5 mm; clearance 0.5 mm; no omitted obstacles | Saved docking assembly parameters and screen | 5,300 points/10,600 cells; minimum sampled dock clearance 1.466976 mm; 0 sampled dock collisions; top-plane residual ~`4e-15 mm` | Are these four robot-dock bores being distinguished from any trajectory-guide bore? | Confirm intended dock layout and bore-role interpretation. |
| 10 | Insertion direction Entry→Target, vector `[0.07504055,-0.87193168,-0.48384301]`, length `6.6719049312 mm` | Saved trajectory-direction record | Reversal false; removal is negative; source surface/trajectory identities match retained Step 4A/4A-complete records | Is this the intended drilling axis and requested depth? | Confirm intended direction/depth. |
| 11 | Patient-contact shell: current, processed undercut, 15,524 points/31,044 cells, 1.5 mm thickness, 0.4 mm fit clearance | Saved shell record and repair provenance | Final topology has one region and zero boundary/nonmanifold edges; candidate source had 23 edges and was rebuilt from validated fitting surface | Is the fitting-surface repair fallback acceptable for operator review and later fit assessment? | Decide whether the shell is the intended review object; do not certify clinical fit here. |
| 12 | Final printable template: current but verification `WARNING`; 58,868 triangles; four through-open robot-dock bores | Saved final-template record and STL diagnostics | One connected occupied/watertight volume; zero boundary/nonmanifold; no residual fused channel voxels; bore metrics include 1.5 mm diameter and 0.3 mm minimum surface clearance; clinical fit/collision warning remains | Is this the intended printable template and are the four openings the intended robot docks? | Confirm intended template/bore interpretation; no clinical acceptance is requested. |
| 13 | Finalized template shell role: no independently materialized object value in `scene_audit`; saved final STL exists | Saved-scene role rule plus `DENTO_Final_Printable_Template.stl` | Audit value is `null`; final STL exists; role selection was not independently materialized in the P1 audit | Which saved model should be treated as the finalized-shell review object? | Identify the intended finalized shell/STL for visual review. |
| 14 | Restored Step 6 package state: `PlanningPackage`; branch `guide-5c0da27697aceceb8f14`; manual-simulation base `ProvisionalLocked`; task Home null | Fresh package hydration and restored-state record | One current branch; base locked; `runtimeRestorePolicy=never-auto-connect`; serialized motion false; FDI31 slot state `Unreviewed` | Is this the intended restored Step 6 branch/base state? | Confirm intended saved workflow state. |
| 15 | Collision payload: no P1 object selected (`null`); later native correlated payload contains 31 objects | P1 saved-package audit plus final native scene acknowledgement | Final native readback trusted 31/31 matching IDs, poses, bounds and policy fingerprint; display-only scene keeps collision copies | Is the existing native/display evidence sufficient to explain the retained rejected pair? | Decide whether the review packet is sufficient or a display-only recapture is needed. |

### U.4 Screenshot and state attribution

| Existing view | Adequate for | Missing / not established |
|---|---|---|
| `p2-context.png` | Broad source/scene orientation and presence of the robot/guide apparatus | Does not identify the evaluated robot state or the template ↔ spindle pair. |
| `p2-target-state.png` | Target/marker context for the retained display-only endpoint scene | Robot configuration and native evaluated sample are not visible. |
| `p2-first-rejected-close-up.png` | Labelled first-invalid marker context | It does not visibly demonstrate the robot state evaluated at transition sample `1/134`. |
| `p2-visible-vs-collision-payload.png` | Display-only surfaces versus the retained collision-audit payload; anatomy hiding is display-only | It is not native contact rendering and does not identify the template ↔ spindle pair by itself. |
| `p2-fdi31-burr-spindle-close-up.png` | Display-only burr/spindle relationship; native FK comparison supports placement at the retained joint vector | FDI31/template is not in the frame, so it does not explain the reported template ↔ spindle contact. |
| Saved `fdi31-p2-rejected-state.mrb` | Rotatable display-only review scene with the retained robot/collision payload | It cannot by itself prove native contact locations or substitute for the missing state-labelled frames. |

If separately authorized, a limited **display-only saved-scene recapture** can
fill the two visual gaps without rerunning native planning or diagnostics:

1. A transition frame with the display-only robot at the exact evaluated
   sample-1/134 vector, Entry/Target/corridor, sample index/fraction, Home
   vector and requested endpoint labelled as separate fields.
2. A static endpoint frame with the display-only robot, FDI31, final printable
   template and spindle together, labelled `phase-aware static_state` and
   `template ↔ spindle`; generic tooth/burr and tooth/spindle contacts should
   remain separately labelled if shown.

The 31-object collision payload must remain intact. Hiding anatomy in these
frames would be display-only and would not remove anything from native
collision checking. This recapture is proposed, not executed, and does not
constitute P1/P2 acceptance.

### U.5 Current stop and specific unresolved questions

1. Are the frozen source/diagnostic packages, Case Foundation/base, FDI31
   target, saved Entry/Target line and endpoint direction in rows 1–5 and 10
   the intended inputs for review?
2. Are the selected support sets, four robot-dock assembly, patient-contact
   shell, final printable template/STL and restored Step 6 branch/base in rows
   7–14 the intended geometry/workflow objects? In particular, should the
   four robot-dock bores be treated as distinct from a trajectory-guide bore?
3. Is the existing packet sufficient for review of the phase-aware static
   template ↔ spindle rejection, generic static contacts and Home-to-endpoint
   corridor rejection, or is the proposed display-only recapture requested?
4. If recapture is requested, is approval limited to the two saved-scene
   display-only frames above, with no native rerun and no P3/P4?

Operator acceptance remains `NOT_RECORDED`; P1 overall scene correctness and
operator review remain `INCOMPLETE`; P3/P4 and all later or hardware actions
remain unauthorized.

## V. Approved offline display-only recapture/review — 2026-09-15

**Scope and status.** The operator authorized one bounded offline Slicer
display-only recapture using the retained inspection MRB and its matching final
P2 JSON packet. This session was an evidence-presentation operation only. It
did not confirm the frozen selections, geometry, clinical intent, P1/P2
acceptance, or any operator-confirmed flag.

**Retained inputs.** The source inspection scene was
`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/inspection-scene/fdi31-p2-rejected-state.mrb`
(SHA-256
`8ded0a8237aa220ff51cb4ea733ff950fad459f5b9ae9e883e3222b1c9a9aa47`). The
matching rejected-state record was
`.../corrected-p2/burr-alias-recheck-corrected/rejected_state.json` (SHA-256
`b185dc8caf3153c524df368c70cbf5395eada198e22d40e1763f5f29bb15a7f1`), with
the matching `state_identity.json` retained alongside it (SHA-256
`05f1f2328a066b1b48878519bae299e7fce69e08658761cb714f848f5a9a9d20`). The
original MRB and packet were not overwritten.

**Execution boundary.** The existing Slicer offline-FK path
(`DENTORobotPlacement.py` through
`DENTOWorkflowLogic.createOrUpdateRobotPlacement` and
`updateRobotJointPoses`) placed display meshes at the saved states. No ROS,
MoveIt, native diagnostic, planner, controller, spindle, trajectory execution,
collision-policy or container lifecycle operation (start/restart/recreate) was
performed; the already-running container was used only as the display-only
Slicer host. The output scene used new display-only copies/annotations and
retained the collision payload; hiding or changing opacity did not remove
collision objects.

**Outputs, in workflow order.** The static endpoint view was written first,
followed by the transition-sample view, in the separate directory
`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915/`.

1. `01-static-endpoint.png` (SHA-256
   `33d2552ba0702c08bc50766b24728f6d93c77911e92466a23f3c7f5614c7ec88`)
   shows FDI31, the retained final printable template, burr and spindle at the
   exact recorded endpoint joint vector. The frame labels the result as the
   phase-aware `static_state` rejection of both retained endpoint candidates
   and labels the reported native pair as `final printable template ↔
   spindle`. Native contact point, penetration depth and clearance were not
   exposed by the retained record, so none is rendered or inferred.
2. `02-transition-sample-1-of-134.png` (SHA-256
   `55b42c909b0a0d0d0cf84bbd09b4308ef096f00cd8cbc7c04eed1f1bec985a19`)
   shows the display robot at the actual evaluated sample 1/134, not at the
   requested endpoint. It labels Home, the requested endpoint, the evaluated
   state, the Entry-to-Target corridor and interpolation fraction
   `0.00746268656716`. Its reason is the recorded corridor violation. It is
   explicitly labelled as the diagnostic Home-to-endpoint transition, not the
   original r13 insertion or a collision-onset reconstruction; collision onset
   remains unknown.

The rotatable scenes are
`01-static-endpoint.mrb` (SHA-256
`eda5526c773cacfa55960903dccf76997ebef34a74f4fd22d47b059357a1cf12`) and
`02-transition-sample-1-of-134.mrb` (SHA-256
`3f298cdd71651fc6ef9acaa4dd3723b87283423780be1370b4d93fca88f41c75`). The
machine-readable manifest is
`display-only-recapture.json`. It records the exact endpoint and evaluated
sample vectors, the output hashes, the unchanged runtime boundary, and
`operator_confirmed_in_this_run=false` / `operator_acceptance=NOT_RECORDED`.

**Visual sufficiency limits.** The endpoint frame visibly demonstrates the
four requested display objects and their roles, but deliberately does not
visually demonstrate a native contact point, depth or clearance. The
transition frame's top attribution banner and saved manifest identify sample
1/134 and its fraction; the numeric state labels in the 3-D view are partially
clustered, so the image alone is not sufficient to re-derive every numeric
joint value without the manifest. These limits are explicit and do not turn
display evidence into native contact evidence.

**Read-only object-identity explanation.** The draft support and visible
support are different saved objects. The draft support is the current locked
surface built from four recorded source support IDs. The visible support is a
trajectory-direction display/fitting surface selected from five teeth,
`FDI31, FDI42, FDI41, FDI33, FDI32`, so the visible five-tooth surface is not
a fifth draft-support ID and does not replace the four-ID source record.

The P1 audit has no independently materialized `FinalizedTemplateShell` role
object (`value=null`), while the retained scene and packet do contain the
`FinalPrintableTemplate` model and the exported
`DENTO_Final_Printable_Template.stl`. The STL is therefore the saved final
printable-template artifact; it must not be described as proof that a separate
finalized-shell role object was present.

The four robot-dock bores and the drilling trajectory guide are separate
geometry roles. The saved docking assembly has four independent occlusal
tangent robot docks (1.5 mm robot bore, 3.5 mm connector, 5 mm depth, 0.5 mm
clearance). The trajectory guide is a separate Entry-to-Target guide sleeve
(2.0 mm inner diameter, 4.4 mm outer diameter, 2.5 mm height, 0.3 mm
clearance). A final template may contain both systems; a dock bore is not
evidence of a drilling-trajectory bore.

**Disposition.** This recapture does not change the gate: P1 saved-input and
completed machine checks remain PASS, P1 overall scene correctness and
operator review remain INCOMPLETE, the bounded native P2 packet remains the
current evidence with `USER_REVIEW_REQUIRED`, operator acceptance remains
`NOT_RECORDED`, and P3/P4 remain unauthorized. No downstream phase follows
from these images.

## W. Operator-observed recapture inconsistency — read-only diagnosis, 2026-09-15

**Current visual disposition: FAIL — recapture frame/state attribution and
saved robot-pose persistence.** This supersedes Section V's visual-sufficiency
claim, not the retained native packet. The operator observed that the template,
FDI31 and robot were separated despite the static collision label, and asked
why the images did not show the collision state. No new execution or repair
was authorized by that question.

Read-only ZIP/XML/VTK inspection of the original inspection MRB and both
`display-only-recapture-20260915/*.mrb` outputs establishes:

1. **Wrong tooth display frame.** `[Review] FDI31 target tooth` has no parent
   transform and its mesh bounds equal the original, unopened source target:
   RAS/mm `[-97.44219,-92.17423,-43.18369,-35.97752,38.08550,56.09957]`.
   The native audit's prepared target bounds are
   `[-98.23880,-92.97633,-83.92379,-68.10648,23.12273,34.02298]`.
   Applying the saved mouth-opening matrix to the review mesh reproduces
   those prepared bounds to approximately 0.0001 mm using rounded MRML
   matrix values. Mean vertex displacement is approximately 40.89 mm.
   In contrast, the final template retains its mouth-opening parent and its
   transformed bounds agree with the saved native template audit. The tooth
   copy therefore mixes unopened anatomy with opened planning geometry;
   this is not evidence that the template should be moved or regenerated.

2. **Static labels use the transition state.** In
   `01-static-endpoint.mrb`, `[Review] Static endpoint labels.mrk.json`
   places Burr at world RAS/mm
   `[-50.7899670853,-28.0827267545,47.3972628722]` and Spindle at
   `[-44.8423703244,-2.92831899432,56.0601471303]` after LPS-to-RAS
   decoding. These exactly match the manifest's evaluated-sample centres,
   not its endpoint centres. The endpoint burr centre is
   `[-95.3410878049,-71.0737663126,30.9895842976]`, 64.04876 mm away.
   The endpoint spindle centre differs by 70.17038 mm. Thus the static
   view's state attribution is inconsistent even before accepting the
   displayed robot pose. The temporary driver was reported removed; the
   precise command/callback ordering that caused this is not established.

3. **Both exported MRBs omit seven referenced robot pose transforms.**
   Robot models reference `vtkMRMLLinearTransformNode6` through `12`, but
   these IDs have no node definitions in either exported MRML. The local
   placement helper deliberately marks its link transforms transient with
   `SetSaveWithScene(False)`. The exports therefore do not contain a
   self-contained saved robot pose. This is a recapture persistence defect,
   not proof that the in-memory screenshot lost those same transforms.

The retained native candidate-0 TCP remains at world RAS/mm
`[-95.0784453044,-74.1255333200,29.2961220580]`, with reported Target
position error `0.00067547155 mm`. That prior native result must not be
conflated with the defective new display reconstruction. The Home-to-endpoint
sample still represents corridor rejection near Home, not the r13 insertion
collision onset. No native collision result is invalidated merely by these
recapture defects; overall native/display parity is not newly accepted.

**Required bounded correction, not execution authorization:** Luna should
repair the review reconstruction against the saved prepared geometry and
native FK, prove frame/state identity immediately before each capture, and
make the review robot pose self-contained across save/reopen. Preserve the
production model's transient-node policy; do not fix this by globally saving
runtime nodes. Retain a reproducible recapture driver. No camera-only retry,
manual geometry repositioning, collision-policy change, planner change or
P3/P4 action follows. The pending item remains under the existing campaign
owners `S6-REUSABLE-CASE-SETUP` / `S6-LIVE-01..02`.

## X. Source-only review recapture correction — 2026-09-15

**Scope and disposition.** In response to Section W, the review-only capture
path was corrected in source without starting Slicer, ROS, Docker, MoveIt,
planning or native diagnostics. No image or new MRB was produced by this
correction, and the prior recapture images/scenes remain explicitly
unaccepted. Operator acceptance remains `NOT_RECORDED`; P1 overall scene
correctness remains `INCOMPLETE`; P3/P4 remain unauthorized.

**Retained driver.** The reproducible driver is now
`Testing/run_dentobot_c1_display_only_recapture.py`, with focused pure checks
in `Testing/test_dentobot_c1_display_only_recapture.py`. It keeps the existing
production robot-placement transient policy unchanged. Review-only copies are
marked display-only and excluded from collision use; the source target and
final template are never moved or rewritten.

**Corrections implemented.** Each requested view starts from a fresh load of
the retained inspection MRB and carries its own explicit state record. The
static endpoint uses the saved endpoint joint vector and the transition view
uses the saved evaluated sample `1/134` plus its recorded starting/requested
vectors and interpolation fraction. The target surface is copied from the
existing world-RAS segmentation-surface helper, and the final printable
template is copied from the existing world-RAS target-attached helper; neither
copy inherits the defective unopened-tooth frame. Geometry is compared by the
existing collision-audit fingerprint and prepared world bounds before any
image is permitted.

Robot review nodes are explicitly made persistent only in the separate review
MRB. After save/reopen, the driver resolves the same saved review target,
template, corridor, labels, base, seven robot models and seven link
transforms; it does not call placement/FK again to manufacture a passing
state. It numerically compares every displayed mesh transform and every
persisted link transform before versus after reopen. For the endpoint it also
compares the displayed TCP, burr and spindle link frames against the saved
native FK matrices, while retaining the offline FK-to-native comparison as a
separate record. A saved TCP marker alone is never accepted as transform
evidence.

**Fail-closed limit.** The retained P2 packet contains native FK matrices for
the endpoint but only a joint vector for transition sample `1/134`. Therefore
the corrected driver will not present a transition image until native
evaluated-sample FK matrices are actually present in the saved evidence. It
does not substitute offline FK, endpoint FK, a marker or a requested endpoint
for that missing native state. This is a missing-evidence blocker, not a new
native run authorization.

**Source verification.** The following source-only checks completed:

```text
PYTHONPYCACHEPREFIX=/tmp/dentobot-c1-display-corrected-pycache python3 -m py_compile Testing/run_dentobot_c1_display_only_recapture.py Testing/test_dentobot_c1_display_only_recapture.py
PYTHONPYCACHEPREFIX=/tmp/dentobot-c1-display-corrected-pycache python3 -m pytest -q -p no:cacheprovider Testing/test_dentobot_c1_display_only_recapture.py
9 passed in 0.02s
```

The graph overlay was refreshed successfully after the code change. No
display-runtime scope was exercised. A future display-only run remains a
separate approval-gated action and must stop before an image if the endpoint
geometry/FK/save-reopen parity or the transition native-FK prerequisite is
not proven. If a future retained packet carries evaluated-sample FK under the
transition evidence record, the driver consumes that record; the current
packet remains empty and therefore blocked.

## Y. Authorized endpoint-only review — pre-execution record, 2026-09-15

The operator explicitly superseded the two-image deliverable for the next
attempt with an endpoint-only review. The transition numerical record remains
preserved and will be reported as `NOT_RUN`; no new native FK will be obtained
and no further transition-FK parsing is added for this session.

The minimal source change adds the explicit endpoint-only mode
`DENTOBOT_C1_RECAPTURE_ENDPOINT_ONLY=true`. Focused source checks pass (`9
passed`). The output location was verified absent before execution:

`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only/`.

The exact recorded invocation for the one bounded offline Slicer session is:

```bash
timeout 180s docker exec dentobot-slicerros2 bash -lc 'set -euo pipefail; export DENTOBOT_C1_RECAPTURE_ENDPOINT_ONLY=true DENTOBOT_C1_RECAPTURE_SOURCE_ROOT=/workspace/data/Slicer_Saved/SampleStudy1/FDI31 DENTOBOT_C1_RECAPTURE_INSPECTION_MRB=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/inspection-scene/fdi31-p2-rejected-state.mrb DENTOBOT_C1_RECAPTURE_REJECTED_STATE=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/rejected_state.json DENTOBOT_C1_RECAPTURE_STATE_IDENTITY=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/state_identity.json DENTOBOT_C1_RECAPTURE_OUTPUT=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only DENTOBOT_C1_RECAPTURE_MANIFEST=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only/endpoint-review.json; timeout 150s xvfb-run -a /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer --no-splash --additional-module-paths /workspace/ros2_ws/src/DentoBot/DENTOWorkflow --python-script /workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_c1_display_only_recapture.py'
```

This command starts only Slicer's offline display process inside the already
running container. It does not source or launch ROS, MoveIt or the simulation
stack, does not connect a controller, and does not run native diagnostics. The
inner `150s` timeout is enforced inside the container; the outer `180s`
timeout bounds the Docker invocation. The session must stop if any endpoint
geometry/FK/save-reopen check fails, without tolerance changes, geometry edits
or retry.

## Z. Endpoint-only runtime result and compatibility stop — 2026-09-15

The exact invocation recorded in Section Y was attempted once after a
read-only preflight. The existing `dentobot-slicerros2` container was already
up, and the exact process inventory contained no Slicer, Xvfb, ROS, MoveIt,
collision-guard, inference or trajectory process. A first host-side Docker
permission denial started nothing; the same command was then executed through
the approved elevated Docker access. The container was not started, restarted
or recreated.

Slicer entered the offline display path and loaded the retained inspection MRB
in approximately 1.04 seconds. Before the endpoint geometry/FK readiness gate
could run, the retained review driver raised:

```text
AttributeError: 'MRMLCorePython.vtkMRMLModelDisplayNode' object has no attribute 'SetPropertiesLabelVisibility'
```

The driver wrote the separate output manifest
`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only/endpoint-review.json`
(SHA-256
`25b6a9b113902967234b5edc2e875e72d40c06aae21b942e6df3ac4f5175594a`). The
directory contains only that 347-byte error manifest: no endpoint image, no
review MRB, and no parity sub-record. The container remained up after the
session, and the post-run process inventory was empty for the same task-owned
and native process classes; no operator-owned session was stopped.

**Endpoint status:** `NOT_ESTABLISHED` because the display runtime stopped at
an API-compatibility error before the endpoint gate. This is not an endpoint
geometry/FK mismatch and is not an endpoint `FAIL`; no prepared-world geometry
identity, displayed TCP/burr/spindle versus saved native endpoint FK, or
save/reopen comparison was obtained. No image or MRB can be presented from
this attempt.

**Transition status:** `NOT_RUN`. The saved transition numerical record,
including sample `1/134`, starting/requested/evaluated values and the missing
native sample-FK fact, remains in the frozen inputs. No new native FK and no
additional transition parsing path was used.

After the stop, the smallest source-only compatibility repair guarded the
optional display-label API and made early error manifests preserve
`offline_display_only_endpoint_review` / `endpoint_only`. `py_compile` and
the focused suite then passed:

```text
PYTHONPYCACHEPREFIX=/tmp/dentobot-c1-endpoint-only-pycache python3 -m py_compile Testing/run_dentobot_c1_display_only_recapture.py Testing/test_dentobot_c1_display_only_recapture.py
PYTHONPYCACHEPREFIX=/tmp/dentobot-c1-endpoint-only-pycache python3 -m pytest -q -p no:cacheprovider Testing/test_dentobot_c1_display_only_recapture.py
10 passed in 0.02s
```

Graphify was refreshed successfully (`8258 nodes, 12948 edges, 732
communities`; `Code graph updated`). The source repair is therefore pure-
verified, but the approved offline display runtime is not re-entered in this
turn. A replacement endpoint session requires a new, specifically bounded
approval. The retained native P2 packet is unchanged: P1 saved-input/machine
checks remain PASS for completed checks, P1 overall scene correctness and
operator review remain INCOMPLETE, operator acceptance remains
`NOT_RECORDED`, and P3/P4 remain unauthorized.

## AA. Authorized endpoint-only repair rerun — pre-execution record, 2026-09-15

The operator explicitly authorized a new bounded endpoint-only Slicer review
after the prior session stopped at the missing optional display-label API. The
authorization permits restarting the container only if needed to recover a
Slicer-testing blocker. It does not authorize ROS/MoveIt/native diagnostic
launch, planning, controller connection, spindle activation, trajectory
execution, geometry/policy changes or P3/P4.

The read-only preflight found the existing dentobot-slicerros2 container
already Up 3 hours, with no matching Slicer/Xvfb/recapture/ROS/MoveIt/
collision-guard/inference/trajectory process. The container was not restarted.
The frozen input hashes remain unchanged:

~~~text
inspection MRB   8ded0a8237aa220ff51cb4ea733ff950fad459f5b9ae9e883e3222b1c9a9aa47
rejected_state   b185dc8caf3153c524df368c70cbf5395eada198e22d40e1763f5f29bb15a7f1
state_identity   05f1f2328a066b1b48878519bae299e7fce69e08658761cb714f848f5a9a9d20
~~~

The prior error manifest and output directory are preserved. This rerun uses
the separate output directory
data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only-repair1/.

The exact invocation recorded before execution is:

~~~bash
timeout 180s docker exec dentobot-slicerros2 bash -lc 'set -euo pipefail; export DENTOBOT_C1_RECAPTURE_ENDPOINT_ONLY=true DENTOBOT_C1_RECAPTURE_SOURCE_ROOT=/workspace/data/Slicer_Saved/SampleStudy1/FDI31 DENTOBOT_C1_RECAPTURE_INSPECTION_MRB=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/inspection-scene/fdi31-p2-rejected-state.mrb DENTOBOT_C1_RECAPTURE_REJECTED_STATE=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/rejected_state.json DENTOBOT_C1_RECAPTURE_STATE_IDENTITY=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/state_identity.json DENTOBOT_C1_RECAPTURE_OUTPUT=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only-repair1 DENTOBOT_C1_RECAPTURE_MANIFEST=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only-repair1/endpoint-review.json; timeout 150s xvfb-run -a /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer --no-splash --additional-module-paths /workspace/ros2_ws/src/DentoBot/DENTOWorkflow --python-script /workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_c1_display_only_recapture.py'
~~~

The inner 150s timeout is enforced inside the container and the outer 180s
timeout bounds the Docker invocation. The transition image remains explicitly
deferred as NOT_RUN; this invocation must not enter transition capture.
Endpoint parity remains a fail-closed gate: any geometry, endpoint FK, or
save/reopen mismatch must stop the session without tolerance changes, geometry
edits or blind retry.

## AB. Endpoint-only repair1 runtime result — second compatibility stop, 2026-09-15

The Section AA invocation ran once in the existing container. It passed the
previous missing SetPropertiesLabelVisibility call, loaded the retained MRB in
approximately 1.20 seconds, and reached the review driver's world-transform
reader. It then stopped before the endpoint geometry/FK/save-reopen gate with:

~~~text
AttributeError: 'MRMLCorePython.vtkMRMLModelNode' object has no attribute 'GetMatrixTransformToWorld'
~~~

The separate repair1 output contains only
endpoint-review.json (361 bytes, SHA-256
1ec4cb53791b7ece4aef65b9ef4f324e7e1871819407a725e1747cfb7f432750). No image,
review MRB or parity record was written. Endpoint status remains
NOT_ESTABLISHED; this is a second runtime API-compatibility stop, not an
endpoint geometry/FK parity failure. Transition status remains NOT_RUN and no
native FK was requested or obtained.

The container stayed Up 3 hours and the post-run inventory was empty for the
checked Slicer/Xvfb/ROS/MoveIt/guard/inference/trajectory classes. No
operator-owned process was touched and no container restart was needed.

The smallest source-only repair adds a direct world-matrix path for transform
nodes and a fail-closed parent-transform fallback for transformable model
nodes; models without a parent use identity. It does not move source anatomy,
the template, burr or spindle, change collision policy, or change the native
diagnostic path. The pure checks now pass 12 tests and Graphify refreshed with
Code graph updated (`8266 nodes, 12962 edges, 731 communities`).

## AC. Endpoint-only repair2 rerun — pre-execution record, 2026-09-15

The current operator authorization covers this needed source repair and one
further bounded endpoint-only Slicer attempt. The preflight again found the
existing container Up 3 hours, no matching Slicer/Xvfb/ROS/MoveIt/guard/
inference/trajectory process, and the repair2 output directory absent. No
restart is currently needed. This is the last display-runtime attempt under
the existing three-failure ceiling; the frozen input hashes and all prior
error artifacts remain preserved.

The exact invocation recorded before execution is:

~~~bash
timeout 180s docker exec dentobot-slicerros2 bash -lc 'set -euo pipefail; export DENTOBOT_C1_RECAPTURE_ENDPOINT_ONLY=true DENTOBOT_C1_RECAPTURE_SOURCE_ROOT=/workspace/data/Slicer_Saved/SampleStudy1/FDI31 DENTOBOT_C1_RECAPTURE_INSPECTION_MRB=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/inspection-scene/fdi31-p2-rejected-state.mrb DENTOBOT_C1_RECAPTURE_REJECTED_STATE=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/rejected_state.json DENTOBOT_C1_RECAPTURE_STATE_IDENTITY=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/state_identity.json DENTOBOT_C1_RECAPTURE_OUTPUT=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only-repair2 DENTOBOT_C1_RECAPTURE_MANIFEST=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only-repair2/endpoint-review.json; timeout 150s xvfb-run -a /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer --no-splash --additional-module-paths /workspace/ros2_ws/src/DentoBot/DENTOWorkflow --python-script /workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_c1_display_only_recapture.py'
~~~

The inner and outer timeouts remain 150s and 180s. The endpoint parity gate
remains fail-closed; transition capture remains explicitly NOT_RUN.

## AD. Endpoint-only repair2 result — parity gate failed closed, 2026-09-15

The repair2 session reached the intended endpoint parity gate and stopped before
save/reopen capture or image generation. The output manifest is
data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only-repair2/endpoint-review.json
(26,492 bytes, SHA-256
3362594236be3227729b5dd59dde7ebcd4cc592b971644465a174b12075ebd3c). No PNG
or review MRB was written because the pre-save parity gate was BLOCKED.

**Measured endpoint evidence:**

- Final printable template: fingerprint match true; maximum bounds error
  0.0 mm against the 0.05 mm tolerance.
- Prepared FDI31 target: fingerprint mismatch. Display fingerprint
  0dce3add8f84d8c990166a8190005ed0f1ad0f8d9b5a738b62521be07a543372 did
  not match the native prepared fingerprint
  cb420afb7bb43829b235e0dc30780b1d85290d508757c8320c5474a10211231d.
  Maximum bounds error was 40.74010467529297 mm against the 0.05 mm
  tolerance. This is the exact endpoint geometry mismatch; no geometry was
  moved and no tolerance was weakened.
- Displayed robot mesh transforms and model-to-link transforms matched their
  offline FK-derived expectations. The saved native-vs-offline endpoint FK
  comparison also matched for TCP, burr and spindle; the TCP translation error
  there was 0.000014754016507267919 mm against 0.25 mm.
- Displayed burr and spindle versus saved native FK matched with zero-degree
  rotation error and translation errors approximately 1.07e-13 mm and
  1.22e-13 mm, respectively. Displayed TCP versus saved native FK was
  unavailable, not accepted: the actual seven-model display set contains
  link-1 through link-5, the spindle and the burr, while the retained catalog
  exposes TCP only as a transform node. The driver correctly rejected using a
  TCP marker or transform-only record as proof of a displayed TCP mesh/link.
- Save/reopen pose parity was not reached because the pre-save gate failed.

**Read-only source attribution:** The driver calls the existing
_segmentationSegmentsSurfaceWorld helper for the target. That helper applies
the segmentation parent-to-world transform. The retained native prepared-target
record includes the Case Foundation/jaw-opening world frame; the target helper
path used here does not apply that additional prepared frame. The final
printable template uses the existing target-attached world-polydata helper and
therefore matches. This identifies a display-contract/frame mismatch, not
permission to move the actual target, regenerate anatomy, change the template,
or change collision policy. The TCP discrepancy is a separate display-evidence
contract gap, not evidence that native TCP FK is wrong.

**Current status:** Endpoint review is BLOCKED on the exact target geometry
mismatch and unavailable displayed TCP evidence. Transition remains NOT_RUN;
its saved sample 1/134 numerical record and missing native FK fact are
preserved. The three display-runtime attempts and their error/parity artifacts
are retained; the retry ceiling is reached for this scoped review. The native
P2 packet is unchanged, P1 overall scene correctness/operator review remain
INCOMPLETE, operator acceptance remains NOT_RECORDED, and P3/P4 remain
unauthorized. No further runtime, geometry/policy repair or tolerance change is
performed under this approval.

## AE. Endpoint-only parity repair2 — revised repair authorization and preflight, 2026-09-15

The operator's new endpoint-only authorization supersedes the prior repair2
runtime stop for this narrowly defined correction only. It authorizes the two
source repairs below, focused pure checks, and at most three further targeted
offline Slicer endpoint attempts. It does not authorize ROS/MoveIt/native
diagnostic launch, planning, transition capture, controller connection,
spindle activation, trajectory execution, geometry/policy changes or P3/P4.
The previous repair1/repair2 artifacts and retry history remain preserved.

**Correction 1 — target preparation.** Read-only production tracing confirms
that native Step 6 collision construction extracts the segmentation closed
surface in world RAS, applies `_step6CaseJawPolydataWorld` once to a moving
target, then applies `vtkTriangleFilter` with lines and vertices disabled.
The retained selected-target record independently requires one jaw-transform
application and retains jaw fingerprint
`9b5664b66fd730cfe6180245e43f4ab31412ce7405f1f29989acd6ed55b75fcb`. The
review driver now applies that unchanged helper exactly once to a display-only
copy, reproduces the native triangle-filter semantics, and checks the source
and prepared fingerprints/bounds against the frozen record. Source
segmentation, parentage, anatomy, trajectory, final template and native
collision payload are not modified.

**Correction 2 — meshless TCP.** The retained robot profile and source URDF
define `dentobot_drill_tcp` as a canonical non-spinning frame with no physical
visual mesh, fixed to `pneumatic_spindle-Copy`. The driver now obtains the
displayed spindle mesh transform, removes its URDF visual-origin offset to
recover the observed spindle-link pose, derives the fixed spindle-link-to-TCP
matrix using the existing `link_transforms_base_m` utility, and compares that
derived observed TCP independently with retained native endpoint TCP FK. It
also requires the loaded robot-profile identity to match the retained
`robot_profile_fingerprint`; no marker or transform-only node is used as
proof.

**Source verification before runtime.** Host and mounted-container hashes
match: driver
`75953b2faf9567f4c90d254dba3509a6e4a3236b2de31f9400911fc37184bb14`, tests
`cdf50314409460fd58fa55fecbbb4b8b13e528e3aea07d754104769e51ea5c8a`.
Compilation without bytecode writes passed; focused tests passed `18/18`.
Graphify was refreshed successfully (`8292 nodes`, `13026 edges`, `720
communities`; `Code graph updated`).

**Runtime preflight.** `dentobot-slicerros2` was already `Up 3 hours`. Its
read-only inventory had no matching Slicer/Xvfb/ROS/MoveIt/DentoBot/guard,
inference or trajectory processes, so no verified process was stopped and no
container restart was needed. Frozen input hashes remain inspection MRB
`8ded0a8237aa220ff51cb4ea733ff950fad459f5b9ae9e883e3222b1c9a9aa47`,
`rejected_state.json`
`b185dc8caf3153c524df368c70cbf5395eada198e22d40e1763f5f29bb15a7f1`, and
`state_identity.json`
`05f1f2328a066b1b48878519bae299e7fce69e08658761cb714f848f5a9a9d20`.
The separate `display-only-recapture-20260915-endpoint-only-repair3/`
directory was absent before execution.

**Exact invocation recorded before execution:**

`timeout 180s docker exec dentobot-slicerros2 bash -lc 'set -euo pipefail; export DENTOBOT_C1_RECAPTURE_ENDPOINT_ONLY=true DENTOBOT_C1_RECAPTURE_SOURCE_ROOT=/workspace/data/Slicer_Saved/SampleStudy1/FDI31 DENTOBOT_C1_RECAPTURE_INSPECTION_MRB=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/inspection-scene/fdi31-p2-rejected-state.mrb DENTOBOT_C1_RECAPTURE_REJECTED_STATE=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/rejected_state.json DENTOBOT_C1_RECAPTURE_STATE_IDENTITY=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/state_identity.json DENTOBOT_C1_RECAPTURE_OUTPUT=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only-repair3 DENTOBOT_C1_RECAPTURE_MANIFEST=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only-repair3/endpoint-review.json; timeout 150s xvfb-run -a /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer --no-splash --additional-module-paths /workspace/ros2_ws/src/DentoBot/DENTOWorkflow --python-script /workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_c1_display_only_recapture.py'`

The endpoint pre-save and post-reopen gates remain fail-closed. The transition
image remains explicitly `NOT_RUN`; no new transition FK may be obtained.

## AF. Endpoint-only parity repair3 result and repair4 preflight, 2026-09-15

The first attempt under the revised authorization loaded the retained MRB but
stopped before the target preparation gate. The unchanged native helper failed
closed with `Reconstruct the opened Case Foundation CBCT displays.` The saved
jaw transform was present, but the inspection MRB did not serialize the two
transient Case Foundation display volumes required by the helper's freshness
contract. The separate repair3 manifest is
`display-only-recapture-20260915-endpoint-only-repair3/endpoint-review.json`,
325 bytes, SHA-256
`9af0d39f8e94363d81192df25e93040d41084120145c1221ea18a335fd23643d`.
No review MRB, PNG, geometry parity or FK comparison was written. The
container remained available and the post-run matching process inventory was
empty; no operator-owned process was touched.

**Correction applied for the next attempt.** The driver now restores only the
missing transient fixed-upper and moving-lower Case Foundation display volumes
in the isolated loaded review scene using the existing
`rebuildCaseFoundationDisplayVolumes` helper. It then verifies the saved
preparation record fingerprint against the retained native jaw fingerprint and
calls the unchanged `_step6CaseJawPolydataWorld` path once, followed by the
native triangle filter. This does not modify the source segmentation, source
parents, target/template/tool geometry, native collision payload, policy or
tolerances. The focused source suite is `20/20`; compilation passed and
Graphify refreshed successfully (`8301 nodes`, `13048 edges`, `720
communities`; `Code graph updated`). Host and container hashes match: driver
`4668e5b3207c5dfa92947529fad329efcf6e498d707a03d47febd93eb69cf9ed`, tests
`6a32b4ee3c4245b5afc78dbedc27db8176c3e635802dbc63d2b3b278091c127e`.

The existing container was checked again and no matching Slicer/Xvfb/ROS/
MoveIt/DentoBot/guard/inference/trajectory process was running. The repair4
output location was absent. Frozen hashes remain unchanged.

**Exact repair4 invocation recorded before execution:**

`timeout 180s docker exec dentobot-slicerros2 bash -lc 'set -euo pipefail; export DENTOBOT_C1_RECAPTURE_ENDPOINT_ONLY=true DENTOBOT_C1_RECAPTURE_SOURCE_ROOT=/workspace/data/Slicer_Saved/SampleStudy1/FDI31 DENTOBOT_C1_RECAPTURE_INSPECTION_MRB=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/inspection-scene/fdi31-p2-rejected-state.mrb DENTOBOT_C1_RECAPTURE_REJECTED_STATE=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/rejected_state.json DENTOBOT_C1_RECAPTURE_STATE_IDENTITY=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/state_identity.json DENTOBOT_C1_RECAPTURE_OUTPUT=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only-repair4 DENTOBOT_C1_RECAPTURE_MANIFEST=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only-repair4/endpoint-review.json; timeout 150s xvfb-run -a /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer --no-splash --additional-module-paths /workspace/ros2_ws/src/DentoBot/DENTOWorkflow --python-script /workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_c1_display_only_recapture.py'`

Repair4 remains endpoint-only; the transition image is `NOT_RUN` and no new
native FK is requested. The pre-save and post-reopen gates remain fail-closed.

## AG. Endpoint-only parity repair4 result and repair5 preflight, 2026-09-15

Repair4 reached the endpoint save/reopen gate. The output manifest is
`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only-repair4/endpoint-review.json`, SHA-256 `4a87c8a7acc08d90c915c51f605e60b8b8d37e957de6314e760554be3f473047`.
The separate review MRB was written at
`.../display-only-recapture-20260915-endpoint-only-repair4/01-static-endpoint.mrb`.
No PNG was written because post-reopen parity failed closed before capture.

Before save, the corrected display copy passed the retained native checks:
prepared FDI31 fingerprint and bounds matched exactly (0.0 mm maximum error),
the saved jaw-preparation fingerprint matched and application count was one,
the robot-profile identity matched, all seven displayed link/mesh transforms
matched, and derived spindle, burr and meshless TCP matched retained endpoint
FK (0.0 degree rotation error; TCP translation error about 0.000014754 mm).
The Case Foundation display volumes were restored only in the isolated review
scene through the existing offline helper.

After reopen, the template/target geometry still matched, but the workflow
rehydrated the transient robot links from the retained parameter-node joint
fields rather than the endpoint vector supplied to the driver. Link 1 stayed
aligned; link 2 onward, spindle, burr and derived TCP did not. The manifest
records representative post-reopen errors of 6.353682 degrees/16.625380 mm
at link 2 and 61.120779 degrees/91.065227 mm at the spindle. Therefore no
image is accepted from repair4 and endpoint review remains `BLOCKED`; this is
a save/reopen pose-persistence defect, not a geometry or native-FK mismatch.
The repair4 MRB and manifest remain preserved as historical evidence.

**Minimal source correction for the remaining authorized attempt.** The
review driver now writes the exact retained J1-J5 endpoint vector into the
existing workflow parameter-node display fields using the workflow's own
degrees/mm convention before saving the separate review scene, keeps visual J6
at canonical zero, reapplies the same offline FK once, and records those
review-only parameter values. Production transient-node policy, source MRB,
anatomy, template/tool geometry, collision semantics and native interfaces are
unchanged. Focused tests pass `22/22`; compilation without bytecode writes
passes. Graphify refreshed successfully (`8307 nodes`, `13064 edges`, `719
communities`; `Code graph updated`). Host and mounted-container hashes match:
driver `b47e47983a87c76e4083846c98b38adc3b71c47f8b8a948bce32f1f1852950c2`,
tests `edac74fc61a644c4caee52c11b2a148bcbbed7b02fecbaf8b24777526a1ccbbd`.

The existing container was refreshed read-only before the next attempt:
`dentobot-slicerros2` was `Up 4 hours`, no matching Slicer/Xvfb/ROS/MoveIt/
DentoBot/guard/inference/trajectory process was present, and no process was
stopped or restarted. The repair5 output location was absent. Frozen input
hashes remain unchanged.

**Exact repair5 invocation recorded before execution:**

`timeout 180s docker exec dentobot-slicerros2 bash -lc 'set -euo pipefail; export DENTOBOT_C1_RECAPTURE_ENDPOINT_ONLY=true DENTOBOT_C1_RECAPTURE_SOURCE_ROOT=/workspace/data/Slicer_Saved/SampleStudy1/FDI31 DENTOBOT_C1_RECAPTURE_INSPECTION_MRB=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/inspection-scene/fdi31-p2-rejected-state.mrb DENTOBOT_C1_RECAPTURE_REJECTED_STATE=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/rejected_state.json DENTOBOT_C1_RECAPTURE_STATE_IDENTITY=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/state_identity.json DENTOBOT_C1_RECAPTURE_OUTPUT=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only-repair5 DENTOBOT_C1_RECAPTURE_MANIFEST=/workspace/data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only-repair5/endpoint-review.json; timeout 150s xvfb-run -a /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer --no-splash --additional-module-paths /workspace/ros2_ws/src/DentoBot/DENTOWorkflow --python-script /workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_c1_display_only_recapture.py'`

Repair5 remains endpoint-only and is the final targeted attempt under this
authorization. The transition image remains explicitly `NOT_RUN`; no new
native FK may be obtained. The endpoint gate remains fail-closed: a failure
of any saved geometry, native FK, or save/reopen comparison stops capture with
no tolerance changes or blind retry.

## AH. Endpoint-only parity repair5 result, 2026-09-15

Repair5 completed the authorized final endpoint-only offline display session.
The canonical packet is
`data/Slicer_Saved/SampleStudy1/FDI31/planner-recovery/c1/c1-p1p2-recheck-20260914-r6/corrected-p2/burr-alias-recheck-corrected/display-only-recapture-20260915-endpoint-only-repair5/endpoint-review.json`,
SHA-256
`d02ee16dbedd6c193670c4e99f7f26f7070393e9b4d644f05b1beefd1dca5fcf`.
Its separate rotatable inspection scene is
`.../display-only-recapture-20260915-endpoint-only-repair5/01-static-endpoint.mrb`,
SHA-256
`04a5f62a455205d83820d7dfab7b9923ef6914d2f78124e71c35f65524c5fcdb`.
The endpoint result is `PASS` for the machine parity gate; the overall review
and operator acceptance remain open.

**Endpoint numerical evidence:**

- The final printable template fingerprint and bounds matched the retained
  native record exactly; maximum bounds error was `0.0 mm` against `0.05 mm`.
- The prepared FDI31 target source and prepared fingerprints matched the
  retained native records exactly; source and prepared bounds errors were
  `0.0 mm`. The saved Case Foundation preparation fingerprint matched
  `9b5664b66fd730cfe6180245e43f4ab31412ce7405f1f29989acd6ed55b75fcb`, and
  the recorded jaw-transform application count was exactly one.
- The loaded robot-description identity matched the retained native identity
  `a0a802c0969546585aa5198d9c31bfb281d969235baa2eaa857718a2f8f146aa`.
  Displayed link/mesh and model/link transforms all matched after reopen.
- The actual displayed spindle mesh, with its visual-origin offset removed,
  produced the canonical meshless `dentobot_drill_tcp` through the existing
  URDF/FK fixed relation. Native endpoint FK comparison matched for burr and
  spindle at about `1.07e-13 mm` and `1.18e-13 mm` translation error, and for
  TCP at `0.000014754 mm`; all rotation errors were `0.0 degrees` against
  the `0.5 degree` tolerance.
- Save/reopen persistence passed: seven robot models, seven link transforms,
  review-pose attributes and world transforms were restored without moving
  the displayed endpoint. The review parameter-node values recorded for
  rehydration were J1 `6.3536824311 deg`, J2 `58.6474968170 mm`, J3
  `-33.6432792161 deg`, J4 `66.8260306861 mm`, J5 `49.3346753787 deg`, and
  canonical visual J6 `0.0 deg`.

The two endpoint images are preserved separately: context
`.../01-static-endpoint-context.png` (SHA-256
`89871ad31287c2d8b8e43726507f99c65b45c4fd668cbaaaecbffa2e154eb211`) and
close-up
`.../01-static-endpoint-closeup.png` (SHA-256
`2bab8ec2fd8f2d7956ce4292b213ebe1c6c310ced43dc244161dde69871224fc`). Both
passed the nonblank capture check and carry the phase-aware static rejection,
native `final template ↔ spindle` pair, and explicit unknown contact fields.
They are display-only evidence; raster label overlap and small target scale in
the context view still require ordinary operator visual review and are not
converted into acceptance by the machine PASS.

The transition sub-result remains `NOT_RUN`: saved native FK for rejected
sample 1/134 is unavailable, so no new transition FK or image was obtained.
The retained transition joint vector, starting state, requested endpoint and
interpolation fraction remain preserved in the packet. Runtime boundary flags
remain false for ROS, MoveIt, native diagnostics, planning, controller,
spindle activation and trajectory execution. The container remained `Up`; the
post-run matching process inventory was empty, and no operator-owned process
was stopped. No source MRB, frozen input, anatomy, template/tool geometry,
collision policy or native interface was changed.

This closes the authorized source/display repair attempt only. It does not
change Campaign-1 status: P1 saved-input/machine checks remain `PASS`, P1
overall scene correctness/operator review remains `INCOMPLETE`, the retained
native P2 packet remains the evidence source with its existing status, and
operator acceptance remains `NOT_RECORDED`. P3/P4 and all later, hardware,
full-flow, repeat/playback and patient-facing actions remain unauthorized.

## AI. Operator endpoint-image review and next-prompt request, 2026-09-15

The operator reports that the repair5 screenshots are now understandable and
acceptable to proceed, and requests the next Luna prompt. Record this as
acceptance of the corrected endpoint visual evidence only, not blanket
acceptance of all 15 automatic inputs, collision-free endpoint validity, or
clinical/physical fit. The repair5 manifest hash was independently read back
as `d02ee16dbedd6c193670c4e99f7f26f7070393e9b4d644f05b1beefd1dca5fcf`;
pre-save/post-reopen gates and the saved-pose checks report PASS. Both retained
images were inspected. No application/runtime check was repeated.

The next proposed handoff is one retained-evidence P1/P2 closeout followed by
conditional P3 under the existing Campaign-1 128-solve contract. Missing
historical Home-transition imagery is deferred, not a prerequisite for static
Target feasibility; no insertion/onset claim follows. Resolve decision-critical
scene/selection gaps before P3; present only genuinely unresolved operator
choices. P1 overall remains incomplete until that reconciliation. This request
does not execute P3 or authorize P4; the returned prompt supplies the bounded
P3 authorization for the operator to send to Luna. No source changes were made.

## AJ. Retained-evidence P1/P2 closeout gate after endpoint-image approval, 2026-09-15

The operator's approval is recorded with the following limited scope: the
repair5 endpoint screenshots are understandable visual evidence of the
retained static endpoint. This does not accept all fifteen automatic input
selections, clinical or physical fit, collision-free motion, full-workflow
correctness, or any P3/P4 result. The machine manifest remains
`operator_acceptance=NOT_RECORDED` and
`operator_confirmed_in_this_run=false`; those fields are not changed by this
review record.

**Retained evidence reconciliation:**

- The repair5 endpoint packet and MRB are the authoritative display-review
  evidence. Endpoint geometry identity, displayed seven-link/model transforms,
  derived meshless TCP, burr/spindle FK parity, and save/reopen pose persistence
  are `PASS` within their recorded tolerances.
- The retained native P2 result is now described precisely as three separate
  evidence classes: (1) phase-aware static rejection of both retained endpoint
  candidates for the final printable template ↔ spindle pair; (2) generic
  static contacts, including FDI31 tooth ↔ spindle and tooth ↔ burr; and (3)
  Home-to-requested-endpoint corridor rejection at transition sample `1/134`.
  The third result is not a Target static verdict and is not the original r13
  insertion edge or collision-onset evidence.
- The native scene acknowledgement is trusted only for the later correlated
  request that matched all expected object IDs, poses/bounds and the policy
  fingerprint (`31/31`). The earlier P1 audit with a null/zero-object
  acknowledgement remains historical evidence of the readback gap and is not
  silently rewritten.
- Row 13's “finalized template shell” is resolved as a bookkeeping alias to
  the retained final printable template/STL in row 12; the P1 audit contains no
  independently materialized finalized-shell object. Row 15's P1 null collision
  payload is retained as the audit-history value; the later correlated native
  31-object payload is the authoritative P2 collision-scene value. Neither
  resolution changes geometry, policy or the operator-review requirement.
- The historical transition image remains `NOT_RUN`: evaluated sample FK
  matrices were not retained. The saved transition joint vector, start state,
  requested endpoint, sample index and interpolation fraction remain preserved;
  no endpoint FK was substituted for transition FK.

**Gate verdict:**

- P1 saved-input and machine checks: `PASS` for the checks actually completed.
- P1 overall scene/input correctness and operator review: `INCOMPLETE`. The
  endpoint image review is recorded, but the intent of the decision-critical
  automatic inputs below has not been explicitly confirmed or corrected.
- P2 bounded static diagnostic evidence: `PASS` with campaign gate
  `USER_REVIEW_REQUIRED`. Contact point, penetration depth and clearance stay
  `UNKNOWN` wherever the native packet did not provide them.
- P3 conditional authorization is not entered yet. Campaign 1 requires the
  P1 technical reconciliation plus recorded operator review before the bounded
  P3 batch. No P3 source edit, runtime, native planning or P4 action occurred.

**Only remaining operator questions:**

1. **Frozen case and task inputs (rows 1–6 and 10):** Should the review and
   any later conditional P3 use exactly the immutable source
   `dentobot-case-13sept.dentocase`, diagnostic package
   `packet-a-fdi31-20260914-r7/FDI31-step5c.dentocase`, Case Foundation Manual
   Simulation Base/planning pose, FDI31 target segment
   `2.25.127809691704402484963988182477922906518`, saved Entry
   `[-95.5797808828, -68.3080212751, 32.5242792904]`, saved Target
   `[-95.0791174633, -74.1254665588, 29.2961247214]`, the `6.6719049312 mm`
   Entry→Target line, the assisted-entry point equal to saved Entry, and the
   saved Entry→Target insertion direction? Reply “yes” or identify the item
   to replace; this asks for intended inputs, not a technical certification.
2. **Scene and workflow objects (rows 7–9, 11–12 and 14):** Should the review
   use exactly the recorded current/locked draft support, visible five-tooth
   support `[FDI31, FDI42, FDI41, FDI33, FDI32]`, four independent occlusal
   tangent robot docks, current patient-contact shell, final printable
   template/STL, and restored Step-6 `PlanningPackage` state on branch
   `guide-5c0da27697aceceb8f14` with `ProvisionalLocked` base and
   `never-auto-connect` restore policy? The four through-open dock bores are
   recorded as robot-dock bores; the retained evidence does not identify a
   separate drilling-trajectory guide bore. Reply “yes” or identify any object
   or bore-role correction; this asks for intended object identity, not a
   certification of the measured mesh facts.

After those two answers, the coordinator can record the P1 review gate and
apply the already-scoped conditional P3 contract if the answers preserve all
frozen invariants. Until then, the campaign remains paused at the P1/P2 review
gate. P4, P5–P7, full-flow/repeat/playback, controller, spindle, motion and
patient-facing actions remain excluded.

## AK. Operator 4A–5B observations and source-only correction, 2026-09-15

The operator supplied five screenshots from a current Slicer session after
opening the immutable `dentobot-case-13sept.dentocase`. Preserved copies, in
workflow order, are under
`/home/light-tarun/dentobot/data/dentobot-runs/fdi31-operator-steps4a-5b-20260915/`:
`73efe180` (4B), `e68d29fa` (4C), `215b1b37` (5A before reset),
`3d2194f8` (5A after reset), and `db3dc88d` (5B). These are operator
observations, not numerical proof of the live MRML state or acceptance.

| Step | Operator observation / decision | Saved-data and source finding | Remaining evidence boundary |
|---|---|---|---|
| 4A | FDI31 appears preselected and twice, including an original closed-mouth pose; operator does not recall saving this and says it does not block downstream navigation. | The immutable source bundle is `PartialOrInspectable` and **does** retain FDI31 target segment `2.25.127809691704402484963988182477922906518` plus target-bounds ROI; its trajectory line has zero control points and no 4C/5A plane. The source and r7 have the same eligible Foundation planning-pose fingerprint `2f6006ce...`. Case Foundation separates closed-source anatomy from opened derived displays; current source code hides all closed-source segments in 3D while the opened view is current. | The screenshot cannot prove a duplicate binary target mask, nor whether the live closed-source display suppression ran. Do not edit the source package or classify this as a geometry change from appearance alone. |
| 4B | Operator confirms two adjacent teeth each side of target: FDI42, FDI41, FDI33, FDI32, with FDI31 fixed. | These are the four selected support IDs visible in the screenshot and the r7 five-tooth draft/visible-support context. | This is review of support membership only, not acceptance of the whole support surface, anatomy or template fit. `W4B-P2-SUPPORT-AUTO` remains the separate priority-2 auto-suggestion UX owner. |
| 4C | Operator requests the pictured **new-case** defaults: radius 10.0, outer 3.0, robot-dock bore 1.0, connector width 3.5, overlap 2.0, shared depth 5.0, clearance 0.5 mm, yaw 35°. The displayed plane looks abnormally oblique. | Schema/UI were split: schema bore 1.5 vs UI 1.0, UI radius 15 vs schema 10. Both now match the requested new-case values. The frozen r7 assembly remains a distinct saved 1.5-mm robot-dock-bore geometry. Its target-crown frame has world-RAS normal `[0.1012292145,-0.8878394799,-0.4488805008]`, 155 crown-cap points and `2.6638967929°` tilt from its mean trajectory. The constructor uses the Case Foundation opened-world target surface, not raw closed CBCT geometry. The pictured 35° yaw is labelled a draft obstacle screen, not final confirmation. | The current unsaved screenshot does not numerically establish its plane origin/normal or transform application. No r7 regeneration, dock move, yaw confirmation or P3 substitution follows from new defaults. |
| 5A | Operator requests 4.0-mm plane-depth default, other values unchanged; first plane looked like 4C, then Create/Reset appeared better. | Schema/UI defaults were 3.0 and now are 4.0 for new cases only; immutable source persists 3.0 and frozen r7 persists 4.0. Reset recomputes the Step-5A plane from active Entry→Target and five selected opened-world crown caps; it does not reuse the target-only 4C frame. R7 Step-5A world point `[-95.27961868,-71.795748,30.588907248]` is Entry plus 4 mm along insertion, and its five-tooth normal `[0.0495809556,-0.7491243684,-0.6605712752]` is `12.4409255812°` from the insertion direction (934 cap points). The pictured visible-support preview changed from 1584 points/2727 cells before reset to 1898 points/3326 cells after, so some downstream display mesh was regenerated. | Different camera views and preview counts do not identify the plane's own pre/post world origin or normal. With no pre-reset saved MRML state, the exact reason for the earlier plane appearance cannot be proved; current after-reset geometry needs numeric readback. |
| 5B | Wrong-looking plane, grey parameter fields and build error for a 1.5-mm drilling-trajectory bore against the 2.0-mm floor. | The immutable source stores **both** `templateSleeveInnerDiameterMm=1.5` and research `templateChannelDiameterMm=1.5`; persisted old values override new-case 2.0-mm defaults. The pictured 1.0-mm 4C robot-dock bore parameter is a different object/role. The pictured grey undercut fields are generated outputs; source does not disable the editable guide-hole spinbox in section `2 · Unified template dimensions` above the screenshot. The old final-control status discarded its existing normalization error and could say “Inputs are ready”; its build preflight could enter cached work before the shared `normalize_docking_parameters` rejected the hole. Both status and preflight now use the same early dimension predicate and point to section 2. | No saved parameter was silently clamped or changed; the 2.0-mm guide-hole floor and collision policy remain unchanged. An explicitly revised **new** case would need dependent geometry regenerated/reviewed, not substituted into frozen r7/P3. Actual live widget clamping/lock behaviour is not proven by source inspection alone. |

Continued source trace found no Step-5A reference/alias to the Step-4C plane:
the support plane is independently recomputed from five opened-world crowns.
In retained r7, the two world-plane centres are `3.8367227631 mm` apart and
their normals differ `14.8413472362°`; such large, nearby planes can look
overlaid from a wide oblique camera without being numerically identical. This
is an explanation of retained geometry, not a verdict on the operator's live
screen. One remaining programmatic Step-5A plane-method default was 3.0 mm
(all current production callers passed depth explicitly); it is now 4.0 mm
for new callers, with its docstring corrected to say crown-cap tilted rather
than exactly normal to Entry→Target. The added focused assertion first failed
against old source, then `Testing/test_step6_planning.py` again passed `24/24`.
No saved plane or case was rebuilt.

Read-only MRML display inspection clarifies 4A: the source bundle contains
three segmentation nodes, `Post_surgery_seg`, `[Case Foundation] Fixed Upper
Jaw + Teeth`, and `[Case Foundation] Moving Lower Jaw + Teeth`. FDI31's same
segment ID is represented in the closed source and opened moving-lower
segmentation; this is the planned anatomy/display proxy, not a second target
selection. At save, the closed source display was aggregate-visible in 3D
while both derived displays were aggregate-hidden. The current workflow's
`_enforceStep6OpenedJawDisplaySeparation` should hide every closed-source
segment before enabling the opened derived views. If both displays become
visible, the same target appears twice at two poses. The current screenshot
does not expose which visibility toggle/callback left both enabled, so no
source display-path edit or geometry correction is claimed without live MRML
readback.

Focused regression first failed as expected (`2 failed`) against the old
defaults/preflight, then the focused planning file passed `24/24`. Changed
Python files compiled with a `/tmp` pycache prefix; the first compilation
attempt failed only because the checkout `__pycache__` path was unwritable.
`git diff --check` passed. No Slicer/ROS/MoveIt/native diagnostic, planner,
container or hardware run occurred, and no operator-owned GUI session was
changed. The source correction changes only newly initialized defaults and
Step-5B diagnostic gating; it does not change frozen r7 parameters/geometry,
the immutable source, anatomy, transforms, tool/TCP, tolerances or collision
policy.

**Updated gate:** P1 prior saved-input/machine checks remain PASS for checks
actually completed; 4B support-ID intent is specifically confirmed, but P1
overall scene/input correctness and operator review remain INCOMPLETE because
the current 4A duplicate-display and 4C/5A plane state are not numerically
reconciled. Retained P2 phase-aware static evidence remains PASS with
USER_REVIEW_REQUIRED, not a new P2 run or full-workflow acceptance. Section AJ's
two grouped “yes” questions are superseded by the operator's concrete 4B
confirmation and 4C/5A/5B concerns; they must not be treated as answered
wholesale. P3/P4 are not entered. The precise missing prerequisite for a live
4C/5A geometry verdict is a separate saved current MRB/`.dentocase` with
world-frame plane/dock/trajectory and display state, not another native run.
The operator subsequently supplied that separate Step-5B MRB; its readback
supersedes this missing-evidence statement in Section AM below.

## AL. Separate 15Sept test-case readback, 2026-09-15

**Operator statement:** They deleted the perceived FDI31 artifact and saved
`data/Slicer_Saved/SampleStudy1/dentobot-case-15sept.dentocase` as a new test
case. This statement is not acceptance of the saved scene or Campaign-1 inputs.
The case SHA-256 is
`d084f0ce733f35bc73eaccf805113a267dbf3ea7b295315c4b5da3fb67136d6a`
(80,353,638 bytes). ZIP integrity passed; all six file entries in its outer
manifest matched their declared size and SHA-256. The archive was not edited.

| Read-only comparison against immutable 13Sept source | 15Sept result / boundary |
|---|---|
| Anatomy and world setup | `Post_surgery_seg.seg.nrrd` and every saved fixed/moving derived segment file are byte-identical; jaw-opening and base matrices, source-segmentation and planning-pose fingerprints also match. The opened-lower planning-surface `.vtk` member has a different byte hash and was not geometrically compared, so total scene-geometry identity and live-renderer correctness are not claimed. |
| Step-4A saved state | FDI31 slot 1 in the active trajectory registry is `Empty`, with no registry target ID, and the earlier empty trajectory-line MRB member is gone. An assisted-entries fiducial member was added. However MRML `targetToothSegmentId` still equals `2.25.127809691704402484963988182477922906518`, and the matching target-bounds ROI is retained (its saved control point moved from `[-94.8082,-39.5806,47.0925]` to `[-95.6076,-76.0151,28.5729]` world-RAS mm). `_updatePlanning` selects the Step-4A combo from that MRML field, so target preselection can persist even with an empty registry. The exact object the operator deleted is not inferable from the package diff alone. |
| Display duplication | The source `Post_surgery_seg` and opened `[Case Foundation] Moving Lower Jaw + Teeth` each save FDI31 with `Visible=true`, `Visible3D=true` and aggregate display visibility true. Thus the saved 3D scene can still show closed/opened FDI31 simultaneously. Subject Hierarchy items rose from 170 to 366, and segmentation virtual branches from 4 to 10; FDI31 virtual refs rose from 3 to 7, alongside repeated refs for other segments. These are repeated hierarchy/display records, **not** evidence of a second binary FDI31 mask. The intended opened-view/save enforcement is not reflected in this MRB; the save-time callback/branch cause is unproven without its trace. |
| Workflow readiness | `PartialOrInspectable`, Foundation pose `VALID`, base `BASE_UNLOCKED`, zero PreparedBranches. The saved support-ID list contains FDI42/41/32, not the separately operator-confirmed four-tooth 4B scene. No saved 4C docks, 5A support plane, final template or prepared branch exists here, so this bundle cannot provide the missing current 4C/5A plane readback or be substituted into P3. |
| Persisted dimensions | Radius 15.0 mm, robot-dock bore 1.0 mm, 5A depth 3.0 mm, trajectory-guide hole 1.5 mm and research channel 1.5 mm remain as saved values. New-case source defaults do not rewrite them. No geometry, parameter or collision-policy correction was applied to this file. |

**Disposition, clarified by the operator:** 15Sept is intended as a reusable
mouth-opened + robot-base-placed foundation, not a Step-5B scene. Its saved
opening/landmarks/base matrix can avoid repeating those placements, but its
base is still `BASE_UNLOCKED` and the saved Step-4A target/ROI, three supports
and two-layer FDI31 3D visibility mean it is not clean `FoundationOnly` input.
Do not delete the authoritative FDI31 segmentation to remove a display copy,
silently lock the base or overwrite the case. The separate Step-5B MRB in AM
supplies current plane evidence. P1 overall remains `INCOMPLETE`; retained P2
native evidence remains `PASS` with `USER_REVIEW_REQUIRED`; Campaign-1 frozen
source/r7 and historical attempts remain unchanged. No Slicer/ROS/native/
planning runtime, P3/P4 or hardware action was performed for this readback.

## AM. Saved Step-5B world-scene audit and source-only plane repair, 2026-09-15

**Operator statement:** `data/Slicer_Saved/SampleStudy1/FDI31/2026-09-15-Scene.mrb`
is the expected Step-5B saved scene, separate from the intended reusable 15Sept
foundation case. Its SHA-256 is
`43bbeeacd6ecb738aa116b0076797f67f361acc2de1cccb0434e53f5c2adca9c`;
`unzip -t` exited 0. The MRB's authoritative source segmentation bytes and
its saved TMJ opening/base matrices match the 15Sept bundle exactly. Neither
saved file was opened or rewritten in Slicer during this audit.

| Saved MRB readback | Evidence and interpretation |
|---|---|
| Workflow/data | FDI31 Entry→Target trajectory and Step-4B draft are present. The draft records support FDI42/41/33/32, matching the operator's separate 4B confirmation. Four independent 4C robot docks and both 4C/5A planes are present. The current 5B patient-contact shell is saved, but `finalPrintableTemplateModel` is absent. |
| Display | Closed-source FDI31 saves `Visible3D=false`; opened moving-lower FDI31 saves `Visible3D=true`, with both aggregate displays enabled. Thus the Step-5B MRB does **not** serialize the same two-layer FDI31 3D visibility seen in the 15Sept foundation bundle. This is saved MRML readback, not live image acceptance. |
| Dimensions | Radius `10.0 mm`, 4C robot-dock bore `1.0 mm`, 5A depth `4.0 mm`; Step-5B drilling-trajectory guide hole and research channel both remain `1.5 mm` against the unchanged `2.0 mm` builder floor. The four dock bores and one guide hole remain separate roles. No parameter was clamped or changed. |
| 4C plane/dock distinction | Saved docking `FrameJson` normal `[0.1062008629,-0.8351349009,-0.5396953530]` world-RAS; the MRML plane handle world-normal column matches within serialization rounding. Its target-crown fit is `1.666813577°` from the Entry→Target axis. The plane's displayed in-plane X/Y handles are each `14.736°` from the docking-frame X/Y; a point-normal plane does not by itself certify the four-dock model's yaw/fit. This is normal/point parity only, not full docking-frame or clinical acceptance. |
| 5A frame | `CrownCapTiltMetricsJson` records fit normal `[0.0462882197,-0.7354511789,-0.6759947959]` and `11.432482206°` fit tilt from the Entry→Target axis. The saved MRML plane's actual world normal is `[0.064557,-0.997913,-0.00134685]`: `42.454376°` from that fit normal and `31.289385°` from the trajectory axis. Applying the saved jaw-opening rotation to the fit normal reproduces the actual normal within `4.7e-7` component error. This is a real saved plane-orientation/frame mismatch, not merely a camera-angle claim. |
| 5A point | Actual world origin `[-95.5081,-71.6786,31.1928]` mm agrees with saved Entry plus `4.0 mm` along insertion within `0.000044 mm`; the defect is orientation, not depth/point placement. The 4C and 5A origins are `3.364800 mm` apart and actual normals differ `32.756783°`. The earlier pre-reset plane was not saved; its exact prior state remains unknown. |

**Source finding and bounded correction:**
`createOrUpdateTemplateSupportBoundaryPlane` computes the five-tooth normal in
opened world-RAS and calls Slicer's `SetNormalWorld`. Subsequently,
`refreshCaseFoundationNodeOwnership` can call the shared
`_reparentCaseFoundationNodePreservingWorld` helper for a new plane. The helper
already preserved each markup's world control-point position, but not a
plane's world normal; reparenting could rotate that normal with the TMJ jaw.
The saved MRB does not retain the exact callback sequence that produced its
5A normal; attribution to this helper is a high-confidence inference from
the exact jaw-rotation match and independently reproduced helper defect.
The same helper is shared by Step-4C/Step-5A and other jaw-owned nodes. It now
snapshots a plane markup's `GetNormalWorld` before reparent and restores it
with `SetNormalWorld` afterward. No new interface, policy, transform, anatomy,
tool, case or saved geometry was introduced or modified. This is a future
creation/reattachment source correction, **not** a retroactive repair of the
saved 5A MRB.

Focused local AST/stub regression against old source failed as expected on
world-normal preservation (`1 failed`, 24 deselected); after the six-line
repair it passed (`1 passed`), and complete
`Testing/test_step6_planning.py` passed `25/25`. Changed Python compiled with
a `/tmp` pycache prefix, `git diff --check` passed, and the overlay-only
Graphify graph refreshed successfully. These are source/pure/static checks;
Slicer API behavior, save/reopen parity of a newly reconstructed 5A plane,
the historical MRB's fit and operator scene review remain unverified.

**Gate:** P1 prior saved-input checks PASS only for completed checks, but P1
overall scene/input correctness remains INCOMPLETE. Retained P2 native static/
transition packet stays PASS with USER_REVIEW_REQUIRED. The reusable 15Sept
foundation is not yet clean/eligible, and the saved 5A plane is not accepted
geometry. No P3/P4, planning, Slicer/ROS/native/container, controller,
spindle, motion or patient-facing action occurred in this audit/repair.
