#!/usr/bin/env bash
# Upload-only mirror: local staging folder -> Google Drive IITM Dentobot/Data.
# Watches for *.dentocase changes and runs rclone sync (debounced).

set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
ENV_FILE="${ENV_FILE:-/home/light-tarun/dentobot/data/drive-sync/gdrive-sync.env}"

usage() {
  cat <<'EOF'
Usage: gdrive-data-sync.bash {once|watch|check}

  once   — upload now (rclone copy: *.dentocase + instructions doc)
  watch  — debounced inotify loop (for systemd)
  check  — verify env, rclone remote, and local root

Configure: copy gdrive-data-sync.env.example to data/drive-sync/gdrive-sync.env
First-time Drive auth: rclone config (remote name must match RCLONE_REMOTE)
EOF
}

load_env() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    printf 'Missing config: %s\nCopy gdrive-data-sync.env.example first.\n' "${ENV_FILE}" >&2
    exit 1
  fi
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  : "${LOCAL_ROOT:?}" "${RCLONE_REMOTE:?}" "${DRIVE_FOLDER_ID:?}"
  DEBOUNCE_SECONDS="${DEBOUNCE_SECONDS:-45}"
  LOG_FILE="${LOG_FILE:-${LOCAL_ROOT%/}/../gdrive-sync.log}"
  INSTRUCTIONS_SRC="${INSTRUCTIONS_SRC:-/home/light-tarun/dentobot/data/Slicer_Saved/DRIVE_SYNC_INSTRUCTIONS.md}"
  INSTRUCTIONS_NAME="${INSTRUCTIONS_NAME:-DRIVE_SYNC_INSTRUCTIONS.md}"
}

stage_instructions() {
  if [[ -f "${INSTRUCTIONS_SRC}" ]]; then
    cp -a "${INSTRUCTIONS_SRC}" "${LOCAL_ROOT}/${INSTRUCTIONS_NAME}"
  fi
}

require_tools() {
  command -v rclone >/dev/null || {
    printf 'rclone not installed (sudo apt install rclone)\n' >&2
    exit 1
  }
}

run_sync() {
  mkdir -p "${LOCAL_ROOT}"
  mkdir -p "$(dirname -- "${LOG_FILE}")"
  stage_instructions
  # copy (not sync): upload-only; never delete remote files missing from staging
  rclone copy "${LOCAL_ROOT}" "${RCLONE_REMOTE}:" \
    --drive-root-folder-id="${DRIVE_FOLDER_ID}" \
    --filter="+ **/*.dentocase" \
    --filter="+ ${INSTRUCTIONS_NAME}" \
    --filter="- *" \
    --create-empty-src-dirs \
    --fast-list \
    --transfers=4 \
    --checkers=8 \
    --drive-chunk-size=64M \
    --timeout=2h \
    --log-file="${LOG_FILE}" \
    --log-level=INFO
}

cmd_check() {
  load_env
  require_tools
  if ! rclone listremotes | grep -qx "${RCLONE_REMOTE}:"; then
    printf 'Remote %s: not in rclone config. Run: rclone config\n' "${RCLONE_REMOTE}" >&2
    exit 1
  fi
  printf 'OK env=%s local=%s remote=%s folder_id=%s\n' \
    "${ENV_FILE}" "${LOCAL_ROOT}" "${RCLONE_REMOTE}" "${DRIVE_FOLDER_ID}"
}

cmd_once() {
  load_env
  require_tools
  run_sync
  printf 'Upload complete at %s\n' "$(date --iso-8601=seconds)"
}

cmd_watch() {
  load_env
  require_tools
  command -v inotifywait >/dev/null || {
    printf 'inotifywait not installed (sudo apt install inotify-tools)\n' >&2
    exit 1
  }
  mkdir -p "${LOCAL_ROOT}"
  printf 'Watching %s (debounce %ss); log %s\n' \
    "${LOCAL_ROOT}" "${DEBOUNCE_SECONDS}" "${LOG_FILE}"
  run_sync
  local instructions_dir
  instructions_dir="$(dirname -- "${INSTRUCTIONS_SRC}")"
  while true; do
    inotifywait -r -e close_write,create,move,delete,moved_to \
      "${LOCAL_ROOT}" "${instructions_dir}"
    sleep "${DEBOUNCE_SECONDS}"
    while inotifywait -r -t "${DEBOUNCE_SECONDS}" \
      -e close_write,create,move,delete,moved_to \
      "${LOCAL_ROOT}" "${instructions_dir}" 2>/dev/null; do
      sleep "${DEBOUNCE_SECONDS}"
    done
    run_sync || printf 'Sync failed at %s\n' "$(date --iso-8601=seconds)" >&2
  done
}

main() {
  case "${1:-}" in
    once) cmd_once ;;
    watch) cmd_watch ;;
    check) cmd_check ;;
    -h|--help|help|"") usage ;;
    *)
      printf 'Unknown command: %s\n' "$1" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
