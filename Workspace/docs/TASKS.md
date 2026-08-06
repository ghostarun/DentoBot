# Dentobot Tasks

Last updated: 2026-08-06

## Active

- Re-authenticate GitHub CLI for `ghostarun`, then publish the verified
  `codex/ubuntu-migration` checkpoint without force and create/update its
  draft pull request. The saved CLI token was invalid when checked on
  2026-08-06.
- On the next authorized interactive launch, confirm DENTO Workflow displays
  the launcher-managed backend Python and run-record root, keeps manual fields
  disabled, and can run the bounded backend health check. Static configuration
  and backend tests have passed; no Slicer GUI was launched for this change.

- Compare interaction and FPS on the original visualization workload. The
  recreated service has already passed launcher preflight, direct Intel Mesa
  rendering, `i915` render-node use, and nice level 0; only the developer's
  workload-level responsiveness confirmation remains.
- With explicit runtime authorization, run the bounded Slicer-native safe-
  deletion test for the Step 4A trajectory and Step 5A draft model. Confirm
  selective auxiliary cleanup, retained target/support/source state, MRB
  save/reload, and recreation after reload.
- Complete developer-run Slicer acceptance of Step 5A: select one target and
  any manually chosen number of distinct whole-tooth supports, create/update
  the draft support-anatomy model, save/reopen the scene, and confirm
  persistence and stale-state behavior.
- Rebuild `Infrastructure/Dockerfile.ubuntu-cpu` cleanly and prove `pip check`,
  all backend tests, Bridge A health, and the Slicer-native test class without
  mutable-container repair.
- Keep local controlled documentation and both existing Google Drive mirrors
  synchronized in place without duplicate files.
- Continue the 3D Slicer medical-imaging workflow; robotics remains
  conceptual/future scope because no robot hardware exists.
- Define the geometry-preserving CBCT/segmentation boundary; the verified
  standard ROS image bridge carries pixels but is not the medical-image
  exchange contract.

## Shelved — remaining Step 4

The accepted Step 4A assistance backlog and Step 4B dentist-focused 2D plan
are preserved in this task list and `docs/DEVELOPMENT_PLAN.md`. They are not
current implementation priorities.

- Accepted deferred Step 4A completion backlog:
  - selecting a trajectory after scene reopen restores its target tooth,
    highlight, bounds, and details from persisted MRML associations; editable
    names never determine identity, and invalid associations produce warnings;
  - ~~keep **Clear Both Points** for clearing Entry/Target while retaining the
    node, and add a confirmed **Delete Trajectory** action that removes only
    the selected trajectory and clears its workflow references~~ — implemented
    with static verification on 2026-08-04; Slicer-native persistence coverage
    is added but not yet run;
  - support multiple trajectories per tooth and show all trajectories in one
    selector, color-grouped by their authoritative target tooth; selecting a
    tooth emphasizes its associated trajectory entries and matching view
    lines while other tooth groups remain visible;
  - assign/persist a deterministic, distinguishable tooth-group color only
    after the tooth has at least one trajectory;
  - automatically name new trajectories `FDIxx-Tnn` (for example,
    `FDI16-T01`, `FDI16-T02`) using the next sequence for that tooth,
    without using the editable name as the association key;
  - enforce the Markups-line invariant of at most two control points, labelled
    Entry and Target; zero/one-point trajectories remain incomplete drafts.

## Next

- After Step 5A live acceptance, define the next research-template geometry
  increment: intended support/contact behavior, clearance, shell/sleeve
  geometry, validation metrics, and acceptance evidence. Step 5A supplies
  source support anatomy only; it is not a printable or clinically validated
  guide.
- Probe Intel NPU visibility only after the clean-image gate; do not claim
  nnU-Net dental inference without a converted and validated model path.
- Reopen the saved Ubuntu MRB in a fresh, cleanly exiting Slicer process and
  verify source reference, 54 segments, closed surfaces, review metadata, and
  CPU provenance.
- Run one bounded Bridge B regression. Run Bridge C again only if a source or
  contract change specifically requires it.
- Run the daily launcher from an Ubuntu desktop terminal and visually confirm
  that Slicer opens directly on DENTO Workflow.
- Define and test the narrow custom SlicerROS2 interface needed by the
  medical-imaging workflow before adding broader ROS scope.
- Repeat geometry validation with a de-identified representative CBCT after
  the DICOM workflow and data-governance procedure are ready.

## Blocked or unresolved

- Custom DENTOBOT SlicerROS2 interfaces, real medical-image geometry exchange,
  and transform-semantic interoperability between host Lyrical and container
  Jazzy are unverified.
- The ordinary Compose container has only the minimal Bridge B Conda runtime;
  the full CPU inference environment currently survives only in the local
  checkpoint image until the clean Dockerfile reconstruction passes.
- Real DICOM/CBCT input, UI-driven asynchronous Bridge B/C behavior in the
  ordinary Compose runtime, and anatomical accuracy remain unverified on
  Ubuntu.
- No Ubuntu workflow has yet been verified against robot hardware.
- No robot hardware currently exists in the development environment; robot
  integration remains future conceptual scope.
- The provenance of existing generated files under `ros2_ws/build` has not been
  established.

## Completed

- Installed the pinned pytest 8.4.2 test dependency in the dedicated external
  Conda backend, passed `pip check`, and ran all 13 inference tests without
  modifying Slicer's embedded Python.
- Centralized machine configuration in an untracked `.dentobot.env`; made the
  launcher export backend, environment, rendering, artifact, and workspace
  paths to Compose and DENTO Workflow; and removed production/test reliance on
  repeated host interpreter paths.
- Added automatic launcher configuration and clear local run-record guidance
  to DENTO Workflow while retaining an explicit advanced manual override and
  portable MRB state.
- Added the Git-tracked `Workspace/` layer for top-level Compose, scripts,
  active Ubuntu documentation, and agent instructions. Preserved the original
  top-level paths as relative symlinks and added a safe bootstrap plus Git
  helper.

- Recorded the initial Ubuntu host, Docker, Compose, Codex, and host ROS 2
  observations.
- Defined Windows documentation as reference-only pending explicit migration.
- Established Ubuntu-local documentation as the current development record.
- Created and verified the separate Google Drive
  `IITM Dentobot/active-development-ubuntu` mirror.
- Restored the continuous Windows-era project context, architecture, plan,
  reproducibility procedure, changelog, and renamed historical logbook into
  both the active Drive folder and local Ubuntu docs.
- Verified the pulled container image, running container, ROS 2 Jazzy package
  environment, SlicerROS2 install prefix, and running Slicer process.
- Installed the official ROS 2 Lyrical Desktop and ROS development tools on
  Ubuntu 26.04, initialized rosdep, and verified bounded C++ publisher to
  Python subscriber communication on the host.
- Verified bidirectional standard string communication and a one-way
  explicitly simulated standard transform message between host Lyrical and
  container Jazzy on the isolated DENTOBOT development domain.
- Passed all 23 upstream headless SlicerROS2 tests, including synthetic MRML
  image and point-cloud bridges, TF2, parameters, services, and QoS.
- Verified exact bidirectional synthetic mono8 image bytes between a host
  Lyrical node and a Slicer MRML scalar-volume bridge in the Jazzy container,
  then repeated the test successfully after a container restart.
- Verified a synthetic oblique, anisotropic int16 MRML/NIfTI Bridge B round
  trip through the real `dentobot_inference` backend and DENTOWorkflow
  geometry validator, including exact voxels and deliberate geometry-mismatch
  rejection.
- Added a single daily launcher that starts the Compose service and verifies
  the persistent minimal Bridge B backend in the existing
  `dentobot` Conda environment, scopes X11 authorization to the Slicer process,
  and loads DENTO Workflow from repository source.
- Repeated the complete synthetic Bridge B round trip with
  `/home/light-tarun/miniconda3/envs/dentobot/bin/python`; exact voxels,
  geometry, and the negative mismatch check all passed.
- Verified headlessly that launcher-equivalent Slicer arguments discover and
  automatically select `DENTOWorkflow`.
- Established the active DENTOBOT Git checkout at `ros2_ws/src/DentoBot` on
  `codex/ubuntu-migration`, published its checkpoint branch/tag, and retained
  the root workspace as a non-Git wrapper. This layout was extended on
  2026-08-06 so its operational text/configuration is tracked through the
  repository's `Workspace/` directory without changing the checkout root.
- Migrated the native Ubuntu CPU backend path into a preserved checkpoint
  image and verified explicit-CPU backend/Slicer happy paths on the public
  fixture, including 54 labels and MRB save.
- Closed the Slicer 5.10 process-lifecycle gate with explicit Qt ownership and
  teardown plus two consecutive health-only probes in 7.76 and 5.91 seconds;
  both Slicer/backend processes exited and no disposable container remained.
