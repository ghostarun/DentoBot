#!/usr/bin/env bash
# Upload-only mirror: local staging folder -> Google Drive IITM Dentobot/Data.
# Watches for *.dentocase changes and runs rclone sync (debounced).

set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
ENV_FILE="${ENV_FILE:-/home/light-tarun/dentobot/data/drive-sync/gdrive-sync.env}"

usage() {
  cat <<'EOF'
Usage: gdrive-data-sync.bash {once|watch|check|bulk-slicer-saved-once}

  once   — upload staged *.dentocase only (exchange layout under drive-sync/Data)
  watch  — debounced inotify on staging folder (systemd)
  check  — verify env, rclone remote, and local root
  bulk-slicer-saved-once — one-time full upload of data/Slicer_Saved/ to
      Drive .../Data/Slicer_Saved/ (all file types; skips if done marker exists)

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
  SLICER_SAVED_ROOT="${SLICER_SAVED_ROOT:-/home/light-tarun/dentobot/data/Slicer_Saved}"
  BULK_REMOTE_SUBDIR="${BULK_REMOTE_SUBDIR:-Slicer_Saved}"
  BULK_LOG_FILE="${BULK_LOG_FILE:-${LOCAL_ROOT%/}/../gdrive-bulk-slicer-saved.log}"
  BULK_DONE_MARKER="${BULK_DONE_MARKER:-${LOCAL_ROOT%/}/../.bulk-slicer-saved-done}"
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
  # copy (not sync): upload-only; never delete remote files missing from staging
  rclone copy "${LOCAL_ROOT}" "${RCLONE_REMOTE}:" \
    --drive-root-folder-id="${DRIVE_FOLDER_ID}" \
    --filter="+ **/*.dentocase" \
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
  while true; do
    inotifywait -r -e close_write,create,move,delete,moved_to "${LOCAL_ROOT}"
    sleep "${DEBOUNCE_SECONDS}"
    while inotifywait -r -t "${DEBOUNCE_SECONDS}" \
      -e close_write,create,move,delete,moved_to "${LOCAL_ROOT}" 2>/dev/null; do
      sleep "${DEBOUNCE_SECONDS}"
    done
    run_sync || printf 'Sync failed at %s\n' "$(date --iso-8601=seconds)" >&2
  done
}

cmd_bulk_slicer_saved_once() {
  load_env
  require_tools
  local force=0
  if [[ "${2:-}" == "--force" ]]; then
    force=1
  fi
  if [[ -f "${BULK_DONE_MARKER}" && "${force}" -eq 0 ]]; then
    printf 'Bulk upload already completed (%s). Use --force to run again.\n' \
      "${BULK_DONE_MARKER}" >&2
    exit 0
  fi
  if [[ ! -d "${SLICER_SAVED_ROOT}" ]]; then
    printf 'Missing Slicer_Saved root: %s\n' "${SLICER_SAVED_ROOT}" >&2
    exit 1
  fi
  mkdir -p "$(dirname -- "${BULK_LOG_FILE}")"
  printf 'Bulk upload %s -> Drive Data/%s/ (log %s)\n' \
    "${SLICER_SAVED_ROOT}" "${BULK_REMOTE_SUBDIR}" "${BULK_LOG_FILE}"
  rclone copy "${SLICER_SAVED_ROOT}/" "${RCLONE_REMOTE}:${BULK_REMOTE_SUBDIR}/" \
    --drive-root-folder-id="${DRIVE_FOLDER_ID}" \
    --create-empty-src-dirs \
    --fast-list \
    --transfers=4 \
    --checkers=8 \
    --drive-chunk-size=64M \
    --timeout=2h \
    --log-file="${BULK_LOG_FILE}" \
    --log-level=INFO
  date --iso-8601=seconds > "${BULK_DONE_MARKER}"
  printf 'Bulk upload complete at %s\n' "$(cat "${BULK_DONE_MARKER}")"
}

main() {
  case "${1:-}" in
    once) cmd_once ;;
    watch) cmd_watch ;;
    check) cmd_check ;;
    bulk-slicer-saved-once) cmd_bulk_slicer_saved_once "$@" ;;
    -h|--help|help|"") usage ;;
    *)
      printf 'Unknown command: %s\n' "$1" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
