# DENTOBOT Architecture

> Cross-platform update (2026-08-11): the Slicer/MRML workflow is shared.
> Windows uses native Slicer plus a WSL2 inference adapter; Ubuntu uses the
> direct Linux adapter inside the verified SlicerROS2 container. Runtime
> acceptance is current on Ubuntu and must be repeated on Windows 11.

## Architectural overview

```text
3D Slicer / later DENTOBOT custom Slicer application
|
|-- DENTOWorkflow scripted module (shared Windows/Linux source)
|-- Slicer DICOM, MRML, slice/3D views, segmentations, markups
`-- Platform process adapter
|   |
|   +-- Windows: native Slicer -> wsl.exe -> Linux backend Python
|   `-- Ubuntu: container Slicer -> direct Linux backend Python
|       +-- NIfTI payloads in an adapter-visible artifact root
|       +-- structured stdout + exit status
|       `-- schema-versioned JSON result metadata
|
+-- Isolated external inference environment
|   |
|   +-- DENTOBOT inference Python package and tests
|   +-- Windows/WSL2: pinned PyTorch/CUDA profile
|   +-- Ubuntu: pinned PyTorch CPU profile
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
the external Linux interpreter owns dependency-heavy compute; the robot
runtime owns hardware safety and real-time behavior. DENTOWorkflow never
imports the external environment into Slicer's embedded Python.

## Step 6 persistent-intent and transient-runtime boundary

```text
MRML / .dentocase (persistent)                 ROS/MoveIt session (transient)
case + world-RAS geometry                      live TF robot + goal robot
base status/source/revision                    Motion Control parameter/probes
optional provisional forehead proxy            publishers/subscribers
Task Home + reviewed assisted limits    -->    strict joint-command guard
immutable task snapshot                        phased task guard configuration
display opacities                               approach/drilling plans + status
```

`DENTORobotWorkflowFacade` is the shared Legacy/New-GUI application seam. It
loads the local MRML robot before ROS, saves/applies Task Home, retains sampled
TCP poses with their six-joint vectors, reviews assisted limits, connects the
runtime without changing modules, synchronizes split target/non-target planning
objects, confirms the task fingerprint, and builds the two preview phases.
Routine calls use SlicerROS2 logic/MRML APIs; the upstream widget is optional
expert diagnostics and never a lifecycle prerequisite.

Task confirmation fingerprints target/trajectory, base, home, reviewed limits,
tool/corridor provenance, and robot resources. Any material input change clears
both transient plans. Appearance and camera changes are excluded. The only
current lock state reachable by an operator is `ProvisionalLocked`;
`RegisteredLocked` is reserved for a future measured registration source.

The explicit CBCT renderer is display-only and singleton-by-source. The curved
forehead proxy is a separately editable visualization envelope, excluded from
planning-scene collision objects and registration evidence. The planning TCP is
`dentobot_drill_tip_provisional`; its CAD offset is not physical calibration.

The external guard preserves the ordinary strict channel and adds task/phase
messages tied to the immutable fingerprint. Terminal contact and drilling may
accept only the burr-to-selected-target pair inside the confirmed corridor.
All other robot/world/self contacts and joint violations remain fail-closed.
No controller or hardware execution path is exposed.

## PoC closure and evidence architecture

The software pipeline and the research-validation pipeline are related but
must not be conflated:

```text
software/MRML correctness
  -> representative anatomy acceptance
  -> printed template seating and dimensional evidence
  -> registration/TRE evidence
  -> robot/tool metrology and safe dry run
  -> bounded end-to-end PoC claim
```

Evidence never propagates upward automatically. A synthetic watertight mesh
test may justify a software-geometry claim, but it cannot justify tooth fit,
print accuracy, docking rigidity, registration accuracy, robot positioning, or
clinical safety. Every milestone records its strongest actual evidence level:
static, synthetic, developer-live, representative anatomy, printed phantom, or
clinician/expert acceptance.

The current fast-track work remains distributed across nine explicit research
lanes: imaging/planning, physical template, registration, head-mounted robot,
tooth-mounted robot, tool/aerotor, sensing and stop logic, verification/
metrology, and research/IP output. The host Arduino pressure-monitor GUI is a
standalone sensing bench in that last hardware-adjacent lane; it is not the
robot-control runtime or a stop-logic implementation. The host Record3D OBJ
viewer is a separate optical-scan inspection bench for iPhone LiDAR exports;
it is not a Slicer RAS import path or a registration method. The UI workflow is not a substitute for
those lanes. In particular, registration and metrology begin while Template V0
is being closed rather than waiting for every planning convenience feature.

The minimum coordinate-frame model for the next robotics bridge is:

```text
CBCT/Slicer RAS
  -> tooth/template planning frame
  -> physical template/docking frame
  -> robot base frame
  -> end-effector frame
  -> bur/tool frame
```

Every edge must be directionally named, tied to a measurement/calibration or
known geometry, timestamped where relevant, and assigned invalidation events.
Registration quality is evaluated at/near the drilling target with target
registration error; fiducial residual alone is insufficient. Template
reseating and robot redocking are distinct repeatability contributors, and
registration error remains separate from robot/TCP positioning error.

## Medical-image display and accuracy boundary

The corrected `vtkMRMLSegmentationNode` remains authoritative and retains
`Binary labelmap` as its editable/source representation. DENTOWorkflow offers
two explicitly different 2D presentation paths through the same MRML node:

- **Native mask pixels (authoritative)** displays the exact binary-labelmap
  samples and is the default, including for older scenes. The visible voxel
  stair-steps are intentional, and this mode is selected before handing a
  segment to Segment Editor.
- **Derived smooth preview (optional)** asks the segmentation display node to
  use the existing derived `Closed surface` representation in slice views. It
  is explicitly non-authoritative and never enabled automatically.

The source CBCT display node exposes only native window/level,
Grey/InvertedGrey lookup-table direction, and interpolation properties. A
per-loaded-volume in-memory snapshot provides a restore action. No alternate
volume or mask is generated, and display changes persist through MRML rather
than through node names. None of these mappings improves acquired resolution
or anatomical truth. Clinical accuracy continues to depend on acquisition
voxel spacing, reconstruction, artifacts, segmentation validation, and
geometric registration.

## Platform launch and configuration boundary

Both launchers provide the same non-persistent environment contract:

```text
DENTOBOT_BACKEND_EXECUTION_MODE=local|wsl
DENTOBOT_WSL_DISTRIBUTION=<required only for wsl>
DENTOBOT_BACKEND_PYTHON=<absolute Linux interpreter>
DENTOBOT_RUN_ARTIFACT_ROOT=<Slicer-visible absolute path>
DENTOBOT_BACKEND_DEVICE=cpu|cuda:0
```

`DENTOPlatform.py` validates this contract, maps local Windows drive paths to
WSL `/mnt/<drive>` paths, and builds shell-free argument arrays. Launcher
paths are never required as MRML identity and are not persisted into new
scenes. The advanced manual fields remain for recovery and legacy scenes.

On Windows, `launch-dentoworkflow.ps1` starts native Windows Slicer and the
backend adapter prepends `wsl.exe`. Docker is not part of core planning. On
Ubuntu, `launch-dentoworkflow.bash` starts the pinned Linux SlicerROS2 image
and the adapter calls the mounted external Linux interpreter directly.

The reusable Ubuntu container has an explicit host-stability boundary. Docker
init reaps descendants below the idle command; a 512-task ceiling prevents an
abandoned Slicer/Xvfb tree from exhausting host PIDs; reduced relative CPU
weight and a positive OOM score preserve preference for the remote desktop
under contention. Headless tests own their X display and use bounded process-
group execution. These are development-runtime containment controls, not
clinical or inference-performance acceptance criteria, and they do not replace
per-run backend cancellation/cleanup.

Normal graphical startup owns the lifecycle of this dedicated container. If it
is already running, the launcher performs a bounded Docker restart before
Compose reconciliation, guaranteeing an empty process namespace for Slicer,
ROS 2, MoveIt, and tests without routinely recreating the mutable container
filesystem. The diagnostic `--check-only` path is intentionally read-only and
continues to reject an active graphical/simulation session instead.

### Active Ubuntu workspace

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

The current Phase-A implementation presents these functions through one compact
stage selector over the existing CTK collapsible sections. Exactly one
top-level stage is expanded at a time, manual section expansion stays
synchronized with the selector, and Previous/Next navigation is presentation
state only. A recommendation is derived from explicit parameter-node inputs but
does not automatically move the operator after initial scene entry. Detailed
guidance, volume metadata, backend overrides, and backend logs remain available
on demand rather than occupying the routine workflow panel continuously.

The active selector contains Case, imaging, segmentation, review, Step 4A
trajectory planning, Step 4B support selection/full-anatomy draft, Step 4C
guide rails/docks, and Steps 5A–5C.
Manual and assisted trajectory creation are two UI paths within Step 4A, not
two sequential workflow stages. They both produce the same referenced
two-point Markups-line representation. The optional assisted controls remain a
collapsible subsection visible only while Step 4A is active.

Support membership follows the same single-authority rule. Step 4B alone owns
the editable same-jaw arch and the persisted membership lock on the
transform-free `TemplateSupportDraft`. Create/update locks; explicit revision
unlocks and invalidates the reference-linked Step 4C/5 branch; rebuild locks
again. Step 5A renders that parent as a read-only package summary and can only
navigate back to Step 4B for change. Its visible-surface controls refine the
locked parent without duplicating target/support membership inputs. A Current
locked model also carries redundant support-ID provenance for narrowly scoped
parameter repair after restore, but source/target mismatch, staleness,
malformed data, or an unlocked state always fails closed.

At every stage, one scene-wide **Views** palette presents the active step's
recommended display, explicit upper/lower/all permanent-tooth mask shortcuts
for 2D, 3D, or both, and a collapsed Advanced inventory. Segmentation records
are classified from their existing review category plus valid permanent-tooth
FDI number, then reduced into operator-facing anatomy groups rather than one
flat row per segment. Routine jaw shortcuts and recommendations use only the
parameter node's authoritative teeth segmentation and input CBCT; unrelated
scene segmentations/volumes remain Advanced objects and cannot leak into the
routine recommended view. Workflow nodes remain grouped by semantic role.
Both Legacy and the six-workspace shell open this same palette and controller.

The recommendation table is explicit for every retained internal stage:

| Stage | Default display intent |
|---|---|
| Case | Case volume in slice views, when available |
| CBCT Imaging | CBCT volume in slice views |
| AI Segmentation | CBCT slices plus all grouped masks |
| Review and Correct | CBCT slices plus all grouped masks for review |
| Step 4A | Target tooth, bounds, and trajectory context |
| Step 4B | Target, selected supports, and complete support draft |
| Step 4C | Support package, trajectory, rails, and docks |
| Step 5A | Support masks, boundary/plane, and visible-surface preview |
| Step 5B | Current shell/guide result, or final template if present |
| Step 5C | Final template, or current shell and docks |
| Step 6 | Active case or phantom with robot and mount context |

Presets and per-group toggles alter display-node visibility only; they never
edit mask voxels, polydata, MRML references, or workflow validity. Before the
first filter the controller snapshots global segmentation 2D/3D visibility
and opacity, every segment's visibility/opacity, and owned-node 2D/3D
visibility. **Restore Previous View** replays that exact snapshot. **Frame
Visible** combines finite world-RAS bounds of the currently visible segments
and nodes and fits existing views without generating geometry.

A volume renderer is not a segmentation mask: it maps scalar CBCT intensities
through a Slicer transfer function and may look like an outer skin/scan
envelope. Opening or refreshing Views must not create a volume-rendering
display node. If one already exists because the operator created it elsewhere
or an MRB restored it, Advanced may list it as **Volume rendering — not a
mask**. It is excluded from every recommended preset and is hidden by an
isolation preset unless explicitly selected.

Viewport presets are deliberately transient presentation state. At MRB save
start, DENTOWorkflow restores the snapshot so the scene stores the operator's
underlying display state; after save it reapplies the active preset. Parameter
replacement, module exit, scene close, or cleanup
restores the snapshot. This avoids making a convenient target-only or
shell-only inspection state an unexplained persistent scene contract. The old
Step 5B-specific visibility group remains readable in compatibility code but
is hidden from the active workflow UI.

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

- **Bridge A — environment health:** `DENTOWorkflow` launches the exact Linux
  Python configured by the platform launcher—through the named WSL
  distribution on Windows or directly on Linux. The backend reports
  interpreter identity, package versions, PyTorch import health, and requested
  device status as JSON. Device failure is explicit; there is no silent
  CPU/CUDA fallback.
- **Bridge B — image round trip:** Slicer exports the selected scalar volume to
  an isolated run directory as NIfTI. The WSL backend loads, rewrites, reloads,
  and checks its affine, shape, voxel type, and voxel checksum. Slicer then
  validates the returned MRML volume's dimensions, scalar type, and IJK-to-RAS
  matrix before retaining it in the scene.
- **Bridge C — teeth segmentation:** the same selected-volume and process
  boundary runs TotalSegmentator `teeth` on the explicit `cpu` or `cuda:0`
  device, validates a
  multilabel NIfTI plus schema-versioned metrics, then creates a named and
  colorized `vtkMRMLSegmentationNode`. Binary-labelmap and closed-surface
  representations provide interactive 2D and 3D display.

All commands use the same asynchronous adapter, bounded live output, process
exit status, schema-versioned JSON, and argument-list construction. Neither
Slicer nor the backend command installs packages, edits Slicer, or treats the
artifact directory as a queue. Bridge C replaces TotalSegmentator's implicit
weight downloader with a cache-only guard and rejects an unavailable requested
device rather than silently changing it.

### Runtime boundary

The Slicer module runs in Slicer's embedded Python interpreter. The inference
package runs in a separate Linux Python interpreter inside WSL2 on Windows or
as a direct child of Linux Slicer. External PyTorch/TotalSegmentator modules
are not imported into Slicer, and MRML node objects cannot cross the process
boundary.

The boundary is therefore an explicitly controlled external process, not a
Python import and not a folder-based job service.

### Direct process execution

For each inference request, the Slicer adapter:

1. Validates the selected source volume and backend configuration.
2. Creates a unique run ID and short staging directory.
3. Exports the source volume to NIfTI with its affine intact.
4. Starts the platform adapter asynchronously with an argument list containing
   the absolute Linux Python interpreter, module name, input, output, result
   metadata path, run ID, and explicit device. Windows prepends `wsl.exe` and
   the configured distribution; Linux invokes the interpreter directly.
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
use a watched folder. The adapter, WSL distribution where applicable, Python
interpreter, artifact root, and device are explicit launcher values verified
by the health check.

### Run artifacts

Use a short, configurable artifact root such as `C:\DENTOBOTRuns` on Windows
or `/workspace/data/dentobot-runs` on Linux. Each run has an isolated UUID
directory; Windows maps the local drive directory into WSL2 under `/mnt`:

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
- Optional Step 4A assistance uses one temporary role-owned Markups fiducial list for
  exactly one or two clinician crown Entry clicks. It is an input annotation,
  not an alternative trajectory. Geometry math runs separately from the UI:
  entry-directed tooth-axis estimation, multi-depth root-side surface caps,
  deterministic transverse two-cluster analysis for the two-root case, and
  Entry↔Target pairing. The only planning outputs are the same ordinary
  Entry→Target line nodes consumed everywhere else.
- Assisted lines reference the authoritative target segmentation/segment,
  immutable target bounds, and input-entry markup; record their analysis; stay
  unlocked; and carry `RequiresManualVerification`. Existing plans are never
  overwritten. Complete-tooth surface analysis is explicitly not canal/apex
  detection, clearance analysis, or plan approval.
- Assisted Step 4A entry placement temporarily isolates the target segment and forces
  its bounds visible. That presentation state is restored on generation,
  explicit exit, save, module exit, and scene close; display state never becomes
  the anatomy or trajectory identity contract.
- Explicit Step 4 and Step 5A view actions reuse those same guarded focus
  snapshots outside placement. Bounds-based framing changes only slice field of
  view and camera focal/position state. The optional 3D↔slice locator uses
  Slicer's singleton crosshair with accurate 3D picking and centred jumps;
  prior crosshair mode/behavior/thickness/pick settings are restored on disable,
  save, exit, and close. No picked point becomes a planning input unless the
  user is separately in a Markups placement interaction.
- Step 4A trajectory verification reuses that same line and the source CBCT
  referenced by its authoritative segmentation. A native slice view receives
  a longitudinal `SliceToRAS`: column 0 is the angle-rotated transverse axis,
  column 1 is Entry→Target, column 2 is their cross-product plane normal, and
  column 3 is the trajectory midpoint. The `-180°..+180°` control therefore
  rotates anatomy circumferentially without moving the line or creating a
  derived volume. The prior slice/composite/line-display state is restored
  when verification ends and is excluded from saved presentation state.
  Red is preferred when available. Slider/wheel events are coalesced to a
  roughly 16 ms display cadence, and optional native linear CBCT interpolation
  is restored to its prior scalar-volume display value when MPR ends.
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
  remain available and visible. The exact selected line is fully emphasized
  and centred in the slice views; same-tooth siblings are dimmed and other
  tooth groups remain visible. The Step 4A selector accepts only role-owned
  Entry→Target lines, and managed FDI/ordinal/completion labels distinguish
  complete and empty same-tooth trajectories after MRB reload.
- Once a tooth has a trajectory, its deterministic persisted RGB lineage color
  is propagated through reference-linked Step 4A bounds, Step 5A support
  anatomy, Step 5B ROI/shell/sleeve nodes, and Step 5C trim/final-shell nodes.
  This is presentation metadata; role attributes, segment IDs, and MRML
  references remain authoritative.
  Steps 5A/5B/5C render the same lineage as an FDI/color badge and selector
  swatches, with Step 5B visibility-control stripes so hidden geometry still
  has a clear parent/child cue.
- Destructive planning actions are role-gated and confirmed. Unlocking,
  interactively editing, clearing, removing a point from, or deleting a
  trajectory first traverses explicit MRML references through the active Step
  4B/4C/5 branch. One stage-level confirmation deletes the reached descendants
  before the upstream geometry changes. The logic-level trajectory deletion
  repeats this contract so controller and future callers cannot diverge.
- Target-tooth switching performs a confirmed complete backtrack of the active
  derived Step 4B/4C/5 branch. Per-trajectory backtracking preserves unrelated
  trajectories and guide selections, the authoritative segmentation, target
  segment, bounds, support-tooth choices, and non-trajectory-derived draft
  support. Full target switching also clears the active draft and branch-local
  guide selections. No node is discovered or deleted by display name.
- Owned primary nodes are removed with only their unreferenced display/storage
  auxiliaries, and parameter references are cleared before scene removal so a
  live selector cannot substitute an unrelated node. MRML save/reload must not
  restore deleted descendants or dangling references, and retained inputs must
  remain sufficient to recreate the branch.
- Step 4B full support anatomy is planning input only. Slicer's segmentation
  extraction already returns world-RAS surfaces, so the derived combined model
  has no parent transform and explicitly records `WorldRASmm`; applying the
  source transform again would be a double transform.
- A role-owned closed Markups boundary and `VisibleTemplateSupportSurface`
  preview select only erupted/accessible support. The continuous curve bridges
  interdental gaps visually, while its world-RAS control points are resampled
  and assigned first to authoritative tooth segment IDs. Extra connected mesh
  islands remain diagnostics inside that source tooth rather than becoming
  anonymous additional “teeth.” Dijkstra clipping evaluates both complementary
  candidates independently per addressed tooth. Entry→Target on the selected
  target trajectory supplies crown-to-root insertion direction; an
  area-weighted directional score retains the candidate toward the opposite
  crown/removal direction even when it is Smaller on one tooth and Larger on
  another. One persisted off-by-default polarity reversal applies to all
  target/support teeth. Boundary, trajectory, polarity, resolution, or source
  revisions mark all descendants stale.
- The current Step 5B vertical slice generates a `PatientContactShell` from
  that preview. Dynamic Modeler Margin supplies fit clearance; Dynamic Modeler
  Hollow supplies wall thickness and closes each patch boundary. Because the
  authoritative selected teeth remain separate surfaces, a lifted closed
  collar derived from the clinician's continuous boundary bridges their shell
  rims on the removal side; it does not create a new patient-contact patch in
  interdental gaps. A cropped, resolution-limited voxel Boolean unions the
  pieces and collar and removes residual material inside the directional
  blockout clearance before extracting a watertight surface. If Hollow leaves
  invalid edges, that cropped domain reconstructs the shell from an
  absolute-distance band around the validated fitting surface rather than
  accepting the invalid mesh. The shell explicitly references the full source
  model, visible patch, boundary, authoritative segmentation, fitting surface,
  Hollow candidate, boundary bridge, and both Dynamic Modeler nodes.
- Step 5B's presentation is a view over that existing dependency graph, not a
  second generation pipeline. It orders approved references, all nine exposed
  dimensions, optional intermediate diagnostics, final-result state, and the
  bottom action footer. Existing parameter-bound Qt widgets are reparented so
  MRML remains authoritative; their original generated layouts stay alive for
  Slicer's GUI-connector traversal. Build/Update calls the same complete-build
  preflight and stale-stage cache. Inspection changes display only, and Step
  5C still owns verification and atomic export.
- A locked, non-selectable two-point `TemplateInsertionDirection` line is
  derived from the selected target trajectory and stores Approach→Seat in world
  RAS; removal is its opposite. The visible-support model references both the
  source trajectory and derived line. Retentive triangles are
  classified from visible-surface normals against removal with an exposed
  angular tolerance. A cropped coordinate frame aligned to removal produces a
  watertight height-field blockout, avoiding SlicerFSP's world-axis assumption.
  The shell references that line and blockout and records fit, thickness,
  resolution, blockout safety, closing, direction geometry, and revisions with
  `UndercutState=Processed`.
- `DENTOGuideGeometry.py` owns replaceable trajectory-guide and target-frame
  docking primitives plus cropped voxel fusion. The current annular guide and
  four-dock/attachment profile remain provisional because no final robot
  mating/load contract exists. Step 4C consumes the complete set of one or two
  locked trajectories for the target tooth and persists them as repeated MRML
  references plus the current Step 4B support draft; Step 5B reuses exactly
  that trajectory set.
- Step 4C schema v4 derives a right-handed target frame in world RAS. Mean
  Entry→Target establishes crown/root polarity. The fitted target-crown-cap
  occlusal normal is `+Z`, a crown principal direction projected into that
  plane is `+X`, and `+Y` completes the frame. A locked, non-selectable Markups
  plane stores the top-face datum. Four hollow docks sit at configurable
  `+X/+Y/-X/-Y` radial offsets; each robot-facing top/opening lies on that
  plane and adjustable depth proceeds crown-to-root along `+Z`. The defaults
  interpret 15 mm as radial offset and 1 mm as bore, but every mechanical
  dimension is visible and labelled provisional.
- Selected Step 4B support segments are ordered first in Step 4C's yaw screen
  and persisted with a direct support-draft MRML reference and update revision.
  All remaining same-jaw whole teeth remain conservative secondary obstacles.
  A changed/stale support selection or draft makes Step 4C and downstream
  geometry stale.
- No Step 4C solid exists at the crown centroid and there are no radial spokes.
  Step 5B generates one closest-surface attachment per dock, retains the
  annular trajectory drill-guide sleeve/local collar as a different mechanical
  role, and clips attachment material against the complete trajectory-guide
  envelope. Any core dock/envelope collision aborts generation instead of
  trimming a load-bearing dock. Schema-v1 central-hub assemblies are stale and
  must be regenerated.
- Docking integration uses a cropped binary domain: remove outer docking
  clearance from the patient shell, union trajectory and four-dock
  reinforcement, add four recorded closest-surface overlapping branches from
  the Step 4C docks to the shell, apply the trajectory-guide exclusion, union
  all guide/dock solids, then subtract all trajectory/dock channels. The
  `FinalPrintableTemplate` explicitly references the patient shell, every
  source trajectory, Step 4C assembly, docking assembly, clearance,
  reinforcement, and channels. Occupied-voxel connectivity—not polygonal
  surface-region count—defines whether the printable material is one solid,
  because a valid hollow object may have nested boundary surfaces. Only
  isolated one-voxel occupied artifacts may be discarded; every larger second
  volume is fatal. World-RAS transformed synthetic coverage verifies fusion,
  watertight topology, MRB reload, and clean subtree deletion.
- Step 5C owns the active final verification gate. It records
  PASS/WARNING/FAIL source, snapshot, axis, topology, occupied-volume, channel,
  and sampling checks. Export reruns the checks, rejects FAIL, and uses the
  existing atomic writer for one `DENTO_Final_Printable_Template.stl`.
  Computational WARNING/PASS does not validate fit, collision clearance,
  strength, registration, sterilization, or robot/drilling safety.
- The older Step 5C separate-finalized-shell path uses Slicer's built-in Dynamic
  Modeler. Plane Cut supplies capped positive/negative regions for the simple
  horizontal trim; Curve Cut supplies inside/outside regions for the adjustable
  uneven margin, followed by capping/triangulation/normals. Its nodes remain
  readable for saved-scene compatibility, but the controller is hidden and no
  longer executed by the active workflow.
- In the retained legacy path, Step 5C isolation is a temporary one-up 3D workspace aligned to the current
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
- The retained legacy Step 5C persists source/edit/Dynamic-Modeler references, source revision,
  method, kept region, edit geometry, state, and topology metrics. A source,
  method, region, or markup change makes the finalized shell Stale. Export
  formerly accepted only a Current, source-matched, watertight Step 5C shell
  and Current Step 5B sleeve. That two-file export is no longer exposed or
  executed by the active workflow.
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
  require the ROI's source reference to match the current Step 4B draft.
  Legacy Step 4A nodes carrying stray Step 5B metadata are repaired in place;
  invalid Step 5B references are cleared without deleting the referenced
  upstream node. Parameter-to-widget synchronization is non-reentrant so the
  resulting MRML repair/name/stale events cannot recurse during scene load.
- Both workflow-owned ROI roles are visible-only geometry: their MRML nodes
  are locked and non-selectable from views, and their translation, rotation,
  and scale handles are disabled on creation, reset, scene load, and refresh.
- The scene-wide viewport panel supersedes the visible Step 5B-only control
  group. It exposes stage recommendations plus grouped anatomy/workflow
  objects at every stage, supports target/shell/final and upper/lower-jaw
  isolation with exact restoration, and intentionally keeps its presets out
  of saved MRB presentation state. Existing volume rendering is labelled as
  rendering rather than a mask and is never created by inventory refresh.
- Workflow-owned nodes carry visible `[Step 4A]`, `[Step 4B]`, `[Step 4C]`, `[Step 5A]`, `[Step 5B]`, or
  `[Step 5C]` name prefixes for selectors and Slicer's Data view. The prefixes
  are UI categorization only; role attributes, stable segment IDs, and MRML
  node references remain authoritative.
- Planning approval is explicit state, invalidated when relevant anatomy,
  trajectory, or registration changes.
- Registration, calibration, tracking, and tool poses are transform nodes in
  a documented frame tree.
- Metrics such as FRE, target error, lateral error, angular error, and depth
  error are computed in reusable logic and displayed by the workflow UI.

## Robot-description foundation

`dentobot_description` is a tracked ROS 2 `ament_cmake` package containing the
received seven-link CAD tree, seven binary STL meshes, a package-resolvable
URDF, neutral and manual joint-state publishers, and an RViz configuration. A
massless `base_link` and identity fixed joint sit above the supplied inertial
root `link-1`; this is an integration frame required because KDL does not
retain inertia on a URDF root. All six supplied movable joints remain
unchanged.

The repository root is also a generic CMake package for the Slicer extension,
so the workspace bootstrap creates
`ros2_ws/src/dentobot_description -> DentoBot/dentobot_description`. This lets
colcon discover the nested ROS package without moving it outside the tracked
repository or reclassifying the Slicer project.

The description launch always publishes the URDF, dynamic TF, and the fixed
base transform. Its `joint_state_mode` chooses exactly one neutral publisher,
the package-owned PyQt manual publisher, or an external test/simulator source.
The manual UI displays revolute/continuous joints in degrees and prismatic
joints in millimetres, but publishes standard ROS radians/metres. Neither
package-owned source has a command subscriber, controller, hardware plugin,
or actuation path.

A Jazzy runtime probe perturbed all six joints independently and verified that
upstream frames stayed fixed, each child exhibited the declared revolute or
prismatic motion, and the downstream `burr` transform responded. RViz loaded
the neutral and articulated models without mesh/resource errors under a
synthetic Xvfb graphical run. This is forward-kinematics and visualization
evidence only. The current frame chain is not the accepted planning-to-
physical registration graph; `burr` is a CAD link name, not a calibrated
bur-tip/TCP frame, and the observed mesh directions, zeros, limits, scale, and
alignment still require engineering/physical acceptance.

Manual mode also owns a deliberately coarse workspace-feedback layer. It
transforms each collision mesh's local STL bounds into `base_link`, encloses
the result in a world-axis-aligned box, skips direct parent-child pairs, and
warns below a default 5 mm box-to-box separation. The same evaluation publishes
green/red `visualization_msgs/MarkerArray` outlines on
`/dentobot/coarse_self_collision_boxes` and displays the current CAD `burr`
link origin. It never rejects a state. This is not an exact mesh collision,
swept-volume, environment, head/patient, or safety check; rotated AABBs and
visual-mesh collision reuse make both false positives and missed real-world
interference possible.

The active draft coordinate convention absorbs the developer-selected pose
`[25.38 deg, 0 mm, 62.46 deg, 0 mm, 1.08 deg, -35.28 deg]` into the URDF so
the published vector is `[0, 0, 0, 0, 0, 0]` there. Finite revolute limits are
shifted without changing span. The integration-only root applies -90 degrees
about X: link-1's local-Y-normal mounting face is parallel to the RViz XY
plane at `Z=0`, and the chain extends above it. J4 retains positive 0–75 mm
coordinates but its axis is negated, making positive travel primarily negative
base X. None of these draft choices establishes physical home, joint
calibration, head-mount registration, or a robot command convention.

### Slicer Step 6 robot-placement slice

`DENTOWorkflow` now contains **6 · Robot Placement** for manual MRML workspace
exploration. It parses the tracked URDF with a pure helper, loads the seven STL
visual models explicitly as raw RAS/CAD millimetre geometry, and assigns each
model a link-pose linear transform. Those seven transforms are children of one editable
`RobotBase` linear transform, so joint changes update only the URDF-local link
poses while base placement moves the complete assembly.

The source checkout reads the adjacent `dentobot_description` package. During
an extension build, CMake copies those same tracked files into a derived
`Resources/RobotDescription` install tree; this supports installed modules
without maintaining a second URDF or mesh source copy.

The provisional mounting surface is an unlocked `RobotMountPlane` Markups
plane. Native 3D translation/rotation handles let a researcher drag it beside a
future head model; an explicit action then orthonormalizes the plane frame and
copies its origin and orientation to the robot base. Base-transform handles,
six local translation buttons, six local rotation buttons, configurable step
sizes, and opt-in keyboard shortcuts provide fine placement. Keyboard shortcuts
exist only while Step 6 is active, the opt-in toggle is set, and no text or
numeric editor has focus.

The Step 6 nodes and joint values persist in the MRML parameter node, but the
stage is not a ROS/SlicerROS2 transform stream or `RobotAdapter`. It creates no
publisher, subscriber, controller, IK, or hardware command. The mount plane is
unregistered draft geometry, `base_link -> burr` remains a CAD chain rather
than a calibrated TCP, and head/mouth/mount/cable/environment collision is
absent.

Step 6 additionally owns a disposable, optional open-mouth scene aid. Three
aligned BodyParts3D STL nodes represent the fixed neurocranium/maxilla and the
movable mandible. They parent under a disposable workspace linear transform that
relocates native BodyParts3D coordinates to the research workspace center on first
load. A four-point Markups node stores approximate left TMJ, right TMJ, upper-
incisor, and lower-incisor inputs; placement is one landmark per button click.
Pure rigid rotation about the left-to-right TMJ axis is solved by deterministic
angular search in world RAS until the transformed lower-incisor point is
approximately 40 mm from the fixed upper point; the result is stored as a jaw
opening transform in workspace-parent local coordinates. A Markups line shows
the achieved gap. Only one phantom set and one robot placement set are permitted.
The model, landmarks, workspace transform, jaw transform, and measurement are
deletable trial nodes and carry no patient, clinical-jaw, collision, or
registration semantics.

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

ROS 2 now provides the narrow robot-description/TF simulation foundation on
Ubuntu; SlicerROS2 remains an optional integration capability and Steps 0–5
do not depend on either. The verified ROS profile is the Ubuntu
24.04/Jazzy/Linux SlicerROS2 container. Current upstream SlicerROS2 1.2 does
not list Windows as a supported build target, so native Windows Slicer remains
a planning client without SlicerROS2. Docker Desktop/WSL2 hosting of the Linux
GUI image is an unverified future profile and must not be presented as native
Windows module support. The description package does not decide whether the
future adapter uses ROS, MoveIt, a vendor SDK, or another transport. Regardless
of host or transport, low-level motion and safety never run in the Slicer
Python process.

## Packaging and deployment

- Windows planning development: native pinned Slicer, source extension path,
  WSL2 backend, and no Docker requirement.
- Ubuntu ROS development: pinned Linux SlicerROS2 container plus source
  extension path.
- AI backend: isolated Linux environment, platform-specific locked Python
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

## Step 6 ROS/MoveIt simulation architecture (2026-08-21)

This section supersedes earlier Step 6 statements that no ROS stream or MoveIt
planner exists. It does not supersede the rule that safety-critical or
low-level motion must remain outside Slicer.

```text
launch-dentoworkflow.bash
  ├─ dentobot_moveit_config/simulation.launch.py
  │    ├─ robot_state_publisher (URDF + TF)
  │    ├─ collision_guard (bounds + swept 5 mm self/world clearance)
  │    ├─ slicer_joint_state_publisher (accepted states; only /joint_states publisher)
  │    ├─ move_group (KDL + OMPL; plan only)
  │    └─ simulation_status_publisher (versioned readiness JSON)
  └─ SlicerROS2 + DENTOWorkflow
       ├─ thin DENTOROS2Bridge status subscriber
       ├─ MRML base placement / forehead plane controls
       ├─ joint candidate → collision guard → simulated /joint_states
       ├─ base_link-frame anatomy/guide collision proxies
       └─ Cartesian plan request → Step 6 preview waypoints
```

Ownership and failure rules:

- The launcher owns ROS process lifetime and shuts the stack down when Slicer
  exits. Embedded Slicer Python contains no `subprocess`, process scan, ROS CLI,
  package discovery, or background launch logic.
- Case scenes own clinical/research MRML data, not live ROS endpoints. The
  SlicerROS2 default node, DENTOBOT status/joint subscribers, joint-command
  publisher, and MoveIt collision proxies are transient (`SaveWithSceneOff`).
  Before any New Empty Case or saved-scene replacement, DENTOWorkflow stops
  preview, disconnects the Slicer-side robot, and releases adapter nodes before
  MRML deletion. After close/import it reattaches SlicerROS2's existing default
  node to the new scene and recreates only the required adapter subscribers.
  The bridge also removes stale publisher/subscriber reference IDs left by the
  pinned SlicerROS2 1.2 removal implementation.
- Developer reload is local to the Slicer Python/UI layer. The fixed-header
  action disconnects the SlicerROS2 robot, removes adapter-owned ROS MRML nodes,
  evicts cached `DENTO*.py` helpers, and invokes Slicer's scripted-module reload.
  It intentionally does not restart or assume ownership of the container or
  external ROS graph, and it preserves the MRML scene.
- Readiness requires the description nodes, collision guard, `/move_group`,
  `/check_state_validity`, `/compute_ik`, `/compute_cartesian_path`, and exactly
  one `/joint_states` publisher. The JSON schema and `simulation_only` mode
  must match; stale or malformed status fails closed.
- `base_link` is parented under the Step 6 base transform for visualization.
  Entry/Target Markups remain world RAS millimetres; SlicerROS2 converts
  base-relative pose matrices to ROS coordinates/metres.
- `dentobot_drill_tip_provisional` is a provisional CAD-derived fixed frame
  7 mm distal to the former burr-origin frame. Its +Z axis follows the spindle
  axis. A Cartesian pose basis is built by setting
  +Z to normalized Entry→Target, projecting a stable reference axis into the
  normal plane, and completing a right-handed orthonormal basis with cross
  products.
- MoveIt builds the `dentobot_arm` serial chain from URDF joint origins, axes,
  types, and limits plus the SRDF `base_link → dentobot_drill_tip_provisional`
  group. The
  configured KDL plugin solves numerical Jacobian-based IK at runtime; there is
  no handwritten DH table or robot-specific IK equation. OMPL RRTConnect is
  available for general planning; the current Entry-to-Target operation uses
  collision-aware Cartesian interpolation.
- Slicer publishes a candidate vector on `/dentobot/slicer_joint_positions`.
  The external guard samples the transition at no more than 1 degree per
  revolute step or 0.5 mm per prismatic step, checks bounds, exact mesh contact,
  FCL/PlanningScene self distance, and robot-world distance at every sample,
  and requires at least 5 mm. Only an accepted vector is republished on
  `/dentobot/validated_joint_positions`; rejection retains the previous
  accepted state and returns the body pair/reason to the UI. The SRDF Allowed
  Collision Matrix excludes adjacent mechanical pairs only.
- Environment meshes are transformed from world RAS into `base_link` RAS and
  published as hidden collision-object proxies. Locking the placed base
  refreshes them; disconnect removes them. The original AABB checker is only a
  coarse MRML fallback and is not part of the ROS-active acceptance gate.
- Planning returns named joint vectors and timing. Step 6 preview streams those
  vectors through the single simulation publisher; any failed publish stops the
  preview and reports an error. No trajectory execution call is exposed.

### Case/runtime persistence boundary

- Case loads replace the MRML scene; they are never merged into existing case
  or robot state.
- The SlicerROS2 default node is hidden, non-serialized, and retained as a
  process singleton across case-level `Clear(0)`. Robot, TF, parameter,
  publisher/subscriber, goal, and MoveIt proxy nodes are runtime-only.
- Motion Control timers/observers and the final upstream subscriber-reference
  slot are synchronously cleared before robot deletion. DENTOBOT uses immediate
  obstacle publish/remove operations so no Qt callback holds a native ROS
  wrapper across reload or New Case.
- The persistent Step 6 base and optional seven-link MRML fallback robot are
  distinct from the live ROS graph. A restored base never implies an active
  ROS connection.
- Step 6 revalidates upstream lineage on import, restore, and motion planning;
  stale Step 4C docking or unverified Step 5C template state is fail-closed.

### DENTOBOT case bundle V1 (2026-08-24)

New routine saves use a `.dentocase` ZIP64 archive around, not instead of, a
Slicer MRB. `scene/case.mrb` remains the sole authority for CBCT,
segmentations, Markups, models, persistent transforms, and parameter-node
references. The outer archive adds `manifest.json`, a SHA-256 inventory,
`workflow/lineage.json`, a portable URDF/SRDF/mesh/MoveIt fingerprint, and a
save report. It records Slicer world RAS and millimetres without duplicating
geometry into a second restore source.

Save first asks Slicer to produce a transient MRB under the existing
StartSave/EndSave sanitization contract, audits the MRML text for serialized
SlicerROS2 nodes/default singleton/active flag, builds the outer archive in a
sibling temporary file, validates every member, then atomically replaces the
destination. The temporary save restores the live scene URL, root directory,
and modified-since-read state.

Open validates archive paths, member count/size, schema, coordinate contract,
file inventory, and all hashes before scene mutation. It then creates a
sanitized recovery MRB, extracts the embedded scene, loads it with clear
semantics, and cross-checks manifest node roles, classes, names, selected
DENTOBOT attributes, world-RAS Markups points, transform matrices, model
bounds/counts, volume IJK-to-RAS geometry, and segmentation count to `1e-6`.
Any post-load mismatch replaces the partial scene with the recovery MRB.
After success, Slicer's scene URL is cleared and its root is set to the package
directory so the deleted extraction path cannot become a later save target and
Ctrl+S cannot overwrite the outer package as an MRML file. Rollback restores
the prior scene location as well as its content.

An installed robot-resource fingerprint mismatch does not corrupt or hide the
case; it visibly blocks Step 6 import until reconciled. A valid package also
does not override Current/Stale state: Step 4C and Step 5C freshness checks run
after import and the ROS connection remains off until an explicit Step 6
action. Legacy MRML/MRB loading remains available as a clearly labelled
compatibility path.

### Motion Control adapter and draft workspace explorer (2026-08-22)

`DENTOROS2Bridge` exposes repository-owned native logic/MRML calls and an
optional adapter around the pinned generic Motion Control widget; the sibling
SlicerROS2 checkout is not modified. After robot setup it parents both the first live `lookup` root and first
`goal_transform` root to the Step 6 base. It derives operator-visible
readiness from the versioned external-stack contract, fixes the planning group
to `dentobot_arm`, injects the configured chain tip
`dentobot_drill_tip_provisional` when no
SRDF `<end_effector>` entry exists, wraps MoveIt IK and trajectory loading to
show outcomes, and forces every trajectory load to `enableExecute=False`.
Adapter callbacks and the added status widget are disconnected/deleted before
module reload, scene clear, or robot teardown.

The two visual robots represent state, not workspace: current follows
`/joint_states`; goal contains one accepted IK/selected joint target. A
workspace is computed independently:

```text
task min/max for J1..J6
  → 6-D Halton low-discrepancy samples (current vector first)
  → display units to radians/metres
  → URDF FK to provisional TCP origin
  → non-adjacent-link AABB separation ≥ 5 mm
  → provisional TCP / subsampled environment point clearance
  → base-frame MRML point cloud parented to Step 6 robot base
```

The cloud is transient (`SaveWithSceneOff`) and marked stale when the base is
moved; task-limit edits remove it. The known `link-3`/`link-5` and
`link-3`/`pneumatic_spindle-Copy` AABB overlaps are narrowly excluded because
their long world-axis boxes overlap throughout the sampled space while the
real MoveIt/FCL smoke pose is valid. Other pairs retain the 5 mm draft rule.
This exception does not enter the SRDF Allowed Collision Matrix and does not
authorize hardware motion.

## Parallel Step 6 and application-shell architecture — 2026-08-24

The active GUI migration is a presentation refactor around the existing
extension, not a standalone application or algorithm rewrite:

```text
Legacy eleven-stage UI ─┐
                        ├─ DENTOWorkflow controller ─ existing MRML logic
Six-workspace shell ────┘             │
                                      └─ DENTORobotWorkflowFacade
                                           ├─ DENTOROS2Bridge
                                           ├─ MoveIt/KDL IK and planning
                                           ├─ PlanningScene/FCL collision guard
                                           ├─ DENTORobotPlacement
                                           └─ simulated plan preview
```

`DENTOApplicationShell.py` owns the two Slicer docks, six-workspace navigation,
task header, substep selector, theme, and Focus/Expert chrome restoration.
`DENTORobotSimulationPanel.py` owns presentation-only cards for runtime,
Goal/IK, and scene/collision actions. It contains no ROS import, URDF parsing,
kinematics, or collision mathematics. `DENTORobotWorkflowFacade.py` is the
UI-independent Step 6 orchestration boundary. Legacy handlers and the new
Robot Simulation page both call this same object.

The shell reparents the authoritative existing module widget into its task
dock. Therefore the Case workspace and not-yet-visually-migrated workspaces
retain their exact MRML bindings and callbacks while the new navigation maps
six workspaces onto stable internal stage indices 0–10. Robot Simulation adds
six operator substeps—Scene and Runtime, Base Placement, Manual Joints, Goal
and IK, Scene and Collision, and Plan and Preview—while reusing the existing
base, joint, workspace, and trajectory widgets where they already satisfy the
contract.

Presentation mode, light/dark theme, Expert mode, and dock geometry are local
`QSettings`. MRML nodes and the parameter node remain authoritative case state;
no second database exists. Switching navigation or theme cannot alter geometry
or workflow lineage. Legacy stays the default until the Case and Robot operator
acceptance cycle is complete. The complete action classification is maintained
in `GUI_ACTION_PARITY.md`.

Lifecycle ownership is symmetrical. Deactivation or module cleanup reparents
the module widget, restores exact captured Slicer chrome, deletes both docks,
disconnects signals, and clears façade preview state. The established ROS
adapter teardown still owns transient SlicerROS2 nodes. A developer reload
therefore preserves case MRML and the external stack but constructs exactly one
new interface instance and requires an explicit robot reconnect.
