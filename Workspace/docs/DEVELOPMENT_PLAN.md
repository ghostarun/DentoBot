# DENTOBOT Development Plan

> Ubuntu transition note (2026-07-29): completed Windows/WSL milestones remain
> historical implementation evidence. Their source and behavior must be
> transferred and reverified before being marked operational on Ubuntu.

## Development policy

- Implement one authorized milestone at a time.
- Prefer a small working vertical slice over disconnected feature fragments.
- Keep the stock Slicer runtime unchanged during extension development.
- Test Slicer and WSL components in their own environments.
- Advance only after acceptance evidence and a short milestone review.
- Future milestones are a blueprint, not authorization to implement them.

## Current baseline: imaging plus external-process bridge

**Status:** Step 0 and Bridge A/B work in the developer's Slicer workflow.
Bridge C has completed a real-CBCT GPU inference and safe Slicer import/display
with 60 validated segments in 2D and 3D. Its validated top-level dependency
versions and reconstruction procedure are now documented. Five new WSL unit
tests, cancellation/error paths, a complete transitive dependency lock,
anatomical validation, and MRB scene persistence remain pending.

The Extension Wizard scaffold and exploratory trajectory code exist, but the
trajectory-first sequence has been superseded. The extension project is now
named DENTOBOT, and all new module identifiers use the `DENTO` prefix. The
project begins with the focused `DENTOWorkflow` shell, then establishes
independent external inference before returning to segmentation review and
trajectory planning.

Acceptance criteria:

- Project context, architecture, agent rules, and roadmap agree.
- Early extension development and later custom-app packaging are distinct.
- WSL2 inference is isolated from Slicer's Python environment.
- Slicer controls inference through direct asynchronous `wsl.exe` process
  execution rather than a watched-folder job system.
- ROS is deferred to a documented robotics decision gate.
- Timestamped low-level development history is maintained in `changelog.md`
  and `logbook.md`.
- Installed Slicer files and Slicer's embedded Python environment remain
  unchanged.

## Step 0: Minimal workflow shell and DICOM viewer

**Status:** implemented; developer reports the current Step 0 workflow works

Goal: provide a clean DENTOBOT entry point for loading and inspecting one
CBCT series without requiring routine use of unrelated Slicer modules.

Implementation:

- Create `DENTOWorkflow` as the user-facing scripted module and extension
  home.
- Replace generated example controls with a minimal Imaging page.
- Add New/Open Case, Import DICOM, selected-volume, Clear Case, and status
  controls.
- Use Slicer's DICOM browser and loader rather than implementing DICOM parsing.
- Use a scalar-volume `qMRMLNodeComboBox` bound to a typed parameter node.
- Display selected volume name, dimensions, spacing, scalar range, and basic
  geometry/orientation status.
- Show the loaded volume in standard slice views and fit slices to content.
- Handle scene close/reopen and observer cleanup.
- Decide during implementation whether to retire or migrate useful code from
  the legacy `DentalNavPlanning`; do not retain threshold-example behavior in
  the user UI or extension build.

Acceptance criteria:

1. A user starts in the DENTO Workflow module.
2. One button opens the standard Slicer DICOM import/browser experience.
3. A valid CBCT series loads as a scalar-volume MRML node.
4. The workflow selects the loaded volume and displays its metadata.
5. Axial, sagittal, and coronal views display the volume correctly.
6. Invalid or malformed input produces an actionable message without altering
   original files.
7. The selected volume persists across module changes and scene save/reopen.
8. No external Python, AI, registration, or robot dependency is introduced.

## Step 1: Standalone WSL2 inference foundation

**Status:** health, NIfTI round trip, and GPU-only `segment-teeth` are
implemented. The three pre-Bridge-C WSL tests and CUDA health pass. Cached
tasks 113/115 and a representative real-CBCT inference have now completed
successfully; the five new segmentation unit tests remain pending. Exact
validated top-level dependencies are now pinned, but a complete
platform-specific transitive lock and clean-machine reconstruction remain
pending.

Goal: make dental segmentation independently runnable and testable without
Slicer.

Implementation:

- Add the `Inference/` Python package and a minimal environment definition;
  lock exact dependencies only after compatibility validation.
- Implement `health --json --require-cuda` for interpreter identity, package
  versions, PyTorch import health, CUDA availability, and GPU identity.
- Define the versioned command-line, structured-stdout, exit-code, and result
  metadata contracts.
- Implement a geometry- and voxel-preserving NIfTI round-trip command so the
  cross-interpreter boundary is tested before model inference.
- Implement `segment-teeth --input ... --output ... --result-json ...`
  using TotalSegmentator's `teeth` task and multilabel NIfTI output.
- Preserve label mapping and NIfTI affine.
- Emit machine-readable progress events without requiring a queue or worker
  service.
- Provide clear exit codes for invalid input, missing model, unavailable GPU,
  out-of-memory, cancellation, and inference/import failure.
- Add unit tests and a de-identified smoke-test fixture or documented fixture
  acquisition process.

Acceptance criteria:

1. Backend tests run entirely inside WSL2.
2. Health check identifies the RTX GPU and usable CUDA PyTorch runtime.
3. A command segments a representative CBCT NIfTI without Slicer running.
4. Output contains the expected dental label map and physical geometry.
5. Complete result metadata is produced for success and failure.
6. No package is installed into Slicer's embedded Python.

### Bridge A/B integration checkpoint

**Status:** passed, including Slicer-launched CUDA health and a round trip of
the explicitly selected real CBCT

These independently testable slices were the gate before Bridge C:

1. Bridge A asynchronously launches the configured WSL distribution and exact
   Conda Python, reports JSON health, and distinguishes missing packages,
   broken PyTorch imports, unavailable CUDA, and a healthy GPU.
2. Bridge B exports the selected MRML scalar volume, runs the backend NIfTI
   round trip, validates backend JSON plus data/geometry, imports the returned
   volume, and stores its parameter-node reference and `DENTOBOT.*` provenance.
3. Slicer remains responsive while the process runs, and Cancel requests
   termination without starting another process.
4. No system Python executes Slicer code; no WSL/Slicer package is installed
   automatically; no model is downloaded.

Successful Bridge A/B verification authorized the current Bridge C source
implementation; it does not count as Bridge C runtime acceptance.

## Step 2: One-click segmentation bridge

**Status:** core happy-path runtime verified; completion testing remains

Goal: run the validated WSL backend from DENTOBOT and receive a segmentation
in the MRML scene.

Implementation:

- Add output segmentation state, a GPU Run action, Cancel, progress, live log,
  and compact metrics to the focused workflow UI.
- Export the selected CBCT to an isolated run-artifact directory as NIfTI.
- Invoke the configured WSL Python interpreter directly with an argument-safe,
  asynchronous process call; do not create a watched-folder queue.
- Stream progress without freezing the UI and support cancellation.
- Handle the process exit code and validate result metadata and NIfTI geometry.
- Import labels into a `vtkMRMLSegmentationNode` with names and source links.
- Create binary-labelmap and closed-surface representations for immediate 2D
  and 3D display.
- Store backend metadata as `DENTOBOT.*` attributes and parameter-node state.
- Require CUDA device 0; reject unavailable CUDA without CPU fallback.
- Prevent implicit model acquisition by replacing TotalSegmentator's runtime
  downloader with a cache-only guard for tasks 113 and 115.

Acceptance criteria:

1. One button runs the `teeth` task on the selected CBCT.
2. Dependency, CUDA, model, process, cancellation, and inference failures are
   distinguishable.
3. A successful run creates a correctly aligned segmentation node.
4. Label names and run metadata are available in the scene.
5. Original CBCT/DICOM data and the Slicer installation remain unchanged.
6. Scene save/reopen retains source and output node references.

Current evidence satisfies criteria 1, 3, 4, and 5 for one representative
CBCT. Dependency/model/CUDA happy-path handling is demonstrated, but the
distinct failure cases in criterion 2 and scene save/reopen in criterion 6
remain to be exercised. Visual alignment is not anatomical ground-truth
validation.

### Deferred Bridge C validation backlog

The developer elected to continue beyond the verified happy path and return to
the following work later. Deferral is non-blocking for Step 3, but these items
remain required before a reproducible release or robustness claim:

1. run the five new segmentation-focused WSL tests;
2. exercise missing dependency, missing model, and unavailable CUDA paths;
3. verify cancellation and descendant-process cleanup;
4. verify out-of-memory, malformed-output, and partial-output behavior;
5. verify source/output references after MRB save and reopen;
6. establish anatomical ground truth and quantitative acceptance criteria;
7. capture a complete transitive environment lock and perform a clean-machine
   reconstruction.

## Step 3: Segmentation review and visualization

**Status:** Steps 3A, 3B, and 3C developer-verified in Slicer 5.12.2

Goal: let the researcher inspect and curate dental labels before planning.

Step 3A implemented scope:

- segmentation selector bound to the existing persistent
  `teethSegmentation` parameter-node reference
- deterministic FDI-aware names and anatomical grouping
- search by anatomy, category, source label, or FDI code
- per-segment visibility checkboxes
- selected-segment 2D/3D emphasis without mask modification
- show all, hide all, and isolate selected actions
- independent global 2D/3D visibility and opacity controls
- observers rebound on selected-node replacement and removed during module
  exit, cleanup, and scene close
- automatic transition from a successful Bridge C run to the review panel

Step 3B implemented scope:

- selected-label anatomy, source name, FDI number, model label ID, voxel
  count, and physical volume
- compact run, source-volume, backend, TotalSegmentator, model/dataset,
  device, timing, and completion provenance
- proper MRML source-volume reference plus versioned per-segment metrics
  persisted on the authoritative segmentation node
- segmentation-level `Unreviewed`, `Needs Correction`, and `Reviewed`
  workflow state with a UTC update timestamp
- direct metadata enrichment for new Bridge C imports and non-fatal migration
  of older imported results from retained `result.json`
- explicit UI language that review state is not anatomical or clinical
  validation
- Slicer-native logic coverage for metadata mapping, node references,
  provenance presentation, selected-label metrics, review-state transitions,
  and invalid state rejection

Step 3C implemented scope:

- one-button handoff of the selected label to Slicer's built-in Segment Editor
- strict validation and binding of the authoritative segmentation, persisted
  source CBCT, and selected segment ID
- conservative whole-segmentation transition to `Needs Correction` when a
  correction revision starts
- correction-start and mask-edit timestamps persisted as `DENTOBOT.*`
  attributes
- inference metrics retained as provenance but explicitly marked
  baseline-only after correction starts
- content-specific observers for source-representation edits and segment
  addition/removal while DENTO Workflow is active
- display, selection, naming, and provenance changes excluded from review
  invalidation
- Slicer-native logic coverage for correction validation, source-node
  recovery, state transition, metric validity, timestamps, and invalid inputs

Remaining Step 3 increments:

- richer opacity/color presets and optional anatomy presets
- optional corrected-mask metric recomputation
- optional per-label review state, only if the research workflow later needs
  tooth-by-tooth acceptance

The developer reports that Steps 3A and 3B work as intended in Slicer 5.12.2
and completed the Step 3C acceptance checklist. The exact segmentation,
source CBCT, and selected segment were handed to Segment Editor; a small
edit/undo cycle and return to DENTO Workflow produced the intended
`Needs Correction` state, baseline-metric messaging, correction activity, and
MRB scene persistence. Step 3 is therefore accepted at its current scope.
Anatomical accuracy, corrected-mask metric recomputation, and optional
per-label review state remain separate validation or enhancement problems.

## Step 4: Procedure definition and minimal trajectory planning

**Status:** Step 4A assistance backlog implemented and Slicer-native verified;
clinical semantics and Step 4B remain unresolved

Goal: define a procedure-specific entry-to-target drill trajectory against
reviewed anatomy.

Implementation themes:

- procedure type and target tooth
- explicit anatomical definitions of entry and target
- two-point Markups line with Entry/Target labels
- live world-RAS length and direction
- bur diameter, maximum depth, and planning metadata
- plan approval and invalidation rules
- logic tests for geometry and invalid state

The existing trajectory experiment may be reused only after it is reviewed
against these requirements.

The Step 4A lifecycle now distinguishes clearing and deletion. **Clear Both
Points** retains the Markups line for reuse. **Delete Selected Trajectory**
requires confirmation and DENTOBOT ownership, removes only the selected line
and unshared display/storage auxiliaries, clears the workflow trajectory
reference, and preserves its target segmentation, tooth selection, and bounds.
Automated save/reload/recreate coverage has passed in Slicer.

Saved trajectory selection now restores the authoritative segmentation,
segment ID, target bounds ROI, target-tooth selector, visibility/highlight, and
details from persisted MRML associations both during scene refresh and manual
selection. Partial or mismatched associations are rejected rather than guessed
from names. New and legacy default names are managed as informative labels such
as `DENTO FDI 14 - Trajectory 2 [Complete]`; names never become identity keys.
The complete Slicer-native suite now covers scene-load and selector restoration,
MRB persistence, editable-name independence, and duplicate disambiguation.

All DENTOBOT trajectories remain available in one selector and are grouped by
their authoritative target tooth. Each tooth receives a deterministic
persisted lineage color once its first trajectory exists; the same color is
propagated by MRML-reference relationships to its Step 4A bounds, Step 5A
support anatomy, and Step 5B ROI/shell/sleeve. Selecting a tooth emphasizes
that group's trajectories while leaving other groups visible and preserving
explicit visibility choices. Step 5A/5B also expose the inherited FDI/color in
lineage badges, owned-node selector swatches, and Step 5B visibility-control
stripes so the relation remains visible when geometry is hidden. Colors and
names are display cues only.

Switching the target-tooth control never rewrites an already-associated
trajectory. An incompatible current trajectory is deselected, and the exact
segmentation/segment pair resolves its own reusable target-bounds ROI. Every
DENTOBOT trajectory is required to satisfy the Markups-line two-control-point
contract, with the points labelled Entry and Target. Active-widget deletion
coverage also verifies that workflow references are cleared before node
removal so selectors cannot substitute unrelated nodes during destruction.

### Step 4A extension — trajectory-aligned longitudinal oblique MPR

**Status:** implemented in source with static verification; live Slicer
acceptance pending

The compact **Trajectory Verification** control reuses the selected
Entry/Target Markups line and its segmentation-to-source-CBCT MRML reference.
It aligns one available native slice view with the trajectory vertically in
plane, rotates the plane `-180°..+180°` about that fixed axis, updates after
valid point edits, and temporarily projects the same Markups line as the 2D
overlay. It creates neither a new trajectory nor an angle-specific volume.

The frame/matrix logic is independently testable, handles vertical and
near-reference trajectories, rejects degenerate/non-finite inputs, and uses
the midpoint as slice origin. Slider and point events are coalesced. Disable,
module exit, scene close, cleanup, Step 5C isolation, and scene saving restore
the prior slice/composite/display presentation; saving then resumes the live
view without serializing the transient override.

The first live review found that recomputing the same numeric angle from a new
world-reference basis made point correction jump to another circumferential
view. The correction path now freezes the slice throughout a Markups drag and,
at interaction end, minimally transports the prior plane normal onto the new
trajectory. In-plane corrections preserve the exact plane, slider motion
continues by relative angle from it, and Reset explicitly reconstructs the
deterministic zero frame. Focused source tests cover in-plane preservation,
off-plane transport, the parallel fallback, handedness, and finite geometry;
live correction usability remains pending.

Live acceptance must confirm vertical overlay, circumferential anatomy change,
point immutability under rotation, stable under-pointer point dragging, exact
plane preservation after in-view correction, source-CBCT selection, state
restoration, MRB save/reopen behavior, vertical-axis safety, and interactive
FPS. Perpendicular cross-sections, depth scrolling,
optimization, collision/wall-thickness analysis, bur volume, and warnings are
future scope.

### Shelved Step 4B plan — dentist-focused 2D placement

**Status:** shelved on 2026-08-03 for later development

Preserved implementation sequence:

1. Add **Focus on Target Tooth** to center and fit the primary slice view on
   the selected target and bounds without silently changing orientation.
2. Represent the planning plane explicitly. Begin with user-captured current
   slice orientation; scanner axial, dental occlusal, and tooth-local planes
   remain distinct future modes requiring explicit definitions.
3. Lock slice rotation while allowing deliberate slice-offset scrolling
   through the target; provide explicit unlock/reorient controls and show the
   active plane mode.
4. Make 2D Entry/Target placement primary, keep the two-point and target-bounds
   invariants, distinguish on-slice from projected points, and retain 3D as
   contextual verification.
5. Synchronize cross-reference position across the other slice views without
   unexpectedly rotating them.
6. Persist plane mode/orientation and target/trajectory associations; warn and
   invalidate safely when stored references or orientation are unavailable.

Live usability acceptance remains developer/dentist-run in Slicer. Static and
ordinary-Python coverage should address plane validation, lock transitions,
association/persistence, stale references, and UI callback integrity. This
plan is preserved only; no Step 4B implementation is currently authorized.

## Step 5: Target-region modeling and template research

**Status:** major renovation checkpoint demonstrated through multi-trajectory
fusion. Visible-support ROI, explicit insertion direction, undercut/blockout,
patient-contact shell, provisional docking clearance/reinforcement, and one
connected unified model are implemented and Slicer-native synthetically
verified. Final PASS/WARNING/FAIL verification and one-STL export remain next.

### Step 5A — draft template support anatomy

Goal: produce a traceable, geometry-preserving anatomical input for later
template design without creating or claiming a dental guide.

Implemented behavior:

- reuse the authoritative Step 4A target tooth;
- let the user manually check any positive number of other whole-tooth
  segments from the same reviewed segmentation;
- impose no automatic adjacency, arch, side, or maximum-count rule;
- require unique support IDs and keep the target distinct from all supports;
- append unmodified world-RAS closed surfaces for the target and selected
  supports into one transform-free `vtkMRMLModelNode`;
- persist source-node,
  segment-ID, FDI, source-name, review-time, geometry-count, schema, and update
  provenance;
- retain the last output when inputs change, but mark it Stale and require an
  explicit Update action;
- persist support selection and model reference in the workflow parameter
  node for scene save/reopen;
- provide a dedicated confirmed deletion action that accepts only the
  DENTOBOT draft-model role, removes the model and unshared display/storage
  auxiliaries, clears its workflow reference, and preserves the target,
  segmentation, and manual support selection for safe recreation.
- create an editable role-owned closed boundary around only the erupted,
  accessible support surfaces and preview the selected patch distinctly;
- adapt SlicerFSP's Dijkstra curve clip per connected tooth surface so a single
  boundary works with DENTOBOT's separate complete-tooth segments rather than
  silently selecting one tooth;
- persist explicit source/boundary/segmentation references, world-RAS control
  points, selection side, processing resolution, revisions, metrics, and stale
  state; delete the owned boundary/preview safely while preserving authority.

Developer-run acceptance in Slicer must cover small and large selections
(including two and ten supports), create/update behavior, target/support
distinctness, save/reopen persistence, source-edit invalidation, and clear
Current/Stale presentation. The added Slicer-native lifecycle test also covers
trajectory/model deletion, retained inputs and selections, save/reload, and
recreation and has passed in the bounded container Slicer runtime.

The visible preview is not an undercut-corrected fitting surface, final shell,
printable guide, clinical validation, or drilling authorization.

### Step 5B — patient-contact shell and guide integration

Current renovation behavior:

- require a Current visible support preview explicitly linked to the Current
  full support model and authoritative segmentation;
- expose fit clearance, wall thickness, and tight-domain processing resolution;
- run native Dynamic Modeler Margin followed by Hollow, retaining both tools
  and their fitting/candidate outputs as hidden role-owned referenced nodes;
- voxel-union the candidate only inside a cropped support domain and subtract
  residual material within the requested anatomy clearance;
- reject empty/open/non-manifold results and record topology, sample-domain,
  minimum-clearance, source-revision, warning, and parameter metadata;
- persist/reload and cleanly delete the shell plus four owned processing nodes;
- define insertion with an editable/persisted Approach→Seat Markups line in
  world RAS, using the opposite vector for removal;
- classify retentive surface triangles by normal/removal angle tolerance and
  construct a cropped insertion-frame directional height-field blockout rather
  than assuming anatomical direction from world axes;
- expose/persist blockout safety and voxel-closing values, re-enforce fit
  clearance after smoothing, and invalidate shell/final geometry after any
  insertion, ROI, support, or parameter change;
- select multiple complete locked trajectories by explicit repeated MRML
  references, rejecting trajectories outside the selected target/support
  anatomy;
- keep the current annular docking profile explicitly provisional and
  replaceable because no final robot rail/channel specification exists;
- adapt the SlicerFSP integration order in a tight voxel domain: docking
  clearance subtraction → reinforcement union → docking union → trajectory
  channel restoration;
- generate/persist/reload one `FinalPrintableTemplate` with explicit patient
  shell, all trajectory, docking, clearance, reinforcement, and channel
  references. The focused two-tooth/two-trajectory regression produces one
  connected watertight component;
- keep that unified model `NotVerified` and non-exportable until Step 5C's
  dedicated verification gate is complete.

The older model-independent raw research shell/sleeve behavior below is now a
labelled provisional developer path, not the target clinical/research flow:

Implemented behavior:

- require the current role-gated Step 5A support model and a complete locked
  Step 4A Entry/Target trajectory;
- create/reset a locked, non-selectable, axis-aligned world-RAS Markups ROI
  automatically around the support model and recompute it before generation;
  the ROI is a visible reference, not a user coverage control;
- list only role-owned Step 5B automatic ROIs in its selector, reject Step 4A bounds
  and unrelated ROIs at the logic boundary, and require the ROI's source
  reference to match the current Step 5A model before reset or generation;
- repair a legacy cross-role Step 4A bounds node in place and clear any invalid
  Step 5B parameter reference without deleting the Step 4A node;
- disable selection and all translation/rotation/scale interaction handles on
  both Step 4A and Step 5B workflow-owned ROI roles, including loaded scenes;
- provide a dedicated confirmed, role-gated delete action for the shell ROI;
  preserve Step 5A, trajectory, dimensions, shell, and sleeve while marking
  retained Step 5B outputs Stale so a fresh ROI can be created;
- provide one Scene visibility panel for the selected Step 4A target box and
  trajectory, Step 5A support anatomy, and Step 5B ROI/shell/sleeve; hiding is
  display-only, persists through MRB save/reopen, and is preserved by ordinary
  refresh, reset, update, and regeneration;
- prefix workflow-owned scene-node names with their Step 4A/5A/5B tag for
  consistent identification in both DENTO Workflow and Slicer's Data view;
- sample signed distance from the world-RAS anatomy and extract an exterior
  clearance/thickness band inside the ROI;
- subtract a trajectory-aligned channel and generate a separate watertight
  annular sleeve extending outward from Entry;
- expose clearance, thickness, sampling, channel diameter, sleeve diameters,
  and sleeve height as persisted research parameters;
- cap voxel sampling to prevent accidental excessive memory use;
- validate finite geometry and boundary/non-manifold edges, report surface
  regions and sleeve/anatomy overlap warnings, and retain source/trajectory/
  ROI references plus parameters and metrics on the MRML output models;
- mark outputs stale when source anatomy, trajectory points, ROI bounds, or
  parameters change;
- save/reload both models in MRB and delete only role-owned outputs. Step 5B
  deliberately does not export its unfinalized raw shell.

Slicer-native synthetic verification passed for geometry generation,
watertight topology, binary STL output, MRB save/reload, output deletion,
shell-ROI deletion/recreation state, strict ROI role/source isolation, legacy
cross-role repair, and all pre-existing DENTO Workflow tests. The reported
2026-07-23 legacy MRB also loads through DENTO Workflow without recursive
refresh or a cross-role ROI; that compatibility check was read-only.
This is research geometry only. The public
EndoPlanner preview informed the workflow comparison but could not be reused
directly because its model weights and several called implementation helpers
are absent.

### Step 5C — dentist-directed fit, margin trim, and STL export

Implemented behavior:

- preserve the current Step 5B shell as a non-destructive source and create a
  separate role-owned finalized shell;
- provide **Isolate Shell in ROI-Aligned 3D View**, which saves layout,
  camera, crosshair, and display visibility; switches to one 3D view; shows
  the source shell alone; and restores the complete previous presentation for
  later 2D verification;
- at zero yaw look along ROI `+Y`, put ROI `+X` to viewport right and ROI `+Z`
  upward, and use half the ROI Z size as parallel scale so its top/bottom meet
  the viewport boundaries;
- lock X/Y/Z translation, pitch, and roll by default while retaining a
  360-degree yaw orbit around ROI `+Z` and interactive zoom; provide a second
  checkbox to freeze yaw while still allowing zoom, and allow a fully free
  camera when the first lock is deliberately cleared;
- keep the simple plane parallel to the ROI top/bottom faces with normal ROI
  `+Z`; use exactly one origin point, project it onto the ROI Z axis, and hide
  all translation/rotation/scale handles so signed Z height is the only cut
  input. Reapply and validate this constraint after reload and before cutting.
  Isolation itself creates no markup and starts no placement; the plane/curve
  buttons are separate deliberate actions;
- implement the simple workflow as a one-click height placement of a Markups
  plane followed by Dynamic Modeler **Plane cut** with capped surface and an
  explicit choice to keep the inferior/negative or superior/positive side;
- implement the uneven-margin workflow as a visible, adjustable Markups
  closed curve whose control points snap to the shell, followed by Dynamic
  Modeler **Curve cut** with an explicit inside/outside choice;
- cap the open Curve Cut boundary, triangulate, clean, orient normals, and
  reject empty or non-watertight finalized output;
- persist the trim method, kept region, plane/curve, Dynamic Modeler node,
  source reference/revision, edit geometry, topology metrics, and finalized
  shell through MRB save/reopen;
- mark the finalized shell Stale whenever its Step 5B source, trim method,
  retained region, or markup geometry changes;
- expose Slicer's full Dynamic Modeler module as an expert handoff while
  keeping DENTOBOT STL export gated to its own traceable finalized shell;
- delete the Step 5C plane, curve, finalized shell, Dynamic Modeler node, and
  owned cut auxiliaries as one confirmed clean reset while retaining Step 5B;
- move atomic binary STL export into Step 5C and require a Current,
  source-matched, watertight finalized shell plus a Current Step 5B sleeve.

Synthetic Slicer-native verification passed for both plane sides, curve cut
and capping, source preservation, watertight output, clean auxiliary deletion,
raw-shell export rejection, binary STL output, lineage propagation, MRB
save/reload, and the complete pre-existing test class. The source-build
process still reports its known VTK debug leaks after the explicit full-suite
pass marker.

The 2026-08-10 ROI-frame corrections passed Python compilation, UI XML
parsing, repository static checks, and added camera-math, ROI-lock, and
ROI-Z-only plane regressions. Live yaw/zoom interaction, constrained height
placement, layout/camera restoration, initial viewport fit, and FPS remain
pending developer-run Slicer acceptance; no new Slicer process was authorized
or launched for these corrections.

The plane starts without an anatomical default after the user requests a new
height, and the earlier expert suggestion of roughly 70–80 percent tooth
coverage is not encoded. A dental/occlusal frame, gingival-margin detection,
fit/contact validation, and any automatic trim recommendation require
representative data and dentist-approved definitions.

### Later Step 5 increments

Next, exercise Steps 5B/5C with representative reviewed anatomy and dentist
input; define intended contact/removal behavior, cervical/gingival margin,
dental orientation frame, Entry surface semantics, hard-invalid versus warning
states, physical sleeve/bit fit, print orientation, material/process
constraints, and a saved planning report. Parameter values and manual margins
remain research inputs until the team supplies validation data.

## Step 6: Registration and calibration

**Status:** planned

Goal: establish explicit transforms among image, patient/tooth, tool, tracker,
and robot frames.

Potential scope:

- image and physical landmarks
- paired-point registration
- registration transform node and frame tree
- FRE and independent target validation
- tool-tip/pivot and hand-eye calibration as required
- validity, timestamp, and invalidation state

## Step 7: Simulated navigation

**Status:** planned

Goal: validate navigation metrics without physical hardware.

Potential scope:

- virtual bur and robot geometry
- simulated transform streams
- drill-tip and axis visualization
- depth, lateral, angular, and target error
- sequence recording and deterministic playback
- fault and stale-transform simulation

## Step 8: Robot adapter and motion simulation

**Status:** planned; transport undecided

Goal: define high-level robot interaction independently of vendor transport.

Potential scope:

- `RobotAdapter` interface and capabilities
- connection/state/fault model
- approved-plan transfer
- motion simulation and collision checks
- request/cancel semantics
- command/event logging

ROS decision gate:

- Identify robot/vendor APIs and timing requirements.
- Compare direct SDK/IPC/TCP against ROS2 and MoveIt.
- Adopt ROS only if existing drivers, motion-planning integration,
  distributed-node needs, or tooling justify its operational cost.

## Step 9: Supervised hardware integration

**Status:** future research scope

Goal: connect the validated adapter to research hardware while keeping
safety-critical behavior outside Slicer.

This step requires a separate hazard analysis, emergency-stop design,
workspace/limit enforcement, communication-loss behavior, and supervised
bench validation before any specimen or patient-context work.

## Step 10: Reproducibility, validation, and custom application packaging

**Status:** planned

Goal: turn the stable workflow into a reproducible DENTOBOT research
application.

Implementation themes:

- representative de-identified datasets and ground truth
- segmentation, planning, registration, and navigation metrics
- automated Slicer/backend contract tests
- validated top-level manifests, complete transitive environment lock, model
  inventory/hashes, and clean-machine reconstruction
- case/procedure audit bundle
- extension packaging and backend setup tooling
- Slicer Custom Application Template integration
- DENTOBOT branding, home module, reduced module set, simplified chrome
- installer and clean-machine acceptance testing

The custom application must reuse the validated extension and contracts; it
must not introduce a second workflow implementation.
