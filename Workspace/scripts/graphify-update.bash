#!/usr/bin/env bash
# Refresh the authoritative overlay AST graph only.
# Always runs from ~/dentobot so agents/hooks cannot recreate the nested
# ros2_ws/src/DentoBot/graphify-out tree.
set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
# Workspace/scripts -> Workspace -> DentoBot -> src -> ros2_ws -> overlay root
overlay_root="$(cd -- "${script_directory}/../../../../.." && pwd -P)"

if [[ ! -d "${overlay_root}/ros2_ws/src/DentoBot" ]]; then
  printf 'graphify-update: could not resolve overlay root from %s\n' \
    "${script_directory}" >&2
  exit 1
fi

if ! command -v graphify >/dev/null 2>&1; then
  if [[ -x /home/light-tarun/.local/bin/graphify ]]; then
    PATH="/home/light-tarun/.local/bin:${PATH}"
    export PATH
  else
    printf 'graphify-update: graphify not on PATH\n' >&2
    exit 1
  fi
fi

mkdir -p "${overlay_root}/graphify-out"
printf '%s\n' "${overlay_root}" >"${overlay_root}/graphify-out/.graphify_root"

# Codex Linux exec often prepends this three times to every command. It is not
# a graphify rebuild failure; strip it so agents judge the real exit status.
filter_codex_stream_noise() {
  sed -e '/^Failed to create stream fd: Operation not permitted$/d'
}

cd -- "${overlay_root}"
set +e
output="$(graphify update . "$@" 2>&1)"
status=$?
set -e

printf '%s\n' "${output}" | filter_codex_stream_noise

if [[ "${status}" -ne 0 ]]; then
  printf 'graphify-update: FAILED (exit %s) under %s\n' \
    "${status}" "${overlay_root}" >&2
  exit "${status}"
fi

if ! printf '%s\n' "${output}" | grep -Eq \
  'Code graph updated|\[graphify watch\] Rebuilt:'; then
  printf 'graphify-update: incomplete output under %s\n' "${overlay_root}" >&2
  exit 1
fi

# graphify update rewrites .graphify_root to "."; keep an absolute pin.
printf '%s\n' "${overlay_root}" >"${overlay_root}/graphify-out/.graphify_root"

printf 'graphify-update: OK under %s\n' "${overlay_root}"
exit 0
