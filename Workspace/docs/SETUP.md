# DENTOBOT Windows and Linux Workstation Setup

Last verified: 2026-08-28

## Scope

This file defines the shared deployment contract and the supported host
profiles. The active IITM workstation remains the fully verified Ubuntu
profile. Native Windows Slicer with a WSL2 inference backend has a tracked
launcher (`PLAT-U-02`); its runtime acceptance must be repeated on a Windows 11
workstation. A third **lab** profile runs the same Linux SlicerROS2 Docker
stack inside WSL2 (`PLAT-U-04`); GUI/ROS acceptance is pending a real lab PC.

| Host profile | Slicer | External inference | Docker | ROS/SlicerROS2 |
|---|---|---|---|---|
| Windows 11 native | Native Windows Slicer | WSL2 Linux | Not required for planning | Not supported (`DENTOBOT_ROS_PROFILE=none`) |
| Windows 11 lab (WSL2) | Linux Slicer 5.10 in `dentobot-slicerros2` (WSLg) | Direct Linux Python in WSL (CPU pin) | Required | Same Ubuntu container stack; unaccepted until `PLAT-U-04` |
| Ubuntu | Pinned Linux SlicerROS2 image | Direct Linux Python | Required by the verified profile | Included and verified |

The planning/template workflow is Slicer/MRML code and remains shared. Never
install PyTorch, TotalSegmentator, nnU-Net, or the DENTOBOT inference package
into Slicer's embedded Python on either platform.

## Windows 11 + WSL2 profile

### Boundary and prerequisites

Use native Windows Slicer for DICOM, MRML, visualization, planning, geometry,
and export. Use an Ubuntu WSL2 distribution only for the dependency-heavy
Linux inference package. The process boundary is `wsl.exe --distribution ...
--exec <absolute-linux-python>`; Conda activation in another console has no
effect on Slicer.

Required components:

- Windows 11 with WSL2 and an Ubuntu distribution;
- a native Windows Slicer version compatible with DENTOWorkflow (the prior
  project baseline used Slicer 5.12.x);
- the DENTOBOT inference environment installed inside WSL2;
- for CUDA, an NVIDIA Windows driver exposing CUDA to WSL2 and the repository's
  pinned CUDA PyTorch profile;
- cached TotalSegmentator tasks 113, 115, and 298; and
- a local Windows run-record root such as `C:\DENTOBOTRuns`.

Do not use a DICOM source directory, removable media, UNC path, or network
share as the run-record root. DENTOWorkflow maps an absolute local drive path
to WSL's `/mnt/<drive>/...` form and rejects UNC paths.

### WSL backend installation

From an Ubuntu WSL2 shell, use the validated environment manifests:

```bash
cd /mnt/c/path/to/DentoBot/Inference
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
python -m pip check
python -m pytest -q
python -m dentobot_inference health --json --require-device cuda:0
```

Model acquisition is a separate explicit setup action, never a Slicer launch
side effect:

```bash
totalseg_download_weights -t craniofacial_structures
totalseg_download_weights -t teeth
```

### Windows launcher

From PowerShell in the repository root:

```powershell
Copy-Item Workspace\.dentobot.windows.env.example .dentobot.windows.env
notepad .dentobot.windows.env

powershell -ExecutionPolicy Bypass -File `
  Workspace\scripts\launch-dentoworkflow.ps1 -CheckOnly
powershell -ExecutionPolicy Bypass -File `
  Workspace\scripts\launch-dentoworkflow.ps1
```

The launcher reads the configuration as data (it does not execute it), checks
the Slicer executable and module source, runs the exact WSL backend health
command, creates the local artifact root, and supplies this non-persistent
runtime contract to Slicer:

```text
DENTOBOT_BACKEND_EXECUTION_MODE=wsl
DENTOBOT_WSL_DISTRIBUTION=<exact distro>
DENTOBOT_BACKEND_PYTHON=<absolute WSL Linux path>
DENTOBOT_RUN_ARTIFACT_ROOT=<absolute local Windows path>
DENTOBOT_BACKEND_DEVICE=cpu|cuda:0
```

Machine paths are not written into new MRB scenes when launcher configuration
is active. The UI retains a visible advanced manual override for recovery.

### Does Windows require Docker for SlicerROS2?

**Native Windows Slicer profile:** no. Imaging, segmentation, planning,
template, verification, and export do not use ROS APIs. Use
`Workspace/scripts/launch-dentoworkflow.ps1` with `DENTOBOT_ROS_PROFILE=none`.

**Windows 11 lab profile (Step 6 with ROS):** yes. Native Windows Slicer cannot
load SlicerROS2. Lab PCs run the same Linux container as Ubuntu, hosted by
WSL2 + Docker, with the GUI on WSLg. Use `install-lab-wsl.bat` /
`launch-lab-workflow.bat` / `update-lab-release.bat`. Do not load Linux
SlicerROS2 binaries into native Windows Slicer. This lab GUI path is
implemented and unpublished until a `lab/*` git tag and GHCR image exist; it
is not Ubuntu-verified and not a substitute for native Windows Slicer.

Current upstream SlicerROS2 1.2 targets Ubuntu 24.04, ROS 2 Jazzy, and
source-built Slicer 5.10/5.12. The published CI image is Linux.

References:

- https://slicer-ros2.readthedocs.io/en/devel/pages/compatibility.html
- https://slicer-ros2.readthedocs.io/en/devel/pages/getting-started.html
- https://slicer-ros2.readthedocs.io/en/devel/pages/ci-docker-image.html

### Windows 11 lab — WSL2 Linux SlicerROS2

Use this profile when a lab PC must run DENTOWorkflow **including Step 6
ROS/MoveIt simulation**. It is not native Windows Slicer. Simulation/preview
only: no hardware motion, drilling, or patient-facing use.

**Prerequisites**

- Windows 11 with WSLg, WSL2 Ubuntu 24.04, Git, and Docker Desktop (WSL2
  backend) or Docker Engine in WSL;
- a GitHub account added as a collaborator on the private DentoBot repository
  (this is the approval model; scripts store no password);
- tens of GB free for the image, `ros2_ws`, and the TotalSegmentator cache;
- CPU inference matching the Ubuntu pin (`DENTOBOT_BACKEND_DEVICE=cpu`).

**Do not zip or copy the Ubuntu overlay.** `~/dentobot` is not a git root.
Do not ship `ros2_ws/build`, `ros2_ws/install`, `ros2_ws/log`, `data/` cases,
or `graphify-out/`. Recreate the overlay inside WSL (see
`Workspace/HOST_LAYOUT.md`).

**First-time install** (from PowerShell, after collaborator access and
`wsl` / `gh auth login` or SSH in WSL):

```bat
Workspace\scripts\install-lab-wsl.bat
```

Or in WSL after cloning DentoBot:

```bash
bash ~/dentobot/ros2_ws/src/DentoBot/Workspace/scripts/install-lab-wsl.bash
```

The installer checks out the tag in `Workspace/LAB_RELEASE`, pins
`slicer_ros2_module`, runs `bootstrap-workspace.bash`, and pulls
`ghcr.io/ghostarun/dentobot/slicerros2:jazzy-moveit-sim-20260821` (tagged
locally as `dentobot/slicerros2:jazzy-moveit-sim-20260821` for Compose).
It fails closed if that git tag is not on origin yet.

Then, once per machine: edit `~/dentobot/.dentobot.env`, create the Ubuntu CPU
backend from `Inference/` (same pin as this workstation), and copy
TotalSegmentator tasks 113, 115, and 298 into
`data/model-cache/totalsegmentator` by USB/rsync. Do not download weights as a
Slicer launch side effect. Do not copy patient identifiers.

**Launch**

```bat
Workspace\scripts\launch-lab-workflow.bat
```

That wrapper calls `scripts/launch-dentoworkflow.bash` inside WSL. Treat WSLg
software/llvmpipe rendering like the CRD session: functional checks only, not
FPS acceptance.

**Update** (pinned tag only; never `integration/gui-step6`)

```bat
Workspace\scripts\update-lab-release.bat
```

Maintainer: after an explicit Git authorization, tag `lab/YYYY-MM-DD`, push
the tag, and publish the image with
`scripts/publish-lab-image.bash --push`. Lab PCs must not rebuild
`Dockerfile.slicerros2` from scratch.

## Ubuntu workspace

- Repository/workspace root: `/home/light-tarun/dentobot`
- ROS 2 workspace: `/home/light-tarun/dentobot/ros2_ws`
- Project data mount: `/home/light-tarun/dentobot/data`
- Slicer user configuration: `/home/light-tarun/dentobot/slicer-user`, bound
  to the container's active `/root/.config/slicer.org` directory
- Container definition: `/home/light-tarun/dentobot/compose.yaml`
- Git checkout: `/home/light-tarun/dentobot/ros2_ws/src/DentoBot`
- Git-tracked workspace layer:
  `/home/light-tarun/dentobot/ros2_ws/src/DentoBot/Workspace`

The workspace root remains a runtime wrapper around the ROS 2 checkout. Its
`AGENTS.md`, `compose.yaml`, `docs`, and `scripts` paths are relative symlinks
to the tracked `Workspace/` directory. This keeps the established top-level
commands while giving the existing DentoBot repository version control over
the launcher, Compose definition, active Ubuntu notes, and helper scripts.

Run Git from the checkout or through the top-level helper:

```bash
scripts/git-dentobot.bash status --short --branch
```

On a newly arranged ROS workspace, run the tracked, non-overwriting bootstrap
after placing the repository at `ros2_ws/src/DentoBot`:

```bash
ros2_ws/src/DentoBot/Workspace/bootstrap-workspace.bash
```

## Verified environment

- Host OS: Ubuntu 26.04 (Resolute Raccoon), x86_64
- Kernel: `7.0.0-28-generic`
- Docker: `29.6.2`
- Docker Compose: `v5.3.1`
- Codex CLI: `0.145.0`
- Host ROS 2: Lyrical Luth desktop, installed under `/opt/ros/lyrical`
- Host ROS development tools: `ros-dev-tools` 1.0.1
- Host ROS package count after sourcing Lyrical: 287
- Host default RMW: `rmw_fastrtps_cpp`
- Dedicated backend test runner: pytest 8.4.2
- External CPU inference stack: DENTOBOT inference 0.2.0, Python 3.12.13,
  NumPy 2.2.6, NiBabel 5.4.2, PyTorch 2.10.0+cpu,
  torchvision 0.25.0+cpu, TotalSegmentator 2.16.0, nnUNet v2 2.8.1, and
  OpenVINO 2026.2.0

## Host ROS 2 setup

ROS 2 Lyrical is the stable binary release matching Ubuntu 26.04 Resolute.
The official `ros2-apt-source` package configures the ROS repository and key.
The installed top-level packages are:

```text
ros2-apt-source 1.2.0~resolute
ros-lyrical-desktop 0.13.0-3resolute.20260617.153257
ros-dev-tools 1.0.1
```

The host environment is not sourced globally. This prevents an implicit
Lyrical environment from contaminating the separate Jazzy SlicerROS2
container workflow. Start a host ROS terminal with:

```bash
cd /home/light-tarun/dentobot
source scripts/source-host-ros2.bash
```

The helper initializes the DENTOBOT software ROS environment with:

- ROS domain ID 73 by default, overridable before sourcing with
  `DENTOBOT_ROS_DOMAIN_ID`
- subnet discovery for the host-network SlicerROS2 container
- rejection of `ROS_LOCALHOST_ONLY=1`
- refusal to overlay Lyrical when another `ROS_DISTRO` is already active
- conditional sourcing of
  `/home/light-tarun/dentobot/ros2_host_ws/install/setup.bash` if a separate
  host-native overlay is later built

Build host-native Lyrical packages in `ros2_host_ws`, separate from the
container-built Jazzy `ros2_ws` artifacts.

`rosdep` was initialized system-wide and its user cache was updated on
2026-07-31. For future package dependency resolution:

```bash
source /home/light-tarun/dentobot/scripts/source-host-ros2.bash
rosdep install --from-paths src --ignore-src --rosdistro lyrical -y
```

Run that command only in a host-native Lyrical workspace, not against the
current container-generated Jazzy build/install artifacts.

The host Lyrical repository did not expose a `ros-lyrical-moveit` or
`ros-lyrical-moveit-ros-planning-interface` package when checked on
2026-07-31. `moveit_ros_planning_interface` remains present in the Jazzy
SlicerROS2 container. Do not assume that the host desktop install includes
MoveIt.

## Container configuration

`compose.yaml` defines the `slicerros2` service:

- Image: `dentobot/slicerros2:jazzy-moveit-sim-20260821` (FROM
  `ghcr.io/rosmed/slicer_ros2_module/ci:jazzy-slicer-v5.10.0` plus MoveIt OMPL
  helpers in `Workspace/Dockerfile.slicerros2`). Lab pulls the same digest from
  GHCR as `ghcr.io/ghostarun/dentobot/slicerros2:jazzy-moveit-sim-20260821`.
- Container: `dentobot-slicerros2`
- Host networking and IPC
- X11 display forwarding
- ROS domain ID 73 by default, overridable with
  `DENTOBOT_ROS_DOMAIN_ID` when Compose is invoked
- ROS automatic discovery range `SUBNET`
- TotalSegmentator cache path supplied as `TOTALSEG_HOME_DIR`, normally
  `/workspace/data/model-cache/totalsegmentator`
- Workspace, data, and Slicer configuration bind mounts
- Long-running `sleep infinity` command for interactive development
- Docker's minimal init process for descendant reaping
- a 512-task PID ceiling, half-default CPU scheduling weight, and OOM score
  adjustment 500 so runaway development work is bounded and the host desktop
  is favored under contention
- a 30-second graceful container stop interval

The canonical Compose file is tracked at `Workspace/compose.yaml`; the
top-level `compose.yaml` is its compatibility symlink. Host mount sources are
resolved from the launcher-supplied `DENTOBOT_WORKSPACE_ROOT`, so Compose no
longer depends on the current shell directory.

The active Slicer build writes `Slicer.ini` under
`/root/.config/slicer.org`. The Compose bind now targets that exact directory,
so Additional Module Paths and other Slicer settings persist across service
recreation. The former `/root/.config/NA-MIC` target was not used by this
build.

### Local EndoPlanner inspection checkout

When
`data/SlicerEndoPlanner-main/PulpChamberOpenPlanning/PulpChamberOpenPlanning.py`
exists, the launcher adds its container directory to Slicer's module search
alongside DENTO Workflow. EndoPlanner then appears under the Endodontics
category after launch; DENTO Workflow remains the startup module.

The public EndoPlanner preview imports optional scientific packages at module
load and uses an older Markups ROI import. The local data checkout contains a
non-packaged inspection compatibility patch that makes those imports optional
and falls back to Slicer 5.10's top-level ROI class. This permits UI inspection
without installing anything into Slicer's embedded Python. It does not make
the preview algorithms complete: trained weights and multiple referenced
network, optimization, and guide-generation helpers are absent from the public
repository. Do not report its processing buttons as validated.

Slicer runs as the container's root user, so `slicer.util.pip_install(...)`
would target `/root/.local/lib/python3.12/site-packages` (or the embedded
installation depending on pip options), not the external DENTOBOT Conda
backend. No EndoPlanner dependency was installed there for this inspection.

### Built-in Slicer modules used by template finalization

DENTO Workflow Step 5C depends on Slicer's built-in `DynamicModeler` and
`Markups` modules. They are declared as scripted-module dependencies and use
the Slicer-provided VTK/MRML implementation; they do not require a Conda or
embedded-Python package installation. A Slicer build used for DENTOBOT must
therefore include both modules. The current container source build does.

The simple finalization path uses a Markups plane and Dynamic Modeler Plane
Cut. The adjustable margin path uses a surface-snapped Markups closed curve
and Dynamic Modeler Curve Cut, followed by a DENTOBOT capping/topology check.
If either built-in module is unavailable, repair or replace the Slicer build;
do not attempt to install a similarly named package into Slicer's Python.

## Backend and run-record configuration

Machine-specific configuration is stored only in the untracked workspace file
`/home/light-tarun/dentobot/.dentobot.env`. Start from the tracked template
`Workspace/.dentobot.env.example`. The active workstation sets:

```bash
DENTOBOT_BACKEND_PYTHON=/home/light-tarun/miniconda3/envs/dentobot/bin/python
DENTOBOT_BACKEND_EXECUTION_MODE=local
DENTOBOT_BACKEND_DEVICE=cpu
DENTOBOT_RENDER_DEVICE=/dev/dri/renderD128
DENTOBOT_RUN_ARTIFACT_ROOT=/workspace/data/dentobot-runs
DENTOBOT_TOTALSEG_HOME_DIR=/workspace/data/model-cache/totalsegmentator
```

The launcher validates this file and exports a small runtime contract:

- `DENTOBOT_BACKEND_PYTHON`: exact external backend interpreter;
- `DENTOBOT_BACKEND_EXECUTION_MODE=local`: Linux starts that interpreter
  directly rather than prepending `wsl.exe`;
- `DENTOBOT_BACKEND_DEVICE=cpu`: explicit device for health and segmentation;
- `DENTOBOT_BACKEND_ENV_DIR`: derived Conda environment directory mounted
  read-only at the same absolute path in the container;
- `DENTOBOT_RENDER_DEVICE`: host/container GPU render node;
- `DENTOBOT_RUN_ARTIFACT_ROOT`: container-local run-record root;
- `DENTOBOT_WORKSPACE_ROOT`: host workspace used for explicit bind sources.

DENTO Workflow uses these launcher values automatically on Ubuntu. It does
not persist their machine paths into the MRB parameter node. The displayed
manual Python and run-record fields are advanced compatibility overrides;
disable automatic launcher configuration only when deliberately testing a
different execution boundary.

Run records are not another Python environment or a folder the user must
remember. Each backend operation creates a UUID directory under the host
`data/dentobot-runs` mount containing the exported input NIfTI, returned
output, and `result.json`. They support validation and diagnosis, may contain
patient-derived image data, remain local, and are excluded from Git and the
documentation Drive mirrors.

The dedicated backend includes the repository-pinned test dependency:

```bash
/home/light-tarun/miniconda3/envs/dentobot/bin/python -m pytest --version
/home/light-tarun/miniconda3/envs/dentobot/bin/python -m pip check
```

Both commands passed on 2026-08-06 with pytest 8.4.2. No package was installed
into Slicer's embedded Python.

## Interactive Slicer rendering configuration

### General Ubuntu container guidance

Containerized Slicer needs three distinct pieces for responsive 2D/3D
rendering:

1. a working host kernel graphics driver and DRM render node;
2. a compatible userspace OpenGL/Mesa or vendor driver inside the container;
3. explicit access to the render device in Compose.

Identify the host adapter, driver, and render nodes before editing Compose:

```bash
lspci -nnk | grep -A4 -Ei 'vga|3d|display'
ls -l /dev/dri
readlink -f /sys/class/drm/renderD128/device/driver
```

For Mesa-backed Intel and AMD graphics, pass the required non-modesetting
render node rather than the display-controller node when possible:

```yaml
services:
  slicerros2:
    devices:
      - /dev/dri/renderD128:/dev/dri/renderD128
```

`renderD128` is common for a single GPU but is not universal. Multi-GPU hosts
may expose `renderD129` or another node; map the node associated with the
intended adapter. If Slicer runs as a non-root container user, also grant the
host render-group GID through `group_add` or an equivalent least-privilege
policy. Do not use broad privileged-container access as a rendering fix.

AMD Mesa systems follow the same DRM-render-node pattern but require a
compatible `radeonsi` userspace driver. Proprietary NVIDIA systems normally
use NVIDIA Container Toolkit and its Compose GPU reservation/device contract;
the Intel `/dev/dri` recipe must not be copied blindly to NVIDIA hardware.

After saving and closing any open Slicer scene, use the launcher so its full
runtime contract is supplied and Compose recreates the service when needed:

```bash
scripts/launch-dentoworkflow.bash --check-only
docker exec dentobot-slicerros2 test -c /dev/dri/renderD128
```

Confirm renderer identity instead of assuming that a visible window implies
GPU acceleration. `glxinfo -B` is suitable when `mesa-utils` is already
installed. Inside Slicer, the Python Interactor can report the active render
window capabilities:

```python
renderWindow = slicer.app.layoutManager().threeDWidget(0).threeDView().renderWindow()
print(renderWindow.ReportCapabilities())
```

Reject `llvmpipe` and `swrast` for the interactive workflow unless software
rendering is an explicitly accepted diagnostic mode.

### Chrome Remote Desktop virtual display

Chrome Remote Desktop (CRD) creates a separate X11 desktop and normally does
not use the physical console display `:0`.

#### Cursor IDE on CRD (`cursor-xfce`)

The normal Cursor desktop icon reuses the local GNOME Electron singleton, so
it often never opens a window on the CRD display. Launch Cursor on CRD with:

```bash
/home/light-tarun/.local/bin/cursor-xfce
# or the "Cursor (Remote XFCE)" application menu entry
```

By default (`CURSOR_XFCE_PROFILE=auto`), that launcher:

- uses the host profile `~/.config/Cursor` when no host Cursor is running, so
  CRD shares the same agent/chat history as the local desktop
- falls back to `~/.config/cursor-crd-profile` when the host profile is already
  in use, to avoid SQLite / singleton conflicts

Force a profile when needed:

```bash
CURSOR_XFCE_PROFILE=host /home/light-tarun/.local/bin/cursor-xfce   # share host chats (quit local Cursor first)
CURSOR_XFCE_PROFILE=crd  /home/light-tarun/.local/bin/cursor-xfce   # isolated CRD profile
```

Quit the currently open CRD Cursor window and relaunch via `cursor-xfce`
after this change; an already-running CRD instance keeps its old profile until
restarted.

Open a terminal inside the CRD desktop and run the normal top-level DENTO
Workflow launcher; do not export a remembered display number manually:

```bash
/home/light-tarun/dentobot/scripts/launch-dentoworkflow.bash
```

The launcher inherits that terminal's current `DISPLAY`, passes it through
Compose and the final `docker exec`, grants container root scoped X11 access
with `xhost +SI:localuser:root`, and revokes that access on exit. `docker
compose up -d` recreates the service when its display environment changed. A
terminal multiplexer or a particular terminal application is not required.
The host Docker service must be active; if `/var/run/docker.sock` is absent,
start `docker.service` through the host service manager before retrying. The
launcher allocates Docker's pseudo-TTY only when both its input and output are
terminals, so the same command also works from Cursor and other non-TTY
automation while remaining attached until Slicer closes.
The launcher starts the simulation stack in its own process group. When Slicer
closes—even with the pinned SlicerROS2 build's known VTK-leak exit code—the
launcher sends bounded INT, TERM, then KILL escalation to that owned group so
ROS and MoveIt children cannot remain orphaned.
The current verified CRD session reported:

```text
DISPLAY=:20.0
XAUTHORITY=/home/light-tarun/.Xauthority
XDG_SESSION_TYPE=x11
CHROME_REMOTE_DESKTOP_SESSION=1
```

On 2026-08-11 the developer confirmed that this launcher displayed container
Slicer in the CRD desktop and opened DENTO Workflow. Closing Slicer ended the
launcher; that observed termination was not an application-start failure.
Future CRD sessions may receive a different display number, which is why the
launcher must be started from a terminal in the currently viewed CRD session.

CRD currently exposes `llvmpipe` software rendering on this workstation. Use
it for functional workflow and visual correctness checks only, not for FPS,
OpenGL, or GPU-performance acceptance. For hardware-rendering validation, use
the physical graphical session through GNOME Desktop Sharing/RDP and confirm
the Intel renderer with `ReportCapabilities()` or `glxinfo -B`.

### Workstation stability and live status

The reusable SlicerROS2 service runs its idle command below Docker's minimal
init, caps the container at 512 tasks, lowers its relative CPU scheduling
weight, and raises its OOM sacrifice score. The PID cap counts threads as well
as processes. It is intentionally generous for Slicer and CPU inference but
prevents an abandoned test tree from consuming the whole host. No container
RAM limit is imposed because the verified CPU segmentation workload has not
established a safe peak-memory cap.

Headless Bridge B phases own an exact host Xvfb PID and always terminate it.
Each phase has an internal 180-second process-group timeout plus a 45-second
outer Docker-client guard. Override the phase timeout only deliberately:

```bash
DENTOBOT_SLICER_TEST_TIMEOUT_SECONDS=300 \
  scripts/test-mrml-nifti-roundtrip.bash
```

Before leaving the workstation, or when remote interaction feels slow, run:

```bash
scripts/check-workstation-health.bash
systemctl is-active chrome-remote-desktop@"${USER}".service
```

The report shows RAM/swap, CRD, container CPU/memory/PIDs, zombies, active
Slicer/Xvfb/backend processes, and top host CPU users. Save the MRB and close
Slicer normally before intentionally recreating or stopping the container.

The developer deliberately retains CRD's private virtual Xfce desktop. A
physical GNOME login may therefore report the same account as already active;
force-stopping that virtual session before local login is accepted operational
behavior. Do not replace CRD with physical-session mirroring merely to remove
that prompt.

On 2026-08-17 journal accounting confirmed that the GDM Wayland greeter had
consumed 2 days 23 hours of CPU over 3 days of wall time while CRD/Xfce was
active. The workstation now keeps CRD/Xfce unchanged but configures only the
physical GDM path for Xorg in `/etc/gdm3/custom.conf`. The previous file is
retained as `/etc/gdm3/custom.conf.pre-dentobot-20260817`. This takes effect
after the next reboot or GDM restart; do not restart GDM with unsaved local
desktop work.

The rotational system disk also uses this persistent policy in
`/etc/sysctl.d/99-dentobot-workstation-stability.conf`:

```text
vm.swappiness = 10
vm.dirty_background_bytes = 134217728
vm.dirty_bytes = 536870912
```

The values were applied live on 2026-08-17. They retain swap but discourage
early swap and bound dirty-page writeback to avoid multi-gigabyte flush bursts
on the HDD. `systemd-oomd` remains enabled, active, and responsible for its
existing user-session memory-pressure policy. The workstation health script
verifies all three kernel values, the configured GDM path, and OOM service.
Overnight CRD observation after reboot remains required before calling the
host-stutter issue closed.

### Verified DENTOBOT Intel integrated-graphics case

This workstation uses Intel Arrow Lake-S integrated graphics, the `i915`
kernel driver, and `/dev/dri/renderD128`. `compose.yaml` passes only that
render node; it does not grant the container DRM modesetting ownership. The
SlicerROS2 image contains Mesa's Intel `iris` driver path.

Slicer 5.10's Linux background-thread implementation uses process-level
`setpriority`. With its default value, starting the background processing or
networking thread lowered the entire `SlicerApp-real` process to nice level
19. The Compose service now sets the documented
`SLICER_BACKGROUND_THREAD_PRIORITY=0` override so the interactive application
remains at normal process priority.

Before correction, the live container had no `/dev/dri` device and
`SlicerApp-real` ran at nice level 19. After service recreation on 2026-08-04,
the live Slicer process ran at nice level 0, held four descriptors to
`/dev/dri/renderD128`, and a direct GLX probe on the same display reported:

```text
vendor=Intel
renderer=Mesa Intel(R) Graphics (ARL)
version=4.6 (Compatibility Profile) Mesa 25.2.8-0ubuntu0.24.04.1
direct=yes
```

The daily launcher refuses to start if this workstation's render node is
unavailable and verifies both the container device and priority override. It
does not silently accept a software-rendering fallback. If this repository is
moved to another Ubuntu host, update the configured render-node path only
after identifying that host's actual adapter and device.

Do not recreate the container while an unsaved Slicer scene is open. After
saving and closing Slicer, run:

```bash
/home/light-tarun/dentobot/scripts/launch-dentoworkflow.bash --check-only
/home/light-tarun/dentobot/scripts/launch-dentoworkflow.bash
```

Hardware-backed direct rendering and normal Slicer process priority are
verified. Comparative FPS remains workload- and scene-dependent; use the same
scene, view layout, surface visibility, and volume-rendering settings when
measuring a performance change.

## Robot-description simulation setup

The first tracked ROS 2 package is
`ros2_ws/src/DentoBot/dentobot_description`. Because the DentoBot repository
root is also detected by colcon as the generic CMake `DENTOBOT` Slicer
extension, the workspace exposes the nested ROS package through this relative
source-space link:

```text
ros2_ws/src/dentobot_description -> DentoBot/dentobot_description
```

`Workspace/bootstrap-workspace.bash` creates and validates that link without
overwriting an existing different path. Build only in the Jazzy container so
the host Lyrical environment does not reuse the container-generated build,
install, or log trees:

```bash
docker exec dentobot-slicerros2 bash -lc \
  'source /opt/ros/jazzy/setup.bash &&
   cd /workspace/ros2_ws &&
   colcon build --symlink-install --packages-select dentobot_description'
```

Run the description without a GUI for joint-state/TF inspection:

```bash
docker exec -it dentobot-slicerros2 bash -lc \
  'source /opt/ros/jazzy/setup.bash &&
   source /workspace/ros2_ws/install/setup.bash &&
   ros2 launch dentobot_description description.launch.py use_rviz:=false'
```

For manual per-joint articulation in the Ubuntu graphical session, run from a
host terminal:

```bash
cd /home/light-tarun/dentobot
./scripts/launch-dentobot-manual-rviz.bash
```

The launcher checks the reusable container, builds only
`dentobot_description`, refuses a duplicate description launch, and opens
RViz beside the package-owned PyQt manual control window. PyQt5 is an explicit
runtime dependency. Revolute controls display degrees, prismatic controls
display millimetres, and published `JointState` values use ROS radians/metres.
Move one joint at a time and verify that upstream links remain fixed, the
joint's child has the declared rotation/translation, and downstream links
follow. Use **Reset all to zero** between comparisons.

The current draft zero is the developer-selected pose formerly displayed as
J1 `25.38 deg`, J2 `0 mm`, J3 `62.46 deg`, J4 `0 mm`, J5 `1.08 deg`, and J6
`-35.28 deg`. After this update all controls display zero at that pose. The
link-1 mounting face lies parallel to RViz XY with the robot above the grid;
positive J4 motion should move primarily in negative base X. An already-open
launch retains the URDF it loaded at startup: close its terminal/windows and
rerun the launcher to see the new coordinates.

Manual mode also draws one base-frame AABB around each transformed collision
mesh. Green outlines are clear; red outlines belong to a non-adjacent pair
whose boxes are less than the default 5 mm apart. The control window lists the
warning pairs and reports the current CAD `burr` link origin in `base_link`
millimetres. Direct parent-child pairs are intentionally ignored. To test a
larger advisory margin from a direct ROS launch, use for example:

```bash
ros2 launch dentobot_description manual.launch.py coarse_clearance_mm:=10.0
```

The current detailed collision meshes duplicate the visual STLs, so the AABB
result is intentionally coarse: overlap may be a false positive and clearance
does not prove triangle, swept-path, cable, forehead/head-mount, head/mouth, or
patient clearance. The displayed burr origin is not a calibrated TCP.

`description.launch.py` accepts `joint_state_mode:=neutral` (default),
`manual`, `slicer`, or `external`. Slicer mode republishes Motion Control
slider commands as `/joint_states`. External mode starts no joint-state source
and is reserved for bounded tests/future simulation. Never run competing
publishers for this model. Neither package-owned publisher exposes a controller,
transmission, `ros2_control` hardware plugin, or hardware motion path. The
manual GUI and Slicer slider stream do not command a robot.

### SlicerROS2 Motion Control from DENTO Workflow Step 6

> Historical initial-bridge procedure (2026-08-18/19), retained only for
> diagnosis history. It is superseded by **Step 6 native placement-to-task
> simulation (updated 2026-08-24)** below. Do not connect before loading the
> local robot/base, Task Home, and reviewed limits; routine Connect no longer
> opens Motion Control or launches a fallback prompt.

Step 6 bridges the tracked `dentobot_description` stack into SlicerROS2
Motion Control without MoveIt. MRML-only Step 6 robot meshes and the ROS 2
robot are separate representations; the bridge parents the SlicerROS2 TF root
under the Step 6 robot-base transform so phantom framing and base nudging stay
aligned. Motion Control sliders stream simulated joint positions on
`dentobot/slicer_joint_positions`; `dentobot_slicer_joint_state_publisher`
republishes them as `/joint_states`. Stop any neutral or manual joint-state
launch before connecting.

**Prerequisites**

- Container `dentobot-slicerros2` running with host networking (ROS domain 73
  by default).
- Slicer opened via `scripts/launch-dentoworkflow.bash`. That launcher sources
  the workspace, merges DENTO Workflow into `SLICER_ROS2_MODULE_PATHS`, and
  runs `ros2 launch slicer_ros2_module slicer.launch.py`. Do not start a host
  or Windows Slicer for this button; those processes have no ROS2 module.
- If Connect reports that the ROS2 Slicer module is missing, reload the
  DENTOBOT extension first (the current container Slicer already has
  SlicerROS2 paths). If this window is host or Windows Slicer, close it and
  relaunch with the script above. Reloading cannot install SlicerROS2 into a
  host Slicer. Connect then offers the MRML robot fallback so place/lock can
  continue.
- If Connect reports that the ros2 CLI is not available, reload the DENTOBOT
  extension. The bridge now unsets Slicer’s `PYTHONHOME` before calling
  `ros2`. Do not expect a raw `ros2` subprocess from Slicer’s Python to work.
- If Connect reports that the Slicer joint-state stack did not appear within
  8 s, reload the DENTOBOT extension. Slicer’s PATH puts SuperBuild
  `python-install/bin` first, so `slicer_joint_state_publisher` was starting
  Slicer Python and crashing (`No module named 'yaml'`) while C++
  `robot_state_publisher` stayed up. The bridge now resets PATH to Jazzy plus
  system directories before launch, stops that incomplete leftover, and keeps
  the launch log. A healthy slicer-mode stack is `/dentobot_robot_state_publisher`
  **and** `/dentobot_slicer_joint_state_publisher`.
- If Connect reports that `robot_state_publisher` is running without the
  Slicer joint publisher, reload the DENTOBOT extension and press Connect
  again. That dialog is the leftover half-stack (or a stale 1.5 s node-list
  cache). Do not start a second description launch from a terminal.

**Terminal A — ROS description stack (no RViz):**

```bash
cd /home/light-tarun/dentobot
./scripts/launch-dentobot-description-for-slicer.bash
```

This builds `dentobot_description`, starts `robot_state_publisher` plus the
Slicer joint-state publisher, and does **not** open RViz. Do not run a second
competing description launch.

**Terminal B — Slicer:**

```bash
./scripts/launch-dentoworkflow.bash
```

In **6 · Robot Placement**:

1. Optionally load the draft phantom and place landmarks.
2. Optionally use **Load / Refresh Robot** for MRML STL articulation, or skip
   directly to ROS 2.
3. Press **Start Stack & Connect Motion Control**. Inside the container this
   can also spawn the slicer-mode description launch if it is not already
   running. If a neutral or manual publisher is already up, stop it first.
   This window must come from `./scripts/launch-dentoworkflow.bash`. If the
   ROS2 module is missing, reload the DENTOBOT extension first; Connect also
   offers the MRML robot fallback so 6.1 is not blocked. Host Slicer cannot
   load SlicerROS2 — close it and relaunch with the script.
4. Slicer opens **ROS2 Motion Control** with MoveIt disabled. Live pose follows
   `/joint_states`. Moving the Motion Control sliders updates that topic
   through the Slicer joint-state publisher (visualization only).
5. Use **Disconnect ROS 2 Robot** to remove the SlicerROS2 robot and restore
   MRML link visibility.

**Load Robot defaults if using the ROS2 module manually:**

| Field | Value |
|-------|--------|
| Parameter node | `/dentobot_robot_state_publisher` |
| Parameter | `robot_description` |
| Fixed frame | `base_link` |

**Verification (container)**

```bash
docker exec dentobot-slicerros2 bash -lc \
  'source /opt/ros/jazzy/setup.bash &&
   ros2 node list | grep dentobot_slicer_joint_state_publisher &&
   ros2 topic echo /joint_states --once'
```

For the separate PyQt slider window outside Slicer, use
`./scripts/launch-dentobot-manual-rviz.bash`. Do not run that together with the
Slicer Motion Control stack.

The integrated URDF preserves the supplied CAD link/joint geometry and STL
triangles, changes mesh references to `package://` URIs, and adds only a
massless `base_link` plus identity fixed joint above the inertial CAD root for
KDL compatibility. Treat joint zeros/directions/limits, masses/inertias, mesh
scale/alignment, collision fidelity, tool/TCP/docking frames, self-collision,
and physical calibration as unverified inputs.

## graphify (Cursor + Codex codebase graph)

[graphify](https://github.com/Graphify-Labs/graphify) builds a local AST knowledge
graph so agents can run `graphify query` instead of repeatedly grepping large
trees. Code extraction is deterministic and stays on-machine; optional semantic
doc passes use the assistant model or an API key.

**Install (host Ubuntu):**

```bash
python3 -m pip install --user pipx
pipx install graphifyy          # PyPI name is graphifyy (two y's)
# ensure ~/.local/bin is on PATH
```

**Project wiring (from repository root):**

```bash
cd /home/light-tarun/dentobot
graphify cursor install         # .cursor/rules/graphify.mdc (alwaysApply)
graphify codex install          # AGENTS.md section + .codex/hooks.json
graphify update .               # AST-only index → ~/dentobot/graphify-out/ (gitignored)
```

Codex app and Codex CLI share the repository skill at
`.agents/skills/graphify/SKILL.md`. Its `agents/openai.yaml` metadata exposes a
**Graphify** entry in app skill pickers, and CLI users can invoke it explicitly
as `$graphify` (or allow its description to match a codebase-navigation
request). Codex discovers repository skills from `.agents/skills`; if an
already-running app or CLI session does not show a newly added skill, restart
Codex and open this repository again.

**Daily use:**

```bash
graphify query "<question>"
graphify path "<symbol A>" "<symbol B>"
graphify explain "<concept>"
graphify update .               # after code edits (no LLM cost)
```

In Cursor chat, `/graphify .` runs the full skill (code + optional docs). For
token economy, prefer `graphify update .` plus `graphify query` for code
questions. Regenerate the graph after substantive refactors.

The live graph is only `~/dentobot/graphify-out/`. Do not keep a second copy
under `ros2_ws/src/DentoBot/graphify-out/`; that nested tree is gitignored.

Optional: `graphify hook install` keeps the graph fresh on git commit (requires
a git repository at the project root). The Ubuntu overlay root is not a git
repository, so the hook belongs in `ros2_ws/src/DentoBot` if used.

## Shared agentic verification (Codex, Cursor, Claude)

The tracked cross-tool policy is
`Workspace/docs/AGENTIC_VERIFICATION_PROTOCOL.md`; the check/resource inventory
is `Testing/verification_matrix.json`. The repository entrypoints are:

- `AGENTS.md` and `Workspace/AGENTS.md` for Codex-compatible agents;
- `.cursor/rules/dentobot-verification.mdc` for Cursor; and
- `CLAUDE.md` for Claude.

The workspace bootstrap links the tracked Claude entrypoint and Cursor rule
into `~/dentobot`, alongside the existing `AGENTS.md` link. Re-run it after a
fresh checkout or overlay reconstruction:

```bash
ros2_ws/src/DentoBot/Workspace/bootstrap-workspace.bash
```

Use `DENTO-VERIFY PLAN p0` to obtain a no-execution proposal. `DENTO-VERIFY p0`
still requires explicit approval of the displayed commands/resources before
workers execute. Static/pure checks may be delegated in parallel; Slicer, ROS
domain 73, MoveIt, Docker runtime, display, install-tree, and MRML operations
are one serialized lane. Complete worker logs remain under
`/tmp/dentobot-verification/<run-id>/` and are not committed.

## Host Arduino pressure monitor

The live pneumatic-pressure GUI is a host-only sensing bench tracked in the
DentoBot git checkout:

- script: `tools/arduino-pressure/pressure_monitor.py`
- firmware: `tools/arduino-pressure/firmware/pressure_monitor/pressure_monitor.ino`
  (14-bit, 460800 baud, `seq,micros,raw_adc`, default **1000 Hz** paced from
  MPX5700 tR=1.0 ms; host may send `RATE <hz>` in 200–1500)
- interpreter: `/home/light-tarun/pressure-env/bin/python` (Python 3.14.6)
- verified packages: `numpy 2.5.2`, `pyserial 3.5`, `PyQt6 6.11.0`,
  `pyqtgraph 0.14.0`
- serial: Arduino UNO WiFi R4 at 460800 baud; pass `--port` or
  `PRESSURE_PORT` (Ubuntu default `/dev/ttyACM0`, Windows `COM3`). The
  account `light-tarun` is in `dialout`
- CSV output: `tools/arduino-pressure/pressure_runs/run_<timestamp>/`, created
  only after **Start Recording + Cues**. Run folders are gitignored.
  **Stop Recording** closes that run
  and stops the auto-cue timer. Live plot continues while idle. Four linked
  plots show filtered pressure, ΔP (fast−slow), filtered dP/dt, and
  p90−p10 spread. The 1-second inset stays on the pressure plot;
  **View → 1 s live only** puts that window on all plots. **Air** defaults
  to **Hide air-off**. **Trace** defaults to **Filtered**. Tissue-boundary
  detection arms only while air is on and **DRILL IN DENTIN** is marked;
  air-off and spinup are not scored. New `samples.csv` columns keep raw
  ADC/pressure plus filtered/ΔP fields; older runs still load. While
  recording, **Start Recording + Cues** starts the stage metronome
  (default 10 s; **Cue every** 1–600 s): AIR OFF → DRILL IN AIR → DENTIN →
  PULP. **CUE NEXT STAGE** (Space) still skips ahead. F1–F4 write
  `annotations.csv` with press minus **Operator latency** (default 400 ms).
  The Live tab always shows **set fs vs measured fs**, ADC bits, MPX5700
  range, and filter taus. **Config** edits sample rate (firmware `RATE`),
  transfer-function scale/offset, and host LPF/median constants; **Apply**
  is disabled while recording. Each run writes `pipeline.json`. Analysis
  prints that fs line and can redetect from the Pipeline tab. After flashing
  the paced sketch, confirm measured Hz ≈ set Hz on the strip. Do not flash
  while another PC is recording.

Do not install these packages into Slicer, the `dentobot` Conda environment, or
the SlicerROS2 container. Cursor workspace settings select `pressure-env` and
provide a **Pressure Monitor** launch configuration. After installing the
Python and debugpy extensions, reload the Cursor window if the Run button is
missing, then open the script and use **Run Python File** or F5 with
**Pressure Monitor**.

From a host terminal in the physical graphical session:

```bash
/home/light-tarun/pressure-env/bin/python \
  /home/light-tarun/dentobot/tools/arduino-pressure/pressure_monitor.py
```

On 2026-08-17 this connected, completed a 2-second baseline calibration, and
wrote samples under the script-local `pressure_runs/` directory. From
2026-08-31 the GUI starts idle: CSV is written only between **Start
Recording + Cues** and **Stop Recording**. Closing the window flushes an
active run and releases the serial port. The GUI is sensing-only: it does
not command a robot or authorize drilling.

Post-run inspection uses the same venv:

```bash
/home/light-tarun/pressure-env/bin/python \
  /home/light-tarun/dentobot/tools/arduino-pressure/pressure_analysis.py
```

That opens the newest `pressure_runs/run_*` folder. Pass a run directory or
`samples.csv` to review a specific acquisition. `--no-gui` prints dips, peaks,
air-off/air-on fractions, load/tissue boundaries on the 50 ms median, and
anomalies. `--min-duration-ms 20` is the confirmed-event floor; shorter
triggers are listed as glitches. `--air-filter hide|highlight|all` is the GUI
display filter (default hide). `--auto-air-thresholds` estimates the
hysteresis gates from that file instead of 8/25 kPa. The inspector defaults
to filtered pressure, ΔP, and filtered dP/dt. Drag the splitter, or use
**Plots only** (F11; Esc restores) so the traces fill the window. **Show**
isolates one trace; double-click a plot does the same. **Auto Y** (default
on) scales each axis to the visible time window. Click a table row or
annotation to zoom; **Fit time** restores the whole run. If the run has
`annotations.csv`, the inspector overlays latency-corrected marks, lists
matched dips, and `--no-gui` prints them. Cursor F5 **Pressure Analysis**
launches the inspector. See `tools/arduino-pressure/README.md` for Ubuntu
and Windows venv setup.

## Host Record3D / iPhone LiDAR scan viewer

The optical-scan inspector is a host-only PyQt6/vispy tool for Record3D OBJ
point-cloud exports (coloured `v x y z r g b` vertices in iPhone camera
metres, usually with no faces):

- script: `scripts/view_record3d_scan.py`
- interpreter: `/home/light-tarun/pressure-env/bin/python`
- extra packages in that venv: `vispy 0.16.2`, `PyOpenGL 3.1.10`,
  `freetype-py 2.5.1`
- inputs: a `.zip` of numbered OBJ frames, a folder of OBJ files, or one OBJ
- local example: `/home/light-tarun/dentobot/data/3dscan_iphone.zip`
  (kept outside Git)

Do not install vispy or PyOpenGL into Slicer, the `dentobot` Conda
environment, or the SlicerROS2 container. Cursor provides a **Record3D Scan
Viewer** launch configuration. From a host terminal in the graphical session:

```bash
/home/light-tarun/pressure-env/bin/python \
  /home/light-tarun/dentobot/scripts/view_record3d_scan.py \
  --source /home/light-tarun/dentobot/data/3dscan_iphone.zip
```

Headless catalog and first-frame stats:

```bash
/home/light-tarun/pressure-env/bin/python \
  /home/light-tarun/dentobot/scripts/view_record3d_scan.py \
  --source /home/light-tarun/dentobot/data/3dscan_iphone.zip \
  --report-only
```

Add `--scan-all` to parse every OBJ. The viewer reads the zip in place and
does not unpack it into `data/`. Coordinates remain Record3D camera metres;
this is a scan-quality check, not a Slicer RAS import, registration, or
clinical validation.

On 2026-08-18 the example zip listed 195 OBJ frames (indices 0–201, missing
163 and 174–179), parsed all frames with point counts 2,940–358,865, and
opened the vispy window on `DISPLAY=:0`.

## Verified container baseline

Verified on 2026-07-29:

- The image is present locally at digest
  `sha256:c7b69b1418d2a293c357614b9e839da32a14493e57bcec10b055c11ccced8927`.
- `dentobot-slicerros2` is running from the Compose service.
- The container reports `ROS_DISTRO=jazzy`.
- `ros2 pkg list` reports 310 packages; `rclpy`, `tf2_ros`, and
  `moveit_ros_planning_interface` are present.
- `/workspace/ros2_ws/install/setup.bash` exists.
- `ros2 pkg prefix slicer_ros2_module` resolves to
  `/workspace/ros2_ws/install/slicer_ros2_module`.
- Slicer and `SlicerApp-real` are running with the built SlicerROS2 module
  directories passed through `--additional-module-paths`.
- The upstream test suite installed `psutil 7.2.2` into the running
  container's embedded Slicer Python on 2026-07-31 because it was absent.
  This is a mutable container-layer dependency and may be installed again
  after container recreation; it is not baked into the pinned image.

The earlier browser-guided session reported an X11 launch failure followed by
a successful fix. The final success is corroborated by the running Slicer
process, but the exact failed command and corrective command were not available
to this CLI session and are not reconstructed here.

## Host/container interoperability verification

Verified on 2026-07-31 with host networking, Fast DDS, ROS domain 73, and
subnet discovery:

- Lyrical host `std_msgs/msg/String` publisher to Jazzy container subscriber
- Jazzy container `std_msgs/msg/String` publisher to Lyrical host subscriber
- Lyrical host `geometry_msgs/msg/TransformStamped` publisher to Jazzy
  container subscriber using explicitly simulated frames and values
- a final host-to-container string test using the persisted Compose defaults
  without command-level domain/discovery overrides
- all 23 upstream headless SlicerROS2 tests, including MRML publisher and
  subscriber nodes, parameters, TF2, services, synthetic image and point-cloud
  bridges, and QoS behavior
- an application-level bidirectional `sensor_msgs/msg/Image` probe between a
  Lyrical host node and Slicer MRML in the Jazzy container
- the same bidirectional image probe after restarting the Compose service

All final endpoints exited successfully. In the image probe, Slicer received
the exact host `3 x 2 x 1` mono8 payload `[11, 22, 33, 44, 55, 66]` in a
`vtkMRMLScalarVolumeNode`; the host received the exact Slicer `4 x 3` mono8
payload with first byte 7, ten middle bytes 200, and final byte 249. The
post-restart run produced the same result.

This verifies the tested standard message definitions, discovery, transport,
and the SlicerROS2 scalar-image-to-MRML pixel bridge in this workstation
configuration. A ROS `sensor_msgs/Image` does not carry the full
patient-space affine needed for CBCT. These results therefore do not validate
real DICOM/CBCT exchange, spacing/origin/direction preservation, RAS/LPS
conversion, registration accuracy, tracking, timing, safety, or robot
behavior.

The host's interactive `python3` currently resolves to Miniconda Python
3.14.6, which does not see Ubuntu's `/usr/lib/python3/dist-packages/em.py` and
cannot import Lyrical `rclpy`. Host ROS Python probes use `/usr/bin/python3`
explicitly; `scripts/host-ros2-image-probe.py` encodes that interpreter in its
shebang. Do not install ROS apt Python dependencies into the Conda base
environment to mask this boundary.

## Synthetic MRML/NIfTI Bridge B verification

Verified on 2026-07-31 using Slicer 5.10.0 in the Jazzy container and the
host's persistent `dentobot` Conda environment:

- backend: `dentobot-inference 0.2.0` loaded from the repository source
- NumPy: 2.2.6
- NiBabel: 5.4.2
- Python: 3.12.13
- backend interpreter:
  `/home/light-tarun/miniconda3/envs/dentobot/bin/python`
- container access: the environment is bind-mounted read-only at the same
  absolute path
- final synthetic evidence:
  `/home/light-tarun/dentobot/data/test-artifacts/bridge-b-l3V0RG`

The test generated a `4 x 5 x 6` int16 MRML volume with:

- KJI array shape `6 x 5 x 4`
- scalar range `-300` to `243`
- anisotropic spacing `0.4 x 0.7 x 1.2` mm
- a 30-degree in-plane oblique orientation
- RAS origin `(12.5, -8.25, 3.75)` mm
- KJI voxel SHA-256
  `26f20beee1e0aa33140dbabf55d17853bc1265e1f9a9718c1e7ba92f3d557bd6`

Slicer exported `input.nii.gz`; the real `dentobot_inference roundtrip`
command loaded, checksummed, rewrote, reloaded, and validated it; Slicer then
loaded both files and ran
`DENTOWorkflowLogic.validateMatchingVolumeGeometry`. Shape, int16 type, voxel
values, zooms, affine, and IJK-to-RAS geometry passed. Maximum observed
IJK-to-RAS difference from the defined matrix was
`4.7683715642676816e-08`, below the `1e-4` acceptance tolerance. A controlled
negative check shifted one returned RAS translation element by `0.01` mm and
confirmed that the DENTOWorkflow validator rejected it.

The input and rewritten gzip file hashes differ because compressed NIfTI
bytes are not the data-equivalence contract. Decoded voxel hashes and physical
geometry are the relevant checks, and both matched.

Use the single daily launcher from an Ubuntu desktop terminal:

```bash
/home/light-tarun/dentobot/scripts/launch-dentoworkflow.bash
```

The launcher validates the existing Conda environment and Compose
configuration, starts or unpauses the development container, checks the same
interpreter from inside the container, prepares
`/workspace/data/dentobot-runs`, grants the container's local root user
temporary X11 access, and opens Slicer directly on DENTO Workflow. Closing
Slicer returns to the terminal and revokes that X11 grant. It does not create
another venv or install packages during routine startup.

To verify the setup without opening Slicer:

```bash
/home/light-tarun/dentobot/scripts/launch-dentoworkflow.bash --check-only
```

Run the full software-only synthetic Bridge B test with:

```bash
/home/light-tarun/dentobot/scripts/test-mrml-nifti-roundtrip.bash
```

The external Conda environment now owns the complete verified Ubuntu CPU
segmentation stack. Install both `torch==2.10.0+cpu` and
`torchvision==0.25.0+cpu` from the official PyTorch CPU wheel index before
resolving `Inference/requirements/ubuntu-cpu.txt`; the generic torchvision
wheel is not an accepted substitute because its compiled operators may not
match CPU-only PyTorch. `Infrastructure/install_ubuntu_backend.sh` encodes
this order, and the launcher checks every pinned top-level version, the model
cache directory, and `dentobot_inference health --require-device cpu` before
opening Slicer.

Cached model tasks 113, 115, and 298 are stored below
`/workspace/data/model-cache/totalsegmentator`. Routine health and inference
runs are cache-only and must fail rather than download weights. The bundled
public 360 x 360 x 330 CBCT fixture completed task 113 on CPU on 2026-08-11 in
329.216 seconds, with matching input/output geometry, 54 detected labels, and
579,353 foreground voxels. Evidence is retained below
`data/dentobot-runs/ubuntu-cpu-conda-20260811-02`.

This is synthetic Bridge B evidence. It does not verify DICOM import,
real-CBCT geometry, segmentation labels, the interactive asynchronous
DENTOWorkflow adapter, or anatomical validity.

There is no robot hardware in the current environment. The project remains in
conceptual design, focused on the 3D Slicer medical-imaging workflow. The
simulated transform used frame names `image_ras_test` and
`simulated_tool_test`; it was plumbing test data, not a measured or registered
pose.

### Simulation-only Slicer Step 6 robot placement

Launch the normal Ubuntu DENTOWorkflow application:

```bash
/home/light-tarun/dentobot/scripts/launch-dentoworkflow.bash
```

The disposable open-mouth design check uses three aligned BodyParts3D 4.3
meshes stored outside Git at
`/home/light-tarun/dentobot/data/phantoms/bodyparts3d`. The workspace data bind
exposes that directory inside the container as
`/workspace/data/phantoms/bodyparts3d`. Restore the public assets as follows if
they are missing:

```bash
mkdir -p /home/light-tarun/dentobot/data/phantoms/bodyparts3d
curl -L 'https://commons.wikimedia.org/wiki/Special:Redirect/file/BodyParts3D_Neurocranium.stl' \
  -o /home/light-tarun/dentobot/data/phantoms/bodyparts3d/neurocranium.stl
curl -L 'https://commons.wikimedia.org/wiki/Special:Redirect/file/BodyParts3D_FJ6380_FJ6468_Maxilla.stl' \
  -o /home/light-tarun/dentobot/data/phantoms/bodyparts3d/maxilla.stl
curl -L 'https://commons.wikimedia.org/wiki/Special:Redirect/file/BodyParts3D_FJ6399_Mandible.stl' \
  -o /home/light-tarun/dentobot/data/phantoms/bodyparts3d/mandible.stl
sha256sum /home/light-tarun/dentobot/data/phantoms/bodyparts3d/*.stl
```

Expected SHA-256 values:

```text
598af81539edc8c055bd1bdca7050257cdb932cb4f189a9f2118ea8d8e373f9f  neurocranium.stl
66b6f1bc89960023e9ecc13d5baf2bb41075bdc48ec5ddac642e3937d06120fb  maxilla.stl
307b6e9b1b0cf90b0c132ee437e16c1b33edecfb7c42fbecfc936925cd4725d3  mandible.stl
```

The files are from BodyParts3D, © The Database Center for Life Science,
licensed under CC BY-SA 2.1 Japan. Source pages are
`BodyParts3D_Neurocranium.stl`,
`BodyParts3D_FJ6380_FJ6468_Maxilla.stl`, and
`BodyParts3D_FJ6399_Mandible.stl` on Wikimedia Commons. A different local
directory may be selected with `DENTOBOT_PHANTOM_ROOT`, which must point
directly to the directory containing the three normalized filenames above.

In the stage selector choose **6 · Robot Placement**. Use **View Controls →
Elements** and keep **Use recommended view when changing steps** on so the
viewport does not load the full 4A–5C stack plus two robots.

**6.0 Choose scene (one of):**

1. **Import Planning Package for Step 6** after completing Steps 0–5 on the
   current case. This validates that the CBCT volume, teeth segmentation,
   trajectory, docking assembly, and printable template are linked. It does
   not import a separate file bundle. Import also sets the CBCT as the slice
   background and frames the case RAS bounds (volume, segmentation, trajectory,
   docks, template, optional tooth ROI). It does **not** frame the phantom
   research origin. Recommended view: CBCT, target tooth, bounds, trajectory,
   docks, template, mount, robot.
2. **Or** load the **draft open-mouth phantom** for placement testing. Place
   the four landmarks (left TMJ, right TMJ, upper incisor, lower incisor) and
   set the approximate 40 mm opening. Recommended view: phantom, mount, robot.
   Case and phantom are mutually exclusive; switching asks for confirmation.

**6.1 Load ROS robot, place, and lock** (enabled after 6.0):

3. Press **Start Stack & Connect Motion Control** to load the robot from ROS
   into the viewport (SlicerROS2, parented to the Step 6 base). Stop any
   competing neutral/manual description launch first. This Slicer window must
   have been started with `./scripts/launch-dentoworkflow.bash`. If the ROS2
   module is still missing, the dialog offers the MRML robot fallback.
4. If ROS is unavailable, use **Fallback if ROS is unavailable → Load /
   Refresh Robot** for the MRML STL chain.
5. Create / snap the mount plane, fine-nudge, then **Lock Base Mount**.
   Unlock to adjust again.

**6.2 Task joint limits** (enabled after a robot is in the scene):

6. Each joint is one row: **min / current pose / max**. Changing min or max
   updates the value spinbox range immediately. **Apply Task Limits to
   Controls** re-clamps all six rows to the URDF mechanical envelope.
   **Reset to URDF Limits** restores that envelope. **Reset All Joints to
   Selected Zero** is on the same row of buttons.

**6.3 Trajectory motion planning** (enabled after case import + lock):

7. **Plan Motion Along Trajectory**, then **Preview Simulated Motion**.
   Phantom-only scenes cannot plan; they are for placement testing. When the
   ROS robot is connected, both buttons re-check that `/slicer` and the
   `dentobot_description` stack are still running (the same sanitized ros2
   CLI used by Connect). If that runtime is gone, Plan/Preview fail closed
   instead of driving joints into an empty graph.

Use **View Controls → Frame Visible** on the active Elements selection instead
of the old Frame Phantom + Robot control (kept only as fallback). Keyboard
nudges remain opt-in and are disabled while the mount is locked.

Step 6 remains simulation-only. The ROS bridge does not command hardware or
solve MoveIt IK. The generic phantom is not clinical jaw kinematics.

## Verification commands

```bash
uname -a
. /etc/os-release && printf '%s %s\n' "$NAME" "$VERSION"
docker --version
docker compose version
codex --version
source /home/light-tarun/dentobot/scripts/source-host-ros2.bash
printf '%s\n' "$ROS_DISTRO"
ros2 pkg list | wc -l
ros2 doctor --report
ros2 run demo_nodes_cpp talker
ros2 run demo_nodes_py listener
printf '%s\n' "$ROS_DOMAIN_ID" "$ROS_AUTOMATIC_DISCOVERY_RANGE"
docker compose ps
docker image inspect \
  dentobot/slicerros2:jazzy-moveit-sim-20260821
docker exec dentobot-slicerros2 bash -lc \
  'source /opt/ros/jazzy/setup.bash && ros2 pkg list'
docker exec dentobot-slicerros2 bash -lc \
  'source /opt/ros/jazzy/setup.bash &&
   source /workspace/ros2_ws/install/setup.bash &&
   ros2 pkg prefix slicer_ros2_module'
/usr/bin/python3 scripts/host-ros2-image-probe.py
docker exec dentobot-slicerros2 bash -lc \
  'source /opt/ros/jazzy/setup.bash &&
   source /workspace/ros2_ws/install/setup.bash &&
   xvfb-run -a /usr/bin/python3 \
   /workspace/ros2_ws/src/DentoBot/Testing/\
run_slicerros2_imaging_bridge_test.py'
```

## Not yet verified

- Interactive RViz inspection of every DENTOBOT visual mesh and frame
- Physical joint zero/direction/range, dynamic, collision, TCP, docking, and
  calibration semantics for the supplied robot description
- A custom DENTOBOT SlicerROS2 interface between Lyrical and Jazzy
- Real DICOM/CBCT or segmentation exchange through SlicerROS2, including
  spacing, origin, direction, affine, and provenance preservation
- Transform coordinate semantics, registration accuracy, or timing behavior
- A separate host-native Lyrical workspace build
- Exact reproducible X11 authorization/fix procedure
- Clean rebuild from an empty `build`, `install`, and `log` state
- Migration of DENTOWorkflow and inference Bridges A–C from Windows/WSL
- A UI-driven asynchronous Bridge B run from DENTOWorkflow and visual
  confirmation of the launcher on the Ubuntu desktop
- Hardware, robot, tracking, and drilling interfaces; no robot hardware is
  currently present. The host Arduino pressure-monitor GUI is a sensing bench
  only.

## Step 6 native placement-to-task simulation (updated 2026-08-24)

Use the normal launcher; do not start the description stack from Slicer:

```bash
cd /home/light-tarun/dentobot/ros2_ws/src/DentoBot
Workspace/scripts/launch-dentoworkflow.bash --check-only
Workspace/scripts/launch-dentoworkflow.bash
```

The launcher builds `dentobot_description` and `dentobot_moveit_config`, starts
one simulation stack, waits for `/dentobot/simulation_status`, then opens
SlicerROS2 with DENTO Workflow. The stack stops when that Slicer session exits.
On every normal GUI invocation, it first restarts the dedicated
`dentobot-slicerros2` container when that container is already running. This
bounded restart stops stale Slicer, ROS 2, MoveIt, and test descendants while
preserving the existing container filesystem and all bind-mounted workspace,
data, and configuration paths. A stopped container is simply started. Compose
may still recreate the container when its image or configuration has actually
changed. Save any open Slicer scene before invoking the launcher: the clean
restart intentionally discards unsaved in-container UI state.

The collision guard parses its versioned phase JSON with JsonCpp. The ROS
package declares `jsoncpp` as a build dependency and CMake links
`JsonCpp::JsonCpp`; do not replace this with delimiter-based string parsing,
because valid task/object labels may contain Unicode punctuation and brackets.
For a focused rebuild in the pinned container:

```bash
cd /workspace/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --base-paths src/DentoBot/dentobot_moveit_config \
  --packages-select dentobot_moveit_config --symlink-install
```

`--check-only` remains non-destructive. It does not restart a running
container and refuses the check when an active DENTOBOT Slicer or simulation
launch is found, allowing it to be used without interrupting an operator
session.

Its container-side shell keeps `errexit`, `nounset`, and `pipefail` for
DENTOBOT logic, but temporarily disables only `nounset` while sourcing the
trusted ROS Jazzy and workspace-generated setup files. This is required because
Jazzy's ament setup reads optional tracing variables such as
`AMENT_TRACE_SETUP_FILES` while they may be unset; leaving `nounset` enabled
there prevents Slicer from being invoked.
During source development, use the fixed-header **Reload Module (Dev)** button
to reload `DENTOWorkflow.py` and every `Resources/Python/DENTO*.py` helper
without restarting Slicer, the container, or the external ROS stack. The MRML
scene remains loaded. The button cancels active backend work, disconnects the
Slicer-side ROS robot, synchronously quiesces Motion Control, removes
adapter-owned publishers/subscribers and obstacle proxies, then uses Slicer's
supported scripted-module reload; reconnect the ROS robot after reloading when
Step 6 testing is required. New Empty Case performs the same Slicer-side
teardown while retaining only the hidden, non-serialized, process-owned default
ROS node.

Saved DENTOBOT MRB packages contain dental case geometry, the optional MRML
fallback robot, and the Step 6 base transform, but never the live ROS robot,
TF/parameter nodes, publishers, subscribers, MoveIt proxies, or an active-ROS
flag. Load Saved Scene uses clear/replace semantics. On restore, stale Step 4C
or Step 5C lineage deactivates Step 6 planning and requires regeneration and
verification upstream.

For a separate diagnostic terminal without Slicer, use:

```bash
Workspace/scripts/launch-dentobot-description-for-slicer.bash
```

Step 6 operator sequence:

1. **6.0 Case and task:** import a valid `.dentocase` and validate its target,
   Entry/Target line, CBCT, guides/template, and lineage. A draft phantom remains
   available for placement experiments but cannot confirm a drilling task.
2. **6.1 Robot, base, and runtime:** load the local MRML robot first. Position
   and review the explicitly labelled Manual Simulation Base with robot,
   CBCT/masks, guides, and trajectory together, then lock it. The old
   base-derived mount-plane/proxy snap is quarantined and supplies no forehead
   or registration truth. **Enable CBCT 3D Context** is
   explicit and creates/reuses one display-only renderer; CT-Bone/uCT-Skull are
   intensity presets and do not segment anatomy. The optional curved forehead
   envelope never appears automatically and is visualization-only. Press
   **Connect ROS + MoveIt (Simulation)** here; Connect stays inside
   DENTOWorkflow, aligns the live robot to the locked base, and acknowledges
   the exact collision scene without requiring Home or workspace evidence.
3. **6.2 Collision-validated Task Home:** use only a guard-accepted current
   state, then save it as Task Home. A different restored Home is reached by a
   MoveIt plan from the monitored current state and every returned waypoint is
   checked by the strict guard. The record is bound to the base, robot profile,
   collision audit, and guard policy. This is a simulation task pose, not
   physical actuator homing.
4. **6.3 ROS workspace and limits:** generate the deterministic candidate set.
   Each retained point uses MoveIt FK and static PlanningScene validity and
   stores its six-joint vector. A bounded 13-sample representative set is also
   planned from Home; unevaluated static-valid points are not called connected.
   Inspect the proposed exploration envelope and explicitly **Review & Apply**;
   generation alone does not apply it.
5. **6.4 Task confirmation:** with runtime, collision audit, Home evidence, and
   reviewed workspace evidence current, confirm one immutable task snapshot.
6. **6.5 Goal 1 — approach:** plan collision-free to the new-case default 2 mm
   pre-entry point (restored cases retain their recorded value), then plan the
   short guarded terminal move to Entry. Before enabling preview, Step 6 must
   prove complete Entry-to-Target reachability. It may vary only cylindrical-
   burr axial roll; failure requires base repositioning and cannot be accepted
   as a partial trajectory.
7. **6.6 Goal 2 — drilling preview:** after Goal 1 completes, plan and preview
   Entry-to-Target strictly inside the approved corridor. The exploratory
   guard may suppress only the configured burr-to-task-anatomy/guide contacts
   and reports every suppression. Every non-tool contact, self-collision,
   joint-bound violation, stale session, lateral escape, backtracking, or
   overshoot is rejected.

The same sequence is exposed by Legacy and New GUI. **Open Expert ROS
Diagnostics** is optional; application-level Views stays available and the
DENTOBOT toolbar returns to Robot Simulation with one click. Routine operation
does not enter `ROS2MotionControl`.

Do not press or script Execute. It is hidden and disabled, and `move_group` has
no controller. `dentobot_drill_tip_provisional` is a CAD-derived fixed frame,
not a physically calibrated TCP; the 2 mm standoff, 1 mm guard margin, contact
suppression, and generic phantom/proxy are research simulation aids only.

Manual and preview values use this ROS-only simulation chain:

```text
/dentobot/slicer_joint_positions
  → /dentobot_collision_guard
  → /dentobot/validated_joint_positions
  → /dentobot_slicer_joint_state_publisher
  → /joint_states
```

Phased preview additionally uses transient JSON contracts on
`/dentobot/task_guard_config`, `/dentobot/task_joint_command`, and
`/dentobot/task_joint_status`. The configuration and every command carry the
same immutable task fingerprint. These topics and their Slicer MRML wrappers
must never be serialized into MRML/MRB/`.dentocase`.

The guard checks the entire sampled transition, not only the requested end
state. Revolute changes are divided into increments no larger than 1 degree;
prismatic changes use increments no larger than 0.5 mm. Every sample must be
inside URDF bounds and at least 1 mm from non-allowed robot links and current
MoveIt world objects. Strict phases must be collision-free. Terminal/drilling
may suppress only the configured burr contact with fingerprinted task anatomy
and the approved guide/template; status reports this explicitly. A rejection
restores the last accepted joint values in the Step 6 and Motion Control
widgets. Locking the base uploads the current case/guide proxies; reconnect or
re-lock after changing the scene. This is a design-test guard, not certified
continuous collision safety.

No explicit IK formula must be entered. The required model configuration is:

- URDF link/joint tree with correct origins, axes, joint types, and limits;
- SRDF group `dentobot_arm`, serial chain `base_link` to
  `dentobot_drill_tip_provisional`, and intentionally allowed adjacent contacts;
- `kinematics.yaml` selecting
  `kdl_kinematics_plugin/KDLKinematicsPlugin`.

MoveIt constructs the RobotModel and KDL numerically solves a requested TCP
pose from a seed joint state. `/compute_ik` tests a single pose. The current
Step 6 `/compute_cartesian_path` call retries bounded end-effector steps down to
0.25 mm, seeds each IK solve from the preceding solution, and returns the
completed fraction; Step 6 accepts at least 0.99. Dense terminal/drilling
samples are retained. OMPL RRTConnect plans the strict current-to-pre-entry
portion after a bounded planning-scene settle/retry; it is not used to replace
the approved straight drilling centreline.

Generic Motion Control interpretation:

- **Robot:** current/grey subscribes to `/joint_states`; red goal is one target
  joint configuration, not a precalculated workspace. Both must remain mounted
  under the same Step 6 base.
- **MoveIt:** `MoveIt ready (detected)` is read-only. The fixed group is
  `dentobot_arm`; the end-effector selector shows the provisional
  `dentobot_drill_tip_provisional`. Planning time is only an upper bound for a request.
- **Manual Joint Control:** suitable for the present free-movement design test;
  every candidate still passes through the external transition guard.
- **3D Control:** Home/Last Goal/Current State choose an initial goal state.
  Current State creates the draggable TCP probe; moving it invokes numerical IK.
- **Trajectory Generation:** MoveIt plans current-to-goal after IK. A
  Simple Joint Trajectory also needs distinct start/goal states; it does not
  invent a path from an unchanged goal. Preview animates simulation only.
- **Planning Scene:** Step 6 uploads the phantom/case surfaces when the base is
  locked. Use the generic obstacle list only for diagnostics.
- The lower SlicerROS2 Parameters/Topics/TF2/Robots panels are diagnostic; no
  normal Step 6 operator edit is required there.

The workspace explorer is separate from IK. It maps a repeatable six-axis
Halton sequence into the selected task limits and runs URDF FK. It filters
other non-adjacent-link AABBs using 5 mm, excludes two displayed persistent
CAD-box false positives, and filters only the provisional TCP origin against a
subsampled environment point cloud. It does not perform exact mesh/swept-volume
environment collision or prove orientation reachability; use MoveIt IK and
planning for each candidate task pose.

### Opt-in six-workspace application shell

The development launcher and module path do not change. Legacy remains the
default. In DENTO Workflow, press **Try New GUI** in developer controls to open
the application-style shell without restarting Slicer or ROS. Press **Legacy
UI** in the shell header to return. The selection is stored in workstation
`QSettings`; it is not saved in MRML or `.dentocase`.

The shell provides **Case**, **Imaging**, **Segmentation**, **Drill Planning**,
**Guide Design**, and **Robot Simulation** around Slicer's native viewport.
Use the task-header selector for substeps. Use the theme selector for complete
light/dark task panels. Clear **Expert** for Focus mode; re-enable it to restore
the exact Slicer menu, toolbars, and module panel captured when the shell was
entered. Theme/navigation changes are presentation-only.

For the current Robot Simulation vertical slice:

1. **6.0 Case and task** validates the package and lineage.
2. **6.1 Robot/Base/Runtime** loads the local model, provides explicit CBCT
   context, locks the reviewed Manual Simulation Base, connects natively, and
   acknowledges the collision scene.
3. **6.2 Validated Task Home** saves a live accepted pose or plans and guards a
   transition from the monitored current state to a restored Home.
4. **6.3 ROS Workspace and Limits** retains MoveIt-FK/static-valid TCP+joint
   samples, separately records bounded Home-connectivity results, and requires
   review before applying the suggestion.
5. **6.4 Task Confirmation** confirms the immutable task only while the
   runtime audit/Home/workspace evidence remains current.
6. **6.5 Goal 1** plans strict pre-entry plus guarded terminal contact.
7. **6.6 Goal 2** plans guarded Entry-to-Target simulation preview.

The capability rows must name `dentobot_arm` and
`dentobot_drill_tip_provisional`. Generic Goal/IK/Plan is an optional façade
diagnostic; the routine sequence does not leave DENTOWorkflow.
6. **Plan and Preview:** plan the approved Entry-to-Target path, preview only,
   and Stop. Hardware Execute is unavailable.

After a source edit use **Reload Module (Dev)**. The external stack and case
scene remain, while the Slicer-side robot and GUI are rebuilt; reconnect before
continuing Robot Simulation. Repeated reload must leave exactly one navigation
dock, one task dock, and no duplicate callbacks.
