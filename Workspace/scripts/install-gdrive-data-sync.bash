#!/usr/bin/env bash
set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
overlay_root="/home/light-tarun/dentobot"
sync_root="${overlay_root}/data/drive-sync"
env_file="${sync_root}/gdrive-sync.env"
example="${script_directory}/gdrive-data-sync.env.example"
unit_src="${script_directory}/systemd/gdrive-data-sync.service"
unit_dst="${HOME}/.config/systemd/user/gdrive-data-sync.service"

chmod +x "${script_directory}/gdrive-data-sync.bash"

mkdir -p "${sync_root}/Data/SampleStudy1"
if [[ ! -f "${env_file}" ]]; then
  cp "${example}" "${env_file}"
  printf 'Created %s\n' "${env_file}"
else
  printf 'Keeping existing %s\n' "${env_file}"
fi

mkdir -p "${HOME}/.config/systemd/user"
cp "${unit_src}" "${unit_dst}"
printf 'Installed %s\n' "${unit_dst}"

if ! rclone listremotes 2>/dev/null | grep -qx 'dentobot_gdrive:'; then
  cat <<'EOF'

Next: authorize Google Drive for rclone (one-time, browser):

  rclone config
    n) New remote
    name: dentobot_gdrive
    Storage: drive
    client_id / client_secret: leave blank (Enter)
    scope: 1 (Full access) or 2 if you prefer drive.file
    root_folder_id: leave blank
    service_account_file: leave blank
    Edit advanced config? n
    Use auto config? y   (opens browser — sign in to your Google account)

Then verify and start the watcher:

  ros2_ws/src/DentoBot/Workspace/scripts/gdrive-data-sync.bash check
  systemctl --user daemon-reload
  systemctl --user enable --now gdrive-data-sync.service
  journalctl --user -u gdrive-data-sync.service -f

Stage bundles under:
  ~/dentobot/data/drive-sync/Data/SampleStudy1/FDI*/
(only approved *.dentocase — not the whole Slicer_Saved tree)

EOF
else
  printf 'rclone remote dentobot_gdrive: already configured.\n'
  printf 'Run: systemctl --user daemon-reload && systemctl --user enable --now gdrive-data-sync.service\n'
fi
