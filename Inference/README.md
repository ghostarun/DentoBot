# DENTOBOT inference backend

## Purpose

This package is the Linux/WSL2 compute layer for the DENTOBOT research
workflow. 3D Slicer owns the user interface, MRML scene, visualization, and
result review. This package owns dependency-heavy image processing and AI
inference. It does not import Slicer and must not be installed into Slicer's
embedded Python environment.

The validated Bridge C happy path uses DENTOBOT backend 0.2.0,
TotalSegmentator 2.16.0, PyTorch 2.10.0 with CUDA 13.0, and Python 3.10.20.
The authoritative installation, evidence, recovery, and traceability procedure
is [REPRODUCIBILITY_AND_TRACEABILITY.md](../docs/REPRODUCIBILITY_AND_TRACEABILITY.md).

## Reproducibility scope

The files under `requirements/` pin the top-level versions observed during the
successful 2026-07-23 Bridge C run. They are a validated compatibility
baseline, not a complete transitive lock. `validated-environment.json` records
the corresponding machine-readable runtime evidence. A full platform-specific
environment export remains a release task.

## Prerequisites

- Windows with WSL2 and the Ubuntu distribution
- a working Windows NVIDIA driver exposed to WSL2
- Conda in WSL2
- the repository available inside WSL, for example under `/mnt/e/...`
- model-cache and run-artifact storage with sufficient free space

Do not install a Linux NVIDIA display driver inside WSL. DENTOBOT uses the
CUDA support exposed by the Windows driver and the CUDA runtime supplied by
the official PyTorch wheel.

## Validated installation

Run these commands from `Inference/` in a WSL shell:

```bash
conda env create -f environment.yml
conda activate dentobot

python -m pip install \
  --index-url https://download.pytorch.org/whl/cu130 \
  -r requirements/pytorch-cu130.txt

python -m pip install \
  --constraint requirements/validated-constraints.txt \
  -r requirements/runtime-validated.txt

python -m pip install --no-deps -e .

python -m pip install \
  --constraint requirements/validated-constraints.txt \
  -r requirements/test-validated.txt
```

If the `dentobot` environment already exists, inspect or remove it deliberately
before recreating it; do not overwrite a working research environment without
capturing its specification.

## Model preparation

Model acquisition is an explicit terminal action and never occurs when Slicer
launches inference:

```bash
totalseg_download_weights -t craniofacial_structures
totalseg_download_weights -t teeth
```

TotalSegmentator normally stores weights below
`~/.totalsegmentator/nnunet/results`. The DENTOBOT runtime replaces implicit
downloading with a cache-only guard.

## Verification

```bash
python -m pip check
python -m pytest
python -m dentobot_inference health --json --require-cuda
```

The health output must report the intended environment interpreter, status
`ok`, CUDA availability, and the expected GPU. The three existing WSL tests
and CUDA health check have passed in the recreated environment. The newer
segmentation failure-path tests are explicitly deferred and are not claimed as
passing.

## Slicer bridge configuration

On the active Ubuntu workspace, start Slicer through
`scripts/launch-dentoworkflow.bash`. The launcher reads the one untracked
`.dentobot.env`, supplies the exact backend interpreter and local run-record
root, and DENTO Workflow uses them automatically. Do not install this package
into Slicer's Python or persist workstation paths in an MRB scene.

The older Windows/WSL compatibility mode remains a manual advanced override.
Configure:

- WSL distribution: `Ubuntu`
- Environment Python: `/absolute/path/to/conda/envs/dentobot/bin/python`
- Run artifacts: a Windows directory such as `C:\DENTOBOTRuns`

Slicer calls the environment by absolute interpreter path. Activating Conda in
a separate terminal does not configure Slicer.

## Backend commands

```bash
python -m dentobot_inference health --json --require-cuda

python -m dentobot_inference roundtrip \
  --input /mnt/c/DENTOBOTRuns/<run-id>/input.nii \
  --output /mnt/c/DENTOBOTRuns/<run-id>/roundtrip.nii \
  --result-json /mnt/c/DENTOBOTRuns/<run-id>/result.json \
  --run-id <run-id>

python -m dentobot_inference segment-teeth \
  --input /mnt/c/DENTOBOTRuns/<run-id>/input.nii \
  --output /mnt/c/DENTOBOTRuns/<run-id>/teeth-segmentation.nii \
  --result-json /mnt/c/DENTOBOTRuns/<run-id>/result.json \
  --run-id <run-id>
```

`segment-teeth` requires CUDA device 0 and does not silently fall back to CPU.
Each run retains its input, validated output when successful, and
schema-versioned `result.json` under the selected artifact root. These files
may contain patient-derived data and must follow project data-governance
rules.

## Support boundary

Bridge C is technically verified for one representative real CBCT: inference
completed, 60 labels were imported, and aligned 2D/3D display was produced.
This does not establish anatomical accuracy, clinical suitability, robust
failure handling, cancellation behavior, or MRB persistence. Those items are
tracked as deferred validation work in `docs/DEVELOPMENT_PLAN.md`.
