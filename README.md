# DENTOBOT

DENTOBOT is an academic research prototype for a focused dental
image-guidance workflow built on 3D Slicer. It is not validated clinical
software and does not authorize drilling or patient treatment.

## Supported runtime profiles

DENTOWorkflow uses the same MRML, planning, and geometry code on Windows and
Linux. Only the external-process and deployment adapters differ:

| Host profile | Slicer process | Inference process | Docker | SlicerROS2 |
|---|---|---|---|---|
| Windows 11 native | Native Windows Slicer | WSL2 Linux (`wsl.exe`) | Not required for planning | Not supported (`ROS_PROFILE=none`) |
| Windows 11 lab (WSL2) | Linux Slicer 5.10 in `dentobot-slicerros2` (WSLg) | Direct Linux Python in WSL (`cpu` or `cuda:0`) | Required | Same Ubuntu container stack |
| Ubuntu | Linux Slicer in the pinned SlicerROS2 container | Direct external Linux Python | Required by the verified profile | Included |

The inference stack is never installed into Slicer's embedded Python. Both
profiles launch the exact external Linux interpreter, exchange NIfTI plus
JSON in isolated run folders, and pass the device explicitly.

### Windows 11 lab (full DENTOWorkflow + Step 6 simulation)

This is the exportable Windows path that matches the Ubuntu Docker/SlicerROS2
stack. GUI is on WSLg (functional checks only; not FPS/GL acceptance). Do
**not** use `launch-dentoworkflow.ps1` here.

Prerequisites: Windows 11 + WSLg, Docker Desktop (WSL2 engine + NVIDIA GPU
support if using `cuda:0`), a WSL Ubuntu distro, GitHub auth that can pull the
private GHCR image, and collaborator access as required by package visibility.

```powershell
# Distro name must match `wsl -l -v` (often "Ubuntu", not "Ubuntu-24.04")
$env:DENTOBOT_WSL_DISTRIBUTION = "Ubuntu"

# 1) GHCR login inside WSL (private image), then install overlay at lab tag
# Prefer WSL shell so $HOME is not eaten by cmd quoting (see SETUP.md).
wsl -d $env:DENTOBOT_WSL_DISTRIBUTION --exec bash -lc "
  set -euo pipefail
  mkdir -p `$HOME/dentobot/ros2_ws/src
  REPO=`$HOME/dentobot/ros2_ws/src/DentoBot
  if [ ! -d `$REPO/.git ]; then
    git clone https://github.com/ghostarun/DentoBot.git `$REPO
  fi
  git -C `$REPO fetch --tags origin
  git -C `$REPO checkout --detach refs/tags/lab/2026-09-03
  bash `$REPO/Workspace/scripts/install-lab-wsl.bash
"

# 2) Once per PC: edit ~/dentobot/.dentobot.env
#   CUDA (Bridge C cu130): Python 3.10 env + DENTOBOT_BACKEND_DEVICE=cuda:0
#   CPU (Ubuntu OpenVINO): Python 3.12 env + DENTOBOT_BACKEND_DEVICE=cpu
#   DENTOBOT_GRAPHICS_MODE=wslg

# 3) Explicit model-cache install (tasks 298, 115, 113). Idempotent.
#    TotalSegmentator 2.16 does NOT accept CLI -t teeth|craniofacial_structures.
#    Do not rely on Slicer to download weights.
Workspace\scripts\install-lab-model-cache.bat

# 4) Launch full Linux SlicerROS2 DENTOWorkflow on WSLg
Workspace\scripts\launch-lab-workflow.bat
```

First launch builds `dentobot_description`, `dentobot_moveit_config`, and
`slicer_ros2_module` into the bind-mounted `ros2_ws` (the host mount hides the
image install tree). CUDA recreates the container with
`Workspace/compose.cuda.yaml`. WSLg uses `Workspace/compose.wslg.yaml` (no
`/dev/dri`). Recorded first-install deltas:
`Workspace/docs/logbook/2026-09-07.md`.

### Windows 11 native + WSL2 (planning only, no ROS)

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
Jazzy, and source-built Slicer 5.10/5.12. A native Windows SlicerROS2 build is
not an upstream tested target. Robot/ROS-integrated work on Windows uses the
**lab** profile above (or the verified Ubuntu workstation).

Official references: [SlicerROS2 compatibility](https://slicer-ros2.readthedocs.io/en/devel/pages/compatibility.html),
[SlicerROS2 getting started](https://slicer-ros2.readthedocs.io/en/devel/pages/getting-started.html), and
[SlicerROS2 CI image](https://slicer-ros2.readthedocs.io/en/devel/pages/ci-docker-image.html).

## Ubuntu workspace orchestration

The existing repository remains at `ros2_ws/src/DentoBot`. Its tracked
`Workspace/` directory now owns the Ubuntu launcher, Compose definition,
helper scripts, active workspace notes, and top-level agent instructions.
The surrounding workspace preserves the familiar `scripts`, `docs`,
`tools`, `compose.yaml`, and `AGENTS.md` paths as relative symlinks.
See `Workspace/HOST_LAYOUT.md` for the overlay map.

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

## ROS 2 robot description

The tracked `dentobot_description` package is exposed to colcon through the
workspace bootstrap's `ros2_ws/src/dentobot_description` relative symlink.
Build and run the simulation-only neutral description inside the Jazzy
container:

```bash
docker exec dentobot-slicerros2 bash -lc \
  'source /opt/ros/jazzy/setup.bash &&
   cd /workspace/ros2_ws &&
   colcon build --symlink-install --packages-select dentobot_description'

docker exec -it dentobot-slicerros2 bash -lc \
  'source /opt/ros/jazzy/setup.bash &&
   source /workspace/ros2_ws/install/setup.bash &&
   ros2 launch dentobot_description description.launch.py use_rviz:=false'
```

The launch publishes neutral joint states and TF for inspection only. It has
no controller, command topic, hardware plugin, or motion path. See
`dentobot_description/README.md` for provenance and unresolved calibration,
collision, frame, and physical-verification work.

DENTOWorkflow also exposes **6 · Robot Placement** for scene-only
placement. It loads the same tracked URDF/STLs into an MRML transform hierarchy,
allows manual joint changes, and provides an editable mount plane with explicit
snap plus local button/keyboard nudges. This is not a live ROS/SlicerROS2 bridge:
it reads no robot state, sends no command, and does not establish head-mount
registration, a calibrated TCP, collision safety, or hardware readiness.

For the current disposable workspace check, Step 6 can load local aligned
BodyParts3D skull/maxilla/mandible meshes, collect approximate left/right TMJ
and upper/lower central-incisor landmarks, and rotate the mandible about the
TMJ axis to an approximately 40 mm final incisor gap. The robot base can then
be dragged/snapped to a provisional forehead plane, fine-tuned by buttons or
opt-in keyboard controls, and articulated with the six manual joint controls.
See `Workspace/docs/SETUP.md` for asset checksums and the exact trial sequence.
This is generic design visualization only, not clinical jaw simulation,
registration, collision validation, or robot control.

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
