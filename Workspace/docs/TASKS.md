# Dentobot Tasks

Last updated: 2026-08-24

## Durable issue-capture keyword

Use `DENTO-NOTE: <observation>` anywhere in a user message to create a durable
workflow issue. Each note is triaged in the same turn as **fix now**, **active
investigation**, **blocked**, or **backlog**. Anything not fixed and verified
immediately is added to this task file with its workflow step, observed
behavior, available evidence, impact, and next verification action; the dated
logbook records the triage outcome.

The consolidated implementation/evidence boundary, improvement backlog,
clinical-accuracy questions, mechanical ambiguities, prohibited
interpretations, and validation gates are recorded in
`PROJECT_CHECKPOINT_2026-08-12.md`. Use that checkpoint when converting the
active list below into clinician, phantom, manufacturing, or robot acceptance
work; an implemented or synthetic PASS is not a clinical claim.

## DENTO-NOTE: native Step 6 placement-to-task sequence — 2026-08-24

- **Triage: fixed now through guarded simulation preview.** Step 6 now exposes
  6.0 Case/task, 6.1 local robot/base/provisional proxy, 6.2 Task Home, 6.3 FK
  workspace and reviewed assisted limits, 6.4 native ROS/MoveIt connection and
  immutable task confirmation, 6.5 collision-checked approach/terminal Entry
  contact, and 6.6 guarded Entry-to-Target drilling preview in both GUIs.
- **Persistence/stale behavior fixed:** base source/revision/status, proxy,
  versioned Task Home, reviewed limits, task snapshot, and opacities persist;
  runtime robots/goals/plans/ROS objects do not. Material input changes
  invalidate the task and both phases; appearance changes do not. Historical
  locked scenes restore as legacy provisional/unreviewed and require review.
- **Visualization fixed at software level:** CBCT rendering is explicit,
  singleton, display-only, geometry-preserving, and independently adjustable
  with masks/robot/goal/guides/mount/trajectory/proxy. Placement Review frames
  their visible union. The curved forehead proxy never appears automatically
  and is excluded from collision/registration evidence.
- **Motion policy fixed at software level:** ordinary/home commands remain
  strict; phase messages are fingerprinted; only selected burr-target contact
  inside the approved corridor can be accepted for terminal/drilling preview.
  Wrong-task, non-target, other-link, self-collision, lateral escape, overshoot,
  and joint-bound cases fail closed. Execute is hidden/disabled.
- **Verified:** 95 host tests; focused native Slicer renderer/base/home/proxy
  MRB round trip; the supplied Step 6 restore at `1e-6`; all three operator
  package fixtures at `1e-6`; isolated ROS/MoveIt strict smoke; and phase-guard
  acceptance/rejection smoke. See today's logbook for exact commands/results.
- **Active operator acceptance:** repeat the complete sequence in the visible
  workstation GUI using a newly regenerated Current Step 4C/5C case. The two
  supplied MRBs truthfully remain stale because their support draft changed.
- **Blocked future capability:** physical actuator homing, calibrated TCP,
  registered base lock, controller ownership, force/stop behavior, hardware
  motion, powered drilling, and Execute require hardware plus a verified safety
  procedure and are not authorized.

## Draft oral-workspace bounds from CBCT — active investigation 2026-08-24

- **Feasibility conclusion:** the current 0.5 mm Slicer dental sample contains
  a visible external cheek/skin-to-air boundary and can support an experimental
  outer facial envelope. It does not expose a continuous inner-cheek boundary:
  the mouth is substantially closed and buccal mucosa is apposed to adjacent
  soft tissue, gingiva, and teeth.
- **Required representation correction:** prototype a confidence-labelled
  `ObservedOralAir` segment rather than claiming an `InnerCheek` anatomical
  layer. Only air-contact mucosal surfaces are observed. Treat all unobserved
  material inside a bounded mouth ROI as occupied/unknown for conservative
  planning; retain teeth/jaw segmentations as separate rigid obstacles.
- **Planned non-destructive trial:** use core Slicer Segment Editor threshold,
  Grow from Seeds, Islands, Scissors/virtual cap planes, and light smoothing;
  create closed-surface previews; sweep acquisition-specific thresholds and
  report surface/volume sensitivity. Do not reuse CT HU constants blindly for
  CBCT grey values.
- **Acceptance required before integration:** open-mouth acquisition or phantom
  with cheeks/lips/forehead inside the FOV; slice-by-slice review; no unintended
  contact with image bounds; explicit mouth-entry/posterior caps; repeatable
  threshold sensitivity; and comparison against an optical/intraoral surface,
  known phantom geometry, or another suitable reference. This remains design
  context, not a clinical or safety-certified workspace boundary.

## Step 5B unified-template panel — 2026-08-24

- **Fixed and focused Slicer-native verified:** Step 5B now presents approved
  inputs/lineage, all nine dimensions, collapsed Advanced intermediate
  processing, unified result, and one bottom Build/Inspect/Delete footer in
  that order. No generation parameter appears after the result or actions.
- **Fixed:** Build/Update remains a build action. A Current final disables and
  labels it as Current; inspection remains on three separate display-only
  buttons. Existing dependency-aware preflight, stale propagation, geometry
  caching, and Step 5C verification/export behavior are unchanged.
- **Verification:** the focused embedded-Slicer layout, navigation, and
  complete-build caching tests printed
  `DENTOBOT_UNIFIED_TEMPLATE_REGRESSION_PASS`; the full host suite returned
  `101 passed`. The representative saved `test1_5b.mrb` loaded and screenshots
  confirmed the visible order and the bottom footer. Its final model correctly
  reports a missing Step 4C docking reference and blocks rebuilding.
- **Active acceptance:** reload the live module and inspect the new Step 5B
  panel at the normal workstation width; use a newly regenerated Current
  Step 4C package to exercise Build/Update, each display-only inspection mode,
  stale-on-dimension-change behavior, Step 5C verification, and MRB reopen.

## View chooser and grouped anatomy — 2026-08-24

- **Fixed and focused Slicer-native verified:** both Legacy and New GUI now
  expose one shared **Views** palette. New GUI has a persistent Views button;
  opening it always lands on Elements rather than an old Display-tab choice.
- **Fixed:** every internal stage 0–10 has an explicit recommended category
  set and concise description. Upper, lower, and all permanent teeth can be
  isolated in 2D, 3D, or both with one click and automatic world-RAS framing.
- **Fixed:** the Advanced inventory groups anatomy and workflow objects rather
  than expanding every segmentation segment into the routine flat list.
- **Fixed:** refreshing Views no longer calls Slicer's volume-render creation.
  Existing renderers are labelled **not a mask**, excluded from recommended
  views, and hidden by other isolation presets unless explicitly selected.
- **Verification:** 80 current host tests passed in the final task-local run; focused
  Slicer mask/palette tests printed `DENTOBOT_GROUPED_VIEWS_PASS`; the visible
  application-shell smoke printed `DENTOBOT_APPLICATION_SHELL_PASS` and
  confirmed the shared Views button. The palette screenshot was visually
  inspected. These use synthetic labels/geometry and Xvfb, not representative
  dental anatomy or clinician acceptance.
- **Active acceptance:** after module reload, open the real segmentation in a
  normal-window session and confirm its imported segment names contain valid
  FDI suffixes; exercise upper/lower/all in each dimension, every stage's
  recommendation, Advanced restore, MRB save/reopen, and light/dark
  readability. A segment without recognized permanent FDI metadata correctly
  remains outside the jaw shortcut and must be fixed at the metadata/import
  boundary rather than guessed from geometry.

## DENTO-NOTE dispositions — 2026-08-22

- **Fixed and Slicer-native verified:** reordered support selection/full draft
  to Step 4B, moved docking to Step 4C, and made the dock schema require and
  record current support anatomy while retaining all same-jaw obstacles.
- **Superseded on 2026-08-24:** replaced the stage-limited Elements
  list with an every-stage, scene-wide inventory. Every segmentation segment
  is individually toggleable, all user-facing displayable nodes are listed,
  and scalar volumes expose separate 3D volume-rendering toggles for CBCT/robot
  comparison. The every-stage requirement remains; the flat per-segment list
  and automatic volume-render creation were replaced by grouped Views because
  they were confusing and mutated scene display state during inventory.
- **Remaining acceptance:** repeat the revised ordering and viewer interaction
  in a normal graphical session on representative saved cases; synthetic and
  Xvfb verification is not dentist, anatomy, mechanical, or clinical
  validation.

## DENTOBOT case-package V1 — 2026-08-24

- **Completed and Slicer-native verified:** added Step 0 `.dentocase` save/open
  around a sanitized authoritative MRB; canonical manifest and SHA-256
  inventory; workflow-lineage and world-RAS/mm validation; portable
  URDF/SRDF/xacro/YAML/mesh fingerprint; ROS-runtime exclusion; preflight,
  recovery snapshot, clear load, post-load validation, and rollback.
- **Verified samples:** `test1_5C_FD14.mrb` and `test1_6_FD14.mrb` completed
  package round trips without restoring a ROS robot or active flag and without
  changing trajectory, model, volume, segmentation, or base-transform
  measurements beyond `1e-6`.
- **Correct fail-closed result:** both supplied samples report Step 4C docking
  as Stale/Draft and Step 5C template as Stale/NotVerified because the Step 4B
  support-anatomy draft changed. Regenerate and confirm Step 4C, then
  regenerate/verify Step 5C, before using either case in Step 6 or treating it
  as a current Step 5C package.
- **Active acceptance:** exercise both new buttons in a normal graphical
  Slicer session, inspect the status label, explicitly connect the external
  stack only after Step 6 import, and save/reopen a newly regenerated current
  package.
- **Backlog:** add a read-only/offline migrator for legacy MRML/MRB archives
  containing serialized SlicerROS2 objects (including the historical
  `step 6-1/2026-08-21-Scene.mrml`), define future schema migration policy, and
  decide whether an optional robot-resource snapshot is needed in addition to
  the current portable fingerprint. Do not load a contaminated legacy scene
  into a live ROS-enabled process as the migration mechanism.

## Step 4B support ownership / Step 5A UI — 2026-08-24

- **Fixed and Slicer-native verified:** the removed internal support checklist
  is now permanently hidden instead of being re-shown as an unmanaged widget
  over the visual arch. The Step 4B arch is a full-width bounded card, and the
  former list/dropdown overlap path is gone.
- **Fixed and Slicer-native verified:** creating/updating the Step 4B support
  draft locks tooth membership persistently. Explicit revision unlocks it and
  marks Step 4C plus all Step 5 children stale; rebuilding locks it again.
  The model provenance can restore a missing support-ID parameter only for a
  Current, locked, source/target-matching package.
- **Fixed and Slicer-native verified:** Step 5A now shows only a read-only
  target/support/draft/state summary and a **Return to Step 4B** action. It no
  longer exposes the arch editor or raw Step 4B draft selector.
- **Verification:** `100 passed` in the reconciled host suite; focused real-Slicer widget,
  layout, lock/provenance, and MRB save/clear/reload tests printed explicit
  PASS markers. No ROS stack or robot motion was used.
- **Active acceptance:** in a freshly launched normal Slicer window, confirm
  the Step 4B card has no overlap at the normal panel width, create/lock a
  representative support package, inspect the read-only Step 5A card, use the
  return/revise path, and confirm Step 4C/5A descendants visibly become stale.

## Active

### PoC closure work order — highest priority

1. **Freeze the procedure boundary.** With the clinical team, write one
   sentence defining the exact autonomous/bounded drilling task and explicitly
   list out-of-scope work, the clinician approval point, re-plan/re-register/
   abandon triggers, permitted phantom/patient motion, and the failure-safe
   state. Do not let “root-canal automation” stand in for a testable use case.
2. **Close Template V0 clinical parameters.** Decide or explicitly defer the
   support/retention surfaces, excluded surfaces, insertion direction,
   acceptable undercut engagement, fit clearance, wall thickness, crown
   coverage, support-tooth count, gingival/cervical margin, bur/channel and
   sleeve/docking role, acceptable rocking/gap, repeated seating count, and
   print/material/process assumptions. Mark every current UI dimension as a
   research default until evidence supports it.
3. **Run one representative end-to-end case.** Use reviewed anatomy and go
   through trajectory review, Step 4B support selection/full draft, Step 4C
   support-aware docks, Step 5A visible support selection, undercut-aware
   shell, unified fusion, Step 5C verification, MRB save/reopen,
   stale/backtracking behavior, and one STL. Label evidence as representative
   anatomy only after this run is observed and recorded.
4. **Print and seat one Template V0.** Record manufacturing settings; test
   terminal seating, removal, rocking, repeat pose over repeated cycles,
   visible flex under expected loads, sleeve/dock rigidity, and physical versus
   planned dimensions. A successful STL or watertight mesh does not close this
   task.
5. **Formalize registration.** Draw the complete RAS → tooth/template →
   physical dock → robot base → end-effector → bur frame graph, define every
   transform source and invalidation event, choose the first PoC registration
   method, build a rigid target-point phantom, and measure target registration
   error over repeated registration, reseating, and redocking.
6. **Create the total-system error budget.** Track image geometry,
   segmentation, planning, manufacturing, seating, docking, registration,
   robot kinematics, and TCP/tool calibration separately in millimetres and/or
   degrees at the target. Replace assumptions with mean/standard deviation/
   worst-case measurements and identify the dominant contributor.
7. **Keep parallel hardware lanes explicit.** Define head-mounted and
   tooth-mounted robot DOF, load path, actuation, workspace, packaging,
   emergency removal, tool-axis/TCP calibration, independent depth limiting,
   safe-stop behavior, and a bounded pressure/acoustic sensing experiment.
   No powered robot motion or drilling is authorized by this task list.
   The host Arduino pressure-monitor GUI now launches from Cursor with
   `/home/light-tarun/pressure-env` and has a live `/dev/ttyACM0` serial path;
   keep using it as sensing-bench evidence only.
8. **Build one weekly demonstration script after the boundary is frozen.** It
   must state the case, evidence level, exact expected result, failure response,
   and artifacts retained. Stop accepting “it worked once” as sufficient for
   critical geometry, persistence, registration, or robot claims.

### Required deep dives on implemented software

- **Segmentation/display:** clinician comparison of native masks versus the
  optional smooth closed-surface preview; source-CBCT quality, artifact, and
  segmentation uncertainty protocol; corrected-mask metric policy.
- **Trajectory planning:** clinical Entry/Target/no-go definitions, bur/depth
  assumptions, oblique-MPR approval needs, assisted-versus-corrected acceptance,
  and repeated placement error on representative teeth.
- **Template geometry:** CBCT-only contact-surface validity, boundary and
  gingival-margin semantics, removable undercut engagement, clearance/wall
  selection, terminal support/latch behavior, channel preservation, and
  physical fit after manufacturing.
- **Docking/rails:** registration-landmark versus load-bearing roles, final
  mating profile, depth/diameter/tolerances, material/load path/deflection,
  removal/redocking repeatability, and the unresolved two-non-parallel-
  trajectory versus one robot-Z-axis problem.
- **Persistence/invalidation:** reopen representative legacy/current scenes,
  switch same-tooth trajectories, edit/delete upstream inputs, and prove that
  only reference-linked descendants are purged or marked Stale.
- **Final verification:** distinguish computational topology from anatomical
  collision, clinical fit, manufacturing accuracy, material strength,
  registration, and robot safety; convert warnings into measured gates only
  when evidence exists.

### Robot description integration — Step 6 slice checklist (2026-08-21)

Branch `cursor/step6-runtime-case-limits-06d8`. See `docs/logbook/2026-08-21.md`
for algorithm detail and fix-vs-replace matrix.

| Slice | Status | Verification |
|-------|--------|--------------|
| MRML placement + open-mouth phantom | Done | Synthetic 2026-08-17 |
| 6.0 import + case framing | Done | pytest 2026-08-19; GUI pending |
| 6.1 SlicerROS2 bridge + Connect fixes | Done (code) | Container pytest 2026-08-19; **GUI Connect pending** |
| 6.2 merged min/value/max limits | Done | pytest 2026-08-19; GUI pending |
| 6.3 plan/preview (SciPy IK + AABB gates) | Done | pytest 2026-08-18/19; GUI pending |
| Preview → `/joint_states` when ROS active | Partial | Fix after Connect GUI pass |
| Bur-axis alignment, reviewed collision meshes | Not started | Backlog |
| MoveIt / hardware | Not started | Unauthorized |

### Robot description integration — active follow-up

- **Step 6 Connect joint-state stack timeout (2026-08-19):** Connect started
  the description launch, then failed after 8 s because
  `/dentobot_slicer_joint_state_publisher` never appeared. Retry then showed
  “RSP is running without the Slicer publisher” from a stale 1.5 s node-list
  cache and from the in-memory module not yet reloaded. Reload the DENTOBOT
  extension, dismiss the dialog, and press Connect again. Both description
  nodes plus `/slicer` are already running.
- **Step 6.0 import frames the case (2026-08-19):** Import Planning Package
  now sets the CBCT as slice background and frames case RAS bounds. Reload
  the DENTOBOT extension and import a completed Steps 0–5 scene. Host and
  container pytest recorded; the Slicer widget test is not executed until
  the graphical session reloads the module.
- **Step 6.2 merged min/value/max rows (2026-08-19):** one row per joint.
  Changing min/max updates the value range. Reload the DENTOBOT extension.
- **Step 6 Plan/Preview require `/slicer` (2026-08-19):** when the ROS robot
  is connected, Plan and Preview re-check `/slicer` and the description
  stack with the sanitized ros2 CLI. Reload the extension before using those
  buttons.
- **Step 6 Connect ros2 CLI from Slicer (2026-08-19):** after the module-import
  fix, Connect failed with “ros2 CLI is not available in this Slicer process.”
  Slicer’s `PYTHONHOME` makes `/usr/bin/python3 ros2` load Slicer stdlib and
  fail `rclpy`. The bridge now unsets that isolation and sources Jazzy plus
  the workspace overlay before every CLI call. Reload the DENTOBOT extension
  and press Connect again. Container pytest covers the PYTHONHOME case.
- **Step 6 Connect requires SlicerROS2 (2026-08-19):** **Start Stack & Connect
  Motion Control** failed with “The ROS2 Slicer module is not available.”
  The bridge looked up a global `slicer` without importing it and treated the
  `NameError` as a missing ROS2 module. It now imports `slicer` at the call
  site, can register installed SlicerROS2 paths, and offers the MRML robot
  fallback. The Ubuntu launcher merges DENTO Workflow into
  `SLICER_ROS2_MODULE_PATHS`. **Reload the DENTOBOT extension** in the current
  SlicerROS2 window (the live process already has SlicerROS2 module paths).
  If this window is host Slicer, close it and run
  `./scripts/launch-dentoworkflow.bash`. Interactive Connect verification
  pending after reload.
- **Step 6 gated sequence + Elements (2026-08-19):** panel order is 6.0 scene
  (case XOR phantom) → 6.1 ROS load/place/lock → 6.2 limits → 6.3 plan.
  Elements has a Step 6 recommended view. Reload the DENTOBOT extension.
  Interactive verification pending in the physical Intel graphical session.
- **Step 6 planning sub-workflow implemented (2026-08-18):** sections **6.0–6.3**
  in DENTOWorkflow — one-click planning-package import, base-mount lock,
  user-defined task joint limits, and simulated trajectory motion planning with
  coarse AABB self-collision and subsampled environment clearance (segmentation
  anatomy, template, docks). Reload the DENTOBOT extension and verify the full
  sequence in the physical Intel graphical session after completing Steps 0–5
  on a representative case. Preview is MRML-only; MoveIt and hardware motion
  remain unauthorized.
- **Step 6 SlicerROS2 bridge implemented (2026-08-18):** `DENTOROS2Bridge.py`,
  Step 6 connect/disconnect UI, `launch-dentobot-description-for-slicer.bash`,
  and `joint_state_mode:=slicer` so Motion Control sliders stream simulated
  `/joint_states`. Reload the DENTOBOT extension and verify **Start Stack &
  Connect Motion Control** in the physical Intel graphical session. Stop any
  existing neutral/manual description launch first.
- Manual articulation is synthetically verified for all six joints: the
  package-owned GUI publishes one joint vector, every independent runtime
  perturbation preserved upstream frames and moved the correct child/tool
  chain, and neutral plus articulated meshes loaded in RViz without resource
  errors. Repeat this in the physical Intel graphical session, moving one
  joint at a time, and confirm handedness, direction, assembly alignment,
  scale against at least one measured dimension, limits, and the neutral
  configuration; retain screenshots only if they contain no sensitive data.
- **2026-08-18:** Step 6 **Start Stack & Connect Motion Control** bridges
  `dentobot_description` into SlicerROS2 Motion Control (joint streaming, no
  MoveIt). Sliders publish simulated `/joint_states` through
  `dentobot_slicer_joint_state_publisher`. Verify interactively in the
  SlicerROS2 container after reloading the DENTOBOT extension.
- Restart the currently open manual launch so it reloads the new draft zero,
  then confirm the photographed configuration appears with all six controls at
  zero, link-1's mounting face is parallel to the RViz grid, the robot remains
  on the intended side of that plane, and positive J4 travel moves in the
  intended opposite/negative-base-X direction.
- Use the new 5 mm non-adjacent link-AABB warnings and displayed CAD burr
  origin only for draft manual workspace exploration. Record joint vectors and
  burr coordinates at useful mouth-workspace poses and obvious flexibility
  limits. The neutral AABB result currently warns on `link-3`/`link-5` and
  `link-3`/spindle; determine later with reviewed geometry whether these are
  real contacts or conservative box overlap.
- Repeat the open-mouth/robot trial in the physical Intel graphical session.
  Replace the synthetic four jaw landmarks and provisional forehead plane with
  deliberate researcher placements, exercise native base/plane handles,
  plane-normal flipping, every local-axis button, opt-in keyboard gating, and
  all six joint controls, then save useful base matrices and joint vectors.
  Treat these as disposable design observations, not registration, calibrated
  TCP, representative anatomy, or patient/cable/mount/swept-path clearance.
- Obtain engineering authority for joint zero definitions, positive axes,
  mechanical ranges, velocity/effort units and limits, masses, centers of
  mass, inertias, and the intended robot base/end-effector/spindle/bur-tip/TCP
  frames. The current CAD-export values remain unverified inputs.
- Replace visual-mesh collision reuse with reviewed simplified conservative
  collision geometry; define self-collision pairs and test representative
  configurations before MoveIt or motion-simulation claims.
- Add explicit docking, physical-template, robot-base, end-effector, and
  calibrated bur-tip frames only after the frame graph and measurement source
  for every edge are agreed. Do not infer physical registration from the
  current `base_link -> burr` CAD transform.
- Define the transport-neutral `RobotAdapter`, simulator state/fault contract,
  controller/safety ownership, and ROS/MoveIt/vendor decision before adding
  command topics or `ros2_control`. Powered motion remains unauthorized.

### Clinical visualization acceptance

- Live-test Step 3's authoritative-default native mask and optional derived
  smooth preview on representative CBCT in the physical Intel-`iris` session.
  Compare the same tooth boundaries at high zoom and in axial, coronal,
  sagittal, and trajectory-oblique slices. Confirm Segment Editor remains in
  the native binary-mask view and no mask geometry, segment count, or source
  representation changes.
- Exercise optional CBCT automatic/manual window-level, standard/inverted
  grayscale, viewport interpolation, native slice-view mouse adjustment, and
  restore-to-loaded-state. Confirm DENTOWorkflow stays synchronized and voxel
  checksums are unchanged. Do not introduce or request sharpening, denoising,
  super-resolution, histogram equalization, or AI enhancement in this path.
- Have the clinician assess contour readability and whether outline/fill,
  opacity, window/level, and anatomy-specific presets need another pass.
  Separately measure interaction FPS. Do not interpret smoother display as
  improved acquisition resolution, segmentation accuracy, registration, or
  drill-planning accuracy.
- Establish a quantitative imaging-quality protocol: document acquisition
  voxel size/reconstruction kernel, artifacts and partial volume, segmentation
  ground truth/uncertainty, and trajectory/registration error budgets. Display
  interpolation alone cannot close these clinical-accuracy gaps.

### Immediate Step 4/5 workload — ordered

1. Live-test the compact eleven-entry DENTOWorkflow navigator in physical Slicer
   session at the normal narrow module-panel width. The final **6 · Robot
   Placement** entry is a simulation experiment and does not establish
   registration.
   Confirm exactly one active
   stage is visible and expanded, Previous/Next/direct selection stay
   synchronized, the task scroll starts at the selected stage, the compact
   recommendation dot remains understandable by tooltip, and CBCT metadata is
   present only inside CBCT Imaging. Exercise the nonmodal View Controls
   palette: close/reopen it, move/resize it, leave and re-enter the module, and
   restart Slicer to confirm its `QSettings` visibility/geometry restore without
   becoming MRB state. Confirm Views is available at every stage, opens on
   Elements in both GUIs, applies each step recommendation, and isolates
   upper/lower/all FDI-labelled teeth in 2D, 3D, and both. Confirm Advanced
   groups other masks/workflow objects and labels only already-existing volume
   renderers as **not a mask**. Check dark/light theme readability. Also
   confirm Step 4A presents manual placement and the optional
   assisted initializer together, Step 4B owns support selection/full draft,
   and Step 4C is the next docking/guide stage.
2. Live-test the optional assisted Step 4A trajectory initializer on
   representative one-root and two-root teeth. Confirm crown Entry placement, target-only mask
   isolation, forced target-bounds visibility, exact display restoration,
   root-branch rejection on ambiguous/fused anatomy, correct Entry↔Target
   pairing, manual MPR correction, locking, MRB reload, and downstream repeated
   trajectory selection. Treat every target as a geometric estimate, not a
   canal/apex detection or safe plan.
   Also reopen a representative MRB with two same-tooth trajectories, select
   each selector entry, and confirm the exact line/points, target controls, and
   views change. Verify Complete/Empty labels remain distinct. Exercise Cancel
   and Continue for unlock/edit/clear/delete backtracking, and confirm Continue
   purges only reference-linked Step 4B/4C/5 descendants while retaining the
   other trajectory and authoritative anatomy.
3. Live-test the **Views → Elements** palette across every workflow
   stage. Exercise recommended, target-only, all-trajectories,
   target/support-mask, docks-only, undercut, shell-only, shell-and-guides,
   final-only, all, and manual checkbox selection where available. Confirm
   target bounds and each same-tooth trajectory are independently selectable;
   **Frame Visible** fits the intended combined bounds; and **Restore Previous
   View** exactly restores segmentation/global/per-segment opacity and owned
   object visibility. Confirm Step 6 can show the complete CBCT volume against
   grouped robot/package elements. If an explicit CBCT renderer is needed for
   Step 6 comparison, create it deliberately in Slicer and confirm Advanced
   labels it as rendering, not a mask. Save an MRB while shell-only is active, verify the
   underlying pre-filter display—not the transient isolation—is serialized,
   and confirm the shell-only preset resumes after saving. Confirm colors and
   opacity remain readable in physical-session Intel rendering and after MRB
   reopen; record any remaining role-color collision.
4. Live-test bidirectional 3D/slice spatial reference through Slicer's native
   accurate crosshair path. Enabling the workflow control uses centred slice
   jumps and Shift-hover picking in 3D; disabling/save/exit restores the exact
   previous crosshair state. Confirm 3D→2D and 2D→3D usability, target/support
   frame snapping, and no conflict with Markups placement or oblique MPR.
5. Live-test the corrected Step 4C schema-v4 geometry on representative
   transformed/untransformed anatomy. Confirm each robot-facing dock top lies
   on the fitted target-crown occlusal plane, depth proceeds crown-to-root,
   the crown centroid has no hub/spokes, and automatic yaw screens selected
   Step 4B supports first while retaining every other same-jaw whole-tooth
   surface without using the opposing jaw. Exercise
   slider correction, Draft/Confirmed state, all 13 viewport annotations,
   obstacle-clearance warnings, common/individual depths, MRB reload,
   schema-v3 staleness/regeneration, support-selection invalidation, and
   deliberate tooth/dock and dock/guide collision rejection. Confirm all four
   independent shell attachments avoid
   the protected trajectory-guide envelope and all drill/dock channels remain
   continuous after fusion. Finalize the mechanical rail/attachment profile,
   tolerances, materials, registration versus load-bearing roles, and
   structural limits before fabrication claims.
6. Resolve two-trajectory robot kinematics before claiming Z-only drilling. A
   fixed dock Z axis cannot represent two non-parallel drill axes at once;
   choose per-trajectory reindexing, angular adjustment, parallel-axis
   constraint, or separate docking poses/assemblies, then record every
   trajectory-to-occlusal-frame transform for registration/homing.
7. Live-test the updated trajectory oblique MPR. It now prefers Red, supports
   focused mouse-wheel slider rotation, coalesces rapid changes to about one
   refresh per 16 ms, fits target bounds deterministically, and temporarily
   enables native linear CBCT display interpolation with exact restoration.
   Confirm edge readability without mistaking interpolation for acquired
   detail, correction-plane stability, crosshair compatibility, CPU/iGPU FPS,
   and whether a dedicated layout/view label is still needed. No volume is
   generated per angle.
8. Live-test the implemented Step 5B unified fusion and Step 5C
   PASS/WARNING/FAIL gate on representative anatomy. Confirm the recorded
   complete-build action reuses a Current cached patient shell, rebuilds only
   missing/stale downstream guide/dock fusion, and exposes fit/undercut,
   shell-plus-guides, and unified-only inspection without changing geometry.
   Reopen `SampleStudy1/test1_5a.mrb` with both segmentations present and
   confirm the persisted authoritative segmentation, target, trajectory,
   support nodes, and its explicitly referenced `PreDentalSurgery` source CBCT
   resume without re-selection; deliberately switching the authoritative
   segmentation must instead clear target-specific descendants and use the new
   segmentation's referenced source CBCT. Confirm a node-independent display
   preset survives MRB reload and can be applied without changing masks or
   workflow references. Then confirm the recorded
   shell-contact reinforcement creates one occupied printable volume, every
   trajectory guide hole and four dock bores remain open, stale trajectories
   or source nodes produce FAIL, and only one atomic STL is exported. Complete
   shell/undercut/terminal-latch, dimensional, clinician, and phantom fit
   acceptance already listed below.

- Repeat the interactive rendering acceptance from the physical Ubuntu
  graphical session through GNOME Desktop Sharing/RDP. Confirm Slicer reports
  the Intel `iris` renderer rather than CRD's `llvmpipe`, then measure the
  trajectory MPR and Step 5C interaction FPS. CRD is accepted only for
  functional/visual checks.
- Perform Windows 11 acceptance of the new native-Slicer/WSL2 launcher on a
  Windows workstation: PowerShell `-CheckOnly`, Slicer module discovery,
  backend health, synthetic NIfTI round trip, one cached CUDA segmentation,
  scene save/reload, cancellation, and path-with-spaces coverage. PowerShell
  AST parsing is also pending because `pwsh` is unavailable on the Ubuntu
  workstation. Do not claim Windows runtime verification until this passes.
- Live-test the saved FDI 13–15 case after restarting/reloading DENTO Workflow:
  regenerate the Step 5A preview with the 50 percent terminal-tooth coverage
  default, confirm FDI 13 and 15 retain only their inward portions while target
  FDI 14 remains fully supported, then regenerate undercut blockout and shell.
  Inspect the 1.0 mm interproximal relief against actual contacts and corners.
  Vary both exposed controls and test target-at-terminal edge-molar cases.
  Geometry is a research approximation until phantom seating/removal and
  clinician acceptance establish suitable values.
- Live-test the new semi-automatic Step 5A support-boundary initializer on
  representative premolar/molar, two-root, asymmetric-support, missing-tooth,
  edge-molar, and tilted-arch cases. The implementation uses Entry→Target for
  polarity, a selected-tooth crown-cap PCA fit for initial plane tilt, one
  scalar depth from Entry, VTK surface intersections, and one resampled planar
  outer envelope that initializes the existing editable Markups closed curve.
  Confirm the locked plane and generated boundary remain current after scene
  reload and that depth, tilt-fit percentage, polarity, trajectory, or curve
  edits invalidate every dependent result. Manual curve editing remains the
  correction path. Treat the 3 mm depth and 10 percent crown-cap fit as
  research defaults; they do not detect the gingival margin. Continue to
  evaluate labelled CBCT-only CEJ/alveolar-crest proxies and registered
  intraoral/desktop surface scans before any clinical default is chosen.
- Exercise the implemented verification gate and single
  `FinalPrintableTemplate` output on real anatomy. Review all WARNING items,
  especially anatomy collision/clearance and voxel sampling of the 1 mm dock
  bores; compare exported STL dimensions to the MRML parameters. Do not treat
  computational PASS/WARNING as clinical or mechanical approval. The annular
  trajectory guide and four-dock profile remain provisional and replaceable.
- Live-test the new visible-support workflow on anonymized representative
  anatomy: draw/edit a margin across multiple separate teeth; confirm automatic
  Entry→Target crown/root polarity selects the crown-side candidate despite
  different tooth sizes; exercise the exceptional Reverse polarity button;
  confirm roots/subgingival surfaces are excluded; and verify extra mesh
  islands are reported without inflating the selected-tooth count.
  Generate the pre-undercut patient-contact shell, inspect seating/clearance/
  rims, save/reload, invalidate/regenerate, and cleanly delete descendants. Also verify
  Approach→Seat insertion semantics, retentive-surface preview, blockout
  removability, multi-trajectory selection, docking/reinforcement placement,
  and the one-component unified model against real crown anatomy.
- Live-test the Step 5A boundary-placement focus: only the target and checked
  support-tooth masks should remain visible/opaque while drawing, the curve
  must not snap to an adjacent unselected tooth, and preview generation, save,
  module exit, and scene close must restore the exact previous display.
- On the representative three-tooth case that previously reported 42 invalid
  Hollow edges, regenerate Step 5B and verify the lifted boundary collar joins
  all selected tooth-shell rims, no fitting/contact surface is introduced in
  interdental gaps, the fallback warning identifies the repaired Hollow input,
  and the output remains one connected watertight removable shell.
- Later QoL: replace the primarily axial/single-height support-boundary drawing
  experience with a focused 3D, surface-constrained gingival/cervical margin
  editor. Allow individual control points to move at different insertion-axis
  heights while remaining snapped to selected subject-tooth surfaces; retain
  2D slices as optional verification instead of forcing one horizontal cut.
  Investigate an assisted initial loop, but keep clinician-editable MRML points
  authoritative.

- Live-test Step 4A trajectory-aligned longitudinal oblique MPR: verify the
  selected source CBCT appears in one native slice with Entry→Target vertical,
  the existing line remains overlaid, `-180°..+180°` changes circumferential
  anatomy without moving either point, the slice stays fixed beneath the
  pointer during correction, an in-view point edit preserves the selected
  circumferential plane after release, later slider movement remains
  continuous, vertical/near-vertical paths remain finite, and
  disable/save/module-exit restores the exact prior slice/composite/display
  state. Measure slider and correction FPS.
- Live-test the corrected Step 5C ROI-frame isolation in Slicer: confirm a
  one-up 3D layout, `+X` right/`+Z` up/looking `+Y` at yaw zero, Step 5B ROI
  top/bottom initial viewport fit, usable mouse-wheel zoom under both lock
  states, yaw-plus-zoom orbit, fixed-orientation-plus-zoom mode, free-camera
  mode, and exact restoration of layout, camera, crosshair, visibility, and
  2D verification views. Confirm the simple plane accepts one point/height,
  remains parallel to the ROI top/bottom faces, cannot rotate/scale/translate
  laterally, survives save/reopen with its ROI link, and cuts the requested
  ROI −Z/+Z side. Compare interaction FPS with the superseded multi-view
  camera observer.
- Confirm that both new and reopened Step 4A/5B bounds ROIs remain visible but
  cannot be picked, translated, rotated, or resized from slice or 3D views.
  Static/source assertions cover locked/selectable/handle state; live Slicer
  acceptance is still required.
- Run developer/dentist acceptance of Steps 5B and 5C on representative
  reviewed dental anatomy: trim the Step 5B ROI; confirm raw-shell contact,
  removability, channel alignment, and warnings; exercise both Step 5C plane
  sides and a surface-snapped closed margin; save/reopen the MRB; then
  export/reopen the finalized shell and sleeve STL parts. Synthetic
  Slicer-native coverage has passed; anatomical fit, printability, and
  clinical use have not.
- Define research-team values and acceptance evidence for clearance,
  thickness, drill-channel diameter, sleeve fit/height, gingival clearance,
  material/process constraints, and Entry-on-surface semantics. Current UI
  values are editable research defaults only.

- In the next Slicer session, rerun **Check Linux Backend** and then
  retry the user-selected new-data segmentation. The external CPU backend,
  cached weights, public-fixture inference, `pip check`, and all 13 backend
  tests now pass; acceptance of the asynchronous UI import path on the new
  dataset remains operator-observed work.

- Compare interaction and FPS on the original visualization workload. The
  recreated service has already passed launcher preflight, direct Intel Mesa
  rendering, `i915` render-node use, and nice level 0; only the developer's
  workload-level responsiveness confirmation remains.
- Complete live UI acceptance of safe deletion for Steps 4A, 5A, and 5B. The
  bounded Slicer-native suite now passes selective auxiliary cleanup, retained
  inputs, MRB save/reload, shell-ROI reset, Step 5B-to-5C cascade cleanup, and
  recreation/deletion behavior.
- ~~Implement the closed-loop Step 4A backtracking boundary~~ — completed and
  focused Slicer-native save/reload verified on 2026-08-13. Unlock, interaction
  start, point undo, clear, and delete now issue one stage-level confirmation
  and purge reference-linked Step 4B/4C/5 descendants; target switching purges the
  complete active derived branch. Live legacy-scene acceptance remains above.
- Extend the same explicit impact/confirmation contract to every meaningful
  Step 5A source/ROI edit before considering closed-loop backtracking complete
  across the whole template workflow.
- Complete developer-run Slicer acceptance of Step 4B: select one target and
  any manually chosen number of distinct whole-tooth supports, create/update
  the full support-anatomy draft, save/reopen the scene, and confirm
  persistence and stale-state behavior. Then exercise Step 5A automatic-plane
  and editable-boundary refinement on that current draft.
- Rebuild `Infrastructure/Dockerfile.ubuntu-cpu` cleanly and prove `pip check`,
  all backend tests, Bridge A health, and the Slicer-native test class without
  mutable-container repair.
- Keep local controlled documentation and both existing Google Drive mirrors
  synchronized in place without duplicate files.
- Continue the 3D Slicer medical-imaging workflow; robotics remains
  conceptual/future scope because no robot hardware exists.
- Define the geometry-preserving CBCT/segmentation boundary; the verified
  standard ROS image bridge carries pixels but is not the medical-image
  exchange contract.

## Shelved — remaining cross-stage viewport/2D placement

The accepted Step 4A assistance backlog is complete. Manual placement and the
assisted-root initializer now coexist as optional creation modes in Step 4A.
Step 4B owns support selection/full draft and Step 4C owns docking. The older
dentist-focused 2D plan is retained as cross-stage viewport work and is
sequenced through the ordered viewport tasks above.

- Accepted deferred Step 4A completion backlog:
  - ~~selecting a trajectory after scene reopen restores its target tooth,
    highlight, bounds, and details from persisted MRML associations; editable
    names never determine identity, and invalid associations produce warnings~~
    — implemented and Slicer-native verified on 2026-08-06;
  - ~~keep **Clear Both Points** for clearing Entry/Target while retaining the
    node, and add a confirmed **Delete Trajectory** action that removes only
    the selected trajectory and clears its workflow references~~ — implemented
    with static verification on 2026-08-04 and active-widget Slicer-native
    deletion/persistence verification on 2026-08-07;
  - ~~support multiple trajectories per tooth and show all trajectories in one
    selector, color-grouped by their authoritative target tooth; selecting a
    tooth emphasizes its associated trajectory entries and matching view
    lines while other tooth groups remain visible~~ — implemented and
    Slicer-native verified on 2026-08-07;
  - ~~assign/persist a deterministic, distinguishable tooth-group color only
    after the tooth has at least one trajectory~~ — implemented across the
    Step 4A/5A/5B reference-linked lineage and Slicer-native verified on
    2026-08-07;
  - ~~automatically give new and legacy-default trajectories tooth-specific,
    sequenced, state-bearing labels~~ — implemented as, for example,
    `DENTO FDI 16 - Trajectory 2 [Complete]`, without using the editable name
    as the association key; exact compact `FDIxx-Tnn` formatting is superseded;
  - ~~enforce the Markups-line invariant of at most two control points,
    labelled Entry and Target; zero/one-point trajectories remain incomplete
    drafts~~ — implemented and Slicer-native verified on 2026-08-07.

## Next

### Step 6 — immediate (after extension reload)

1. Reload DENTOBOT extension; stop stale `description.launch.py` if present.
2. **Start Stack & Connect Motion Control** — verify sliders drive live TF.
3. Import Planning Package on representative MRB; Plan/Preview with ROS active.
4. Stream preview waypoints to `/joint_states` (small bridge follow-up).

### PoC and platform (unchanged priority)

- Derive and validate a dental/occlusal orientation frame and dentist-approved
  gingival/cervical margin semantics before offering any automatic trim height
  or 70–80 percent coverage recommendation.
- Define how a deliberately edited expert Dynamic Modeler output may be
  adopted into the DENTOBOT Step 5C provenance contract; arbitrary module
  output is currently available for expert work but is not silently accepted
  for STL export.
- After Steps 5B/5C live acceptance, add the saved planning/geometry report
  and refine hard-invalid versus warning rules from measured research
  evidence.
- Probe Intel NPU visibility only after the clean-image gate; do not claim
  nnU-Net dental inference without a converted and validated model path.
- Reopen the saved Ubuntu MRB in a fresh, cleanly exiting Slicer process and
  verify source reference, 54 segments, closed surfaces, review metadata, and
  CPU provenance.
- Run one bounded Bridge B regression. Run Bridge C again only if a source or
  contract change specifically requires it.
- Run the daily launcher from an Ubuntu desktop terminal and visually confirm
  that Slicer opens directly on DENTO Workflow.
- Define and test the narrow custom SlicerROS2 interface needed by the
  medical-imaging workflow before adding broader ROS scope.
- Repeat geometry validation with a de-identified representative CBCT after
  the DICOM workflow and data-governance procedure are ready.

## Blocked or unresolved

- Observe the safeguarded CRD/container workstation overnight. The 2026-08-14
  synthetic lifecycle check passed. On 2026-08-17 the physical GDM path was
  configured for Xorg and low-swap/bounded-HDD-writeback settings were applied.
  Reboot when local work is saved, leave CRD/Xfce active overnight, and record
  GDM CPU, memory/swap, I/O pressure, CRD availability, and container PIDs the
  next day before closing the stability issue.

- Resolve the Slicer 5.10 aggregate test-runner exit-code discrepancy. After
  isolating every `DENTOWorkflowTest.runTest()` member with a fresh MRML scene,
  all assertions reached the explicit PASS marker with no traceback and no
  leftover process, but the aggregate Slicer wrapper returned 1. The same
  affected Step 5A test and all UI/MRB/Step 5 focused runs return cleanly when
  invoked separately; a trivial Slicer `exit(0)` also returns 0.

- Custom DENTOBOT SlicerROS2 interfaces, real medical-image geometry exchange,
  and transform-semantic interoperability between host Lyrical and container
  Jazzy are unverified.
- The ordinary Compose container has only the minimal Bridge B Conda runtime;
  the full CPU inference environment currently survives only in the local
  checkpoint image until the clean Dockerfile reconstruction passes.
- Real DICOM/CBCT input, UI-driven asynchronous Bridge B/C behavior in the
  ordinary Compose runtime, and anatomical accuracy remain unverified on
  Ubuntu.
- No Ubuntu workflow has yet been verified against robot hardware.
- No robot hardware currently exists in the development environment; robot
  description/TF simulation has begun, but calibrated control and hardware
  integration remain future scope.
- The provenance of existing generated files under `ros2_ws/build` has not been
  established.

## Completed

- Step 6 Connect PATH sanitization on 2026-08-19. Slicer-first PATH made
  `slicer_joint_state_publisher` crash on `import yaml` while C++ RSP stayed
  up (8 s timeout). Bridge now resets PATH; leftover incomplete launch was
  stopped. Host pytest 23 passed / 5 skipped; container
  `test_ros2_bridge.py` + `test_ros2_cli_slicer_env.py` 14 passed. Healthy
  stack verified: both `/dentobot_robot_state_publisher` and
  `/dentobot_slicer_joint_state_publisher` with `/slicer`. Reload the
  extension; hardware motion was not run.

- Step 6.0 case-into-view and 6.2 merged joint-limit UI on 2026-08-19.
  Import frames the case package (not the phantom origin). 6.2 is one
  min/value/max row per joint. Plan/Preview re-check `/slicer` when ROS is
  active. Host pytest: 28 passed, 1 skipped (`scipy` absent). Container
  pytest: 32 passed with live `SlicerApp-real` listing `/slicer`. Interactive
  Connect/Import/limits after extension reload remain operator-run. No
  hardware motion.

- Added a host Record3D / iPhone LiDAR OBJ viewer on 2026-08-18.
  `scripts/view_record3d_scan.py` opens a zip, folder, or single coloured OBJ
  point cloud in a vispy arcball view, with frame scrubbing, RGB/height colour,
  and catalog checks (missing indices, small frames, point count, millimetre
  extent). It reuses `/home/light-tarun/pressure-env` plus vispy 0.16.2. The
  example `data/3dscan_iphone.zip` listed 195 frames, parsed all of them
  (2,940–358,865 points, no empties), and opened a GUI window on `DISPLAY=:0`.
  Coordinates stay Record3D camera metres. This is scan-quality inspection
  only, not Slicer import, registration, or clinical validation.

- Preserved the private CRD/Xfce virtual-desktop workflow while installing the
  2026-08-17 host responsiveness policy. Journal accounting confirmed the GDM
  Wayland greeter had consumed 2d 23h CPU over 3d wall time. The physical GDM
  path is now configured for Xorg; live and persistent kernel settings use
  swappiness 10 with 128 MiB background/512 MiB hard dirty-page thresholds;
  systemd-oomd remains active. The health report verifies these values and
  treats CRD being stopped during an active physical-seat login as expected.
  Reboot activation and overnight acceptance remain active above.

- Added the simulation-only Slicer Step 6 robot-placement slice on 2026-08-14.
  DENTOWorkflow now parses the tracked URDF, loads all seven STLs explicitly as
  raw RAS/CAD geometry, and parents seven link-pose transforms beneath one
  editable robot-base transform. It provides six manual joint controls, an
  editable mount plane, orthonormal snap-to-plane, transform handles, local
  X/Y/Z and Rx/Ry/Rz nudge buttons, and opt-in keyboard shortcuts gated to the
  active Step 6 stage. Two pure geometry tests, focused Slicer logic,
  widget, navigator, and synthetic MRB save/reopen tests passed. This is
  synthetic scene-only evidence,
  not head-mount registration, TCP calibration, collision validation, a ROS
  bridge, IK, controller, or hardware motion.

- Added the disposable Step 6 open-mouth workspace trial on 2026-08-17. It
  loads aligned BodyParts3D neurocranium/maxilla/mandible assets, rotates only
  the mandible about four approximate TMJ/incisor landmarks to an approximately
  40 mm final incisor gap, and displays it beside the manually placeable and
  articulated seven-link robot. Four host tests, focused Slicer logic/widget
  tests, MRB save/reopen, and an inspected Xvfb viewport passed; the graphical
  run reported `40.001 mm`, seven robot models, and three phantom models. This
  is disposable synthetic design evidence, not literal jaw translation,
  clinical jaw mechanics, physical-session ergonomics, reach/collision,
  registration, TCP, controller, hardware, or motion acceptance.

- Refined the disposable Step 6 open-mouth trial on 2026-08-17 evening. Landmark
  placement is progressive one-at-a-time with a separate clear control; only one
  phantom and one robot set are allowed; a workspace transform co-locates phantom
  and robot in the viewport; and the jaw hinge matrix is converted to workspace-
  parent local coordinates before application. Five host pure-geometry tests
  passed; Slicer logic/widget tests were updated for workspace-aligned
  landmarks and post-opening co-location bounds. Interactive extension reload was
  not re-verified in the physical session.

- Added the first simulation-only ROS 2 integration on 2026-08-14. The tracked
  `dentobot_description` package contains the normalized URDF, all seven
  checksum-locked binary STL meshes, neutral/manual/external joint-state
  modes, an RViz configuration, and static integrity tests. The package-owned
  PyQt window controls all six joints in human-readable degrees/millimetres
  while publishing ROS SI units. Jazzy build/test passed; a runtime probe
  independently verified every joint's child/downstream TF behavior and
  upstream invariance, and RViz rendered neutral and articulated models
  without mesh/resource errors before clean shutdown. This is synthetic
  description/forward-kinematics evidence only, not physical calibration,
  collision, IK, Slicer, controller, hardware, or motion evidence.
- Added a draft manual workspace aid on 2026-08-14: seven collision-mesh-derived
  AABBs, a 5 mm advisory for 15 non-adjacent link pairs, green/red RViz
  markers, and base-frame CAD burr-origin coordinates. Static/Jazzy tests and
  an Xvfb RViz subscription/visual check passed. Neutral reports two
  conservative overlaps. This is not exact mesh, swept-volume, head/patient,
  head-mount, or safety collision evidence.
- Rebased the integrated description on 2026-08-14 to the developer's
  photographed design pose: old J1/J3/J5/J6 values
  `25.38/62.46/1.08/-35.28 deg` now read zero, the link-1 mounting face is
  parallel to RViz XY, and positive J4 moves primarily in negative base X.
  Seven direct tests, eight Jazzy-reported tests, an isolated six-joint TF
  probe, zero-state publication, and RViz inspection passed. These are draft
  visualization coordinates, not physical homing/calibration evidence.

- Replaced the oversized fixed workflow chrome on 2026-08-14 with an 81-pixel
  two-row stage/action bar, a true one-visible-stage wizard, CBCT-local volume
  metadata, and one nonmodal Elements/Display palette that reparents the
  existing authoritative widgets. Palette visibility and geometry use
  application `QSettings`, not MRB state. A real Slicer main-window capture at
  a 405-pixel module-panel width showed every fixed action reachable and only
  the Case stage visible. Focused UI, display, MRB, trajectory, and Step 5 tests
  exited cleanly; the isolated aggregate suite reached its explicit assertion
  PASS marker without a traceback. Its wrapper status discrepancy is recorded
  above. Physical-session palette placement/theme/interaction acceptance
  remains active.

- Added and verified Ubuntu workstation containment on 2026-08-14: Docker init
  descendant reaping, a 512-task container ceiling, reduced relative CPU
  weight, OOM preference for preserving the host desktop, a 30-second stop
  grace period, duplicate-live-Slicer launch refusal, exact Xvfb ownership,
  bounded headless phases, and a read-only CRD/RAM/swap/container health
  report. Launcher/backend health and the complete synthetic Bridge B round
  trip passed; post-test state was docker-init PID 1, zero zombies, and no
  remaining Slicer/Xvfb process.

- Fixed the representative Step 5B patient-shell four-edge failure on
  2026-08-13. The defect was one uncapped square where the fitting-surface
  distance band plus voxel closing reached the cropped image maximum; it was
  not a patient-surface or blockout non-manifold junction. Cropped-domain
  padding now includes wall thickness, the estimated half-voxel diagonal,
  morphological reach, and two exterior background samples, with an explicit
  zero-occupied-border invariant before contouring. `SampleStudy1/test1_5a.mrb`
  produced one 61,552-triangle shell with zero invalid edges/border samples,
  and the focused fallback plus full template-pipeline tests passed. Live GUI
  inspection and physical fit/clearance acceptance remain required.
- Fixed the saved-scene Step 5A/5B handoff on 2026-08-13. Persistent-header
  reparenting no longer leaves qMRML node selectors detached from the active
  scene, and non-geometric Markups/load-time parameter events no longer mark
  unchanged support or docking geometry stale. The representative
  `SampleStudy1/test1_5a.mrb` now restores a Current visible-support source,
  Current Draft docking assembly, its derived insertion-direction node, and an
  enabled undercut-analysis action. True trajectory geometry edits still mark
  docking descendants stale; focused widget and full template-pipeline tests
  passed.
- Corrected fresh-module workflow navigation on 2026-08-13. A brand-new empty
  scene now initializes on **Case** rather than skipping directly to **1 · CBCT
  Imaging**. Entering a de-identified case label makes Imaging the next
  recommendation without moving the operator automatically. Python/UI/static
  gates and the focused Slicer-native navigation widget test passed.
- Created `DENTOBOT_Daily_Compass.docx` on 2026-08-13 as the editable personal
  operating workbook for daily outcomes, capture, clinical decisions,
  evidence levels, PoC priorities, parallel lanes, Template V0 physical tests,
  registration/error budget, weekly clarity, and Codex handoff. The final
  Letter-format DOCX rendered to 11 pages and every page was visually checked.
  It remains working memory; controlled Markdown files remain authoritative.
- Unified manual and assisted trajectory creation under one Step 4A navigation
  stage on 2026-08-13. The navigator now has nine stages, assisted entry nodes
  use Step 4A tags, and the independent four-dock assembly is Step 4B. Both
  creation paths retain the same Markups-line/MRML reference contract.
- Implemented and focused Slicer-native verified the global Step 4A–5C
  viewport element selector on 2026-08-13. Stage-aware presets and live
  checkboxes cover masks, bounds, trajectories, assisted entries, support
  geometry, undercut/blockout, shell, docks/fusion auxiliaries, and final
  template. Combined world-RAS framing and exact prior-display restore pass;
  MRB save callbacks serialize the underlying display and resume the transient
  preset afterward. The duplicate legacy Step 5B visibility panel is hidden.
  Physical-session and representative-scene acceptance remain active above.

- Implemented and Slicer-native verified the corrected Step 4B → 5B → 5C
  schema-v3 vertical slice through 2026-08-13. Step 4B creates a world-RAS fitted
  target-crown occlusal frame, locked reference plane, and four independent
  hollow docks with their robot-facing openings on that plane, configurable
  radial offset, crown-to-root shared/individual depths, no crown hub/spokes,
  and explicit repeated trajectory provenance. A cached deterministic yaw
  sweep screens all other same-jaw whole-tooth surfaces; manual yaw correction,
  13 referenced dimension annotations, Draft/Confirmed state, MRB persistence,
  and the Step 5B confirmation gate have focused synthetic coverage. Step 5B keeps trajectory drill
  guides separate, creates four dock-to-shell attachments, protects the guide
  envelope, and combines the parts into one occupied watertight printable
  volume. Step 5C reports persisted
  PASS/WARNING/FAIL checks, blocks FAIL, re-verifies on export, and writes one
  atomic binary `DENTO_Final_Printable_Template.stl`. The transformed synthetic
  test passed generation, one-voxel artifact cleanup, verification, export,
  MRB reload, changed-trajectory failure, restored verification, and deletion.
  Mechanical/clinical/phantom acceptance remains active.
- Verified containerized DENTO Workflow display through Chrome Remote Desktop
  on 2026-08-11. Starting the normal top-level launcher from the active CRD
  terminal inherited `DISPLAY=:20.0`, recreated/reconfigured the Compose
  service as needed, granted temporary scoped X11 access, verified the backend,
  and opened Slicer in DENTO Workflow. The CRD session used `llvmpipe`, so this
  closes remote functional display only—not GPU-performance acceptance.
- Added the semi-automatic Step 5A support-boundary initializer on 2026-08-11.
  A locked Markups plane uses trajectory-derived crown/root polarity, a robust
  selected-tooth crown-cap tilt estimate, and one configurable insertion-axis
  depth. It cuts every selected tooth, joins the disconnected planar contours
  into one resampled editable boundary, and runs the existing visible-support
  extraction. The real `SampleStudy1/test1_5a.mrb` case intersected all three
  selected teeth and generated an 83-point boundary plus a 1,460-point/
  2,566-cell preview with zero omissions. Focused review-gate, draft-model,
  manual-boundary, automatic-plane, stale-state, deletion, and MRB reload
  regressions passed. Terminal support clipping now uses each end tooth's
  adjacent selected tooth in the insertion frame rather than a crown/root
  split.
- Added the shared Windows/Linux backend runtime contract on 2026-08-11.
  Linux now exports explicit `local`/`cpu` settings through Compose; Windows
  has a tracked data-only configuration example and PowerShell launcher for
  native Slicer plus WSL2 inference. Added a Slicer-independent platform
  helper and five passing ordinary-Python tests. Core Windows planning does
  not require Docker; current SlicerROS2 remains assigned to the verified
  Linux profile.
- Restored the active Ubuntu CPU TotalSegmentator backend on 2026-08-11. The
  external Conda environment now has the complete pinned stack, including the
  matched official CPU `torch==2.10.0+cpu` and
  `torchvision==0.25.0+cpu` wheels. Compose/launcher persistence now supplies
  and verifies the cache-only TotalSegmentator home. A bundled public CBCT run
  passed geometry and label validation in 329.216 seconds with 54 detected
  labels and 579,353 foreground voxels; `pip check`, CPU health, and 13 backend
  tests passed in the application container.

- Added insertion-frame undercut/removability processing on 2026-08-11. The
  blockout now uses substantive same-arch authoritative tooth surfaces as
  collision-only anatomy, performs configurable transverse interproximal
  relief, and persists those parameters and source IDs. Added configurable
  inward partial coverage of non-target terminal support teeth, protected
  target-terminal edge cases, and applied the same world-RAS clip planes after
  bridge union/closing. The saved Scene_5b resolved from six shell components
  without relief to one watertight 31,240-triangle component with relief and
  terminal clipping; focused math, shell fallback, full MRML save/reload,
  docking/fusion, XML, AST, and static checks passed.
- Replaced global Smaller/Larger support-side selection on 2026-08-11 with
  trajectory-directed per-tooth candidate scoring and an optional single
  polarity reversal. The preview now counts authoritative tooth segment IDs,
  reports extra connected islands separately, references the source trajectory,
  and creates a locked derived insertion line. Focused Slicer tests passed a
  mixed-size Smaller/Larger crown case, three teeth containing six raw islands,
  polarity reversal, downstream shell/fusion, and MRB reference persistence.

- Corrected the Step 5A visible-support preview contract on 2026-08-11. A
  single loop may now yield valid patches from the disconnected teeth it
  actually addresses without one untouched/unmappable draft tooth aborting the
  entire preview. The UI explains placement/finish behavior and reports
  included versus source tooth surfaces. The focused Slicer-native three-tooth
  regression passed preview, downstream shell/fusion, MRB reload, and cleanup.

- Completed the 2026-08-10 meeting checkpoint for the renovated template
  vertical slice: per-tooth visible crown/support ROI, explicit world-RAS
  insertion direction, normal-based undercut preview, directional blockout,
  undercut-aware Dynamic Modeler/voxel patient shell, repeated MRML references
  for multiple approved trajectories, provisional annular docking clearance
  and reinforcement, and one connected watertight unified model. The focused
  transformed two-tooth/two-trajectory Slicer test passed generation, topology,
  MRB reload, reference persistence, and clean subtree deletion. The unified
  output remains intentionally `NotVerified` and non-exportable.

- Added the source implementation and focused Slicer-native math coverage for
  Step 4A longitudinal trajectory MPR. It reuses the existing trajectory and
  referenced CBCT, constructs an orthonormal singularity-safe frame, updates
  native `SliceToRAS` only, coalesces interactive events, projects the same
  line as an overlay, freezes the slice during point drags, transports the
  selected plane continuously after correction, and restores transient
  presentation state. Python/UI/repository static gates passed on 2026-08-10;
  live acceptance remains active.
- Replaced the Step 5C fixed-anterior multi-view isolation source behavior
  with an ROI-aligned, one-up 3D yaw workspace; added separate non-yaw/yaw
  locks with zoom retained, full presentation-state restoration, and an
  ROI-Z-height-only simple plane; separated isolation from markup placement;
  and made Step 4A/5B ROIs immutable in views. Python/UI/repository static
  checks passed on 2026-08-10; live Slicer acceptance remains active.
- Published the accumulated Ubuntu workflow checkpoint to the existing remote
  `codex/ubuntu-migration` branch without force as feature commit `56eaf34`.
  The previously recorded Git authentication blocker no longer prevents a
  normal branch push; no pull request was requested in this batch.
- Added and Slicer-native synthetically verified Step 5C dentist-directed shell
  finalization. It preserves the Step 5B raw shell, supports capped Dynamic
  Modeler Plane Cut positive/negative regions and surface-snapped closed-curve
  inside/outside trimming, rejects non-watertight output, persists edit/source
  provenance and stale state, cleanly deletes its owned subtree, and owns the
  only shell-plus-sleeve STL export action. The isolated anterior world-RAS
  view, lineage controls, MRB persistence, and Step 5B cascade were also
  exercised; representative anatomy acceptance remains active.
- Completed and Slicer-native verified the remaining Step 4A assistance
  backlog: multiple trajectories remain in one selector; deterministic
  target-tooth colors persist through Step 4A/4B/5A/5B descendants; selecting a
  tooth emphasizes its group without hiding others or retargeting a valid
  line; target bounds are unique per segmentation/tooth; and the two-point
  Entry/Target invariant is enforced. Step 5A/5B now make the inherited color
  explicit with lineage badges, selector swatches, and Step 5B visibility
  stripes. Active-widget deletion tests also close the selector
  auto-substitution race by clearing workflow references before MRML node
  removal.
- Fixed and Slicer-native verified the Step 5B shell-ROI cross-role defect.
  The selector now exposes only Step 5B-owned ROIs, geometry/reset/deletion
  reject Step 4A bounds and wrong-source ROIs, legacy contaminated Step 4A
  bounds are repaired in place without duplication, and parameter refresh is
  non-reentrant. The supplied `2026-07-23-Scene_5a.mrb` passed a read-only
  compatibility load with no recursion or remaining cross-role ROI.
- Added and Slicer-native verified Step 5B Scene visibility controls for the
  selected Step 4A target box/trajectory, Step 4B support draft, Step 5A
  visible support surface, and Step 5B
  ROI/shell/sleeve. Hidden state survives MRB save/reopen and regeneration.
  Added role-driven `[Step 4A]`, `[Step 5A]`, and `[Step 5B]` scene-name tags
  without using names for ownership or identity.
- Installed the pinned pytest 8.4.2 test dependency in the dedicated external
  Conda backend, passed `pip check`, and ran all 13 inference tests without
  modifying Slicer's embedded Python.
- Centralized machine configuration in an untracked `.dentobot.env`; made the
  launcher export backend, environment, rendering, artifact, and workspace
  paths to Compose and DENTO Workflow; and removed production/test reliance on
  repeated host interpreter paths.
- Added automatic launcher configuration and clear local run-record guidance
  to DENTO Workflow while retaining an explicit advanced manual override and
  portable MRB state.
- Added the Git-tracked `Workspace/` layer for top-level Compose, scripts,
  active Ubuntu documentation, and agent instructions. Preserved the original
  top-level paths as relative symlinks and added a safe bootstrap plus Git
  helper.

- Recorded the initial Ubuntu host, Docker, Compose, Codex, and host ROS 2
  observations.
- Defined Windows documentation as reference-only pending explicit migration.
- Established Ubuntu-local documentation as the current development record.
- Created and verified the separate Google Drive
  `IITM Dentobot/active-development-ubuntu` mirror.
- Restored the continuous Windows-era project context, architecture, plan,
  reproducibility procedure, changelog, and renamed historical logbook into
  both the active Drive folder and local Ubuntu docs.
- Verified the pulled container image, running container, ROS 2 Jazzy package
  environment, SlicerROS2 install prefix, and running Slicer process.
- Installed the official ROS 2 Lyrical Desktop and ROS development tools on
  Ubuntu 26.04, initialized rosdep, and verified bounded C++ publisher to
  Python subscriber communication on the host.
- Verified bidirectional standard string communication and a one-way
  explicitly simulated standard transform message between host Lyrical and
  container Jazzy on the isolated DENTOBOT development domain.
- Passed all 23 upstream headless SlicerROS2 tests, including synthetic MRML
  image and point-cloud bridges, TF2, parameters, services, and QoS.
- Verified exact bidirectional synthetic mono8 image bytes between a host
  Lyrical node and a Slicer MRML scalar-volume bridge in the Jazzy container,
  then repeated the test successfully after a container restart.
- Verified a synthetic oblique, anisotropic int16 MRML/NIfTI Bridge B round
  trip through the real `dentobot_inference` backend and DENTOWorkflow
  geometry validator, including exact voxels and deliberate geometry-mismatch
  rejection.
- Added a single daily launcher that starts the Compose service and verifies
  the persistent minimal Bridge B backend in the existing
  `dentobot` Conda environment, scopes X11 authorization to the Slicer process,
  and loads DENTO Workflow from repository source.
- Repeated the complete synthetic Bridge B round trip with
  `/home/light-tarun/miniconda3/envs/dentobot/bin/python`; exact voxels,
  geometry, and the negative mismatch check all passed.
- Verified headlessly that launcher-equivalent Slicer arguments discover and
  automatically select `DENTOWorkflow`.
- Established the active DENTOBOT Git checkout at `ros2_ws/src/DentoBot` on
  `codex/ubuntu-migration`, published its checkpoint branch/tag, and retained
  the root workspace as a non-Git wrapper. This layout was extended on
  2026-08-06 so its operational text/configuration is tracked through the
  repository's `Workspace/` directory without changing the checkout root.
- Migrated the native Ubuntu CPU backend path into a preserved checkpoint
  image and verified explicit-CPU backend/Slicer happy paths on the public
  fixture, including 54 labels and MRB save.
- Closed the Slicer 5.10 process-lifecycle gate with explicit Qt ownership and
  teardown plus two consecutive health-only probes in 7.76 and 5.91 seconds;
  both Slicer/backend processes exited and no disposable container remained.

## 2026-08-21 — Step 6 ROS/MoveIt repair checkpoint

### Completed and verified

- Replaced embedded ROS process/CLI orchestration with an external
  launcher-owned simulation stack and versioned readiness topic.
- Added `dentobot_moveit_config`: `dentobot_arm`, KDL, OMPL RRTConnect,
  conservative draft limits, adjacent-link collision exclusions, and disabled
  trajectory execution.
- Added provisional `dentobot_tool_tcp`; aligned +Z with the spindle axis.
- Connected Step 6 and ROS2 Motion Control joint inputs to an external
  collision guard and the single simulated joint source; rejected commands
  restore the last accepted UI state and preview stops on rejection.
- Transformed phantom/teeth/template/docking surfaces into `base_link` and
  published hidden MoveIt collision proxies with 5 mm robot padding.
- Verified 51 host tests; launcher health and both ROS packages build; the ROS
  package suite reports 9 tests with no failures; ROS smoke returned direct KDL
  IK success and Cartesian fraction 1.0; embedded
  Slicer loaded the open-mouth phantom/robot and returned a 29-point fraction
  1.0 plan.
- Verified the 5 mm gate with a safe 40-sample transition whose minimum self
  distance was 12.713 mm and a rejected transition at 4.500 mm between
  `link-1` and `link-3`; the accepted `/joint_states` value did not move.
- Added a persistent **Reload Module (Dev)** UI action. It preserves the scene,
  Slicer process, container, and external ROS stack while reloading the main
  module and all DENTO Python helpers; it deliberately disconnects the
  Slicer-side robot and clears adapter-owned ROS nodes before replacement.
- Verified the real Slicer reload path under Xvfb: the button was visible, the
  widget and helper-module objects were replaced, the MRML sentinel survived,
  and the disposable Slicer process exited zero.
- Fixed the graphical launcher abort caused by Bash `nounset` entering the ROS
  Jazzy setup files. Verified the exact strict-mode/source sequence, then
  launched Slicer on `DISPLAY=:0` directly into DENTOWorkflow with the external
  simulation status ready and exactly one `/joint_states` publisher.
- Made normal GUI startup restart the dedicated DENTOBOT container before
  Compose reconciliation, clearing stale Slicer/ROS/MoveIt/test descendants
  without routine container recreation. A seeded `sleep 300` process was gone,
  Slicer and the external stack reached ready state, final container state was
  stopped, and the host regression suite passed 52 tests. `--check-only`
  remains non-destructive.
- Fixed the Step 0 **New Empty Case** / **Load Saved Scene** crash path. Scene
  close now stops preview and releases the Slicer-side robot plus adapter-owned
  ROS MRML nodes before deletion; runtime ROS nodes are excluded from MRB save;
  the default ROS node is reattached after scene replacement; and transform
  display handle calls are guarded for the pinned Slicer 5.10 API. The final
  Xvfb lifecycle probe cleared a scene, reloaded an MRB containing a locked
  Step 6 base transform, restored the sentinel and parameter references, and
  printed `DENTOBOT_SCENE_LIFECYCLE_PASS`. The focused host suite passed 54
  tests. The known SlicerROS2 debug-leak exit code 1 occurs only after this PASS
  during scripted application shutdown and remains active item 4 below.
- Extended that regression with a live robot: module reload now disconnects
  and reconnects without native loss; New Empty Case retains only the hidden
  process-owned default ROS node and reconnects cleanly; stale final
  subscriber references are removed. The real `test1_6_FD14.mrb` sanitizing
  round trip preserved world-RAS trajectory length (15.760533814 mm), final
  template mesh counts (29,962 points), bounds, and base matrix while restoring
  no ROS graph or active flag. Its stored Step 4C/5C outputs are stale, so Step
  6 is now deliberately deactivated until they are regenerated and verified.

### Active next tasks

1. In a normal graphical session, load the disposable open-mouth phantom,
   connect the ROS robot, drag/snap/fine-nudge the base onto the forehead, and
   manually exercise all six Step 6/Motion Control joints. Launcher startup is
   now verified; the interactive operator exercise remains.
2. Create reachable disposable Entry→Target lines in the mouth and record
   accepted/rejected MoveIt fraction, joint vectors, and collision messages.
3. Decide how forehead mount contact should be represented or selectively
   allowed; do not disable non-adjacent collision pairs by convenience.
4. Repair or upstream-report SlicerROS2 headless teardown exit code 1 after
   otherwise successful MoveIt smoke output.
5. Repair or upstream-report the MoveIt 2.12.4 `move_group` SIGINT teardown
   segmentation fault; service behavior passes and all other nodes exit cleanly.
6. Calibrate real TCP and replace draft visual-mesh collision geometry only
   after the robot/head-mount design stabilizes.

### Explicitly blocked/out of scope

- Execute, controllers, `ros2_control`, robot hardware, drilling, patient use,
  and clinical safety validation remain unauthorized.
- Git commit/push and Google Drive synchronization were not performed in this
  implementation turn.

## 2026-08-22 — Motion Control and draft workspace increment

### Completed and verified

- Parent current and goal SlicerROS2 robot roots to the same Step 6 base.
- Replace the editable Move Group Exists toggle with detected readiness; fix
  `dentobot_arm` and expose `dentobot_tool_tcp` without requiring an SRDF
  end-effector group.
- Show IK/plan status in Motion Control and keep Execute hidden/disabled.
- Add Step 6.3 deterministic Halton joint-space/FK workspace generation,
  5 mm coarse AABB filtering, phantom/case TCP point-clearance filtering,
  transient base-parented visualization, stale marking, and clear/regenerate.
- Narrowly exclude two documented persistent CAD-AABB false positives from the
  coarse fallback; keep the ROS-active MoveIt/FCL gate authoritative.
- Verify 61 host tests and real Slicer/ROS/MoveIt JSON evidence: +1 mm generic
  IK, 25-point generic plan, fraction-1.0 Step 6 path, and 116/200 accepted
  workspace points with 84 other AABB rejections.

### Active next tasks

1. Perform the normal graphical operator trial and record representative
   forehead placement, joint ranges, mouth-space IK goals, and plan failures.
2. Decide the intended forehead mount contact representation in the MoveIt
   planning scene without weakening unrelated collision checks.
3. Repair or report the pinned SlicerROS2 headless VTK-leak exit after the
   explicit success result and the MoveIt SIGINT teardown defect.
4. Calibrate the physical TCP and replace draft collision geometry only after
   the mechanical design stabilizes.

### Out of scope

- Controllers, Execute, hardware motion, drilling, patient use, and clinical
  safety validation remain disabled/unauthorized.
- No Git commit/push or Google Drive synchronization was requested or performed
  in this increment.

## 2026-08-24 — Parallel Step 6 / application-shell checkpoint

### Completed and verified

- Created `integration/gui-step6` from the clean accepted baseline; retained
  one repository, module, ROS workspace, and container mount.
- Added the reusable robot workflow façade with structured capabilities and
  results, operator-unit conversion, base/joint/IK/collision/planning/preview
  orchestration, and no execution method. Routed Legacy Step 6 handlers through
  it and added pure contract tests.
- Added the opt-in six-workspace Slicer shell, workstation-local Legacy/New
  mode selection, light/dark themes, Focus/Expert mode, dock cleanup, and stable
  mapping of internal stages 0–10. Legacy remains default.
- Added the Robot Simulation task presentation with six substeps and dedicated
  runtime, Goal/IK, and Scene/Collision cards. Current and goal robot roots stay
  under the same base; the user manipulates a TCP goal rather than the base.
- Updated the live MoveIt smoke to call the façade for capability reporting,
  KDL/MoveIt IK, and joint-goal planning. Verified one `/joint_states` source,
  `dentobot_arm`, `dentobot_tool_tcp`, FCL-backed rejection, three planning
  surfaces, fraction-1.0 Cartesian planning, and 116/200 draft workspace points.
- Recorded `81 passed` for the full host suite. Real Slicer printed
  `DENTOBOT_APPLICATION_SHELL_PASS`; module reload preserved its sentinel and
  replaced helper/widget objects; ROS-backed reload/New Case/saved-scene flow
  printed `DENTOBOT_SCENE_LIFECYCLE_PASS`. Launcher `--check-only` rebuilt both
  ROS packages and passed.

### Active next tasks

1. Run the twelve-item normal-window operator acceptance in the new shell and
   record actual forehead placement, all six joint motions, mouth-space TCP
   goals, IK failures/successes, collision messages, and plan/preview behavior.
2. Keep Legacy as default and fallback until that acceptance passes. Fix façade
   or lifecycle defects in shared code; do not add robot logic to GUI files.
3. Migrate Imaging, Segmentation, Drill Planning, and Guide Design one
   workspace at a time. Compare node roles/references, Current/Stale state,
   geometry hashes/bounds, lineage, exports, and failures on cloned scenes.
4. Decide the intended forehead-mount contact representation without weakening
   unrelated MoveIt/FCL checks. Keep the draft AABB cloud labelled approximate.
5. Upstream-report or isolate the pinned SlicerROS2 VTK/class-loader shutdown
   leak. Explicit PASS markers are functional evidence, not clean shutdown.
6. After a stabilization cycle and complete parity inventory, make the shell
   the development default; remove Legacy presentation only in a later,
   separately verified change.

### Boundaries

- No copied `DENTOWorkflow-v1/v2`, second state database, custom renderer,
  standalone Qt application, hardware execution, controller, drilling, or
  patient-facing motion.
