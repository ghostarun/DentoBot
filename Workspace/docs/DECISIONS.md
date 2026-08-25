# Dentobot Technical Decisions

## 2026-08-25 — Validate schema-v1 lineage as saved requirements, not exact future dictionaries

Status: software implemented and host verified; operator Slicer reopen pending

Treat schema-v1 `.dentocase` lineage dictionaries as append-only contracts.
Every key and value present in the saved package must reconstruct, with the
existing `1e-6` numerical tolerance and exact list lengths, but a newer
application may reconstruct additional dictionary keys. MRML node IDs remain
traceability metadata and are excluded from semantic equivalence. When a saved
value is missing or changed, report its first nested field path.

Reason: newly added target/jaw lineage attributes are legitimate stronger
metadata, not geometry drift. Requiring identical dictionary key sets made an
otherwise internally consistent Step 6 package fail at
`targetToothBoundsRoi`. Allowing only actual-side extensions preserves
fail-closed validation of all evidence the package did record without forcing
a schema bump for every append-only metadata field.

Parameter-node-to-GUI binding is read-only synchronization. Step 4C docking
input and yaw callbacks must not invalidate geometry or orientation while
`setParameterNode` connects/restores widgets. A delayed yaw signal is also a
no-op only when its value agrees with both the restored parameter and the
docking assembly's persisted `ParametersJson`; a genuine operator change still
sets orientation to Draft and cascades staleness normally. Package validation
therefore observes persistent MRML meaning rather than a widget-binding side
effect.

## 2026-08-25 — Compose views from anatomy/dimension/CBCT/overlays and enforce stage-owned interaction

Status: implementation and synthetic Slicer verification complete;
representative-case operator acceptance remains active

Replace the 3×3 tooth-button grid and flat reparented Advanced list with one
shared `ViewComposition` contract and compact selectors for Anatomy, 2D/3D,
CBCT, and overlay groups. Resolve metadata into upper/lower/full anatomy
without geometry inference. Present individual nodes and segments in a fresh,
hierarchical Advanced tree so its lifecycle does not depend on a moved
Designer list. Recommended compositions remain explicit for all eleven
internal stages and never create a CBCT renderer.

An explicit CBCT 3D choice may lazily ask Slicer's Volume Rendering logic for a
default intensity renderer. DENTOBOT tracks and deletes only nodes it created
for that view session; it restores slice-composite assignments and existing
renderer state exactly. This preserves the distinction between intensity
rendering and a segmentation/model.

Treat markup editability as stage ownership. Outside its owning stage, a
DENTOBOT markup is locked and non-selectable, then restored exactly on return.
In Step 6, case versus draft phantom and MRML versus ROS robot sources are XOR;
mouth-opening landmarks and the robot mount plane are editable only while
their explicit preparation substep permits it. Advanced visibility cannot
bypass these source rules. The robot workspace context card reports scene,
robot, jaw-opening, and base-lock state before the operator changes the view.

Reason: the viewer must maximize 3D-viewport usefulness without allowing a
presentation action or accidental handle drag to mutate upstream geometry and
stale a later shell/template branch. This remains simulation/research UI; it
does not authorize hardware motion or make clinical claims.

## 2026-08-25 — Require non-destructive case mouth opening before Step 6.1

Status: implemented and synthetic/automated verified; representative operator
acceptance remains open

Imported Step 6 case packages must complete **6.0A — Open Case Mouth about the
TMJ** before load-robot, base lock, ROS connect, planning-scene sync, or other
6.1+ actions. Reuse the draft-phantom four-landmark TMJ hinge solver
(`solve_hinge_rotation_for_gap`) without resampling or parenting the source
CBCT or segmentation under the hinge. Persist landmarks, target gap, hinge
transform, gap line, and derived opened lower-jaw / mandibular display proxies;
gate on freshness (geometry, landmarks, fingerprint, matrix, gap). Phantom
scenes remain an alternate XOR path and do not require 6.0A.

Reason: collision-aware motion planning needs intra-oral clearance, but a CBCT
volume cannot partially rotate only the mandible without destructive
resampling. A derived planning surface plus mandibular trajectory proxies keep
source anatomy intact while making opened-mouth obstacles and targets available
to MoveIt. The requirement is research planning preparation, not clinical jaw
kinematics or physical registration evidence.

## 2026-08-25 — Bound occupied-voxel artifact cleanup by physical volume

Status: accepted and representative-scene verified for research geometry

During final shell/guide/dock voxel fusion, retain the hard requirement for one
connected printable occupied region. Permit cleanup only when exactly one
region exceeds the artifact threshold and every other region is no larger than
0.1 mm³ in sampled volume, with a one-voxel compatibility floor at coarse
sampling. Persist raw region sizes, the resolution-derived sample threshold,
and every removed-region count/volume alongside the final one-region metrics.

Reason: `test1_5b2.mrb` generated four valid independent shell-contact branches
but VTK sampling produced occupied regions `[85852, 3, 1, 1]`. The former
single-voxel-only rule rejected a three-voxel island of approximately
0.080 mm³ as though it were a detached dock. A fixed voxel-count threshold
would vary physically with processing resolution. The bounded-volume rule
removes numerical islands while preserving failure for a detached guide, dock,
shell section, or any other larger second component. It is topology cleanup,
not manufacturing-feature deletion or mechanical/clinical acceptance.

## 2026-08-25 — Allocate a Docker TTY only for interactive GUI launches

Status: implemented and live-launch verified

Keep the Ubuntu launcher attached to Slicer in both interactive and
non-interactive callers. Pass `-it` to the final `docker exec` only when both
standard input and standard output are terminals; otherwise use an attached
non-TTY exec. Start the simulation stack in its own process group and clean
that complete owned group with bounded INT, TERM, then KILL escalation when
Slicer exits. X11 forwarding, scoped `xhost` access, and the
no-hardware-execution boundary are unchanged.

Reason: an unconditional `-it` aborts before Slicer starts when Cursor or
automation has no terminal-backed stdin, even though `DISPLAY` and X11 are
valid. Also, signalling only the top-level `ros2 launch` PID can orphan its
ROS/MoveIt children after Slicer's known nonzero VTK-leak shutdown. Conditional
TTY allocation and bounded process-group ownership address both lifecycle
failures.

## 2026-08-24 — Keep Step 6 native, gated, persistent-by-contract, and preview-only

Status: implemented and automated simulation verified; representative operator
and hardware/calibration acceptance remain blocked

Routine Step 6 stays inside `DENTOWorkflow` and uses one shared Legacy/New-GUI
façade. Its ordered gates are: validate case/task; for imported cases complete
required 6.0A non-destructive TMJ mouth opening; load the local MRML robot and
place/provisionally lock its base; record a case/base/profile-specific six-joint
Task Home; generate an FK workspace and explicitly review its assisted-limit
proposal; connect ROS/MoveIt, apply home, synchronize obstacles, and confirm one
immutable task snapshot; preview a strict approach plus terminal Entry contact;
then preview Entry-to-Target drilling. `ROS2MotionControl` is an explicit expert
diagnostic only, with application-level Views retained and a one-click return.

Persistent MRML/`.dentocase` state includes the base status/source/revision,
optional curved forehead proxy and dimensions, versioned Task Home, reviewed
assisted limits, immutable task snapshot, display opacities, and placement
context. ROS robot/TF wrappers, goal robot, Motion Control nodes, plans,
publishers/subscribers, phase-guard sessions, and active flags are transient and
are reconstructed only after Connect. Old locked scenes normalize to legacy
provisional/unreviewed state and cannot plan until reviewed. Changes to target,
trajectory, base, proxy, home, limits, tool profile, or robot resources
invalidate confirmation and both phases; camera and opacity changes do not.

The explicit **Enable CBCT 3D Context** action creates or reuses exactly one
volume-render display, copies the current scalar display mapping initially, and
never resamples voxels or changes IJK-to-RAS. CT-Bone and uCT-Skull are intensity
appearance presets, not anatomy segmentations. The optional curved forehead
contact envelope is labelled Unregistered/Provisional/Visualization-only and is
excluded from registration and collision evidence. Only `ProvisionalLocked` is
reachable until a measured registration workflow exists.

The CAD burr-link origin is superseded as a planning label by
`dentobot_drill_tip_provisional`, a CAD-derived fixed frame that remains
uncalibrated. The collision guard keeps ordinary/manual/home commands strict and
adds a versioned simulation-only phase channel. Goal 1 is strict to a default
5 mm pre-entry point; only its terminal segment may accept the selected
burr-to-target contact at Entry. Goal 2 may ask the Cartesian solver to ignore
intentional target contact, but an independent guard still rejects wrong-task,
off-corridor, overshoot/backtracking, non-target, other-link, self-collision,
and joint-bound violations. Execute remains hidden and disabled.

Reason: serializing external ROS state caused duplicate subscribers, null URDF
roots, ambiguous fallback robots, and unsafe stale behavior. A deterministic
persistent intent layer plus transient runtime reconstruction preserves one
world-RAS/mm geometry authority while keeping intentional target contact
narrow, phase-specific, and simulation-only.

## 2026-08-24 — Present Step 5B as one ordered unified-template build

Status: implemented and focused Slicer-native verified; representative
normal-window acceptance remains active

Keep the dependency-aware Step 5B backend and its cached geometry contracts,
but present them as one operator sequence: approved inputs and lineage, all
generation dimensions, optional advanced fit/intermediate processing, unified
result, then the complete action footer. The routine build action validates
the Step 4A trajectory, Step 4B support package, Step 4C docking assembly, and
Step 5A visible support surface before voxel work; it regenerates only missing
or stale blockout, shell, or fusion stages and reuses Current intermediates.

Do not make a Current result's build button behave like an inspection button.
When Current, disable and label that action as status; keep fit, shell/guide,
and unified-result inspection as separate display-only actions. Keep deletion
visually subordinate and last. The older staged generation controls remain
available only in the collapsed Advanced section or as hidden compatibility
adapters for saved parameter-node bindings.

The panel reuses and reparents the existing Designer widgets instead of
creating duplicate controls. The original Designer layouts must remain alive,
even when empty, because Slicer's parameter-node GUI connector still traverses
the generated UI wrapper and queries their properties.

Reason: showing result/actions before dimensions implied that geometry had
already been finalized and made Step 5B look like an extension of Step 4B or
Step 5C. One visible dependency order matches the actual algorithm while
preserving MRML roles, world-RAS/mm geometry, invalidation, caching, and Step
5C verification/export contracts.

## 2026-08-24 — Group Views by operator intent; never create renderers during inventory

Status: implemented and focused Slicer-native verified; representative
normal-window acceptance remains active

Replace the flat every-segment Elements list with one shared Views palette for
Legacy and the six-workspace shell. The routine surface contains the explicit
recommendation for each internal stage and one-click upper/lower/all
permanent-tooth masks in 2D, 3D, or both. FDI quadrants 1/2 map to upper and
3/4 to lower; only review records categorized as `Teeth` with a valid
two-digit permanent FDI number enter those jaw groups. Routine jaw and stage
recommendations are scoped to the parameter node's authoritative teeth
segmentation and input CBCT; unrelated scene segmentations/volumes stay in a
collapsed Advanced inventory with the role-owned workflow objects.

Supersede the 2026-08-22 decision to create a separate default 3D renderer for
every scalar volume during Elements refresh. That code queried Slicer's first
volume-rendering display node and, when absent, called
`CreateDefaultVolumeRenderingNodes`. Therefore DENTOBOT triggered a new
display node while Slicer rendered the intensity data of whichever CBCT or
sample scalar volume was already in the scene. It did not generate a skin
segmentation or new voxel dataset, but the resulting transfer function could
look like a skin/outer scan envelope and the `[3D Volume]` label obscured that
distinction.

Inventory is now read-only: it only queries an existing renderer, labels it
**Volume rendering — not a mask**, excludes it from every recommended preset,
and hides it during other isolation presets. Creating a renderer is an
explicit Slicer/operator action outside inventory refresh. Existing MRB
renderers remain compatible and restorable. The mask and workflow selection
snapshot/restore contract is unchanged.

Reason: opening a chooser must not mutate the MRML scene, and routine dental
views should be expressed in anatomical/task language rather than a flat list
of implementation objects. Central pure classification keeps the same
recommendations and FDI grouping available to both presentations without
duplicating mask, geometry, or rendering logic.

## 2026-08-24 — Step 4B exclusively owns locked support-tooth membership

Status: implemented and Slicer-native verified; representative normal-window
acceptance remains active

Step 4B is the only editor for target/support-tooth membership. Creating or
updating `TemplateSupportDraft` sets the persisted
`DENTOBOT.SupportSelectionLocked=true` contract. A current locked package
disables the visual arch buttons. Revising membership is an explicit Step 4B
action that sets the lock false and immediately marks the support draft, Step
4C docks, and every reference-linked Step 5 descendant stale; updating the
draft rebuilds and locks the package again. Legacy role-owned drafts without
the attribute are treated as locked and acquire the explicit attribute during
UI reconciliation.

Step 5A is a read-only consumer of that parent package. It displays the target,
support list, draft identity, Current/Stale state, and lock state, plus one
button to return to Step 4B. It never displays or mutates the support arch or
the raw Step 4B draft selector. If a saved parameter node loses only its
support-ID JSON, a Current locked draft whose segmentation and target
references still match may restore those IDs from its redundant model
provenance. Unlocked, stale, malformed, or mismatched packages are never
promoted.

Reason: stage-local widgets are transient presentation state and must not be
allowed to become a second authority. One persisted parent lock makes
backtracking deliberate and prevents Step 5A from silently diverging from the
support anatomy used by Step 4C collision screening. Geometry remains
transform-free world-RAS/mm; this decision changes ownership and invalidation,
not measurements or coordinates.

## 2026-08-24 — One backend, two switchable presentations during GUI migration

Status: application-shell foundation and Case/Robot Simulation vertical slice
implemented; remaining workspace presentation migration is active

Develop the Step 6 robotics track and the custom-GUI track on one authoritative
integration branch and one mounted source tree. Do not copy the 34,000-line
`DENTOWorkflow` module into versioned folders or create a second ROS workspace.
The eleven-stage Legacy presentation and six-workspace application shell share
the same MRML scene, parameter node, workflow logic, ROS adapter, and robot
workflow façade.

Store only presentation preferences—`legacy`/`shell`, light/dark theme, Expert
mode, and dock geometry—in workstation-local `QSettings`. They are not case
state and must not enter MRML or `.dentocase`. Legacy remains the fail-closed
default while migration is incomplete. Either presentation can switch at
runtime without restarting Slicer, the container, or ROS.

Step 6 widget handlers now call `DENTORobotWorkflowFacade`. The façade accepts
operator degrees/millimetres and Slicer world-RAS/millimetre poses, delegates
SI conversion to the ROS adapter, uses existing workflow logic for placement
and workspace generation, and returns structured success/code/message/details
results. It owns no hardware-execution operation. MoveIt/KDL remains the IK
authority, MoveIt PlanningScene/FCL remains the ROS-active collision authority,
and the Halton/FK/AABB cloud remains explicitly approximate.

Reason: a shared service seam permits continued robotics fixes while UI pages
are migrated incrementally. Duplicated module trees or late backend merges
would create divergent scene state, coordinate logic, and safety behavior.

## 2026-08-24 — Wrap authoritative MRB scenes in a validated case bundle

Status: implemented and Slicer-native verified as case-bundle schema V1

Routine workflow saves use a versioned `.dentocase` ZIP64 package. Its
embedded `scene/case.mrb` remains the only restore authority for image,
segmentation, model, Markups, persistent transform, and workflow parameter
state. The wrapper adds a canonical manifest, SHA-256 member inventory,
workflow-lineage snapshot, portable robot-resource fingerprint, and save
report. JSON metadata validates the MRB after load; it does not recreate or
transform geometry.

ROS publishers, subscribers, TF/robot wrappers, MoveIt proxies, the
SlicerROS2 default node, active-connection flags, and machine-specific
absolute paths are runtime state and must never be case content. The persistent
Step 6 base and optional local MRML robot remain distinct from a live ROS
connection. Reconnection is always an explicit Step 6 action. Installed URDF,
SRDF, YAML, xacro, and mesh inputs are fingerprinted by portable component
names and content hashes; a mismatch is visible and blocks Step 6 import until
it is reconciled.

2026-08-25 amendment: a programmatic case-package MRB snapshot explicitly
suspends active-connection attributes and marks SlicerROS2 nodes transient
around the save, then restores the active flag only in the running scene.
General StartSave/EndSave observers remain defense in depth for ordinary MRB
saves but are not the sole package-boundary mechanism. The archive audit still
rejects any runtime token or active flag that reaches the snapshot.

Open is transactional at the application level: preflight validates schema,
safe paths, inventory, sizes, and every checksum before changing the scene; a
sanitized recovery MRB is then created; the embedded MRB is loaded with clear
semantics and compared with its manifest to `1e-6`; and a failed post-load
check restores the recovery scene. Package integrity is deliberately separate
from workflow freshness. A valid package with stale Step 4C/5C lineage remains
stale and is blocked rather than silently promoted.

Reason: MRB alone cannot express the boundary to external ROS runtime state,
resource compatibility, or a preflight/rollback protocol. A second geometry
serialization would risk coordinate divergence, so it is explicitly avoided.
Legacy MRML/MRB remains a labelled compatibility path pending an offline
migrator for historically contaminated scenes.

## 2026-08-19 — Description launch from Slicer must not use Slicer Python on PATH

Status: implemented; host and container pytest recorded; leftover incomplete
launch stopped and a healthy slicer-mode stack started for retry

**Start Stack & Connect Motion Control** started `description.launch.py` but
timed out after 8 s. Live nodes were `/dentobot_robot_state_publisher` and
`/slicer` only. The launch child used ``/usr/bin/env python3``; Slicer’s PATH
puts SuperBuild ``python-install/bin`` first, so the Python joint publisher
imported Slicer Python, failed ``import yaml``, and exited. C++
``robot_state_publisher`` stayed up, so Connect waited on a half-stack.

ROS children now export a Jazzy-plus-system PATH before sourcing overlays,
in addition to unsetting ``PYTHONHOME``/``PYTHONPATH``. A slicer-mode launch
that has RSP without ``dentobot_slicer_joint_state_publisher`` is stopped
before retry. Launch stdout is kept in a tempfile. Connect also forces a
fresh ``ros2 node list`` so a 1.5 s cache from the failed half-stack cannot
report “RSP without slicer publisher” after both nodes are up. This does not
command hardware.

## 2026-08-19 — Step 6.2 merged min / value / max joint rows

Status: implemented; host and container pytest recorded; interactive Slicer
verification pending after extension reload

6.2 had two UIs for the same six joints: task min/max envelopes and a nested
Manual Joint Motion group of value spinboxes. Operators had to look in two
places and Apply was the only way to copy limits onto the pose controls.

Each joint is now one grid row: min, current pose, max. Widget names are
unchanged (`robotJointNTaskMinSpinBox`, `robotJointNSpinBox`,
`robotJointNTaskMaxSpinBox`). Changing min or max updates the value range
immediately; Apply still clamps to URDF mechanical limits. The nested group
is removed. This is display/control layout only: it does not change IK,
collision, or hardware policy.

## 2026-08-19 — Step 6.0 import frames the case package, not the phantom origin

Status: implemented; host and container pytest recorded; Slicer widget test
added; interactive graphical run pending after extension reload

Import Planning Package previously validated IDs and set a flag, then framed
the research workspace (phantom/robot origin). The case CBCT never became the
slice background, so 6.0 looked empty.

Import now sets `inputVolume` on the slice viewers, unions RAS bounds of the
case package (volume, segmentation, trajectory, docks, template, optional
tooth ROI), and frames that box. Phantom/robot framing stays on the fallback
**Frame Scene + Robot** path. Elements recommended view includes `case_volume`
and `bounds`. Degenerate zero-extent boxes are ignored so an empty node cannot
pull the camera to the origin.

## 2026-08-19 — Keep /slicer healthy on later Step 6 actions

Status: implemented; host and container pytest recorded; live SlicerApp-real
listed `/slicer`

Connect is not the only Step 6 action that talks to ROS. Plan and Preview now
call `ensure_slicer_ros2_runtime(require_stack=True)` when the ROS robot is
active, using a forced `ros2 node list` so a 1.5 s cache cannot hide a dead
`/slicer`. Preview joint waypoints also push into ROS2 Motion Control /
`/joint_states`. ROS-only scenes do not require MRML STL meshes. All ros2 CLI
from Slicer still unsets `PYTHONHOME`. No hardware command.

## 2026-08-19 — Run ros2 CLI from Slicer without PYTHONHOME

Status: implemented; host and container pytest recorded

Slicer sets ``PYTHONHOME`` to its SuperBuild interpreter. ``ros2`` uses
``#!/usr/bin/python3``, so a child process inherits that prefix, loads Slicer
stdlib, and fails importing ``rclpy`` (``librcl_action.so``). Connect then
reported “ros2 CLI is not available in this Slicer process” even though
``/opt/ros/jazzy/bin`` was on PATH.

All DENTOBOT ros2 CLI calls now ``unset PYTHONHOME PYTHONPATH
PYTHONEXECUTABLE``, source Jazzy plus the workspace overlay, and pass a child
environment with those Slicer Python variables removed. Description-stack
launch uses the same sanitized ``bash -c``. This does not command hardware.

## 2026-08-19 — Load SlicerROS2 with DENTO Workflow; import slicer in the bridge

Status: implemented; host pytest recorded; interactive Connect verification pending

**Start Stack & Connect Motion Control** reported “The ROS2 Slicer module is
not available” while DENTO Workflow was loaded. The live `dentobot-slicerros2`
Slicer command line already included SlicerROS2 `qt-loadable-modules` and
`qt-scripted-modules` plus DENTO Workflow. The bridge helper
`get_ros2_logic()` used a global `slicer` name without importing it; that
`NameError` was swallowed and surfaced as a missing-module dialog.

`DENTOROS2Bridge` now imports `slicer` at the call site, then instantiates
`ROS2` / `ROS2MotionControl` from installed SlicerROS2 paths if they are not
loaded yet. The Ubuntu launcher also merges DENTO Workflow into
`SLICER_ROS2_MODULE_PATHS` after sourcing the workspace so `slicer_args` only
selects the module. If ROS2 is still absent (host or Windows Slicer), Connect
explains the launcher requirement and offers the MRML URDF robot so 6.1
place/lock is not blocked.

Reload the DENTOBOT extension in a Slicer window that was started with
`./scripts/launch-dentoworkflow.bash`. If this window is host Slicer, close it
and relaunch through that script. Hardware and MoveIt remain out of scope.

## 2026-08-19 — Step 6 gated robotic sequence and Elements recommended view

Status: implemented; host pytest recorded; interactive Slicer verification pending

Step 6 is a gated robotic workflow, not a lab dump:

- **6.0 Choose scene (XOR):** import the Steps 0–5 case package, or load the
  draft phantom. Switching asks for confirmation; importing a case deletes the
  phantom; loading a phantom clears the imported-case flag.
- **6.1 Load ROS robot, place, and lock:** disabled until a scene is active.
  Placement and lock require a robot in the scene (ROS preferred; MRML STL
  load is fallback only). Lock freezes the mount.
- **6.2 Task joint limits:** enabled once a robot is present.
- **6.3 Plan / preview:** enabled only with an imported case and a locked base.

View Controls → Elements now has a Stage 6 list (target, trajectory, docks,
template, phantom, robot, mount). Recommended view is applied on scene/robot
load and when entering Step 6 with auto-recommended on. Step 6 no longer
force-shows every robot/phantom display node.

MRML **Load / Refresh Robot** and **Frame Scene + Robot** remain as fallback
controls. Hardware, MoveIt, and clinical collision validation remain out of
scope.

## 2026-08-18 — Inspect Record3D iPhone OBJ scans with a host vispy viewer

Status: parser and GUI smoke verified on `data/3dscan_iphone.zip`; interactive
orbit/playback acceptance is operator-run; this is not registration

Keep iPhone Record3D point-cloud inspection on the host as a standalone
PyQt6/vispy script (`scripts/view_record3d_scan.py`). Reuse
`/home/light-tarun/pressure-env` for Qt/NumPy and add only `vispy`, `PyOpenGL`,
and `freetype-py` there. Do not import these packages into Slicer, the
`dentobot` Conda inference environment, or the SlicerROS2 container.

Open a zip, a folder, or a single OBJ in place. Record3D's OBJ export is a
coloured vertex list in camera metres, typically without faces; retain that
frame and unit. Do not silently convert the cloud into Slicer RAS, unpack the
328 MiB example zip into `data/`, or treat a plausible render as anatomical
validation. The sidebar reports frame count, missing indices, point count,
bounding-box extent in millimetres, colour presence, and unusually small
frames so later optical-surface registration work has a checked input.

Reason: the example export is a 195-frame LiDAR sequence, not a Slicer MRML
asset. A host GPU point viewer can scrub that sequence without contaminating
the medical-image scene or the inference Python.

## 2026-08-17 — Host Arduino pressure monitor uses a dedicated venv and Cursor launch config

Status: live serial/GUI launch verified on the physical Ubuntu session; this is
sensing-bench evidence only

Keep the Arduino UNO WiFi R4 pressure-monitor script on the host as a
standalone PyQt6/pyqtgraph tool. Run it with the existing
`/home/light-tarun/pressure-env` interpreter, not Slicer's embedded Python, not
the `dentobot` Conda inference environment, and not a container Python. Point
the Cursor workspace Python interpreter and the **Pressure Monitor** launch
configuration at that venv so the Run button and F5 use the packages already
installed there (`numpy`, `pyserial`, `PyQt6`, `pyqtgraph`).

Serial remains `/dev/ttyACM0` at 460800 baud. CSV runs stay under
`ros2_ws/src/Arduino/pressure_runs/` next to the script, not under the home
directory. This bench does not command a robot, authorize
drilling, or implement the future sensing/stop-logic runtime.

Reason: the script needs GUI and serial packages that must not enter the
Slicer or inference Pythons. The workstation already had a working venv; Cursor
had no Python runner until the Microsoft Python and debugpy extensions were
installed.

## 2026-08-17 — Preserve private CRD/Xfce and stabilize the physical host path

Status: installed and live kernel settings verified; reboot activation and
overnight CRD soak pending

Retain Chrome Remote Desktop's separate Xfce virtual desktop because work in
that session must not appear on the physical monitor. Accept force-stopping
the same-user virtual session before a physical GNOME login; that session
handoff is not the responsiveness defect being solved.

Move only the physical GDM/GNOME login path from Wayland to Xorg. Keep swap
enabled but reduce swappiness from 60 to 10 and replace percentage-based dirty
page limits with 128 MiB background and 512 MiB hard writeback thresholds on
the rotational system disk. Preserve the active systemd-oomd policy and the
existing container process safeguards.

Reason: journal accounting showed the idle GDM Wayland greeter consumed almost
one full CPU continuously for three days while CRD/Xfce was active. Earlier
whole-host stalls also followed memory pressure on an HDD configured to permit
early swap and multi-gigabyte dirty-page accumulation. The new boundary keeps
the required private virtual session while removing the observed greeter KMS
path and reducing swap/writeback latency. It does not claim closure until a
post-reboot overnight observation passes.

## 2026-08-18 — Step 6 planning sub-workflow: import, mount lock, task limits, simulated motion plan

Status: implemented; host pytest recorded; interactive Slicer verification pending

Split Step 6 into four operator stages tied to upstream workflow artifacts:

- **6.0 Import planning package** — one click validates and links the existing
  MRML case graph: CBCT volume, teeth segmentation, trajectory, docking assembly,
  and printable template. No separate file bundle is created.
- **6.1 Move and lock robot base mount** — placement controls remain available
  until **Lock Base Mount** freezes the base transform and mount plane handles.
- **6.2 Task joint limits** — per-joint min/max translation or revolution
  (degrees for revolute joints, millimetres for prismatic joints) are stored on
  the parameter node, clamped to URDF mechanical bounds, and applied to Step 6
  joint spin boxes and motion planning.
- **6.3 Trajectory motion planning (simulation)** — samples the approved
  Entry-to-Target line, solves position-only IK per waypoint with SciPy
  L-BFGS-B, and rejects configurations with coarse non-adjacent link AABB
  self-collision plus subsampled environment clearance against segmentation
  closed surfaces, template shell, docking assembly, and optional support
  anatomy. **Preview Simulated Motion** streams joint waypoints in MRML only.

This remains simulation-only: no MoveIt, no `move_group`, no hardware command,
no swept-volume collision, and no calibrated TCP. The default 5 mm AABB
self-clearance can reject the draft neutral pose because conservative boxes on
`link-3`/`link-5` overlap; treat clearance as a tunable research gate, not a
clinical safety claim.

Implementation: `DENTOStep6Planning.py`, Step 6 UI group boxes in
`DENTOWorkflow.ui`, logic/widget handlers in `DENTOWorkflow.py`.

## 2026-08-18 — Step 6 SlicerROS2 Motion Control bridge (no MoveIt)

Status: implemented; container ROS verification recorded; interactive Slicer
session pending reload

Add an optional second robot path in Step 6 that loads `dentobot_description`
through SlicerROS2 instead of MRML STL meshes alone. The workflow starts or
detects `description.launch.py` with `joint_state_mode:=slicer`, loads
`robot_description` from `/dentobot_robot_state_publisher`, parents the ROS
robot root TF lookup under `[Step 6] DENTO Robot Base Placement`, configures
ROS2 Motion Control with `move_group` disabled, and hides MRML link meshes
while ROS motion control is active. Motion Control sliders stream simulated
joint commands on `dentobot/slicer_joint_positions`;
`dentobot_slicer_joint_state_publisher` republishes them as `/joint_states`.
This remains visualization only: no hardware command, MoveIt planning, or
calibrated TCP. Refuse to start if a competing neutral or manual publisher is
already running. Keep the MRML placement path for offline workspace work.
Launcher: `scripts/launch-dentobot-description-for-slicer.bash`.

## 2026-08-17 — Use a disposable pure-hinge open-mouth phantom in Step 6

Status: implemented and synthetic graphical Slicer-verified; evening UX,
workspace-layout, and hinge-parent fixes synthetically re-verified on 2026-08-17;
physical-session, head-mount, workspace, collision, and clinical acceptance pending

Load the public aligned BodyParts3D neurocranium, maxilla, and mandible as
local non-patient design assets. Keep the skull/maxilla fixed and place four
approximate landmarks one at a time in the scene: left TMJ, right TMJ, upper
central incisor, and lower central incisor. Use progressive Place-landmark
clicks so the operator can pan between points; clear landmarks with a separate
control. Rotate the mandible rigidly about the resulting TMJ axis until the
transformed lower-incisor point is approximately 40 mm from the fixed upper-
incisor point. The 40 mm requirement is the final inter-incisor gap, not a
literal 40 mm mandibular translation.

Only one draft phantom set and one robot placement set may exist in Step 6 at a
time. On first load, parent the phantom meshes under a disposable workspace
transform that relocates them from BodyParts3D native coordinates to the
research workspace center `(0, -150, 250)` mm RAS so the phantom and robot
share the same viewport. The hinge solver still operates in world RAS, but the
jaw opening transform must store the equivalent matrix in workspace-parent local
coordinates when the jaw node parents under that workspace transform.

Keep this path visibly disposable and intentionally simple. Do not add
anatomical joint translation, soft tissue, contact, clinical landmarking,
patient registration, or a jaw biomechanics solver. Let the researcher place
the robot on an approximate forehead plane with the existing Step 6 snap/fine
controls, then explore the intraoral space with the existing manual six-joint
controls. No automated end-effector control, ROS command, collision guarantee,
or hardware motion is authorized.

Reason: the current design iteration needs a rapid visual reach/flexibility
trial and will be superseded once it has informed the mechanical design. A
deterministic rigid hinge and explicit measured gap are sufficient for that
bounded purpose and avoid implying clinical accuracy.

## 2026-08-14 — Make robot placement DENTOWorkflow Step 6

Status: implemented and Slicer-native synthetically verified; physical-session
placement UX, head/mouth geometry, registration, TCP, and safety acceptance
pending

Add **6 · Robot Placement** after the planning/template stages in the visible
DENTOWorkflow sequence. Load the tracked seven STL visual models directly as
raw RAS/CAD millimetre geometry and reproduce the tracked URDF forward chain
with one transform per link under one persistent editable robot-base transform.
Joint controls remain in the selected-zero display units: degrees for rotary
joints and millimetres for prismatic joints.

Represent a provisional head/forehead mounting surface with an unlocked
`vtkMRMLMarkupsPlaneNode`. Let the researcher drag its native translation and
rotation handles, then explicitly snap the robot base origin and orientation to
that plane after removing scale/shear. Fine placement post-multiplies local-base
translations/rotations. Provide buttons for every local axis and opt-in keyboard
nudges, but enable shortcuts only while Step 6 is active and ignore them
while a text or numeric editor has focus.

This is an in-scene MRML experiment only. It neither subscribes to nor
publishes ROS, defines a SlicerROS2 bridge, computes IK, commands a controller,
or authorizes hardware motion. The plane is not a registered head mount; the
`burr` link is not a calibrated TCP; and no head, mouth, cable, swept-volume,
force, or clinical collision guarantee is implied.

Reason: the current design iteration needs fast manual placement and
articulation beside later head/mouth models, while the physical frame graph and
control architecture remain deliberately unresolved. A native Slicer transform
hierarchy makes that bounded visualization test possible without prematurely
coupling it to ROS or robot commands.

## 2026-08-14 — Adopt the photographed configuration as a draft robot zero

Status: implemented and synthetically/RViz verified; engineering and physical
zero-frame acceptance pending

Treat the developer-selected manual state J1 `25.38 deg`, J2 `0 mm`, J3
`62.46 deg`, J4 `0 mm`, J5 `1.08 deg`, and J6 `-35.28 deg` as the draft design
zero. Absorb the four nonzero rotary values into their URDF joint origins so
every published joint position is zero at that pose. Shift each finite rotary
limit by the same offset, preserving its original span. This is a coordinate
redefinition, not evidence of encoder or mechanical homing.

Rotate the integration-only fixed `base_link -> link-1` transform by -90
degrees about X. Link-1's thin local-Y mounting face then lies on the RViz XY
plane, while the articulated chain and CAD burr origin extend above the grid.
Negate the J4 prismatic axis but retain its positive 0–75 mm range; positive J4
travel must therefore move primarily in negative `base_link` X.

Reason: the selected pose is a more useful starting configuration for manual
mouth-workspace exploration, a planar mounting reference makes RViz inspection
easier, and the observed J4 direction was opposite the intended design motion.
The received source URDF remains unchanged for traceability.

## 2026-08-14 — Use 5 mm link AABBs only as draft workspace feedback

Status: implemented and synthetically verified; representative head/mouth,
physical geometry, and collision-engine acceptance pending

During manual joint articulation, derive one base-frame axis-aligned bounding
box from each transformed URDF collision mesh. Ignore direct parent-child
pairs and warn when any other pair's Euclidean box separation is below 5 mm.
Display the pair/distance in the manual window, publish green/red RViz box
outlines, and report the CAD `burr` link origin in base coordinates to support
early reach/flexibility exploration. Warnings are advisory and never block a
joint-state update.

Do not call this exact self-collision detection. Rotated AABBs are
configuration-dependent conservative envelopes, and the URDF currently reuses
detailed visual STLs as collision meshes. A box overlap can be a false positive
and box clearance can miss triangle-level, swept-volume, cable, head, patient,
or mounting interference. The burr origin is not a calibrated TCP. Human-head
and mouth geometry will enter only through a later Slicer/MRML experiment after
the movable robot and mounting-frame assumptions are ready.

Reason: this design iteration needs rapid manual reach and flexibility
feedback before the head mount, exact collision geometry, end-effector
kinematics, and Slicer transform bridge are defined. The 5 mm advisory is cheap,
visible, and appropriately bounded for that pre-initial experiment.

## 2026-08-14 — Validate manual joint articulation before Slicer or IK

Status: implemented and synthetically verified in Jazzy/RViz; physical CAD
direction, scale, zero, and limit acceptance pending

Make independently controlled joint-state publication and forward-TF
inspection the next bounded robot-integration gate. The description package
owns a simulation-only PyQt control window that presents revolute joints in
degrees and prismatic joints in millimetres while publishing ROS-standard
radians/metres. Its launch selects exactly one of neutral, manual, or external
joint-state modes. It does not expose a command topic, controller,
`ros2_control` hardware interface, Slicer bridge, inverse-kinematics solver, or
end-effector command.

Require each joint to pass an independent runtime perturbation: upstream
frames remain fixed, the joint child exhibits the correct rotational or
translational motion, and the downstream tool chain responds. Use RViz for
graphical inspection of the neutral and articulated meshes, then obtain
engineering/physical acceptance for handedness, zeros, directions, ranges,
scale, and alignment before defining end-effector control.

Reason: a valid URDF tree and a visible neutral mesh do not establish usable
kinematics. Isolating forward articulation first makes bad axes, joint order,
units, or CAD transforms observable without coupling them to Slicer, IK, a
controller, or hardware motion.

## 2026-08-14 — Begin ROS integration with a description-only simulation boundary

Status: implemented and synthetically verified in Jazzy; visual, physical,
kinematic, collision, calibration, and hardware acceptance pending

Track the received URDF and seven STL meshes in a standalone
`dentobot_description` ROS 2 package. Preserve every supplied movable link,
joint, transform, limit, inertial value, mesh scale, and triangle; change only
the generic robot name and relative mesh paths, then add a massless
`base_link` with an identity fixed joint above the supplied inertial root for
KDL compatibility. Record source checksums and fail tests on unexpected mesh
changes.

Publish a deterministic six-joint neutral pose and the resulting TF tree for
visualization. The neutral publisher has no command subscriber, controller,
transmission, `ros2_control` plugin, hardware adapter, or motion capability.
Keep RViz optional and do not treat a rendered mesh or resolved transform as
evidence that joint zeros, directions, ranges, dynamics, collision geometry,
TCP/docking frames, or physical calibration are correct.

Expose the tracked nested package to colcon with a bootstrap-managed relative
source-space symlink because the DentoBot root is already detected as the
generic CMake Slicer extension. Build this package in the existing Jazzy
container; do not mix its build/install/log trees with host Lyrical.

Reason: the received description enables a useful simulation-first vertical
slice now, while keeping powered motion, robot commands, safety, and the final
ROS/MoveIt/vendor transport decision outside the Slicer and description
processes.

## 2026-08-14 — Use a compact stage wizard and an application-level view palette

Status: implemented and Slicer-native verified; physical-session UX acceptance
pending

Keep only the selected top-level workflow stage visible and expanded. The
module panel owns a fixed two-row control bar containing stage navigation,
quick-view selection, frame/restore, a compact guidance action, and the entry
point to a nonmodal **DENTOBOT View Controls** tool palette. Put selected-volume
metadata inside CBCT Imaging rather than in fixed module chrome.

Move the existing Elements and Display widgets into the palette instead of
creating parallel controls. Elements is disabled before Step 4A; Display stays
available. Store only the palette's visibility and window geometry in Qt
application `QSettings`, so the choice follows the workstation/application and
does not enter an MRB case. Hide the palette when the module exits and restore
the remembered preference when it is entered again.

Reason: persistent accordions and display groups consumed most of a roughly
405-pixel-wide module panel and left too little height for the actual clinical
task. Reparenting the authoritative widgets preserves their signals, MRML
bindings, display-preset schema, and display-only behavior while returning the
panel to a true task-focused wizard. This remains an extension UI improvement,
not the later reduced custom-Slicer application.

## 2026-08-14 — Bound and reap the reusable Slicer development container

Status: implemented and synthetic Bridge B verified; overnight observation
pending

Keep the reusable SlicerROS2 container, but run its `sleep infinity` command
below Docker's minimal init so exited descendants are reaped. Cap the
container at 512 tasks, give it half the default relative CPU scheduling
weight, set OOM score adjustment 500, and allow a 30-second graceful stop.
Do not impose a RAM limit until representative CPU segmentation establishes a
safe peak; an incorrect hard cap would turn valid inference into a failure.

Refuse a second launcher session while a live Slicer/ROS launch exists.
Headless Bridge B phases own and reap their exact Xvfb process and apply an
internal process-group timeout, with an outer Docker-client guard. Provide a
read-only health command for CRD, RAM/swap, container PIDs/zombies, active
runtime processes, and high host CPU consumers.

Reason: the failed overnight session showed memory-pressure journal flushes,
service timeouts, CRD signaling loss, and a container with about 620 tasks,
including lingering Slicer/Xvfb work and zombies. There was no recorded OOM
kill, GPU reset, thermal event, disk error, or Wi-Fi disconnect. On the
rotational system disk, swap-backed process buildup can stall the desktop long
before an OOM kill. Reaping, bounded task creation, and contention priority
protect the remote control plane without changing the inference environment.

## 2026-08-13 — Complete-template build is cached and scene restoration follows explicit references

Status: implemented and focused Slicer-native verified; representative live
fusion/inspection acceptance pending

Make the routine Step 5B action a dependency-aware complete build. It first
preflights the current Step 5A support inputs, insertion direction, confirmed
Step 4B four-dock assembly, and exact locked source trajectories. It then
generates only a missing/stale directional blockout, patient-contact shell, or
unified trajectory-guide/dock fusion. A Current patient shell is an expensive
cached derived input and must not be regenerated for display inspection or a
guide/dock-only rebuild. Separate fit, shell-plus-guides, and unified-only
inspection actions alter MRML display visibility and framing only.

On MRB import, the persisted singleton parameter node and its explicit MRML
references remain authoritative. If its selected segmentation references a
different source CBCT than the saved global slice background/input volume,
restore the segmentation's referenced source CBCT. Never select the newest
segmentation merely because another corrected/exported segmentation also
exists. A deliberate authoritative-segmentation change remains destructive to
target-specific downstream state and switches to that segmentation's own
source volume.

Store display presets as node-independent parameter sets in the MRML parameter
node. They may include segmentation overlay/opacity/representation and CBCT
window-level/grayscale/interpolation values, but do not bind the preset to a
specific DICOM or segmentation node ID. Workflow element presets remain
transient display filters and must be restored around scene save rather than
becoming geometry or ownership state.

Reason: shell voxel generation is the expensive stage; verification needs many
display passes but no geometry rebuild. Saved-scene continuation must also be
deterministic when one scene legitimately contains multiple volumes and
segmentations with different coordinate frames.

## 2026-08-13 — Step 4B yaw is collision-screened, editable, and explicitly confirmed

Status: schema v3 implemented and synthetically verified; representative
anatomy, clinician, mechanical, and phantom acceptance pending

Define dock yaw as rotation of all four dock centres about the stored
target-crown frame `+Z` normal. Automatic placement performs a deterministic
5-degree sweep and ranks candidates against sampled closed surfaces from every
other whole-tooth segment on the target FDI arch. The opposing jaw is excluded;
the target supplies the frame rather than acting as an obstacle. Because Step
4B precedes Step 5A support selection, the screen does not silently depend on a
later support list.

The winning yaw is a **Draft**, not an approval. Persist the selected angle,
collision-clearance request, obstacle segment IDs, sampled-clearance metrics,
and any omitted obstacle surfaces. Let the user adjust yaw with the slider,
rebuild the draft, inspect referenced read-only centroid/radius/diameter/depth
Markups lines in 2D/3D, and explicitly confirm the current orientation. Any
dimension, yaw, trajectory, or relevant upstream change returns the assembly
to Draft/Stale. Step 5B fusion requires a Current, Confirmed schema-v3 assembly.

Treat vertex-to-finite-cylinder screening as conservative draft assistance,
not continuous-surface collision proof or clinical validation. A detected dock
collision is a final-verification FAIL; an omitted same-jaw obstacle surface is
a visible WARNING. The final rail profile, tolerances, load path, segmentation
uncertainty, and physical collision/fit still require representative and
printed-phantom evidence.

## 2026-08-13 — Close a bounded PoC by evidence, not feature count

Status: accepted as the immediate development-order decision; clinical
thresholds and physical evidence remain pending

Treat the current software/template vertical slice as a candidate Template V0
that must now be bounded and tested, not as permission to continue broad
feature accumulation. Freeze the exact automated clinical task, exclusions,
clinician approval point, failure-safe state, and the Template V0 contact,
clearance, wall, margin, insertion, undercut, guide, docking, and manufacturing
assumptions before making a stronger PoC claim.

Advance the next work packages in this order: representative-anatomy live
acceptance; one printed Template V0 with seating/removal/repeatability and
critical-dimension measurements; an explicit planning-to-robot coordinate-frame
graph and first target registration error experiment; parallel robot/tool/
sensing requirements; and a system error budget. Convenience or visualization
work may interrupt this order only when it fixes an observed failure that
prevents one of those bounded tests.

Label each works claim by its strongest actual evidence: static inspection,
synthetic automated test, developer-live test, representative anatomy, printed
phantom, or clinician/expert acceptance. Software topology PASS does not imply
physical seating, mechanical rigidity, registration accuracy, or clinical
acceptance.

Reason: the implementation now contains many synthetically verified
capabilities, while the highest-risk assumptions remain clinical fit,
manufacturing, registration, load path, robot kinematics, and total-system
accuracy. More feature count would hide rather than close those gaps.

## 2026-08-13 — Daily Compass is editable working memory, not engineering authority

Status: accepted

Maintain `DENTOBOT_Daily_Compass.docx` as the researcher's single editable
day-to-day mental-model workbook. It is the first place for free-form capture,
today's outcomes, uncertainties, meeting notes, and lane-level status. The
researcher may edit it directly; at an explicit documentation checkpoint,
Codex reads those edits, reconciles them against repository state, and updates
the controlled Markdown documents and dated logbook as appropriate.

The Daily Compass is not the source of truth for clinical thresholds,
architecture, verification claims, or task completion. Those remain in
`PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `DEVELOPMENT_PLAN.md`, `DECISIONS.md`,
`TASKS.md`, `REPRODUCIBILITY_AND_TRACEABILITY.md`, and the dated logbooks.
Conflicts are resolved explicitly; unreviewed notes are never silently promoted
to accepted decisions. Git and Google Drive synchronization remain batched and
approval-driven rather than occurring after every edit.

Reason: one editable operating picture restores a practical OneNote-like habit
without weakening traceability or turning transient thoughts into undocumented
engineering commitments.

## 2026-08-13 — One Step 4A owns manual and assisted trajectory creation

Status: implemented and focused Slicer-native verified; live UX acceptance
pending

Treat manual Entry→Target placement and assisted root-target initialization as
optional creation modes inside one **Step 4A — Trajectory Planning** stage.
Both modes create and edit the same role-owned two-point
`vtkMRMLMarkupsLineNode` in world RAS, use the same target/bounds references,
and feed identical verification, backtracking, docking, and template logic.
Assisted entry markups are tagged Step 4A and remain explicitly provisional;
they are not a sequential completion gate and do not establish a second
trajectory abstraction.

The stage navigator therefore has nine entries. Step 4A expands the primary
manual planning controls plus a nested-looking optional assisted section;
guide rails and docks move from the former Step 4C label to **Step 4B**.
Persistent identity remains role/reference based, so old scene display names
do not become migration contracts. Role-owned assisted and docking nodes are
retagged for the current Step 4A/4B Data-view vocabulary when refreshed.

Reason: assisted planning is an alternate initializer that must still be
manually reviewed and corrected. Showing it as a later workflow step implied
that both manual and assisted planning were sequentially required.

## 2026-08-13 — Stage-aware viewport filters are transient presentation state

Status: implemented and focused Slicer-native verified; live clinician UX and
physical-rendering acceptance pending

Provide one **Viewport — Elements in View** panel from Step 4A through Step
5C. Build its inventory from the active segmentation's stable segment IDs and
role/reference-owned MRML nodes, not display names. Expose step-relevant quick
views and independent checkboxes for target/support/other masks, target bounds,
the exact trajectory set, assisted entries, occlusal plane/docks, support
boundary/plane/preview, insertion/undercut/blockout, patient shell, fusion
auxiliaries, and final printable template. The Step 4A recommended view shows
only the selected trajectory unless assisted entries are being reviewed; the
explicit planning preset can show all same-target trajectories.

Visibility filtering changes only MRML display nodes. Capture the exact prior
segmentation global/per-segment visibility and opacity plus owned-node 2D/3D
visibility before the first filter, allow combined world-RAS framing, and
offer one exact restore action. Treat presets as transient application
presentation: restore the underlying scene display at save start, serialize
that original state, then reapply the active preset after save. Scene close,
module exit, cleanup, parameter-node replacement, or navigation before Step
4A also restores the snapshot. Hide the older duplicate Step 5B visibility
panel from the active UI while keeping its compatibility code.

Reason: users need rapid isolation without manipulating Slicer's Data tree,
but a convenient shell-only or target-only view must never alter masks,
geometry, references, or silently become the saved scene's unexplained
visibility state.

## 2026-08-13 — Trajectory edits use confirmed reference-driven backtracking

Status: implemented and focused Slicer-native save/reload verified; live
legacy-scene acceptance pending

Treat Entry→Target trajectories as upstream geometry, not isolated lines.
Before a selected trajectory is unlocked, interactively moved, cleared, has a
point removed, or is deleted, traverse explicit MRML references from that
trajectory through the active Step 4C/5 branch. If derived geometry exists,
show one confirmation listing the affected workflow stages and delete the
reached derived subtree before allowing the change. Deleting the trajectory
also enforces this cascade in logic so future callers cannot bypass it.

Retain the authoritative segmentation, target tooth/segment ID, target-bounds
ROI, support-tooth choices, unrelated trajectories, and the Step 5A draft
support model when it is not trajectory-derived. Switching to another target
tooth is a complete active-branch backtrack: confirm and remove Step 4C and all
Step 5 derived objects, then clear branch-local guide selections. A
role-specific deletion failure in an old or partially migrated MRB may fall
back only to the exact active parameter-node objects already identified as
impacted; it must never delete by display name.

Filter the Step 4A selector to DENTOBOT Entry→Target lines. On selection,
synchronize the persisted parameter reference, target controls, and views;
make the exact chosen line fully opaque with labels while dimming same-tooth
siblings. Managed labels retain FDI, per-tooth ordinal, and Complete/Empty
state so duplicate same-tooth lines remain distinguishable after reload.

Reason: saved scenes could contain two visually identical trajectories while
only one had usable points, and deleting or changing an upstream line left
stale docking, support, shell, or final-template children selected deep in
Step 5. Reference-driven backtracking restores a deterministic closed-loop
workflow without conflating names with identity.

## 2026-08-13 — Keep native imaging authoritative; make display mappings optional

Status: implemented and Slicer-native verified; clinician acceptance pending

Keep `vtkMRMLSegmentationNode` with `Binary labelmap` as the authoritative
segmentation representation and the default 2D display. For an explicitly
optional, non-authoritative preview, allow the segmentation display node to
intersect its existing derived `Closed surface` representation with the slice
plane. Persist the choice as a DENTOBOT MRML attribute. Opening Segment Editor
changes the display to native-mask mode so voxel corrections are made against
the exact editable representation. Older scenes must not be automatically
switched to the derived preview.

Expose only Slicer's native scalar-volume display mapping for the referenced
source CBCT: automatic/manual window and level, Grey/InvertedGrey lookup-table
selection, and optional viewport interpolation. Capture the display state when
the volume is first bound so it can be restored. Do not filter, sharpen,
denoise, resample, or modify CBCT voxels; do not modify the mask, replace the
authoritative representation, or describe any display mapping as recovered
anatomy. The acquired voxel spacing,
reconstruction quality, partial-volume effects, metal artifacts, segmentation
uncertainty, and registration uncertainty remain accuracy limits.

Reason: the reported jagged overlay was the 0.5 mm binary labelmap grid, while
3D already used a smooth derived surface. The two representations serve
different purposes, but medical-image honesty requires the native grid to be
the default. Window/level and grayscale direction can improve the visibility
of existing intensity differences without creating new image information.

## 2026-08-12 — Step 4C schema v2 uses four independent occlusal-plane docks

Status: implemented and Slicer-native synthetically verified; representative
anatomy, dimensional, mechanical, phantom, and clinician acceptance pending

Replace the rejected crown-centred hub/radial-spoke topology with four
independent hollow robot/registration docks. Approved Entry→Target axes now
establish only crown/root polarity. A target-crown-cap PCA fit supplies the
occlusal-plane normal, with a deterministic trajectory-perpendicular fallback
for a degenerate or greater-than-60-degree fit. The crown-cap centroid is the
pattern origin; no solid is placed there.

Each dock's designated robot-facing top/opening lies on the stored occlusal
plane. Configurable depth proceeds from that face along the crown-to-root
occlusal normal. The 15 mm radial offset, 1 mm bore, outer diameter, attachment
width/overlap, and shared or individual depths remain visible provisional
research parameters.

Step 5B creates four separate closest-surface dock-to-shell attachments. It
keeps the trajectory-aligned annular drill-guide sleeves and their local shell
collars as a different mechanical role. Robot-dock solids and attachments are
processed against the drill-guide clearance envelope; any core-dock/envelope
intersection is a hard generation error rather than trimming a load-bearing
dock, while attachment/reinforcement material is clipped before final fusion.
All drill-guide and dock channels are subtracted last.

Schema `2.0` makes older Step 4C nodes stale and requires regeneration. Final
verification requires four independent dock components, zero central hubs,
zero radial spokes, four shell attachments, top-face coplanarity, the
guide-exclusion record, one occupied printable component, and preserved
channels. This resolves the reported topology/overimposition defect; it does
not finalize the rail cross-section, load path, tolerances, materials,
registration semantics, or two-trajectory robot kinematics.

## 2026-08-12 — Reject the central-hub interpretation of Step 4C rails

Status: superseded by the schema-v2 independent-dock implementation above;
retained as the decision history for rejected checkpoint `7800cb6`

The clinician/robotics intent is not a crown-centred mounting hub with four
spokes. The target-tooth crown/occlusal plane constrains the intended guide-
rail surface/tangent reference. It is not permission to place a solid dock
base or hub over the target crown. Four surrounding dock holes and their rails
must remain geometrically distinct from the trajectory-aligned drill guide and
must not obstruct its channel or required working clearance.

The rejected checkpoint implementation exposed three separate concepts that
must not be conflated:

1. the annular trajectory guide and its local shell-attachment reinforcement;
2. the four robot/registration dock holes and their rail bodies; and
3. the structural connections that merge those parts into the tooth-supported
   shell.

At checkpoint `7800cb6`, `create_target_frame_docking_geometry()` created a
central hub at the crown-cap centroid and four radial cylindrical connectors.
This was a provisional attempt to make all four docks one connected printable assembly.
Because a drill trajectory Entry is commonly near the same target-crown
region, the hub/spokes can overimpose the annular trajectory guide and produce
the reported blocked or cluttered geometry. This topology is rejected as the
intended mechanical design even though its synthetic Boolean/connectivity test
passes.

`create_multi_trajectory_docking_geometry()` is also misleadingly named: it
creates the trajectory-aligned annular guide sleeve, its clearance, a local
reinforcement collar, and the restored drill channel. That collar came from
the SlicerFSP-inspired clearance → reinforcement → union → channel-restoration
sequence. It is not one of the four robot docking rails. Retain only the
minimum independently justified shell attachment around the drill guide; do
not turn it into a second robot dock or let it merge blindly with the rail
network.

Before replacing the current checkpoint geometry, define the rail cross-
section, which rail surface is coincident/tangent with the occlusal plane, the
four dock axial datum, how each rail reaches the shell without a central hub,
the exclusion/clearance envelope around every drill guide, and the required
load path. The revised generator should route four independent surrounding
rail/dock branches to verified shell attachment regions while reserving the
trajectory-guide envelope, then subtract all drill/dock channels last and
verify their continuous openings and dimensions.

Reason: a watertight connected Boolean output can still embody the wrong
mechanical topology. Passing synthetic connectivity cannot substitute for the
intended spatial relationship among crown plane, drill guide, rails, and shell.

## 2026-08-12 — Provisional Step 4C feeds one verified 5B/5C printable model

Status: implemented and Slicer-native synthetically verified; mechanical,
phantom, and clinician acceptance pending

Implement the requested four-dock pattern as explicitly provisional research
geometry without claiming that it is the final robot interface. Step 4C uses
the complete set of one or two locked target-tooth trajectories. Their mean
Entry→Target direction defines crown/root polarity; a target crown-cap fit
defines occlusal normal `+Z`, a crown-cap principal axis defines transverse
`+X`, and `+Y` completes a right-handed world-RAS frame. No world axis is
anatomical. The reference plane and preview retain explicit segmentation and
repeated trajectory references.

Interpret the currently requested `15 mm` as the configurable radial distance
from target crown centroid to each of four `+X/+Y/-X/-Y` dock centres, and
interpret `1 mm` as the configurable bore. Keep outer diameter, attachment
branch width/overlap, common dock depth, and the optional four independent
depths visible. These are development defaults, not approved tolerances or a
frozen mechanical profile. All robot-facing top/opening surfaces lie in the
stored crown/occlusal plane; dock depth proceeds crown-to-root along `+Z`.

Step 5B regenerates the Step 4C solids from stored frame/parameters, combines
them with the existing per-trajectory annular guide holes, and uses four
recorded closest-surface attachments to give every dock a volumetric connection
to the patient shell outside the protected guide envelope. A tight voxel Boolean subtracts clearances,
unions reinforcement/docking, restores every channel, removes only isolated
one-voxel contour artifacts, and rejects more than one substantive occupied
volume. Slicer's closed-surface segmentation accessor is already world RAS;
never apply the parent transform to its result a second time.

Step 5C is now the active final geometry/provenance gate and one-STL export.
It records PASS/WARNING/FAIL checks for current inputs, support ROI and
insertion-direction provenance, undercut processing, trajectory snapshots and
axis agreement, four-dock coplanarity, non-empty/watertight topology, one
occupied printable volume, channel/reinforcement masks, and resolution versus
requested wall/bore dimensions. A clinical collision/fit review remains a
WARNING because software topology cannot validate fit or robot safety. FAIL
blocks export; PASS/WARNING permits exactly one atomic binary STL after the
checks are rerun. The old ROI/raw-shell/separate-sleeve/trim/two-file path is
hidden and no longer executed; its node-reading logic remains for old-scene
compatibility.

This does not resolve the kinematics of two non-parallel trajectories under a
single fixed robot Z axis, registration semantics, materials, structural
loads, manufacturing tolerances, sterilization, clinical fit, or drilling
authorization.

## 2026-08-12 — One active workflow stage in the Slicer module panel

Status: implemented and Slicer-native synthetically verified; live visual
acceptance pending

Keep the existing CTK collapsible sections and their MRML-bound controls, but
place a compact stage navigator above them. Selecting a stage expands exactly
one top-level section and collapses its peers; manually expanding a section
updates the navigator. Previous/Next buttons provide linear movement without
making stage completion a hidden prerequisite or changing workflow data.

Long instructional and detailed safety paragraphs are hidden by default behind
one explicit guidance toggle, while a permanent `RESEARCH PROTOTYPE — NOT
CLINICALLY VALIDATED` banner and all operational status/error labels remain
visible. Volume metadata and backend process output are independently
collapsible/optional. Launcher-managed backend paths are hidden unless the
operator deliberately enables manual overrides. Secondary panels such as
selected-label details, provenance, planning summary, oblique MPR, docking
fusion, and the scene-visibility inventory are nested collapsibles; the primary
patient-contact shell panel remains open. The navigator recommends the next
incomplete stage from explicit parameter-node state but never yanks the
operator away from the stage they are inspecting after initialization.

Reason: the prior single scrolling column exposed every expanding section,
verbose paragraph, machine path, and output log simultaneously. The navigation
layer reduces cognitive and vertical load without replacing widgets, node
references, callback contracts, or Slicer's standard views.

## 2026-08-12 — View navigation remains transient MRML presentation state

Status: implemented and Slicer-native synthetically verified; physical-session
usability and FPS acceptance pending

Expose explicit workflow view actions rather than treating placement side
effects as the only way to focus anatomy. Step 4 can temporarily isolate the
authoritative target segment and immutable bounds; Step 5A can isolate the
target plus selected support segments. Both operations snapshot and restore the
exact previous segment/model visibility. Bounds-based frame actions centre all
active slice views and cameras without moving anatomy, changing trajectory
coordinates, or creating copied models.

For bidirectional spatial reference, use Slicer's singleton
`vtkMRMLCrosshairNode` and native accurate 3D picking. The optional control uses
centred slice jumps and Shift-hover in 3D, then restores the exact previous
crosshair mode, behavior, thickness, and fast-pick setting when disabled,
saved, closed, or the module exits. Do not create a second scene browser or a
custom picking coordinate system.

Keep trajectory MPR on the native scalar-volume slice reslice pipeline. Prefer
the Red slice deterministically, coalesce slider/wheel changes to approximately
one 60 Hz refresh, and optionally enable native linear display interpolation.
Interpolation is display-only and the previous volume-display setting is
restored; no resampled CBCT is generated.

Reason: view controls must improve focus and cross-reference without becoming
new anatomical/planning state or polluting saved scenes. Native MRML camera,
slice, crosshair, and display nodes already provide the required behavior and
avoid duplicate rendering pipelines.

## 2026-08-11 — Assisted surface-derived root targets retain the trajectory contract

Status: implemented as a research initializer and Slicer-native synthetically
verified; representative-tooth and clinician acceptance pending

Use one temporary role-owned `vtkMRMLMarkupsFiducialNode` only to collect the
clinician's one or two crown Entry clicks. It is not an alternative trajectory
representation. Resolve crown/root polarity from those entries and the complete
target-tooth closed surface, estimate a rootward tooth axis without assuming a
world axis, and analyze several root-side surface caps. For the two-root V1,
use deterministic transverse two-cluster separation and pair the resulting
rootward targets to the entries by minimum transverse travel.

Create ordinary two-point `vtkMRMLMarkupsLineNode` trajectories in world RAS,
with the existing target-segmentation, target-segment, target-bounds, color,
name, and downstream guide contracts. Persist the entry-markup reference and
analysis metrics on every created trajectory, leave all generated trajectories
unlocked, and label them `RequiresManualVerification`. Never overwrite an
existing target-tooth trajectory set; regeneration requires deliberate deletion
of the old set. Scene save/reload must preserve both the input markup and every
source reference.

During entry placement, temporarily isolate only the selected target-tooth
mask, force its immutable target bounds visible, center the slice views, and
fit the visible 3D target. Restore the exact prior segment and bounds visibility
on explicit exit, generation, save, module exit, or scene close.

Reason: full ToothFairy tooth surfaces can initialize rootward geometry but do
not identify a pulp/canal centreline, dentin clearance, perforation risk, or a
safe drill target. The estimator therefore reduces placement effort without
creating a second planning truth or disguising the result as clinically
approved.

## 2026-08-11 — Four-dock robot rail geometry waits for an approved local-frame contract

Status: superseded in implementation scope by the 2026-08-12 provisional
research geometry; final mechanical approval remains blocked

Place docking/registration geometry after approved one/two-trajectory planning
and before template fusion. Define a persisted target-tooth local frame from a
clinician-accepted crown/occlusal reference plane and target-tooth centroid;
never substitute world X/Y/Z. The requested assembly contains four hollow dock
features around the target, with top faces coplanar/tangent to that reference
plane, a shared depth control by default, and an explicit unlock for four
individual depths. Keep registration-landmark semantics separate from the
intraoral robot's mechanical docking semantics even if both consume the same
frame. Feed the resulting replaceable docking assembly into the existing
clearance → reinforcement → shell union → channel-restoration pipeline.

Do not freeze final geometry until the mechanical team resolves whether
`15 mm` means radial centroid-to-dock offset, feature length, or both; whether
`1 mm` is the bore or outer diameter; required wall thickness, tolerances,
four-hole layout, depth sign/reference, material/process limits, and the actual
rail/channel mating profile. Also resolve the kinematic fact that one fixed
robot Z axis cannot align simultaneously with two non-parallel trajectories:
the system needs a per-trajectory docking pose, an angular adjustment, a
parallel-trajectory constraint, or separate assemblies.

Reason: these unresolved values change fit, strength, robot homing, and the
meaning of Z-only drilling. Encoding plausible-looking defaults now would turn
an architectural placeholder into misleading manufacturing geometry.

## 2026-08-11 — CRD is a functional display path, not a GPU acceptance path

Status: accepted and developer-verified for container GUI display

Launch DENTO Workflow from a terminal inside the current Chrome Remote Desktop
session so the existing launcher inherits its dynamically assigned X11
`DISPLAY`; do not hardcode `:0` or a prior CRD display number. Continue using
the launcher's scoped `xhost` grant/revoke and Compose recreation behavior.

Treat CRD's current `llvmpipe` renderer as sufficient for functional and visual
workflow verification only. Hardware-rendering, responsiveness, and FPS claims
must come from the physical Ubuntu graphical session exposed through GNOME
Desktop Sharing/RDP, with the renderer identity explicitly checked.

Reason: the developer verified that the containerized Slicer window appears in
CRD on `:20.0`, but software rendering cannot validate the Intel iGPU path or
the performance bottleneck that motivated the original rendering work.

## 2026-08-11 — Shared Windows/Linux launcher contract; SlicerROS2 stays Linux

Status: accepted; Ubuntu runtime verified, Windows runtime acceptance pending

DENTOWorkflow's Slicer/MRML and geometry code remains one cross-platform
implementation. Machine differences are isolated behind a shared launcher
contract containing execution adapter, absolute Linux backend Python,
Slicer-visible artifact root, explicit device, and the WSL distribution only
when applicable.

- Windows 11 uses native Windows Slicer and the `wsl` process adapter. The
  tracked PowerShell launcher validates and supplies WSL2 inference settings.
  Docker is not required for Steps 0–5.
- Ubuntu uses the `local` process adapter inside the pinned Linux SlicerROS2
  Docker profile and the current CPU backend.
- Inference dependencies remain outside Slicer's embedded Python on both
  platforms. Launcher machine paths are not the MRML identity contract.

Upstream SlicerROS2 1.2 currently targets Ubuntu 24.04, ROS 2 Jazzy, and
source-built Slicer 5.10/5.12; its published CI image is Linux. Therefore
native Windows SlicerROS2 is not claimed. Docker Desktop/WSL2 hosting of the
Linux GUI image remains an experimental future profile, while ROS-integrated
work uses the verified Ubuntu runtime.

## 2026-08-11 — Active Ubuntu backend owns a matched CPU segmentation stack

Status: implemented and verified on the bundled public CBCT fixture

Keep PyTorch, torchvision, TotalSegmentator, nnUNet, OpenVINO, and DENTOBOT
inference in the external host Conda environment that is mounted read-only
into the SlicerROS2 container. Install PyTorch 2.10.0+cpu and torchvision
0.25.0+cpu together from the official PyTorch CPU index; a generic torchvision
wheel is rejected even when package metadata appears compatible. Keep Slicer's
embedded Python limited to UI/MRML responsibilities.

Use `/workspace/data/model-cache/totalsegmentator` as the launcher-managed,
cache-only TotalSegmentator home. Compose receives it explicitly as
`TOTALSEG_HOME_DIR`; the launcher validates the exact top-level dependency
versions, cache directory, and CPU health before starting the workflow. No
implicit CUDA fallback, embedded-Python installation, or runtime model
download is allowed.

Reason: the formerly minimal Conda backend passed transport checks but could
not segment. Installing only CPU PyTorch was also insufficient: nnUNet's
trainer discovery imports torchvision through `timm`, and the generic wheel
lacked the matching compiled `torchvision::nms` operator. The matched CPU pair
completed the repository's public fixture with valid output geometry and
labels while preserving the existing external-process architecture.

## 2026-08-11 — Trajectory/crown-cap support-plane boundary initializer

Status: implemented and Slicer-native verified; clinician/phantom acceptance
pending

Keep the editable closed Markups curve as the authoritative final Step 5A
support boundary, but initialize it from a locked derived Markups plane. Use
Entry→Target as the crown-to-root polarity and insertion frame; never interpret
“horizontal” as world Z. Place the plane at one visible scalar depth from Entry
and initialize its tilt from a PCA plane fitted to configurable crown-side caps
of all selected target/support surfaces. Fall back to the trajectory-normal
plane when the fit is degenerate or implausibly oblique.

Cut each substantive selected tooth surface independently, project every valid
intersection into the fitted plane, form one deterministic planar outer convex
envelope across interdental gaps, resample it, and lift it back into world RAS
as the editable curve. Raw disconnected cutter contours are not treated as an
already connected guide boundary. Persist explicit plane→draft and
plane→trajectory references plus source geometry, depth, cap percentage,
polarity, and fitted orientation attributes. A change to any input makes the
boundary/preview and descendants stale.

Reason: CBCT tooth segmentations are disconnected and do not provide a reliable
gingival margin. The plane supplies a reproducible one-control initializer and
the connected envelope removes the need to manually bridge every tooth, while
the editable curve preserves clinician correction. The current 3 mm depth and
10 percent crown-cap fraction are research defaults only; they must not be
presented as gingival detection or clinically validated mounting parameters.
Registered optical surface data remains the preferred future source for true
visible crown/gingival geometry.

## 2026-08-11 — Directional undercut blockout and partial terminal-tooth latches

Status: implemented and verified on synthetic geometry plus the saved
representative Scene_5b; clinician/phantom fit acceptance pending

Treat normal-based undercut coloring as a diagnostic preview, not as the
removability operation. Build the fitting exclusion as a cropped height field
in the explicit insertion/removal frame. Use substantive closed surfaces from
the authoritative segmentation's same-arch teeth as collision-only anatomy,
including nearby unselected teeth; these surfaces may remove impossible
interproximal material but must never become patient-contact surfaces. Apply a
configurable transverse-only closing distance to block narrow interdental and
terminal embrasures without closing along the insertion axis.

Define the two ends of a mapped support span from the visible-patch centroids
projected perpendicular to insertion direction, then use PCA to avoid assuming
world X/Y/Z follows the dental arch. For each non-target terminal tooth, retain
only the configured inward fraction (50 percent research default) and persist
its world-RAS half-space. Apply the same half-spaces to the contact preview and
again after boundary-bridge union and shell closing, so downstream processing
cannot regrow the removed outer end. If the target itself is terminal, preserve
it and clip only the opposite non-target end; fewer than three mapped teeth do
not receive an automatic terminal clip.

Reason: SlicerFSP's RegisterModule identifies undercut-facing normals and
hollows/unions the result, but uses hardcoded world-axis choices and does not
provide a complete automatic seating solver for disconnected CBCT tooth
segments. DENTOBOT needs adjacent-tooth collision awareness, explicit
insertion-frame blockout, and controlled terminal latches while retaining the
clinician-selected visible surface as the only fitting basis. The current
clearance/relief/coverage values remain configurable research defaults and
require phantom and clinician validation.

## 2026-08-11 — Trajectory-directed per-tooth support-side selection

Status: implemented and Slicer-native synthetically verified; representative
anatomy acceptance pending

Do not classify the desired visible support patch by one global Smaller/Larger
surface-area choice. Entry→Target on the currently selected complete trajectory
for the Step 5A target tooth is the default crown-to-root and Approach→Seat
direction. Its opposite is the crown/removal direction. Evaluate both Dijkstra
clip candidates independently for every addressed tooth and retain the
candidate with the greater area-weighted displacement in the crown/removal
direction. Apply the same vector to all selected supporting teeth without
assuming world X/Y/Z.

Expose only a compact, off-by-default **Reverse polarity** override. It swaps
Entry/Target direction for all target/support teeth and is persisted as an
explicit parameter and geometry snapshot. The visible-support model references
the source trajectory; a locked, non-selectable `TemplateInsertionDirection`
line is derived automatically for downstream undercut/blockout processing.
Trajectory edits, trajectory selection changes, or polarity changes make the
preview and descendants stale until regeneration.

Count selected teeth from stable authoritative segment IDs, not connected mesh
components. A tooth segment may contain extra disconnected islands. Assign the
boundary to its source tooth first, select the island most strongly addressed
by that tooth's boundary samples, and report other islands separately as
diagnostics. They must not inflate a three-tooth selection into six “teeth.”

Reason: crown-patch area changes with tooth size and boundary height, so the
clinically intended side can be the smaller candidate on one tooth and the
larger candidate on another. Trajectory direction supplies a consistent,
already-planned anatomical polarity, while the explicit reversal covers an
exception without adding another routine manual direction-placement task.

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
tooth. The boundary is allowed to address only a subset of the disconnected
surfaces in the draft model: preserve one selected patch per successfully
addressed tooth, explicitly orient its normals away from the source closed
anatomy, and report untouched or unmappable surfaces as visible omissions.
Reject the operation only when no valid patch can be extracted. This keeps the
preview exploratory without silently presenting omitted teeth as selected.

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

Individual selected teeth do not provide the connected gingival/base mesh that
SlicerFSP assumes. Step 5B therefore derives a separate lifted closed collar
from the clinician's continuous support loop and unions it with the per-tooth
shells. The collar is structural, lies on the removal side, and is
re-subtracted against the directional blockout so interdental spans do not
become unintended fitting/contact surfaces. An open or non-manifold Dynamic
Modeler Hollow result remains diagnostic provenance, not an accepted solid;
the cropped voxel path reconstructs it from the validated fitting-surface
distance band and still requires one connected watertight output.

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

## 2026-08-21 — External ownership for Step 6 ROS/MoveIt

Status: accepted for simulation

The desktop launcher, not embedded Slicer Python, owns the ROS graph and
process lifetime. The Slicer adapter is limited to a versioned readiness
subscriber, MRML robot setup, simulated joint publication, planning-scene
publication, and planning requests. Previous Slicer-side subprocess launch,
process scanning, ROS CLI polling/cache, and dynamic module-path mutation are
retired.

Reason: the older bridge mixed UI state, Python-runtime isolation, process
lifetime, graph discovery, and robot control. Keeping ROS external produces one
observable state machine, prevents duplicate joint publishers, and keeps the
medical UI responsive and testable.

## 2026-08-21 — MoveIt is plan/preview only

Status: accepted for draft research simulation

Use `dentobot_arm` with KDL and OMPL for Cartesian planning, but set
`allow_trajectory_execution=false` and provide no controller, transmission,
`ros2_control`, hardware driver, or execution call. Manual controls and planned
waypoints update visualization through one simulated `/joint_states` source.

Reason: the current goal is design reach/flexibility testing in an open-mouth
phantom. Planning is useful; physical execution is neither required nor
authorized.

## 2026-08-21 — Provisional TCP and draft collision contract

Status: provisional

Add `dentobot_tool_tcp` at the CAD burr-link origin with +Z aligned to the
spindle axis. Publish Step 6 phantom, teeth, docking, and guide surfaces in the
`base_link` frame, retain exact robot meshes, exclude adjacent pairs only, and
retain MoveIt's 5 mm robot-world padding, and enforce an explicit 5 mm measured
self/world clearance in the manual command guard. Retain the original AABB
checker as a fast MRML-only fallback.

This contract supports design iteration only. It must be replaced or calibrated
before metrology, tool-tip accuracy, head-mount contact allowances, continuous
swept-volume safety, hardware motion, or clinical claims.

## 2026-08-21 — Gate simulated joint commands outside Slicer

Status: accepted for draft simulation

Route every manual or preview joint candidate through the external
`dentobot_collision_guard`; do not publish the candidate directly as robot
state. Interpolate from the last accepted vector with maximum increments of
1 degree for revolute joints and 0.5 mm for prismatic joints. At every sample,
use the MoveIt RobotModel/PlanningScene and FCL-backed collision environment to
check URDF limits, exact collision, self distance with the SRDF Allowed
Collision Matrix, and robot-world distance. Require at least 5 mm; on failure,
retain and republish the last accepted vector and return a versioned structured
status to Slicer.

Reason: MoveIt provides robust collision primitives and planning-scene
functions, but a UI slider is not automatically a planned path. Directly
publishing slider values could jump through an invalid intermediate pose, and
generic robot padding alone does not establish a measured 5 mm self-clearance
contract. This gate reuses MoveIt's model rather than adding another kinematic
or geometry implementation.

KDL remains the runtime IK plugin. The URDF/SRDF and provisional TCP define the
chain; no Denavit-Hartenberg table or symbolic inverse solution is maintained
in DENTOBOT code. This reduces duplicate logic, but it does not infer incorrect
CAD axes, physical zero offsets, joint limits, or a calibrated tool center
point. Those inputs remain engineering/calibration responsibilities.

## 2026-08-21 — Clean normal launch by restarting, not routinely recreating

Status: accepted for the dedicated development container

Every normal graphical launch first performs a bounded restart of the existing
running `dentobot-slicerros2` container, then lets Compose reconcile it. This
terminates stale Slicer, ROS 2, MoveIt, and test descendants while preserving
the container filesystem and bind mounts. A stopped container is started
without a preliminary restart. `--check-only` remains non-destructive and
refuses to proceed when an active graphical or simulation session is present.

Reason: force-recreating on every launch also removes stale processes, but it
needlessly discards mutable Slicer runtime state and triggered another `psutil`
installation during the rehearsal. Restarting the exactly named, dedicated
container gives the desired empty process namespace at lower startup and
network cost. Compose remains responsible for necessary recreation when the
image or service configuration changes. Because restart terminates the current
GUI, the launcher must warn operators to save open Slicer scenes first.

## 2026-08-21 — Case scenes exclude live SlicerROS2 adapter state

Status: accepted and verified in the pinned Slicer 5.10/SlicerROS2 environment

Treat the SlicerROS2 default node and DENTOBOT-owned ROS subscribers,
publishers, and MoveIt collision proxies as runtime resources rather than case
content. Mark them `SaveWithSceneOff`, stop Step 6 preview, disconnect the
Slicer-side robot, and shut down the adapter before MRML scene deletion. After
scene close/import, reattach the existing SlicerROS2 default node to the active
scene before the workflow recreates its status subscriber.

The pinned SlicerROS2 implementation retains a stale publisher/subscriber
reference because its removal code addresses the reference count as an index.
The Python bridge therefore removes the exact adapter-owned reference ID after
the upstream deletion call. It does not remove unrelated or valid ROS nodes.

Reason: Step 0 New Empty Case and Load Saved Scene replace the MRML scene.
Serializing or retaining live ROS wrapper nodes across that boundary made saved
MRBs depend on a detached default ROS node and allowed callbacks/wrapped VTK
objects to survive teardown. Case geometry and workflow parameters remain
persistent; external ROS process lifetime remains launcher-owned.

Amendment after active-robot reproduction: the default ROS node is a
process-owned singleton retained by case-level `Clear(0)` and remains excluded
from save. Motion Control is quiesced before native robot removal, and the
upstream stale final subscriber-reference slot is removed explicitly. DENTOBOT
does not use upstream deferred MoveIt obstacle publish/remove callbacks because
they retain native wrappers beyond scene or module lifetime. Saved runtime
`Ros2MotionControlActive` flags are cleared when no live robot exists.

Step 6 import and motion planning also revalidate trajectory coordinate/lock
state, current and confirmed Step 4C docking geometry, and current verified
Step 5C template geometry. A saved boolean cannot override stale upstream
lineage.

## 2026-08-22 — Adapt generic Motion Control; sample workspace in joint space

Status: accepted for simulation-only design testing

Keep SlicerROS2 as the generic robot/MoveIt provider and implement DENTOBOT
semantics in a reversible bridge adapter. Current and goal robot roots inherit
the same placed base. MoveIt readiness is detected rather than operator
toggled; `dentobot_arm` and the provisional `dentobot_tool_tcp` are fixed for
this robot; IK and planning outcomes are visible; Execute is unavailable.

Compute the draft workspace by deterministic joint-space sampling plus URDF
forward kinematics, not by repeated random IK. IK answers reachability for a
requested pose and remains the correct target-control operation. A Halton
sequence gives repeatable coverage of all six task ranges without the
combinatorial cost of a Cartesian grid. Filter the visualization with the
coarse 5 mm AABB rule and provisional TCP/environment distance, while keeping
MoveIt/FCL authoritative for every ROS-active candidate or planned path.

Exclude exactly the two persistent CAD-AABB false-positive pairs documented in
the description package from the coarse fallback. They are not added to the
SRDF Allowed Collision Matrix: exact geometry has already accepted a nonzero
test pose, whereas their axis-aligned boxes reject every sample. This preserves
a useful draft cloud without converting a bounding-box artifact into a robot
collision-policy claim.

## 2026-08-22 — Support anatomy precedes docking; Elements is scene-wide

Status: support-order portion accepted; flat inventory and automatic
volume-render creation superseded by the 2026-08-24 grouped Views decision

Split the former Step 5A UI responsibility. Step 4B now owns same-jaw support
tooth selection and the complete world-RAS support-anatomy draft. The former
Step 4B docking stage becomes Step 4C. Step 5A retains only visible erupted
support-surface definition and refinement. Existing MRML role names and
parameter references remain stable for saved-scene compatibility; visible
node step prefixes are refreshed by role.

Step 4C schema v4 requires and directly references a current Step 4B draft.
Its collision screen orders the selected supports first and then retains all
other same-jaw whole teeth as conservative obstacles. It records support IDs
and the source-draft revision; changing or regenerating support anatomy marks
the docking assembly and downstream fusion stale. This makes the dependency
explicit without weakening collision scope or changing world-RAS geometry.

Make the Elements viewer available at every workflow stage. Inventory every
segment in every segmentation individually, every user-facing displayable
MRML node, and a distinct 3D volume-rendering toggle for each scalar volume.
Presets remain display-only and restore exact prior state across save handling;
geometry, mask voxels, references, coordinate frames, and validity are not
changed by viewing. This removes step-dependent blind spots, including the
inability to compare full CBCT volume rendering with the Step 6 robot.
