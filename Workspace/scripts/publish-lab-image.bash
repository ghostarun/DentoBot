#!/usr/bin/env bash
# Maintainer-only: tag the local Compose SlicerROS2 image for GHCR.
# Does not create git tags, commit, or push the DentoBot repository.

set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
# shellcheck source=lab-release-lib.bash
source "${script_directory}/lab-release-lib.bash"

push_image=false

usage() {
  printf '%s\n' \
    "Usage: publish-lab-image.bash [--push]" \
    "" \
    "Tags COMPOSE_IMAGE as IMAGE from Workspace/LAB_RELEASE." \
    "With --push, uploads to GHCR. Lab PCs must not rebuild Dockerfile.slicerros2." \
    "Git commit/tag/push of DentoBot remains a separate explicit authorization."
}

while (( $# > 0 )); do
  case "$1" in
    --push)
      push_image=true
      shift
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
done

load_lab_release "$(lab_release_default_path)"

if ! docker image inspect "${COMPOSE_IMAGE}" >/dev/null 2>&1; then
  printf 'Local compose image is missing: %s\n' "${COMPOSE_IMAGE}" >&2
  printf 'Build it on the Ubuntu workstation with docker compose build, then retry.\n' >&2
  exit 2
fi

printf 'Tagging %s -> %s\n' "${COMPOSE_IMAGE}" "${IMAGE}"
docker tag "${COMPOSE_IMAGE}" "${IMAGE}"

if [[ ${push_image} != true ]]; then
  printf '%s\n' \
    "Tagged locally. Re-run with --push after: docker login ghcr.io" \
    "This script does not git tag ${DENTOBOT_TAG} or push the DentoBot repo."
  exit 0
fi

docker push "${IMAGE}"
printf 'Pushed %s\n' "${IMAGE}"
printf 'Create and push git tag %s only after an explicit commit authorization.\n' \
  "${DENTOBOT_TAG}"
