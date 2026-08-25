# DENTOBOT Inference Reproducibility and Traceability

> Ubuntu transition note (2026-07-29): the validated execution layer below is
> the Windows/WSL2 baseline. It remains controlled historical evidence, not an
> Ubuntu installation procedure. An Ubuntu-specific validated baseline must be
> added without rewriting the earlier record.

## Document control

| Field | Value |
|---|---|
| Document status | Controlled research-development baseline |
| Applicable backend | DENTOBOT inference 0.2.0 |
| Applicable host application | 3D Slicer 5.12.2 |
| Validated execution layer | WSL2, Ubuntu, Python 3.10.20 |
| Baseline validation date | 2026-07-23 |
| Evidence level | One successful real-CBCT GPU happy-path run |
| Intended use | Research and development only |

This document is the normative procedure for reconstructing the external
inference environment, checking its identity, and retaining sufficient
evidence to trace a DENTOBOT inference run. It does not establish anatomical
accuracy, clinical safety, or regulatory compliance.

## Planned Step 6.0A anatomy/collision trace contract — accepted 2026-08-25

Status: documentation baseline only; no implementation or PASS evidence yet

The future imported-case open-mouth record must preserve enough information to
reconstruct the displayed anatomy and every simulation collision object without
using STL as a second geometry authority. Required persistent evidence is:

- source CBCT ID/geometry and reviewed segmentation ID/revision/fingerprint;
- fixed-upper and moving-lower source segment membership with segment IDs, FDI
  metadata, names, terminology, colors, point/cell counts, and bounds;
- four world-RAS landmarks, their intended source segments, placement method,
  exact-source projection residual, FOV margin, and MPR review state;
- solver/schema version, canonical hinge axis, source/target/achieved gap,
  angle, reachability result, direction evidence, and world-RAS rigid matrix;
- source/final upper-lower contact metrics plus warning acceptance and UTC
  review timestamp when applicable;
- per-segment collision manifest: stable object ID, source fingerprint,
  applied anatomy transform, world-to-robot-base transform, unit conversion,
  topology result, and explicit collision padding; and
- invalidation reason/state for any changed source segment, landmark, gap,
  hinge, base, target, attachment, or margin.

Geometry assertions must prove that source CBCT IJK-to-RAS and source segment
voxel/count/bounds evidence are unchanged; fixed upper surfaces are unchanged;
and every lower surface equals its source world-RAS surface transformed by the
accepted hinge matrix to `1e-6`. Displayed MRML surfaces and MoveIt inputs must
agree after the recorded millimetre-to-metre/base-frame conversion. Collision
surfaces must be finite, non-empty, triangulated, and closed/watertight before
sync. An implementation must reject a missing/stale/invalid required surface.

Schema-v1 jaw openings are compatibility evidence only and restore Legacy/
Stale. Derived MRML anatomy may be saved for immediate display but is validated
or reconstructed from the authoritative segmentation. ROS/MoveIt collision
objects, publishers, and connection flags are not saved. Required evidence
levels are pure/Slicer synthetic tests followed by a governed representative-
anatomy normal-window trial of `dentobot-case-step6.dentocase`; neither level
establishes clinical jaw motion, registration, calibrated TCP, or hardware
safety.

## Ubuntu synthetic Bridge B evidence

On 2026-07-31, the Ubuntu workstation completed a software-only synthetic
MRML/NIfTI round trip. This is migration evidence beneath the controlled
Windows/WSL baseline above; it does not replace the real-CBCT evidence level
or establish a complete segmentation inference environment.

Execution components:

- 3D Slicer 5.10.0 from the pinned Jazzy SlicerROS2 container
- persistent host Conda Python 3.12.13 environment at
  `/home/light-tarun/miniconda3/envs/dentobot/bin/python`
- read-only bind mount of that environment at the same path in the container
- DENTOBOT inference 0.2.0 loaded from repository source
- NumPy 2.2.6 and NiBabel 5.4.2
- no CUDA, model weights, inference, patient data, or hardware

The source MRML volume was a generated `4 x 5 x 6` int16 grid with anisotropic
`0.4 x 0.7 x 1.2` mm spacing, an oblique RAS direction, nonzero RAS origin,
known voxel values, and a recorded KJI checksum. Slicer exported NIfTI, the
standalone backend rewrote and validated it, and Slicer re-imported both
volumes. The backend reported `geometryMatch=true` and `dataMatch=true`.
DENTOWorkflow's validator accepted the matching pair and rejected a deliberate
`0.01` mm matrix perturbation. The maximum unperturbed matrix difference from
the defined IJK-to-RAS matrix was approximately `4.77e-08`.

The final persistent-runtime synthetic artifacts are under
`data/test-artifacts/bridge-b-l3V0RG`. They contain no patient data and are not
part of the Google Drive documentation mirror. The environment persists
independently of container recreation, and the launcher verifies its exact
top-level Bridge B package versions on both sides of the bind mount. It is not
a complete transitive lock and does not
include the segmentation stack. Before an Ubuntu release claim, capture a
complete dependency snapshot, establish the full inference environment, run
through the interactive asynchronous DENTOWorkflow adapter, and repeat with
governed de-identified representative imaging.

### Ubuntu launcher and test configuration update — 2026-08-06

The current Ubuntu workspace no longer stores the host interpreter and run
root in multiple scripts or MRB parameter values. The untracked
`.dentobot.env` at the workspace root supplies the exact backend interpreter
and render node. The tracked launcher derives the Conda environment directory
and workspace root, then supplies `DENTOBOT_BACKEND_PYTHON`,
`DENTOBOT_BACKEND_ENV_DIR`, `DENTOBOT_RUN_ARTIFACT_ROOT`,
`DENTOBOT_RENDER_DEVICE`, and `DENTOBOT_WORKSPACE_ROOT` to the relevant
processes. `Workspace/.dentobot.env.example` is the reconstruction template;
the populated local file must not be committed or mirrored to Drive.

Pytest 8.4.2, already pinned in
`Inference/requirements/test-validated.txt`, was installed into the dedicated
Python 3.12 backend on 2026-08-06. `python -m pip check` and all 13 inference
tests passed there. This expands test tooling only; it does not add a Slicer
dependency, segmentation stack, model cache, or clinical evidence.

### Ubuntu process-lifecycle containment — 2026-08-14

The reusable Compose service runs below Docker's minimal init, has a 512-task
ceiling, lower relative CPU scheduling weight, OOM score adjustment 500, and a
30-second graceful stop. Synthetic Bridge B no longer relies on opaque
`xvfb-run` lifecycle behavior: the tracked harness owns the exact Xvfb PID,
uses a 180-second internal process-group timeout per Slicer phase, retains a
45-second Docker-client guard, and reaps the display on every exit path.

After service recreation, launcher/backend health passed. A complete synthetic
MRML/NIfTI export, backend round trip, matching re-import, and controlled
geometry-rejection test exited 0 under the new harness. The container then
reported `/sbin/docker-init -- sleep infinity`, zero zombies, and no remaining
Slicer or Xvfb process. This verifies the bounded synthetic path, not an
overnight soak or representative segmentation peak task/memory needs.

### Ubuntu robot-description/manual-articulation evidence — 2026-08-14

The Jazzy container built and tested `dentobot_description` after adding
neutral, manual, and external joint-state modes. Five direct static tests and
the ament wrapper passed (six reported tests total). An isolated runtime probe
published one bounded nonzero value to each movable joint in turn and checked
TF from `base_link`: every upstream frame remained unchanged; revolute joints
changed child orientation without child translation; prismatic joints changed
child translation without child orientation; and the downstream `burr` frame
responded as expected. The probe emitted
`DENTOBOT_RUNTIME_KINEMATICS_PASS`.

An Xvfb graphical run loaded the package-owned manual PyQt window and RViz.
The ROS graph contained exactly the manual publisher and
`robot_state_publisher`, all six zero joint states were present, and RViz
reported no mesh/resource load errors. A separate external-state run rendered
the nonzero vector `[0.45 rad, 0.03 m, 0.35 rad, 0.02 m, 0.4 rad, 0.5 rad]`.
Both runs shut down without a residual robot-description process. Evidence is
Synthetic: it verifies software forward kinematics and mesh loading, not
physical direction, scale, calibration, collision, IK, end-effector control,
Slicer integration, controller behavior, hardware motion, or safety.

The later draft-clearance addition derives seven link AABBs from the exact
collision STL bounds, evaluates 15 non-adjacent pairs at a 5 mm threshold, and
publishes the outlines as a `MarkerArray`. At neutral it deterministically
reports two zero-distance box overlaps: `link-3`/`link-5` and
`link-3`/`pneumatic_spindle-Copy`; the CAD burr-link origin remains
`[-40.630, -193.784, 29.233]` mm in `base_link`. Six direct static tests passed.
In Jazzy/RViz, the marker topic had exactly one manual-node publisher and one
RViz subscriber; the warning panel and seven green/red outlines were visually
observed, OpenGL initialized, and shutdown left no residual process. A first
runtime attempt rejected colcon's valid symlink-installed meshes because their
resolved paths left the install prefix; URI-component validation replaced that
incorrect resolved-prefix check before the passing run.

This remains Synthetic AABB evidence. It is neither triangle-level nor swept-
volume collision proof and includes no head, mouth, patient, head-mount, cable,
or environment geometry.

The subsequent developer-selected-zero update absorbed the photographed
`[25.38 deg, 0 mm, 62.46 deg, 0 mm, 1.08 deg, -35.28 deg]` state into URDF
origins. At q=0, pure FK and live RViz report the CAD burr-link origin as
`[-49.565, 1.370, 197.675]` mm in the newly aligned `base_link`; all six
published positions are zero. Link-1's collision AABB spans `Z=-22..0 mm`,
confirming its thin mounting face is parallel to XY at the grid plane. A
positive 10 mm J4 perturbation displaces its child approximately
`[-9.997, 0.224, 0.000]` mm in base coordinates.

Seven direct tests and eight Jazzy-reported tests passed. An isolated ROS
domain six-joint TF probe emitted `DENTOBOT_RUNTIME_KINEMATICS_PASS`, including
the negative-base-X J4 assertion. The isolated manual/RViz run published six
zeros, rendered the selected upright pose and AABB markers without resource
errors, and shut down cleanly. The developer's already-open original-domain
manual session was not stopped and must be restarted to load the revised URDF.

### Slicer Step 6 robot-placement evidence — 2026-08-14

Two host-side pure geometry tests passed. They reparse the tracked URDF,
confirm seven visual meshes, verify the selected-zero CAD burr origin, assert
that +10 mm J4 moves link-5 primarily in negative base X, remove scale/shear
from a mount-plane frame, and verify local-base translation/rotation nudges.

Focused Slicer 5.10/SlicerROS2 Xvfb tests then loaded all seven STL files as
explicit raw RAS geometry, created seven link-pose transform children beneath
one base transform, verified non-empty mesh data and the parent hierarchy,
compared loaded link-1 bounds with a direct STL read, moved J4, created and
snapped an editable mount plane, applied a local nudge, saved/reopened an MRB
with the base pose and all role references intact, and deleted all 16 owned
nodes. A separate widget test exercised the Step 6 stage, seven-link
load action, opt-in keyboard shortcut gate, local nudge, mount-plane creation,
automatic shortcut disablement on stage exit, and cleanup. The existing
workflow-navigation test passed with ten entries.

A fresh extension CMake configure/default build copied and compiled the module
and derived the installed RobotDescription resource tree from the one tracked
source package. A Slicer run using only that build-tree module path resolved the
packaged URDF/STLs, loaded seven meshes, emitted
`DENTOBOT_PACKAGED_ROBOT_LAB_PASS`, and exited 0.

Evidence is Synthetic. It verifies scene geometry, synthetic MRB persistence,
and bounded UI behavior in headless Slicer. It does not verify physical-session
dragging ergonomics, save/reopen of a representative head scene,
head/mouth/mount geometry, registration, a calibrated TCP, exact or
swept collision, ROS/SlicerROS2 streaming, IK, a controller, hardware motion,
forces, or clinical safety.

### Draft open-mouth robot-workspace evidence — 2026-08-17

BodyParts3D neurocranium, maxilla, and mandible meshes were checksum-verified
and loaded together in Slicer 5.10/SlicerROS2. Two pure-Python tests verify that
the hinge transform is rigid, fixes both TMJ-axis points, reaches an
approximately 40 mm upper-to-lower incisor distance, and rejects a degenerate
axis. A focused Slicer logic test loaded three non-empty phantom models and all
seven robot models, created a pure TMJ-axis jaw transform, snapped the robot to
a provisional forehead plane, saved/reopened the MRB, and removed all owned
nodes. A focused widget test exercised the same load/open workflow through the
Step 6 UI and verified manual J4 articulation in its reversed direction.

A graphical Xvfb Slicer run then showed the open-mouth phantom and articulated
robot together, with visible Step 6 base placement controls and the separate
six-joint control window. The run emitted
`DENTOBOT_OPEN_MOUTH_VIEWPORT_PASS 40.001 7 3`; the three inspected PNGs are
local QA evidence under `/home/light-tarun/dentobot/data/` and are deliberately
not repository or Drive documentation artifacts. An initial capture exposed
that the workflow display layer had hidden all Step 6 model display nodes; the
stage update now restores robot and phantom visibility while Step 6 is active,
and the widget test covers the phantom visibility regression.

Evidence is synthetic graphical/developer-inspected, not physical-session,
representative anatomy, or clinical evidence. The 40 mm value is the resulting
incisor gap, not a 40 mm translatory mandibular displacement. Landmark choices,
forehead plane, head mount, joint vectors, collision clearance, TCP, and mouth
workspace are provisional design inputs. No ROS state, controller, hardware,
patient data, or robot motion was used.

### Step 6 evening refinement — 2026-08-17

After workspace co-location was added, applying the world-RAS hinge matrix
directly to the jaw transform (parented under the phantom workspace transform)
separated the mandible from the skull. The fix converts the solver output with
`world_transform_to_parent_local()` before `SetMatrixTransformToParent`.

Additional evening changes: progressive one-at-a-time landmark placement with a
separate clear control; strict singleton enforcement for phantom and robot
placement sets; workspace transform relocation to `(0, -150, 250)` mm RAS;
combined **Frame Phantom + Robot** framing; and suggested robot-base placement
when the phantom is already loaded.

Five host pure-geometry tests passed, including
`test_draft_jaw_opening_hinge_survives_workspace_parent_translation`. Slicer
logic tests were updated for workspace-aligned landmark coordinates, seven-node
phantom cleanup, and a 150 mm mandible/maxilla center bound after opening.
Interactive Slicer extension reload was not re-run in the physical session.

### Ubuntu CPU segmentation baseline — 2026-08-11

The same external Conda environment now contains the Ubuntu CPU inference
stack: Python 3.12.13, DENTOBOT inference 0.2.0, NumPy 2.2.6, NiBabel 5.4.2,
PyTorch 2.10.0+cpu, torchvision 0.25.0+cpu, TotalSegmentator 2.16.0, nnUNet v2
2.8.1, OpenVINO 2026.2.0, and pytest 8.4.2. PyTorch and torchvision are a
matched pair from the official CPU wheel index. The first repaired run exposed
and retained a generic-wheel mismatch as
`ubuntu-cpu-conda-20260811`; the corrected run is
`data/dentobot-runs/ubuntu-cpu-conda-20260811-02`.

The corrected public-fixture run requested and used CPU, loaded cached tasks
113, 115, and 298 from
`/workspace/data/model-cache/totalsegmentator`, completed in 329.216365
seconds, preserved 360 x 360 x 330 geometry at 0.5 mm spacing, detected 54
non-background labels, and produced 579,353 foreground voxels. The output and
run-record SHA-256 values are respectively
`9ffb207be1c2ff305b7e190bef5def5633971e721d6b6a7e122b77bc0d839364` and
`4af8b4151eb198a0e72deffe02504e42c086b384753f8a2ba8de6742b4526d1c`.
The output hash exactly matches the preserved
`ubuntu-cpu-standalone-20260731` checkpoint result for the same fixture.
`pip check`, 13 container-native backend tests, backend health, output geometry,
and label validation passed. This is execution evidence on a public fixture,
not anatomical-accuracy or clinical evidence.

The launcher passes the cache path into Compose as `TOTALSEG_HOME_DIR`, checks
the exact CPU dependency set and cache directory, and requires a successful
CPU health response. The Slicer process continues to own MRML/UI work only; it
launches the external interpreter and does not import or install this stack in
Slicer's embedded Python.

## 1. System boundary

DENTOBOT intentionally separates two Python environments on both platforms:

1. Slicer's embedded Python owns the module UI, MRML scene, NIfTI
   export/import, validation, and visualization.
2. A dedicated external Linux Python owns PyTorch, TotalSegmentator, nnU-Net,
   and inference. Windows reaches it through WSL2; Ubuntu invokes it directly
   from the SlicerROS2 container.

Both platform launchers supply the adapter, absolute Linux interpreter,
Slicer-visible artifact root, and explicit device. Windows additionally
supplies the WSL distribution. Slicer does not activate Conda, import external
packages, install dependencies, or download models.

## 2. Reproducibility levels

DENTOBOT distinguishes the following evidence:

- **Bootstrap specification:** `Inference/environment.yml` creates the named
  environment with the validated Python version.
- **Validated top-level pins:** `Inference/requirements/*.txt` record the
  directly validated package versions and the official PyTorch wheel source.
- **Machine-readable baseline:** `Inference/validated-environment.json`
  records the successful runtime, model tasks, accelerator, and run metrics.
- **Complete platform lock:** a `conda list --explicit` export plus a complete
  pip inventory captured from a verified environment. This has not yet been
  committed and remains required for formal release reconstruction.

Top-level pins improve repeatability but do not guarantee byte-identical
transitive dependencies. Do not describe the current manifests as a complete
lock file.

### 2.1 System-development evidence labels

Inference reproducibility is only one contributor to the DENTOBOT PoC. Use the
following label on every material cross-subsystem works claim:

| Evidence label | Minimum meaning |
|---|---|
| Static | Source, document, or stored-state inspection only |
| Synthetic | Automated/generated-data test with recorded command and result |
| Developer-live | Observed in the live application by the developer |
| Representative anatomy | Run on governed relevant CBCT/scene with recorded outcome |
| Printed phantom | Fabricated, seated, or physically measured output |
| Clinician/expert | Reviewed against a stated acceptance question |

Labels do not imply the levels above or below them were completed unless those
checks are recorded separately. For example, clinician preference about a
viewport does not establish dimensional print accuracy, and a synthetic
topology PASS does not establish clinical seating. Record platform, source
revision, input class, parameters, verification method, result, and unresolved
limitations beside the claim.

Once Template V0 is frozen, retain one weekly end-to-end acceptance record
covering reviewed anatomy, trajectory approval, current/stale references,
unified-template verification, MRB save/reopen, one STL, and the exact evidence
level reached. Printed, registration, or robot results must remain separate
until their own measurements exist.

## 3. Validated Windows/WSL compatibility baseline

| Component | Validated value |
|---|---|
| DENTOBOT backend | 0.2.0 |
| 3D Slicer | 5.12.2 |
| Python | 3.10.20 |
| NumPy | 2.2.6 |
| NiBabel | 5.4.2 |
| PyTorch | 2.10.0+cu130 |
| TotalSegmentator | 2.16.0 |
| nnUNet v2 | 2.8.1 |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU |
| Requested/actual device | cuda:0 / cuda:0 |
| PyTorch CUDA runtime | 13.0 |
| TotalSegmentator task | teeth, task 113 |
| Crop task | craniofacial_structures, task 115 |

The successful evidence run processed a 580 x 580 x 300 CBCT with 0.25 mm
isotropic spacing, produced 60 non-background segments, and completed in
75.232826 seconds. These values identify the evidence run; they are not
performance guarantees or accuracy claims.

## 4. Prerequisites

- official 3D Slicer 5.12.2 on Windows;
- WSL2 with the intended Ubuntu distribution;
- Conda installed inside WSL2;
- a compatible Windows NVIDIA driver available to WSL2;
- sufficient disk space for model weights and per-run artifacts;
- a repository checkout mounted into WSL.

The Windows NVIDIA driver exposes GPU support to WSL. Do not install a Linux
NVIDIA display driver inside WSL. A separate CUDA toolkit is unnecessary for
the validated prebuilt PyTorch wheel unless later work must compile CUDA code.

## 5. Environment installation procedure

Open a WSL terminal and change to the repository's `Inference` directory:

```bash
cd /mnt/e/IITM_DentaNav/DentalNav/DentalDrillNav/Inference
conda env create -f environment.yml
conda activate dentobot
```

Install the validated CUDA-enabled PyTorch wheel from the official PyTorch
index:

```bash
python -m pip install \
  --index-url https://download.pytorch.org/whl/cu130 \
  -r requirements/pytorch-cu130.txt
```

Install the validated runtime dependencies, the editable DENTOBOT package, and
the test dependency:

```bash
python -m pip install \
  --constraint requirements/validated-constraints.txt \
  -r requirements/runtime-validated.txt

python -m pip install --no-deps -e .

python -m pip install \
  --constraint requirements/validated-constraints.txt \
  -r requirements/test-validated.txt
```

`--no-deps` prevents the editable backend install from re-resolving versions
already installed from the controlled manifests. Stop and investigate any
resolver conflict rather than forcing incompatible packages.

## 6. Model-cache preparation

Run model downloads explicitly from the configured environment:

```bash
totalseg_download_weights -t craniofacial_structures
totalseg_download_weights -t teeth
```

TotalSegmentator's default cache is below
`~/.totalsegmentator/nnunet/results`. The Slicer-launched runtime is
cache-only: it must fail clearly if a required model is absent rather than
silently initiating a download.

For a formal release snapshot, record the task identifiers, cache location,
file inventory, byte sizes, and cryptographic hashes without uploading model
files to the documentation mirror.

## 7. Installation verification

Run:

```bash
python -m pip check
python -m pytest
python -m dentobot_inference health --json --require-cuda
```

Acceptance requires:

- the interpreter path is the intended `dentobot` environment;
- dependency checks report no broken requirements;
- the existing backend tests pass;
- health status is `ok`;
- CUDA is available and the expected GPU is listed.

Only tests actually run in WSL or Slicer may be reported as passed. The five
new segmentation-oriented WSL tests are currently deferred.

## 8. Slicer configuration

Configure the DENTO Workflow bridge with:

| Setting | Validated value |
|---|---|
| WSL distribution | `Ubuntu` |
| Environment Python | `/home/tarun/miniconda3/envs/dentobot/bin/python` |
| Run-artifact root | `C:\DENTOBOTRuns` |

The absolute interpreter path is authoritative. A Conda environment activated
in an unrelated terminal does not affect the process launched by Slicer.

## 9. Per-run traceability contract

Every inference uses a unique run ID and isolated artifact directory. The
schema-versioned `result.json` is the primary machine-readable evidence and
records, at minimum:

- command, run ID, timestamps, terminal status, and errors;
- backend, Python, package, model/task, and schema versions;
- requested and actual compute device and GPU identity;
- input/output paths, shape, spacing, affine, and data type;
- detected labels and label metadata;
- inference and total runtime and peak GPU allocation.

Slicer attaches namespaced `DENTOBOT.*` provenance to the imported
segmentation. The source volume, output, and result metadata must agree before
the output is retained in the MRML scene.

Run artifacts may contain patient-derived data. Keep them local, apply the
project's de-identification and retention rules, and never upload them to the
documentation mirror.

## 10. Environment snapshot procedure

After a fully verified installation, capture platform-specific evidence:

```bash
mkdir -p environment-evidence
conda list --explicit > environment-evidence/conda-explicit-linux-64.txt
python -m pip freeze --all > environment-evidence/pip-freeze.txt
python -m pip check > environment-evidence/pip-check.txt
python -m dentobot_inference health --json --require-cuda \
  > environment-evidence/health.json
sha256sum environment.yml requirements/*.txt \
  > environment-evidence/manifest-sha256.txt
```

Review the files for local paths or sensitive information before committing or
sharing them. A source-control revision identifier should be recorded beside
the environment snapshot once the project is maintained in a Git repository.

## 11. Failure trace and support bundle

When a run fails, preserve the failed run directory and collect:

- `result.json`, structured standard output, terminal exit code, and UTC time;
- DENTOBOT backend and Slicer versions;
- WSL distribution, interpreter path, and `health --json --require-cuda`;
- `python -m pip check`;
- `python -m pip show torch TotalSegmentator nnunetv2 nibabel numpy`;
- whether tasks 113 and 115 exist in the configured model cache;
- sufficient non-identifying steps to reproduce the failure.

Do not attach the input NIfTI, output segmentation, screenshots containing
identifiers, or complete run directory unless data-governance approval
explicitly permits it.

## 12. Deferred validation backlog

The successful Bridge C path is accepted as the current development baseline.
The following work is deferred, not waived:

1. execute the five segmentation-focused WSL unit tests;
2. exercise missing dependency, missing model, and unavailable CUDA behavior;
3. verify cancellation and descendant-process cleanup;
4. verify out-of-memory, malformed output, and partial-output cleanup;
5. verify MRB scene save/reopen persistence and node references;
6. establish anatomical ground truth and quantitative accuracy criteria;
7. capture a complete transitive environment lock and clean-machine rebuild.

These items do not block work on the next UI milestone, but they must be
resolved before a reproducible release or any claim of robust operation.

## 13. Change control

Material changes to Python, CUDA/PyTorch, TotalSegmentator, nnUNet, model
tasks, model files, output schema, or the Slicer/backend contract require:

1. an updated manifest or baseline record;
2. rerun health and applicable automated tests;
3. a representative inference smoke test;
4. review of output geometry and label metadata;
5. timestamped entries in `docs/changelog.md` and `docs/logbook.md`.

## 14. Primary technical references

- [TotalSegmentator repository and installation](https://github.com/wasserth/TotalSegmentator)
- [TotalSegmentator Python API](https://github.com/wasserth/TotalSegmentator/blob/master/totalsegmentator/python_api.py)
- [Official PyTorch previous-version wheels](https://pytorch.org/get-started/previous-versions/)
- [NVIDIA CUDA on WSL guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)
- [Conda environment management](https://docs.conda.io/projects/conda/en/stable/user-guide/tasks/manage-environments.html)
- [Conda environment export](https://docs.conda.io/projects/conda/en/latest/commands/env/export.html)

## 15. Step 6 ROS/MoveIt evidence procedure

The reproducible container layer is built from
`Workspace/Dockerfile.slicerros2` and tagged
`dentobot/slicerros2:jazzy-moveit-sim-20260821`. The added runtime packages are
`moveit_configs_utils`, `moveit_planners_ompl`, and `xacro`; the 2026-08-21
verified ROS package versions were MoveIt 2.12.4, OMPL 1.7.0, and xacro 2.1.1.

Run the non-GUI environment/build gate:

```bash
Workspace/scripts/launch-dentoworkflow.bash --check-only
```

For the clean-start lifecycle acceptance test, start the dedicated container,
seed a harmless long-running `sleep` process, and invoke the normal GUI
launcher. The launcher must report a bounded restart, Compose must report the
same container as running rather than force-recreated, the seeded process must
be absent, and only the expected Slicer/simulation stack may remain. After the
GUI proof, close the launcher and stop the dedicated container. Do not use this
test while an unsaved Slicer scene is open. The 2026-08-21 rehearsal satisfied
all of these conditions and ended with `dentobot-slicerros2` stopped.

With the simulation stack running, record:

```bash
ros2 topic echo /dentobot/simulation_status std_msgs/msg/String \
  --once --field data
ros2 topic info /joint_states --verbose
python3 Testing/run_dentobot_moveit_smoke.py
```

The expected status has `mode=simulation_only`, both readiness flags true, and
`joint_state_publisher_count=1`. The ROS smoke must observe J2/J4 commands,
`base_link → dentobot_tool_tcp` TF, a valid state, direct `/compute_ik` success,
a nonempty Cartesian trajectory with fraction at least 0.99, acceptance of a
clear interpolated transition, rejection below 5 mm, and preservation of the
last accepted `/joint_states` state.

`Testing/run_dentobot_slicer_moveit_smoke.py` is the embedded-Slicer acceptance
probe. Its 2026-08-21 result loaded three BodyParts3D meshes, measured a
40.0009 mm incisor gap, snapped the base to the forehead plane, moved J2/J4,
published three collision surfaces, and returned a 29-point MoveIt path with
fraction 1.0. The upstream SlicerROS2 build still exits code 1 during headless
plugin teardown after printing the successful result; treat that exit as an
open lifecycle defect, not a clean-run claim. The ordinary open-mouth MRML
regression exits zero.

The 2026-08-21 guard evidence used a 40-sample accepted transition with minimum
self distance `0.0127129535156 m`. A deliberately under-clearance vector was
rejected between `link-1` and `link-3` at `4.500000 mm`, below the `5.000000 mm`
draft minimum. Direct KDL IK for a 1 mm TCP +X target returned six joints and
MoveIt success code 1. Collision-aware Cartesian interpolation for the same
offset returned fraction 1.0 and eight timed trajectory points. The live stack
then exposed a separate MoveIt 2.12.4 SIGINT teardown segmentation fault in an
`rclcpp::CallbackGroup` destructor; this is recorded as an environment/upstream
lifecycle defect and not hidden by the successful service assertions.

For source-reload acceptance, run Slicer with a main window under the verified
SlicerROS2 environment inside the development container:

```bash
source /opt/ros/jazzy/setup.bash
source /workspace/ros2_ws/install/setup.bash
export LD_LIBRARY_PATH=/workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-loadable-modules:/workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules:${LD_LIBRARY_PATH:-}
xvfb-run -a /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer \
  --additional-module-paths \
  /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-loadable-modules \
  /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules \
  /workspace/ros2_ws/src/DentoBot/DENTOWorkflow \
  --python-script \
  /workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_slicer_reload_smoke.py
```

The 2026-08-21 Xvfb run returned
`button_visible=true`, `module_reload_success=true`,
`helper_module_reloaded=true`, and `scene_preserved=true`, then exited zero.
This proves replacement of the widget plus helper-module cache eviction and
MRML persistence. It does not prove that an active robot connection survives;
the accepted design intentionally disconnects that Slicer-side connection so
it can be recreated against the unchanged external stack.

For the Step 0 scene-replacement regression, use the same sourced ROS and
`LD_LIBRARY_PATH` environment above and replace the final script with:

```bash
xvfb-run -a /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer \
  --no-splash \
  --additional-module-paths \
  /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-loadable-modules \
  /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules \
  /workspace/ros2_ws/src/DentoBot/DENTOWorkflow \
  --python-script \
  /workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_scene_lifecycle_smoke.py
```

The probe selects DENTOWorkflow, confirms adapter ROS nodes are transient,
locks a Step 6 base transform using the pinned Slicer 5.10 display API, saves
an MRB, clears the scene, reloads the MRB, and verifies the workflow parameter
node, sentinel data, locked transform, and ROS references after both
replacements. The 2026-08-21 result printed
`DENTOBOT_SCENE_LIFECYCLE_PASS` without the former transform exception or stale
subscriber warning. The upstream SlicerROS2 VTK leak report still makes the
scripted Slicer process return 1 after the PASS marker; this is the same open
teardown-only defect described above, not a scene-replacement failure.

The active version of this probe connects and resolves the DENTOBOT URDF,
reloads the scripted module, reconnects, clears to New Empty Case, reconnects
again, and reloads the saved case. Acceptance is the
`DENTOBOT_SCENE_LIFECYCLE_PASS` marker with no process loss before it.

For the operator-supplied FDI 14 Step 6 bundle, replace the final script with:

```bash
/workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_step6_restore_smoke.py
```

This loads `/workspace/data/Slicer_Saved/SampleStudy1/test1_6_FD14.mrb` with
clear semantics, verifies that no ROS robot or active flag is restored,
fail-closes its explicitly stale Step 4C/5C state, saves/reloads a sanitized
MRB, and compares world-RAS trajectory points/length, final-template bounds and
mesh counts, and the robot-base world matrix to `1e-6`.

### 2026-08-22 Motion Control/workspace acceptance

Host verification from the repository checkout:

```bash
PYTHONPYCACHEPREFIX=/tmp/dentobot-pycache \
  /home/light-tarun/miniconda3/envs/dentobot/bin/python \
  -m pytest -q Testing dentobot_description/test
git diff --check
```

Expected recorded result: `61 passed` and no whitespace diagnostics. A
standalone 600-sample workspace probe must be deterministic; the 2026-08-22
run completed in 0.191 s, accepted 348, rejected 252 by actionable 5 mm AABB
pairs, and reported two documented coarse-box exclusions.

The real container acceptance uses the existing sourced MoveIt launch plus:

```bash
xvfb-run -a /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer \
  --additional-module-paths \
  /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-loadable-modules \
  /workspace/ros2_ws/install/slicer_ros2_module/lib/Slicer-5.10/qt-scripted-modules \
  /workspace/ros2_ws/src/DentoBot/DENTOWorkflow \
  --python-script \
  /workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_slicer_moveit_smoke.py
```

Acceptance is the JSON report before shutdown. The recorded report includes
`goal_root_matches_live_root=true`, `selected_tcp=dentobot_tool_tcp`, detected
read-only MoveIt status, hidden execution, successful +1 mm generic IK, a
25-point generic plan, Step 6 Cartesian fraction 1.0, J2/J4 at 0.02 m, and a
200-sample workspace with 116 accepted and 84 actionable AABB rejections. The
known SlicerROS2 VTK leak still causes process exit 1 after this explicit
report; do not record that scripted process as a clean shutdown.

## 16. DENTOBOT case-bundle persistence evidence — 2026-08-24

Routine case persistence uses schema-V1 `.dentocase` packages. The required
members are `manifest.json`, `scene/case.mrb`,
`integrity/checksums.sha256`, `workflow/lineage.json`,
`robot/robot-profile.json`, and `records/save-report.json`. The MRB is the sole
geometry source; the JSON records are integrity, compatibility, provenance,
and post-load validation evidence. Coordinate declarations are Slicer world
RAS in millimetres, and numerical restore comparisons use `1e-6` tolerance.
Within schema V1, saved lineage dictionaries are append-only requirements:
every saved key/value must reconstruct, while a newer reader may add keys that
an older package could not record. Lists remain exact, MRML IDs are ignored for
semantic equivalence, and a missing or changed saved value fails with its
first nested field path. This rule prevents new provenance metadata from being
misreported as geometry drift without weakening validation of saved evidence.

Host contract verification:

```bash
PYTHONPYCACHEPREFIX=/tmp/dentobot-casebundle-full-pycache \
  /home/light-tarun/miniconda3/envs/dentobot/bin/python \
  -m pytest -q Testing dentobot_description/test
```

The recorded 2026-08-24 result was `67 passed`. Tests cover round trip,
inventory and hash validation, path/duplicate rejection, serialized-ROS
rejection, deterministic portable robot fingerprints, UI/install contracts,
and the existing workflow/ROS/planning regressions.

The real Slicer evidence uses
`Testing/run_dentobot_case_bundle_smoke.py`. It opened the de-identified
operator samples `test1_5C_FD14.mrb` and `test1_6_FD14.mrb`, saved and
validated packages, reloaded them, and reproduced world-RAS trajectories,
model point/cell counts and bounds, volume geometry, segmentation counts, and
robot-base matrices to `1e-6`. It printed
`DENTOBOT_CASE_BUNDLE_PASS`. The separate
`Testing/run_dentobot_case_bundle_transaction_smoke.py` deliberately supplied
a valid archive with mismatched workflow metadata, observed post-load
rejection, restored the prior sentinel scene, and printed
`DENTOBOT_CASE_BUNDLE_TRANSACTION_PASS`.

Both scripts printed their explicit PASS marker before the pinned SlicerROS2
VTK debug-leak report made scripted shutdown return 1. Record the marker as
functional evidence but not as a clean process-shutdown result. These are
software persistence results on representative saved research scenes; they do
not validate anatomy, registration, robot accuracy, hardware safety, or
clinical use. Normal-window operator acceptance and a regenerated current
Step 5C package remain required.

## 17. Application-shell and robot-façade evidence — 2026-08-24

Presentation settings use `QSettings` keys below
`DENTOBOT/ApplicationShell`; they are deliberately excluded from MRML,
`.dentocase`, workflow lineage, and geometry hashes. Stage indices, MRML node
references, parameter values, world-RAS/mm coordinates, and existing case
transactions remain authoritative. Both GUI modes therefore exercise the same
traceable backend records.

The pure host suite returned `81 passed`. Contract coverage includes the six
workspace/stage mapping, fail-closed mode/theme normalization, presentation-
only Robot panel imports, façade degree/mm to radian/metre conversion, task
limits, rejected-joint rollback, base lock state, static bridge contracts, and
existing workflow/description regressions.

`Testing/run_dentobot_application_shell_smoke.py` constructed a real Slicer
main window, selected all six workspaces, mapped stage 5B to Guide Design,
exposed seven Robot Simulation substeps, showed the native gated cards
cards, applied both themes, toggled Focus/Expert, restored Legacy, saved a
screenshot, and printed `DENTOBOT_APPLICATION_SHELL_PASS`.

The live ROS/MoveIt smoke reported `facade_contract=true`, exactly one joint
publisher, group `dentobot_arm`, TCP `dentobot_drill_tip_provisional`, a +1 mm IK solution,
five joint-goal plan points, 29 Cartesian trajectory points at fraction 1.0,
three planning-scene obstacles, a rejected forehead-collision start, a
collision-clear 20 mm base nudge, and 116/200 accepted draft workspace samples.
The ROS-backed lifecycle test reconnected after module reload and New Empty
Case, restored the saved locked base, and printed
`DENTOBOT_SCENE_LIFECYCLE_PASS`.

The pinned SlicerROS2/MoveIt class-loader and VTK objects still produce a
nonzero process exit after explicit functional success. Tests must record both
facts: the PASS/JSON result is functional evidence, while shutdown remains an
open dependency defect. This evidence is synthetic/developer-runtime only; it
does not establish calibrated kinematics, validated clearance, hardware
execution, drilling safety, or clinical suitability.

## 18. Native Step 6 placement/task and phase-guard evidence — 2026-08-24

The current planning link is `dentobot_drill_tip_provisional`. It is fixed 7 mm
distal to the former CAD burr-origin frame and is still a provisional design
frame, not physical TCP calibration. Rebuild the changed guard and description
resources from the container workspace before acceptance:

```bash
source /opt/ros/jazzy/setup.bash
cd /workspace/ros2_ws
colcon build --base-paths /workspace/ros2_ws/src/DentoBot/dentobot_moveit_config \
  --packages-select dentobot_moveit_config
```

Host contract gate:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider \
  Testing dentobot_description/test
```

Recorded result: `95 passed in 1.27s`. Coverage includes base/home/task state
transitions and invalidation, workspace joint-vector retention and assisted
limit suggestions, phase/config schemas, seven shell substeps, provisional TCP
resources, façade/bridge contracts, and static phase-guard policy.

Focused Slicer tests recorded:

- `test_DENTOWorkflowStep6NativePlacementPersistence` passed after proving that
  Views refresh creates no renderer; explicit enable creates exactly one;
  presets/opacity alter display only; CBCT scalars, IJK-to-RAS, and mask bounds
  remain unchanged; visible case+robot bounds frame together; and proxy,
  base/home/opacities/renderer survive MRB round trip.
- `run_dentobot_step6_restore_smoke.py` printed
  `DENTOBOT_STEP6_RESTORE_PASS` for `test1_6_FD14.mrb`, including trajectory
  length `15.760533814 mm`, `29,962` template points, no restored ROS robot or
  active flag, and `1e-6` geometry tolerance.
- `run_dentobot_case_bundle_smoke.py` printed
  `DENTOBOT_CASE_BUNDLE_PASS` for `test1_5C_FD14.mrb`,
  `test1_6_FD14.mrb`, and `dentobot-step6.dentocase`. The two MRBs retained
  their truthful stale Step 4C/5C lineage. The historical `.dentocase` restored
  geometry at `1e-6` but reported the expected old robot-profile fingerprint,
  so planning stays review-gated.

The isolated ROS-domain-74 guard probe is
`Testing/run_dentobot_phase_guard_smoke.py`. It recorded selected burr-target
contact accepted in-corridor and rejection of strict target contact, non-target
contact, self-collision, wrong task, lateral corridor escape, overshoot, and
joint bounds. `Testing/run_dentobot_moveit_smoke.py` separately retained the
strict joint/clearance, TF, IK, and Cartesian baseline. No hardware, controller,
powered motion, or drilling was exercised.

The normal-window Xvfb acceptance used
`Testing/run_dentobot_slicer_moveit_smoke.py` with an isolated simulation stack.
Its final JSON recorded native Connect and Goal/IK/Plan staying in
DENTOWorkflow, hidden Execute, Views retained through expert diagnostics and
Return, coincident current/goal roots, a successful −1 mm IK target, a 55-point
goal plan, and 119/200 workspace samples. The disposable visual phantom's
forehead-tangent placement did not become collision-clear during the bounded
diagnostic search, so that report did not rerun the redundant Cartesian check;
the separate strict and phase-guard smokes remain the collision authorities.

The updated application-shell smoke printed
`DENTOBOT_APPLICATION_SHELL_PASS` with seven Robot Simulation substeps. The
scene-lifecycle probe reconnected after developer reload and New Empty Case,
then restored a saved locked-base scene and printed
`DENTOBOT_SCENE_LIFECYCLE_PASS`. Each functional result preceded the known
nonzero pinned SlicerROS2 teardown leak; no clean-shutdown claim is made.

## 19. Modular source/API checkpoint — 2026-08-25

`Testing/contracts/dentoworkflow_api.json` records the accepted public class,
method-signature, annotation, return, decorator, and parameter-field surface.
`Testing/test_modular_structure.py` reconstructs that surface across the public
entrypoint and internal mixins, rejects duplicates, checks import direction and
CMake installation, enforces the 1,500-line routine-module ceiling, and rejects
new process/network imports. The manifest proves API relocation parity; it does
not prove behavioral, clinical, or hardware equivalence by itself.

Recorded modular checkpoint evidence:

- `pytest -q Testing`: `99 passed`;
- `git diff --check`: pass;
- application shell: `DENTOBOT_APPLICATION_SHELL_PASS`;
- composable viewer: `DENTOBOT_COMPOSABLE_VIEWS_PASS` with no shutdown
  traceback after the cleanup guard;
- bounded Step 6 case import/view: `DENTOBOT_MODULAR_STEP6_CASE_VIEW_PASS`;
- five consecutive developer reloads:
  `DENTOBOT_FIVE_RELOAD_CYCLES_PASS`, with both helper and internal-module
  identities replaced on every cycle.

A current ROS-backed lifecycle rerun does not reproduce the older functional
PASS: after initial connect, module reload, and reconnect, Slicer aborts while
clearing the MRML scene. Record the earlier PASS as historical evidence and
the 2026-08-25 abort as the current unresolved Track 1 result. No warm
active-ROS scene-replacement claim is permitted until a later rerun passes.
