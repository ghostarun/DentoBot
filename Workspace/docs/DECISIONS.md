# Dentobot Technical Decisions

## 2026-08-10 — Visible-support ROI and Dynamic Modeler patient-contact shell

Status: Priorities 1–4 implemented as a demonstrable vertical slice and
Slicer-native synthetically verified; final verification/export and
representative-anatomy clinician acceptance pending

Supersede whole-tooth geometry as the direct fitting surface. The reviewed
`vtkMRMLSegmentationNode` remains authoritative and Step 5A may still derive a
full target/support model for planning, but a role-owned closed Markups curve
must explicitly select the erupted/accessible support patch before any fitting
shell is generated. Persist the curve, preview model, source model,
authoritative segmentation, world-RAS control-point geometry, selection side,
sampling resolution, revisions, and metrics through explicit MRML references.

Adapt SlicerFSP `SurgicalGuide.CurveAndClip()` without its name-based node
contracts. DENTOBOT's input differs because each segmented tooth is a separate
closed surface, so keep a continuous linear clinician boundary across
interdental gaps, resample its world-RAS control points, assign samples to the
nearest connected tooth, and apply `vtkSelectPolyData` Dijkstra clipping per
tooth. Reject a boundary that does not adequately address every selected
surface. Preserve one selected patch per tooth and explicitly orient its
normals away from the source closed anatomy.

Generate the patient-contact shell by running Dynamic Modeler
Margin for fit clearance and Dynamic Modeler Hollow for thickness/side walls.
Then adapt SlicerFSP's labelmap-Boolean principle in a tight bounding box: voxel
union overlapping shell pieces, remove residual geometry within the requested
anatomy clearance, and extract a watertight manifold surface at the exposed
processing resolution. Keep fitting surface, Hollow candidate, and both
Dynamic Modeler nodes as hidden role-owned auxiliaries referenced by the shell.
Use an explicit two-point world-RAS `TemplateInsertionDirection` line whose
semantics are Approach→Seat and whose opposite is the removal direction.
Classify retentive visible-surface triangles by surface normal against that
removal vector; never assume insertion from world X/Y/Z. Create a cropped
insertion-frame height-field blockout, apply configurable blockout safety and
voxel closing, re-enforce clearance after closing, and persist the line,
blockout, tolerances, input revisions, and direction geometry through MRML.
The visible shell remains `ResearchOnly` but records
`UndercutState=Processed`.

No finalized robot docking-rail specification exists in the repository.
Therefore retain DENTOBOT's annular sleeve as explicitly provisional,
parameterized development geometry behind a replaceable helper boundary.
Support any number of selected, complete, locked, anatomy-associated
trajectories and persist each as a repeated MRML node reference. Adapt the
SlicerFSP integration sequence—not its ring contract—by subtracting docking
clearance, adding a load-spreading reinforcement collar, unioning docking
solids, and restoring trajectory channels in one tight cropped voxel domain.
The resulting `FinalPrintableTemplate` is one connected watertight model in
the synthetic regression, but remains `NotVerified` and non-exportable until
the dedicated PASS/WARNING/FAIL gate is implemented.

`GetSegmentClosedSurfaceRepresentation()` already returns world-RAS geometry.
Derived Step 5A support models therefore have no parent transform and carry
`CoordinateConvention=WorldRASmm`; retaining the segmentation transform would
apply it twice. Legacy derived models with the obsolete contract must be
explicitly updated before entering the new shell path.

Reason: full CBCT crowns and roots are valid planning anatomy but are not the
clinically accessible seating surface. A single connected-scan curve algorithm
also silently selects only one component when used on separate tooth segments.
The adapted per-surface selection plus native Margin/Hollow and a cropped voxel
clearance Boolean gives traceable margins, controlled fit, clean topology, and
a replaceable vertical slice for later undercut and docking integration.

## 2026-08-10 — Step 5C zoom and ROI-Z-only plane control

Status: implemented with static verification; live Slicer interaction pending

Keep the initial one-up 3D camera aligned and fitted to the automatic Step 5B
ROI, but do not continuously constrain parallel scale. The normal isolation
lock fixes translation, pitch, and roll while permitting both yaw and zoom;
the yaw lock fixes orientation while zoom remains available. Re-entering the
explicit isolate action resets yaw and the initial ROI fit. Subsequent plane
or curve actions must preserve the user's zoom.

Represent the simple cut as one Point-Normal Markups plane origin constrained
to the Step 5B ROI Z axis. The normal is always ROI `+Z`, so the plane remains
parallel to the locked ROI top/bottom faces. Project each placed or moved
origin onto that axis, preserve only its signed Z height, require exactly one
control point, and hide translation/rotation/scale handles. Reapply this
constraint after scene load and immediately before finalization; validation
rejects a missing ROI reference, tilted normal, or lateral origin.

Reason: locking camera scale made relevant anatomy leave the practical editing
window with no recovery. A free zoom does not change the ROI coordinate frame.
Likewise, X/Y plane translation has no effect on an infinite plane but exposes
confusing controls, while rotation violates the intended simple horizontal
cut. One ROI-Z height is the complete minimal input.

## 2026-08-10 — Native trajectory-aligned longitudinal oblique MPR

Status: implemented with static verification; live Slicer interaction and
performance acceptance pending

Extend Step 4A with a trajectory verification view that reuses the selected
role-owned `vtkMRMLMarkupsLineNode`, its world-RAS Entry/Target points, the
trajectory's referenced authoritative segmentation, and that segmentation's
source-CBCT reference. Do not create a second trajectory or resampled CBCT.

Construct a stable right-handed frame around Entry→Target, using world `+Z`
as the preferred reference and world `+Y` near the parallel singularity.
Write native `SliceToRAS` columns as rotated transverse X, trajectory Z, and
their cross-product normal, with the trajectory midpoint as origin. Thus the
trajectory lies vertically in the plane; it is deliberately not the slice
normal. A `-180°..+180°` slider changes only this matrix through Slicer's
existing reslice pipeline.

Use the first available standard slice view rather than a hard-coded MRML node
name. Capture and restore its matrix, field of view, composite layers/link
state, and the selected trajectory's display/projection state. Restore before
scene save, module exit, scene close, cleanup, or Step 5C isolation, then
resume after save. Event-loop-coalesce point/slider updates and write only
changed MRML properties.

Point correction must preserve the clinician-selected view. Freeze the slice
matrix while a Markups control point is actively dragged. At interaction end,
project the prior slice normal onto the plane perpendicular to the corrected
Entry→Target axis and reconstruct the closest valid longitudinal frame; an
in-plane edit therefore retains the exact circumferential plane. Apply later
slider changes as angle deltas from that transported frame. Use the prior
horizontal axis as the finite fallback only when the corrected trajectory is
parallel to the old normal. **Reset Orientation** deliberately discards this
interaction history and reconstructs deterministic world-reference 0°.

Reason: longitudinal circumferential CBCT inspection is standard oblique MPR
and belongs at the existing trajectory/view boundary. Native slice reslicing
is more responsive and traceable than generating angle-specific volumes, and
reference-based reuse prevents divergent planning state. This is verification
assistance, not perforation detection, trajectory approval, or drilling
authorization.

## 2026-08-10 — ROI-frame yaw workspace and immutable workflow bounds

Status: implemented with static verification; live Slicer interaction and
performance acceptance pending

Supersede Step 5C's fixed anterior world-RAS camera with a temporary
ROI-aligned one-up 3D workspace. The current Step 5B automatic bounds ROI is
the view-frame authority: at zero yaw the camera looks along ROI `+Y`, ROI
`+X` is viewport right, and ROI `+Z` is viewport up. Parallel scale equals
half the ROI Z size so its top and bottom align with the viewport boundaries.
Yaw orbits around ROI `+Z` through 360 degrees.

Use two explicit camera locks. **Lock X/Y/Z translation, pitch, and roll** is
on by default and leaves yaw and zoom available. **Lock yaw too** freezes the
remaining orientation angle, keeps zoom available, and implies the first lock.
Unchecking the first lock also clears yaw lock and permits a free camera. The
horizontal trim plane stays normal to ROI `+Z` independently of camera locks;
its one origin point supplies only the constrained ROI-Z height.

Isolation stores and replaces presentation state only: layout, camera,
crosshair, and node visibility are restored on explicit exit, module exit,
scene close, or cleanup. The isolate action does not create a markup or enter
placement mode; plane and curve placement remain separate deliberate actions.
This separates 3D editing from later 2D verification and reduces concurrent
rendering and interaction work.

Treat both `TargetToothAABB` and the compatibility-named
`TemplateShellTrimROI` as immutable workflow-owned bounds. They remain
optionally visible but are locked, non-selectable from views, and have all
translation/rotation/scale handles disabled. Step 5B recomputes its ROI from
the Step 5A anatomy before shell generation; user-adjustable Step 5B ROI
semantics are superseded. Preserve the existing role string and node reference
contract for MRB compatibility.

Reason: simultaneous 2D/3D interaction, continuously rewritten camera state,
and editable bounds created a laggy and error-prone margin workflow. A
turntable-style ROI frame supports controlled 360-degree plane/curve work,
while immutable generated bounds prevent accidental upstream geometry changes.

## 2026-08-07 — Non-destructive Step 5C finalization gates STL export

Status: implemented and Slicer-native synthetically verified; representative
anatomy and dentist interaction acceptance pending

Keep the generated Step 5B shell as a traceable raw source. Step 5C creates a
separate finalized model through Slicer's built-in Dynamic Modeler and is the
only workflow step allowed to export the shell. Export requires a Current,
source-matched, watertight finalized shell and a Current Step 5B sleeve; it
must reject the raw shell, stale output, missing provenance, or open topology.

Provide two edits over the same provenance contract. The simple path places a
Markups plane at a surgeon-selected height and uses capped Plane Cut with an
explicit positive/negative kept side. The uneven-margin path uses an
adjustable surface-snapped closed Markups curve, Curve Cut inside/outside, and
a DENTOBOT capping/cleanup/topology pass. Persist method, kept region, markup
geometry, source revision, references, and metrics so MRB reload and stale
detection are deterministic. Expert Dynamic Modeler remains available for
inspection and advanced work, but arbitrary expert output is not silently
adopted as the exportable DENTOBOT result.

Use an anterior world-RAS parallel view for the initial interaction, with R/L
horizontal and S/I vertical. The optional lock constrains camera orientation
and plane normal but permits zoom and plane translation. Do not encode the
suggested 70–80 percent tooth coverage or label this an occlusal/dental frame;
both require representative anatomy and dentist-approved definitions.

Delete Step 5C as a narrow owned subtree while retaining its Step 5B source.
When Step 5B is confirmed for deletion, cascade through Step 5C first to avoid
dangling child provenance. This implements the parent/child backtracking rule
for these steps without mutating the raw source during margin exploration.

Reason: a planar cut is fast for ordinary cases, while an adjustable closed
margin accommodates uneven gingival anatomy. Separating raw and finalized
models makes retries reversible, preserves traceability, and prevents an
unreviewed intermediate shell from being mistaken for an export-ready part.

## 2026-08-07 — Target-tooth visual lineage and non-retargeting selection

Status: implemented and Slicer-native verified

Derive one deterministic, vivid RGB color from each trajectory's authoritative
target segment/FDI record after that tooth has at least one trajectory. Persist
the color and target metadata on the trajectory and propagate it through MRML
references to the matching Step 4A target-bounds ROI, Step 5A support model,
and Step 5B trim ROI, shell, and sleeve. The color is a visual lineage cue
only; role attributes, stable segment IDs, and MRML references remain the
identity and dependency contract.

Expose that lineage explicitly in every affected workflow step, not only on
MRML display nodes. Step 5A and Step 5B show a colored FDI/hex lineage badge;
their owned-node selectors show matching swatches; and Step 5B visibility
controls show the same stripe even when an object is hidden in the views.

Keep every DENTOBOT trajectory in the shared selector. Selecting a target
tooth emphasizes that tooth's trajectory group without hiding other groups or
overriding explicit visibility choices. If the current trajectory belongs to
a different tooth, clear the current selection instead of silently retargeting
the line. Maintain one reusable target-bounds ROI per exact segmentation and
target segment so switching teeth never mutates another tooth's bounds.

Require every DENTOBOT trajectory to be a Markups line whose class invariant
allows only Entry and Target. Reject imported or programmatic lines that do
not satisfy that two-point contract. Before deleting any selected Step 4A,
5A, or 5B node, clear its workflow parameter reference so a live MRML selector
cannot auto-select an unrelated scene node during removal.

Reason: multiple trajectories and descendants were difficult to correlate,
and changing the tooth selector could otherwise overwrite a valid persisted
association. A deterministic lineage cue makes the closed workflow legible,
while preserving reference-based identity prevents color/name edits from
changing provenance. Pre-clearing parameter references closes a selector race
found by the active-widget deletion regression.

## 2026-08-07 — Isolate Step 4A bounds from the Step 5B trim ROI

Status: implemented and Slicer-native verified, including the reported legacy
MRB

Treat `DENTOBOT.BoundsRole=TargetToothAABB` and
`DENTOBOT.MarkupsRole=TemplateShellTrimROI` as mutually exclusive ownership
contracts. Filter the Step 5B selector to the Step 5B role, disallow arbitrary
ROI creation from that selector, and require its source-model reference to be
the current Step 5A model before reset or generation. Never adopt, delete, or
generate from a Step 4A target-bounds ROI in Step 5B.

When a legacy Step 4A bounds node contains stray Step 5B attributes, repair
that same node in place by clearing the Step 5B role/schema/source reference
and restoring locked target bounds. Clear an invalid Step 5B parameter
reference without deleting the referenced scene node. Guard the complete
parameter-to-widget refresh against re-entry because role/name migration and
stale-state repair legitimately emit nested MRML Modified events while an MRB
is opening.

Reason: Step 5B previously listed every Markups ROI and treated an unowned
Step 4A bounds node as reusable. One node could therefore acquire both roles,
be resized/unlocked as a trim ROI, feed meaningless shell geometry, and cause
nested refreshes, duplicate nodes, or a recursion crash. UI filtering alone
would not protect loaded or programmatically corrupted scene state, so the
logic and migration layers enforce the same boundary.

## 2026-08-07 — Workflow-owned visibility controls and step-tagged scene names

Status: implemented and Slicer-native verified

Expose non-destructive visibility checkboxes in Step 5B for the selected Step
4A target-bounds ROI and trajectory, Step 5A support anatomy, and Step 5B trim
ROI, shell, and sleeve. The checkboxes manipulate MRML display-node visibility
only; they do not delete, invalidate, or regenerate geometry. Preserve an
existing node's visibility during bounds refresh, support-model update, ROI
reset, and shell/sleeve regeneration, and rely on MRML to persist the display
state in saved scenes.

Prefix DENTOBOT-owned planning and template node names with `[Step 4A]`,
`[Step 5A]`, `[Step 5B]`, or `[Step 5C]`. Apply the prefix to legacy owned
nodes by role so the same objects are identifiable in DENTO Workflow selectors
and Slicer's Data/Subject Hierarchy view. Names remain presentation only;
ownership, identity, and dependencies continue to use role attributes and node
references.

Reason: the planning and trim bounding boxes are useful while editing but can
obscure the template result. Direct workflow controls are faster and clearer
than requiring routine Data-module navigation, while step tags make advanced
scene inspection understandable without creating a second data model.

## 2026-08-06 — Persisted trajectory identity and explicit Step 5B ROI reset

Status: implemented and Slicer-native verified

When a saved or manually selected Step 4A trajectory has a complete persisted
target association, restore its authoritative segmentation, segment ID, target
bounds ROI, tooth selector, highlight, and trajectory details as one guarded
parameter-node update. Reject partial or mismatched saved associations instead
of overwriting them or guessing from an editable name.

Managed and legacy default trajectory names are presentation labels only. Show
the FDI tooth, per-tooth sequence, and current Empty/Entry only/Complete/Invalid
state so multiple trajectories can be distinguished before deletion; retain
MRML references and segment IDs as identity. Permit deletion of the Step 5B
shell trim ROI only when it has the DENTOBOT ROI role. Preserve Step 5A,
trajectory, dimensions, shell, and sleeve, but mark retained Step 5B outputs
Stale because their ROI reference was removed.

Reason: scene reload previously restored the trajectory selector without
restoring its target tooth, and duplicate default names made empty and complete
trajectories indistinguishable. The ROI also lacked a clean reset-to-new
lifecycle. These behaviors now have explicit ownership and persistence tests.

## 2026-08-06 — Model-independent Step 5B research template geometry

Status: implemented with synthetic Slicer-native verification; anatomical and
fabrication acceptance pending

Do not copy or claim execution of the incomplete public EndoPlanner preview.
Use it only as an interaction and literature reference. Implement Step 5B in
DENTOBOT with Slicer/VTK geometry that has no trained-model dependency: a
world-RAS exterior distance-band shell trimmed by a user-controlled ROI, a
trajectory-aligned drill channel, and a separate closed annular sleeve.

Keep clearance, thickness, sampling, channel diameter, sleeve inner/outer
diameters, and sleeve height as explicit persisted research parameters. Store
shell and sleeve as separate role-gated MRML models with source-model,
trajectory, and ROI references, parameter/geometry metadata, stale-state
invalidation, and confirmed deletion. The original direct Step 5B STL-export
choice is superseded by the 2026-08-07 Step 5C finalization/export decision.
Require a current Step 5A model and a complete locked Step 4A trajectory. Treat
multi-region shells and sleeve/anatomy overlap as visible warnings, not hidden
success.

Reason: the preview's guide method calls omitted helpers and uses fixed-index
arch segments, fixed dimensions, voxel-grid assumptions, and incomplete
intersection logic. Reimplementing the narrow geometry contract gives us
testable ownership, coordinate, persistence, and export behavior without
pretending that preview code, default dimensions, printability, or clinical
safety has been validated.

## 2026-08-06 — Inspect EndoPlanner without modifying embedded Slicer Python

Status: accepted for local source inspection

Patch only the untracked local preview checkout so optional third-party imports
do not prevent UI instantiation, and add a Slicer 5.10 Markups ROI import
fallback. Do not install its broad unpinned dependency command into Slicer's
embedded Python merely to reveal subsequent failures. Let the launcher include
the preview path only when the checkout exists, and persist Slicer settings at
the build's actual `/root/.config/slicer.org` location.

Reason: `nibabel` was only the first missing import. The preview also expects
legacy package APIs, omits model weights, and references many undefined
implementation symbols. Installing packages would mutate the wrong runtime
without producing an operational planner.

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

Status: accepted and Slicer-native verified

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
test now passes.

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
