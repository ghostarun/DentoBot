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

## What Git retrieves

Git contains:

- extension CMake configuration;
- the current `DENTOWorkflow` Python source and Qt Designer UI;
- the standalone `dentobot-inference` package and ordinary-Python tests;
- top-level validated dependency manifests and environment bootstrap;
- `validated-environment.json`;
- the disabled legacy scaffold retained for traceability;
- controlled architecture, roadmap, reproducibility, changelog, and logbook
  documents;
- complete repository history from the Git baseline onward.

Git does not contain installed applications, Python environments, model
weights, generated build products, medical/research data, or credentials.

## Non-Git transfer and reconstruction manifest

| Material | Git? | Transfer treatment |
|---|---:|---|
| DENTOWorkflow and inference source | Yes | Clone and verify the handoff commit. |
| Top-level Python requirements | Yes | Use for reconstruction; they are not a complete transitive lock. |
| Conda environment directory | No | Do not copy. Recreate and verify in the selected Ubuntu execution layer. |
| Complete Conda/pip inventory | Not yet | Capture from the verified WSL environment after reviewing it for local paths. |
| TotalSegmentator tasks 113 and 115 | No | Download explicitly or transfer separately with file inventory and hashes. |
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

1. Confirm the working tree contains only the intended feature and
   documentation changes.
2. Run static Python, UI XML, UI-reference, callback, and whitespace checks.
3. Run DENTOWorkflow's Slicer-native self-test in Slicer 5.12.2 when
   explicitly authorized.
4. Manually verify target selection, trajectory placement, world-RAS values,
   and MRB save/reopen.
5. Update `docs/changelog.md` and `docs/logbook.md` with the exact evidence and
   limitations.
6. Commit and push `codex/target-tooth-trajectory`.
7. Record the pushed commit in the session handoff.
8. Reconcile changed documentation with
   `IITM Dentobot/active-development-ubuntu` without replacing Ubuntu-only
   history.

The active Drive documentation was read during the Windows session, but the
available connector did not expose a file upload or update operation. The Git
handoff is therefore the authoritative transfer path for this increment, and
Drive reconciliation remains an explicit Ubuntu-side task.

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

## Compatibility gates

### Gate 1: source and UI

- parse every Python source file without importing Slicer in ordinary Python;
- parse `DENTOWorkflow.ui`;
- confirm all `self.ui.*` references and callbacks resolve;
- confirm the extension is discoverable in Slicer 5.10.

### Gate 2: Slicer-only workflow

- reload DENTO Workflow in the Ubuntu Slicer 5.10 container;
- run the Slicer-native self-test;
- select a retained segmentation;
- select one whole-tooth target;
- create and place Entry and Target;
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
3. GPU health with explicit CUDA requirement;
4. verify cached model tasks 113 and 115;
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
