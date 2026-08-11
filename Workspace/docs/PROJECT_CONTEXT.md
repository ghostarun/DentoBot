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
6. Define and approve a dental drilling trajectory.
7. Assemble target/support anatomy and generate a traceable raw template shell
   and trajectory sleeve.
8. Finalize the shell with a dentist-directed plane or closed-curve margin,
   verify the retained region, and export only the current finalized shell and
   sleeve.
9. Register image space to patient/tooth space.
10. Calibrate tool and robot frames.
11. Rehearse navigation and motion in simulation.
12. Connect to a robot adapter for supervised research experiments.
13. Record inputs, transforms, plans, events, and verification results.

The precise dental procedure and the anatomical meaning of entry, target,
depth, and safety margins must be agreed with the clinical/research team
before trajectory-planning acceptance criteria are finalized. Template contact,
gingival/cervical margin, removability, printability, and manufacturing
acceptance likewise require dentist-approved definitions and representative
validation data; a successful STL export is not clinical or fabrication
approval.

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

### Defer ROS

ROS/ROS2 is neither required nor prohibited. The baseline design uses a small
transport-neutral robot adapter and simulation-first development. At the
robotics architecture gate, ROS will be adopted only if concrete benefits
such as existing drivers, MoveIt integration, multi-process coordination,
transform tooling, or ecosystem reuse outweigh its deployment complexity.

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
