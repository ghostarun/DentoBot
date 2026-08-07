# DENTOBOT Architecture

## Architectural overview

```text
3D Slicer / later DENTOBOT custom Slicer application
|
+-- DENTOWorkflow scripted module (focused user workflow)
+-- Slicer DICOM, MRML, slice/3D views, segmentations, markups
+-- Platform process adapter
|   +-- Windows: direct WSL2 process
|   `-- Ubuntu container: direct local Linux process
|       +-- NIfTI payloads
|       +-- structured stdout + exit status
|       `-- JSON result metadata
|
+-- Isolated inference Python environment
|   +-- DENTOBOT inference Python package and tests
|   +-- Windows/WSL: PyTorch/CUDA
|   +-- Ubuntu: PyTorch CPU plus OpenVINO device discovery
|   +-- TotalSegmentator `teeth` / ToothFairy3
|   `-- Future image-processing or planning backends
|
+-- External robot-control environment (later)
    |
    +-- Robot adapter and simulator
    +-- Motion planning and hardware API
    +-- Safety interlocks and real-time control
```

The boundaries are deliberate. Slicer owns interactive medical-image state;
an isolated external interpreter owns dependency-heavy compute; the robot
runtime owns hardware safety and real-time behavior.

### Ubuntu launcher-supplied runtime configuration

The active Ubuntu checkout adds a tracked `Workspace/` layer without moving
the ROS package or rewriting Git history. Its launcher, Compose definition,
active Ubuntu notes, and helper scripts are exposed at the surrounding
workspace's established paths through relative symlinks. A single untracked
`.dentobot.env` supplies the host backend interpreter and render device.

The launcher derives the workspace and Conda environment directories and
exports an explicit `DENTOBOT_*` runtime contract. Compose uses it for
absolute bind sources and container environment values. On Ubuntu,
DENTOWorkflow consumes the launcher-provided backend Python and run-record
root automatically without persisting those machine paths in the MRB scene;
manual values remain an advanced override. This changes configuration
ownership, not the process boundary: Slicer still launches a separate Python
interpreter and exchanges NIfTI plus JSON rather than importing Conda modules.

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
python -m dentobot_inference health --json --require-device <cpu|cuda:0>
python -m dentobot_inference roundtrip --input <input.nii> --output <roundtrip.nii> --result-json <result.json> --run-id <uuid>
python -m dentobot_inference segment-teeth --input <input.nii> --output <teeth-segmentation.nii> --result-json <result.json> --run-id <uuid> --device <cpu|cuda:0>
```

### Bridge A, Bridge B, and Bridge C

The integration slices establish one boundary in independently testable stages:

- **Bridge A — environment health:** `DENTOWorkflow` launches the exact Python
  interpreter configured by the user through the selected platform adapter. The
  backend reports interpreter identity, package versions, PyTorch import
  health, requested compute device, CUDA state, and OpenVINO-visible devices as
  JSON. Device failure is explicit; there is no silent fallback.
- **Bridge B — image round trip:** Slicer exports the selected scalar volume to
  an isolated run directory as NIfTI. The WSL backend loads, rewrites, reloads,
  and checks its affine, shape, voxel type, and voxel checksum. Slicer then
  validates the returned MRML volume's dimensions, scalar type, and IJK-to-RAS
  matrix before retaining it in the scene.
- **Bridge C — explicit-device teeth segmentation:** the same selected-volume
  and process boundary runs TotalSegmentator `teeth` on either CUDA device 0
  or CPU, validates a
  multilabel NIfTI plus schema-versioned metrics, then creates a named and
  colorized `vtkMRMLSegmentationNode`. Binary-labelmap and closed-surface
  representations provide interactive 2D and 3D display.

All commands use the same asynchronous adapter, bounded live output, process
exit status, schema-versioned JSON, and argument-list construction. Neither
Slicer nor the backend command installs packages, edits Slicer, or treats the
artifact directory as a queue. Bridge C replaces TotalSegmentator's implicit
weight downloader with a cache-only guard and rejects an unavailable requested
device rather than silently changing devices.

The native Ubuntu adapter was validated on 2026-07-31 in the SlicerROS2
Slicer 5.10 container. It invokes `/opt/dentobot-venv/bin/python` directly,
uses `/workspace/data/dentobot-runs`, and requests `cpu`. A public Slicer
CBCT fixture completed standalone inference and the Slicer import/review-scene
path. This is platform compatibility evidence, not anatomical or clinical
validation.

### Runtime boundary

The Slicer module runs in Slicer's embedded Python interpreter. The inference
package runs in a separate Linux Python environment: inside WSL2 on Windows or
as a direct child process in the Ubuntu SlicerROS2 container. PyTorch,
TotalSegmentator, nnU-Net, and OpenVINO are not imported into Slicer, and MRML
node objects are never passed into the inference process.

The boundary is therefore an explicitly controlled external process, not a
Python import and not a folder-based job service.

### Direct process execution

For each inference request, the Slicer adapter:

1. Validates the selected source volume and backend configuration.
2. Creates a unique run ID and short staging directory.
3. Exports the source volume to NIfTI with its affine intact.
4. Starts the platform adapter asynchronously with an argument list containing
   the absolute Linux Python interpreter, module name, input, output, result
   metadata path, run ID, and explicit device. Windows prepends `wsl.exe` plus
   the distribution; Ubuntu launches the interpreter directly.
5. Streams structured stdout and ordinary diagnostic output into the Slicer
   UI without blocking the Qt event loop.
6. Supports cancellation and records the terminal process exit code.
7. On success, validates the output and imports it into MRML.

On Slicer 5.10, the compatibility adapter owns its fallback `QProcess` as a
child of the module widget. After draining the final output, it disconnects
the PythonQt signal callbacks, closes the process object, and schedules it for
Qt deletion before completion handling continues. Headless harnesses also
clean up the workflow widget before requesting Slicer shutdown. This prevents
a completed backend child or a signal/closure reference cycle from retaining
the Slicer process.

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

On Ubuntu the equivalent command begins directly with
`/opt/dentobot-venv/bin/python`; paths remain native container paths and
`--device cpu` is explicit.

### Run artifacts

Use a short, configurable staging root such as `C:\DENTOBOTRuns` on Windows
or `/workspace/data/dentobot-runs` on Ubuntu. Each run has an isolated UUID
directory visible to both Slicer and the backend:

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
to update the changelog or logbook places those files and any other changed
design documents in the next approved synchronization batch; it does not
require a Drive/Git write after every prompt. The mirror contains
documentation only; patient data, run artifacts, models, and secrets are
excluded.

## Planning and registration architecture

- Dental annotations and AI outputs live in segmentation/markup nodes.
- A trajectory is an explicit two-point line with documented entry/target
  semantics and world-RAS length.
- Destructive planning actions require confirmation and the expected
  DENTOBOT role. They delete the selected primary node and only its
  unreferenced display/storage auxiliaries, then clear the corresponding
  workflow parameter reference. Shared auxiliaries and unrelated nodes are
  preserved.
- Trajectory deletion retains segmentation, target tooth, and bounds. Draft-
  model deletion retains segmentation, target, and ordered manual supports.
  Save/reload must not restore deleted nodes or dangling references, and the
  retained source state must remain sufficient to recreate each output.
- Planning approval is explicit state, invalidated when relevant anatomy,
  trajectory, or registration changes.
- Registration, calibration, tracking, and tool poses are transform nodes in
  a documented frame tree.
- Metrics such as FRE, target error, lateral error, angular error, and depth
  error are computed in reusable logic and displayed by the workflow UI.

The Step 4A source increment keeps planning inputs inside
`DENTOWorkflow`. The authoritative teeth segmentation remains the source of
target anatomy. Only records classified as whole teeth are eligible for the
draft target selector; pulp, canal, jaw, implant, and other segments remain
available for review but are not silently promoted to target teeth.

The selected target segment ID and `vtkMRMLMarkupsLineNode` are persisted by
the workflow parameter node. The trajectory stores a proper node reference to
the target segmentation plus namespaced attributes for the target segment ID,
source name, FDI number, `EntryToTarget` role, `SlicerRASmm` coordinate
convention, and `Draft` status. Control point 0 is Entry and control point 1 is
Target. Their positions and Euclidean length are read in world RAS
millimetres.

The active target also owns a persistent `vtkMRMLMarkupsROINode` representing
the whole-tooth closed surface's axis-aligned world-RAS bounding box. The ROI
is visible and locked. Initial placement and later drag edits are constrained
at the workflow layer: a newly placed out-of-bounds point is removed, while an
existing point dragged out of bounds is restored to its last valid position.
This AABB is a coarse PoC workflow constraint, not proof that a point lies
inside tooth material and not an anatomical safety margin.

Clearing and deleting are distinct. **Clear Both Points** retains the selected
trajectory node. **Delete Selected Trajectory** accepts only a line carrying
the DENTOBOT `EntryToTarget` role, removes the line and any now-unreferenced
display/storage auxiliaries, and clears the workflow trajectory reference.
The target segmentation, target segment, and bounds are deliberately retained.

Step 4A target selection has display priority over the independent Step 3
review selection. The target is emphasized in both 2D and 3D while other
segments remain contextual. The Markups interaction mode is explicitly
rebound to the selected line after Slicer enters place mode because Slicer
5.12.2 otherwise resets the active placement class to Fiducial.

This increment does not define a dental procedure, interpret entry/target
anatomy, approve a plan, calculate clearance, generate a template, or
authorize drilling. Those remain later planning and validation increments.

### Step 5A draft support-anatomy model

Step 5A adds a geometry-preserving `vtkMRMLModelNode` boundary between the
reviewed tooth segmentation and later template-design research. The selected
Step 4A target remains authoritative. The user manually checks one or more
other distinct whole-tooth segments from that same Reviewed segmentation;
there is no inferred adjacency, arch, side, ordering, or maximum count.

The model contains the appended, unmodified local closed surfaces for the
target and every checked support. It observes the same parent transform as the
segmentation rather than hardening or silently changing coordinates. A node
reference and namespaced attributes persist the source segmentation, target
ID/FDI, ordered support IDs/FDIs, source names, review timestamp, source
point/cell counts, schema version, status, and update time.

Selection or segmentation-content changes do not delete or silently regenerate
the output. They mark the model Stale, retain it visibly in orange for review,
and require an explicit Update; current output is teal. The parameter node
persists the ordered support selection and model reference across scene save
and reopen.

**Delete Draft Support Model** accepts only the DENTOBOT
`TemplateSupportDraft` role, removes the model and any now-unreferenced
display/storage auxiliaries, and clears the model reference. It retains the
segmentation, Step 4A target, and ordered support selection for deliberate
recreation.

This boundary is anatomical source material only. It performs no smoothing,
remeshing, Boolean union, offset/contact inference, guide-shell or sleeve
generation, drill-channel creation, export, printability assessment, clinical
validation, or drilling authorization.

### Step 4A–5C lineage and template derivation

Each trajectory is associated with an authoritative segmentation and target
segment through MRML references and attributes, never its editable name.
Multiple trajectories may belong to one tooth; each carries a deterministic
persisted tooth-lineage color. That presentation color propagates through the
matching Step 4A bounds, Step 5A support model, Step 5B ROI/shell/sleeve, and
Step 5C edit/final-shell nodes. Roles, segment IDs, and references—not colors
or `[Step 4A]` through `[Step 5C]` name prefixes—remain authoritative.

Step 5B converts the Step 5A model to world-RAS VTK geometry and samples an
ROI-trimmed exterior distance band. It subtracts a channel aligned to the
locked Entry-to-Target line and creates a separate analytic annular sleeve
extending outward from Entry. Both outputs store source, trajectory, ROI,
parameter, revision, and topology metadata. A source, trajectory, ROI, or
parameter change makes them Stale. The raw Step 5B shell is not exportable.

The Step 5B trim ROI and Step 4A target-bounds ROI are mutually exclusive
roles. The selector and logic accept only a Step 5B ROI referencing the
current Step 5A model. Legacy cross-role contamination is repaired in place;
invalid parameter references are cleared without deleting unrelated nodes.
Visibility controls affect MRML display state only and cover the active Step
4A bounds/trajectory, Step 5A model, and Step 5B ROI/shell/sleeve.

Step 5C keeps the raw shell unchanged and creates a separate finalized shell
using Slicer's built-in Dynamic Modeler. Plane Cut supplies capped
positive/negative regions for the simple horizontal trim. Curve Cut supplies
inside/outside regions for an adjustable surface-snapped closed margin;
DENTOBOT then caps, triangulates, cleans, orients, and rejects empty or
non-watertight retained geometry.

The Step 5C front view is a world-RAS anterior parallel camera with R/L
horizontal and S/I vertical. Its optional lock constrains camera orientation
and the plane normal while retaining zoom and plane translation. It is not a
dental/occlusal frame and does not encode an automatic 70–80 percent coverage
rule. The method, kept region, markup geometry, source/edit/Dynamic-Modeler
references, source revision, state, and topology metrics persist in MRML.

Export accepts only a Current, source-matched, watertight Step 5C shell and a
Current Step 5B sleeve. Step 5C deletion removes only its role-owned plane,
curve, finalized shell, Dynamic Modeler node, and cut auxiliaries while
retaining Step 5B. Confirmed Step 5B deletion first cascades through these
children. STL creation remains a research export action, not printability,
manufacturing, clinical, or drilling authorization.

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
