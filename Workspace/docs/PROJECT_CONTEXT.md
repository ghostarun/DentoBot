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
- Robot execution and safety require a separate control architecture,
  hazard analysis, and verification program.

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
7. Derive the target-tooth/occlusal frame and generate the provisional
   trajectory guide plus four independent robot/registration docking features.
8. Select only the erupted, accessible support surfaces; establish insertion
   direction; process undercuts; and generate the patient-contact shell.
9. Fuse shell, trajectory guide, reinforcement, and docking geometry into one
   referenced `FinalPrintableTemplate` model.
10. Run the Step 5C PASS/WARNING/FAIL gate and export one atomic STL only from
    the current verified unified model.
11. Register image/planning space to the physical tooth/template and robot
    frames.
12. Calibrate tool, robot, and docking transforms.
13. Rehearse navigation and motion in simulation.
14. Connect to a robot adapter for supervised research experiments.
15. Record inputs, transforms, plans, events, measurements, and verification
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
BodyParts3D neurocranium, maxilla, and mandible meshes. Four manually placed
landmarks define an approximate left/right TMJ hinge and upper/lower central
incisor pair. The mandible is rigidly rotated about that hinge until the
straight-line incisor gap is approximately 40 mm; 40 mm is the requested final
gap, not a literal mandible translation. This is a generic visual design aid,
not clinically accurate jaw mechanics, anatomy, registration, or collision
evidence.

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
