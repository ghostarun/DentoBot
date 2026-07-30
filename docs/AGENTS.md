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
- **The Step 4 target-tooth and trajectory-input foundation is implemented in
  source but not yet runtime-verified.** DENTO Workflow now filters the
  authoritative segmentation to whole-tooth targets, persists one selected
  segment ID, creates/selects a two-point Markups line, labels its world-RAS
  points as Entry and Target, displays its geometric length, and associates
  the line with the target segmentation and segment. The implementation
  deliberately excludes procedure semantics, plan approval, anatomical safety
  checks, template generation, registration, and drilling authorization. Its
  Slicer-native tests and manual MRB round trip remain pending in Slicer
  5.12.2 and later require compatibility verification in the Ubuntu Slicer
  5.10 container.

## Product strategy

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
  seven Markdown files are mirrored as raw `.md` files in the connected Google
  Drive folder `IITM Dentobot/docs`:
  `https://drive.google.com/drive/folders/1M5uicX_Vkk2Y130p5k4rme1TjfavWJuO`.
- Preserve these Drive file IDs during synchronization:
  `AGENTS.md` = `1hXoq1I_3IgUeMPmyrUJc7LecDvFswACJ`;
  `ARCHITECTURE.md` = `1hA49tz-wZwbr6v2F6HTWG1Zgjy4TR1J5`;
  `DEVELOPMENT_PLAN.md` = `1u0lCVRoRKX-rXZtL56ZfciQmPFizG4rJ`;
  `PROJECT_CONTEXT.md` = `1w-ZyVP5neW_uOljPntXUxdaqHRR0Q4Yw`;
  `REPRODUCIBILITY_AND_TRACEABILITY.md` =
  `1urW1C4iTqaMLqavON10zbRNnPnEm83Hf`;
  `changelog.md` = `1C2LbkEE914W_xzAcBMMcTcMBJm_suAQl`;
  `logbook.md` = `1zBztLFd-es_91NglYrHYJ-rtYEQ0at6E`.
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
