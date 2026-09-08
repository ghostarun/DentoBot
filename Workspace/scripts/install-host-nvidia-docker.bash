#!/usr/bin/env bash
# One-time host setup for DENTOBOT on Ubuntu with an NVIDIA GPU.
# From the overlay root after bootstrap:
#   bash ros2_ws/src/DentoBot/Workspace/scripts/install-host-nvidia-docker.bash
# or, with scripts/ symlinked:
#   bash scripts/install-host-nvidia-docker.bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  exec sudo -E bash "$0" "$@"
fi

REAL_USER="${SUDO_USER:-${USER}}"
REAL_HOME="$(getent passwd "${REAL_USER}" | cut -d: -f6)"
WORKSPACE_ROOT="${DENTOBOT_WORKSPACE_ROOT:-${REAL_HOME}/dentobot}"

if ! command -v nvidia-smi >/dev/null 2>&1 || ! nvidia-smi >/dev/null 2>&1; then
  printf '%s\n' \
    'A working host NVIDIA driver is required before this installer.' \
    'Install the Ubuntu-recommended driver for this GPU, reboot, verify' \
    '`nvidia-smi`, then rerun. This script does not replace or purge drivers.' >&2
  exit 2
fi

echo "==> Installing Docker Engine (official apt repo)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
if ! command -v docker >/dev/null 2>&1; then
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
  fi
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

echo "==> Installing NVIDIA Container Toolkit"
if ! command -v nvidia-ctk >/dev/null 2>&1; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update -y
  apt-get install -y nvidia-container-toolkit
fi

nvidia-ctk runtime configure --runtime=docker
systemctl enable --now docker
systemctl restart docker

usermod -aG docker,render,video "${REAL_USER}"

echo
echo "Host packages installed."
echo "After a new login (docker group), verify:"
echo "  nvidia-smi"
echo "  docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi"
echo "  ${WORKSPACE_ROOT}/scripts/launch-dentoworkflow.bash --check-only"
