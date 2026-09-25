# SlicerROS2 and Slicer 5.12 Upgrade Assessment

Assessment date: 2026-09-09

Implementation branch: `upgrade/slicerros2-5.12-performance` (created
2026-09-25 and reset onto the completed
`cursor-agent/dentoworkflow-debug-20260918` checkpoint, with no branch-only
commits at kickoff). This branch is the DentoBot integration lane; the
SlicerROS2 fork needs its own isolated branch/worktree. The preceding workflow,
test, and controlled-document work was committed on the prior DentoBot branch
before upgrade implementation began.

2026-09-25 source checkpoint: the fork's five dirty files were audited and
committed on `dentobot/slicer-ros2-step6-20260903` as `abb39e5`; its
`upgrade/slicer-5.12` branch begins at that same commit. A requested
collision check now fails closed when the planning scene is unavailable. The
local upstream `4ef3d5b` is already an ancestor. A fresh GitHub fetch failed
on DNS, so newer upstream state remains unverified and no merge has occurred.

Continuation: an approved network fetch resolved upstream `origin/main` to
`4f52f10`; its three intervening commits touched CI/Docker/docs, and the fork
upgrade branch merged them as `6454b1b` without changing DentoBot native APIs.
The candidate base resolved to digest
`sha256:5724ea6fdfffb25cb502ecd09cc540ca5eeb4c46196677ec22bef30b99c8aed2`.
An isolated image build first failed because two June MoveIt apt build versions
were no longer indexed; a base-image package query found current September
builds of the same `2.12.4` release. A second build passed with explicit
`MOVEIT_VERSION=2.12.4-1noble.20260903.075820` and
`MOVEIT_OMPL_VERSION=2.12.4-1noble.20260903.093406`; the Dockerfile's 5.10
defaults were retained. The resulting local candidate is
`dentobot/slicerros2:platu06-slicer512-00bb35055611` at image ID
`sha256:8a0eb790fb748d8eed3cb8f9e3749995db200026da97ec5f9de796faf1a01dc6`.
The 5.10 rollback image ID stayed
`sha256:544c5b759ccef7ce6c41157bbd7bd8b602657de367f1f6b71352de054c81b019`.
An isolated sequential colcon build, with read-only source mounts and separate
build/install/log output, passed `dentobot_description`, `slicer_ros2_module`
and `dentobot_moveit_config` in 6 min 58 s. Native modules installed under
`Slicer-5.12`; this is build evidence, not runtime compatibility or performance
acceptance.

The first approved, network-isolated headless module-reload gate emitted
`DENTOBOT_FIVE_RELOAD_CYCLES_PASS` with all five widget/helper reloads and scene
preservation valid. Slicer exited 1 on shutdown and logged retained native
ROS2/MRML objects. Treat reload behavior and shutdown hygiene separately;
`S6-U-01` owns the latter. Saved-case correctness, lifecycle, ROS/MoveIt API,
and comparative performance gates have not run on the 5.12 candidate.

Source follow-up under `S6-U-01`: fork commit `676a91c` corrected five
raw-`New()` assignments to `vtkSmartPointer`. The approved post-fix repeat
passed all five reload cycles but still exited 1: retained objects fell from
139 across 21 classes to 120 across 20, and the default ROS node disappeared.
Fork commit `a922233` then adopted the raw `CreateNodeByClass` references in
three factories and corrected a matrix construction; its isolated incremental
SlicerROS2 build passed. The candidate image retains its original source
labels; its separately mounted scratch native install contains both fixes.
The approved post-`a922233` repeat passed all five reload cycles and printed
no `vtkDebugLeaks` objects, but Slicer's launcher still reported an abnormal
exit (code 1) without a diagnostic in the captured output. Native shutdown
remains open; saved-case correctness, lifecycle, ROS/MoveIt API and comparative
performance remain open.

An approved isolated exit diagnostic reproduced SIGSEGV after the five-cycle
pass. The fault instruction address was unmapped; the captured stack returned
into `rcl_subscription_fini` immediately after `rmw_destroy_subscription`.
This points to ROS subscription teardown or unloaded code during shutdown,
without identifying the owning object or a safe correction. The three-run
diagnostic ceiling is reached; obtain a symbolic backtrace in a newly approved
bounded scope before changing teardown order.

Tarun authorized that next gate. A temporary debug image derived from the
unchanged candidate captured a GDB stack: a live String subscription is
destroyed by Slicer's late MRML scene clear, after ROS module teardown, and
faults in `rcl_subscription_fini` through `rmw_destroy_subscription` at an
unmapped instruction address. Fork commit `379d130` releases active
subscriptions on application quit and before ROS logic shutdown, and fixes
subscriber reference removal to use the matching index. Its isolated native
build passed. This source/build result still needs one approved case-free
five-reload zero-exit check; no saved-case or performance acceptance follows.

Tarun approved that one check. The five reload assertions passed again, with
no VTK leak report, but the Slicer launcher still exited 1 abnormally. Its
captured log is byte-identical to the pre-`379d130` failed run. The installed
native library contains `DisconnectSubscriptions`; the result does not show
whether its quit/destructor paths executed. Keep `379d130` as an unaccepted
source candidate. The next bounded diagnostic is a GDB breakpoint on the
cleanup method and module/logic destructors, plus the crash stack, under new
runtime approval; do not repeat an uninstrumented reload.

The approved breakpoint gate confirmed `DisconnectSubscriptions` executes in
the ROS logic destructor. The remaining SIGSEGV is a different owner: late
MRML scene cleanup destroys a `vtkMRMLROS2NodeNode` whose `rclcpp::Node`
still owns an internal `NodeTimeSource` subscription. Fork commit `0fc13ec`
destroys tracked ROS nodes before `ROSShutdown` and makes repeated `Destroy()`
a quiet no-op; the isolated native build passed. One newly approved case-free
five-reload/zero-exit check is needed before accepting shutdown.

Tarun approved that check. All five reload assertions passed and the native
SIGSEGV was no longer observed, but Slicer exited 1 with `vtkDebugLeaks`: 56
retained objects across 12 classes, mostly generated ROS message wrappers and
their nested VTK fields. Source inspection found their generator assigned raw
`vtk...::New()` results into `vtkSmartPointer` fields. Fork commit `856e927`
uses smart-pointer `New()` and regenerates wrappers when the generator changes.
An isolated native rebuild passed; inspection of 134 generated `.cxx` files
found 53 smart-pointer nested initializations and zero raw nested assignments.
At that source/build checkpoint, the generated ownership fix still needed an
approved case-free five-reload zero-exit gate.

Tarun authorized that gate. The isolated 5.12 run against the rebuilt
`856e927` install emitted `DENTOBOT_FIVE_RELOAD_CYCLES_PASS`, preserved the
scene through all five reloads, and exited 0 with no VTK leak, traceback or
abnormal-exit line. This accepts the synthetic module reload/shutdown gate.
Broader scene lifecycle, ROS/MoveIt APIs, a representative saved case, normal
window behavior and same-case performance comparison remain open; the 5.10
rollback and `LAB_RELEASE` are unchanged.

The approved isolated simulation lifecycle then completed first connect,
module reload, reconnect, New Empty Case, reconnect, disconnect and saved-scene
reload, emitting `DENTOBOT_SCENE_LIFECYCLE_PASS`. Native shutdown exited 1
with three retained `vtkMRMLROS2ParameterNode` objects, matching the three
robot connections. The first attempt stopped at an unrelated Case Foundation
lock on an empty synthetic scene; the fixture now checks the restored base
without that lock. The fork's robot description parameter allocation used raw
`New()` into a smart pointer; changing it to smart-pointer `New()` passed an
isolated native rebuild. This is a source/build correction only. One isolated
zero-exit lifecycle rerun remains the next gate; fork APIs, a representative
saved case and same-case performance remain open. The accepted 5.10 runtime
was untouched.

Tarun approved one isolated rerun against rebuilt fork `1a91963`. It emitted
`DENTOBOT_SCENE_LIFECYCLE_PASS` after every connect/reload/clear/save-reopen
step and exited 0. No VTK leak, traceback or abnormal-exit line appeared.
The watchdog saw no alert or OOM kill; Slicer peaked at 961.2 MiB RSS,
106 threads and 47 file descriptors. The simulation stack was cleaned up and
the accepted 5.10 container remained idle. This accepts the synthetic
simulation scene-lifecycle and native shutdown gate. MoveIt still reported
that it could not retrieve `file://` robot meshes and had no link geometry;
the lifecycle test does not validate collision geometry. Resolve and verify
that before any representative collision/planning acceptance. Fork APIs,
saved-case compatibility, normal-window behavior and same-case performance
remain open.

The next mesh gate traced the seven `file://` robot-resource errors to
Slicer's pinned SuperBuild curl setting `CURL_DISABLE_FILE=ON`. The fork's
Dockerfile now guards and switches this setting to OFF and caps full compilation
at three jobs. A first fresh build was interrupted at VTK object 236/11013;
a detached replacement build is in progress under the distinct
`dentobot/slicerros2:platu06-file-curl-base` tag. The focused static
robot-geometry smoke requires seven nonempty visual meshes and positive
MoveIt contact with a temporary static obstacle. Source/syntax checks have
passed; the image, native rebuild, runtime collision check, representative
case and performance comparison remain pending.

Tarun limited the running host-network build to the last full Slicer rebuild
without new approval. Use it only to test the curl FILE/symbol-interaction
hypothesis. On success, require the existing focused smoke to show nonempty
robot meshes, known positive static MoveIt contact and clean teardown; do
not promote the image or modify upstream further. Then inspect mesh URI
resolution, resource_retriever's real curl path, symbol isolation, bypass
options and smaller integration-layer fixes read-only. A `package://` rewrite
is not accepted without tracing retrieval. On unrelated SuperBuild or
dependency failure, stop this platform rebuild path and report the blocker.

## Decision

Start a controlled Slicer 5.12 migration now on an isolated upgrade branch,
while retaining the accepted Slicer 5.10 image as the rollback baseline. Build
the DentoBot runtime as a thin layer on the upstream SlicerROS2 5.12 image and
merge the current upstream SlicerROS2 branch into the DentoBot fork. Do not
modify the existing 5.10 container in place, imitate selected 5.12 libraries in
the old image, or switch lab releases before the 5.12 candidate passes the
approved compatibility and workflow gates.

Use Slicer `v5.12.0` for the first candidate. It is the version explicitly
tested by SlicerROS2 1.2 and used by the upstream container. At the 2026-09-25
research refresh, Slicer 5.12.4 is the latest published 5.12 patch. It should
be evaluated only after the supported 5.12.0 migration is accepted; its faster
large-surface picking has a reported picked-point offset regression relevant
to dental markup placement. Check that issue's disposition and test picked
point accuracy before considering 5.12.4 for this workflow.

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

### Scope and order

The purpose is a reproducible candidate and measured workflow improvement, not
an automatic cure for the current stalls. Complete the measured `S6-P2-03`
native `RemoveRobot`, case-load and shutdown investigation independently. Before
changing an image, record the current 5.10 case and Connect/Disconnect timing,
Qt heartbeat gaps, peak process/container memory, CPU, GPU and exit status.
Use the same case bytes, hardware, renderer, DentoBot source revision and
workflow actions for the 5.12 comparison. Run one Slicer/ROS session at a time.

Gate the candidate in this order: capture the fork's uncommitted native work;
pin upstream source and image digest; build in isolation; pass native/API and
saved-case correctness checks; measure performance; then consider a lab release.
The existing 5.10 runtime and `LAB_RELEASE` remain the rollback until the last
gate. Do not execute planner motion or hardware actions as part of this upgrade.

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
   Parameterize the hardcoded Slicer-5.10 paths in
   `Workspace/scripts/update-lab-release.bash` and
   `Workspace/scripts/launch-dentoworkflow.bash` for the candidate, while
   retaining the existing 5.10 launch path.
4. Do not copy selected Slicer 5.12 libraries into the 5.10 image. Slicer is a
   source-built superbuild with coupled C++ dependencies, so such a hybrid is
   neither supported nor reproducible.

The DentoBot derivative Dockerfile accepts `SLICERROS2_BASE_IMAGE`, with the
existing 5.10 image as its default. The isolated 5.12 candidate was built from
the pinned digest above. The two launcher scripts accept
`DENTOBOT_SLICER_VERSION=5.12` for versioned install cleanup paths; their
default remains `5.10`. The accepted 5.10 image and release manifest have not
been replaced.

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

Use the existing UI/resource watchdog and phase timers for Step 2 pulp-mask
preparation, Step 3A/3B open-mouth and robot placement, Step 4A assisted
trajectories, Step 4C docks, Step 5B template, and Step 6 Connect, workspace
generation and simulation-only planning diagnostics. For each, retain elapsed
time, longest Qt event-loop gap, completed/total progress counts, peak RSS,
container CPU/memory pressure and failure/exit signature. Compare repeated
representative runs where the result varies. Attribute any gain to the measured
phase; do not substitute whole-run time for UI responsiveness.

Correctness parity and no material workflow regression are mandatory. A speed
claim requires repeatable measured improvement; release-note relevance alone is
not performance evidence.

### Phase 5 — promote or roll back

After operator acceptance, publish a new immutable DentoBot runtime image
digest, update the SlicerROS2 SHA and Slicer version in the lab manifest, advance
the planned `stable/lab` pointer, and cut a new `lab/YYYY-MM-DD` tag. If any
correctness, lifecycle, rendering, or planning gate fails, retain 5.10 as the
lab release while fixing the isolated 5.12 branch.

For later upstream updates, keep the derivative Dockerfile small, pin the
upstream source commit and base-image digest, and build/publish a new immutable
candidate only when the Slicer, ROS, native module, or system dependency layer
changes. Lab machines pull the published image and matching source manifest;
they do not rebuild it. The bind-mounted Python workflow can be iterated without
rebuilding the base image when its installed package/launcher contract permits.
Every promoted image records its source SHAs, base digest, dependency pins,
build commands, and comparison result. A mutable upstream tag alone is never
the lab release identity.

## Sources

- https://github.com/rosmed/slicer_ros2_module
- https://slicer-ros2.readthedocs.io/en/devel/pages/compatibility.html
- https://slicer-ros2.readthedocs.io/en/devel/pages/getting-started.html
- https://discourse.slicer.org/t/slicer-5-12-summary-highlights-and-changelog/47540
- https://github.com/Slicer/Slicer/wiki/Release-Details
