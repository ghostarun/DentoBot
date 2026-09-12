# S6-REUSABLE-CASE-SETUP — FDI32 Diagnostic and Release Evidence

**Date:** 2026-09-13

**Scope:** Case Foundation, offline Manual Simulation Base, opened-frame
trajectory authoring, and downstream Step 4B–5C navigation

**Case:** `dentobot-case-13sept.dentocase` (operator-supplied, preserved
read-only)

**Verification mode:** bounded Slicer/Xvfb diagnostic run; no ROS, MoveIt,
robot motion, drilling, hardware, or patient-facing action

## Executive result

The requested implementation slice is complete and the corrected focused
workflow passes end to end through assisted FDI32 trajectory generation:

```text
Case load (diagnostic integrity copy)
  -> Stage 3 Case Foundation / committed mouth opening
  -> Step 6 offline local robot + Manual Simulation Base
  -> Step 4A target selection before base lock
  -> FDI32 crown-centre assisted entry
  -> valid opened-frame assisted trajectory
  -> Manual mode remains available
  -> Step 4B, 4C, 5A, 5B, 5C remain navigable
```

The intermittent early-step full-anatomy failure and the blank/off-camera
opened-jaw Step 4A trajectory view were traced to shared display and coordinate
frame boundaries, not to the source CBCT or reviewed segmentation. The
production changes now normalize all relevant segmentation visibility and use
the jaw-owner-aware opened planning frame for lower-jaw bounds, entry points,
targets, and framing.

This is targeted runtime evidence, not final task closure. The supplied package
still fails its production integrity gate because its saved MRML base revision
is inconsistent with its saved lineage/environment revision. The original
package was not changed.

## Scope and evidence boundary

The controlled records used for this retrospective were `backlog.md`,
`TASKS.md`, `DEVELOPMENT_PLAN.md`, `DECISIONS.md`,
`ARCHITECTURE.md`, `REPRODUCIBILITY_AND_TRACEABILITY.md`, and the dated
logbook. The engineer-owned `IITM Dental Drilling Robot — Project Tracker` was
not opened or modified; its already recorded aliases are treated only through
the controlled backlog crosswalk. No patient identifiers are recorded here.

The run intentionally did **not** claim:

- a current Step 5C PASS or a completed PreparedBranch;
- ROS/MoveIt connection, Task Home, collision-scene acknowledgement, planning,
  guarded preview, or hardware safety;
- physical registration, robot accuracy, anatomy correctness, or clinical
  suitability;
- acceptance of the original package's stale integrity state;
- normal-window operator acceptance.

## Source package and diagnostic repair

| Item | Observed value | Interpretation |
|---|---|---|
| Original package | `/home/light-tarun/dentobot/data/Slicer_Saved/SampleStudy1/dentobot-case-13sept.dentocase` | Operator-supplied input; preserved unchanged |
| Original SHA-256 | `14ed8f0f61e0c791d31b9582af7969ce712dd80d8cfd3a33319da63d0a996a15` | Checksum remains unchanged after the run |
| Production load result | `step6BasePlacementRevision 1` disagreed with saved lineage/environment revision `0` | Correct fail-closed behavior; not bypassed in production |
| Diagnostic copy | `data/dentobot-runs/case13sept-fdi32-repaired18/diagnostic-integrity-repaired-case.dentocase` | Test-only copy |
| Diagnostic edit | One inner MRML token changed from `1` to `0`; MRB, manifest scene hash/size, and checksum list rebuilt | Narrow integrity diagnosis; not a migration or replacement |
| Diagnostic copy SHA-256 | `a1de5621051c96d2cd4c053eea561e74e126d5ace3a7b2e81663c3315654446f` | Applies only to this evidence run |

The repair was necessary to exercise the Case Foundation and planner code. A
future exact-package acceptance run must use an explicit current save or a
reviewed migration that produces a consistent package; weakening the loader is
not an acceptable fix.

## Implementation delivered

### 1. Workflow presentation and visibility

- Segmentation and review are presented as Stage 2 continuation.
- The open-mouth Case Foundation is a dedicated Stage 3 section titled
  `Case Foundation — Open Mouth Setup (required before Step 4A)`.
- Step 4A begins with trajectory planning after the committed pose.
- Recommended views now show the full rigid reviewed planning anatomy rather
  than a stale pulp-only subset.
- Aggregate, 2D, 3D, and every per-segment visibility flag are normalized for
  the selected reviewed segmentation and Case Foundation derived displays.
- The colored fixed-upper and moving-lower displays are authoritative for an
  opened case; the beige opened-lower fallback is hidden when the colored
  moving proxy exists.

### 2. Shared opened planning frame

- Added one shared jaw-owner-aware planning-bounds helper.
- Upper targets remain in source/world coordinates.
- Lower targets use the moving-lower Case Foundation proxy bounds once the pose
  is current.
- Assisted entries are accepted in the planning/opened world, converted back to
  immutable source coordinates for root/pulp analysis, then converted back to
  opened world coordinates for trajectory publication.
- The trajectory provenance records both source and planning points and the
  `OpenedCaseFoundationWorldRAS` coordinate-system identity.
- Planning ROI, bounds validation, target focus, and Step 4A framing use the
  same opened-frame contract.
- Camera clipping is reset and then constrained around the focused bounds so
  hidden/stale workflow actors cannot move the near plane in front of the
  target.

### 3. Step 4A gate correction

With a current Case Foundation pose, Step 4A target selection, Manual/Assisted
mode selection, assisted count selection, and assisted entry placement are
enabled even while the Manual Simulation Base remains unlocked. Base review and
the later ROS gate retain their own independent eligibility requirements.

### 4. Focused verification harness

`Testing/run_dentobot_case13sept_fdi32_workflow_smoke.py` now:

- keeps the source package read-only;
- applies only the opt-in diagnostic revision repair;
- verifies Case Foundation pose and no restored ROS state;
- reconstructs the local robot offline;
- checks Stage 3 and Step 6 display visibility;
- checks Step 4A target/assisted controls before base locking;
- selects FDI32;
- computes a crown-cap point from the reviewed closed surface;
- maps that point into the opened lower-jaw planning frame;
- generates one assisted trajectory;
- asserts the generated Entry and Target lie inside opened target bounds;
- captures UI and actual VTK viewport PNGs;
- walks the downstream stage sections without creating a PreparedBranch or
  activating ROS.

## Measured success/error comparison

| Checkpoint | Earlier failure or risk | Corrected observation | Status |
|---|---|---|---|
| Original case load | Saved base revision `1` versus environment revision `0` | Production loader still rejects the original; diagnostic copy is used only to inspect the workflow | **Expected error / unresolved integration blocker** |
| Stage 3 full anatomy | Intermittent pulp-only or incomplete segmentation view | Fixed upper and moving lower Case Foundation displays: aggregate `true`, 3D `true`, all 15 segments `true` | **Pass** |
| Step 6 opened anatomy | Beige lower-jaw fallback could obscure the reviewed colors | Fixed/moving colored proxies visible; beige fallback `false` | **Pass** |
| Step 6 local robot | ROS state could be mistaken for restored runtime state | Seven local link models reconstructed; `ros_active: false`; no ROS nodes/transforms restored | **Pass** |
| Step 4A before base lock | Target selector and assisted controls stayed disabled until base lock | Target selector, placement mode, count, and entry placement enabled with base `Unlocked` | **Pass** |
| Entry frame | Crown entry was selected in source/closed coordinates while the jaw was opened | Source point mapped into opened planning frame before placement | **Pass** |
| Target bounds | Closed source bounds did not contain opened lower-jaw points | Shared bounds helper returns moving-lower opened proxy bounds | **Pass** |
| Assisted generation | Generated line could be valid numerically but off-camera/absent from viewport | Valid two-point FDI32 line is visible inside the opened target bounds | **Pass** |
| Manual fallback | Assisted selection could leave placement mode locked | Manual mode remains enabled after assisted generation | **Pass** |
| Downstream navigation | Later stages could become inaccessible after early setup | 4B, 4C, 5A, 5B, 5C sections became visible and remained pose-eligible | **Pass (navigation only)** |
| PreparedBranch/Step 5C | No current branch/evidence exists in the foundation-only diagnostic case | Runner correctly created zero PreparedBranches and did not claim Step 5C PASS | **Expected not-run boundary** |
| ROS gate | Live state must not be restored or implied by offline setup | `ros_active: false`; no connection attempted | **Pass / intentionally not exercised** |

## Runtime parameters and fingerprints

| Parameter | Value |
|---|---:|
| Source volume | `PostDentalSurgery` |
| Reviewed segmentation | `Post_surgery_seg` |
| Pose eligibility | `VALID` |
| Planning-pose fingerprint | `2f6006ce3404580a20a0be7a417799772bd78313ed2f8685915e66b079593e5a` |
| Source volume fingerprint | `5da4bf481fa08fd1c96b6c6c92ba23fde8a7c52be50de84b4bb3fad146e19ce8` |
| Source segmentation fingerprint | `551dc41227a127c1af9f2938ad35db37b3972e2fbb056d98f02bcb1f32d7cdc5` |
| Base setup fingerprint | `2784c8166b6b9cc8c1ca54169fcc0a504df82cd4eaa7f14ab6271e682590ab0e` |
| Foundation fingerprint | `ca22376acf308933127d5c9119a9ff01342e92c28b899c7e311bdd8c1cdc4789` |
| Robot link count | `7` |
| Base state | `Unlocked`, `robotBaseMountLocked=false` |
| PreparedBranch count | `0` |
| ROS active | `false` |
| Target | FDI `32` — lower left lateral incisor |
| Automated crown-cap source entry | `[-100.73516082763672, -37.3179931640625, 54.4561653137207]` RAS mm |
| Opened planning entry | `[-101.53327443967304, -69.6108299989029, 32.5407449482724]` RAS mm |
| Generated target | `[-100.62081112637362, -74.45570323982005, 30.13010928847464]` RAS mm |
| Generated line length | `5.487854799733803` mm |
| Defined points | `2` |
| Creation method | `EntryDirectedRootSurfaceCapV1` |
| Planning coordinate system | `OpenedCaseFoundationWorldRAS` |

## Visual evidence

All 24 PNGs referenced by `result.json` exist. The key evidence is below;
the complete set is in
`/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired18/`.

### Stage 3 — Case Foundation

![Stage 3 Case Foundation UI](/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired18/stage3-case-foundation-ui.png)

![Stage 3 full vivid reviewed anatomy](/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired18/stage3-case-foundation-viewport.png)

### Step 6 — offline robot and Manual Simulation Base

![Step 6 offline base UI](/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired18/step6-offline-base-ui.png)

![Step 6 robot with opened reviewed anatomy](/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired18/step6-offline-base-viewport.png)

### Step 4A — FDI32 assisted generation

![Step 4A controls before base lock](/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired18/step4a-target-selection-unlocked-base-ui.png)

![Step 4A generated FDI32 trajectory UI](/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired18/step4a-fdi32-assisted-generated-ui.png)

![Step 4A generated FDI32 trajectory viewport](/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired18/step4a-fdi32-assisted-generated-viewport.png)

### Downstream navigation

![Step 4B remains inspectable](/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired18/stage5-ui.png)

![Step 5C remains navigable](/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired18/stage9-ui.png)

Machine-readable evidence: [result.json](/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired18/result.json)

Runtime log: [run.log](/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired18/run.log)

## Verification commands and results

| Level | Command/check | Result |
|---|---|---|
| Static | `PYTHONPYCACHEPREFIX=/tmp/dentobot-case13sept-pycache6 python3 -m py_compile DENTOWorkflow/Resources/Python/dentobot_workflow/logic_planning_dependencies.py DENTOWorkflow/Resources/Python/dentobot_workflow/logic_workflow.py DENTOWorkflow/Resources/Python/dentobot_workflow/widget_planning_focus.py Testing/run_dentobot_case13sept_fdi32_workflow_smoke.py` | Pass |
| Static | `git diff --check` | Pass |
| Graph | `graphify update .` | Pass after source changes |
| Pure targeted | `python3 -m pytest -q Testing/test_modular_structure.py Testing/test_view_presets.py` | 12 passed; one unrelated pre-existing context-budget failure |
| Slicer runtime | Bounded serialized FDI32 runner in the pinned SlicerROS2 container, using the opt-in diagnostic copy | Pass markers listed above; exit 0 |
| Evidence files | Re-read `result.json`; check all 24 referenced PNGs | 24/24 present |

The one pure-test failure is not part of this change: the existing
`test_active_workflow_modules_stay_within_context_budget` reports
`widget_template_build.py` at 1,511 lines against a 1,500-line policy. No
unrelated module was refactored to hide that result.

After the pass marker, Slicer printed Qt teardown callbacks that attempted to
touch destroyed planning widgets. They did not alter `result.json`, occurred
after `DENTOBOT_CASE13_FDI32_WORKFLOW_PASS`, and are retained as non-causal
teardown noise rather than a workflow failure.

## Retrospective against controlled task crosswalk

| Controlled ID / tracker alias | Accomplishment in this slice | Remaining status |
|---|---|---|
| `S6-REUSABLE-CASE-SETUP` | Case Foundation before Step 4A, branchless offline base path, full-anatomy view normalization, opened-frame FDI32 assisted generation, and focused evidence | Source/targeted runtime implementation is complete; exact package integrity, current Step 5C branch, and normal-window acceptance remain open |
| `A-012`, `A-014`, `A-027` software/workflow umbrella | Reused the existing parameter node, MRB authority, Case Foundation snapshot, and PreparedBranch registry without adding a second state system | Continue through the existing S6 acceptance gate; no parallel planner architecture |
| `A-035` trajectory assistance / `S4A-PULP-ENDPOINT` | Demonstrated the current assisted root-target path on FDI32 with source/planning provenance | FDI31 legacy regeneration and anatomical review remain pending; FDI32 geometry is not clinical evidence |
| `A-023`, `A-032` template automation / `W5-U-03`, `W5-U-04` | Preserved the existing Step 4B–5C algorithms and only proved downstream navigation | Current Step 5B/5C fusion and residual-fragment blockers still require a reviewed clean case |
| `S6-RESTORE-ROBOT-ROS` | Verified offline local robot reconstruction without ROS restoration | Warm/cold exact-package restore and explicit ROS gate remain pending |
| `S6-LIVE-01..05` | Did not alter planner/guard/collision policy; kept live work behind the explicit gates | Stage 3 full planner, guard, repeat, and reviewed clean-case loop remain pending |
| `S6-FDI11-DEPTH` | Did not tune depth, margins, or collision policy from this visual issue | FDI21 housing contact remains a separate unprioritized diagnostic blocker |
| `W4-U-02` / view acceptance | Fixed the reported full-anatomy presentation path in the targeted case | Normal-window smooth-mask and representative view acceptance remains open |
| `PLAT-U-07` | No case data or Drive synchronization was attempted | Separate workstation/case-exchange pilot remains unprioritized |

The current order remains `W5-U-04` → `S6-REUSABLE-CASE-SETUP` exact/current
single-target acceptance → optional explicit pairing/32×3 → `S6-LIVE-01..05`.
The older F0/F1/F2 `.dentostudy` concept, a second planner registry, and the
retired Draft Open-Mouth Phantom are not revived by this work.

## Priority checklist for Stage 3 planner completion

The following checklist is the smallest dependency-ordered route from this
implementation checkpoint to an end-to-end Stage 3 planner acceptance. The
priority labels describe completion importance, not a new backlog or a change
to the recorded task IDs.

| Priority | Importance | Owner / task | Required action and evidence |
|---:|---|---|---|
| P0 | Release blocker | `S6-REUSABLE-CASE-SETUP` | Resolve the supplied case revision mismatch by an explicit current save or reviewed migration. Reopen the resulting package and prove source, segmentation, Case Foundation, base, registry, and checksum identities. |
| P0 | Geometry gate | `W5-U-04` → `W5-U-03` | Use a reviewed clean case to classify the retained FDI31 fragment, make one evidence-backed construction correction, and require four open bores, zero channel occupancy, one connected printable solid, and no hidden source dock duplicate. Do not raise the cleanup threshold. |
| P0 | Branch gate | `S6-REUSABLE-CASE-SETUP` | Complete one current `4A→4B→4C→5A→5B→5C` single-target path. Record current Step 5C PASS/WARNING/FAIL identity, create exactly one schema-3 PreparedBranch, and prove activation is atomic and reversible. |
| P0 | Operator gate | `S6-REUSABLE-CASE-SETUP` | Perform the ten normal-window observations: review→landmarks→opening, smooth controls, opened MPR, aligned descendants, offline base, foundation-only save/reopen, branch switch, gap invalidation, base rereview plus Step 5C rerun, and ROS enablement only after every gate is current. |
| P0 | Planner core | `S6-LIVE-01` | With a reviewed clean case and explicit ROS/MoveIt approval, prove strict Home→PreEntry, fixed-axis PreEntry→Entry, fixed-axis Entry→Target, bounded IK fallback, exact FK endpoint residuals, and first-invalid diagnostics. No hardware motion. |
| P0 | Safety/runtime gate | `S6-LIVE-02` | Verify independent J1–J5 phase guards, stale identity rejection, non-target/self/world collision rejection, and the narrowly configured burr/guide warning policy. Keep warnings distinct from collision-free claims. |
| P1 | Repeatability | `S6-LIVE-03` | Prove Goal 1→Goal 2→guarded Return Home→replan or branch switch without Slicer restart; stale plans, guards, and acknowledgements must be cleared while shared foundation remains. |
| P1 | Evidence quality | `S6-LIVE-04` | Verify acknowledgement-driven playback, selectable speeds, accepted/total waypoint reporting, separate Stage 1/2/3 routes, and complete/partial/first-invalid labels. |
| P1 | Assisted anatomy review | `S4A-PULP-ENDPOINT` / `W4-U-01` | Deliberately regenerate the legacy FDI31 assisted set in a current case and perform the normal-window anatomical review of native/displayed pulp contact and slice glyph projection. |
| P2 | Optional expansion | Explicit pairing / 32×3 registry | Run only after the default single-target branch path is accepted. Keep pairing explicit and never auto-merge three trajectories. |
| Deferred | Product expansion | `DCP-*`, `DSS-*`, `PLAT-U-07` | Do not start Studio, database, batch, whole-folder case sync, or platform migration as a workaround for the remaining workflow gates. |

## Recommended next verification packet

1. Obtain or create an explicitly current saved package with consistent base
   revision/lineage; preserve the diagnostic copy as historical evidence.
2. Run the existing focused `runtime.s6_reusable_case` matrix target against
   that package, then stop on the first causal failure.
3. Build one current single-target Step 4B–5C branch and record Step 5C
   evidence before activating it.
4. Ask separately for the approved normal-window and, later, ROS/MoveIt runtime
   windows. Do not infer either from this offline diagnostic.

**Release disposition:** implementation and targeted runtime evidence are
complete; the S6 backlog item remains open until the exact-package, current
PreparedBranch, and normal-window acceptance gates above are recorded.
