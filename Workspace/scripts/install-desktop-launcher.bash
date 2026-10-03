#!/usr/bin/env bash
# Add (or --remove) a "DENTO Workflow" app-menu entry on a native Ubuntu desktop.
# The entry runs <workspace>/scripts/launch-dentobot-desktop.bash, so it always
# opens the checkout that the workspace scripts link points to. Not for WSL.

set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
repository_root="$(cd -- "${script_directory}/../.." && pwd -P)"
default_workspace_root="$(cd -- "${repository_root}/../../.." && pwd -P)"
workspace_root="${DENTOBOT_WORKSPACE_ROOT:-${default_workspace_root}}"
applications_dir="${XDG_DATA_HOME:-${HOME}/.local/share}/applications"
desktop_file="${applications_dir}/dentobot-workflow.desktop"

usage() {
  printf '%s\n' \
    "Usage: scripts/install-desktop-launcher.bash [--remove]" \
    "" \
    "Installs ${desktop_file}" \
    "which opens DENTO Workflow from ${workspace_root}/scripts in a terminal."
}

case "${1:-}" in
  "")
    ;;
  --remove)
    rm -f -- "${desktop_file}"
    printf 'Removed %s\n' "${desktop_file}"
    exit 0
    ;;
  --help|-h)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

if [[ -e /dev/dxg || -d /mnt/wslg ]]; then
  printf '%s\n' \
    'This is a WSL host; use the Windows lab shortcuts (launch-lab-workflow.bat) instead.' >&2
  exit 2
fi

entry="${workspace_root}/scripts/launch-dentobot-desktop.bash"
if [[ ! -x ${entry} ]]; then
  printf '%s\n' \
    "Workspace launcher is missing or not executable: ${entry}" \
    "Check that ${workspace_root}/scripts links to the active checkout's Workspace/scripts." >&2
  exit 2
fi

mkdir -p -- "${applications_dir}"
cat >"${desktop_file}" <<EOF
[Desktop Entry]
Type=Application
Name=DENTO Workflow
Comment=Open 3D Slicer with DENTO Workflow from the current DentoBot checkout (simulation only)
Exec="${entry}"
Icon=${repository_root}/DentalDrillNav.png
Terminal=true
Categories=Science;MedicalSoftware;
StartupNotify=false
Actions=choose-checkout;

[Desktop Action choose-checkout]
Name=Choose checkout…
Exec="${entry}" --choose-checkout
EOF
if command -v desktop-file-validate >/dev/null 2>&1; then
  desktop-file-validate "${desktop_file}"
fi
printf 'Installed %s\nIt runs %s\n' "${desktop_file}" "${entry}"
