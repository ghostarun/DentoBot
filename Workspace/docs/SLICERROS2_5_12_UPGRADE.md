# SlicerROS2 and Slicer 5.12 Upgrade Assessment

Assessment date: 2026-09-09

## Decision

Start a controlled Slicer 5.12 migration now on an isolated upgrade branch,
while retaining the accepted Slicer 5.10 image as the rollback baseline. Build
the DentoBot runtime as a thin layer on the upstream SlicerROS2 5.12 image and
merge the current upstream SlicerROS2 branch into the DentoBot fork. Do not
modify the existing 5.10 container in place, imitate selected 5.12 libraries in
the old image, or switch lab releases before the 5.12 candidate passes the
approved compatibility and workflow gates.

Use Slicer `v5.12.0` for the first candidate. It is the version explicitly
tested by SlicerROS2 1.2 and used by the upstream container. Slicer 5.12.3 is
the latest Slicer patch release observed during this assessment, but it should
be evaluated only after the supported 5.12.0 migration is accepted.

## What DentoBot changed

### Runtime image and orchestration

`Workspace/Dockerfile.slicerros2` is already a small derivative image. It:

1. inherits the upstream
   `ghcr.io/rosmed/slicer_ros2_module/ci:jazzy-slicer-v5.10.0` image;
2. installs pinned `moveit-configs-utils`, `moveit-planners-ompl`, and `xacro`
   packages needed by the DentoBot plan-only stack; and
3. adds DentoBot source, release, and pinned-SlicerROS2 OCI labels.

The Compose and launcher layer adds behavior absent from the upstream CI image:

- a persistent development container with init-based child reaping, bounded
  process count, stop grace period, and conservative host resource priority;
- host networking/IPC for ROS 2, fixed ROS domain/discovery settings, and
  host-UID/GID ownership for bind-mounted files;
- bind mounts for both source repositories, generated ROS workspace, local
  cases/run artifacts, model cache, Slicer home, and the external inference
  environment;
- host X11/DRM support, a WSLg overlay, and an NVIDIA CUDA overlay; and
- capability and identity checks in the DentoBot launcher and lab publisher.

These are DentoBot deployment requirements. They should remain a thin layer on
the new upstream image rather than being copied into or used to fork the full
upstream Dockerfile.

### SlicerROS2 source fork

The published lab manifest pins DentoBot's SlicerROS2 fork at `17f9993`. From
the common upstream base `4ef3d5b`, that commit changes ten files by 612 added
and 55 removed lines. It adds:

- explicit-start MoveIt joint planning with bounded inputs and result text;
- read-only MoveIt state-validity and explicit-state forward-kinematics calls;
- optional collision checking in MoveIt IK, colliding-body-pair diagnostics,
  and caller-supplied IK seeds;
- safer MRML/ROS node lifetime handling, including reference-based parameter
  lookup, removal ownership corrections, null guards, and robot reference
  restoration; and
- a focused ROS/MRML lifetime regression script.

Commit `49492e0` adds canonical drill-TCP FK evaluation. Four currently
uncommitted fork files add the DentoBot five-dimensional position-plus-tool-axis
IK solver, residual diagnostics, collision control, and its Python entrypoint.
Those uncommitted changes must be reviewed and captured explicitly before the
upgrade branch is considered reproducible.

## Exact upstream comparison

| Item | DentoBot state | Current upstream observed 2026-09-09 | Consequence |
|---|---|---|---|
| SlicerROS2 base | `4ef3d5b` (`testing Slicer 5.12`) plus DentoBot fork commits | `4f52f10` | DentoBot's base already postdates SlicerROS2 1.2 and its 5.12 test commit |
| Upstream distance | Fork remote still points at `4ef3d5b` | Three commits beyond `4ef3d5b` | Small integration delta |
| Runtime source code | DentoBot-specific C++/Python fork | No runtime-code changes between `4ef3d5b` and `4f52f10` | Upstream merge should not redesign DentoBot APIs |
| Container default | Slicer 5.10 base | Slicer 5.12.0 base | Primary required runtime change |
| CI | DentoBot local/runtime checks | New reusable upstream 5.10/5.12 build workflow | Useful reference; no need to copy it into DentoBot immediately |
| Documentation | Local 5.10 baseline | Updated API and limitation docs | Review for changed operational expectations |

The upstream 5.12 image manifest currently resolves to
`sha256:5724ea6fdfffb25cb502ecd09cc540ca5eeb4c46196677ec22bef30b99c8aed2`.
Release work must re-resolve and record the digest at the actual freeze rather
than trusting a mutable tag.

## Relevant Slicer 5.12 changes

Slicer 5.12 adds or fixes several areas used by DentoBot:

- GPU-transform rendering for linearly transformed 3D segmentations;
- improved segmentation material controls and multiple segmentation crash or
  transformed-statistics fixes;
- a redesigned browser for large DICOM databases and core DICOM SEG support;
- non-linearly transformed volume rendering, leaner rendering synchronization,
  and volume-property fixes;
- improved markup direction and transform visualization controls;
- clearer effective visibility for nested subject-hierarchy items;
- MRML, observer-lifetime, table, scene-view, packaging, and startup fixes; and
- VTK 9.6, ITK 5.4.6, CTK, DCMTK, Python-package, and build-system updates.

The first DentoBot candidate remains Qt 5.15 because that is how the upstream
SlicerROS2 5.12 image is built. The documented DICOM-import performance change
specific to Qt 6 therefore does not apply to this candidate. The dependency
updates and GPU segmentation path are promising, but DentoBot must measure its
own representative workflow before making a performance claim.

Slicer 5.12 is also a useful stabilization point because it retains Qt 5.15
compatibility while later Slicer development moves toward Qt 6 and may introduce
more API changes.

## Upgrade plan

### Phase 1 — preserve and reconstruct source

1. Keep the existing Slicer 5.10 image/tag/digest unchanged as rollback.
2. In an isolated worktree, create `upgrade/slicer-5.12` from the current
   committed fork state, merge upstream `4f52f10`, and preserve upstream
   history. No current upstream runtime-code conflict is expected.
3. Review and commit the current position-axis IK work separately. Produce one
   auditable fork delta from upstream and classify each patch as general
   SlicerROS2 repair or DentoBot-only API.
4. Consider upstreaming generally useful lifetime fixes later. Upstreaming is
   not a migration prerequisite.

### Phase 2 — build a clean candidate

1. Change only the DentoBot derivative image base to the upstream SlicerROS2
   `jazzy-slicer-v5.12.0` digest. Retain the existing pinned MoveIt/OMPL/xacro
   additions and DentoBot metadata.
2. Give the candidate a new development image name. Do not overwrite the 5.10
   image and do not update `LAB_RELEASE` yet.
3. Rebuild SlicerROS2 and DentoBot ROS packages from clean `build/`, `install/`,
   and `log/` products because compiled Slicer extensions cannot cross the
   Slicer/VTK/ITK ABI boundary.
4. Do not copy selected Slicer 5.12 libraries into the 5.10 image. Slicer is a
   source-built superbuild with coupled C++ dependencies, so such a hybrid is
   neither supported nor reproducible.

### Phase 3 — approved compatibility gates

Follow `AGENTIC_VERIFICATION_PROTOCOL.md` and
`Testing/verification_matrix.json`, using the cheapest sufficient check first:

1. prove image digest, Slicer 5.12.0, ROS Jazzy, MoveIt pins, graphics provider,
   and clean module/package build identity;
2. build the DentoBot SlicerROS2 fork and run upstream headless module tests;
3. verify module discovery, DENTOWorkflow construction/reload, scene lifecycle,
   ROS node cleanup, publishers/subscribers, TF, parameters, and imaging bridge;
4. verify every DentoBot fork API: explicit-start planning, state validity, FK,
   collision diagnostics, seeded IK, and position-axis IK;
5. load one reviewed representative case and verify segmentation display,
   transforms, markups, view presets, guide/template geometry, save/reload, and
   external inference exchange; and
6. run the simulation-only ROS/MoveIt readiness and bounded Step 6 workflow
   gates. No hardware motion or drilling is part of this migration.

### Phase 4 — measure before claiming performance

Run 5.10 and 5.12 on the same machine, renderer, case, scene state, and DentoBot
revision. Record startup, case load/save, DICOM import when used, segmentation
surface update under transforms, 2D/3D interaction, guide regeneration, memory,
and GPU usage. External TotalSegmentator inference is a separate process, so a
Slicer upgrade should not be credited for backend inference changes.

Correctness parity and no material workflow regression are mandatory. A speed
claim requires repeatable measured improvement; release-note relevance alone is
not performance evidence.

### Phase 5 — promote or roll back

After operator acceptance, publish a new immutable DentoBot runtime image
digest, update the SlicerROS2 SHA and Slicer version in the lab manifest, advance
the planned `stable/lab` pointer, and cut a new `lab/YYYY-MM-DD` tag. If any
correctness, lifecycle, rendering, or planning gate fails, retain 5.10 as the
lab release while fixing the isolated 5.12 branch.

## Sources

- https://github.com/rosmed/slicer_ros2_module
- https://slicer-ros2.readthedocs.io/en/devel/pages/compatibility.html
- https://slicer-ros2.readthedocs.io/en/devel/pages/getting-started.html
- https://discourse.slicer.org/t/slicer-5-12-summary-highlights-and-changelog/47540
- https://github.com/Slicer/Slicer/wiki/Release-Details
