# DENTOBOT Windows-to-Ubuntu Transfer

## Purpose

This document defines the safe transfer of the working Windows/WSL DENTOBOT
repository into the Ubuntu workstation at `/home/light-tarun/dentobot`.
It separates material recoverable from Git from runtime state that must be
reconstructed, deliberately transferred, or preserved only on the Ubuntu
workstation.

The transfer is a staged migration, not permission to overwrite the current
Ubuntu workspace. The Windows/WSL implementation was verified primarily in
3D Slicer 5.12.2. The Ubuntu container currently uses Slicer 5.10 and ROS 2
Jazzy, so compatibility must be demonstrated rather than assumed.

## Ubuntu migration status — 2026-07-31

- The remote feature hash was independently verified as
  `72da94207d33234a12f5d904c23733ff382f9e43`.
- The comparison clone remains separate at
  `/home/light-tarun/dentobot-migration/DentoBot`.
- The active Git checkout is
  `/home/light-tarun/dentobot/ros2_ws/src/DentoBot` on
  `codex/ubuntu-migration`; the existing Compose/data/settings layout was not
  overwritten.
- The selected runtime boundary is a direct local process inside the existing
  SlicerROS2 container. Slicer still owns MRML; the isolated
  `/opt/dentobot-venv` owns PyTorch, TotalSegmentator, nnU-Net, and OpenVINO.
- The Ubuntu source/UI, ordinary-Python backend, Slicer-native tests,
  standalone CPU inference, MRML import/closed surfaces, and MRB save have
  passed on a public Slicer dental CBCT fixture. Exact evidence is controlled
  in `REPRODUCIBILITY_AND_TRACEABILITY.md`.
- Slicer-launched Bridge A health and Bridge C also reached successful terminal
  results. Bridge C produced 54 imported segments and a saved MRB, but the
  headless Slicer process did not exit cleanly after interruption. Process
  lifecycle cleanup is the first post-checkpoint gate; no expensive rerun is
  justified before it passes with health-only probes.
- A reproducible install script, CPU constraints, Dockerfile, and Compose
  device-mapping example are under `Infrastructure/` and `Inference/`.
  Clean-image reconstruction and independent MRB reopen remain pending.
- No robot motion, drilling, patient data transfer, or clinical/anatomical
  validation was performed.

## Verified Git source

- Remote: `https://github.com/ghostarun/DentoBot.git`
- Default branch at transfer preparation: `main`
- Verified pre-feature baseline: `81836a7fdf9385b0a746097b8934568e7a329dd6`
- Feature branch: `codex/target-tooth-trajectory`
- The handoff must state the final pushed feature commit. Do not infer it from
  this document because a commit cannot contain its own hash.

The repository was clean before the feature branch was created. A live
`git ls-remote` check confirmed that GitHub `main` contained the recorded
baseline.

At Windows closeout, Step 4A was developer-verified on the retained teeth
phantom in Slicer 5.12.2 at the current PoC interaction scope. The feature
branch is published to GitHub; the exact final remote hash must be copied from
the session handoff and matched on Ubuntu before the clone is accepted.
Earlier isolated automated Slicer results are retained only as diagnostic
history; they are not the manual acceptance authority.

## What Git retrieves

Git contains:

- extension CMake configuration;
- the current `DENTOWorkflow` Python source and Qt Designer UI;
- the standalone `dentobot-inference` package and ordinary-Python tests;
- top-level validated dependency manifests and environment bootstrap;
- `validated-environment.json`;
- the disabled legacy scaffold retained for traceability;
- controlled architecture, roadmap, reproducibility, changelog, and logbook
  documents, including this transfer guide;
- complete repository history from the Git baseline onward.

Git does not contain installed applications, Python environments, model
weights, generated build products, medical/research data, or credentials.

## Non-Git transfer and reconstruction manifest

| Material | Git? | Transfer treatment |
|---|---:|---|
| DENTOWorkflow and inference source | Yes | Clone and verify the handoff commit. |
| Top-level Python requirements | Yes | Use for reconstruction; they are not a complete transitive lock. |
| Conda environment directory | No | Do not copy. Recreate and verify in the selected Ubuntu execution layer. |
| Complete Conda/pip inventory | Not yet | Optional reconstruction evidence; capture from the verified WSL environment only after reviewing it for local paths. |
| TotalSegmentator tasks 113, 115, and 298 | No | Download explicitly or transfer separately with file inventory and hashes. |
| `C:\DENTOBOTRuns` artifacts | No | Do not copy wholesale. Retain only approved, de-identified evidence needed for validation. |
| DICOM, NIfTI, NRRD, MRB, STL, and other research data | No | Transfer only through an approved local channel; never Git or the documentation Drive mirror. |
| Representative validation CBCT | No | Select a de-identified fixture and record its governance, geometry, and checksum separately. |
| Slicer installation and embedded Python | No | Install/use the pinned Ubuntu container build; never copy installed Windows Slicer files. |
| Slicer user settings | No | Recreate settings deliberately. Use an approved MRB only when scene state is required. |
| TotalSegmentator cache path | No | Record the selected Ubuntu cache path and verify cache-only behavior before inference. |
| GitHub credentials/tokens | No | Authenticate independently on Ubuntu; never copy credentials into the repository. |
| Ubuntu `compose.yaml`, `ros2_ws`, `data`, `slicer-user`, and active docs | No in this repository | Preserve in place and compare before integration. |
| Active Ubuntu Drive documentation | No in this repository | Treat the Ubuntu-local copy as authoritative and reconcile rather than overwrite. |

## Windows closeout before transfer

- [x] Confirm the repository contains only intended Step 4A and documentation
  changes plus ignored generated caches.
- [x] Manually verify the corrected Step 4A target, bounds, paired placement,
  undo/reset, and lock interaction on the retained teeth phantom.
- [x] Record that manual result as the current PoC acceptance authority.
- [x] Pass static Python AST, UI XML/object/reference/callback, Markdown fence,
  and Git whitespace checks.
- [x] Update the controlled local documentation and verify its Drive mirror.
- [x] Commit this final closeout.
- [x] Push `codex/target-tooth-trajectory`.
- [x] Record the exact pushed commit in the session handoff.
- [ ] On Ubuntu, reconcile the Git documentation with
  `IITM Dentobot/active-development-ubuntu` without replacing Ubuntu-only
  history.

Assistant-launched Slicer testing is not currently authorized. Static source,
UI, callback, Markdown, and whitespace checks remain part of Windows closeout.
The developer owns live Slicer acceptance unless explicit authorization is
renewed for a specific automated runtime action.

The repository `docs/` files are mirrored to the raw Markdown folder
`IITM Dentobot/docs` for cross-session context. That mirror is not a transfer
channel for data, model weights, credentials, or runtime artifacts. Ubuntu's
active development documents remain a separate reconciliation input and must
not be overwritten automatically.

Optional environment evidence commands, run inside the verified WSL
`dentobot` environment:

```bash
mkdir -p /tmp/dentobot-environment-evidence
conda list --explicit \
  > /tmp/dentobot-environment-evidence/conda-explicit-linux-64.txt
python -m pip freeze --all \
  > /tmp/dentobot-environment-evidence/pip-freeze.txt
python -m pip check \
  > /tmp/dentobot-environment-evidence/pip-check.txt
python -m dentobot_inference health --json --require-cuda \
  > /tmp/dentobot-environment-evidence/health.json
```

Review all evidence for local editable paths, usernames, credentials, and
sensitive paths before deciding whether it belongs in Git or a local transfer
bundle.

The environment-evidence capture is optional for the initial source transfer.
It becomes important before claiming clean-machine inference
reconstruction. Do not delay the Git source handoff merely to copy an
environment directory; environments must be recreated.

## Handoff manifest for anything outside Git

Create a separate manifest only for non-Git material actually required on the
Ubuntu workstation. Each entry must record:

- a non-identifying item name and purpose;
- source and intended destination;
- byte size and SHA-256 checksum;
- data classification and transfer approval;
- whether it is reconstructible, a model cache, a de-identified fixture, or
  unique evidence.

Do not add an item just because it exists on Windows. For the initial source
and Step 4A compatibility work, Git is sufficient. A separate approved
transfer is needed only if Ubuntu lacks required cached model weights, a
governed de-identified validation fixture, or unique evidence that cannot be
reconstructed.

## Safe Ubuntu retrieval

Do not clone over `/home/light-tarun/dentobot`. The existing directory owns
the current Compose, ROS 2 workspace, persistent mounts, and authoritative
Ubuntu documentation.

Use a separate comparison location:

```bash
mkdir -p /home/light-tarun/dentobot-migration
git clone \
  https://github.com/ghostarun/DentoBot.git \
  /home/light-tarun/dentobot-migration/DentoBot
git -C /home/light-tarun/dentobot-migration/DentoBot \
  switch codex/target-tooth-trajectory
git -C /home/light-tarun/dentobot-migration/DentoBot \
  status --short --branch
git -C /home/light-tarun/dentobot-migration/DentoBot \
  rev-parse HEAD
```

Before using the clone, compare its reported hash with the exact pushed hash
in the Windows handoff. If the feature branch is absent or the hashes differ,
stop and correct the Git handoff rather than copying local source files
ad hoc.

Compare before choosing the final layout:

- Git repository source and documentation;
- Ubuntu `compose.yaml` and bind mounts;
- `ros2_ws/src`, build, install, and log provenance;
- Ubuntu active control documents and dated logbook;
- Slicer 5.10 module paths and persistent user configuration;
- available GPU, CUDA, model-cache, and data paths.

Recommended initial disposition: keep the clone separate and mount or add its
extension source path to the container. Do not copy it into an installed Slicer
tree and do not convert the existing Ubuntu root into a Git repository until
the layout decision and file comparison are recorded.

## First Ubuntu session

1. Preserve and inventory `/home/light-tarun/dentobot`; do not overwrite it.
2. Clone the pushed feature branch into the comparison location and verify its
   hash.
3. Compare Compose, ROS workspace, bind mounts, persistent Slicer settings,
   model-cache paths, data paths, and active Ubuntu documentation.
4. Complete Gate 1 before launching runtime compatibility work.
5. Complete the Slicer-only part of Gate 2 with the retained phantom before
   adapting inference.
6. Choose and document the native-Ubuntu backend boundary before attempting
   Bridges A, B, or C.

The source/UI and Slicer-only gates can proceed without copying the Windows
Conda environment, Slicer installation, run artifacts, or patient/research
data.

## Compatibility gates

### Gate 1: source and UI

- parse every Python source file without importing Slicer in ordinary Python;
- parse `DENTOWorkflow.ui`;
- confirm all `self.ui.*` references and callbacks resolve;
- inspect MRML observer removal and transient planning-state cleanup paths;
- confirm the extension is discoverable in Slicer 5.10.

### Gate 2: Slicer-only workflow

- reload DENTO Workflow in the Ubuntu Slicer 5.10 container;
- run the Slicer-native self-test only under the testing authorization active
  for that Ubuntu session;
- select a retained segmentation;
- select one whole-tooth target;
- create and place Entry and Target;
- verify target-priority highlighting, the visible locked bounds ROI,
  out-of-bounds rejection, undo/reset, and pair locking;
- verify world-RAS coordinates, non-zero length, target association, and
  explicit draft status;
- save and reopen an MRB and verify parameter-node and MRML references.

This gate does not require inference and should be completed before adapting
the external process bridge.

### Gate 3: external backend architecture

The current bridge is Windows-specific because it launches `wsl.exe`, accepts
a Windows staging root, and converts Windows paths to `/mnt/<drive>` paths.
Do not run it unchanged on Ubuntu.

First choose and document one execution boundary:

- Slicer container to backend in the same container;
- Slicer container to a separate host process;
- Slicer container to a separate inference container.

Preserve the existing command/result contracts while replacing only the
platform adapter. Keep argument-list execution, unique run directories,
structured output, exit status, cache-only models, geometry validation, and
MRML import invariants.

### Gate 4: inference validation

Run in order:

1. reconstruct the environment;
2. `pip check` and ordinary-Python tests;
3. health with the explicitly selected CPU or CUDA device;
4. verify cached model tasks 113, 115, and transitive crop task 298;
5. standalone de-identified inference;
6. Slicer-launched health;
7. Bridge B geometry-preserving round trip;
8. Bridge C segmentation and MRML import;
9. review/correction and scene persistence.

Record exact commands, versions, outputs, failures, and unresolved differences
in the Ubuntu dated logbook. Windows evidence remains historical until the
corresponding Ubuntu gate passes.

## Safety boundary

No transfer or compatibility test authorizes robot motion, drilling,
patient-facing use, or clinical conclusions. Do not move patient identifiers,
credentials, models, or run artifacts through the documentation mirror.
