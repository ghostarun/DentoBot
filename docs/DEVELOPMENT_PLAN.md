# DENTOBOT Development Plan

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

**Status:** Steps 3A and 3B implemented in source; in-Slicer acceptance pending

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

Remaining Step 3 increments:

- richer opacity/color presets and optional anatomy presets
- correction handoff to Segment Editor
- approval invalidation after manual edits or source replacement

Step 3A acceptance requires an in-Slicer run against the retained 60-segment
Bridge C result: search for an FDI tooth, toggle it, emphasize and isolate it,
restore all labels, change 2D/3D opacity, switch segmentation nodes, and
confirm that scene saving preserves the selected node and display state.
Step 3B acceptance additionally requires checking a known label against
`result.json`, changing and persisting the segmentation-level workflow state,
and confirming that source reference, provenance, metrics, and review
timestamp survive MRB save/reopen. Later Step 3 acceptance will add editable
segments and edit-driven review invalidation.

## Step 4: Procedure definition and minimal trajectory planning

**Status:** planned; clinical semantics unresolved

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

## Step 5: Planning constraints and verification

**Status:** planned

Goal: quantify relationships between the plan and reviewed anatomy.

Potential scope:

- trajectory-to-segmentation intersection checks
- clearance and safety margins
- canal/tooth containment metrics
- entry-angle and depth constraints
- warnings distinct from hard-invalid states
- saved planning report

Thresholds require research-team decisions and validation data.

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
