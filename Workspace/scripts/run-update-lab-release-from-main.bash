#!/usr/bin/env bash
# Fetch the update-lab-release script from origin/main and run it.
# Lets frozen lab/* checkouts upgrade even when their local updater is old.

set -euo pipefail

REPO="${DENTOBOT_REPO:-$HOME/dentobot/ros2_ws/src/DentoBot}"
WORKSPACE="${DENTOBOT_WORKSPACE_ROOT:-$HOME/dentobot}"

if [[ ! -d ${REPO}/.git ]]; then
  printf 'DentoBot clone is missing: %s\n' "${REPO}" >&2
  exit 2
fi

git -C "${REPO}" fetch origin main
git -C "${REPO}" fetch --tags origin

TMP="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP}"
}
trap cleanup EXIT

mkdir -p "${TMP}/Workspace/scripts"
git -C "${REPO}" show origin/main:Workspace/scripts/update-lab-release.bash \
  >"${TMP}/Workspace/scripts/update-lab-release.bash"
git -C "${REPO}" show origin/main:Workspace/scripts/lab-release-lib.bash \
  >"${TMP}/Workspace/scripts/lab-release-lib.bash"
chmod +x "${TMP}/Workspace/scripts/update-lab-release.bash"

set +e
DENTOBOT_REPO="${REPO}" DENTOBOT_WORKSPACE_ROOT="${WORKSPACE}" \
  bash "${TMP}/Workspace/scripts/update-lab-release.bash" "$@"
status=$?
set -e
exit "${status}"
