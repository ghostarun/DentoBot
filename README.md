# DENTOBOT

DENTOBOT is an academic research prototype for a focused dental
image-guidance workflow built on 3D Slicer. It is not validated clinical
software and does not authorize drilling or patient treatment.

## Supported runtime profiles

DENTOWorkflow uses the same MRML, planning, and geometry code on Windows and
Linux. Only the external-process and deployment adapters differ:

| Host profile | Slicer process | Inference process | Docker | SlicerROS2 |
|---|---|---|---|---|
| Windows 11 | Native Windows Slicer | WSL2 Linux (`wsl.exe`) | Not required | Not in the supported Windows planning profile |
| Ubuntu | Linux Slicer in the pinned SlicerROS2 container | Direct external Linux Python | Required by the current verified profile | Included |

The inference stack is never installed into Slicer's embedded Python. Both
profiles launch the exact external Linux interpreter, exchange NIfTI plus
JSON in isolated run folders, and pass the device explicitly.

### Windows 11 + WSL2

Copy and edit the machine-local example, then launch native Windows Slicer:

```powershell
Copy-Item Workspace\.dentobot.windows.env.example .dentobot.windows.env
powershell -ExecutionPolicy Bypass -File `
  Workspace\scripts\launch-dentoworkflow.ps1 -CheckOnly
powershell -ExecutionPolicy Bypass -File `
  Workspace\scripts\launch-dentoworkflow.ps1
```

The Windows launcher validates Slicer, the named WSL distribution, the exact
Linux backend interpreter, the requested CPU/CUDA device, and a local Windows
run-record directory before opening DENTO Workflow. Docker Desktop is not
needed for segmentation, planning, template generation, verification, or STL
export.

Current upstream SlicerROS2 1.2 compatibility targets Ubuntu 24.04, ROS 2
Jazzy, and source-built Slicer 5.10/5.12. A Linux CI image is provided, but a
native Windows SlicerROS2 build is not an upstream tested target. Therefore,
robot/ROS-integrated DENTOBOT work uses the verified Ubuntu profile. Running
the Linux GUI image through Docker Desktop/WSL2 is possible to investigate,
but it is not yet a supported or verified DENTOBOT Windows profile.

Official references: [SlicerROS2 compatibility](https://slicer-ros2.readthedocs.io/en/devel/pages/compatibility.html),
[SlicerROS2 getting started](https://slicer-ros2.readthedocs.io/en/devel/pages/getting-started.html), and
[SlicerROS2 CI image](https://slicer-ros2.readthedocs.io/en/devel/pages/ci-docker-image.html).

## Ubuntu workspace orchestration

The existing repository remains at `ros2_ws/src/DentoBot`. Its tracked
`Workspace/` directory now owns the Ubuntu launcher, Compose definition,
helper scripts, active workspace notes, and top-level agent instructions.
The surrounding workspace preserves the familiar `scripts`, `docs`,
`compose.yaml`, and `AGENTS.md` paths as relative symlinks.

Create the compatibility links safely in a new workspace with:

```bash
Workspace/bootstrap-workspace.bash
```

Copy `Workspace/.dentobot.env.example` to the workspace root as
`.dentobot.env` and edit only that untracked file for the local Conda
interpreter and graphics device. DENTO Workflow receives those values from
the launcher automatically; no machine path needs to be remembered or saved
in an MRB scene.

From the surrounding workspace, Git can be addressed without remembering the
nested checkout path:

```bash
scripts/git-dentobot.bash status --short --branch
```

## Ubuntu interactive rendering

A visible Slicer window does not prove hardware acceleration. On Ubuntu,
containerized Slicer needs a working host GPU driver, a compatible userspace
OpenGL driver in the image, and explicit access to the intended DRM render
node.

Inspect the host first:

```bash
lspci -nnk | grep -A4 -Ei 'vga|3d|display'
ls -l /dev/dri
readlink -f /sys/class/drm/renderD128/device/driver
```

For Mesa-backed Intel or AMD graphics, map the actual non-modesetting render
node into the service:

```yaml
services:
  slicerros2:
    devices:
      - /dev/dri/renderD128:/dev/dri/renderD128
```

The node number may differ on multi-GPU systems. Non-root container users also
need the matching host render-group GID. AMD requires a compatible Mesa
`radeonsi` driver. Proprietary NVIDIA deployments normally use NVIDIA
Container Toolkit rather than this Intel/AMD DRM recipe.

Slicer 5.10 may lower the entire Linux process priority when initializing its
background threads. Preserve interactive priority with:

```yaml
services:
  slicerros2:
    environment:
      SLICER_BACKGROUND_THREAD_PRIORITY: "0"
```

Save and close Slicer before recreating a container. Then verify both device
access and renderer identity; reject `llvmpipe` or `swrast` unless software
rendering is deliberately requested.

### Verified workstation configuration

The active IITM workstation has Intel Arrow Lake-S integrated graphics using
`i915` and `/dev/dri/renderD128`. Its verified Slicer renderer is
`Mesa Intel(R) Graphics (ARL)`, OpenGL 4.6, with direct rendering enabled and
Slicer running at nice level 0. The workspace launcher validates the render
node and priority override before opening DENTO Workflow.

From the Ubuntu workspace root:

```bash
/home/light-tarun/dentobot/scripts/launch-dentoworkflow.bash --check-only
/home/light-tarun/dentobot/scripts/launch-dentoworkflow.bash
```

The complete workstation procedure is maintained in
`/home/light-tarun/dentobot/docs/SETUP.md`.
