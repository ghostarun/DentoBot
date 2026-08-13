# DENTOBOT Project Checkpoint — 2026-08-12

## Purpose and evidence boundary

This checkpoint separates implemented software capability from demonstrated
technical behavior, research assumptions, and unresolved clinical or mechanical
requirements. It is intended to support development planning and discussions
with dental, manufacturing, registration, and robotics collaborators.

The application remains a **research prototype that is not clinically
validated**. No successful visualization, synthetic geometry test, MRB reload,
verification report, or STL export establishes anatomical accuracy, physical
fit, mechanical strength, sterility, registration accuracy, safe drilling, or
regulatory suitability.

Status terms used here:

- **Implemented:** source and UI behavior exist.
- **Synthetically verified:** a bounded generated-data test passed in Slicer.
- **Operator observed:** a developer exercised the behavior interactively.
- **Clinically unresolved:** a dentist-approved definition or acceptance test
  is still missing.
- **Mechanically unresolved:** dimensions, materials, loads, or the mating
  interface are still provisional.

## What is done

### Platform and inference boundary

- DENTOWorkflow keeps Slicer's embedded Python responsible for Qt, MRML,
  DICOM, geometry, and visualization, while a separate Linux Python environment
  owns PyTorch, TotalSegmentator, nnU-Net, and inference.
- Ubuntu uses the verified SlicerROS2 container plus a direct external CPU
  backend. Windows has a native-Slicer/WSL2 launcher contract, but that launcher
  still requires Windows 11 acceptance.
- The Ubuntu external environment has a matched CPU PyTorch/torchvision stack,
  cached TotalSegmentator weights, passing dependency health, and 13 passing
  backend tests.
- A public CBCT fixture completed CPU segmentation with preserved geometry,
  54 detected labels, and recorded run evidence.
- CRD can display and operate DENTOWorkflow through the normal launcher. It
  uses `llvmpipe`, so it is a functional display path rather than a GPU/FPS
  validation path.

### Segmentation review

- The imported `vtkMRMLSegmentationNode` remains the authoritative corrected
  anatomy.
- FDI-aware label browsing, visibility, isolation, source provenance, review
  states, and Segment Editor handoff are implemented.
- Correction activity invalidates a prior Reviewed state conservatively and
  labels inference measurements as pre-correction provenance.
- Corrected anatomical accuracy and corrected-mask quantitative metrics are
  not yet established.

### Step 4A — manual trajectory and verification

- Trajectories use one authoritative two-point `vtkMRMLMarkupsLineNode` with
  Entry and Target in world RAS millimetres.
- Multiple trajectories per tooth, persisted target association, informative
  state-bearing names, lineage colours, deletion, reload restoration, and
  downstream invalidation are implemented.
- Longitudinal trajectory-aligned oblique MPR uses Slicer's native reslice
  pipeline and rotates around the fixed Entry→Target axis without creating a
  new volume.
- Point correction preserves the selected circumferential MPR plane through
  parallel transport of the previous view frame.
- Target-only focus, all-view framing, native crosshair reference, and exact
  restoration of transient visibility/view state are implemented.

### Step 4B — assisted one/two-root initialization

- The user places one or two crown Entry points.
- A dependency-free surface algorithm estimates crown-to-root direction,
  examines root-side surface caps, and separates two transverse branches when
  requested.
- The output is the same ordinary Entry→Target line representation used by
  manual planning and downstream geometry.
- Generated trajectories remain unlocked and are explicitly marked
  `RequiresManualVerification`.
- The method is a geometric initializer. It is not canal-centre, apex,
  perforation-risk, or safe-path detection.

### Step 4C — provisional target-frame docks and rails

- One or two locked target trajectories and the target-tooth crown cap define
  a right-handed local frame without assuming a world anatomical axis.
- Schema v2 uses trajectory direction for crown/root polarity and fits the
  target-crown occlusal normal. A locked reference plane and four independent
  hollow docks are generated with explicit MRML references to the segmentation
  and every source trajectory.
- Each robot-facing dock top/opening lies on the fitted plane; depth proceeds
  crown-to-root. There is no crown-centred hub or radial spoke.
- The UI exposes shared depth and optional four-independent depths.
- Current development defaults are visible and recorded: 15 mm dock radius,
  1 mm bore, 3 mm outer diameter, 3.5 mm attachment-branch diameter, 2 mm
  endpoint overlap, and 5 mm dock depth.
- Step 5B creates four separate shell attachments, keeps the trajectory drill
  guide/local collar distinct, clips attachments against the guide envelope,
  and rejects any core dock collision with that envelope.
- These values and the present automatic attachment form are provisional research
  geometry, not a finalized robot mating interface.

### Step 5A — visible support selection

- The target and manually selected support teeth are derived from the
  authoritative segmentation without turning the combined draft model into a
  second source of truth.
- A trajectory-directed semi-automatic plane uses a crown-cap tilt estimate
  and one insertion-axis depth to initialize an editable closed support curve.
- Intersections from disconnected teeth are joined into one resampled outer
  boundary instead of requiring a manually drawn bridge through every gap.
- The visible-support preview maps results back to stable tooth segment IDs,
  treats extra islands as diagnostics, and selects the crown-side patch per
  tooth using the trajectory direction.
- Target/support-only focus prevents neighbouring unselected teeth from
  confusing routine boundary placement.
- Current 3 mm plane depth, 10 percent crown-cap fit, 0.5 mm curve sampling,
  and 50 percent terminal-support coverage are research defaults.

### Step 5B — undercut-aware shell and unified guide

- A derived Approach→Seat insertion-direction line is persisted in world RAS;
  a polarity-reversal control covers exceptional cases.
- Retentive-surface analysis, directional height-field blockout, adjacent-tooth
  collision-only anatomy, transverse interproximal relief, and terminal-tooth
  partial coverage are implemented.
- Dynamic Modeler Margin/Hollow is combined with cropped voxel reconstruction
  when an open or non-manifold Hollow candidate cannot be accepted.
- A lifted structural collar bridges disconnected tooth-shell rims on the
  removal side without declaring the interdental bridge a patient-contact
  surface.
- The patient shell, trajectory guides, Step 4C dock assembly, docking
  clearances, reinforcement, shell-contact link, and restored guide channels
  are fused into one `FinalPrintableTemplate` model.
- Occupied material connectivity is measured in the voxel domain, avoiding a
  false failure caused by inner and outer boundary surfaces of a hollow solid.

### Step 5C — verification and export

- The active Step 5C path evaluates source/current-state, support ROI,
  insertion direction, undercut processing, trajectory snapshots and axes,
  dock coplanarity, topology, occupied-volume count, reinforcement/channel
  masks, and wall/bore sampling.
- Results are classified as PASS, WARNING, or FAIL and persisted on the final
  model.
- FAIL disables normal export. Export reruns verification rather than trusting
  stale UI state.
- The manufacturing output is one atomic binary
  `DENTO_Final_Printable_Template.stl` rather than separate shell and sleeve
  files.
- The old raw-shell/separate-sleeve/trim/two-file controller is hidden and no
  longer executed, while its node readers remain for older-scene compatibility.

### Workflow UI and persistence

- The module now exposes ten stages with one top-level section expanded at a
  time, Previous/Next navigation, direct jumps, and a non-disruptive recommended
  next stage.
- Detailed guidance, metadata, machine paths, backend output, and secondary
  panels are hidden until requested. The research-only warning remains visible.
- Owned-node deletion is role-gated and confirmed. Upstream edits mark or
  remove dependent outputs rather than silently exporting outdated geometry.
- Focus, crosshair, MPR, and isolation operations are transient presentation
  state and restore the previous view configuration.

## What is done well

- **One source of anatomical truth:** corrected segmentation remains
  authoritative; generated models are traceable derivatives.
- **Reference-based identity:** stable segment IDs, role attributes, and MRML
  node references are used instead of editable display names.
- **Coordinate discipline:** geometry is expressed in world RAS millimetres;
  local dental/docking frames are explicit and no world axis is called
  anatomical by assumption.
- **No second trajectory truth:** manual and assisted planning produce the same
  two-point line representation.
- **Stale-state awareness:** trajectory, support, insertion, and parameter
  changes invalidate downstream geometry and verification.
- **Reversible processing:** source anatomy is preserved; role-owned derived
  subtrees can be deleted and regenerated.
- **Robust geometry strategy:** native surface tools are used where stable and
  cropped voxel operations are used for topology-sensitive Boolean work.
- **Honest evidence labels:** provisional geometry and surface-derived targets
  are visibly marked as research-only and manually verifiable.
- **Export safety:** final export is atomic, one-file, reference-gated, and
  reverified immediately before writing.
- **Runtime isolation:** dependency-heavy inference does not mutate Slicer's
  embedded Python environment.

## What can be improved

- Replace the development-style collapsible module panel with a themed stacked
  workflow, persistent case header, stage rail, compact viewport toolbar, and
  explicit advanced drawers before custom-application packaging.
- Centralize scattered inline Qt styles into one accessible theme with
  semantic status roles; do not rely on colour alone.
- Split the approximately 22,000-line workflow controller further so trajectory,
  guide, verification, view-state, and legacy compatibility behavior can be
  tested and maintained independently.
- Continue shrinking the visible legacy Step 5 surface and eventually migrate
  compatibility readers out of routine controller paths after a scene-version
  policy is agreed.
- Add a dedicated labelled MPR layout and reduce simultaneous rendering work
  if physical-session profiling confirms a remaining bottleneck.
- Improve the support-margin editor from a primarily plane-initialized loop to
  a focused 3D surface-constrained editor with independently adjustable point
  heights.
- Add corrected-mask metrics and optionally per-label review only after the
  clinical team defines what review means.

## What needs to be improved before a reliable research demonstration

- Live-verify the corrected Step 4C independent-dock/attachment topology and
  continuous drill/dock bores on representative anatomy; replace the generic
  closest-surface attachment branches when the robot load-path profile is
  defined.
- Run the full Step 4B→4C→5A→5B→5C workflow interactively on multiple
  representative de-identified cases, not only synthetic geometry.
- Verify the ten-stage UI, focus/restoration controls, MPR correction, scene
  save/reload, deletion, staleness, regeneration, verification, and one-STL
  export together in a physical Intel-`iris` session.
- Recheck the formerly failing three-tooth/42-invalid-edge case and document
  whether the reconstructed shell seats and removes plausibly.
- Inspect every guide channel and 1 mm dock bore after voxelization; compare
  STL dimensions against the requested MRML parameters.
- Exercise transformed and untransformed scenes to confirm no hidden double
  transform or local/world-frame regression.
- Build and test the packaged extension, not just the source-path launcher.
- Rebuild the Ubuntu CPU image from its Dockerfile and repeat dependency,
  backend, and Slicer-native gates without mutable-container repairs.
- Perform Windows 11 launcher and native-Slicer/WSL2 acceptance before claiming
  cross-platform runtime support.

## What could be added later

- A complementary MPR cross-section normal to the trajectory with depth
  scrolling from Entry to Target.
- Quantitative dentin-wall thickness, lateral clearance, collision, and bur
  containment analysis after ground-truth anatomical definitions exist.
- Registered intraoral or desktop surface scans to supply actual exposed crown
  and gingival-margin information that CBCT alone cannot reliably provide.
- Automatic support-margin suggestions based on labelled CEJ/alveolar or
  registered optical-surface evidence, always retaining clinician editing.
- A saved case/planning/verification report with software revision, inputs,
  parameters, warnings, measurements, and final STL hash.
- Mechanical simulation or finite-element screening of dock and shell load
  paths after materials, loads, and boundary conditions are supplied.
- Dedicated registration/calibration, simulated navigation, and robot-adapter
  stages after the current geometry is validated.
- A branded DENTOBOT custom Slicer application with reduced chrome, embedded
  task-specific Slicer tools, developer mode, and clean-machine installers.

## What needs to be added before clinical, fabrication, or robot claims

### Clinical accuracy and workflow requirements

- A precise procedure definition: intended dental procedure, target anatomy,
  tooth classes, root-count scope, jaw scope, and explicit exclusions.
- Dentist-approved meanings of Entry, Target, target depth, bur axis, and
  acceptable trajectory correction.
- Quantitative segmentation accuracy criteria against governed expert ground
  truth, including performance under CBCT artifacts, restorations, missing
  teeth, fused roots, and poor contrast.
- A dentist-approved definition of the exposed support surface, gingival/CEJ
  clearance, terminal-tooth coverage, allowed contact regions, and regions
  that must never contact the guide.
- Measured fit, retention, seating repeatability, removal force, rocking, and
  positional repeatability on dental phantoms before any patient-context use.
- Clinically justified clearance, wall thickness, interproximal relief,
  undercut tolerance, and smoothing/resolution ranges.
- Independent confirmation that each guide channel maintains the required
  dentin clearance and does not create a lateral perforation risk.

### Manufacturing and mechanical requirements

- Final dock/rail mating profile and an unambiguous drawing defining every
  diameter, wall, depth, datum, tolerance, and assembly direction.
- Define the rail cross-section and identify exactly which rail surface is
  coincident or tangent with the target crown/occlusal plane. Define four
  shell-attachment paths that do not require a central crown hub.
- Define a protected clearance envelope around the annular trajectory guide;
  the four dock rails and their reinforcements must not enter that envelope.
- Confirmation of whether 15 mm is a radial centre offset, feature length, or
  another datum, and whether 1 mm is a bore, pin, or outer feature.
- Separation of registration-landmark functions from load-bearing robot-dock
  functions, even if they share one local frame.
- Material, printer technology, print orientation, shrinkage compensation,
  minimum feature size, post-processing, sterilization, and reuse policy.
- Expected robot mass, forces, moments, vibration, fatigue cycles, accidental
  load cases, and required factor of safety.
- Physical dimensional inspection and destructive/load testing of printed
  phantoms and dock specimens.

### Registration, kinematics, and safety requirements

- A documented image↔tooth↔guide↔robot↔tool frame tree and a measured
  registration/calibration procedure.
- Required FRE/TRE, angular error, lateral error, depth error, repeatability,
  and latency tolerances.
- Resolution of the two-trajectory kinematic conflict: one fixed robot Z axis
  cannot follow two non-parallel trajectories without reindexing, angular
  adjustment, a parallel constraint, or separate docking poses.
- Tool-tip, axis, hand-eye, and dock-pose calibration with independent target
  validation.
- Collision limits, workspace limits, force/torque limits, emergency stop,
  communication-loss response, fault recovery, and supervised bench tests.
- A safety architecture that keeps low-level motion and drilling outside the
  Slicer Python process.

## Questions that must be answered to remove clinical ambiguity

1. What exact operation is being planned, and what anatomy defines success?
2. Is Target the radiographic apex, canal centre, a planned depth short of the
   apex, or another clinically selected point?
3. What minimum remaining dentin thickness and lateral safety margin are
   acceptable along the complete bur volume?
4. Which teeth and root morphologies are in the first validated indication,
   and which morphologies must cause the assisted algorithm to refuse?
5. Is Entry always on exposed enamel/occlusal surface, and how is that surface
   confirmed when CBCT blooming or restoration artifacts are present?
6. Where should the guide margin sit relative to gingiva/CEJ, and can CBCT be
   sufficient, or is an optical scan mandatory?
7. Which support surfaces should carry load, which should provide retention,
   and which must be relieved completely?
8. What seating/removal force and positional repeatability constitute an
   acceptable snug but removable guide?
9. What constitutes clinician approval of a trajectory and final template,
   and what evidence must be retained with that approval?
10. Which verification failures are absolute FAIL conditions and which may be
    accepted as documented WARNINGS by a qualified operator?

## Questions that must be answered to remove mechanical and robotics ambiguity

1. What are the final robot docking and registration interfaces, and are they
   physically separate components or one shared pattern?
2. What exact datum defines the common dock seating plane?
3. How does the robot constrain all six degrees of freedom, and what prevents
   backlash, rocking, incorrect polarity, or partial seating?
4. How is each trajectory transformed into the dock frame, particularly when
   two trajectories are not parallel?
5. Does the robot reorient between trajectories, or is the guide expected to
   encode multiple fixed axes mechanically?
6. What are the permissible pose, manufacturing, and assembly tolerances in
   the complete image-to-bur error budget?
7. What loads reach the teeth, periodontal structures, shell, rails, and docks
   during homing and drilling?
8. How will the printed guide be inspected to confirm bores, channel axes,
   wall thickness, and dock coplanarity before use?

## Questions that must be answered to remove generic research ambiguity

- What is the primary research hypothesis: segmentation assistance, trajectory
  accuracy, guide fit, robot registration, drilling accuracy, or the complete
  system?
- What is the primary quantitative endpoint and its acceptance threshold?
- What comparator will be used: freehand planning, conventional static guide,
  commercial planning software, or another robotic method?
- How many representative scans, tooth types, phantoms, repeats, and operators
  are required for each stage of validation?
- How will inter- and intra-operator variability be measured?
- What data are permitted, how are they de-identified, and what is the retention
  and access policy for DICOM, MRB, NIfTI, logs, and STL artifacts?
- Which software/model/configuration revisions are frozen for each experiment?
- What failure taxonomy and stopping rules distinguish an algorithm refusal,
  operator correction, geometric failure, fabrication failure, and safety
  failure?

## Current claims and prohibited interpretations

| Supported statement | Do not infer |
|---|---|
| The software can generate and reference traceable derived geometry in Slicer. | The anatomy or guide is clinically accurate. |
| Synthetic tests produced one watertight occupied template volume. | The printed template will fit, retain, or withstand load. |
| A verification report can PASS/WARNING computational checks. | Clinical, manufacturing, registration, or safety approval. |
| Surface analysis can initialize one/two rootward trajectories. | Canal/apex detection or a safe drilling trajectory. |
| Four provisional docks can be generated in a target frame. | A finalized robot mating or registration design. |
| One atomic STL can be exported. | The STL is authorized for fabrication or use. |

## Recommended next gates

1. **Repository/reproducibility gate:** package all helper modules, run static
   and focused Slicer tests, inspect the final diff, and publish a clean branch.
2. **Live software gate:** exercise the full workflow on several anonymized
   representative scenes in the physical GPU-backed session.
3. **Clinical-definition gate:** answer the clinical questions above and turn
   each answer into a measurable acceptance rule.
4. **Phantom fit gate:** print shells/guides, measure seating, removal,
   retention, dimensions, channel axes, and repeatability.
5. **Mechanical-interface gate:** freeze the dock drawing, material, load case,
   tolerance stack, and two-trajectory kinematics.
6. **Registration/safety gate:** validate the frame chain, calibration, error
   budget, simulation, interlocks, and supervised bench behavior.
7. **Product-UI gate:** retain the same MRML/logic contracts while packaging a
   themed reduced DENTOBOT custom Slicer application.
