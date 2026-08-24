# DENTOBOT Inference Reproducibility and Traceability

## Document control

| Field | Value |
|---|---|
| Document status | Controlled research-development baseline |
| Applicable backend | DENTOBOT inference 0.2.0 |
| Applicable host application | 3D Slicer 5.12.2 on Windows; Slicer 5.10 on Ubuntu |
| Validated execution layer | WSL2 Python 3.10.20 CUDA; Ubuntu container Python 3.12.3 CPU |
| Baseline validation dates | 2026-07-23 CUDA; 2026-07-31 Ubuntu CPU |
| Evidence level | One real-CBCT CUDA happy path and one public-fixture Ubuntu CPU/import/MRB path |
| Intended use | Research and development only |

This document is the normative procedure for reconstructing the external
inference environment, checking its identity, and retaining sufficient
evidence to trace a DENTOBOT inference run. It does not establish anatomical
accuracy, clinical safety, or regulatory compliance.

## 1. System boundary

DENTOBOT intentionally separates two Python environments:

1. 3D Slicer's embedded Windows Python owns the module UI, MRML scene, NIfTI
   export/import, validation, and visualization.
2. A dedicated Conda Python inside WSL2 owns PyTorch, CUDA access,
   TotalSegmentator, nnU-Net, and inference.

Slicer launches the WSL interpreter by its absolute path. It does not activate
Conda, import WSL packages, install dependencies, or download models.

### 1.1 Ubuntu configuration checkpoint — 2026-08-06

The tracked `Workspace/.dentobot.env.example` defines the active Ubuntu local
runtime configuration shape. A populated `.dentobot.env` lives only at the
surrounding workspace root and is excluded from Git and Drive. The launcher
derives and exports the exact backend interpreter, Conda environment
directory, run-record root, render node, and workspace root to Compose and
Slicer. DENTOWorkflow does not require those machine paths typed into or
persisted with the scene.

Pytest 8.4.2, already pinned by
`Inference/requirements/test-validated.txt`, was installed in the dedicated
Ubuntu Python 3.12 backend. `pip check` and all 13 inference tests passed. No
package was installed into Slicer's embedded Python, and this evidence does
not establish full segmentation/model reconstruction or anatomical accuracy.

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

## 3. Validated compatibility baseline

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

### 3.1 Native-Ubuntu compatibility baseline

| Component | Validated value |
|---|---|
| Git source branch | `codex/ubuntu-migration` |
| Migrated source baseline | `72da94207d33234a12f5d904c23733ff382f9e43` |
| Container base | `ghcr.io/rosmed/slicer_ros2_module/ci:jazzy-slicer-v5.10.0` |
| Slicer | 5.10.0, build date 2025-11-10 |
| Python | 3.12.3 at `/opt/dentobot-venv/bin/python` |
| NumPy / NiBabel | 2.2.6 / 5.4.2 |
| PyTorch | 2.10.0+cpu |
| TotalSegmentator / nnUNet v2 | 2.16.0 / 2.8.1 |
| OpenVINO | 2026.2.0 |
| Requested/actual inference device | cpu / cpu |
| TotalSegmentator tasks | teeth 113; craniofacial 115; transitive total-fast crop 298 |
| Public fixture | Slicer `CBCTDentalSurgery`, `PreDentalSurgery` volume |
| Input geometry | 360 x 360 x 330; 0.5 mm isotropic; int16 |
| Inference result | 54 labels; 579,353 foreground voxels; geometry/label validation passed |
| Runtime | 217.848237 seconds total; 217.058393 seconds inference |
| Slicer result | 54 segments, closed surfaces, review metadata, MRB saved |

A later fully Slicer-launched Bridge C run used run ID
`794b7570c5e24583b0a62ffe2a7d8471`. Slicer exported the public fixture,
launched the isolated CPU backend asynchronously, received `status: ok`,
imported 54 segments, and saved the final MRB. Backend runtime was
372.777041 seconds. The longer time than the standalone baseline is evidence
from one concurrently active development container, not a benchmark.

Artifact and model files remain outside Git and Drive. Their SHA-256 evidence:

| Item | SHA-256 |
|---|---|
| Public fixture NIfTI | `a574237fdb32372582991932224d2fdefba98e0271f05fb2b32487b82a7019ed` |
| Validated teeth NIfTI | `9ffb207be1c2ff305b7e190bef5def5633971e721d6b6a7e122b77bc0d839364` |
| Result JSON | `f22b24fa02105989ff145f25e908bd4e277561e17d37c953e74fab512671f0e0` |
| Slicer review MRB | `9acabe27aa1e35fc5de293578f0b9554a836fbc8536407b8f3970e0b6723af54` |
| Task 113 checkpoint | `195ef8bb3f6de012c1200a961110ac5df525025cdbadbe09077ea35fd5424ef0` |
| Task 115 checkpoint | `8a65ceca091d90e4eb42ae994840e5813cb811bc8dc587c3612c05490259b44f` |
| Task 298 checkpoint | `3489323a4b759506ab46b489eb78b72142f2143aea6e6d828604d754bd7a9270` |
| Slicer-launched result JSON | `250c102d3cbdbd86720fbb99a1a85be95ddcc0e8bbfaa273e84192b02f7f8fa9` |
| Slicer-launched teeth NIfTI | `2fec20e589ee41beb5cba1e9c67e2e8d96e817bd5ea34574245a59cfaab71f79` |
| Slicer-launched final MRB | `dadb4ceeb229aa097688685116b997182710c5dd840d575b91a88b60984eb04f` |

The successful MRB save is not yet an independent close/reopen inspection.
The public sample is useful for software compatibility but is not dental
ground truth and does not establish anatomical accuracy.

The backend and MRB completed, but the original headless Slicer test process
did not exit after the controlling terminal session was interrupted. That
lifecycle defect was closed on 2026-08-03 without rerunning segmentation. The
Slicer 5.10 fallback now gives `QProcess` explicit Qt parent ownership,
disconnects its Python callbacks after draining output, closes it, and
schedules deletion. The health harness also explicitly releases its widget.

Two consecutive Bridge A probes ran from disposable, network-disabled
containers based on checkpoint image
`sha256:b7b02f5d37e2b6d6edec6f0bd06783464a4714a7fd24b5ca248abf32acf81512`,
with the repository source mounted read-only. They returned successful
explicit-CPU health in 7.758992707 and 5.913129843 seconds, respectively;
OpenVINO reported `CPU`, both Slicer processes exited zero, the backend child
exited, and both disposable containers were removed. The ordinary Compose
container remains a separate minimal Bridge B runtime and does not contain
`/opt/dentobot-venv`; clean reconstruction of the full checkpoint environment
is still the next gate.

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

### 5.1 Native-Ubuntu installation

Inside the SlicerROS2 container, install `python3-venv`, then run:

```bash
/workspace/ros2_ws/src/DentoBot/Infrastructure/install_ubuntu_backend.sh \
  /workspace/ros2_ws/src/DentoBot
```

The script creates `/opt/dentobot-venv`, installs PyTorch 2.10.0 from the
official CPU wheel index before resolving TotalSegmentator, applies
`ubuntu-cpu-constraints.txt`, installs the backend editable, runs `pip check`
and tests, and requires explicit CPU health. Installing PyTorch first prevents
the TotalSegmentator resolver from replacing it with a CUDA wheel.

For clean-image construction use
`Infrastructure/Dockerfile.ubuntu-cpu`. The Compose override example shows
persistent model/data paths and Intel accelerator device mapping. The
hard-coded example render-group ID must be replaced with the host's actual
group ID.

## 6. Model-cache preparation

Run model downloads explicitly from the configured environment:

```bash
totalseg_download_weights -t craniofacial_structures
totalseg_download_weights -t teeth
```

TotalSegmentator 2.16 also invokes task 298 transitively while producing the
rough crop needed by tasks 115 and 113. On the validated Ubuntu version its
CLI task choices did not expose every required internal task, so task 298 was
downloaded explicitly through TotalSegmentator's own registered library API:

```bash
TOTALSEG_HOME_DIR=/workspace/data/model-cache/totalsegmentator \
  /opt/dentobot-venv/bin/python -c \
  "from totalsegmentator.libs import download_pretrained_weights; download_pretrained_weights(298)"
```

TotalSegmentator's default cache is below
`~/.totalsegmentator/nnunet/results`. The Slicer-launched runtime is
cache-only: it must fail clearly if a required model is absent rather than
silently initiating a download.

For a formal release snapshot, record tasks 113, 115, and 298, cache location,
file inventory, byte sizes, and cryptographic hashes without uploading model
files to the documentation mirror.

### 6.1 OpenVINO and Intel NPU boundary

OpenVINO 2026.2.0 is installed so the Ubuntu backend can report devices.
Without accelerator devices mapped into the container, the validated health
run saw only `CPU`. TotalSegmentator 2.16 accepts CPU, CUDA, and Apple MPS
device paths; it does not offer OpenVINO NPU as a direct execution option.
NPU device visibility is therefore a deployment probe, not evidence that the
dental nnU-Net model runs on the NPU. A future NPU milestone must convert the
relevant model pipeline, compare labels/geometry against an accepted baseline,
measure performance and memory, and preserve CPU/CUDA as explicit alternatives
until equivalence is demonstrated.

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

The Windows launcher supplies the DENTO Workflow bridge with:

| Setting | Validated value |
|---|---|
| WSL distribution | `Ubuntu` |
| Environment Python | `/home/tarun/miniconda3/envs/dentobot/bin/python` |
| Run-artifact root | `C:\DENTOBOTRuns` |

The absolute interpreter path is authoritative. A Conda environment activated
in an unrelated terminal does not affect the process launched by Slicer.
Use `Workspace/scripts/launch-dentoworkflow.ps1`; the UI fields are an
advanced fallback, not the normal machine-configuration store. Ubuntu uses
`Workspace/scripts/launch-dentoworkflow.bash` with the `local` adapter and its
separate CPU pins.

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
### Step 5A MRML model traceability

A Step 5A draft support-anatomy model is derived only from a Reviewed
authoritative segmentation and remains in the MRML scene. Its node reference
role is `DENTOBOT.TemplateSourceSegmentation`. Required namespaced attributes
record the model role/schema/status, Current or Stale geometry state and
reason, target segment/FDI, ordered support segment and FDI JSON lists, support
count, source segment-name map, source review timestamp, source point/cell
counts, coordinate convention, and update UTC time.

The output retains source-local geometry and observes the segmentation's
parent transform. Selection or mask-content changes must mark the model Stale
instead of silently changing or deleting it. Scene save/reopen must preserve
the parameter-node support selection, output reference, model provenance,
geometry state, and source reference.

Static coverage includes a target plus ten supports and an explicit update to
two supports. Live Slicer creation and independent save/reopen evidence remain
developer-run and pending; static checks alone do not establish that
acceptance.


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

## 15. Ubuntu native Step 6 evidence — 2026-08-24

The current tool link is `dentobot_drill_tip_provisional`; it is CAD-derived
and not physically calibrated. The host contract command
`PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider Testing
dentobot_description/test` returned `95 passed`. Focused Slicer probes verified
explicit singleton rendering without scalar/IJK/mask geometry changes,
base/proxy/home/opacity MRB round trip, the supplied Step 6 restore, and three
case packages at `1e-6`. Isolated ROS probes verified strict MoveIt behavior and
that only selected burr-target contact in the approved task corridor is
accepted; wrong task, non-target, self collision, bounds, lateral escape, and
overshoot are rejected. These are simulation/software results only.
