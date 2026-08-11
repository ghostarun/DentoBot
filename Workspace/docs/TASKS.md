# Dentobot Tasks

Last updated: 2026-08-11

## Active

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
- Build the verification gate and single `FinalPrintableTemplate` output after
  the now-working undercut/docking fusion. Require current source snapshots, one intended
  connected watertight component, docking-axis/dimension checks, anatomy
  clearance, and PASS/WARNING/FAIL before the existing atomic writer may export
  one STL. Do not invent a final rail profile; no finalized repository rail
  specification was found, so the current annular primitive remains explicitly
  provisional and replaceable.
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
- Confirm the closed-loop backtracking contract before implementation: a
  meaningful Step 4A edit would confirm and cascade-delete its Step 5A/5B
  descendants, while a Step 5A edit would confirm and delete Step 5B
  descendants. Define the confirmation boundary before interactive point
  editing so dialogs never fire on every mouse move.
- Complete developer-run Slicer acceptance of Step 5A: select one target and
  any manually chosen number of distinct whole-tooth supports, create/update
  the draft support-anatomy model, save/reopen the scene, and confirm
  persistence and stale-state behavior.
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

## Shelved — remaining Step 4

The accepted Step 4A assistance backlog is complete. The Step 4B
dentist-focused 2D plan remains preserved in this task list and
`docs/DEVELOPMENT_PLAN.md` and is not a current implementation priority.

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
  integration remains future conceptual scope.
- The provenance of existing generated files under `ros2_ws/build` has not been
  established.

## Completed

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
  target-tooth colors persist through Step 4A/5A/5B descendants; selecting a
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
  selected Step 4A target box/trajectory, Step 5A anatomy, and Step 5B
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
