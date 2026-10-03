#!/usr/bin/env bash
# App-menu entry point: run the DENTO Workflow launcher in this terminal and
# keep the window open afterwards so launcher errors stay readable.

set -uo pipefail

script_directory="$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")" && pwd -P)"

bash "${script_directory}/launch-dentoworkflow.bash" "$@"
status=$?
printf '\nDENTO Workflow launcher exited with status %s.\n' "${status}"
if [[ -t 0 ]]; then
  read -r -p 'Press Enter to close this window. ' _ || true
fi
exit "${status}"
