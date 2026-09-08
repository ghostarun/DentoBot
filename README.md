# DENTOBOT

DENTOBOT is an academic research prototype for a focused dental
image-guidance workflow built on 3D Slicer. It is not validated clinical
software and does not authorize drilling or patient treatment.

## Alternating development between machines

Use `main` as the shared development baseline and work on only one machine at
a time. Before switching devices, commit the intended source/documentation
changes and push the active branch. On the next device, inspect `git status`,
fetch origin, and use `git pull --ff-only` on that same branch before editing.
If Git reports local changes or divergent history, preserve that work and
reconcile it before continuing; do not reset or force-push to synchronize.
Uncommitted files and local-only commits do not travel between machines.

Keep `.dentobot.env`, `compose.override.yaml`, datasets, model caches, Conda
environments, and build/install trees local to each device. Record the active
branch, commit, outstanding work, and verification limits in the dated logbook
at handoff. Each machine retains its own CPU/CUDA and graphics configuration.

The Ubuntu NVIDIA and Windows WSLg/CUDA setup paths are integrated in `main`.
Each remains tied to its documented host profile and recorded verification;
installation on a new machine still ends with the profile's check-only gate.

## Supported runtime profiles

DENTOWorkflow uses the same MRML, planning, and geometry code on Windows and
Linux. Only the external-process and deployment adapters differ:

| Host profile | Slicer process | Inference process | Docker | SlicerROS2 |
|---|---|---|---|---|
| Windows 11 + WSLg (primary) | Linux Slicer 5.10 in `dentobot-slicerros2` through WSLg | Direct Linux Python in WSL (`cpu` or `cuda:0`) | Required | Included; Steps 0–6 simulation |
| Native Windows fallback | Native Windows Slicer | WSL2 Linux (`wsl.exe`) | Not required | Unavailable; Steps 0–5 only |
| Ubuntu (CPU) | Linux Slicer in the pinned SlicerROS2 container | Direct external Linux Python (`cpu`) | Required | Included |
| Ubuntu + NVIDIA | Same container | Direct external Linux Python (`cuda:0`) | Required + NVIDIA Container Toolkit | Included |

The inference stack is never installed into Slicer's embedded Python. Both
profiles launch the exact external Linux interpreter, exchange NIfTI plus
JSON in isolated run folders, and pass the device explicitly.

### Windows 11 + WSLg: primary full workflow and Step 6 simulation

Use this profile when Windows must run the same Linux SlicerROS2 simulation
stack as Ubuntu. It requires Windows 11 with WSLg, Docker Desktop using the
WSL2 engine, a WSL Ubuntu distribution, and NVIDIA container support when
using `cuda:0`. WSLg is accepted for functional GUI checks, not rendering
performance acceptance.

```powershell
# Use the exact name printed by: wsl -l -v
$env:DENTOBOT_WSL_DISTRIBUTION = "Ubuntu"

# From a clone checked out at the intended lab tag or integration revision:
Workspace\scripts\install-lab-wsl.bat

# Cache TotalSegmentator tasks 298, 115, and 113. Safe to rerun.
Workspace\scripts\install-lab-model-cache.bat

# Launch Linux SlicerROS2 through WSLg.
Workspace\scripts\launch-lab-workflow.bat
```

The installer creates the WSL overlay and pins the SlicerROS2 dependency. Set
`DENTOBOT_GRAPHICS_MODE=wslg` in `~/dentobot/.dentobot.env`; select `cpu` with
the Python 3.12 CPU environment or `cuda:0` with the Python 3.10 cu130
environment. The launcher merges the tracked WSLg and CUDA Compose overlays,
builds the three required ROS packages in the bind-mounted workspace, checks
the selected inference device, and fails before GUI launch when prerequisites
are missing. See `Workspace/docs/SETUP.md` for GHCR authentication, environment
creation, first-install recovery, and exact verification commands.

### Legacy fallback: native Windows Slicer, Steps 0–5 only

This is a limited compatibility workaround. It deliberately hides Step 6,
does not load SlicerROS2, and must not be used when the full Windows
installation is intended. Native Windows Slicer plus native Windows ROS is
outside the current project scope.

Copy and edit the machine-local example, then launch native Windows Slicer:

```powershell
Copy-Item Workspace\.dentobot.windows.env.example .dentobot.windows.env
powershell -ExecutionPolicy Bypass -File `
  Workspace\scripts\launch-native-windows-steps0-5.ps1 -CheckOnly
powershell -ExecutionPolicy Bypass -File `
  Workspace\scripts\launch-native-windows-steps0-5.ps1
```

The Windows launcher validates Slicer, the named WSL distribution, the exact
Linux backend interpreter, the requested CPU/CUDA device, and a local Windows
run-record directory before opening DENTO Workflow. Docker Desktop is not
needed for Steps 0–5 segmentation, planning, template generation,
verification, or STL export. The launcher sets an explicit workflow profile
that removes Step 6 and disables its saved-checkpoint runtime restoration.

Current upstream SlicerROS2 1.2 compatibility targets Ubuntu 24.04, ROS 2
Jazzy, and source-built Slicer 5.10/5.12. A native Windows SlicerROS2 build is
not an upstream tested target. Robot/ROS-integrated Windows work uses the
primary Windows WSLg profile above. Native Windows Slicer remains the
Steps 0–5 fallback only.

Official references: [SlicerROS2 compatibility](https://slicer-ros2.readthedocs.io/en/devel/pages/compatibility.html),
[SlicerROS2 getting started](https://slicer-ros2.readthedocs.io/en/devel/pages/getting-started.html), and
[SlicerROS2 CI image](https://slicer-ros2.readthedocs.io/en/devel/pages/ci-docker-image.html).

## Ubuntu workspace orchestration

The repository lives at `ros2_ws/src/DentoBot` under an overlay root such as
`~/dentobot`. Tracked `Workspace/` owns the Ubuntu launcher, Compose
definition, helper scripts, active workspace notes, and top-level agent
instructions. The overlay preserves `scripts`, `docs`, `tools`,
`compose.yaml`, and `AGENTS.md` as relative symlinks. See
`Workspace/HOST_LAYOUT.md` for the overlay map.

Create the compatibility links safely in a new workspace with:

```bash
mkdir -p ~/dentobot/ros2_ws/src
git clone https://github.com/ghostarun/DentoBot.git ~/dentobot/ros2_ws/src/DentoBot
# Pin slicer_ros2_module to Workspace/LAB_RELEASE (required for Slicer launch)
git clone https://github.com/ghostarun/slicer_ros2_module.git \
  ~/dentobot/ros2_ws/src/slicer_ros2_module
git -C ~/dentobot/ros2_ws/src/slicer_ros2_module checkout \
  "$(awk -F= '/^SLICERROS2_SHA=/{print $2}' \
    ~/dentobot/ros2_ws/src/DentoBot/Workspace/LAB_RELEASE)"
bash ~/dentobot/ros2_ws/src/DentoBot/Workspace/bootstrap-workspace.bash
```

Copy `Workspace/.dentobot.env.example` to the workspace root as
`.dentobot.env` and edit only that untracked file for the local Conda
interpreter, device (`cpu` or `cuda:0`), and graphics render node. DENTO
Workflow receives those values from the launcher automatically; no machine
path needs to be remembered or saved in an MRB scene.

From the surrounding workspace, Git can be addressed without remembering the
nested checkout path:

```bash
scripts/git-dentobot.bash status --short --branch
```

### Ubuntu first-run checklist

1. Install Docker Engine. For NVIDIA hosts also install the NVIDIA Container
   Toolkit (`Workspace/scripts/install-host-nvidia-docker.bash` or equivalent)
   and reboot if the kernel module and userspace driver versions disagree.
2. Create the Conda `dentobot` environment from `Inference/` using either the
   Ubuntu CPU manifests or the Bridge C CUDA pins
   (`environment.yml` + `requirements/pytorch-cu130.txt` +
   `requirements/runtime-validated.txt`). Install CUDA torch **and**
   torchvision from the same `cu130` index (`torchvision==0.25.0+cu130`); a
   generic torchvision wheel breaks TotalSegmentator with
   `operator torchvision::nms does not exist`. Install packages into the env
   with `PYTHONNOUSERSITE=1` so nothing lands only under `~/.local` (user-site
   is not bind-mounted into the container).
3. Cache TotalSegmentator tasks **113**, **115**, and **298** under
   `data/model-cache/totalsegmentator`. Prefer calling
   `totalsegmentator.libs.download_pretrained_weights` for task IDs 115 and
   113; the CLI `-t` choices do not currently expose `teeth` /
   `craniofacial_structures` by name. Task 298 arrives with `total` /
   `total_fast`.
4. Build or pull the Compose image
   `dentobot/slicerros2:jazzy-moveit-sim-20260903` (see
   `Workspace/Dockerfile.slicerros2` / `Workspace/LAB_RELEASE`).
5. On NVIDIA hosts, the launcher automatically merges the tracked
   `Workspace/compose.cuda.yaml` when `DENTOBOT_BACKEND_DEVICE=cuda:0`.
   Reserve an untracked `compose.override.yaml` for machine-specific changes.
6. The launcher builds `dentobot_description`, `dentobot_moveit_config`, and
   `slicer_ros2_module` inside the container. A missing
   `slicer_ros2_module` install produces
   `package 'slicer_ros2_module' not found` at GUI launch.

```bash
cd ~/dentobot
./scripts/launch-dentoworkflow.bash --check-only
./scripts/launch-dentoworkflow.bash
```

Long-form workstation notes remain in `Workspace/docs/SETUP.md`.

## Ubuntu + NVIDIA (CUDA inference)

Verified on Ubuntu 22.04 with an AMD iGPU + NVIDIA RTX 4060 Laptop (driver
580.x, CUDA 13.0 wheels). Split responsibilities deliberately:

- **Slicer OpenGL:** Mesa DRM render node (AMD/Intel), set
  `DENTOBOT_RENDER_DEVICE` to the matching `/dev/dri/renderD*`.
- **Segmentation CUDA:** host Conda Python with `torch==2.10.0+cu130`,
  `DENTOBOT_BACKEND_DEVICE=cuda:0`, NVIDIA devices injected into the container
  through Container Toolkit and the tracked CUDA Compose overlay.

Example overlay `.dentobot.env` fragment:

```bash
DENTOBOT_BACKEND_PYTHON=/absolute/path/to/conda/envs/dentobot/bin/python
DENTOBOT_BACKEND_EXECUTION_MODE=local
DENTOBOT_BACKEND_DEVICE=cuda:0
DENTOBOT_RENDER_DEVICE=/dev/dri/renderD128   # Mesa node, not nvidia
```

Confirm before GUI launch:

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi
"$DENTOBOT_BACKEND_PYTHON" -m dentobot_inference health --json --require-device cuda:0
./scripts/launch-dentoworkflow.bash --check-only
```

Reject `llvmpipe` / `swrast` for interactive OpenGL acceptance unless software
rendering is deliberate. A driver/library version mismatch
(`NVML` vs loaded kernel module) requires reboot after cleaning duplicate
driver packages.

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
readlink -f /sys/class/drm/renderD129/device/driver
```

For Mesa-backed Intel and AMD graphics, map the actual non-modesetting render
node into the service (Compose already takes `DENTOBOT_RENDER_DEVICE`):

```yaml
services:
  slicerros2:
    devices:
      - /dev/dri/renderD128:/dev/dri/renderD128
```

The node number may differ on multi-GPU systems. Non-root container users also
need the matching host render-group GID. AMD requires a compatible Mesa
`radeonsi` driver. Proprietary NVIDIA CUDA for the *inference* process uses
NVIDIA Container Toolkit and `Workspace/compose.cuda.yaml`; do not copy the
Intel/AMD DRM recipe blindly as a substitute for `/dev/nvidia*`.

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

### Verified workstation notes

- **IITM CPU/Intel profile:** Intel Arrow Lake-S (`i915`),
  `/dev/dri/renderD128`, Mesa Intel OpenGL 4.6, Slicer nice 0,
  `DENTOBOT_BACKEND_DEVICE=cpu`. Full procedure: `Workspace/docs/SETUP.md`.
- **NVIDIA dual-GPU profile (2026-09-07):** Ubuntu 22.04, AMD Mesa render node
  for Slicer + NVIDIA RTX 4060 for `cuda:0` inference; launcher
  `--check-only` passed with CUDA health inside the container. See logbook
  `2026-09-07` and task `PLAT-U-05`.
