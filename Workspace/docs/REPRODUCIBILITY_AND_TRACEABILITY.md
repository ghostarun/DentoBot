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
