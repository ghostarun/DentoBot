# DENTOBOT Agent Instructions

## Purpose and authority

DENTOBOT is a research prototype for a focused, image-guided,
robot-assisted dental drilling workflow built on 3D Slicer.

These instructions govern all agent work in this repository. Read
`PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `DEVELOPMENT_PLAN.md`, `changelog.md`,
and `logbook.md` before substantial implementation. Work only on the
milestone explicitly authorized by the user. Roadmap items are context, not
permission.

DENTOBOT is not validated clinical software and must not be described or
used as an autonomous patient-treatment system.

## Current state and authorized next milestone

- The CMake extension project is named `DENTOBOT`; the workspace directory
  retains its older name for continuity.
- All new Slicer modules use `DENTO` plus PascalCase, such as
  `DENTOWorkflow`, `DENTOSegmentation`, `DENTORegistration`, and
  `DENTOTrajectory`.
- The legacy `DentalNavPlanning` scaffold still contains generated threshold
  code and an exploratory trajectory experiment, but it is no longer included
  in the extension build.
- The earlier trajectory-first plan has been superseded.
- **Step 0: Minimal workflow shell and DICOM viewer** is implemented in
  `DENTOWorkflow`; the developer has reported that its current workflow works.
- **Bridge A and Bridge B** are implemented and work in the developer's
  workflow. The standalone WSL
  package tests and CUDA health command pass in the recreated `dentobot`
  environment, and the developer reports that the non-WSL Slicer-native tests
  pass. Slicer-originated Bridge A reached the adapter, and the first Bridge B
  attempt reached WSL/live output but exposed slow compressed-NIfTI checksum
  behavior. After the source fix, the complete Bridge B Slicer/WSL/MRML round
  trip passed first with a synthetic Slicer test volume and then with the
  explicitly selected real CBCT after the selector-authority fix.
  Bridge A checks the configured WSL Python and CUDA runtime. Bridge B exports
  the explicitly selected scalar volume, performs a geometry-preserving NIfTI
  round trip in WSL, validates the result, and imports it into MRML.
- **Bridge C's core runtime path is verified by developer-supplied Slicer
  evidence.** A real 580 x 580 x 300 CBCT at 0.25 mm isotropic spacing completed
  the GPU-only `segment-teeth` path in Slicer 5.12.2. TotalSegmentator teeth
  task 113 and craniofacial crop task 115 produced 60 validated segments; the
  module imported and displayed them in aligned 2D slice overlays and a 3D
  closed-surface view. Reported metrics were 75.2 seconds total runtime,
  48.65 cm^3 foreground, and 2.16 GiB peak GPU allocation. Do not extend this
  evidence to anatomical/clinical accuracy, the five new WSL unit tests,
  cancellation/error-path behavior, or MRB save/reopen persistence; those
  remain separately pending.
- Bridge C's validated top-level dependencies and formal reconstruction and
  traceability procedure are recorded in
  `REPRODUCIBILITY_AND_TRACEABILITY.md`. This is not yet a complete transitive
  lock or clean-machine reconstruction. The developer has explicitly deferred
  the remaining Bridge C failure, cancellation, persistence, and accuracy
  checks; keep them on the roadmap and do not silently treat them as passed.
- **The native-Ubuntu CPU compatibility path is engineering-verified in the
  SlicerROS2 Slicer 5.10 container as of 2026-07-31.** The repository is on
  `codex/ubuntu-migration` from published feature hash
  `72da94207d33234a12f5d904c23733ff382f9e43`. The local process adapter,
  explicit CPU device, 13 backend tests, full Slicer-native test class,
  public-fixture standalone inference, 54-label MRML import/closed surfaces,
  and MRB save passed. The run does not establish anatomical or clinical
  accuracy, a clean-image rebuild, cancellation robustness, or robot/hardware
  readiness. TotalSegmentator requires cached tasks 113, 115, and transitive
  crop task 298. OpenVINO discovery is separate from inference; do not claim
  the Intel NPU runs the nnU-Net dental model without a converted and validated
  model path.
- Slicer-launched Bridge A and Bridge C subsequently produced successful
  reports, including 54 imported segments and a saved MRB. The earlier
  headless shutdown defect is closed as of 2026-08-03: the Slicer 5.10
  `QProcess` fallback now releases its signal callbacks and process object,
  and two consecutive network-disabled Bridge A health probes exited cleanly
  in disposable checkpoint-image containers. No segmentation was rerun.
- **Step 3A exploration and Step 3B inspection/provenance are developer-
  verified in Slicer 5.12.2.** The developer reports that the implemented
  review workflow works as intended, including its universal
  segmentation-level review state. Do not reinterpret that state as
  per-label approval or anatomical/clinical validation.
- **Step 3C correction handoff is developer-verified in Slicer 5.12.2.** The
  developer completed the full acceptance checklist: the selected label,
  authoritative segmentation, and persisted source CBCT were correctly handed
  to Slicer's built-in Segment Editor; correction changed the universal state
  to `Needs Correction`; baseline-metric messaging and correction activity
  were shown; and the MRB scene round trip preserved the expected state.
  Source-representation edits and segment addition/removal are observed while
  DENTO Workflow is active; display, naming, selection, and provenance changes
  do not invalidate review. This evidence confirms workflow behavior, not
  anatomical or clinical accuracy.
- **The Step 4A target-tooth and trajectory-input foundation is developer-
  verified on the retained teeth phantom in Slicer 5.12.2 at the current PoC
  interaction scope.** DENTO Workflow now filters the
  authoritative segmentation to whole-tooth targets, persists one selected
  segment ID, makes that target the priority 2D/3D highlight, creates a locked
  visible world-RAS bounding-box ROI, and rejects trajectory points outside
  it. The workflow creates/selects one two-point Markups line, labels its
  points Entry and Target, displays its geometric length, offers undo/reset
  and pair locking, and associates the line with the target segmentation,
  segment, and bounds. The implementation
  deliberately excludes procedure semantics, plan approval, anatomical safety
  checks, template generation, registration, and drilling authorization. Its
  first manual test exposed five interaction defects; after the correction
  batch, the developer reported that the target highlight, target bounds,
  paired placement, and edit/lock controls work as intended. Earlier isolated
  automated Slicer results remain diagnostic history and are not the
  acceptance authority. Current working policy prioritizes rigorous
  ordinary-Python logic tests and static checks, while the developer performs
  live Slicer acceptance unless explicit authorization is renewed for a
  specific automated runtime action. Dentist-focused 2D orientation/focus
  locking is a Step 4B design problem because the intended reference plane is
  not yet specified. Compatibility and scene-persistence verification remain
  pending in the Ubuntu Slicer 5.10 container.
- **Explicit Step 4A trajectory deletion is implemented and statically
  verified.** A dedicated confirmed action accepts only a DENTOBOT
  `EntryToTarget` line, clears its workflow reference, and removes only that
  line plus unshared display/storage auxiliaries. It preserves the reviewed
  segmentation, target tooth, bounds, shared auxiliaries, and unrelated user
  nodes. Added Slicer-native save/reload/recreate coverage has not yet run.

## Product strategy
- **Step 5A draft support-anatomy modeling is implemented in source and awaits
  developer-run Slicer acceptance.** It reuses the Step 4A target and accepts
  any positive number of manually checked, distinct whole-tooth supports from
  the same Reviewed segmentation, with no inferred adjacency or maximum count.
  It creates/updates one transform-preserving, provenance-bearing draft model
  from unmodified closed surfaces and marks it Stale after input changes.
  Slicer-native logic coverage for two and ten supports was added but was not
  run in the implementation session. Do not describe this output as a guide,
  contact design, printable template, clinical validation, or drilling
  authorization.
- Step 5A now has a separate confirmed delete action for the DENTOBOT draft
  model. It preserves the target and ordered manual support selection so the
  model can be recreated, and applies the same unshared-auxiliary rule as
  trajectory deletion. Runtime deletion/persistence acceptance remains
  pending.


Use two deliberate phases:

1. **Workflow development:** build the focused DENTOBOT scripted extension that runs
   inside an official installed Slicer build. Reuse Slicer DICOM, MRML,
   slice/3D views, segmentations, markups, transforms, and scene persistence.
2. **Custom application packaging:** after the workflow is stable, use the
   Slicer Custom Application Template or supported Slicer build options to
   brand the application and omit irrelevant modules and chrome.

Do not copy or fork Slicer DICOM/viewer internals into a standalone GUI.
Do not build a custom Slicer application during early workflow milestones.

## Architectural boundaries

### Slicer layer

- Keep user workflow, MRML orchestration, visualization, interaction, and
  scene persistence in Slicer scripted modules.
- Use MRML nodes as the shared in-application data model.
- Keep UI event handling in widget classes and reusable scene operations in
  logic classes.
- Use Qt Designer `.ui` files and Slicer MRML-aware widgets.
- Store persistent selections and settings in typed parameter nodes.

### External compute layer

- Put AI inference and other dependency-heavy computation in the versioned
  `Inference/` Python package, executed in an isolated WSL2 environment.
- Slicer must not import PyTorch, TotalSegmentator, nnU-Net, or CUDA packages.
- Invoke the WSL backend directly from Slicer as an asynchronous external
  process using `wsl.exe`, an explicit distribution, an explicit Python
  interpreter, and an argument list.
- Use NIfTI as the volume payload, structured standard output for live status,
  process exit codes for terminal status, and JSON for result metadata.
- Do not introduce a watched-folder queue, polling worker, or persistent
  service in the baseline implementation. Add a service only after a measured
  requirement justifies its lifecycle and deployment complexity.
- Do not pass geometry-free NumPy arrays across the boundary.

### Robot layer

- Keep real-time control, safety interlocks, emergency stop, servo loops,
  and hardware motion execution outside Slicer and outside the UI process.
- Use a transport-neutral robot adapter. ROS/ROS2 is not a default dependency.
- Reconsider ROS only at the later robotics architecture gate.

## Protection of Slicer and source data

- Never edit files in an installed Slicer directory.
- Never install Slicer extensions or Python packages automatically.
- Never launch Slicer, WSL processes, installers, or model downloads without
  explicit user authorization for that action.
- Never use system Python to execute a Slicer module.
- Never modify or delete original patient DICOM data. Use non-destructive,
  de-identified working copies when cleanup is required.
- Treat DICOM paths, logs, screenshots, and metadata as potentially
  identifying research data.
- Do not build or modify the upstream Slicer source tree during extension
  development.

## Slicer rules

- `slicer`, `qt`, `ctk`, VTK-wrapped MRML classes, and qMRML widgets are
  available only inside Slicer.
- Use `qMRMLNodeComboBox` or another MRML-aware widget for node selection.
- Slicer internal positions are world RAS coordinates in millimetres.
- DICOM data is normally LPS on disk and converted by Slicer on import.
- Volume arrays use KJI order; transform IJK through the volume geometry
  before treating a voxel position as RAS.
- Preserve source volume geometry. Represent registration and tracking with
  transform nodes rather than hardening transforms without justification.
- Clean up all MRML observers during scene close, module exit, and widget
  cleanup.

## External inference execution rules

- Every inference run must have a unique run ID and isolated artifact
  directory. The directory is staging and evidence, not a queue or control
  mechanism.
- The Slicer adapter owns process launch, live output handling, cancellation,
  exit-status handling, output validation, and MRML import.
- Pass arguments directly to the process API. Never build an unescaped shell
  command from user-controlled paths or settings.
- Inputs and outputs must include physical geometry and label metadata.
- Validate output shape, spacing, direction/affine, label type, and label map
  before importing a result into the MRML scene.
- Record backend, model/task, package versions, requested and actual device,
  runtime, timestamps, status, and errors in a JSON result document.
- CPU fallback after a GPU failure must be explicit; never silently turn a
  short GPU run into a potentially long CPU run.
- Do not send patient data to cloud services unless a later, separately
  approved data-governance plan allows it.

## Documentation and traceability rules

- `changelog.md` is the low-level, textual version history of material
  repository changes. Record what changed, what was preserved or removed,
  validation performed, and any known limitations.
- `logbook.md` is the low-level session record. Record material ideas,
  decisions, prompt/request summaries, experiments, failures, diagnoses,
  fixes, reversions, unresolved questions, and next actions.
- Add an explicit timestamp with timezone to every new entry. A single
  timestamp may cover one cohesive batch when separate timestamps would be
  redundant. For reconstructed history, state that the original event time is
  unavailable and record when the reconstruction was written.
- Update both files during every material implementation or architecture
  change. A discussion-only session normally updates `logbook.md`; it updates
  `changelog.md` only when repository state or an accepted specification
  changes.
- Preserve history. Do not silently rewrite an earlier decision after it is
  superseded; add a later entry that states what replaced it and why.
- Never place patient identifiers, credentials, tokens, or other secrets in
  either file.
- `REPRODUCIBILITY_AND_TRACEABILITY.md` is the controlled professional source
  for inference installation, dependency baselines, environment evidence,
  diagnostic bundles, and reconstruction. Do not use `changelog.md` or
  `logbook.md` as the installation procedure.
- The repository `docs/` directory is the canonical documentation source. Its
  eight Markdown files are mirrored as raw `.md` files in the connected Google
  Drive folder `IITM Dentobot/docs`:
  `https://drive.google.com/drive/folders/1M5uicX_Vkk2Y130p5k4rme1TjfavWJuO`.
- Preserve these Drive file IDs during synchronization:
  `AGENTS.md` = `1hXoq1I_3IgUeMPmyrUJc7LecDvFswACJ`;
  `ARCHITECTURE.md` = `1hA49tz-wZwbr6v2F6HTWG1Zgjy4TR1J5`;
  `DEVELOPMENT_PLAN.md` = `1u0lCVRoRKX-rXZtL56ZfciQmPFizG4rJ`;
  `PROJECT_CONTEXT.md` = `1w-ZyVP5neW_uOljPntXUxdaqHRR0Q4Yw`;
  `REPRODUCIBILITY_AND_TRACEABILITY.md` =
  `1urW1C4iTqaMLqavON10zbRNnPnEm83Hf`;
  `UBUNTU_TRANSFER.md` = `1lQ9QJFInl-FM-OuqOBJBIcNmLCjrc0_X`;
  `changelog.md` = `1C2LbkEE914W_xzAcBMMcTcMBJm_suAQl`;
  `logbook.md` = `1zBztLFd-es_91NglYrHYJ-rtYEQ0at6E`.
- The active Ubuntu wrapper controls and dated notes are also tracked in this
  repository under `Workspace/`. Their top-level workspace paths are
  compatibility symlinks, and their separate
  `IITM Dentobot/active-development-ubuntu` Drive IDs remain authoritative for
  that mirror. Do not merge same-named files across the two Drive folders.
- Whenever the user asks to update `changelog.md` or `logbook.md`, update the
  local canonical files first and, when the connected Drive is available,
  replace the bytes of their corresponding Drive files in place. Also sync any
  other local design document changed in the same batch. Preserve existing
  Drive file IDs instead of creating duplicate versions, then verify the
  mirrored folder contents before handoff.
- Documentation mirroring does not authorize uploading DICOM, NIfTI,
  segmentations, run artifacts, patient information, credentials, or any
  non-document project data.

## Coding conventions

- Prefer small vertical slices that leave the current application usable.
- Use type hints for public Python interfaces.
- Validate inputs at subsystem boundaries and raise actionable exceptions.
- Log important state transitions and unexpected failures; expected negative
  tests must not be presented as application errors.
- Avoid global mutable state and hidden environment mutation.
- Use stable, namespaced MRML attributes such as `DENTOBOT.*`.
- Keep backend code independent of Slicer so it can be tested with ordinary
  Python inside WSL2.
- Pin and lock external backend dependencies after compatibility validation.

## Naming conventions

- Product, extension project, and later custom application: `DENTOBOT`.
- Slicer module identifiers and Python classes: `DENTO` plus PascalCase.
- Human-facing module titles may contain spaces, for example `DENTO Workflow`.
- External Python distribution/CLI: `dentobot-inference`; import package:
  `dentobot_inference`.
- Do not introduce new `DentalNav*` or `DentalDrillNav*` identifiers. Preserve
  old names only when recording history or referring to the disabled legacy
  scaffold.

## Required working method

Before editing:

1. Read the governing documents and inspect the relevant code/configuration.
2. Explain the proposed behavior and identify files to be changed.
3. Resolve Slicer-versus-backend ownership explicitly.
4. Review the latest `changelog.md` and `logbook.md` entries for unfinished
   work, failures, and superseded decisions.

After editing:

1. Review the complete diff and confirm unrelated files were not changed.
2. Run only tests authorized in the appropriate environment.
3. State exactly what was tested, where it ran, and what remains manual.
4. Never claim a Slicer, WSL, GPU, robot, or hardware test passed unless it
   actually ran in that environment.
5. Update `changelog.md` and `logbook.md` before handoff whenever the work is
   material under the traceability rules above.
6. If the task includes a changelog/logbook update, complete and verify the
   Google Drive mirror described in the documentation rules before handoff
   whenever the connector is available.

## Standing close-day protocol

The phrases **"close my day"** and **"close the day"** are standing
authorization to execute this protocol for the current repository. The phrase
does not authorize a force-push, robot/hardware motion, deletion of research
data, or upload of patient data, model weights, runtime artifacts, credentials,
or secrets.

1. Inspect the current branch, upstream, status, diff, and recent commits.
   Separate intended work from pre-existing or unrelated changes; never stage
   unrelated files.
2. Run `Infrastructure/close_day_checks.sh`, supplying
   `DENTOBOT_BACKEND_PYTHON` when the dedicated backend exists. Run any
   additional environment-specific checks needed for work performed that day.
3. Update `logbook.md` newest-first with the request, decisions, experiments,
   failures and diagnoses, exact evidence, unresolved risks, and tomorrow's
   first actions. Update `changelog.md` and any controlled architecture,
   roadmap, reproducibility, or transfer document affected by the work.
4. State accomplishments in two frames: today's explicit agenda and the
   overall development plan. Keep research/engineering evidence distinct from
   anatomical, clinical, robot, or hardware validation.
5. Review the complete diff, stage only intended repository files, and create
   one descriptive Git commit. Create an annotated tag named
   `checkpoint/YYYY-MM-DD-HHMM-IST` at that commit.
6. Push the current branch and tag without force when an upstream exists or
   can be safely established. If authentication or network access prevents the
   push, preserve the local commit/tag and report the exact blocker.
7. Replace changed controlled Markdown bytes in the existing Drive files,
   preserving the IDs listed above. Reconcile Ubuntu-only active-development
   notes rather than overwriting their history. Verify names, IDs, modified
   state, and content after synchronization.
8. Report the commit hash, tag, push result, Drive synchronization result,
   checks run, remaining limitations, and tomorrow's first concrete command or
   task. A close is complete only when every step either succeeded or has an
   explicit recorded blocker.
