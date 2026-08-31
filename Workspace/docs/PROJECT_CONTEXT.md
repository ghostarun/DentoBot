# DENTOBOT Project Context

> Cross-platform note (2026-08-11): product and safety decisions are shared.
> Native Windows Slicer + WSL2 inference and Ubuntu SlicerROS2 + direct Linux
> inference now use one explicit launcher contract. Ubuntu is runtime verified;
> the new Windows launcher still requires Windows 11 acceptance.

## Project goal

DENTOBOT is an academic engineering prototype for a streamlined dental
image-guidance workflow. It should guide a researcher through case imaging,
AI-assisted anatomy extraction, trajectory planning, registration,
navigation, and eventual robot integration without exposing the full breadth
of the standard 3D Slicer interface.

The project is built **on** Slicer rather than by reimplementing Slicer.
Slicer supplies the medical-image application framework; DENTOBOT supplies
the focused workflow, domain behavior, external compute adapters, and later
custom branding.

## Product and module naming

- `DENTOBOT` is the parent product, extension project, and future custom
  Slicer application name.
- New Slicer modules use `DENTO` plus PascalCase. The first module is
  `DENTOWorkflow`; future independent modules may include
  `DENTOSegmentation`, `DENTORegistration`, and `DENTOTrajectory`.
- Human-facing titles may add spaces, such as `DENTO Workflow`.
- The current workspace directory and disabled legacy scaffold retain older
  names for traceability; they do not define the product identity.

## Research status

- The software is for research and architecture development only.
- The current Ubuntu phase is conceptual system design and medical-imaging
  workflow development in 3D Slicer.
- No robot hardware is currently available or connected.
- It is not a medical device or validated clinical navigation system.
- AI outputs require human review and independent validation.
- Planned trajectories do not authorize drilling.

## Active Step 6 stabilization checkpoint — 2026-08-29

Priority-0 source implementation now separates a diagnostic Manual Simulation
Base from the deferred physical forehead/mount problem, audits exact
per-segment collision payloads against the guard's monitored MoveIt scene,
retains bounded partial-path evidence with first-invalid classification, and
uses explicit free-space, strict-axis, terminal-contact, and drilling stages.
The 2026-08-31 runtime-first continuation also makes 6.1 own ROS/scene
bootstrap, plans and guards any different current-to-Home transition in 6.2,
and makes 6.3 persist MoveIt FK/static-valid samples separately from a bounded
Home-connectivity classification. The latest focused native/UI build and
static gate passed, but the checkpoint is not yet operator-runtime accepted;
no hardware or execution path is enabled.

The current renovation is now locked to one action owner per substep. 6.1 alone
owns Connect/Disconnect, runtime diagnostics, and collision-scene audit; 6.4
is confirmation-only. The earlier shared card that displayed those runtime
actions in both substeps was an incomplete presentation refactor, not a second
accepted connection path. Source has been split and the hidden XML runtime
buttons are disabled. The expanded native/UI batch passed the isolated
`slicer_ros2_module` rebuild, four-module Python syntax check, and both
repository whitespace/conflict checks; it remains operator-runtime-unverified.
- Robot execution and safety require a separate control architecture,
  hazard analysis, and verification program.

## 2026-08-24 native Step 6 placement-to-task checkpoint

Step 6 is now one seven-gate simulation workflow inside DENTOWorkflow rather
than a handoff to the generic Motion Control module. It restores only persistent
operator intent: case/trajectory lineage, the robot-base state, optional
provisional forehead proxy, Task Home, reviewed assisted limits, immutable task
confirmation, and display preferences. Live ROS/TF robots, goal controls,
plans, publishers/subscribers, guard sessions, and connection flags remain
transient and are rebuilt after an explicit gated Connect.

The operator can explicitly enable one display-only CBCT volume renderer and
review CBCT/masks, robot, guides, trajectory, mount plane, goal, and optional
curved forehead envelope together. Renderer creation and appearance controls do
not change voxel data or IJK-to-RAS. The forehead envelope and current
`dentobot_drill_tip_provisional` frame are visualization/design inputs, not
registered anatomy or a physically calibrated TCP.

The external MoveIt guard now distinguishes strict approach, terminal Entry
contact, and drilling preview. Intentional contact is limited to the burr and
selected target tooth inside the confirmed Entry-to-Target corridor; every
other contact, wrong/stale task, corridor escape, overshoot, self-collision, or
joint-bound violation remains rejected. Hardware homing, controller ownership,
force/stop behavior, powered motion, drilling, and Execute remain unavailable.

## 2026-08-28 Step 6 stabilization direction

The immediate robotics objective is now trustworthy diagnosis rather than
planner success on one retained case. In order, DENTOBOT will audit the exact
per-segment collision geometry and transforms supplied to MoveIt, expose
structured last-valid/first-invalid candidate diagnostics, and implement three
explicit simulation stages: strict free-space motion to PreEntry, strict axial
approach to Entry with a narrow terminal contact tolerance, and guarded
Entry-to-Target drilling. Diagnostic evidence is persistent; active ROS/MoveIt
objects remain transient.

The recovered post-stabilization roadmap preserves three distinct study
increments. F0 manually aggregates reviewed single-attempt evidence into an
evidence-only `.dentostudy`; F1 automatically evaluates every eligible
trajectory in the active case at one reviewed base without animation or
execution; F2 compares trajectory × base pose only after Track E supplies a
stable base contract. Case geometry and the current attempt remain in
`.dentocase`; studies reference source package identity and never restore
geometry or ROS runtime state.

The existing base-derived mount plane cannot be interpreted as forehead truth
or a robot mount interface. Its snap path is quarantined for this work and
immediate trials use a clearly labelled manual simulation-base pose. Full
mount-frame design, automatic base optimization, system-wide frame
formalization, and physical registration remain separate later work. The
retained partial Cartesian result is therefore a negative diagnostic fixture,
not yet evidence of collision, mechanical workspace, or placement failure.

## Developer context

The developer has prior experience with standalone Python/C++, Qt, ITK, VTK,
and WSL2/Conda/CUDA inference deployments, and is learning:

- Slicer scripted modules and extension packaging
- MRML scene and node design
- qMRML widgets and parameter nodes
- module-to-module orchestration
- Slicer-to-WSL process and medical-image exchange
- Slicer-based custom application packaging

Changes should remain educational. Explain ownership, coordinate systems,
data flow, and Slicer-specific choices rather than generating opaque code.

## Product form

### Development form

An installable DENTOBOT extension loaded by an official Slicer build.
`DENTOWorkflow` becomes the user-facing home and progressively adds only the
controls needed for the current research workflow. Standard Slicer views
remain the visualization surface. Separate DENTO modules are introduced only
when a domain boundary becomes independently reusable or testable.

### Final research-application form

A custom Slicer-based application, produced only after the workflow is
stable, with:

- DENTOBOT branding and home workflow
- a reduced set of bundled/visible modules
- simplified menus and toolbars
- standard Slicer MRML, rendering, DICOM, and extension infrastructure
- an external inference runtime
- an external robot-control runtime

This is not achieved by copying Slicer code into a standalone Qt application.
It is achieved using supported Slicer custom-build mechanisms.

## Target workflow

1. Start or open a case.
2. Import and load CBCT DICOM data.
3. Inspect image geometry and data quality.
4. Run dental segmentation in the external inference backend.
5. Review and correct teeth, pulp/canal, jaw, sinus, and related labels.
6. Define, verify, and approve one or two Entry-to-Target trajectories using
   either manual placement or the optional assisted initializer.
7. Select same-jaw support teeth and generate a traceable full-anatomy support
   draft before any docking geometry is placed.
8. Derive the target-tooth/occlusal frame and generate four provisional
   robot/registration docks using the selected support anatomy first, and all
   remaining same-jaw teeth second, in the collision-aware yaw screen.
9. Select only the erupted, accessible support surfaces; establish insertion
   direction; process undercuts; and generate the patient-contact shell.
10. Fuse shell, trajectory guide, reinforcement, and docking geometry into one
   referenced `FinalPrintableTemplate` model.
11. Run the Step 5C PASS/WARNING/FAIL gate and export one atomic STL only from
    the current verified unified model.
12. Register image/planning space to the physical tooth/template and robot
    frames.
13. Calibrate tool, robot, and docking transforms.
14. Rehearse navigation and motion in simulation.
15. Connect to a robot adapter for supervised research experiments.
16. Record inputs, transforms, plans, events, measurements, and verification
    results.

The precise dental procedure and the anatomical meaning of entry, target,
depth, and safety margins must be agreed with the clinical/research team
before trajectory-planning acceptance criteria are finalized. Template contact,
gingival/cervical margin, removability, printability, and manufacturing
acceptance likewise require dentist-approved definitions and representative
validation data; a successful STL export is not clinical or fabrication
approval.

## Current PoC closure contract

The immediate objective is a bounded, defensible TRL-4 research PoC, not a
feature-complete planning product. Progress is judged by evidence that the
narrow workflow has explicit inputs, preserved world-RAS geometry, traceable
Current/Stale state, bounded failure behavior, repeatable physical output, and
measured error sufficient to connect planning to registration and robot
execution.

The near-term order is:

1. freeze the exact clinical task boundary and Template V0 assumptions;
2. run the implemented planning/template workflow on representative reviewed
   anatomy and close live usability defects that prevent that bounded test;
3. print one Template V0 and measure seating, removal, rocking, repeatability,
   critical dimensions, and docking rigidity;
4. define the complete coordinate-frame graph and the first target
   registration error experiment;
5. advance head-mounted robot, tooth-mounted robot, tool, sensing, and
   metrology lanes in parallel without allowing them to disappear behind UI
   work; and
6. build a system error budget in which measured values progressively replace
   assumptions.

Every material claim must state its evidence level: static inspection,
synthetic automated test, developer-live test, representative anatomy,
printed phantom, or clinician/clinical expert acceptance. A stronger-sounding
claim must not be inferred from a weaker evidence level.

## Major design decisions

### Reuse Slicer capabilities

DENTOBOT will orchestrate rather than recreate:

- DICOM database, import, and scalar-volume loading
- slice and 3D views
- VTK rendering and display nodes
- segmentations and terminology
- markups and measurements
- transforms and registration representation
- scene save/reopen and subject hierarchy

For routine DENTOBOT persistence, the Slicer MRB remains authoritative for
case geometry and workflow references, while a versioned `.dentocase` wrapper
adds integrity checks, workflow/coordinate lineage, and robot-resource
fingerprints. Live ROS nodes, publishers, subscribers, TF state, Motion
Control wrappers, and MoveIt proxies are never case content and must be
reconstructed explicitly in Step 6.

### Isolate heavy Python dependencies

AI inference runs in an ordinary, independently testable Linux Python package.
The initial model is TotalSegmentator's `teeth` task based on ToothFairy3.
Native Windows Slicer launches the configured interpreter through WSL2; Linux
Slicer launches it directly. Neither imports PyTorch into Slicer. NIfTI files
carry image payloads, standard output carries live status, the process exit
code carries terminal status, and JSON records reproducible result metadata.

Bridge C requires an explicit `cpu` or `cuda:0` device, rejects silent device
fallback, and requires the TotalSegmentator `teeth` and craniofacial crop
weights to be cached before Slicer launches inference. The Slicer action does
not install dependencies or download models.

The process boundary is explicit: Slicer's Python interpreter and the external
Linux Python cannot import each other's runtime objects. Slicer exports and
imports MRML-compatible data while the backend package remains independently
executable and testable across the `wsl` and `local` adapters.

### Use ROS 2 narrowly for description/simulation; retain the robot transport gate

The verified Ubuntu/Jazzy environment now owns a simulation-only
`dentobot_description` package for the supplied URDF, meshes, neutral/manual
joint states, and TF publication. The bounded manual mode moves one URDF joint
at a time in RViz so joint order, motion type, and downstream forward-TF
behavior can be checked before end-effector control is defined. A draft 5 mm
AABB warning compares non-adjacent link boxes and reports the CAD burr-link
origin for early reach/flexibility exploration. The developer-selected
photographed pose is the current draft joint zero; the link-1 mounting face is
parallel to the RViz XY plane and positive J4 motion is reversed into negative
base X. These are design coordinates, not calibrated mechanical/encoder zeros.
This establishes a
reproducible robot-description and articulation foundation; it does not
perform exact or swept collision checking, include the head/mouth/head-mount
geometry, create a live Slicer/ROS transform bridge, solve inverse kinematics,
expose a command interface, or select the hardware-control transport.

DENTOWorkflow Step 6 is now simulation-only Robot Placement. It loads the
tracked URDF/STLs into an MRML transform hierarchy, permits manual joint
changes, and places the whole robot with an editable/snappable mount plane plus
fine local-axis controls. This is a scene-local design experiment, not
registration, a calibrated head mount/TCP, or a connection to robot state or
hardware.

For the current disposable workspace trial, Step 6 can also load aligned
BodyParts3D neurocranium, maxilla, and mandible meshes under a disposable
workspace transform that co-locates them with the robot. Four manually placed
landmarks define an approximate left/right TMJ hinge and upper/lower central
incisor pair; each landmark is placed one at a time. The mandible is rigidly
rotated about that hinge until the straight-line incisor gap is approximately
40 mm; 40 mm is the requested final gap, not a literal mandible translation.
The hinge matrix is solved in world RAS and stored in workspace-parent local
coordinates. Only one phantom set and one robot placement set are allowed. This
is a generic visual design aid, not clinically accurate jaw mechanics, anatomy,
registration, or collision evidence.

The baseline control design still uses a small transport-neutral robot adapter
and simulation-first development. At the robotics architecture gate, broader
ROS/MoveIt adoption will occur only if concrete benefits such as vendor
drivers, motion-planning integration, multi-process coordination, transform
tooling, or ecosystem reuse outweigh deployment complexity. Steps 0–5 remain
independent of ROS.

## Core Slicer data model

- `vtkMRMLScalarVolumeNode`: source CBCT
- `vtkMRMLSegmentationNode`: dental AI and corrected anatomy
- `vtkMRMLMarkupsLineNode`: planned drill trajectory
- `vtkMRMLMarkupsFiducialNode`: registration and validation landmarks
- `vtkMRMLModelNode`: tooth, bur, guide, patient, and robot geometry
- `vtkMRMLLinearTransformNode`: registration, calibration, and tracking frames
- `vtkMRMLSequenceNode`: recorded transforms and navigation playback
- `vtkMRMLTableNode` or text nodes: structured measurements and event summaries
- `vtkMRMLScriptedModuleNode`: persistent workflow selections and state

## Coordinate conventions

- DICOM is normally stored in patient LPS coordinates.
- Slicer stores scene geometry internally in RAS millimetres.
- Voxel indices are IJK; NumPy arrays are KJI.
- External NIfTI exchange must preserve its affine.
- All imported inference results must be geometry-checked against the source
  volume before becoming MRML segmentation data.
- Robot, tracker, patient, image, and tool frames must remain explicit nodes
  and transforms; frame identity must never be inferred from similar numbers.

## Data and safety constraints

- Preserve original DICOM data and maintain de-identified working datasets.
- Keep patient data local unless an approved governance plan says otherwise.
- Do not treat model confidence or visual plausibility as clinical validation.
- Slicer may issue high-level approved plans and visualize device state, but
  safety-critical control must remain in the external robot-control layer.

## Documentation and traceability

The documentation has three levels:

- `PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, and `DEVELOPMENT_PLAN.md` describe
  the accepted high-level product, architecture, and roadmap.
- `REPRODUCIBILITY_AND_TRACEABILITY.md` is the formal, controlled operating
  procedure for inference installation, environment identity, evidence
  capture, failure traces, and reconstruction.
- `changelog.md` and `logbook.md` preserve low-level development history from
  which later reports, methods sections, retrospectives, and higher-level
  documentation can be produced.

The changelog records actual repository and specification changes. The
logbook records the reasoning around them, including failed attempts and
superseded decisions. Both are timestamped, append-oriented records and must
exclude patient-identifying data and secrets.

The local repository remains authoritative. For cross-chat project context,
the seven Markdown files in `docs/` are mirrored as raw `.md` files in the
connected Google Drive folder `IITM Dentobot/docs`. Changelog/logbook update
requests include an in-place Drive sync of the corresponding files and any
other design documents changed in the same batch. This mirror is strictly for
documentation and never includes patient data, inference artifacts, or
credentials.

## 2026-08-21 Step 6 robot-simulation checkpoint

Step 6 now has a verified **simulation-only** ROS 2/MoveIt planning baseline.
The DENTOBOT launcher owns `robot_state_publisher`, one guarded simulated
`/joint_states` source, `move_group`, a collision-guard node, and a versioned
readiness publisher.
Slicer does not start, inspect, or kill ROS processes; it subscribes to the
readiness contract, loads the URDF, aligns `base_link` to the manually placed
forehead mount transform, submits manual joint candidates to the guard, and
requests plans.

The 2026-08-21 provisional planning frame was `dentobot_tool_tcp` at the CAD
burr-link origin. It was superseded on 2026-08-24 by
`dentobot_drill_tip_provisional`, fixed 7 mm distally with +Z aligned to the
spindle axis. It remains explicitly **not** a calibrated burr tip. MoveIt
trajectory execution, controllers, hardware
interfaces, drilling, and clinical safety claims remain disabled. The generic
open-mouth phantom and 5 mm draft clearance policy remain disposable design
checks, not patient registration or validated collision safety. Every manual
or preview joint transition is interpolated and screened with MoveIt's exact
URDF collision geometry before the accepted state reaches `/joint_states`.

The fixed workflow header now includes **Reload Module (Dev)** for rapid source
iteration. It preserves Slicer, the loaded MRML scene, the container, and the
launcher-owned ROS stack while replacing `DENTOWorkflow.py` and all
`Resources/Python/DENTO*.py` helper modules. To prevent stale callbacks and ROS
MRML nodes, it cancels active inference work and disconnects the Slicer-side
robot before replacement; Step 6 must reconnect afterward.

## 2026-08-22 Motion Control usability and workspace checkpoint

The generic SlicerROS2 Motion Control module is now adapted at runtime to the
DENTOBOT simulation contract. The grey/current and red/goal robot hierarchies
share the same Step 6 base parent, so a goal is a second joint
configuration of the mounted robot rather than a second world-origin robot.
The UI displays detected MoveIt readiness, fixes the planning group to
`dentobot_arm`, exposes `dentobot_drill_tip_provisional` even though the
SRDF has no separate end-effector group, and reports IK/plan results beside the
controls. Execute remains hidden and disabled.

Step 6 also has a separate draft TCP Workspace Explorer. It maps a
deterministic six-dimensional Halton sequence into the selected task joint
limits, evaluates each vector using URDF forward kinematics, and renders the
accepted provisional-TCP origins as a base-parented point cloud. The coarse
fallback rejects non-adjacent robot AABBs below 5 mm and TCP origins below the
configured subsampled environment clearance. Two documented CAD-AABB pairs
that overlap at every pose but are accepted by MoveIt/FCL are excluded only
from this draft box gate; MoveIt remains authoritative for ROS-active motion.
The cloud is a design-coverage aid, not an IK proof, exact mesh/swept collision
result, calibrated tool workspace, or clinical validation.

## 2026-08-24 application-shell development checkpoint

DENTOBOT now has an opt-in six-workspace application shell inside stock Slicer
while the eleven-stage interface remains the default fallback. Both
presentations use the same MRML/parameter state and backend. The shell adds
Case, Imaging, Segmentation, Drill Planning, Guide Design, and Robot Simulation
navigation, light/dark themes, and Focus/Expert mode; it is the foundation for
the later custom Slicer package, not a separate Qt application.

Step 6 UI orchestration now passes through one robot workflow façade. Legacy
and new Robot Simulation controls share the same ROS bridge, MoveIt/KDL IK,
PlanningScene/FCL collision guard, base placement, and plan-preview code. The
current vertical slice is developer-runtime verified, but normal-window
operator acceptance and the visual migration of Imaging through Guide Design
remain active. Legacy must not be removed or cease to be the default until
those parity checks and one stabilization cycle pass.
