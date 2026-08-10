# DENTOBOT Architecture

> Ubuntu transition note (2026-07-29): this architecture records the accepted
> Windows/WSL implementation baseline through Step 3C. Platform-specific
> process, path, GPU, and packaging boundaries are migration inputs, not yet
> verified Ubuntu architecture.

## Architectural overview

```text
Windows
|
+-- 3D Slicer / later DENTOBOT custom Slicer application
|   |
|   +-- DENTOWorkflow scripted module (focused user workflow)
|   +-- Slicer DICOM, MRML, slice/3D views, segmentations, markups
|   +-- Direct WSL process adapter
|       +-- NIfTI payloads
|       +-- structured stdout + exit status
|       `-- JSON result metadata
|
+-- WSL2 inference environment
|   |
|   +-- DENTOBOT inference Python package and tests
|   +-- PyTorch/CUDA
|   +-- TotalSegmentator `teeth` / ToothFairy3
|   +-- Future image-processing or planning backends
|
+-- External robot-control environment (later)
    |
    +-- Robot adapter and simulator
    +-- Motion planning and hardware API
    +-- Safety interlocks and real-time control
```

The boundaries are deliberate. Slicer owns interactive medical-image state;
WSL2 owns dependency-heavy compute; the robot runtime owns hardware safety and
real-time behavior.

## Active Ubuntu workspace and configuration boundary

The Ubuntu development layout preserves the DentoBot Git checkout inside the
ROS 2 workspace while versioning its surrounding operational controls:

```text
/home/light-tarun/dentobot
|-- .dentobot.env                     # local machine values; never Git
|-- AGENTS.md -> .../Workspace/AGENTS.md
|-- compose.yaml -> .../Workspace/compose.yaml
|-- docs -> .../Workspace/docs
|-- scripts -> .../Workspace/scripts
`-- ros2_ws/src/DentoBot              # Git checkout
    |-- Workspace                     # tracked wrapper/configuration
    |-- DENTOWorkflow
    `-- Inference
```

The tracked launcher resolves both roots from its own canonical path, reads
the single local environment file, derives the Conda environment directory,
and exports an explicit `DENTOBOT_*` contract to Compose and Slicer. Compose
uses absolute workspace bind sources. DENTO Workflow consumes the launcher
backend Python and run-record root automatically but stores only the choice to
use launcher configuration, not the machine paths, in its parameter node.
Manual paths remain an advanced compatibility override.

This is still a two-interpreter architecture. Slicer does not activate Conda
or import its packages. It starts the external interpreter as a child process
and exchanges geometry-bearing NIfTI plus JSON metadata. Per-run records are
local evidence/payload directories, never a queue and never a Git or Drive
artifact.

## UI strategy

### Phase A: extension-based workflow development

Develop `DENTOWorkflow` as the single user-facing home module inside an
official Slicer installation. It will present a staged UI such as:

1. Case and imaging
2. Segmentation
3. Planning
4. Registration and calibration
5. Navigation and simulation
6. Robot connection
7. Review and export

Only implemented stages are enabled. Standard Slicer slice and 3D views stay
visible. Developer tools and other Slicer modules remain available to the
developer, even though routine workflow users should not need them.

The generated `DentalNavPlanning` threshold example is not the product UI and
is excluded from the extension build. Its useful experiments may be migrated
into correctly named DENTO modules after review.

### Phase B: reduced custom application

After end-to-end workflow validation, create a custom Slicer build using the
Slicer Custom Application Template or supported Slicer build options. Set the
DENTO Workflow as the home module, bundle required extensions, and disable
or hide irrelevant modules, menus, and toolbars.

This phase changes packaging and presentation, not the MRML data model or
workflow contracts developed in Phase A.

## Step 0 imaging architecture

DENTOBOT does not implement a DICOM parser or renderer. The first workflow
page provides a minimal DENTOBOT-controlled entry point that:

1. Opens Slicer's DICOM browser/import workflow.
2. Lets the user load a DICOM series into the MRML scene.
3. Selects or confirms the resulting `vtkMRMLScalarVolumeNode`.
4. Shows volume identity, dimensions, spacing, scalar range, orientation, and
   geometry status.
5. Uses standard Slicer slice and 3D views for inspection.
6. Stores the selected volume in the DENTOWorkflow parameter node.

Original DICOM is never rewritten. Auxiliary or malformed files are handled
through a non-destructive clean working copy outside the source dataset.

## Slicer module organization

Initially prefer one workflow module with internal logic classes instead of
forcing users to switch between many modules:

```text
DENTOWorkflowWidget
|
+-- Imaging page
+-- Segmentation page
+-- Planning page
+-- Registration/navigation pages (later)

DENTOWorkflowLogic
|
+-- Case and MRML orchestration
+-- Inference process adapter
+-- Planning operations
+-- Validation and metadata operations
```

Split logic into additional Python files or hidden modules only when a
boundary becomes independently reusable or testable. Modules communicate
through MRML nodes and explicit interfaces, not widget-to-widget access.

All new module identifiers use `DENTO` plus PascalCase. `DENTOWorkflow` is the
home/orchestration module. If segmentation, registration, trajectory planning,
navigation, or robot integration later warrant separate modules, their names
will be `DENTOSegmentation`, `DENTORegistration`, `DENTOTrajectory`, and
similarly structured identifiers. User-facing labels may contain spaces.

## External inference architecture

### Package boundary

The repository will contain an ordinary Python package under `Inference/`:

```text
Inference/
|-- pyproject.toml
|-- environment.yml
|-- src/dentobot_inference/
|   |-- __main__.py
|   |-- cli.py
|   |-- health.py
|   |-- roundtrip.py
|   `-- segmentation.py
|-- tests/
`-- dependency lock file       # after compatibility validation
```

It must run and be testable without Slicer. The first implemented commands
are:

```text
python -m dentobot_inference health --json --require-cuda
python -m dentobot_inference roundtrip --input <input.nii> --output <roundtrip.nii> --result-json <result.json> --run-id <uuid>
python -m dentobot_inference segment-teeth --input <input.nii> --output <teeth-segmentation.nii> --result-json <result.json> --run-id <uuid>
```

### Bridge A, Bridge B, and Bridge C

The integration slices establish one boundary in independently testable stages:

- **Bridge A — environment health:** `DENTOWorkflow` launches the exact Python
  interpreter configured by the user inside the named WSL distribution. The
  backend reports interpreter identity, package versions, PyTorch import
  health, CUDA availability, and device names as JSON. CUDA failure is
  explicit; there is no silent CPU fallback.
- **Bridge B — image round trip:** Slicer exports the selected scalar volume to
  an isolated run directory as NIfTI. The WSL backend loads, rewrites, reloads,
  and checks its affine, shape, voxel type, and voxel checksum. Slicer then
  validates the returned MRML volume's dimensions, scalar type, and IJK-to-RAS
  matrix before retaining it in the scene.
- **Bridge C — GPU teeth segmentation:** the same selected-volume and process
  boundary runs TotalSegmentator `teeth` on CUDA device 0, validates a
  multilabel NIfTI plus schema-versioned metrics, then creates a named and
  colorized `vtkMRMLSegmentationNode`. Binary-labelmap and closed-surface
  representations provide interactive 2D and 3D display.

All commands use the same asynchronous adapter, bounded live output, process
exit status, schema-versioned JSON, and argument-list construction. Neither
Slicer nor the backend command installs packages, edits Slicer, or treats the
artifact directory as a queue. Bridge C replaces TotalSegmentator's implicit
weight downloader with a cache-only guard and rejects unavailable CUDA rather
than silently using the CPU.

### Runtime boundary

The Slicer module runs in Slicer's embedded Windows Python interpreter. The
inference package runs in a separate Linux Python interpreter inside WSL2.
Linux PyTorch/CUDA modules cannot be imported into the Windows Slicer process,
and MRML node objects cannot be passed directly into the Linux process.

The boundary is therefore an explicitly controlled external process, not a
Python import and not a folder-based job service.

### Direct process execution

For each inference request, the Slicer adapter:

1. Validates the selected source volume and backend configuration.
2. Creates a unique run ID and short staging directory.
3. Exports the source volume to NIfTI with its affine intact.
4. Starts `wsl.exe` asynchronously with an argument list containing the WSL
   distribution, absolute Linux Python interpreter, module name, input,
   output, result metadata path, and run ID. Bridge C itself fixes execution
   to CUDA device 0.
5. Streams structured stdout and ordinary diagnostic output into the Slicer
   UI without blocking the Qt event loop.
6. Supports cancellation and records the terminal process exit code.
7. On success, validates the output and imports it into MRML.

Conceptually, the argument list represents:

```text
wsl.exe
  --distribution <distro>
  --exec <linux-python>
  -m dentobot_inference segment-teeth
  --input /mnt/c/DENTOBOTRuns/<run-id>/input.nii
  --output /mnt/c/DENTOBOTRuns/<run-id>/teeth-segmentation.nii
  --result-json /mnt/c/DENTOBOTRuns/<run-id>/result.json
  --run-id <run-id>
```

The implementation passes these as separate process arguments. It does not
concatenate a shell command, depend on interactive environment activation, or
use a watched folder. The WSL distribution and Python interpreter path are
explicit configuration values verified by the health check.

### Run artifacts

Use a short, configurable staging root such as `C:\DENTOBOTRuns`. Each run
has an isolated UUID directory visible to WSL2 under `/mnt/c/DENTOBOTRuns`:

```text
<run-id>/
|-- input.nii
|-- teeth-segmentation.nii
`-- result.json
```

This directory is a payload, diagnostic, and reproducibility artifact. It is
not polled as a queue and does not control execution. Large model computation
may copy data into the WSL-native filesystem internally if measurement shows
that mounted Windows-file performance is a bottleneck, but final output must
return to the adapter-visible run directory.

### Process status contract

- Structured progress is emitted as one JSON object per stdout line with an
  event type such as `started`, `progress`, `warning`, or `completed`.
- Human-readable diagnostics are streamed through the process adapter.
- Exit code zero means the command reached a successful terminal state;
  nonzero exit codes distinguish invalid input, environment/model failure,
  GPU failure, out-of-memory, cancellation, and inference failure.
- The Slicer adapter treats a success exit code without valid output and
  metadata as a failed run.

### Result contract

`result.json` includes at minimum:

- schema version, run ID, command, and terminal status
- actionable error code/message when unsuccessful
- backend, task, model/package versions, and weights identifier when available
- requested/actual device, CUDA version, and GPU name
- start/end timestamps and runtime
- input dimensions, spacing, scalar type, and affine
- output filename, dimensions, spacing, affine, and integer label type
- label ID-to-name mapping and segment count
- inference duration, peak allocated/reserved GPU memory, foreground voxel and
  physical volume totals, and per-label voxel/volume metrics

### Import invariants

Before creating or updating a `vtkMRMLSegmentationNode`, validate:

- run ID and schema are expected
- process exited successfully and result status is successful
- output exists and is readable
- shape and physical geometry match the input within defined tolerances
- labels are non-negative integers
- every nonzero label has metadata

The imported segmentation receives namespaced `DENTOBOT.*` attributes that
link it to its source volume, inference result metadata, model/package
versions, CUDA device, runtime, GPU memory, and artifact paths. Bridge C makes
the validated result visible.

Step 3A adds an MRML-native review surface without copying or modifying mask
geometry. The existing `teethSegmentation` parameter reference drives a
segmentation selector and a grouped, FDI-aware label explorer. Search and
selection live in the widget; segment visibility, per-segment emphasis, global
2D/3D visibility, and opacity live in the segmentation display node and
therefore follow normal scene persistence. `Show All`, `Hide All`, and
`Isolate Selected` act only on display properties.

Step 3B keeps quantitative inspection and provenance on the authoritative
segmentation node so an MRB scene does not depend on a live WSL process. The
source CBCT is a proper node reference with role `DENTOBOT.SourceVolume`.
Namespaced `DENTOBOT.*` attributes store the run, backend/model/package,
device, timing, artifact-path, aggregate-metric, and review-state fields.
`DENTOBOT.SegmentMetricsJson` is a versioned compact document keyed by stable
segment ID and contains each detected label's model ID, source name, voxel
count, and physical volume. New Bridge C imports write this metadata after all
result validation succeeds. An older imported Bridge C segmentation may
migrate once from its retained validated `result.json`; inability to restore
that file is non-fatal and leaves the masks available with an explicit
metadata warning.

Review state applies to the whole segmentation and is limited to
`Unreviewed`, `Needs Correction`, or `Reviewed`, with a UTC update timestamp.
It is a researcher workflow marker, not an approval signature or anatomical,
clinical, regulatory, or treatment validation.

Step 3C delegates mask correction to Slicer's built-in Segment Editor. DENTO
Workflow validates the selected segment and the persisted
`DENTOBOT.SourceVolume` reference, configures Segment Editor with that
segmentation/source/segment triple, clears display-only emphasis, and switches
modules. Beginning a correction revision immediately changes the universal
state to `Needs Correction`, stores `DENTOBOT.CorrectionStartedUtc`, and marks
`DENTOBOT.SegmentMetricsValidity` as `pre-correction-inference`. This
conservative transition is required because DENTO Workflow releases its MRML
observers when Segment Editor becomes active; a previously `Reviewed` result
must not remain approved during an external editing session.

When DENTO Workflow is active, only `vtkSegmentation` source-representation
content changes and segment addition/removal record
`DENTOBOT.LastSegmentationEditUtc` and invalidate a previously reviewed state.
Generic segment metadata changes and display-node changes are intentionally
excluded. The original inference metrics remain available as provenance but
are explicitly labelled baseline-only after correction begins; Step 3C does
not silently present them as measurements of corrected masks. Review remains
segmentation-wide; per-label approval state is not part of the current data
model.

## Service evolution

The one-shot direct CLI process is the baseline because it is simple,
inspectable, independently testable, and under the Slicer adapter's lifecycle
control. A persistent localhost or remote service is introduced only if
measurements show a material need for lower repeated-call latency, shared GPU
scheduling, multi-client access, or remote inference. OpenIGTLink is reserved
for live transforms and device data, not bulk AI inference.

## Repository and documentation structure

```text
DentalDrillNav/                 # current workspace directory; project is DENTOBOT
|-- DentalNavPlanning/          # disabled legacy scaffold and experiment
|-- DENTOWorkflow/              # current focused Slicer workflow module
|-- Inference/                  # standalone WSL Python package
|   |-- requirements/           # validated top-level dependency manifests
|   |-- environment.yml        # minimal Conda/Python bootstrap
|   `-- validated-environment.json
|-- docs/
|   |-- AGENTS.md               # mandatory agent rules
|   |-- PROJECT_CONTEXT.md      # product and research context
|   |-- ARCHITECTURE.md         # accepted system boundaries and contracts
|   |-- DEVELOPMENT_PLAN.md     # staged roadmap and acceptance criteria
|   |-- REPRODUCIBILITY_AND_TRACEABILITY.md
|   |-- changelog.md            # timestamped low-level change history
|   `-- logbook.md              # timestamped session/reasoning history
`-- CMakeLists.txt
```

The uppercase documents are controlled, concise sources for accepted context,
architecture, roadmap, and the formal inference reproducibility procedure. The
two lowercase raw records are append-oriented sources of detail:
`changelog.md` describes actual changes, while `logbook.md` preserves ideas,
prompts, decisions, attempts, failures, fixes, reversions, and unresolved work.
When the accepted baseline changes, update the applicable controlled documents
and record the reason and effect in both raw records.

The repository files are canonical and are mirrored byte-for-byte as Markdown
in the connected `IITM Dentobot/docs` Google Drive folder for use by the
non-Codex project chat. Existing Drive file IDs are updated in place. A request
to update the changelog or logbook also triggers synchronization of those
files and any other design documents changed in the same batch. The mirror
contains documentation only; patient data, run artifacts, models, and secrets
are excluded.

## Planning and registration architecture

- Dental annotations and AI outputs live in segmentation/markup nodes.
- A trajectory is an explicit two-point line with documented entry/target
  semantics and world-RAS length.
- Step 4A trajectory verification reuses that same line and the source CBCT
  referenced by its authoritative segmentation. A native slice view receives
  a longitudinal `SliceToRAS`: column 0 is the angle-rotated transverse axis,
  column 1 is Entry→Target, column 2 is their cross-product plane normal, and
  column 3 is the trajectory midpoint. The `-180°..+180°` control therefore
  rotates anatomy circumferentially without moving the line or creating a
  derived volume. The prior slice/composite/line-display state is restored
  when verification ends and is excluded from saved presentation state.
- During 2D Entry/Target correction, Markups start/end-interaction events hold
  that slice matrix fixed under the pointer. After the drag, the previous
  plane normal is minimally projected onto the corrected trajectory's
  perpendicular space, then the longitudinal frame is rebuilt around it. An
  edit made in the displayed plane keeps that exact circumferential plane;
  subsequent slider motion is delta-based from the transported frame. Reset
  alone returns to the deterministic world-reference zero frame.
- The Markups-line class contract is enforced as exactly two possible control
  points, labelled Entry and Target. Zero/one defined points are incomplete
  drafts; imported or programmatic lines outside that contract are rejected.
- Selecting or reopening a persisted trajectory restores its target
  segmentation, segment ID, target bounds ROI, tooth selector, highlight, and
  details from MRML references/attributes as one guarded update. Managed names
  expose FDI, sequence, and completion state for usability, but names are never
  identity or provenance keys.
- A target-tooth selection never retargets a trajectory already associated
  with another tooth. It deselects that line and resolves one reusable target
  bounds ROI for the exact segmentation/segment pair. All trajectory groups
  remain available and visible; the selected tooth changes opacity, glyph,
  line, and label emphasis without changing visibility.
- Once a tooth has a trajectory, its deterministic persisted RGB lineage color
  is propagated through reference-linked Step 4A bounds, Step 5A support
  anatomy, Step 5B ROI/shell/sleeve nodes, and Step 5C trim/final-shell nodes.
  This is presentation metadata; role attributes, segment IDs, and MRML
  references remain authoritative.
  Steps 5A/5B/5C render the same lineage as an FDI/color badge and selector
  swatches, with Step 5B visibility-control stripes so hidden geometry still
  has a clear parent/child cue.
- Destructive planning actions are role-gated and confirmed. Deleting a
  DENTOBOT trajectory or draft support-anatomy model removes the primary MRML
  node and only its unreferenced display/storage auxiliaries, then clears the
  relevant workflow reference. The reference is cleared before scene removal
  to prevent a live selector from substituting an unrelated node. Shared nodes
  and source inputs are preserved.
- Trajectory deletion retains target tooth, segmentation, and bounds; draft-
  model deletion retains target/support selection. MRML save/reload must not
  restore deleted nodes or dangling workflow references, and retained inputs
  must remain sufficient to recreate the output.
- Step 5B converts the Step 5A model to world-RAS VTK geometry before sampling
  an ROI-trimmed exterior distance band. It subtracts a channel aligned to the
  locked Entry-to-Target line and creates a separate analytic annular sleeve
  extending outward from Entry. Both derived models store explicit source,
  trajectory, and ROI references plus their parameter and topology metadata.
- Step 5B output is stale whenever the source model revision, trajectory world
  points, ROI world bounds, or dimensional parameters differ from the values
  captured at generation. The resulting shell is a non-destructive raw source;
  Step 5B does not expose STL export.
- Step 5C stores a separate finalized shell and uses Slicer's built-in Dynamic
  Modeler. Plane Cut supplies capped positive/negative regions for the simple
  horizontal trim; Curve Cut supplies inside/outside regions for the adjustable
  uneven margin, followed by an explicit capping/triangulation/normal pass.
  Empty or non-watertight finalized geometry is rejected.
- Step 5C isolation is a temporary one-up 3D workspace aligned to the current
  Step 5B automatic ROI. At yaw zero the camera looks along ROI `+Y`, ROI `+X`
  is viewport right, and ROI `+Z` is viewport up; half the ROI Z size is the
  parallel scale, aligning its top/bottom with the viewport. An in-viewport XYZ
  axes marker makes that frame visible; its prior marker and axis-label settings
  are restored on exit. The default lock
  fixes translation, pitch, and roll while allowing yaw around ROI `+Z` and
  interactive zoom; a second lock freezes yaw but still permits zoom. The
  horizontal plane has exactly one editable origin point, remains normal to
  ROI `+Z`, and projects its origin onto the ROI Z axis so only signed height
  can change. This is an ROI frame, not an anatomy-derived dental/occlusal
  frame, and no automatic 70–80 percent coverage rule is encoded.
- Isolation saves the previous layout, camera, crosshair, and display
  visibility; explicit exit, module exit, scene close, and cleanup restore
  them. It does not create a markup or enter placement mode. Plane/curve
  placement is deliberate and separate, and 2D views return for later manual
  verification instead of rendering/interacting alongside the 3D edit.
- Step 5C persists source/edit/Dynamic-Modeler references, source revision,
  method, kept region, edit geometry, state, and topology metrics. A source,
  method, region, or markup change makes the finalized shell Stale. Export
  accepts only a Current, source-matched, watertight Step 5C shell and Current
  Step 5B sleeve. STL export is an explicit local action and never implies
  printability, manufacturing approval, or clinical/drilling authorization.
- Deleting Step 5C removes its role-owned plane, curve, finalized shell,
  Dynamic Modeler node, and cut-output auxiliaries while retaining the Step 5B
  source. Confirmed Step 5B deletion first cascades through those Step 5C
  children so it cannot leave dangling source references.
- The Step 5B automatic bounds ROI is a separately owned, role-gated node.
  Its historical `TemplateShellTrimROI` role string is retained for scene
  compatibility, but its earlier user-adjustable semantics are superseded.
  It is recomputed from Step 5A before shell generation. Deleting it
  removes only the ROI and unshared auxiliaries; Step 5A, trajectory,
  dimensions, shell, and sleeve remain, with the derived outputs marked Stale
  until a new ROI is created and generation is rerun.
- Step 4A target bounds and the Step 5B automatic ROI have mutually exclusive
  role attributes. The Step 5B selector lists only its own role; reset, generation,
  and deletion repeat the role check in logic, and reset/generation also
  require the ROI's source reference to match the current Step 5A model.
  Legacy Step 4A nodes carrying stray Step 5B metadata are repaired in place;
  invalid Step 5B references are cleared without deleting the referenced
  upstream node. Parameter-to-widget synchronization is non-reentrant so the
  resulting MRML repair/name/stale events cannot recurse during scene load.
- Both workflow-owned ROI roles are visible-only geometry: their MRML nodes
  are locked and non-selectable from views, and their translation, rotation,
  and scale handles are disabled on creation, reset, scene load, and refresh.
- Step 5B exposes display-only visibility controls for the selected Step 4A
  target box and trajectory, Step 5A support model, and Step 5B trim ROI,
  shell, and sleeve. These controls write MRML display-node visibility, which
  persists with the scene; geometry refresh/regeneration preserves an
  existing hidden state.
- Workflow-owned nodes carry visible `[Step 4A]`, `[Step 5A]`, `[Step 5B]`, or
  `[Step 5C]` name prefixes for selectors and Slicer's Data view. The prefixes
  are UI categorization only; role attributes, stable segment IDs, and MRML
  node references remain authoritative.
- Planning approval is explicit state, invalidated when relevant anatomy,
  trajectory, or registration changes.
- Registration, calibration, tracking, and tool poses are transform nodes in
  a documented frame tree.
- Metrics such as FRE, target error, lateral error, angular error, and depth
  error are computed in reusable logic and displayed by the workflow UI.

## Robot architecture and ROS decision gate

Slicer communicates only with a high-level `RobotAdapter` interface:

```text
connect / disconnect
getCapabilities
loadApprovedPlan
getState
simulateMotion
requestMotion
cancelMotion
acknowledgeFault
```

The initial implementation is a simulator. The hardware adapter and transport
(vendor SDK, local IPC, TCP, serial, or another protocol) are selected only
after robot requirements are known.

ROS/ROS2 is reconsidered if the project needs existing robot drivers, MoveIt,
distributed nodes, standardized transform tooling, or a broader robotics
ecosystem. It is not adopted merely as a message transport. Regardless of
transport, low-level motion and safety never run in the Slicer Python process.

## Packaging and deployment

- Development: official pinned Slicer version plus source extension path.
- AI backend: documented WSL2 distro, isolated environment, locked Python
  dependencies, model cache, and health check.
- Workflow release: packaged DENTOBOT extension plus backend setup guide.
- Final research application: custom Slicer package with DENTO modules
  bundled and irrelevant UI/modules disabled.

## Authoritative references

- Slicer custom builds and application options:
  https://slicer.readthedocs.io/en/latest/developer_guide/build_instructions/overview.html
- Slicer extensions and custom application recommendation:
  https://slicer.readthedocs.io/en/latest/developer_guide/extensions.html
- Slicer DICOM loading workflow:
  https://github.com/Slicer/Slicer/blob/main/Docs/user_guide/data_loading_and_saving.md
- TotalSegmentator:
  https://github.com/wasserth/TotalSegmentator
- NVIDIA CUDA on WSL2:
  https://docs.nvidia.com/cuda/wsl-user-guide/index.html
