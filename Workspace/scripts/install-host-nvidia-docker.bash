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

echo "==> Ensuring NVIDIA driver metapackage is installed (prefer 580 line)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y nvidia-driver-580 nvidia-utils-580 || \
  apt-get install -y nvidia-driver-550 nvidia-utils-550
# Remove a conflicting older 550 userspace/kernel set when 580 is present.
if dpkg -l 'nvidia-driver-580' 2>/dev/null | grep -q '^ii'; then
  apt-get remove -y --purge \
    'nvidia-driver-550' \
    'nvidia-utils-550' \
    'nvidia-compute-utils-550' \
    'libnvidia-*-550' \
    'linux-modules-nvidia-550-*' \
    'linux-objects-nvidia-550-*' \
    'nvidia-firmware-550-*' \
    'nvidia-kernel-source-550' \
    'nvidia-kernel-common-550' \
    2>/dev/null || true
  apt-get autoremove -y
fi

echo "==> Installing Docker Engine (official apt repo)"
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

mkdir -p "${WORKSPACE_ROOT}"
OVERRIDE="${WORKSPACE_ROOT}/compose.override.yaml"
REPO_WORKSPACE="${WORKSPACE_ROOT}/ros2_ws/src/DentoBot/Workspace"
cat > "${OVERRIDE}" <<EOF
# Local NVIDIA GPU override for DENTOBOT (not committed).
# Inference runs host Conda Python via docker exec and needs /dev/nvidia*.
services:
  slicerros2:
    build:
      context: ${REPO_WORKSPACE}
      dockerfile: Dockerfile.slicerros2
    gpus: all
    environment:
      NVIDIA_VISIBLE_DEVICES: all
      NVIDIA_DRIVER_CAPABILITIES: compute,utility,graphics,display
EOF
chown "${REAL_USER}:${REAL_USER}" "${OVERRIDE}"

echo
echo "Host packages installed."
echo "If nvidia-smi reports a Driver/library version mismatch, reboot once."
echo "After a new login (docker group), verify:"
echo "  nvidia-smi"
echo "  docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu22.04 nvidia-smi"
echo "  ${WORKSPACE_ROOT}/scripts/launch-dentoworkflow.bash --check-only"
