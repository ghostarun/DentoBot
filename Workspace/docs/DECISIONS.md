# Dentobot Technical Decisions

## 2026-08-06 — Git-tracked workspace layer and launcher-owned runtime configuration

Status: accepted; publication pending GitHub re-authentication

Keep the established Git repository at `ros2_ws/src/DentoBot` and preserve
its history and remote. Track the formerly loose Ubuntu workspace controls
under its new `Workspace/` directory: launcher and helper scripts, Compose,
the top-level agent entrypoint, and active Ubuntu documentation. Preserve the
existing `/home/light-tarun/dentobot/{scripts,docs,compose.yaml,AGENTS.md}`
paths as relative compatibility symlinks. Do not create a second Git
superproject or rewrite the repository into a ROS-workspace monorepo merely
to capture these files.

Store workstation-specific values in one local `.dentobot.env`, created from
the tracked example and excluded from Git. The launcher is the configuration
authority: it derives the workspace and Conda environment roots, validates
the interpreter and render node, passes explicit host mounts to Compose, and
exports the backend Python and run-record root to Slicer. DENTO Workflow uses
that contract automatically and does not persist launcher paths into MRB
scenes. Its manual fields remain an explicit advanced override.

Reason: this removes duplicated machine paths, keeps scenes portable, retains
the proven ROS checkout and remote, makes the operational workspace and notes
reviewable in the same Git history, and avoids committing local environments,
medical/run data, model caches, Slicer state, or credentials. Pytest 8.4.2 is
installed only in the external Conda backend as the already pinned test
dependency; Slicer's embedded Python remains unchanged.

## 2026-08-04 — Confirmed deletion of DENTOBOT-owned draft outputs

Status: accepted; Slicer-native persistence test pending

Steps 4A and 5A expose separate confirmed delete actions for the selected
DENTOBOT trajectory and draft support-anatomy model. Deletion is permitted
only when the selected node has the expected DENTOBOT role. It removes the
primary MRML node, clears the corresponding workflow reference and transient
widget state, and removes that node's display or storage auxiliaries only when
they are no longer referenced elsewhere in the scene.

Target-tooth selection, reviewed segmentation, target bounds, manual support
selection, and unrelated or shared nodes are preserved. Editable names are
never used as ownership evidence. This gives users a clean destructive action
without turning ordinary selection changes into implicit deletion or allowing
the workflow to remove arbitrary user-created nodes.

Reason: Clear Both Points deliberately retains a trajectory node, while a
discarded trajectory or draft anatomy model needs an explicit lifecycle end.
MRML reference cleanup and save/reload behavior are part of the deletion
contract. Static checks pass and a Slicer-native delete/save/reload/recreate
test has been added; its execution remains a separate authorized runtime gate.

## 2026-08-04 — Batch documentation and external synchronization

Status: accepted

Maintain local controlled notes for material project checkpoints, but do not
rewrite them or synchronize Google Drive and Git after every conversational
prompt. Batch notes and external synchronization periodically, tell the
developer when a checkpoint is due, and obtain approval before Drive or Git
writes. The developer explicitly approved the current documentation, Drive,
and Git batch on 2026-08-04.

## 2026-08-04 — Hardware rendering and normal Slicer process priority

Status: accepted; technical runtime verification complete

The daily SlicerROS2 Compose service passes the host Intel graphics render node
`/dev/dri/renderD128` into the container and sets
`SLICER_BACKGROUND_THREAD_PRIORITY=0`. Only the render node is exposed; the
container is not given DRM modesetting ownership. The daily launcher treats a
missing host/container render node or a missing priority override as an
actionable startup failure instead of silently accepting software rendering.

Reason: the laggy live Slicer process had no `/dev/dri` device and ran at nice
level 19. Slicer's bundled Linux implementation and documentation confirm that
the default background-thread setting can lower the entire process through
`setpriority`. The image contains Mesa's Intel `iris` driver path, so exposing
the render node plus the supported priority override is the smallest change
that addresses both evidenced bottlenecks. After the developer authorized
recreation, the replacement service reported direct rendering through
`Mesa Intel(R) Graphics (ARL)`, OpenGL 4.6, opened the `i915` render node from
Slicer, and kept `SlicerApp-real` at nice level 0. Comparative FPS and
user-perceived responsiveness on the original workload remain the usability
acceptance gate.

## 2026-08-03 — Manual arbitrary-count support anatomy for Step 5A

Status: accepted

Step 5A uses the authoritative Step 4A target tooth plus a completely manual
selection of one or more distinct whole-tooth support segments from the same
Reviewed segmentation. The workflow must not infer adjacency, arch, side, or
a maximum count: a user selection of two, ten, or another positive number is
valid when the segment identities satisfy those invariants.

The output is one traceable `vtkMRMLModelNode` made by appending unmodified
closed-surface copies of the target and selected supports. It preserves the
source segmentation's parent transform and records source references,
segment/FDI/name lists, review timestamp, geometry counts, schema, and update
time. Input changes keep the prior model but mark it Stale; regeneration is
explicit.

Reason: Step 5A must support user-directed research configurations without
embedding unapproved dental adjacency assumptions. Its model is anatomical
source material only, not a guide shell, contact design, printable template,
clinical validation, or drilling authorization.

## 2026-08-03 — Explicit Qt ownership for Slicer 5.10 backend processes

Status: accepted

The Slicer 5.10 compatibility adapter owns its fallback `QProcess` as a child
of the DENTO Workflow widget. After final output is drained, the adapter must
disconnect its PythonQt callbacks, close the process object, and schedule Qt
deletion before terminal completion handling continues. Headless harnesses
must also release the workflow widget before requesting application shutdown.

Validate this lifecycle with health-only probes before another segmentation
run. Use the preserved full-backend checkpoint image in disposable,
network-disabled containers with repository source mounted read-only; the
ordinary Compose container deliberately contains only the minimal Bridge B
Conda runtime. Headless display orchestration must own and reap its exact Xvfb
PID instead of relying on an opaque wrapper.

Reason: the backend child had already completed, but retained Qt/Python
callback ownership and test-wrapper behavior made Slicer shutdown
non-deterministic. Two consecutive Slicer 5.10 Bridge A probes now exit cleanly
without model execution, patient data, or robot/hardware activity.

## 2026-07-31 — Persistent minimal Bridge B runtime and one-command launcher

Status: accepted

Use `scripts/launch-dentoworkflow.bash` as the daily Ubuntu entry point for
the current Slicer medical-imaging work. It starts the existing Compose
service, loads DENTO Workflow from repository source, and keeps the external
Bridge B interpreter in the existing host Conda environment at
`/home/light-tarun/miniconda3/envs/dentobot/bin/python`. Compose bind-mounts
that environment read-only at the same absolute path so the Slicer process can
launch it directly. The launcher temporarily grants X11 access to the
container's local root user and revokes it when Slicer exits.

Keep this runtime deliberately minimal and isolated: Python 3.12.13,
DENTOBOT inference 0.2.0,
NumPy 2.2.6, NiBabel 5.4.2, packaging 26.2, and typing-extensions 4.16.0. It is
the verified MRML/NIfTI Bridge B execution environment, not the future full
segmentation environment. PyTorch, TotalSegmentator, CUDA model dependencies,
and model weights remain a separate migration and validation task.

Do not create or maintain a second backend venv or Docker named volume for
this workflow. Conda owns dependency installation; the daily launcher only
validates the prepared environment.

Launch Slicer through the lower-level `slicer_ros2_module` launch file because
the package's `ros2 run ... slicer` wrapper rejects forwarded Slicer CLI
options in this image. The module is selected with Slicer's startup Python
option after its repository path is added.

## 2026-07-31 — Treat ROS image bridging as pixel transport, not CBCT geometry

Status: accepted

Use the standard SlicerROS2 `sensor_msgs/msg/Image` to
`vtkMRMLScalarVolumeNode` bridge for bounded, synthetic interoperability tests
between host Lyrical and container Jazzy. Keep the bidirectional probe
software-only and verify dimensions, encoding, and exact pixel bytes before
claiming transport success.

Do not treat this bridge as the accepted bulk CBCT or segmentation exchange
contract. `sensor_msgs/Image` does not by itself preserve the full
patient-space affine, DICOM context, RAS/LPS semantics, provenance, or
segmentation metadata required by the medical-imaging workflow. A real
geometry-preserving DENTOBOT data contract remains a separate design and
validation task.

## 2026-07-31 — ROS interoperability is imaging-workflow plumbing only

Status: accepted

Use ROS domain 73 and subnet discovery as the DENTOBOT development defaults
for bounded communication between the host Lyrical environment and the
host-network Jazzy SlicerROS2 container. Store these defaults in the host
source helper and Compose service, while allowing an explicit domain override.

Successful standard string and simulated transform tests establish only basic
DDS discovery, transport, and tested standard-message compatibility. They do
not adopt ROS as the future robot-control architecture and do not validate
custom SlicerROS2 interfaces, medical-image exchange, registration,
coordinate semantics, tracking, motion, or safety.

There is no robot hardware. DENTOBOT is in conceptual design, and current
implementation priority is the 3D Slicer medical-imaging workflow. Robotics
architecture and hardware integration remain at their existing future gates.

## 2026-07-31 — Supported host Lyrical with isolated container Jazzy

Status: accepted

Install ROS 2 Lyrical Desktop and ROS development tools on the Ubuntu 26.04
host. Lyrical is the stable binary distribution matching Ubuntu Resolute.
Keep the verified SlicerROS2 container on its image-provided ROS 2 Jazzy
environment until a compatible Lyrical SlicerROS2 image or a deliberate
rebuild is evaluated.

The host Lyrical environment is sourced explicitly through
`scripts/source-host-ros2.bash`, not globally from `.bashrc`. The existing
`ros2_ws/build`, `install`, and `log` trees were produced in the Jazzy
container and must not be reused as host Lyrical build outputs. Cross-
distribution DDS communication is a test target, not an assumed guarantee;
message definitions, QoS, RMW behavior, and SlicerROS2 interfaces must be
verified before integration claims.

Reason: this gives the workstation a vendor-supported ROS 2 development
environment without mixing Ubuntu releases or silently combining two ROS
distributions. It preserves the already verified SlicerROS2 container while
making the compatibility boundary explicit.

## 2026-07-29 — Separate active Ubuntu development from Windows history

Status: accepted

The Ubuntu workstation documentation under this repository's `docs/` directory
is the current source of truth for active development.

The existing Google Drive `IITM Dentobot/docs` directory contains Windows-era
development material. It is preserved as reference-only and will not be merged
into the active record automatically.

Google Drive will contain a sibling folder named `active-development-ubuntu`.
Files synced there mirror the active local documentation. Any Windows-era
procedure must be deliberately reviewed, adapted, executed, and verified before
being added to the Ubuntu documentation.

Reason: silently mixing two operating systems and partially transferred
workflows would make setup instructions and task state unreliable.

## 2026-07-29 — Container-first SlicerROS2 baseline

Status: provisional

The current checked-in `compose.yaml` is the active integration baseline. It
uses the Jazzy/Slicer 5.10 SlicerROS2 container image. ROS 2 is not currently
available in the host shell.

This decision remains provisional until the container, Slicer GUI, and ROS 2
environment have been launched and verified on the Ubuntu workstation.

Update: the container, ROS 2 Jazzy environment, SlicerROS2 install prefix, and
Slicer process were verified on 2026-07-29. The container-first baseline is now
accepted. A clean rebuild and functional module tests remain separate tasks.

## 2026-07-29 — Continuous documentation with platform-qualified history

Status: accepted

The product context, architecture, development plan, reproducibility procedure,
and changelog imported from Windows remain the continuous project history and
design baseline. Platform-specific Windows/WSL execution instructions are not
Ubuntu instructions until migrated and verified.

The Windows logbook is retained as
`docs/logbook/logbook-windows-history.md`. New Ubuntu activity uses dated
logbooks. This preserves chronology without blending platform-specific claims.

## 2026-07-29 — Git migration deferred

Status: accepted

Git initialization and remote reconciliation are postponed until the
documentation system and Ubuntu workflow migration are complete. This
supersedes the earlier placement of Git recovery among immediate active tasks.
