# DENTOBOT Development Plan

## Development policy

- Implement one authorized milestone at a time.
- Prefer a small working vertical slice over disconnected feature fragments.
- Keep the stock Slicer runtime unchanged during extension development.
- Test Slicer and WSL components in their own environments.
- Advance only after acceptance evidence and a short milestone review.
- Future milestones are a blueprint, not authorization to implement them.

## Current baseline: imaging plus external-process bridge

**Status:** Step 0 and Bridge A/B work in the developer's Windows Slicer
workflow. Bridge C completed the established real-CBCT CUDA run with 60
validated segments. On 2026-07-31 the migrated native-Ubuntu path also passed:
13 backend tests, the complete Slicer-native workflow suite, standalone CPU
inference on a public dental CBCT, 54-label Slicer import/closed-surface
creation, and a 25.7 MB MRB save. The Ubuntu run used Slicer 5.10, Python
3.12.3, PyTorch 2.10.0+cpu, and TotalSegmentator 2.16.0. This establishes an
engineering compatibility path, not anatomical or clinical accuracy.
Cancellation/error paths, a complete transitive dependency lock, independent
MRB reopen verification, and anatomical validation remain pending.

The Extension Wizard scaffold and exploratory trajectory code exist, but the
trajectory-first sequence has been superseded. The extension project is now
named DENTOBOT, and all new module identifiers use the `DENTO` prefix. The
project begins with the focused `DENTOWorkflow` shell, then establishes
independent external inference before returning to segmentation review and
trajectory planning.

Acceptance criteria:

- Project context, architecture, agent rules, and roadmap agree.
- Early extension development and later custom-app packaging are distinct.
- External inference is isolated from Slicer's Python environment.
- Slicer controls inference through a direct asynchronous argument-list
  process adapter (`wsl.exe` on Windows, local Linux Python on Ubuntu) rather
  than a watched-folder job system.
- ROS is deferred to a documented robotics decision gate.
- Timestamped low-level development history is maintained in `changelog.md`
  and `logbook.md`.
- Installed Slicer files and Slicer's embedded Python environment remain
  unchanged.

### Immediate Ubuntu task set after the 2026-07-31 checkpoint

Execute these in order. Do not start another expensive segmentation run until
the preceding gate is closed.

1. **Deterministic process shutdown — completed 2026-08-03:** the Slicer 5.10
   `QProcess` fallback now has explicit parent ownership and disconnect/close/
   delete-later teardown. Two consecutive health-only probes completed in
   7.76 and 5.91 seconds with successful CPU health, clean Slicer/backend
   exits, and no disposable container left behind. No segmentation ran.
2. **Clean image reconstruction — next:** build
   `Infrastructure/Dockerfile.ubuntu-cpu` from scratch and run `pip check`, all
   backend tests, Bridge A health, and the Slicer-native test class. Gate: no
   dependency installation or manual repair inside the resulting container.
3. **NPU visibility only:** map `/dev/accel/accel0` and the render device into
   a disposable container and record OpenVINO device discovery. Gate: report
   only visibility/driver evidence; do not run or claim dental inference on
   NPU.
4. **Scene persistence:** reopen the saved Ubuntu MRB in a new Slicer process
   and verify the source reference, 54 segments, closed surfaces, review
   metadata, and CPU provenance. Gate: the fresh Slicer process also exits
   cleanly.
5. **Bounded bridge regression:** run Bridge B once. Run Bridge C again only
   if source changed after this checkpoint or a specific unresolved contract
   requires it. Apply a 15-minute wall-clock cap and inspect child processes
   before retrying any failure.
6. **Planning continuation:** after the Ubuntu runtime gates, resume Step 4B
   dentist-focused 2D planning design. Keep robot motion and drilling outside
   scope until their later safety gate.

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

**Status:** health, NIfTI round trip, and explicit-device `segment-teeth` are
implemented. The Windows WSL/CUDA evidence remains valid. On Ubuntu, 13
ordinary-Python tests and explicit CPU health passed; cached tasks 113, 115,
and transitive crop task 298 completed a public-CBCT inference in 217.85
seconds. Exact Ubuntu top-level constraints and a container build/install
recipe are present, but a complete platform-specific transitive lock and
clean-image rebuild remain pending.

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

1. Backend tests run entirely in the isolated external Python environment.
2. Health identifies and enforces the explicitly requested CPU or CUDA device.
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

**Status:** Windows CUDA and Ubuntu CPU happy paths verified; robustness and
clinical/anatomical validation remain

Goal: run the validated external backend from DENTOBOT and receive a
segmentation in the MRML scene.

Implementation:

- Add output segmentation state, a GPU Run action, Cancel, progress, live log,
  and compact metrics to the focused workflow UI.
- Export the selected CBCT to an isolated run-artifact directory as NIfTI.
- Invoke the configured external Python interpreter through the platform
  adapter with an argument-safe, asynchronous process call; do not create a
  watched-folder queue.
- Stream progress without freezing the UI and support cancellation.
- Handle the process exit code and validate result metadata and NIfTI geometry.
- Import labels into a `vtkMRMLSegmentationNode` with names and source links.
- Create binary-labelmap and closed-surface representations for immediate 2D
  and 3D display.
- Store backend metadata as `DENTOBOT.*` attributes and parameter-node state.
- Require an explicit `cpu` or `cuda:0` device and reject an unavailable
  request without fallback.
- Prevent implicit model acquisition by replacing TotalSegmentator's runtime
  downloader with a cache-only guard for tasks 113, 115, and transitive crop
  task 298.

Acceptance criteria:

1. One button runs the `teeth` task on the selected CBCT.
2. Dependency, CUDA, model, process, cancellation, and inference failures are
   distinguishable.
3. A successful run creates a correctly aligned segmentation node.
4. Label names and run metadata are available in the scene.
5. Original CBCT/DICOM data and the Slicer installation remain unchanged.
6. Scene save/reopen retains source and output node references.

Current Windows and Ubuntu evidence satisfies criteria 1, 3, 4, and 5 for
representative CBCTs. Ubuntu also saved an MRB containing the imported
segmentation, but an independent reopen inspection remains for criterion 6.
Distinct cancellation, out-of-memory, and malformed-output cases remain.
Visual alignment is not anatomical ground-truth validation.

### Deferred Bridge C validation backlog

The developer elected to continue beyond the verified happy path and return to
the following work later. Deferral is non-blocking for Step 3, but these items
remain required before a reproducible release or robustness claim:

1. preserve the passing 13-test Ubuntu backend baseline and rerun the complete
   suite from a clean rebuilt image;
2. exercise missing dependency, missing model, unavailable CPU/CUDA, and
   device-mismatch paths;
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

**Status:** Step 4A developer-verified on the retained teeth phantom in Slicer
5.12.2 at the current PoC interaction scope; Step 4B dentist-focused 2D
orientation design, Ubuntu Slicer 5.10 compatibility and scene persistence,
and clinical semantics remain unresolved. Confirmed trajectory deletion is
implemented and statically verified; its Slicer-native persistence test is
pending.

Goal: define a procedure-specific entry-to-target drill trajectory against
reviewed anatomy.

Step 4A implemented scope:

- filter the authoritative segmentation to whole-tooth target candidates;
- persist one target segment ID with the workflow parameter node;
- create or select a persistent `vtkMRMLMarkupsLineNode`;
- associate the line with its target segmentation and segment using an MRML
  node reference and `DENTOBOT.*` attributes;
- label control point 0 as Entry and control point 1 as Target;
- display both points in world RAS millimetres and calculate non-zero
  Euclidean length;
- clear stale target associations when the segmentation or segment changes;
- present the result explicitly as a draft research input rather than an
  approved drilling plan.
- give the selected target priority over Step 3 review highlighting in both
  2D and 3D;
- generate a locked visible axis-aligned world-RAS bounding box from the
  active tooth surface and reject/restore points that leave it;
- explicitly rebind Slicer placement to the selected Markups line so one line
  receives exactly Entry and Target rather than creating fiducial lists;
- provide Undo Last Point, confirmed Clear Both Points, and lock/unlock for a
  complete valid pair;
- provide a separate confirmed Delete Selected Trajectory action, restricted
  to the DENTOBOT trajectory role, that clears its workflow reference and
  removes only the line and unshared auxiliaries while retaining target state.

The developer reports that the corrected Step 4A interaction works as
intended on the retained teeth phantom. This accepts the current target,
bounds, two-point placement, and correction-control behavior for fast-track
PoC development. It does not establish anatomical accuracy, a clinically
meaningful entry or target, an approved plan, or Ubuntu compatibility.
Earlier isolated automated Slicer runs are retained as diagnostic history,
not as the acceptance authority. Live Slicer validation is developer-run
unless explicit authorization is renewed for a specific automated action;
ordinary-Python logic tests and static checks remain required for every
increment.

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

The reusable two-point creation and length concepts from the disabled legacy
experiment have now been migrated into DENTO Workflow with target-tooth
association, persistence, stale-reference handling, and draft-only safety
language. The remaining themes above are not implemented by this increment.

Step 4B dentist-focused 2D planning scope:

- make 2D slice placement the primary workflow and treat 3D placement as
  secondary;
- provide one action to focus slice views on the selected target and bounds;
- define the intended planning plane before implementing orientation lock:
  scanner axial, dental occlusal, and tooth-local planes are not equivalent;
- once the reference plane is accepted, lock slice rotation while preserving
  deliberate slice scrolling through the target;
- evaluate projection visibility, point jumping, zoom, and cross-view
  synchronization with the dentist rather than optimizing for a non-clinical
  operator;
- retain the current 3D view for context and verification, not as the primary
  precision-placement interface.

## Step 5: Target-region modeling and template research

**Status:** Steps 5A, 5B, and 5C implemented and synthetically verified;
developer/dentist anatomical and interaction acceptance pending

### Step 5A — draft template support anatomy

The workflow reuses the Step 4A target and lets the user manually select any
positive number of distinct additional whole-tooth segments from the same
Reviewed authoritative segmentation. It deliberately has no automatic
adjacency, arch, side, or maximum-count rule.

Step 5A appends unmodified closed-surface copies of the target and selected
supports into one traceable `vtkMRMLModelNode`, preserves the segmentation's
parent transform, and persists selection/provenance. Changed inputs retain the
last output as Stale until the user explicitly updates it. A dedicated
confirmed delete action is restricted to the DENTOBOT draft-model role; it
clears the model reference and removes only the model and unshared auxiliaries
while preserving target and support selection for recreation.

Developer-run Slicer acceptance must exercise small and large selections,
including two and ten supports, plus create/update, scene save/reopen,
selection persistence, source-edit invalidation, and Current/Stale
presentation. Slicer-native lifecycle coverage has passed for trajectory/model
deletion, retained inputs, save/reload, and recreation.

Step 5A is source support anatomy only. It excludes smoothing, remeshing,
Boolean operations, offsets, contact inference, gingival clearance,
shell/sleeve/drill-channel generation, export, printability, clinical
validation, and drilling authorization.

### Step 5B — model-independent raw research shell and sleeve

Step 5B requires the current role-gated Step 5A model and a complete locked
Entry/Target trajectory. It creates a separately owned world-RAS Markups ROI,
samples an exterior clearance/thickness band around the anatomy inside that
ROI, subtracts a trajectory-aligned channel, and creates a separate watertight
annular sleeve extending outward from Entry.

The shell ROI selector accepts only the Step 5B role and matching Step 5A
source. Reset, generation, and deletion repeat those checks in logic; legacy
Step 4A bounds contaminated with Step 5B metadata are repaired in place.
Deleting the ROI retains upstream state and generated models but marks the
models Stale. Scene visibility controls cover the selected Step 4A bounds and
trajectory, Step 5A support model, and Step 5B ROI/shell/sleeve. Output nodes
persist explicit sources, parameters, topology metrics, and Current/Stale
state. Step 5B deliberately does not expose STL export for its unfinalized raw
shell.

Synthetic Slicer-native verification passed for geometry generation,
watertight topology, MRB save/reload, strict ROI role/source isolation, legacy
cross-role repair, output deletion/recreation, and existing workflow
regressions. The public EndoPlanner preview informed comparison only; its
trained weights and several called helpers are absent from the public checkout.

### Step 5C — dentist-directed fit, margin trim, and STL export

Step 5C preserves the Step 5B shell as a non-destructive source and creates a
separate role-owned finalized shell. **Continue: Isolate Shell in Front View**
preserves prior visibility, shows the source shell alone, and establishes an
anterior parallel-projection world-RAS camera. The optional lock keeps R/L
horizontal and S/I vertical while allowing zoom and edit translation; this is
not yet a scanner-independent dental or occlusal frame.

The simple path places a one-click Markups plane height and runs Dynamic
Modeler Plane Cut with a capped positive/negative kept-side choice. The
uneven-margin path uses an adjustable, surface-snapped Markups closed curve,
runs Dynamic Modeler Curve Cut with inside/outside selection, then caps,
triangulates, cleans, and orients the retained surface. Empty or non-watertight
finalized geometry is rejected. The method, region, markup geometry,
source/edit/Dynamic-Modeler references, source revision, and topology metrics
persist through MRB save/reopen; any relevant change makes the result Stale.

The built-in Dynamic Modeler module remains available as an expert handoff,
but DENTOBOT export accepts only its own Current, source-matched, watertight
Step 5C shell plus the Current Step 5B sleeve. Confirmed Step 5C reset removes
only its role-owned markups, finalized shell, Dynamic Modeler node, and cut
auxiliaries. Confirmed Step 5B deletion cascades through those descendants.

Synthetic Slicer-native verification passed for both plane sides, Curve Cut
and capping, source preservation, watertight output, clean auxiliary deletion,
raw-shell export rejection, binary STL output, lineage propagation, MRB
save/reload, UI loading, anterior-view preparation, and the complete existing
test class. The Slicer source build reports known VTK debug leaks after the
explicit full-suite pass marker.

The earlier expert suggestion of roughly 70–80 percent tooth coverage is not
encoded. A dental/occlusal frame, gingival-margin detection, fit/contact
validation, and automatic trim recommendation require representative data and
dentist-approved definitions.

### Later Step 5 increments

Exercise Steps 5B/5C with representative reviewed anatomy and dentist input;
define intended contact/removal behavior, cervical/gingival margin, dental
orientation frame, Entry surface semantics, hard-invalid versus warning
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
