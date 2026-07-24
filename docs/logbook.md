# DENTOBOT Development Logbook

## Purpose

This is the raw, append-oriented record of DENTOBOT development sessions. It
captures the reasoning that does not belong in a concise architecture or
roadmap: ideas, user requests and prompt summaries, assumptions, questions,
decisions, attempted implementations, observations, failures, diagnoses,
fixes, reversions, unresolved issues, and next actions.

Every entry must include an explicit date, time, and timezone. One timestamp
may cover a cohesive session update when finer timestamps would be redundant.
If historical material is reconstructed, record the reconstruction time and
state that the original event time is unavailable. Do not record patient
identifiers, credentials, access tokens, or other secrets.

Suggested entry fields are:

- session objective or request summary;
- ideas and alternatives considered;
- decision and rationale;
- implementation or files changed;
- test environment and evidence;
- failure symptoms and likely/confirmed cause;
- fix, reversion, or current disposition;
- unresolved questions and next action.

## 2026-07-24 15:00:25 IST (UTC+05:30) — Git repository setup

### Request and decision

- The developer requested ongoing project version control with frequent,
  detailed commits after creating a GitHub repository.
- The local project directory was not recognized as a Git working tree and no
  remote URL was discoverable.
- The existing changelog and logbook remain the detailed human-readable
  history. Git commits provide atomic snapshots and concise summaries.

### Repository policy

- Commit cohesive changes with imperative, descriptive messages.
- Update both `docs/changelog.md` and `docs/logbook.md` for every material
  implementation or architecture change, following the governing agent
  instructions.
- Keep generated files, environments, build output, runtime artifacts,
  secrets, and medical/research image data out of Git by default.
- Inspect the diff and run proportionate authorized validation before each
  commit.

### Current disposition

- A local baseline repository and initial commit are being created.
- Adding the GitHub remote and pushing remain pending until the repository URL
  is supplied.
- No Slicer, WSL, CUDA, model, robot, or hardware process was run.

## 2026-07-24 14:29:14 IST (UTC+05:30) — Step 3A implementation session

### Request and scope

- The developer accepted the proposed segmentation-review plan and authorized
  implementation.
- The increment was intentionally limited to Step 3A exploration and display.
  Review/approval state, per-label metrics, color presets, and Segment Editor
  correction handoff were not pulled forward.

### Design decisions

- The existing Bridge C `vtkMRMLSegmentationNode` remains authoritative.
  Creating duplicate labelmaps or model nodes for review would add state and
  persistence risk without improving inspection.
- The existing `teethSegmentation` parameter field now also binds the review
  selector, so inference output, manual selection, module switching, and scene
  persistence share one node reference.
- Search and tree selection are transient widget concerns. Visibility,
  emphasis, and opacity are segmentation-display-node properties.
- Selecting a segment emphasizes it by reducing contextual segment opacity;
  `Show All`, `Hide All`, and `Isolate Selected` clear that emphasis to provide
  predictable actions.
- Actual labels from the successful Bridge C result were inspected to ground
  categories and FDI parsing. Tooth pulp source codes such as `fdi133` are
  displayed as tooth FDI 33 while retaining `133` in searchable source
  metadata.

### Implementation and safety

- Added the review UI, parameter binding, observers, FDI/category logic,
  visibility/isolation/emphasis operations, and Slicer-native tests.
- A successful segmentation automatically transitions from the backend panel
  to the review panel.
- All operations are display-only and do not alter mask geometry, input CBCT,
  run artifacts, model files, or installed Slicer files.

### Verification and next action

- Static AST, UI XML, object-reference, uniqueness, and MRML selector
  connection checks passed.
- No Slicer process was launched, so runtime behavior and the added
  Slicer-native test are not yet reported as passing.
- Next, reload `DENTOWorkflow` in Slicer 5.12.2, run its self-test, and manually
  exercise search, selection emphasis, per-label visibility, isolation,
  show-all restoration, opacity, node switching, and scene persistence using
  the retained Bridge C segmentation.

## 2026-07-24 13:55:18 IST (UTC+05:30) — Reproducibility documentation session

### Request and decision

- The developer confirmed that the working Bridge C path is verified and asked
  to skip its non-working or untested paths for now while retaining them in a
  later TODO list.
- The developer requested professional dependency-installation and README
  documentation suitable for reproducibility and traceback, rather than using
  the intentionally raw changelog/logbook as an operating manual.
- The accepted documentation hierarchy now separates controlled system/design
  documents, one formal reproducibility procedure, and two raw audit records.

### Evidence grounding

- The retained successful run metadata was used as the source for the
  validated baseline: Python 3.10.20, NumPy 2.2.6, NiBabel 5.4.2, PyTorch
  2.10.0+cu130, TotalSegmentator 2.16.0, nnUNet v2 2.8.1, CUDA 13.0, and the
  NVIDIA GeForce RTX 4060 Laptop GPU.
- Teeth task 113 and craniofacial crop task 115 were retained as the explicit
  model-cache requirements.
- Official upstream guidance was checked for the PyTorch CUDA 13.0 wheel
  index, TotalSegmentator installation/model cache, Conda export semantics,
  and NVIDIA's WSL driver boundary.

### Implementation

- Created validated top-level dependency manifests, a minimal Conda bootstrap,
  and a machine-readable environment-evidence record.
- Replaced the informal inference README with a reproducible installation and
  operational guide, backed by the new formal document.
- Added installation verification, environment snapshot, diagnostic-bundle,
  data-governance, and change-control procedures.
- Updated the roadmap with a named deferred Bridge C validation backlog.

### Limitations and next action

- The manifests pin validated direct dependencies but do not freeze every
  transitive package. A platform-specific explicit export and clean-machine
  reconstruction remain later release work.
- The deferred Bridge C items were neither run nor repaired in this session
  and must not be reported as passed.
- The next feature milestone may proceed to Step 3 segmentation review and
  visualization while preserving the deferred validation gate.

## 2026-07-23 21:41:08 IST (UTC+05:30) — First successful Bridge C real-CBCT result

### Developer report

- The developer supplied a screenshot from official 3D Slicer 5.12.2 and
  reported that the result was visually excellent with no mistakes observed
  so far.
- The screenshot is treated as runtime evidence for the technical happy path,
  while the developer's positive visual assessment is recorded as an
  observation rather than anatomical or clinical validation.

### Observed input and configuration

- Module: `DENTO Workflow`.
- Selected and bridged source: `Unnamed Series`.
- CBCT dimensions: 580 x 580 x 300 voxels.
- Spacing: 0.250 x 0.250 x 0.250 mm.
- Scalar type/range: signed short, -1000 to 3095.
- Geometry: valid IJK-to-RAS; displayed orientation I->L, J->P, K->S.
- WSL distribution: `Ubuntu`.
- Backend interpreter:
  `/home/tarun/miniconda3/envs/dentobot/bin/python`.
- Run-artifact root: `C:\DENTOBOTRuns`.

### Successful output

- Segmentation node: `DENTOsegmentation_Teeth_93cbd5d1`.
- Backend result status: `ok`.
- TotalSegmentator task: `teeth`, task ID 113.
- Crop task: `craniofacial_structures`, task ID 115.
- Output storage: multilabel `uint8` NIfTI on the same 580 x 580 x 300 grid at
  0.25 mm isotropic spacing.
- Validated segment count: 60.
- Total runtime displayed by the workflow: 75.2 seconds.
- Foreground volume: 48.65 cm^3.
- Peak GPU allocation: 2.16 GiB.
- The axial, coronal, and sagittal views showed colored label overlays on the
  CBCT. The 3D view showed the generated colored jaw, tooth, sinus, canal, and
  related closed-surface structures.
- The workflow displayed its green completion state and retained the explicit
  research-only/human-review warning.

### What this proves

- The visible selected CBCT was exported rather than synthetic test data.
- Both required TotalSegmentator model caches were usable.
- The CUDA-only inference route completed rather than falling back to CPU.
- The backend returned a successful geometry/label contract and metrics.
- Slicer accepted the output, created the persistent segmentation node, copied
  names/colors, generated closed surfaces, and displayed the result in 2D/3D.

### What remains unproven

- Visual plausibility is not ground-truth anatomical accuracy or clinical
  validation.
- The five newly added WSL unit tests were not shown in this evidence.
- Cancellation and deliberate dependency/model/CUDA/error cases remain to be
  exercised.
- An MRB save/reopen round trip is still required to confirm persistence of
  source/output references, representations, and provenance.
- Exact dependency locking should follow after the verified environment
  versions are captured.

### Disposition

- Bridge C's core happy path is now runtime-verified for one real CBCT.
- No code fix or reversion is required from this result.
- The local documentation status was updated and its corresponding Drive
  mirrors were synchronized in place.

## 2026-07-23 21:34:29 IST (UTC+05:30) — Cross-chat documentation synchronization

### Request

- While validating Bridge C, the developer requested that all current
  repository documentation be copied into the existing connected Google Drive
  project folder for use as context in a non-Codex ChatGPT project.
- The developer also requested a standing behavior: whenever `logbook.md` or
  `changelog.md` is updated in a future session, synchronize the corresponding
  Drive copies.

### Grounding and decision

- Google Drive search found one exact folder named `IITM Dentobot`, ID
  `1e7AWrEeVLctMKfWaBGiqv0Ck8p0AbFWh`.
- Its existing direct children were a project tracker spreadsheet and a
  personal work-journal document; no `docs` child existed.
- A `docs` child was created with ID
  `1M5uicX_Vkk2Y130p5k4rme1TjfavWJuO`.
- The local `docs/` directory remains canonical because it is part of the
  development workspace and follows the repository's traceability rules.
  Drive is a byte-for-byte Markdown mirror for context transfer, not an
  independent editing authority.
- Future synchronization updates existing Drive file IDs in place to avoid
  duplicates and preserve links/revision history. Any other design document
  changed in the same changelog/logbook batch is synchronized too.

### Additional Bridge C verification recorded

- Both CLI help surfaces parsed and exposed `segment-teeth` with `--input`,
  `--output`, `--result-json`, and `--run-id`.
- Python AST, Qt UI XML, Python-to-UI reference matching, TOML version/extras,
  and Markdown fence checks passed.
- The active docs no longer contain the searched stale statements that Bridge
  C is only future work.
- These are static/contract checks only. They do not replace the pending WSL,
  TotalSegmentator, CUDA inference, Slicer import, or MRB persistence tests.

### Synchronization result

- Uploaded `AGENTS.md`, `ARCHITECTURE.md`, `DEVELOPMENT_PLAN.md`,
  `PROJECT_CONTEXT.md`, `changelog.md`, and `logbook.md` as raw Markdown into
  `IITM Dentobot/docs`.
- Recorded the six confirmed Drive file IDs in `AGENTS.md` so future syncs can
  update the existing objects directly without name-based ambiguity.
- Verified the folder inventory after upload.
- No patient data, imaging, segmentation, inference artifact, credential,
  model, or source code was uploaded.

### Disposition

- The local and Drive documentation sets are synchronized at this entry.
- The Drive mirror rule is now explicit in the governing agent, context, and
  architecture documents.
- Nothing was reverted. Bridge C runtime acceptance remains pending.

## 2026-07-23 21:14:55 IST (UTC+05:30) — Bridge C implementation session

### Request and incoming evidence

- The developer confirmed that the corrected Bridge B now uses the intended
  CBCT and works.
- The next request was to implement Bridge C quickly: run TotalSegmentator
  teeth inference, display mask outputs, retain inference metrics, and keep
  segmentation outputs safely loadable.

### Technical facts checked

- TotalSegmentator's current official Python API exposes the `teeth` task as
  task 113, based on ToothFairy3, and returns a multilabel NIfTI when `ml=True`.
- The task first runs `craniofacial_structures` task 115 to locate
  `teeth_lower` and `teeth_upper`; therefore a healthy offline run needs both
  model caches, not only the ToothFairy3 checkpoint.
- The API accepts `gpu:0`, but its device-selection helper can fall back to
  CPU and its normal execution path calls an automatic weight downloader.
- The design consequently performs its own CUDA precheck, fixes the requested
  device to CUDA 0, and replaces the imported downloader function with a
  cache-only validator for the life of the backend process.
- Slicer's documented native path is to load a returned integer label map,
  associate a color table, import it into a
  `vtkMRMLSegmentationNode`, create a closed-surface representation for 3D,
  and remove temporary label/color nodes after the segmentation has copied
  their contents.

### Decisions

- Bridge C remains one direct asynchronous CLI invocation; the run directory
  is an artifact/provenance boundary, not a watched job queue.
- Slicer remains responsible for selected-volume authority, NIfTI export,
  MRML geometry validation, segmentation creation, visualization, scene
  references, and user-facing errors.
- WSL remains responsible for PyTorch/CUDA, model execution, label validation,
  and metric generation.
- CPU fallback, package installation, and weight download are not exposed from
  the Slicer button.
- A single validated multilabel `teeth-segmentation.nii` is retained alongside
  the exported input and `result.json`. Rich review/grouping controls remain
  Step 3 rather than expanding Bridge C.

### Implementation

- Added backend version `0.2.0`, CLI command `segment-teeth`, TotalSegmentator
  task/label integration, offline cache guards, GPU metrics, physical label
  volumes, progress events, stable errors, and safe failure cleanup.
- Added five inference-side unit tests that do not execute a model or require
  TotalSegmentator to be installed.
- Added the Slicer GPU action and completion pipeline. Returned data must pass
  the schema/run-ID/status/model/device contract, source-grid comparison,
  integer label-ID comparison, and exact per-label voxel-count comparison
  before import.
- Added deterministic names/colors, segmentation parameter-node persistence,
  2D/3D representations, compact displayed metrics, and detailed
  `DENTOBOT.*` provenance attributes.
- Updated environment/setup instructions and architectural/current-state
  documents. No installed runtime or patient source file was changed.

### Verification performed

- Static parsing passed for ten Python files.
- The `.ui` file passed XML parsing.
- `pyproject.toml` parsed as version `0.2.0` with `test` and `segmentation`
  optional dependency groups.
- Windows base Python could not run the backend suite because it lacks
  `pytest` and `nibabel`. This was an environment limitation, not a test pass
  or a diagnosed code failure. No dependency was installed as a workaround.
- WSL, Slicer, CUDA inference, and model downloads were deliberately not
  launched during this source-editing session.

### Required next validation

From `Inference/` in the existing WSL environment:

```bash
conda activate dentobot
python -m pip install -e ".[test,segmentation]"
python -m pytest
totalseg_download_weights -t craniofacial_structures
totalseg_download_weights -t teeth
python -m dentobot_inference health --json --require-cuda
```

The two download commands are explicit user actions and may use substantial
network/storage. After they finish, reload `DENTOWorkflow`, run its
Slicer-native tests, select the real CBCT, and click **Run Teeth Segmentation
(GPU)**. A successful run should leave `input.nii`,
`teeth-segmentation.nii`, and `result.json` in one
`C:\DENTOBOTRuns\<run-id>` directory and create a visible
`DENTOsegmentation_Teeth_<run-prefix>` node. The final acceptance check is to
save an MRB, reopen it, and confirm the source and segmentation references,
labels, representations, and provenance remain available.

### Disposition

- Bridge C source is implemented.
- Nothing was reverted.
- Runtime acceptance is pending and must be based on the developer's WSL and
  Slicer evidence.

## 2026-07-23 20:55:56 IST (UTC+05:30) — Selector and parameter reference divergence

### User correction

- The developer clarified that the visible **Selected volume** was already the
  intended CBCT when Bridge B nevertheless exported/returned
  `SyntheticCBCT`.
- Therefore the preceding interpretation—an unchanged visible selection—was
  incomplete. The probable boundary failure is stale parameter persistence or
  GUI-binding divergence.

### Implementation response

- The qMRML selector is now explicitly connected to a synchronization handler
  that compares MRML node IDs and updates `inputVolume`.
- The round-trip click path treats `inputVolumeSelector.currentNode()` as
  authoritative instead of trusting a possibly stale wrapper reference.
- The same selector drives the new **Bridge input** label, and imported output
  is explicitly renamed after the reader returns.

### Next action

- Reload DENTO Workflow, ensure **Selected volume** and **Bridge input** both
  show the intended CBCT, then rerun Bridge B.
- On completion, verify the returned name begins
  `DENTOBOT_RoundTrip_` and inspect its `DENTOBOT.SourceVolumeID` attribute if
  further provenance diagnosis is needed.

## 2026-07-23 20:47:25 IST (UTC+05:30) — Bridge B passed with the selected synthetic source

### Result and interpretation

- The developer confirmed that the optimized Bridge B run completed and the
  returned scalar volume loaded into Slicer's slice viewer.
- The source was `SyntheticCBCT`, not the newly loaded CBCT. This was not a
  backend substitution: Bridge B always exports the parameter node's explicit
  `inputVolume`, which remained set to the test node.
- DENTOWorkflow only auto-selects a newly loaded DICOM volume when it can
  associate the load with its own **Open DICOM Browser** handoff. It preserves
  an existing selection when a volume is loaded through another route.

### UX change and next action

- Added a read-only **Bridge input** value to the AI Backend Bridge panel and
  included the source volume name in preparation/completion status.
- Automatic replacement with the newest scene volume was rejected because it
  could silently process the wrong research dataset.
- Reload the module, choose the actual CBCT in **Selected volume**, verify the
  same name appears as **Bridge input**, and rerun. The synthetic pass verifies
  bridge mechanics; real-CBCT performance and geometry acceptance remain to be
  recorded.

## 2026-07-23 20:40:34 IST (UTC+05:30) — First Bridge B run stalled during checksum

### Runtime observation

- After clicking **Test NIfTI Round Trip**, Slicer launched the WSL process and
  received the structured “Loading input NIfTI” event, proving argument
  dispatch, artifact visibility, backend startup, and live stdout delivery.
- No later progress event appeared for more than three minutes. The UI
  remained responsive and presented an enabled Cancel button.

### Diagnosis and fix

- The stall occurred during input metadata/checksum creation immediately after
  the load event. The prior checksum loop accessed each plane directly through
  a compressed NiBabel proxy, which can repeatedly decompress a `.nii.gz`
  stream for a large CBCT.
- Bridge staging was changed to uncompressed `.nii`. The checksum now
  materializes the proxy once, then hashes planes from memory. This trades
  temporary backend memory roughly proportional to one voxel array for linear
  I/O behavior and predictable runtime.
- Progress reporting now distinguishes load, input checksum, write, reload,
  output checksum, and completion in the Slicer status label.
- The `SyntheticCBCT` shown as Returned volume came from the Slicer-native
  parameter-reference test rather than a successful Bridge B return. Test
  cleanup now clears synthetic MRML state even when a test fails.

### Next action

- Cancel the old process, rerun `python -m pytest` in the editable WSL
  environment, reload DENTO Workflow, select the intended CBCT, and retry
  Bridge B.
- Confirm that a new `.nii` run directory reaches completion and that the
  returned MRML volume passes geometry validation. Cancellation/process-tree
  behavior and the successful Bridge B terminal state remain unverified.

## 2026-07-23 20:31:54 IST (UTC+05:30) — First Slicer Bridge A attempt exposed local-name bug

### Failure and cause

- Clicking **Check WSL + CUDA** reached `onCheckBackend` but raised
  `UnboundLocalError: cannot access local variable '_'`.
- The method unpacked the unused staging-root return value into `_`. Python
  therefore treated `_` as a local variable throughout the function, while
  the same name is also Slicer's imported translation function used earlier in
  the method.
- The exception occurred while creating the error-display context, before the
  external process was launched. This was a DENTOWorkflow source bug, not a
  WSL, CUDA, environment, or Slicer-installation failure.

### Fix and next action

- Renamed the local to `_stagingRoot` and statically scanned the module for
  other assignments that could shadow `_`; none remain.
- Static AST validation passed. Reload DENTO Workflow and retry
  **Check WSL + CUDA**. Runtime success is not yet claimed.

## 2026-07-23 20:26:30 IST (UTC+05:30) — Slicer tests passed; UI-field ambiguity corrected

### Reported result

- The developer reports that the Slicer-native DENTOWorkflow tests passed.
- This verifies the module's non-WSL test suite inside Slicer, in addition to
  the previously passing standalone WSL tests and CUDA health command.

### Communication failure and correction

- The developer pasted the example WSL distribution, environment Python, and
  run-artifact lines into Bash. Bash correctly rejected them because they were
  labels for fields in the Slicer module UI, not terminal commands.
- The failed Bash lines made no changes. The corrected workflow is to retrieve
  the distribution name using `echo "$WSL_DISTRO_NAME"` and then type that
  value, the absolute environment Python path, and the Windows staging path
  into DENTO Workflow's **AI Backend Bridge** panel.
- Slicer-originated Bridge A and Bridge B remain the next validation actions.

## 2026-07-23 20:20:29 IST (UTC+05:30) — Clean backend tests and CUDA health passed

### Developer-run evidence

- The developer recreated the corrupted environment while retaining the Conda
  name `dentobot`.
- Editable installation of `dentobot-inference` and its test dependencies
  completed without the prior missing-metadata symptoms.
- Pytest collected three tests and all passed in 2.89 seconds:
  `test_health.py` and both tests in `test_roundtrip.py`.
- The explicit CUDA health command returned status `ok` and identified the
  correct WSL Python, RTX 4060 Laptop GPU, PyTorch/CUDA runtime, NiBabel, and
  NumPy.
- TotalSegmentator was correctly reported as absent at this stage.

### Interpretation and next action

- The earlier failure is treated as environment corruption resolved by
  recreation, not a DENTOBOT source fix.
- Standalone Bridge A backend health and the backend half of the Bridge B
  round-trip contract are now verified.
- Next, configure the exact distribution and
  `/home/tarun/miniconda3/envs/dentobot/bin/python` in DENTO Workflow. Run
  Slicer-originated Bridge A, then select a de-identified scalar volume and run
  Bridge B.
- Slicer callback handling, Windows-to-WSL artifact access, Slicer NIfTI
  export/import, MRML geometry comparison, cancellation, and returned-node
  persistence remain unverified until that run.

## 2026-07-23 20:15:14 IST (UTC+05:30) — Environment corruption confirmed

### Follow-up evidence

- Force-reinstalling Pygments restored `pygments.token`, but pytest then
  failed while importing another incomplete package:
  `ModuleNotFoundError: No module named 'exceptiongroup._exceptions'`.
- `python -m pip check` confirmed broader inconsistency: many distributions
  have missing `METADATA`, multiple required packages are treated as absent,
  PyTorch 2.10.0+cu130 expects Triton 3.6.0 but Triton 3.4.0 is installed,
  Torchvision 0.23.0 expects PyTorch 2.8.0, and Voxtell constrains PyTorch below
  2.9.

### Disposition

- Repeated single-package repairs are rejected as the primary path because
  they would not produce the clean, reproducible backend environment required
  by the project.
- The recommended non-destructive recovery is to create a separate clean Conda
  environment, first install and test only the DENTOBOT bridge package, then
  install one officially matched CUDA-enabled PyTorch build, and only after
  Bridge A/B pass add a pinned TotalSegmentator stack.
- The existing `dentobot` environment is left untouched for comparison until
  the clean environment is validated. No environment command was run by the
  coding agent.

## 2026-07-23 20:10:39 IST (UTC+05:30) — Bridge A health success and broken test dependency

### Runtime evidence

- Installing the editable `dentobot-inference` project plus its test extra
  succeeded in the WSL Conda environment named `dentobot`.
- The backend health command completed with schema status `ok`.
- It reported Python 3.10.20 from the expected environment, WSL2 Linux, one
  available `NVIDIA GeForce RTX 4060 Laptop GPU`, PyTorch 2.10.0+cu130,
  CUDA availability true, TotalSegmentator 2.13.0, NiBabel 5.4.2, and NumPy
  2.2.6. This is the first recorded successful Bridge A backend health result.
- This command was run by the developer in WSL, not by the coding agent.

### Test-run failure and diagnosis

- `python -m pytest` did not start the DENTOBOT tests because importing pytest
  reached Pygments and failed with
  `ModuleNotFoundError: No module named 'pygments.token'`.
- Pip also warned that `METADATA` files were absent from numerous installed
  distributions. These symptoms indicate incomplete/corrupted installed
  package files or metadata in this environment, rather than a failure in a
  DENTOBOT test.
- The least disruptive next attempt is to force-reinstall Pygments, verify its
  import, run `python -m pip check`, and rerun pytest. If missing-metadata
  warnings or other corruption remain, recreating the environment from a
  documented specification is preferred over accumulating repairs.
- Bridge B has not yet been tested.

## 2026-07-23 20:07:16 IST (UTC+05:30) — First WSL environment setup attempt

### Observed result

- The developer created/activated a Conda environment named `dentobot`; the
  environment Python resolved to
  `/home/tarun/miniconda3/envs/dentobot/bin/python`.
- Running `pytest` failed because pytest was not installed in that environment.
- Running `python -m dentobot health --json --require-cuda` failed with
  `No module named dentobot`.

### Diagnosis and next action

- Renaming the Conda environment is valid and does not require a source change.
- The Python import package is deliberately named `dentobot_inference`; the
  distribution name is `dentobot-inference`. There is no module named
  `dentobot`.
- The editable project and test extra still need to be installed into the
  active environment using `python -m pip install -e ".[test]"` from the
  `Inference/` directory. This keeps pytest and backend dependencies inside the
  Conda environment; the suggested Ubuntu `apt` package must not be used.
- After installation, run tests through the active interpreter with
  `python -m pytest`, then run
  `python -m dentobot_inference health --json --require-cuda`.
- A healthy CUDA result additionally requires a compatible CUDA-enabled
  PyTorch build in this environment. No package installation or WSL command
  was performed by the coding agent.

## 2026-07-23 17:05:09 IST (UTC+05:30) — Bridge A/B implementation session

### Request and clarified knowledge boundary

The developer confirmed prior success with WSL2-based GPU inference and plans
to create a clean Conda environment for DENTOBOT. The unfamiliar part is how
Slicer's embedded Windows Python should execute a backend that uses the WSL
environment. After the interpreter boundary was explained, the developer
authorized implementing Bridge A and Bridge B.

Slicer owns the MRML volume, Qt UI, process lifecycle, validation, and returned
scene node. WSL owns only the ordinary Python backend. Slicer never imports
Linux PyTorch or TotalSegmentator, and WSL never receives an MRML object.

### Scope decision

- Bridge A proves the configured distribution, exact Conda Python, package
  state, PyTorch import, and CUDA device through a read-only health command.
- Bridge B proves the real medical-image transport by exporting NIfTI,
  rewriting it in WSL, checking data and physical geometry on both sides, and
  importing a returned scalar volume.
- TotalSegmentator was intentionally not added. A passing transport boundary
  is required before model inference and label-map import are introduced.
- The environment definition is minimal and intentionally not an unvalidated
  CUDA/TotalSegmentator lock. Exact GPU/model versions will be recorded only
  after the developer validates the new Conda environment.

### Implementation details

- Created the independently testable `dentobot_inference` package with module
  and console entry points, health reporting, a NIfTI round-trip command,
  atomic result-JSON writes, structured progress, backend/version metadata,
  and unit tests.
- Extended `DENTOWorkflow` with persisted backend configuration and returned
  volume reference.
- Added direct asynchronous launch through `wsl.exe --distribution <name>
  --exec <absolute-python> -m dentobot_inference ...`. Every token is a process
  argument; there is no `bash -c`, command concatenation, or interactive Conda
  activation.
- Each image run receives a UUID directory under the configured local Windows
  staging root. The adapter maps drive paths to `/mnt/<drive>/...`, currently
  rejects UNC paths, and refuses volumes with unresolved parent transforms.
- On completion, the adapter validates exit status, JSON schema, command, run
  ID, backend data/geometry checks, file presence, MRML dimensions, scalar
  type, and IJK-to-RAS geometry. An invalid imported node is removed.
- The returned scalar volume is scene-owned, linked to its source/result using
  `DENTOBOT.*` attributes, and retained through the typed parameter node.
- Scene close and widget cleanup request cancellation. Process output and its
  in-memory parsing buffer are capped at 2,000 lines.

### Validation and observed failure

- Static Python parsing and UI XML/reference checks passed.
- Official Slicer 5.12 API documentation confirmed the non-blocking
  `launchConsoleProcess` argument and callback contract used by the adapter.
- A read-only attempt to inspect the installed 5.12.2 `util.py` signature was
  denied by the coding workspace sandbox. The file was neither read nor
  modified; the versioned official documentation was used instead.
- A source-tree health invocation ran under the coding session's ordinary
  Windows Miniconda Python. It correctly identified that NumPy and NiBabel
  were absent, returned a JSON error document, and used exit code 2.
- Attempting to check backend imports showed
  `ModuleNotFoundError: No module named 'numpy'`. This is not a DENTOBOT code
  regression; it means this unrelated Windows environment cannot run the
  declared backend tests. No dependency was installed and no workaround was
  attempted.
- Slicer, WSL, CUDA, backend round-trip tests, and model inference were not
  launched. Therefore none are claimed as passing.

### Next action

The developer should create/install the package in the dedicated WSL Conda
environment, run its ordinary unit tests and health command there, then enter
the exact distribution/Python paths in DENTO Workflow. Bridge A should be
verified before Bridge B. Any Slicer 5.12.2 API or geometry discrepancy found
in that run should be fixed before adding the TotalSegmentator command.

## 2026-07-23 15:49:05 IST (UTC+05:30) — DENTOBOT naming decision and Step 0 implementation

### Request summary

The developer authorized starting Step 0 and introduced a crucial product-name
change: the entire application is now `DENTOBOT`, and every new module must use
the `DENTO` prefix. Example domain names discussed were segmentation,
registration, and trajectory modules. The developer also requested a guided
walkthrough of the first workflow module.

### Naming decision

- Parent product, extension CMake project, and later custom application:
  `DENTOBOT`.
- Code identifiers use `DENTO` plus PascalCase for readability and normal
  Slicer/Python class conventions: `DENTOWorkflow`, `DENTOSegmentation`,
  `DENTORegistration`, and `DENTOTrajectory`.
- Human-facing labels may contain spaces, such as `DENTO Workflow`.
- Existing older names remain only in the physical workspace, disabled legacy
  code, and historical records.
- The old root logo filename was left untouched and unused rather than deleting
  or silently repurposing a binary asset.

### Step 0 ownership

- Slicer owns the DICOM database/browser, MRML scene, scalar volume, and slice
  viewers.
- `DENTOWorkflow` owns only the focused buttons, selected-node state, metadata
  presentation, and workflow guidance.
- No DICOM parser, image renderer, PyTorch package, or external backend was
  added.

### Implementation

- Root `CMakeLists.txt` now declares `project(DENTOBOT)` and builds only
  `DENTOWorkflow`.
- The old `DentalNavPlanning` folder was preserved but removed from the build,
  preventing its threshold/sample UI from appearing as part of DENTOBOT.
- Added a Qt Designer UI containing:
  - DENTOBOT and Step 0 headings;
  - de-identified case label;
  - New Empty Case and Open Saved Scene;
  - Open DICOM Browser;
  - scalar-volume selector and Show in Slice Views;
  - status and volume metadata fields.
- Added a typed parameter node with `caseName` and `inputVolume`, bound using
  `SlicerParameterName` properties.
- Before opening DICOM, the widget records existing scalar-volume node IDs. On
  return to DENTO Workflow, it selects the newest volume created by that DICOM
  visit; otherwise it preserves the saved selection or chooses the latest
  scalar volume when no selection exists.
- Volume metadata validation checks scalar-node type, image data, dimensions,
  positive finite spacing, and a non-singular IJK-to-RAS matrix. Orientation is
  summarized by dominant I/J/K directions in Slicer RAS.
- Selecting a valid volume sets it as the background in standard slice views
  and fits the views.
- Scene and parameter observers are disconnected during module exit, scene
  close, and cleanup, then restored on re-entry as needed.
- New Empty Case asks for confirmation before clearing MRML nodes and explicitly
  states that original DICOM files are not modified.

### Supporting API review

Official Slicer documentation/source was consulted for:

- DICOM browser/module usage;
- `SlicerParameterName` GUI binding and typed parameter nodes;
- scripted-module UI loading;
- `setSliceViewerLayers(background=..., fit=True)`;
- `loadScene`, which raises on failure rather than requiring a Boolean check;
- Slicer's standard Yes/No confirmation helper.

### Validation performed

- Static AST parsing confirmed valid Python syntax without importing or
  executing the Slicer module.
- PowerShell XML parsing confirmed that the `.ui` file is well formed.
- Parsed-XML checks confirmed all UI names referenced by Python exist.
- `caseName` and `inputVolume` parameter bindings were found.
- Static CMake inspection confirmed the new module is included and the legacy
  module is excluded.

### Failed auxiliary check and resolution

- The first PowerShell widget-name check used incorrectly escaped quotes in a
  `Select-String` expression. PowerShell emitted parameter-binding errors even
  though the surrounding command returned exit code zero and printed a
  misleading PASS line.
- This was a validation-script failure, not a DENTOWorkflow code failure. It
  made no file changes and required no reversion.
- The check was replaced with XPath queries against the already parsed XML.
  The corrected check passed for every Python UI reference.

### Not tested

- Slicer 5.12.2 was not launched.
- The module was not imported in Slicer's embedded Python.
- Slicer-native tests were not run.
- DICOM import/load, automatic post-DICOM selection, slice display, New Case,
  MRB save/reopen, and UI layout remain manual acceptance items.
- No installed Slicer directory, WSL environment, dependency, or model was
  changed or launched.

### Next action

Load `DENTOWorkflow` into the newly installed Slicer 5.12.2, run the module's
Reload and Test action, and then perform the Step 0 UI/DICOM/scene-round-trip
checklist. Fix only evidence-backed compatibility issues found in that run
before beginning standalone inference Step 1.

## 2026-07-22 20:13:27 IST (UTC+05:30) — Direct process decision and documentation update

### Request summary

The developer objected to a jobs-based Slicer–WSL interface. Their preferred
mental model was a Slicer Python module that launches an ordinary Python
backend in the appropriate WSL environment, allowing core inference to be
developed and tested independently of Slicer.

They then authorized updating the project documents and requested two raw
records:

- a detailed textual changelog for version/context tracking;
- a detailed session logbook covering ideas, prompts, implementation,
  failures, causes, fixes, and reversions.

Both records were required to include date and time for each update unless a
single timestamp naturally covers redundant details.

### Technical clarification

- Slicer scripted modules run in Slicer's embedded Windows Python process.
- A WSL package runs in a distinct Linux Python process. Installing or
  selecting a WSL environment does not make its Linux modules importable into
  Slicer, and an MRML node cannot be passed as an in-process Python object.
- Slicer can nevertheless start the WSL Python command directly and own its
  lifecycle.
- Bulk CBCT/segmentation data still require serialization across the process
  boundary. NIfTI is retained because it carries voxel geometry and an affine.

### Alternatives considered

1. **Folder/job queue with request and result manifests:** inspectable and
   recoverable, but too much orchestration for the initial single-user
   workflow.
2. **Direct one-shot WSL process:** simplest initial control flow, with Slicer
   receiving live output and exit status. Selected as the baseline.
3. **Persistent localhost service:** potentially useful for repeated low
   latency calls, shared GPUs, multiple clients, or remote inference, but not
   justified before measurements.
4. **Import Linux inference packages directly into Slicer:** rejected because
   the Windows and Linux interpreter/binary environments are separate.

### Accepted decision

The baseline inference path is now:

```text
Slicer MRML volume
  -> export geometry-preserving NIfTI
  -> asynchronously invoke explicit WSL Python command
  -> stream structured stdout and diagnostics
  -> inspect process exit status
  -> validate NIfTI + result metadata
  -> import segmentation into MRML
```

Per-run directories remain only as staging, diagnostic, and reproducibility
artifacts. There is no watched-directory queue, polling worker, or persistent
backend service in the baseline.

### Documentation implemented

- Updated `AGENTS.md`, `PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, and
  `DEVELOPMENT_PLAN.md` to use the direct process model.
- Added `changelog.md` and `logbook.md`.
- Added a repository/documentation structure and mandatory agent rules for
  maintaining both records.
- Preserved the earlier job-contract decision as explicitly superseded history
  instead of silently rewriting the record.

### Documentation-editing observation — 2026-07-22 20:19:48 IST (UTC+05:30)

- An initial combined documentation patch was rejected because one large
  architecture context block did not match exactly.
- The patch tool rejected that attempt before applying it, so there was no
  partial state to revert.
- The change was reapplied as smaller patches per document and section. Those
  patches succeeded.
- Verification then found two remaining active uses of “job” in the agent
  rules and Step 2 acceptance criteria. They were changed to “run.” Remaining
  job terminology is restricted to historical explanations or explicit
  rejection of a folder-based job service.

### Validation status

Documentation-only at this point. No Slicer or WSL process was launched and no
backend CLI was implemented or tested. At `2026-07-22 20:19:48 IST
(UTC+05:30)`, Markdown fence counts were confirmed even and no non-document
file had been modified during this update. The next implementation milestone
remains Step 0 unless the developer explicitly authorizes another milestone.

## 2026-07-22 20:13:27 IST (UTC+05:30) — Retrospective reconstruction of prior sessions

This reconstruction was written at the stated timestamp from the available
conversation and repository. Exact times for the earlier events were not
captured. The sequence below preserves their known order but must not be
treated as minute-accurate history.

### 1. Initial planning and agent-context request

- The developer had created a Slicer extension and module from templates and
  requested an academic PRD-like development document suitable for clean
  agentic coding and prompt engineering.
- `docs/AGENTS.md` was designated as the rigid source of project instructions.
- The target runtime was identified as official 3D Slicer 5.12.2.

### 2. Original Task 1 trajectory foundation

- The initial plan preserved the generated threshold UI while adding a
  `vtkMRMLMarkupsLineNode` parameter reference, trajectory creation logic,
  world-RAS length calculation, and Slicer-native tests.
- Loading a CBCT was deliberately not part of Task 1 because the logic was
  intended to be testable from known world-coordinate points independent of
  image data.
- This caused understandable product-context confusion: a mathematical line
  existed without yet defining the dental procedure, source CBCT, anatomical
  entry, or target. The later roadmap therefore moved procedure semantics and
  trajectory planning after imaging and segmentation review.

### 3. Markups API failure

- The first trajectory implementation attempted
  `vtkMRMLMarkupsLineNode.SetMaximumNumberOfControlPoints(2)`.
- Slicer 5.12.2 raised `AttributeError` because that wrapped setter was not
  available; the node exposed `GetMaximumNumberOfControlPoints()`.
- The current repository code creates the line and verifies that the line-node
  class already reports a maximum of two points. It removes the node and raises
  an error if the invariant is not true.
- A final passing in-Slicer test was not captured and must not be claimed.

### 4. Confusing sample volume and console messages

- Reload-and-test displayed a head MR/CT-like sample because the generated
  threshold test still registered and downloaded Slicer sample data. It was
  not the developer's CBCT and was not introduced as a new DentalNav dataset.
- Messages stating that exactly two trajectory points or a valid line were
  required corresponded to deliberate negative tests, but they appeared as
  application errors and made the test output confusing.
- VTK warnings about filters with zero input connections were also observed
  around the generated threshold/sample workflow.
- Task 1 implemented logic/tests only; it did not add an interactive trajectory
  placement UI. Therefore no visible planned trajectory was expected from the
  module UI at that stage.
- No clean, final Task 1 acceptance run was recorded.

### 5. Concern about installed Slicer files

- The developer was concerned that original Slicer files had been changed.
- The repository work belongs under
  `E:\IITM_DentaNav\DentalNav\DentalDrillNav`; editing extension source there
  is separate from modifying the installed Slicer application.
- To make the boundary enforceable, agent instructions now prohibit editing
  installed Slicer, automatically installing packages/extensions, or launching
  Slicer/WSL/installers/model downloads without explicit authorization.
- The developer later chose to uninstall and reinstall Slicer. That external
  installation action was not performed by the repository documentation work.

### 6. Proposed Task 1.5 dental segmentation

- The developer proposed loading CBCT, running TotalSegmentator's dental
  `teeth`/ToothFairy model from one module button, preferring CUDA, and first
  proving that results and metadata return to the 3D workspace.
- Display and interactive label review were intentionally deferred until
  backend execution worked reliably.

### 7. Installed-Slicer PyTorch failure

- TotalSegmentator inside Slicer failed while importing PyTorch with
  `ModuleNotFoundError: No module named 'torchgen'`.
- PyTorchUtils then failed to uninstall `torch` and `torchvision` because its
  pip subprocess returned a nonzero exit status.
- The symptoms were consistent with an incomplete or inconsistent embedded
  PyTorch installation, but a complete root-cause diagnosis and successful
  repair were not recorded.
- No fix was validated. The developer elected to reinstall Slicer cleanly.
- This failure motivated keeping PyTorch/CUDA/model dependencies outside
  Slicer's embedded Python environment.

### 8. Hybrid Slicer and standalone Python idea

- The developer proposed independently developing inference scripts in WSL2,
  then bridging them into a Slicer-based UI.
- The accepted correction was not to copy or "rip" Slicer internals into a
  new standalone viewer. Instead, early development uses a focused Slicer
  extension that reuses DICOM, MRML, slice views, rendering, segmentations,
  markups, and persistence.
- After the workflow is stable, supported custom-Slicer packaging can reduce
  visible modules and application chrome.
- Robot integration is deferred and transport-neutral. ROS/ROS2 will be
  reconsidered only when robot drivers, MoveIt, distributed processes, or
  other concrete requirements justify it.

### 9. First documentation reset

- The governing documents were rewritten around the extension-first,
  custom-application-later strategy.
- Step 0 became a minimal DentalNav workflow shell using Slicer's DICOM loader
  and standard views; Step 1 became independent WSL inference; Step 2 became
  one-click integration.
- That reset initially described a file/job contract with request/result JSON.
- No application code was changed during the reset.

### 10. Reconsideration of the file/job interface

- The developer challenged whether a jobs-based interface was efficient.
- Review concluded that job folders were overly elaborate as the primary
  control plane for the initial desktop workflow.
- The decision was revised to the direct asynchronous process architecture
  documented in the preceding entry. This was a specification replacement,
  not a code reversion, because the job adapter had not been implemented.

### Open items after reconstruction

- Review and authorize Step 0 implementation.
- Decide the exact name/location of the future `DentalNavWorkflow` module.
- During Step 1, select and record the WSL distribution, Linux Python version,
  environment manager, CUDA/PyTorch/TotalSegmentator versions, model cache,
  and representative de-identified test data.
- Define a safe, testable cancellation strategy for the WSL process tree.
- Define structured stdout event and result JSON schemas before implementing
  the Step 2 adapter.
- Do not claim Task 1, TotalSegmentator, CUDA, or WSL integration is currently
  passing.
