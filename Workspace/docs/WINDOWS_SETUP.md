# DENTOBOT Windows Installation

This is the canonical Windows installation guide. `SETUP.md` retains shared
Ubuntu/container details; this file owns Windows host preparation, WSL,
Docker-provider choice, installation, updates, and acceptance evidence.

DENTOBOT is a research simulation environment. These instructions do not
authorize robot motion, drilling, patient use, or safety-critical operation.

## Supported Windows profiles

| Profile | Use | Slicer | ROS/MoveIt |
|---|---|---|---|
| WSL2 + WSLg + Docker Engine | Default full profile | Linux Slicer in the pinned container | Included; simulation only |
| WSL2 + WSLg + Docker Desktop | Supported alternative when Desktop is healthy | Same pinned Linux container | Included; simulation only |
| Native Windows Slicer + WSL inference | Legacy Steps 0–5 fallback | Native Windows Slicer | Unavailable |

The full profile uses one Ubuntu WSL2 distribution for the repository,
external inference environment, Docker API, Linux container, and WSLg GUI.
Keep `~/dentobot` in the WSL Linux filesystem. Do not place the workspace under
`/mnt/c`, copy an Ubuntu workspace, or transfer `build/`, `install/`, `log/`,
case data, model caches, or credentials through Git.

## Release status

`origin/main` contains the September 9 Windows WSLg/CUDA integration, but the
current `Workspace/LAB_RELEASE` still selects `lab/2026-09-03`. That older tag
does not contain the complete WSLg/CUDA Compose and model-cache integration.
Do not describe a clone of `main` as a lab release, and do not install another
machine from a dirty development checkout.

The next reproducible Windows rollout must use a new accepted `lab/YYYY-MM-DD`
tag and its matching GHCR image. Until that freeze exists, record the exact
source SHA on machines using an integration revision and treat them as test
installations.

## 1. Prepare Windows and WSL

From an elevated PowerShell terminal:

```powershell
wsl --update
wsl --install -d Ubuntu-24.04
wsl -l -v
```

Use the exact distribution name printed by `wsl -l -v`; do not assume it is
`Ubuntu-24.04`. Current Ubuntu installations normally use systemd. In WSL:

```bash
ps -p 1 -o comm=
systemctl is-system-running || true
```

If PID 1 is not `systemd`, enable it in `/etc/wsl.conf`, then run
`wsl --shutdown` from PowerShell and reopen the distribution:

```ini
[boot]
systemd=true
```

For CUDA, install a current NVIDIA Windows driver with WSL support, run
`wsl --update`, and verify `nvidia-smi` inside WSL. Do not install a Linux
kernel display driver inside WSL.

## 2. Choose one Docker provider

Use exactly one provider for the selected WSL distribution. Do not combine a
direct Docker Engine with Docker Desktop WSL integration. Before continuing,
verify which daemon the `docker` client reaches and remove any ambiguity.

### Default: Docker Engine inside WSL

Install Docker Engine, Buildx, and the Compose plugin from Docker's official
Ubuntu repository. Follow the current upstream procedure rather than a copied
convenience script:

- https://docs.docker.com/engine/install/ubuntu/

Required packages:

```text
docker-ce
docker-ce-cli
containerd.io
docker-buildx-plugin
docker-compose-plugin
```

Enable the daemon and grant the workstation operator access:

```bash
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Close the WSL session after changing group membership, run `wsl --shutdown`
from PowerShell, and reopen WSL. Membership in the `docker` group grants
root-equivalent control over this Docker host; add only the intended operator.

Verify the provider before installing DENTOBOT:

```bash
docker context show
docker version
docker compose version
docker info
systemctl is-enabled docker.service
systemctl is-active docker.service
```

For CUDA containers, install and configure NVIDIA Container Toolkit using the
current NVIDIA instructions, restart Docker, and run a container GPU probe:

- https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
- https://docs.nvidia.com/cuda/wsl-user-guide/

Do not treat host `nvidia-smi` alone as container-CUDA evidence.

### Alternative: Docker Desktop WSL2 backend

Use Docker Desktop only when its WSL2 backend and integration for the selected
Ubuntu distribution are healthy. Do not install Docker Engine separately in
that distribution. Follow:

- https://docs.docker.com/desktop/features/wsl/

Confirm `docker version`, `docker compose version`, and `docker info` from the
same WSL shell used for DENTOBOT. A working Windows Docker Desktop window does
not prove that the selected distribution has Docker integration.

## 3. Authenticate without storing secrets in Git

Install Git and GitHub CLI in WSL. Authenticate the operator account to GitHub
and the private GHCR package using current GitHub guidance. Never put a token,
password, patient identifier, or machine credential in this repository,
`.dentobot.env`, a batch file, or the logbook.

The exact secret/account manifest will be added only after the operator
provides a reviewed, non-secret field structure. Until then, record only the
account/access prerequisites and successful authentication outcome.

## 4. Install an accepted DENTOBOT release

Lab and test users install immutable `lab/YYYY-MM-DD` tags. `main` is active
development. The planned `stable/lab` branch will be the moving
accepted-release pointer after the next isolated release checkpoint. Neither
branch is the runtime identity recorded for an experiment.

After the next Windows-capable lab tag is published:

```bash
mkdir -p "$HOME/dentobot/ros2_ws/src"
git clone https://github.com/ghostarun/DentoBot.git \
  "$HOME/dentobot/ros2_ws/src/DentoBot"
git -C "$HOME/dentobot/ros2_ws/src/DentoBot" fetch --tags origin
git -C "$HOME/dentobot/ros2_ws/src/DentoBot" checkout --detach \
  "refs/tags/lab/YYYY-MM-DD"
bash "$HOME/dentobot/ros2_ws/src/DentoBot/Workspace/scripts/install-lab-wsl.bash"
```

The installer must leave DentoBot at the manifest's dated tag, pin
`slicer_ros2_module` to the manifest SHA, recreate the overlay, and pull the
matching GHCR image. Lab machines do not build the base image.

## 5. Configure inference and model weights

Create the machine-local `~/dentobot/.dentobot.env` from the release example.
Use the release-pinned CPU or CUDA environment exactly; do not install the
inference stack into Slicer's embedded Python.

For the current integration design:

- CPU uses the pinned Python 3.12 CPU/OpenVINO profile.
- CUDA uses the pinned Python 3.10 `cu130` profile and matching
  `torch`/`torchvision` builds.
- `DENTOBOT_GRAPHICS_MODE=wslg` selects the WSLg Compose overlay.
- `DENTOBOT_BACKEND_DEVICE=cpu` or `cuda:0` selects the inference profile.

Install TotalSegmentator tasks 298, 115, and 113 with the release's
`install-lab-model-cache.bash` helper. Model acquisition is an explicit setup
step and never a Slicer launch side effect.

## 6. Check before launch

Run the release launcher in check-only mode:

```bash
"$HOME/dentobot/scripts/launch-dentoworkflow.bash" --check-only
```

The gate must establish the Docker API, Compose configuration, image identity,
inference interpreter and versions, selected CPU/CUDA device, WSLg mounts, and
required bind-mounted ROS packages. Fix the first failed prerequisite; do not
change model pins, disable checks, or rebuild the lab image locally.

Then launch from WSL or the release's Windows wrapper:

```bash
"$HOME/dentobot/scripts/launch-dentoworkflow.bash"
```

WSLg startup is functional evidence only. Record the renderer before making a
graphics-performance claim.

## 7. Accept a new machine

Record these non-secret identities:

```text
Windows build
WSL version
distribution name and Ubuntu version
systemd state
Docker provider, context/socket, client/server version
Docker Compose version
NVIDIA Windows driver and WSL CUDA report, when applicable
NVIDIA Container Toolkit version, when applicable
DentoBot tag and SHA
slicer_ros2_module SHA
GHCR image name and digest
inference profile and device
TotalSegmentator task presence
graphics mode and renderer
```

Acceptance requires the release check-only gate, WSLg Slicer startup, one
representative segmentation, ROS/MoveIt simulation readiness, and recorded
shutdown/cleanup behavior. These checks require the normal DENTOBOT verification
approval process. They do not authorize hardware motion.

## 8. Update a lab machine

Publish and accept a new dated release first. Then run
`update-lab-release.bash` or its `.bat` wrapper. The updater may change only the
detached DentoBot tag, pinned `slicer_ros2_module` SHA, GHCR image, and generated
ROS products. It must preserve `.dentobot.env`, cases, model cache, Slicer home,
and credentials.

Never update a lab machine by pulling `main`, checking out `stable/lab`, copying
another workstation's overlay, or force-changing a dirty lab checkout.

## Native Windows fallback

Native Windows Slicer plus WSL inference remains a Steps 0–5 fallback. It does
not load SlicerROS2 or expose Step 6. Use the explicitly named native fallback
launcher from an accepted release. Do not combine native Windows Slicer with
Linux SlicerROS2 libraries.
