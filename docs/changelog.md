# DENTOBOT Low-Level Changelog

## Purpose

This file is the append-oriented, textual version history for DENTOBOT. It
records material source, documentation, configuration, dependency, model, and
accepted-specification changes in enough detail for an AI coding agent or a
researcher to reconstruct how the repository evolved.

Every entry must contain an explicit date, time, and timezone. One timestamp
may cover a cohesive change batch when separate timestamps would be redundant.
Retrospective entries must state when they were recorded and whether the
original event time is unknown. Do not include patient identifiers, secrets,
or credentials.

Use newest-first ordering. Each entry should state:

- what changed and why;
- files or subsystems affected;
- behavior added, removed, preserved, or superseded;
- verification performed and its environment;
- limitations, pending validation, and whether anything was reverted.

## 2026-07-30 22:14:45 IST (UTC+05:30) — Step 4A automated Slicer acceptance

### Authorized verification

- After explicit developer authorization, launched isolated hidden Slicer
  5.12.2 processes without starting WSL, inference, CUDA, models, DICOM,
  robot, or hardware operations.
- Ran the complete `DENTOWorkflowTest` Slicer-native suite.
- Exercised the actual widget path with an already-existing synthetic
  segmentation containing one whole tooth, one pulp segment, and one jaw
  segment.
- Confirmed that selecting the segmentation enables Step 4A and produces one
  eligible FDI 16 target plus the placeholder.
- Selected and persisted `tooth-16`, created a
  `vtkMRMLMarkupsLineNode`, labelled its points Entry and Target, retained
  `SlicerRASmm` and `Draft` attributes, and verified the known 3-4-12
  trajectory length of 13.0 millimetres.
- Saved and reopened a synthetic MRB and confirmed restoration of the target
  segment ID, segmentation reference, trajectory reference, trajectory
  geometry, and trajectory-to-segmentation node reference.

### Test-harness findings and limitations

- The first widget-harness attempt constructed the widget without a parent,
  causing Slicer's base class to call `setup()` before subclass initialization.
  The harness was corrected to use Slicer's registered-widget construction
  pattern; no product source change was required.
- The first persistence fixture used empty segments and could not be stored as
  an MRB. Adding synthetic closed-surface representations corrected the
  fixture, after which save/reopen passed.
- The Windows app-control bridge was unavailable, so the test used Slicer's
  supported command-line/Python runtime rather than clicking the developer's
  visible Slicer instance.
- Manual point placement on the retained teeth phantom and Ubuntu Slicer 5.10
  compatibility remain pending. The disposable test script, result JSON, and
  synthetic MRB were removed after verification. Nothing in product source
  was reverted.

## 2026-07-30 20:39:31 IST (UTC+05:30) — Step 4A segmentation-selection refresh fix

### Observed and corrected

- During the first interactive Step 4A test, the developer reported that the
  target-tooth selector remained disabled after an existing segmentation was
  selected in the Step 3 review panel.
- Confirmed that Step 4A does not require a new inference run or any additional
  backend output. It consumes existing whole-tooth segment names ending in
  valid two-digit FDI codes.
- Added an explicit planning refresh after the review-segmentation selection
  handler. This avoids relying on parameter-node observer ordering that may
  differ across Slicer versions.
- Restored the agreed `Step 4A` identifier in the panel and controlled
  documentation.

### Verification and limitations

- Static Python parsing and UI XML/reference checks passed after the fix.
- Interactive retest in the developer's running Slicer session remains
  pending. No inference, WSL, CUDA, model, DICOM, or hardware process was
  launched for this correction.
- Selecting a tooth in the Step 3 explorer remains a non-destructive review
  highlight. The target must be explicitly chosen in Step 4A.

## 2026-07-30 18:25:34 IST (UTC+05:30) — Step 4A target-tooth and draft trajectory inputs

### Added and changed

- Added the Step 4A planning panel to DENTO Workflow.
- Added persistent `targetToothSegmentId` and
  `vtkMRMLMarkupsLineNode` parameter-node state.
- Restricted target choices to whole-tooth records from the authoritative
  segmentation. Pulp, canal, jaw, implant, restoration, and other anatomy
  remain reviewable but are excluded from target-tooth selection.
- Added draft trajectory creation and selection, explicit Entry/Target point
  labels, interactive Markups placement, world-RAS coordinates, and Euclidean
  length.
- Associated each configured trajectory with its target segmentation using an
  MRML node reference and with its target segment using namespaced
  `DENTOBOT.*` attributes.
- Cleared stale target associations when the selected segmentation changes, the
  target is cleared, or the retained segment no longer qualifies.
- Added Slicer-native logic-test source for target filtering, invalid targets,
  target references, point labels, partial and complete lines, a known
  13-millimetre trajectory, coincident points, and parameter-node
  persistence.
- Updated the controlled architecture, roadmap, and agent state.
- Added `docs/UBUNTU_TRANSFER.md` with the verified Git boundary, non-Git
  manifest, safe comparison clone procedure, Slicer 5.10 compatibility gates,
  and external-backend migration sequence.

### Preserved

- The authoritative segmentation, Step 3 review/correction behavior, inference
  process contract, source CBCT, masks, and run artifacts are unchanged.
- The increment does not define procedure-specific anatomy, approve a plan,
  calculate clearance, generate a patient-specific template, perform
  registration, or authorize drilling.
- The disabled legacy trajectory scaffold remains unchanged as historical
  source; its two-point creation and length concepts were reimplemented under
  current DENTO Workflow ownership rather than enabling the old module.

### Verification and limitations

- All 11 repository Python files passed static AST parsing without importing a
  Slicer module in ordinary Python.
- `DENTOWorkflow.ui` parsed as XML; all 67 Python `self.ui.*` references
  resolve, all statically discovered callbacks resolve, and UI object names
  are unique.
- `git diff --check` passed apart from informational line-ending warnings.
- An ordinary Windows-Python `pytest` attempt did not run because that
  interpreter does not have pytest installed. This is not a failure of the
  Slicer-native planning tests or the separately controlled WSL environment.
- Slicer, WSL, CUDA, TotalSegmentator, DICOM, research data, robot, and
  hardware processes were not launched. Module reload, interactive placement,
  the Slicer-native test, and MRB persistence remain pending in Slicer 5.12.2;
  compatibility must then be verified in Ubuntu Slicer 5.10.
- Nothing was reverted.

## 2026-07-24 16:11:03 IST (UTC+05:30) — Step 3C acceptance and quiet negative test

### Accepted and changed

- Recorded the developer's successful completion of the complete Step 3C
  checklist in Slicer 5.12.2. The selected label, authoritative segmentation,
  and source CBCT were correctly handed to Segment Editor; correction state,
  baseline-metric messaging, correction activity, and MRB persistence behaved
  as intended.
- Marked Steps 3A, 3B, and 3C developer-verified at the current Step 3 scope.
- Reworked the missing-source negative test to temporarily remove and restore
  the source reference on the existing valid test segmentation instead of
  creating a scene-owned orphan segmentation. This preserves the same
  `ValueError` coverage while avoiding expected Subject Hierarchy warnings.

### Verification and limitations

- The application workflow and Step 3C checklist were run by the developer in
  Slicer 5.12.2 and reported successful.
- The observed `CorrectionWithoutSource` Qt messages were traced to the
  deliberate negative-test fixture, not the real segmentation or correction
  workflow. The revised quiet fixture is statically validated here but still
  needs one future in-Slicer self-test run to confirm the console is quiet.
- Replaced `AGENTS.md`, `DEVELOPMENT_PLAN.md`, `changelog.md`, and
  `logbook.md` in place in the Drive mirror. Metadata readback confirmed the
  existing file IDs and byte sizes matching the local files.
- No anatomical or clinical accuracy claim was added. Corrected-mask metric
  recomputation and per-label review states remain optional later work.
- Nothing was reverted.

## 2026-07-24 15:50:44 IST (UTC+05:30) — Step 3C correction handoff

### Added and changed

- Added `Edit Selected Label in Segment Editor` to the segmentation review
  panel.
- Added strict handoff validation for the selected segment and the
  segmentation's persisted `DENTOBOT.SourceVolume` CBCT reference.
- Configured Slicer's built-in Segment Editor with the authoritative
  segmentation, source volume, and selected segment instead of copying masks
  or embedding another editing implementation.
- Starting a correction revision now conservatively sets the whole
  segmentation to `Needs Correction`, records a UTC correction-start time,
  and marks imported voxel/volume metrics as pre-correction inference
  baselines.
- Added content-specific observation of source-representation modifications
  and segment addition/removal while DENTO Workflow is active. These changes
  record the mask-edit timestamp and invalidate a previously `Reviewed`
  result; display, naming, selection, and metadata changes do not.
- Updated selected-label and provenance UI language so original inference
  metrics are not presented as current measurements after correction begins.
- Extended Slicer-native logic tests for source-volume validation, correction
  handoff state, metric validity, edit timestamps, automatic review
  invalidation, and invalid segment IDs.
- Recorded the developer's confirmation that Steps 3A and 3B work as intended
  in Slicer 5.12.2 and that the universal review state is intentional.

### Preserved

- The authoritative segmentation node, source geometry, original inference
  artifacts/provenance, and universal review-state model are preserved.
- No per-label approval state, corrected-mask metric recomputation,
  registration, planning, navigation, robotics, ROS, or clinical validation
  was added.

### Verification and limitations

- Official Slicer source and Slicer 5.12 developer documentation were checked
  for Segment Editor setters and `vtkSegmentation` event semantics.
- All 11 repository Python files passed AST parsing without importing the
  Slicer module in system Python. The Qt UI passed XML parsing; all 57
  `self.ui.*` references and 16 statically discovered callbacks resolve, UI
  object names are unique, Markdown fences are balanced, and `git diff
  --check` is clean.
- Slicer, WSL, CUDA, TotalSegmentator, DICOM, patient data, and installed
  Slicer files were not launched or modified during implementation.
- Replaced `AGENTS.md`, `ARCHITECTURE.md`, `DEVELOPMENT_PLAN.md`,
  `changelog.md`, and `logbook.md` in place in the Drive mirror. Folder
  readback confirmed stable file IDs and byte sizes matching the local files.
- Step 3C's Slicer-native test and manual Segment Editor handoff remain
  pending in the developer's Slicer 5.12.2 runtime. Nothing was reverted.

## 2026-07-24 15:06:56 IST (UTC+05:30) — Step 3B metrics, provenance, and review state

### Added and changed

- Extended the `Segmentation Review` panel with selected-label details:
  human-facing anatomy, source label, FDI number, model label ID, voxel count,
  and physical volume in mm³ and cm³.
- Added a compact provenance summary for run ID, source CBCT, backend and
  TotalSegmentator versions, model task/dataset/crop, CUDA device, inference
  and total time, and completion timestamp.
- Added segmentation-level `Unreviewed`, `Needs Correction`, and `Reviewed`
  workflow states with a persistent UTC update timestamp. UI warnings state
  explicitly that `Reviewed` is not clinical validation.
- Added a proper `DENTOBOT.SourceVolume` MRML node reference and versioned
  `DENTOBOT.SegmentMetricsJson` data keyed by stable segment ID. New Bridge C
  imports now persist the validated result's per-label metrics and expanded
  provenance directly on the segmentation node.
- Added a non-fatal compatibility path for older imported Bridge C results:
  when versioned review metadata is absent, the module attempts to validate
  and migrate the retained `result.json`. Missing or invalid retained
  metadata produces a visible warning without discarding the segmentation.
- Consolidated Bridge C provenance assignment through the new metadata
  enrichment routine after successful output validation and import.
- Extended Slicer-native logic tests for source-node references, per-label
  metric mapping, provenance rendering, review-state persistence, and invalid
  review-state rejection.
- Updated the controlled agent, architecture, and development-plan documents
  to record the Step 3B schema and remaining Step 3C boundary.

### Preserved

- Segment masks, reference geometry, inference commands, CUDA-only policy,
  artifact validation, and the Step 3A display behavior are unchanged.
- Segment Editor correction, edit-driven review invalidation, clinical
  approval, registration, planning, navigation, robot control, and ROS remain
  outside this increment.

### Verification and limitations

- All 11 repository Python files passed AST parsing without importing the
  Slicer module in system Python.
- `DENTOWorkflow.ui` passed XML parsing; all 54 `self.ui.*` references resolve
  to declared UI objects, and all 15 statically discovered signal callback
  methods exist.
- Slicer, WSL, CUDA, TotalSegmentator, DICOM, patient data, and installed
  Slicer files were not launched or modified.
- Updated the existing Drive files for `AGENTS.md`, `ARCHITECTURE.md`,
  `DEVELOPMENT_PLAN.md`, `changelog.md`, and `logbook.md` in place. Folder
  readback confirmed the same five file IDs and matching byte sizes.
- The extended Slicer-native test, known-label metric comparison, and MRB
  scene save/reopen acceptance remain pending in official Slicer 5.12.2.
  Nothing was reverted.

## 2026-07-24 15:00:25 IST (UTC+05:30) — Git version-control baseline

### Added and changed

- Added a repository-root `.gitignore` covering Python caches and packaging
  output, local environments, CMake build products, editor metadata, runtime
  artifacts, local environment files, and common medical/research image
  formats.
- Established Git as the source-version history from this project state
  forward. Material implementation and architecture commits continue to be
  described in this changelog and in `docs/logbook.md`.

### Safety and limitations

- Source medical/research data remains outside version control by default.
- No patient data, credentials, installed Slicer files, dependencies, models,
  or application behavior were changed.
- The GitHub remote is pending the repository URL and the initial push is
  therefore not part of this local baseline.

### Verification

- The ignore rules and staged baseline were inspected with Git locally.
- No Slicer, WSL, CUDA, model, robot, or hardware process was run.

## 2026-07-24 14:29:14 IST (UTC+05:30) — Step 3A segmentation explorer

### Added and changed

- Added a `Segmentation Review` panel to `DENTOWorkflow.ui` with a persistent
  segmentation selector, anatomy/FDI search, grouped label tree, visibility
  checkboxes, show/hide/isolate actions, 2D/3D visibility toggles, and opacity
  sliders.
- Added deterministic review descriptors for TotalSegmentator labels,
  including human-facing FDI tooth names and categories for teeth, pulp,
  jaws, neural/mandibular canals, sinuses/airway, restorations/implants, and
  other anatomy.
- Added reusable MRML logic for segment enumeration, visibility, isolation,
  selected-segment emphasis, and global 2D/3D display control.
- Reused the existing `teethSegmentation` parameter-node reference. Existing
  Bridge C results are auto-selected by their `DENTOBOT.BridgeOperation`
  provenance when no persistent selection exists.
- Added segmentation/display observers with cleanup and rebinding across
  node replacement, module exit, scene close, and cleanup.
- A successful Bridge C completion now collapses the backend panel and opens
  the review panel.
- Added Slicer-native logic coverage for FDI/category mapping, result
  discovery, visibility, isolation, emphasis, opacity, and invalid inputs.

### Preserved

- Bridge C command construction, inference, NIfTI validation, segmentation
  import, provenance, and source geometry were not changed.
- Review actions modify only MRML display properties; they do not duplicate,
  edit, resample, or otherwise change segmentation masks.
- Step 3B review state/provenance and Step 3C Segment Editor handoff remain
  outside this increment.

### Verification and limitations

- The Python source passed AST parsing. The Qt Designer file passed XML
  parsing; all 38 `self.ui.*` references resolve to declared UI objects, and
  the new selector has an MRML-scene connection.
- The display methods were checked against official Slicer segmentation
  display-node documentation.
- Slicer was not launched. The new Slicer-native test and manual 60-label UI
  acceptance run remain pending in official Slicer 5.12.2.
- No WSL, CUDA, model, inference, DICOM, patient data, installed Slicer file,
  or run artifact was changed. Nothing was reverted.

## 2026-07-24 13:55:18 IST (UTC+05:30) — Formal inference reproducibility baseline

### Added and changed

- Added `docs/REPRODUCIBILITY_AND_TRACEABILITY.md` as the controlled,
  professional installation, reconstruction, evidence, and diagnostic
  procedure for the external inference environment.
- Reworked `Inference/README.md` into a concise operational entry point with
  the Slicer/WSL boundary, validated setup commands, explicit model-cache
  preparation, verification, bridge configuration, commands, artifact rules,
  and limitations.
- Reduced `Inference/environment.yml` to a Python 3.10.20 Conda bootstrap and
  added exact validated top-level pip manifests under
  `Inference/requirements/`.
- Added `Inference/validated-environment.json`, recording backend 0.2.0,
  Slicer 5.12.2, the successful package/CUDA/GPU/model-task baseline, and the
  scope of the evidence run without patient identifiers.
- Updated the architecture, project context, development plan, and agent rules
  to distinguish controlled professional documentation from raw audit records.

### Deferred by decision

- Bridge C's verified happy path is accepted for continued development.
  Failure injection, cancellation/process cleanup, five segmentation-focused
  WSL tests, MRB persistence, anatomical validation, a complete transitive
  lock, and a clean-machine rebuild remain explicit later TODOs.
- The top-level pins are not described as a complete dependency lock.

### Verification and limitations

- The JSON baseline was parsed, dependency files and internal documentation
  links were checked, and Markdown structure was reviewed locally.
- Version values were grounded in the retained successful Bridge C
  `result.json` and official TotalSegmentator, PyTorch, Conda, and NVIDIA WSL
  installation guidance.
- No Slicer, WSL, model, CUDA, or inference process was launched in this
  documentation/dependency-manifest change. No patient data, installed Slicer
  file, model cache, or run artifact was modified or uploaded.
- Nothing was reverted.

## 2026-07-23 21:41:08 IST (UTC+05:30) — Bridge C real-CBCT runtime evidence

### Verified

- Developer-supplied evidence from official 3D Slicer 5.12.2 confirms that the
  Bridge C happy path completed without a displayed error.
- The selected real CBCT had dimensions 580 x 580 x 300, 0.25 mm isotropic
  spacing, signed-short scalar storage, valid IJK-to-RAS geometry, and was the
  same `Unnamed Series` shown as **Bridge input**.
- The GPU-only TotalSegmentator path completed teeth task 113 with
  craniofacial crop task 115 and returned an integer multilabel NIfTI matching
  the source 580 x 580 x 300 grid.
- Slicer retained `DENTOsegmentation_Teeth_93cbd5d1` with 60 validated
  segments. Colored masks were visible in the 2D slice views and the
  closed-surface representation was visible in the 3D view.
- The displayed metrics were 75.2 seconds total runtime, 48.65 cm^3 foreground
  volume, and 2.16 GiB peak GPU allocation. The terminal report showed
  `status: ok` and retained the research-output warning.

### Status changes

- Updated `AGENTS.md` and `DEVELOPMENT_PLAN.md` from “Bridge C runtime pending”
  to “core happy-path runtime verified.”
- This evidence verifies model-cache readiness, GPU inference, output contract
  validation, MRML import, label naming/coloring, and immediate 2D/3D display
  for one representative CBCT.

### Limitations

- The screenshot demonstrates technical execution and visual alignment, not
  anatomical accuracy, clinical validity, completeness against ground truth,
  or suitability for planning.
- The five new WSL unit tests, explicit error/cancellation paths, exact
  dependency lock, and MRB save/reopen persistence are not evidenced by this
  update and remain pending.
- No source code, installed Slicer file, environment, model, or patient data
  was changed or uploaded. Nothing was reverted.

### Files affected

- `docs/AGENTS.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/changelog.md`
- `docs/logbook.md`
- Corresponding raw Markdown mirrors in `IITM Dentobot/docs`

## 2026-07-23 21:34:29 IST (UTC+05:30) — Documentation mirror and final Bridge C static checks

### Added

- Established `IITM Dentobot/docs` in the connected Google Drive as a raw
  Markdown mirror of the repository's six documentation files.
- Added a standing agent rule: local repository documents remain canonical;
  changelog/logbook requests include an in-place sync of their corresponding
  Drive files plus any other design documents changed in the same batch.
- Explicitly excluded patient data, DICOM/NIfTI, segmentations, run artifacts,
  models, credentials, and other non-document data from this Drive workflow.

### Verified since the preceding entry

- `dentobot_inference --help` and `segment-teeth --help` both parsed and exposed
  the expected Bridge C command and required arguments.
- All 23 `self.ui.*` references in `DENTOWorkflow.py` matched objects in the Qt
  Designer file.
- Ten Python files passed AST parsing; the UI passed XML parsing;
  `pyproject.toml` passed TOML parsing at version `0.2.0`; all Markdown code
  fences were balanced.
- A stale-contract search found no active documentation still claiming that
  TotalSegmentator/Bridge C was a future or unimplemented command.

### Drive synchronization

- Grounded the existing Drive folder `IITM Dentobot` with ID
  `1e7AWrEeVLctMKfWaBGiqv0Ck8p0AbFWh`.
- Created its `docs` child folder with ID
  `1M5uicX_Vkk2Y130p5k4rme1TjfavWJuO`.
- Uploaded all six `.md` files as raw Markdown and verified the child-folder
  inventory. Future updates must replace those file contents in place and
  preserve their Drive IDs.

### Files affected

- `docs/AGENTS.md`
- `docs/PROJECT_CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/changelog.md`
- `docs/logbook.md`
- Connected Google Drive folder `IITM Dentobot/docs`

### Limitations

- This update adds documentation mirroring, not automatic background
  synchronization. Sync occurs when explicitly requested through an agent
  session with the connected Drive available.
- Bridge C WSL tests, model inference, Slicer import/display, and scene
  round-trip verification remain pending from the previous entry.
- No implementation, installed Slicer file, environment, model, or patient
  artifact was changed or reverted.

## 2026-07-23 21:14:55 IST (UTC+05:30) — Bridge C GPU teeth segmentation source

### Added

- Bumped `dentobot-inference` from `0.1.0` to `0.2.0` and added the
  `segment-teeth` command.
- Added GPU-only TotalSegmentator `teeth` inference on CUDA device 0 with no
  CPU fallback.
- Added a cache-only runtime guard for both required open models:
  ToothFairy3 task 113 and craniofacial crop task 115. The guard requires
  dataset metadata, plans, and final checkpoint files and prevents
  TotalSegmentator's Python API from downloading weights during a Slicer run.
- Added schema-versioned success/failure JSON with model/package versions,
  input/output geometry, CUDA identity, inference/total runtime, peak allocated
  and reserved GPU memory, detected labels, per-label voxel counts and physical
  volumes, and actionable error codes.
- Added backend validation for three-dimensional geometry, affine/spacing,
  integer/nonnegative labels, known teeth label IDs, and nonempty foreground.
  Incomplete output NIfTI is removed after a failed run while `result.json` is
  retained.
- Added five backend tests covering metrics, unknown labels, missing input,
  complete offline model caches, and missing model caches.
- Added a **Run Teeth Segmentation (GPU)** workflow action. It exports the
  exact visible selected volume, reuses the asynchronous WSL adapter, validates
  the returned report, geometry, label IDs, and voxel counts, and only then
  imports the result.
- Added deterministic label names/colors, a persistent
  `vtkMRMLSegmentationNode` parameter reference, binary-labelmap and
  closed-surface representations, 2D/3D visibility, compact inference metrics,
  and `DENTOBOT.*` provenance attributes.

### Changed

- Renamed the reproducible Conda environment definition to `dentobot` and
  aligned it with the working Python 3.10 environment.
- Added the optional `segmentation` dependency extra for
  `TotalSegmentator>=2.11,<3`.
- Updated backend setup/runtime instructions and the governing architecture,
  roadmap, and agent state to describe Bridge C accurately.
- Recorded the developer's confirmation that the selector-authority fix made
  the real-CBCT Bridge B round trip work.

### Files affected

- `Inference/src/dentobot_inference/segmentation.py`
- `Inference/src/dentobot_inference/cli.py`
- `Inference/src/dentobot_inference/__init__.py`
- `Inference/tests/test_segmentation.py`
- `Inference/pyproject.toml`
- `Inference/environment.yml`
- `Inference/README.md`
- `DENTOWorkflow/DENTOWorkflow.py`
- `DENTOWorkflow/Resources/UI/DENTOWorkflow.ui`
- `docs/AGENTS.md`
- `docs/PROJECT_CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/changelog.md`
- `docs/logbook.md`

### Verification and limitations

- Static AST parsing passed for all ten relevant Python source/test files.
- The Qt Designer UI file parsed successfully as XML, and `pyproject.toml`
  parsed with version `0.2.0` and both optional extras.
- Backend tests could not be run from Windows base Python because that
  interpreter has neither `pytest` nor `nibabel`; no package was installed to
  alter it.
- WSL unit tests, TotalSegmentator installation, model downloads, real
  inference, Slicer-native tests, result import/display, and MRB scene
  persistence were not run by this change and must not yet be reported as
  passing.
- No installed Slicer file, Slicer embedded package, WSL environment, model
  cache, original DICOM file, registration, trajectory, robotics code, or ROS
  component was changed. No implementation was reverted.

## 2026-07-23 20:55:56 IST (UTC+05:30) — Visible volume selector made authoritative

### Corrected diagnosis

- The developer clarified that Slicer's visible **Selected volume** already
  showed the real CBCT, while Bridge B still used `SyntheticCBCT`.
- This supersedes the earlier assumption that the user had left the visible
  selector on the test node. It indicates divergence between the
  `qMRMLNodeComboBox` current node and the persisted parameter-node reference
  trusted by the click handler.

### Fixed

- Added an explicit `currentNodeChanged` handler that synchronizes the visible
  selector's exact MRML node ID into the parameter node.
- Made `onRunRoundTrip` read `inputVolumeSelector.currentNode()` directly,
  validate that it is a scalar volume, and synchronize persistence immediately
  before export.
- The **Bridge input** display now reads from the same selector source used by
  the click handler.
- The imported result name is now forced after load to
  `DENTOBOT_RoundTrip_<run-id>`, independent of file-reader naming behavior.

### Verification

- Static Python AST validation passed.
- All 20 Python UI references resolved against the parsed UI.
- A real-CBCT retry is required to verify the runtime fix. No installed Slicer
  file was modified.

## 2026-07-23 20:47:25 IST (UTC+05:30) — Bridge B synthetic round trip passed and source clarified

### Validation evidence

- The developer reports that Bridge B completed after the compressed-I/O fix,
  returned a volume to MRML, and displayed it in the Slicer slice viewer.
- The successful run used `SyntheticCBCT`, confirming the complete
  Slicer-export, Windows/WSL artifact, backend validation, process completion,
  Slicer-import, MRML geometry validation, and returned-node path for a small
  synthetic volume.

### UI correction

- The run used test data because DENTOWorkflow's persisted **Selected volume**
  still referenced `SyntheticCBCT`; loading another volume does not
  intentionally override an existing explicit selection.
- Added a **Bridge input** field beside the backend configuration. It mirrors
  the exact selected scalar volume that the round-trip button will export.
- Preparation and success status text now name that selected source volume.
  The user must explicitly choose the intended CBCT in the existing Selected
  volume selector before the real-data retry.

### Verification and pending work

- The changed Python passed static AST parsing.
- The UI parsed as valid XML, and all 19 Python UI references resolved.
- A real-CBCT Bridge B run remains pending. No automatic “latest volume”
  override was added because silent source replacement would be unsafe and
  surprising.

## 2026-07-23 20:40:34 IST (UTC+05:30) — Bridge B compressed-NIfTI performance fix

### Observed failure

- The first Slicer-originated Bridge B attempt remained at the backend's
  “Loading input NIfTI” progress event for more than three minutes.
- The implementation calculated a voxel checksum by repeatedly slicing a
  NiBabel proxy backed by compressed `.nii.gz`. On a large CBCT, random slice
  access may repeatedly decompress the same stream and make the checksum
  disproportionately slow.

### Changed

- The Slicer adapter now stages Bridge B input and output as uncompressed
  `.nii` files. NIfTI affine/geometry is retained while avoiding gzip
  random-access overhead across the Windows/WSL boundary.
- The backend now materializes an image proxy once before hashing it in
  bounded planes, so directly supplied compressed NIfTI is processed
  sequentially rather than decompressed for every plane.
- Added explicit input/output checksum progress events, and the Slicer panel
  now displays backend progress messages instead of remaining at “Starting
  WSL backend”.
- Slicer-native tests now clear their synthetic MRML nodes in a `finally`
  block, preventing the test-only `SyntheticCBCT` reference from remaining in
  the Returned volume field after a test run.
- Updated active backend and architecture documentation to show uncompressed
  staging artifacts. Compressed NIfTI remains supported by the backend CLI.

### Verification and pending work

- The changed Slicer and backend files passed static AST parsing.
- The developer must rerun the three WSL tests, reload DENTO Workflow, and
  retry Bridge B. Runtime performance and MRML import are not yet claimed as
  passing.
- The stalled run should be cancelled. No installed Slicer file was modified.

## 2026-07-23 20:31:54 IST (UTC+05:30) — Bridge A translation-name shadowing fix

### Fixed

- Renamed the unused staging-root local in
  `DENTOWorkflowWidget.onCheckBackend` from `_` to `_stagingRoot`.
- Assigning to `_` made it a local variable throughout the method and
  shadowed Slicer's imported translation function `_()`, producing
  `UnboundLocalError` before the WSL health process could start.

### Verification

- The module passed static Python AST parsing after the fix.
- An AST check confirmed that no assignment target named `_` remains in the
  module.
- Slicer-originated Bridge A must be retried after reloading the module. No WSL
  process reached launch during the failed attempt, and no installed Slicer
  file was modified.

## 2026-07-23 20:26:30 IST (UTC+05:30) — Slicer-native tests reported passing

### Validation evidence

- The developer reports that DENTOWorkflow's Slicer-native tests passed inside
  Slicer after the Bridge A/B implementation.
- These tests cover the existing scalar-volume logic plus bridge path mapping,
  argument-list construction, JSON extraction, geometry comparison, and
  parameter-node references without launching WSL.

### Remaining scope

- The WSL configuration values were initially pasted into Bash because the
  prior walkthrough did not state clearly enough that they are labels and
  values for the AI Backend Bridge panel inside DENTO Workflow.
- Bash produced syntax/command-not-found messages only; no environment or
  repository change resulted.
- Slicer-originated WSL health and the complete Bridge B round trip remain
  pending.

## 2026-07-23 20:20:29 IST (UTC+05:30) — Clean WSL backend validation

### Validation evidence

- The developer recreated the Conda environment under the retained name
  `dentobot` and installed the repository as editable with its test extra.
- All three standalone backend tests passed under WSL2 with Python 3.10.20:
  the health-contract test, successful NIfTI data/geometry round trip, and
  missing-input failure result.
- `health --json --require-cuda` returned schema status `ok`, using
  `/home/tarun/miniconda3/envs/dentobot/bin/python`.
- The health result reported one NVIDIA GeForce RTX 4060 Laptop GPU, CUDA
  available, PyTorch 2.10.0+cu130 with CUDA 13.0, NiBabel 5.4.2, and NumPy
  2.2.6.

### Scope and pending verification

- This establishes the standalone WSL backend and CUDA portion of Bridge A.
- The health process has not yet been launched from Slicer. Bridge B has not
  yet exported a Slicer MRML volume, crossed WSL, or imported and validated the
  returned MRML volume.
- TotalSegmentator is intentionally absent from the clean environment at this
  checkpoint and model inference remains unimplemented.
- No source behavior was reverted and no installed Slicer file was modified.

## 2026-07-23 17:05:09 IST (UTC+05:30) — Bridge A/B external inference boundary

### Added

- Added the standalone `Inference/` Python distribution
  `dentobot-inference`, with a minimal Conda environment template and no
  dependency on Slicer's Python.
- Added `health --json --require-cuda`, which reports the actual interpreter,
  core package versions, guarded PyTorch import health, CUDA availability,
  CUDA runtime, and device names without installing or downloading anything.
- Added `roundtrip`, which loads and rewrites a NIfTI image, validates shape,
  affine, voxel type, and a chunked SHA-256 voxel checksum, and always writes a
  schema-versioned JSON result for success or failure.
- Added backend unit tests for the health contract, geometry/data preservation,
  and missing-input failure.
- Added an AI Backend Bridge panel to `DENTOWorkflow` with parameter-bound WSL
  distribution, absolute environment-Python path, staging root, returned
  volume reference, health check, NIfTI round trip, cancellation, status, and
  bounded process output.
- Added a direct asynchronous `wsl.exe` adapter that uses separate arguments,
  a named distribution, and the exact Linux Python interpreter. It does not
  construct a shell command or activate Conda interactively.
- Added isolated run IDs/directories, Windows-to-WSL path conversion,
  NIfTI export, JSON/run-ID/schema validation, MRML import, source/output
  geometry comparison, and `DENTOBOT.*` provenance attributes.
- Extended Slicer-native tests for path conversion, command construction,
  JSON extraction, geometry mismatch rejection, and parameter-node
  persistence. These tests do not launch WSL.

### Changed

- Updated the project context to reflect the developer's existing
  WSL2/Conda/CUDA experience and current focus on Slicer-to-WSL orchestration.
- Updated the active architecture and roadmap to make Bridge A/B the explicit
  gate before TotalSegmentator integration.
- Renamed this file's active title/purpose from DentalNav to DENTOBOT while
  retaining older names in historical entries.

### Verification and limitations

- Static AST parsing passed for the Slicer module and every backend Python
  source/test file.
- The Qt Designer file parsed as valid XML, and all Python `self.ui` references
  resolved to named UI objects.
- Official Slicer 5.12 documentation confirmed that
  `launchConsoleProcess(..., blocking=False)` accepts line and completion
  callbacks with the signatures used by the adapter.
- The ordinary Windows Python available to this coding session lacked NumPy
  and NiBabel. The health command was executed from source and correctly
  returned structured status `error` with exit code 2 and both missing
  dependencies; no package was installed.
- Backend round-trip unit tests were not run because their declared
  dependencies were absent. Slicer, WSL, CUDA, and TotalSegmentator were not
  launched or tested, and no model was downloaded.
- Slicer-native tests, asynchronous callback compatibility, cancellation
  behavior, NIfTI geometry round trip, parameter persistence, and UI layout
  remain to be verified in Slicer 5.12.2 and the user's WSL environment.
- No existing behavior was reverted, no installed Slicer file was modified,
  and TotalSegmentator inference/segmentation import is not yet implemented.

## 2026-07-23 15:49:05 IST (UTC+05:30) — DENTOBOT rename and Step 0 workflow implementation

### Changed

- Renamed the CMake extension project and parent product identity from the
  earlier DentalNav/DentalDrillNav naming to `DENTOBOT`.
- Established `DENTO` plus PascalCase as the identifier convention for all new
  Slicer modules. Examples are `DENTOWorkflow`, `DENTOSegmentation`,
  `DENTORegistration`, and `DENTOTrajectory`.
- Updated the active agent instructions, project context, architecture, and
  development plan to use DENTOBOT naming. Historical entries retain old names
  so the rename remains traceable.
- Removed stale placeholder homepage, icon URL, and screenshot URL values from
  extension metadata instead of replacing them with invented public URLs.
- Changed the root extension build to include `DENTOWorkflow` and exclude the
  legacy `DentalNavPlanning` module.

### Added

- Added the `DENTOWorkflow` scripted module with:
  - a minimal DENTOBOT Step 0 UI;
  - a de-identified case-label field;
  - New Empty Case with explicit confirmation;
  - Open Saved Scene for MRML/MRB scenes;
  - Open DICOM Browser using Slicer's core DICOM module;
  - a parameter-bound scalar-volume selector;
  - automatic display in Slicer's slice views;
  - name, dimensions, spacing, scalar type/range, orientation, and geometry
    status;
  - typed MRML parameter-node persistence;
  - scene-close, module-exit, and cleanup observer handling.
- Added Slicer-native logic tests for missing input, missing image data,
  synthetic volume geometry/metadata, latest-volume selection, and parameter
  node references.
- Added `DENTOWorkflow/CMakeLists.txt` and
  `DENTOWorkflow/Resources/UI/DENTOWorkflow.ui`.

### Preserved or disabled

- The physical workspace directory retains its older name; it is not the
  product identity.
- `DentalNavPlanning` remains in the repository as disabled legacy history.
  Its threshold UI, sample-data behavior, and trajectory experiment are not
  included in the DENTOBOT extension build.
- Original DICOM files remain outside scene clearing and are never modified by
  New Empty Case.

### Verification

- `DENTOWorkflow.py` passed a static Python AST parse. It was not imported or
  executed with system Python.
- `DENTOWorkflow.ui` parsed as well-formed XML.
- All Python `self.ui` references were matched to named objects in the parsed
  UI, and both `SlicerParameterName` bindings were found.
- Root CMake registration was checked to include `DENTOWorkflow` and exclude
  `DentalNavPlanning`.

### Limitations and pending validation

- Slicer was not launched. The module, UI, DICOM browser handoff, MRML
  parameter persistence, scene round-trip, and Slicer-native tests remain
  unverified in Slicer 5.12.2.
- No real or sample DICOM data was loaded.
- No WSL, CUDA, TotalSegmentator, registration, trajectory, or robot behavior
  was added or run.
- No installed Slicer file was read or modified by this change.

## 2026-07-22 20:13:27 IST (UTC+05:30) — Direct WSL process architecture and raw records

### Changed

- Replaced the proposed file/job communication architecture with a directly
  controlled, asynchronous WSL process architecture.
- Defined Slicer as the lifecycle owner: it exports NIfTI, invokes an explicit
  WSL distribution and Linux Python interpreter through `wsl.exe`, streams
  structured stdout, handles cancellation and exit status, validates the
  result, and imports it into MRML.
- Retained an isolated per-run directory only for NIfTI payloads, logs, and
  reproducibility metadata. It is no longer described as a queue, watched
  directory, worker protocol, or process-control mechanism.
- Replaced the planned `segment --request <request.json>` entry point with
  explicit CLI arguments for input, output, device, result JSON, and run ID.
- Reserved persistent HTTP/RPC services for a future measured requirement,
  rather than making one part of the initial design.
- Added mandatory timestamped traceability rules to the agent instructions and
  documented the raw-record layer in project context and architecture.

### Added

- Added `docs/changelog.md` for material repository/specification changes.
- Added `docs/logbook.md` for ideas, prompt/request summaries, decisions,
  experiments, failures, fixes, reversions, and session history.

### Files affected

- `docs/AGENTS.md`
- `docs/PROJECT_CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/DEVELOPMENT_PLAN.md`
- `docs/changelog.md`
- `docs/logbook.md`

### Preserved

- Slicer remains responsible for DICOM, MRML, visualization, interaction, and
  scene persistence.
- PyTorch, CUDA, and TotalSegmentator remain isolated in WSL2.
- NIfTI remains the geometry-preserving bulk image exchange format.
- JSON remains the reproducibility/result metadata format.
- No ROS dependency was introduced.

### Verification and limitations

- This was a documentation-only change. No Slicer, WSL, CUDA, model, or robot
  process was run.
- At `2026-07-22 20:19:48 IST (UTC+05:30)`, all six documentation files were
  checked for stale active-contract phrases and balanced Markdown code fences.
  Historical mentions of the superseded job design were intentionally kept in
  this changelog and the logbook.
- The same check found no non-document file modified after this documentation
  batch began.
- The actual process adapter and backend CLI do not yet exist and therefore
  remain unvalidated implementation plans.
- No application source, installed Slicer file, dependency, or model was
  changed by this update.

## 2026-07-22 19:57:35–19:57:42 IST (UTC+05:30) — Initial architecture and roadmap reset

The timestamps in this heading are derived from the saved file timestamps of
the four governing documents.

### Changed

- Reframed the product as a focused Slicer extension during workflow
  development, followed later by a supported custom Slicer application build.
- Defined Slicer, external inference, and robot-control responsibilities.
- Made a minimal DICOM workflow shell Step 0, ahead of segmentation and
  trajectory planning.
- Isolated inference in a standalone WSL2 package and deferred ROS to a later
  evidence-based robotics decision gate.
- Added explicit protection against editing installed Slicer or original DICOM
  data.

### Superseded detail

- This version proposed a NIfTI/JSON job-directory contract as the primary
  Slicer–WSL interface. The 20:13:27 entry replaced that control model with
  direct process invocation while retaining file artifacts for bulk data and
  provenance.

### Verification

- Documentation structure and code-fence balance were checked.
- No application code was changed in this reset.

## Through 2026-07-22 15:53:04 IST (UTC+05:30) — Retrospective earlier repository state

This entry was written at `2026-07-22 20:13:27 IST (UTC+05:30)` from the
repository and available conversation history. The heading uses the observed
trajectory-file timestamp only to place the reconstructed state in sequence.
The original scaffold-creation time and individual edit times were not
captured, so they must not be inferred from either timestamp.

### Pre-existing scaffold

- `DentalDrillNav` was created using the Slicer Extension Wizard template.
- `DentalNavPlanning` retained the generated threshold UI, sample-data
  registration, threshold logic, and threshold test.

### Exploratory trajectory change

- `DentalNavPlanning/DentalNavPlanning.py` was extended with a
  `trajectoryLine` parameter-node reference, trajectory-line creation logic,
  world-RAS Euclidean length calculation, and Slicer-native test coverage.
- The current file timestamp observed during reconstruction was
  `2026-07-22 15:53:04 IST`.
- The exploratory trajectory code was not removed, but the trajectory-first
  roadmap was superseded by the Step 0 workflow-shell plan.
- A passing in-Slicer result for the final exploratory code is not documented;
  it must therefore be treated as unverified.

### Runtime/dependency state

- No TotalSegmentator, PyTorch, CUDA, or WSL dependency is part of this
  repository at this point.
- Reported failures in the installed Slicer environment did not produce a
  repository dependency change.
