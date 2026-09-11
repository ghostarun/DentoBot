# DENTOBOT Tasks

Last reconciled: 2026-09-11

## Current work order

This is the only active queue. Priority assignments are retained; a dependency
does not acquire a new priority. Historical attempts are in dated logbooks.
AGENTS.md and AGENTIC_VERIFICATION_PROTOCOL.md own process/model/check rules;
completed `AGENT-PLAN-FIRST`, `AGENT-SOL-RESTORE` and
`AGENT-VERIFY-ECONOMY` changes remain recorded in the 2026-09-09 logbook.

| Order | Existing task | Disposition |
|---:|---|---|
| 1 | `W5-U-04` (P0) | Static and synthetic checks plus FDI11 saved-case fusion pass, including clean final-fusion dock screenshots. FDI31 rebuild retains one 5-voxel fragment; its RAS localization indicates a likely central guide/sleeve remnant, pending contributor classification. |
| 2 | `S6-REUSABLE-CASE-SETUP` (P0) | Three-deliverable implementation and focused automated single-target acceptance pass. Normal-window operator review follows the Step 5B bore/connectivity correction. |
| 3 | Same P0, main-workflow integrity gate | Operator reviews one normal-window `4A→4B→4C→5A→5B→5C→6` preparation/import. Do not infer that review from the headless pass. |
| 4 | Same P0, optional testing foundation | Expose prepared-branch selection only in opt-in multi-target testing; keep normal single-target workflow intact. |
| 5 | `S6-LIVE-01..05`, `S6-FDI11-DEPTH` | Resume only after workflow integrity is accepted and within applicable runtime authorization. Stage 3, withdrawal, Home and repeat remain unaccepted. |
| 6 | `S6-WORKSPACE-PURPOSE` | Unprioritized design item; required before Studio Workspace migration. It is not permission to tune clearance now. |
| 7 | `DCP-*`, `DSS-*`, `DHW-*` (P1) | Remain behind Track-A acceptance. Reuse accepted foundation; no automatic Studio/runner/Results/SQLite expansion. |

Platform upgrade `PLAT-U-06`, other backlogs and UI polish retain their own
scope and priority. They do not interrupt this correction merely because their
plans exist. No drilling cycle, ROS/planner/collision algorithm change, commit
or push is authorized by this cleanup.

## Immediate blockers and next task

| Order | Immediate blocker | Blocks |
|---:|---|---|
| 1 | `W5-U-04` passes FDI11, but FDI31 rebuild has one retained 5-voxel component. The approved RAS diagnostic locates it away from every dock bore, suggesting a central guide/sleeve remnant; contributor classification and normal-window bore inspection remain pending. | Step 5B/5C printable-template acceptance and the full PreparedBranch normal-window review. |
| 2 | Explicit-pair and optional 32 × 3 runtime acceptance remain downstream and were not authorized or exercised by this correction. | Promotion of the optional testing workflow only; not the corrected default single-target path. |
| 5 | After workflow integrity, the current FDI11 case still has an unresolved Stage-3 FDI21 contact; axial withdrawal, guarded Home and a fresh repeat remain unaccepted. | Track-A closure and all P1 Case Platform/Studio work. |

**Next task to perform:** after explicit approval, run one narrow FDI31
contributor-classification diagnostic that attributes each retained component to
the shell, guide/sleeve, reinforcement or dock masks. Do not tune a dock branch
from the current location evidence alone. Use the result to select one
evidence-backed construction correction, then rerun the same FDI31 build once.
Require four open bores, one printable occupied volume and no residual channel
voxels before normal-window PreparedBranch review. Stop before Stage 3, robot
motion or Studio work.

## Immediate P0 — bore-safe Step 5B dock attachments

- **ID:** `W5-U-04`; **Priority:** 0 (operator-promoted 2026-09-10);
  **State:** Synthetic and FDI11 runtime verified, including clean
  final-fusion bore-axis screenshots. FDI31 reconstruction retains a 5-voxel
  fragment. Its approved RAS localization is away from every dock bore and
  likely central guide/sleeve geometry; source-contributor classification and
  operator review are pending explicit approval.
- **Failure evidence:** Extended 9.6 mm through-bore subtraction preserved the
  bore but split FDI11 into `[60677, 9, 4, 3, 1, 1, 1, 1, 1, 1]` occupied
  regions. The corrected FDI11 rebuild now has one region `[62258]`, zero
  residual channel occupancy and open-bore visual evidence. A fresh FDI31
  rebuild has `[45966, 5, 2, 2, 1, 1, 1, 1]`; its largest remnant is at least
  7.66 mm from any dock-bore axis, so it is not evidence to tune a dock branch
  without contributor classification. The 0.1 mm³ cleanup ceiling and
  one-solid gate remain authoritative.
- **Corrected contract:** Route each cylindrical shell attachment tangent to a
  protected bore radius equal to `bore radius + connector radius + one voxel`.
  Land it on the reinforced outer annulus with at least one voxel of ligament,
  retain configured endpoint overlap, extended final channel subtraction and
  four independent branches. Fail early with Step 4C/5B control guidance when
  the annulus, route or allowed gap cannot support that construction.
- **Diagnostics:** A disconnected final fusion now reports voxel counts,
  approximate extra-region volumes, the cleanup ceiling, the Step 5B
  **Shell + Guides** inspection view and the Step 4C radius/yaw/dimension
  controls to review. It explicitly warns against increasing the artifact
  threshold to hide a mechanical fragment.
- **Boundaries:** No patient shell, trajectory, bore/connector numeric value,
  artifact threshold, collision policy, robot plan or clinical/physical-fit
  acceptance changes. `W5-U-03` retains broader Step 5B/5C acceptance and
  `W4C-U-01` retains future mechanical/rail design.
- **Acceptance:** Focused synthetic geometry proves four bore-tangent branches,
  one-voxel minimum annular/bore clearance, zero protected-channel occupancy,
  four open bore axes, one watertight occupied solid and schema-1 invalidation.
  FDI11 now passes this acceptance. FDI31 must still pass after contributor
  classification and one evidence-backed construction correction, then receive
  normal-window inspection from both bore faces. The bounded automated sequence
  is registered as verification profile `w5u04-bore-safe-template`.

## Step 6 offline restore — existing related backlog

- **ID:** `S6-RESTORE-ROBOT-ROS`; **Priority:** Unprioritized.
- **Observation:** Package load connected ROS before a usable local robot.
- **Current contract:** Offline geometry/configuration hydration, then explicit
  runtime activation. The former automatic checkpoint reconnect sequence is
  superseded, including for schema-1 migration.
- **Disposition:** Audit load/callback ordering under the current P0 correction;
  retain this ID for remaining robot reconstruction acceptance. Fresh and warm
  loads must not auto-connect or duplicate runtime objects. Saved Home is
  configuration, not restored live validation.
- **Evidence:** 2026-09-09 logbook; representative normal-window acceptance pending.

## Step 6.3 workspace purpose and clearance review before Studio — 2026-09-09

- **ID:** `S6-WORKSPACE-PURPOSE`; **Priority:** Unprioritized; **Recommended priority:** 0 for purpose/clearance review and any demonstrated current-workflow defect; **Triage:** Backlog, discussion/design prerequisite for Studio workspace migration. Broader Studio presentation remains P1.
- **Affected workflow:** Step 6.3 Generate Workspace, reviewed exploration limits, retained joint/TCP samples and Home-connectivity evidence; downstream planning seeds and future Studio workspace/study eligibility.
- **Operator observation and request:** The 5 mm clearance leaves no TCP workspace in the intraoral space. Step 6.3 needs updating for the latest developments, and its purpose must be discussed and revamped before the Simulation Studio revamp.
- **Evidence available:** Operator observation; the exact 5 mm parameter, its geometric reference and rejection path have not been inspected or reproduced in this turn. Existing context describes 6.3 as retained static-valid MoveIt-FK TCP/joint samples plus a bounded Home-connectivity classification; reviewed min/max limits are an exploration envelope, not a collision-free box.
- **Risk/impact:** An unsuitable exclusion may discard useful intraoral candidates or present misleading feasibility evidence. Conversely, removing clearance without distinguishing TCP location, complete tool/robot geometry and phase-specific contact could admit invalid states. An empty sampled set is not proof that no task path exists.
- **Discussion deliverable:** Agree whether 6.3 supplies an exploratory reachability display, reusable Home-connected planner seeds, task-specific feasibility evidence, or separately labelled combinations; specify what is mandatory for a single trajectory and what is reusable across the 96-record registry. Separate joint/FK reach, whole-robot static collision validity, Home connectivity and full oriented task-path acceptance.
- **Bounded follow-up:** Locate every consumer of the reported 5 mm setting and determine whether it is an ROI inset, TCP exclusion, tool-envelope allowance or collision policy. Compare it with the current five-DOF canonical TCP, actual tool/guide geometry and phase-specific rules. Propose the smallest justified 6.3 behavior/UI/invalidation change after discussion; no replacement clearance value is selected here.
- **Dependencies:** This purpose/ownership decision precedes Studio Workspace migration and workspace-related shared-environment fingerprints. Current restore readiness and freshly validated Home are prerequisites for live generation checks; existing `S6-LIVE-05` still gates the wider Studio implementation.
- **Next verification action:** First perform a scoped source/settings audit and document the contract. Then, under the prescribed approval, use a reviewed intraoral case to attribute sample rejection to the exact filter, distinguish static-valid/Home-connected/untested samples, and check reconnect/target-change invalidation. Full-task guards remain authoritative; no collision margin, joint limit, anatomy authority or live-validity requirement is relaxed by this note.

## P0 reusable Step 6 setup and PreparedBranches

- **ID:** `S6-REUSABLE-CASE-SETUP`; **Priority:** 0.
- **State:** Operator approved the audited correction and its focused automated
  single-target acceptance passed. The narrow FDI31 recovery now loads the
  package offline without the former environment-mismatch rollback; static and
  exact-package headless checks passed for that boundary. The package's legacy
  Step 5C final-guide schema 1.0 is deliberately stale under current schema 2.0,
  so the planning context is deactivated and transient mouth-open proxy is not
  retained. Duplicate source-dock hiding is implemented for eligible schema-2
  branch restoration, but cannot be accepted against this legacy package until
  the planned rework chooses an inspection-only migration or regeneration path.
- **Main workflow:** One target tooth; one trajectory normally or an explicitly
  paired two for a real two-canal case. Never auto-merge three trajectories.
- **Optional testing:** Separate opt-in workflow over the existing 32-tooth ×
  three-slot registry. T1→A, T2→B, T3→C are independent PreparedBranches;
  T1+T2→AB is allowed only through deliberate pairing. Registry capacity is
  neither template multiplicity nor a main-workflow requirement.
- **PreparedBranch:** Exact trajectory selection and pairing intent, patient
  shell, unified template, dependent guide references and Step 5C verification
  identity. Step 6 selects this complete branch, not a raw trajectory.
- **Switch:** Preserve unchanged jaw opening, landmarks, base matrix/lock,
  Task Home and shared anatomy/environment. Swap the full branch and Step 5C
  evidence atomically. Invalidate branch confirmation/collision acknowledgement,
  plans, previews, guards and diagnostics; never stale shared setup solely
  because selection changed. Real dependency edits still invalidate dependents.
- **Legacy:** Three-trajectory templates remain inspectable but cannot become
  eligible prepared branches. Do not silently split geometry or discard case
  content. Load stays offline; migration writes only on explicit later save.
- **Plan:** [PreparedBranch correction plan](DEVELOPMENT_PLAN.md#s6-reusable-case-setup-correction-plan).
  The 2026-09-10 decision supersedes tooth-owned/per-slot-copy and raw-selector
  interpretations. Existing MRML, registry and .dentocase remain authority.
- **Evidence:** Registry schema/pure tests now cover one canonical branch record,
  selected-branch authority, explicit pairing, scoped staleness and fail-closed
  legacy migration. Static compilation and `git diff --check` pass; host pure
  suite is 85/85, container planning set 67/67 and container restore set 39/39.
  The focused runner invoked only the single-target current workflow, asserted
  eligibility, failed-activation preservation and Step 6 import, and exited 0
  with `DENTOBOT_REUSABLE_CASE_PASS`. Evidence is under
  `/tmp/dentobot-verification/prepared-branch-single-20260910/`.
  The exact failing package is
  `data/Slicer_Saved/SampleStudy1/FDI31/run2-dentobot-case-step6x5.dentocase`.
  Static MRML inspection shows the transformed Step 5C proxy plus a separately
  visible, untransformed `[Step 4C] DENTO Four Independent Robot Docks` model.
  The 2026-09-10 exact headless load reached `_openCaseBundle` successfully with
  `step6SchemaMigrationPending=True`; it then correctly classified the saved
  `DENTOBOT.FinalGuideSchemaVersion=1.0` as stale against required schema 2.0.
- **Next:** Broader mouth-opening relocation/rework must explicitly decide the
  legacy-final policy: a clearly labelled inspection-only proxy versus mandatory
  Step 5C schema-2 regeneration. Then rerun the exact FDI31 load to accept
  hidden source Step 4C docks/plane, transformed proxy, and reset visibility.
  No robot algorithm or downstream scope is authorized by this recovery patch.

## FDI11 / Stage 3 — paused pending workflow integrity

- **ID:** `S6-FDI11-DEPTH`; **Priority:** Unprioritized; related P0
  acceptance stays under `S6-LIVE-01..05`.
- **Latest evidence:** The recorded -4 mm in-memory local-Z trial reaches the
  6 mm Stage-3 endpoint kinematically and records configured housing/template
  warnings, then rejects non-rotating spindle housing contact with adjacent
  FDI21 at the final drilling waypoint. Complete preview, axial withdrawal,
  monitored Home and the fresh repeat cycle have not passed.
- **Case:** The reviewed source package remains unchanged:
  `data/Slicer_Saved/SampleStudy1/FDI11/dentobot-case-step6x4x2.dentocase`.
  Its source trajectory is 7.977207292891484 mm; the recorded simulation cap
  is 6 mm, with no claim that the capped endpoint is pulp.
- **Policy evidence:** Bounded configured housing/guide contact and 0.1 mm
  burr/guide clearance are case-specific recorded authorizations, not defaults.
  Adjacent-anatomy contact remains forbidden. This cleanup does not change
  dimensions, base, depth, margins, guards or endpoint rules.
- **References:** `logbook/2026-09-08.md` hard-constraint checkpoint;
  `logbook/2026-09-09.md` exact-case evidence; retained views/state at
  `data/dentobot-runs/fdi21-blocker-20260909/`. Older fractions and former
  2 mm burr/x4 results remain historical evidence only.
- **Next:** After PreparedBranch/main-workflow integrity acceptance, reconcile
  current reviewed case/tool/guide identity against the retained blocker and
  propose the smallest applicable Stage-3 check. Do not automatically rerun,
  relocate the base or relax collision rules from this entry.

## Assisted access endpoint — 2026-09-07

- **ID:** `S4A-PULP-ENDPOINT`; **Priority:** 0; **State:** Source and focused automated verification passed (2026-09-10); exact FDI31 normal-window anatomical review remains pending.
- **Operator observation:** The displayed FDI31 assisted target appears inside the pulp mask in 2D but does not contact the displayed pulp surface in 3D. The operator requires the mismatch fixed now, not deferred.
- **Exact-case finding:** The 4.23 mm line in `FDI31-step5c.mrb` belongs to a saved three-line set and has no current assisted-generation provenance; the Placement menu describes the creation action, not an existing line's origin. Slice projection also rendered off-slice Entry/Target glyphs over the mask. The saved Target is at the native voxel boundary, while the smoothed closed surface can diverge from that boundary.
- **Corrected contract:** New single/dual assisted generation must prove a shared interval between the selected tooth's FDI-matched binary pulp mask and its displayed 3D surface, preserve Entry and direction, and atomically set Target to the first point contained by both (the farther entry boundary). Record both boundary points and their offset. Reject a native/display miss or non-overlap. Off-slice trajectory projection is disabled. Existing/manual trajectories and Step 6 policy remain unchanged.
- **Verification:** Final diff check and scoped pycompile passed; pure endpoint test passed 1/1; focused Slicer target emitted `DENTOBOT_ASSISTED_PULP_PASS` and `DENTOBOT_STEP4A_P0_PASS`, exited 0, and left no Slicer process. Evidence: `/tmp/dentobot-verification/step4a-p0-20260910/result.json`.
- **Next:** Reload the module, deliberately delete the legacy FDI31 set, generate one current assisted line, and record normal-window 3D surface contact plus non-projecting 2D slice behavior before anatomical approval.

## Immediate P0 — restore truthful Step 4A smooth masks

- **ID:** `W4-U-02`; **Priority:** 0; **State:** Root-cause correction and focused automated verification passed (2026-09-10); normal-window visual acceptance remains pending.
- **Operator observation:** Smooth masks do not work and must be restored now as Priority 0.
- **Finding:** The checked control returned without applying anything outside the special oblique-verification state and did not synchronize itself from the actual CBCT and segmentation display modes. It could therefore present a checked no-op in ordinary Step 4A.
- **Corrected contract:** With a complete selected trajectory, the same switch operates in ordinary Step 4A and oblique verification, using Slicer's existing scalar interpolation and closed-surface 2D representation without modifying source voxels or masks. Outside oblique verification it reflects the actual joint CBCT/mask state; oblique exit restores the captured prior modes.
- **Verification:** Focused Slicer target exercised the ordinary Step 4A handler, actual CBCT interpolation, smooth/native mask representations and endpoint persistence; it emitted `DENTOBOT_STEP4A_DISPLAY_PASS` and `DENTOBOT_STEP4A_P0_PASS` and exited 0. Evidence: `/tmp/dentobot-verification/step4a-p0-20260910/result.json`.
- **Next:** Confirm in a normal Slicer window that on/off visibly changes both CBCT and masks, the checked state is truthful, and oblique disable/exit restores the prior modes. The broader representative Step 4/backtracking acceptance remains part of this task after the P0 regression check.

## Immediate P0 — terminal coverage disconnects shell collar

- **ID:** `S5B-TERMINAL-COLLAR`; **Priority:** 0; **State:** Completed: approved host regression and exact FDI11 saved-loop/fresh-auto-loop preview→shell→unified builds passed, both exit 0 (2026-09-08).
- **Operator observation:** Automatic Step 5A boundary and manual backside adjustments both leave Step 5B unable to generate the shell/unified template. Screenshot reports two remaining components; target FDI11, four support teeth, terminal coverage 50%.
- **Source finding:** The bridge previously used the full boundary, then terminal half-planes clipped the completed union. This can remove both end connections and split a collar into two rails. This is a concrete failure mechanism, not yet proof of the exact screenshot's cause.
- **Implementation:** Clip and close the boundary at the existing terminal planes before collar construction. Retain the same anatomy exclusion, final coverage clipping and one-component gate. Error text no longer implies that redrawing alone necessarily resolves the failure.
- **Verification:** Old collar produced two regions; corrected collar produced one watertight region in original and rotated frames. Combined host run: 3 passed; compilation and diff check exit 0. Evidence: `/tmp/dentobot-verification/pulp-shell-20260908/`.
- **Exact-case evidence:** FDI11 `dentobot-case-step5b.dentocase`; saved and freshly regenerated automatic boundary both have 50 points, address all five teeth, and produce 3,363-point/6,028-triangle previews. Both shells have one surface region and zero invalid edges; both unified outputs have 74,988 triangles, one occupied volume region and zero invalid edges. Source package checksum unchanged; logs in the evidence directory.
- **Next:** Operator reload and normal-window build/inspection. Development defect is verified; anatomical/manufacturing and Track A acceptance remain separate.
- **Sequencing:** Operator requested completion of pulp-endpoint and P0 prompts one after another; endpoint source work precedes this correction. Approved host checks passed; runtime resources remain serialized.

## Immediate P0 baseline cleanup — retired pre-surgery workarounds

- **ID:** `S6-P0-BASELINE-CLEANUP`; **Priority:** 0; **State:** Source cleanup, 63 focused Python tests, native guard build, and 14-check synthetic ROS phase-guard test passed. Clean-case full-loop acceptance remains pending.
- **Reason:** The retired pre-surgery/x4 fixture exposed collision and guide-fit problems. It must not drive production exceptions or planner tuning. New baseline cases must use reviewed post-surgery/clean anatomy and a finalized Step 5C guide/tool model.
- **Implemented:** The production burr-proximity helper now returns only the selected target-tooth object. Adjacent teeth, jaw anatomy, and guide/template objects remain authoritative for collision and the research clearance margin. The façade no longer sends guide/template IDs as clearance exemptions, and the ROS bridge rejects non-empty guide-clearance exemptions.
- **Quarantined:** The historical Step 5C template-collision bypass is unavailable by default and requires the explicit process variable `DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE=1`. Session anatomy-review proxies are ignored by collision publication unless `DENTOBOT_ENABLE_HISTORICAL_ANATOMY_REVIEW=1`. Neither override is saved into a case or treated as baseline evidence.
- **Preserved:** J1–J5 canonical-TCP planning, J6-outside-planning policy, strict self/world/anatomy checks, the selected-target terminal-contact policy, endpoint/guard checks, and retained diagnostics remain unchanged.
- **Next:** Review/select one clean post-surgery case and complete its guarded approach, drilling, Return Home and repeat gate. Native guard evidence: `/tmp/dentobot-verification/cleanup-guard-20260907/`. Do not revive the retired x4 override or tune tolerances/base placement to make that fixture pass.

## Active operator interruption — Step 6A changed-target geometry

- **ID:** `S6A-CHANGED-TARGET-GEOMETRY`; **Priority:** Unprioritized (operator requests immediate cleanup); **State:** Source guard implemented; focused host verification and authorized Slicer clear/save round-trip passed; clean FDI44 end-to-end rerun remains pending.
- **Observed:** Operator completed the workflow on a different target tooth and reports FD14-like remnants attached/fused after applying the open-mouth transform. Screenshot is evidence of unexpected visible geometry; its source and actual fusion are unconfirmed.
- **Impact:** Step 6A preview and any derived planning geometry need an ownership audit before acceptance. Do not remove anatomical components based on appearance alone.
- **Evidence:** Source proxy reconstruction clears prior segments, while mandibular template display is copied separately from referenced Steps 0–5 models. The readable historical FD14 MRB contains explicit FD14 Step 5C template and Step 6 obstacle lineage. The relocated FDI44 archive was read-only audited through the authorized container path and showed FDI44 text/lineage with no FD14 strings; the authorized FD14 load → New Empty Case → save regression then reported zero FD14 hits in the saved MRML and lineage.
- **Implementation:** Target changes now clear Step 6A transient jaw/target-attached geometry before downstream deletion; authoritative segmentation changes do the same. The target-attached display builder filters models by persisted target lineage and hides/marks mismatched stale models. Restore validation now rejects mismatched trajectory/ROI/docking/template target chains, clears disposable opened-jaw proxies when deactivating a stale package, keeps mismatched source visibility suppressed, refuses to let a saved trajectory silently overwrite the active target during UI hydration, and keeps Reset reachable for stale transient refs while ROS is disconnected.
- **Verification:** Temporary-cache compile and `git diff --check` passed; the focused pure Step 6 suite passed `58 tests` including the modular/context budget; Graphify refreshed. The authorized pinned-container Slicer round-trip loaded FD14, cleared it with New Empty Case, saved a validated bundle, and reported `mrml_FDI14=0` and `lineage_FDI14=0`; no motion or hardware operation was performed.
- **Next action:** Repeat the complete FDI44 workflow from a clean session and visually verify Step 6A. The clear/save regression now supports session carry-over as the cause when New Empty Case is used successfully, while the separate FDI44 archive audit remains text/lineage-only and cannot establish binary mesh identity. Regenerate FDI44 Step 4A/4C/5C if the package reports a cross-target chain; only then repeat 6.0A. See `logbook/2026-09-07.md`.

## Track A priority 0 gate — paused during PreparedBranch correction

| Order | ID | Priority | State | Next bounded action |
|---:|---|---:|---|---|
| 1 | `S6-LIVE-00` | 0 | Documentation checkpoint recorded; source baseline `ea504349f99f` preserved; scoped static/pure checks, rebuild, runtime marker, and graph refresh recorded | Keep the checkpoint boundary explicit while reconciling the remaining Stage-3 reachability issue |
| 2 | `S6-LIVE-01` | 0 | Source implemented; full Stage-3 acceptance open. Older 60/64 result is historical; current FDI11 evidence is above | After workflow integrity, resolve the reviewed case's exact Stage-3 blocker and require complete endpoint/guard evidence |
| 3 | `S6-LIVE-02` | 0 | Implemented: independent guard remains authoritative for J1–J5; legacy six-value spindle motion is rejected | Runtime trial must confirm every Stage 1/2/3 waypoint, narrow burr exception, and external-spindle boundary |
| 4 | `S6-LIVE-03` | 0 | Implemented: endpoint checks, consumed stop state, guarded Return Home/replan loop, and diagnostic/live-preview overlap guard | Runtime trial must complete Goal 1→Goal 2→Return Home→replan without Slicer restart |
| 5 | `S6-LIVE-04` | 0 | Implemented: timestamp/speed playback, 30 Hz display coalescing, progress UI, static phase paths | Runtime trial must confirm selectable speed preserves ordered acknowledgements and visible paths |
| 6 | `S6-LIVE-05` | 0 | Historical x4 Goal-1 evidence is retained only as a negative diagnostic; clean-case acceptance is not yet run | Select a reviewed post-surgery/clean case with finalized guide/tool geometry, then complete the full guarded loop |

## P1 Case Platform / Simulation Studio — blocked by `S6-LIVE-05`

| Order | ID | Priority | State | Entry condition |
|---:|---|---:|---|---|
| 1 | `DCP-00` | 1 | Planned | Track A full loop accepted; freeze façade/backend handoff |
| 2 | `DCP-01` | 1 | Complete as planning record | This 2026-09-05 supersession; no implementation work beyond controlled docs |
| 3 | `DCP-02..08` | 1 | Remaining work deferred; promoted P0 subset is under correction | `DCP-00`; reuse accepted registry/environment/persistence rather than implementing them again |
| 4 | `DCP-09..10` | 1 | Planned | Case/platform foundations accepted |
| 5 | `DSS-01..05` | 1 | Planned | Data/platform foundation accepted; migrate Track-A behavior without changes |
| 6 | `DSS-06..12` | 1 | Planned | Guarded Preview parity accepted |
| 7 | `DHW-01..02` | 1 | Planned | Explicit later safety/architecture approval |

## Legacy task aliases

`S6-P0-01` full-chain planning is continued under `S6-LIVE-01..05`.
`S6-P0-02` restore continues under `S6-RESTORE-ROBOT-ROS` and the P0
PreparedBranch checks. Their old auto-reconnect and fixed-roll instructions
are historical. `S6-P0-DEPTH`, `S6-P0-CLEARANCE` and
`S6-P0-ANATOMY-REVIEW` retain historical evidence in the 2026-09-04–09
logbooks; no retired-case override is an active recovery action.

`AGENT-ASTRA-LOW` is superseded by `AGENT-SOL-RESTORE`; model policy is
maintained only in AGENTS.md, with dated rationale in DECISIONS.md.

## Next — queued by priority

| ID | Priority | State | Entry condition | Next acceptance action |
|---|---:|---|---|---|
| `S6-P1-01` | 1 | Partially implemented; anatomical safeguards pending | Current P0 correction accepted | Add bilateral condylar/crown regions, exact-source snapping, MPR review and representative anatomy acceptance |
| `S6-P2-01` | 2 | Planned | `S6-P0-02` checkpoint matrix understood | Implement one post-load visual integrity panel for Steps 1–6 with Current, Needs attention, Stale, Blocked upstream, and Rejected states |
| `S6-P2-02` | 2 | Planned | `S6-P1-01` accepted | Add smooth display-only incisor-gap preview and one explicit commit action |
| `S6-P2-03` | 2 | Planned | Priority-0 correctness accepted | Add shared truthful busy/progress/result/cancel behavior to long-running actions without fake percentages |
| `W4B-P2-SUPPORT-AUTO` | 2 | Backlog; operator screenshot confirms narrow two-row support arch | Current P0 PreparedBranch correction accepted; preserve Step 4B ownership | Auto-suggest the four nearest same-jaw support teeth—two on each side in dental-arch order—then require ordinary Step 4B review/lock. Deliver a one-row selected-jaw layout during the GUI revamp, with manual editing for edge, missing, or unsuitable teeth |
| `UI-P3-01` | 3 | Planned | Studio functional acceptance and Priority 1–2 correctness | Refine the New GUI while proving Legacy parity, incorporating the `W4B-P2-SUPPORT-AUTO` single-row jaw requirement, and adding no new MRML/ROS side effects |
| `S6-U-01` | 4 | Deferred reliability DENTO-NOTE. Functional connect/reload/reconnect/New Case/reconnect/save-reopen passes after the native ownership repair; only application shutdown still reports retained SlicerROS2/MoveIt VTK objects and class-loader warnings | Priority 0–3 work or an observed runtime regression no longer blocks it | Centralize native shutdown, release robot/parameter/pub-sub/MoveIt wrappers before library unload, correct test process-group cleanup, then require a zero-exit lifecycle run with no SlicerROS2 leaks |

## Unprioritized active and backlog

| ID | State | Next bounded action |
|---|---|---|
| `S3-U-01` | Scan/run inspection workflow implemented; focused Slicer PASS | Operator reload and visual check on the real preDental/postDental scene; confirm Step 0–3 context bar, source-paired switching, compare, rename, and Step 4 handoff |
| `S6-U-04` | Fix implemented; normal-window acceptance pending. Goal 1 diagnostics **Close** did not dismiss the window before or after evidence review, forcing use of the title-bar X | Run Goal 1, open diagnostics, verify **Close** dismisses it both before and after **Mark Current Evidence Reviewed**, then reopen it and confirm no stale callback/window state |
| `S6-U-02` | Manual Simulation Base containment accepted; physical forehead/mount relationship unresolved | Obtain mount-face CAD/contact normal and define patient-contact-to-base transform, offsets, review, persistence, and invalidation |
| `W4-U-01` | Active design | Define reviewed crown region and MPR contract, then implement source-fingerprinted Entry snapping |
| `W5-U-01` | Physical-fit provenance unresolved; optional export manifest remains backlog | Correct/verify guide bore versus burr; decide separately whether an optional path-independent STL manifest is useful. Neither STL nor manifest establishes Step 6 geometry authority |
| `IMG-U-01` | Representative acceptance pending | Compare authoritative masks and optional display previews on governed CBCT; define acquisition/artifact/segmentation uncertainty evidence |
| `W4C-U-01` | Design and representative acceptance pending | Validate support-aware docks, collisions, channels, rail roles, tolerances, and the non-parallel-trajectory versus one robot-axis constraint |
| `W5-U-02` | Representative and physical acceptance pending | Validate the read-only Step 4B support pack in Step 5A, editable margin, undercut/removability, shell contact, seating, and terminal support on governed anatomy/phantom |
| `W5-U-03` | Representative acceptance pending. **DENTO-NOTE 2026-09-07:** Step 5B unified-template creation needs detailed operator testing beyond smoke. During 2026-09-10 Step 4A verification, the combined runner passed Step 4A display, assisted pulp and FDI11 shell stages, then failed independently at unified fusion with 10 occupied volumes `[60677, 9, 4, 3, 1, 1, 1, 1, 1, 1]`. Read-only diagnosis traces the regression boundary to the current `W5-U-04` extended through-bore subtraction: the same case passed on 2026-09-08 before dock channels grew from 5.6 mm to 9.6 mm; FDI11's 2.2 mm bore leaves 9- and 4-voxel slivers above the conservative 0.1 mm³ cleanup ceiling. The supplied FDI31 run-2 Step6x5 package is a successful comparison case (saved raw regions `[45846, 1]`, cleaned to one), not the failed artifact | Localize the FDI11 slivers and correct the shared bore/attachment construction under `W5-U-04` without relaxing the one-solid gate or blindly raising the artifact threshold; then run current Step 5B fusion and Step 5C PASS/WARNING/FAIL on both FDI11 and FDI31, reopen, stale-lineage, channel-preservation, and one-STL flow; include dock/rail visibility and printability review |
| `W5-U-05` | **DENTO-NOTE 2026-09-07 (UX / workflow).** Step 5B template dimensions interact badly with upstream steps; **no clear Reset** for the unified-template path; **no interactive viewing** while sizing/fusing; the **Advanced** collapsible must be collapsed manually every entry even though 5B is a **required** stage, not an optional advanced detour | Redesign Step 5B panel: promote primary unified-template controls out of “Advanced”; add owned Reset (geometry + params + stale markers); add interactive 3D inspection while adjusting dimensions; gate/validate dimension coupling against Step 4A/4C/5A lineage so bad upstream combos fail closed with an explicit message |
| `VIEW-U-01` | Cross-workflow normal-window acceptance pending. **DENTO-NOTE 2026-09-07:** mask 2D/3D opacity sliders no longer reachable in the viewer path the operator uses — see `VIEW-U-02` | Exercise grouped anatomy, stage presets, manual toggles, frame/restore, opacity, CBCT rendering labels, save/reopen, and Legacy/New parity without renderer or geometry side effects |
| `VIEW-U-02` | **DENTO-NOTE 2026-09-07.** Viewer no longer exposes **2D / 3D opacity sliders for masks**. Legacy still wires `segmentation2DOpacitySlider` / `segmentation3DOpacitySlider` in segmentation UI; operator path (likely New GUI / View Controls) lost them. Needs a **deeper UI/UX plan**, not a one-off restore | Map Legacy vs New GUI vs View Composition ownership of mask opacity; design always-available 2D fill/outline + 3D surface opacity controls (stage-safe, display-only, scene-persistent); plan parity with CBCT opacity and group visibility; implement after written UX plan acceptance, then close with normal-window trial |
| `S6-U-03` | Experimental design; not planning authority | Derive only confidence-labelled observed oral-air surfaces when suitable open-mouth/phantom data exists; keep unobserved space occupied/unknown |
| `CASE-U-01` | Backlog | Define and implement an offline no-ROS migrator for contaminated historical MRML/MRB scenes; never load them into a live ROS process |
| `PLAT-U-01` | Blocked by clean-image acceptance | Rebuild the pinned Ubuntu inference image and accept dependency, backend, Bridge, Slicer import, and persistence behavior without mutable-container repair |
| `PLAT-U-02` | Retired as a primary install; retained as an explicit native Windows Steps 0–5 fallback. Source hides Step 6 and blocks its automatic runtime restore; real-host regression pending | On a Windows workstation, run the renamed fallback check and verify Steps 0–5 plus absence of Robot Simulation; keep native Windows ROS out of scope |
| `PLAT-U-04` | Direct Docker Engine inside WSL2 is the approved default and `WINDOWS_SETUP.md` is canonical; Docker Desktop WSL integration is an exclusive alternative. One Desktop install passed recorded WSLg/CUDA startup; the direct-Engine machine still lacks exact acceptance evidence | Capture the second machine manifest and approved check-only, GUI, segmentation, and simulation evidence; reconcile an isolated release revision, create/advance `stable/lab`, and publish a new immutable lab tag and image identity |
| `PLAT-U-05` | Ubuntu NVIDIA dual-GPU setup and launcher support integrated; laptop `--check-only` and in-container CUDA passed, while IITM CPU regression remains pending | Run the documented check-only gate on the IITM CPU workstation after updating to the integration commit; retain CPU configuration unless CUDA is intentionally adopted |
| `PLAT-U-06` | Active investigation: the fork base already includes upstream's Slicer 5.12 test commit, current upstream is only three non-runtime-code commits ahead, while the accepted derivative image still uses Slicer 5.10.0 | Preserve the 5.10 rollback; create an isolated 5.12.0 upgrade branch, merge upstream, capture/audit the uncommitted fork APIs, build from the upstream 5.12 digest, then request approval for the staged compatibility and performance gates in `SLICERROS2_5_12_UPGRADE.md` |
| `PLAT-U-03` | Deferred observation | After an approved reboot, record overnight CRD/GDM availability and resource behavior before closing workstation stability |
| `QA-U-01` | Unresolved | Diagnose why the aggregate Slicer test wrapper returns nonzero although isolated members reach PASS; do not treat isolated PASS as aggregate closure |
| `ROS-U-01` | Future design | Define geometry-preserving medical-image and transform semantics before broadening ROS scope beyond current bounded simulation interfaces |
| `POC-U-01` | Strategic parallel lane | Freeze one narrow task and acceptance thresholds, then run representative software, print/seating, registration, and error-budget work |

## Future track

The former F0/F1/F2 and separate .dentostudy sequence is superseded by
`DCP-*`/`DSS-*`; it is not a second implementation queue. Physical
registration/mount/controller work retains its existing prerequisites.

## Recently closed or superseded

These are pointers only; complete evidence remains in the archive, decisions,
reproducibility record, changelog, and dated logbook.

| Item | Disposition |
|---|---|
| Cross-tool agentic verification protocol | V1 source/pure-contract complete 2026-09-02: one canonical protocol and resource-aware matrix serve Codex, Cursor, and Claude; runtime execution remains approval-gated and serialized |
| GitHub default / overlay / Windows-lab conversion docs | `main` is authoritative; the pinned lab release and private Linux/amd64 GHCR image are published. First Windows WSLg/CUDA functional startup passed on 2026-09-07; repeatability on the next clean lab PC remains `PLAT-U-04` |
| Overlay Drive/MCP temps and nested `DentoBot/graphify-out/` | Deleted 2026-09-02; live graph stays at overlay `graphify-out/`. Launch scripts kept |
| Portable overlay `arduino-pressure/` package | Superseded; live bench is `tools/arduino-pressure/` in the DentoBot git tree |
| Host Arduino pressure fs / pipeline Config tab | Source complete 2026-09-02; `py_compile` and `--no-gui` verified; live flash/Hz click pending. Sensing-only |
| Step 6 action ownership/runtime-first ordering | Accepted and moved to the Development Plan ownership contract; no longer an active task |
| Collision object identity/audit | Runtime-accepted for the exact x4 scene; recheck only when its fingerprint changes |
| Viewer showing only internal tooth anatomy | Source-fixed and exact-package verified; remaining normal-window restore/toggle acceptance is owned by `S6-P0-02`, not a duplicate Priority-0 workstream |
| Step 6 substep split/restore deadlock | Fixed; superseded by `S6-P0-02` for checkpoint reconstruction acceptance |
| Schema-v1 bundle compatibility and orientation replay | Implemented and verified; retained as migration history |
| Goal 1 world/base Cartesian conversion defect | Diagnosed/fixed; remaining full-chain work belongs only to `S6-P0-01` |
| Earlier spindle-roll candidate planning | Superseded by spindle-locked arm-route planning; old evidence is historical only |
| Economical workflow modularization | Completed; the active ROS scene-clear abort remains only under `S6-U-01` |

## DENTO-NOTE triage and maintenance rules

- Record every new `DENTO-NOTE` once with a stable ID, affected workflow,
  evidence, impact, priority (or `Unprioritized`), and next acceptance action.
- Priority order is numeric and ascending: 0, 1, 2, 3. A documented dependency
  may execute earlier without acquiring a fabricated priority.
- Update the existing row when state changes; do not create a second active
  section, dated `Next` list, or repeated prose copy.
- Put implementation chronology in today's logbook and durable rationale in
  `DECISIONS.md`. Put exact hashes, schemas, and verification results in
  `REPRODUCIBILITY_AND_TRACEABILITY.md`.
- Move completed/superseded detail to an archive at a controlled documentation
  checkpoint. Do not delete historical evidence.
- No task is successful without recorded verification. Current approval covers
  `py_compile`, scoped pure `pytest`, and necessary production SlicerROS builds;
  Slicer/ROS/MoveIt runtime checks remain operator-led unless separately approved.
- No hardware motion, drilling, patient-facing action, or clinical/safety claim
  is authorized by this queue.
