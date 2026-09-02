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
repository_root="$(cd -- "${script_directory}/../.." && pwd -P)"
release_revision="$(git -C "${repository_root}" rev-list -n 1 \
  "refs/tags/${DENTOBOT_TAG}" 2>/dev/null || true)"
if [[ -z ${release_revision} ]]; then
  lab_unpublished_tag_message
  exit 2
fi

if ! docker image inspect "${COMPOSE_IMAGE}" >/dev/null 2>&1; then
  printf 'Local compose image is missing: %s\n' "${COMPOSE_IMAGE}" >&2
  printf 'Build it on the Ubuntu workstation with docker compose build, then retry.\n' >&2
  exit 2
fi

IFS='|' read -r image_source image_revision image_version < <(
  docker image inspect "${COMPOSE_IMAGE}" --format \
    '{{ index .Config.Labels "org.opencontainers.image.source" }}|{{ index .Config.Labels "org.opencontainers.image.revision" }}|{{ index .Config.Labels "org.opencontainers.image.version" }}'
)
if [[ ${image_source} != "https://github.com/ghostarun/DentoBot" \
  || ${image_revision} != "${release_revision}" \
  || ${image_version} != "${DENTOBOT_TAG}" ]]; then
  printf 'Local image OCI release identity is wrong.\n' >&2
  printf '  source:   %s\n' "${image_source}" >&2
  printf '  revision: %s (expected %s)\n' "${image_revision}" "${release_revision}" >&2
  printf '  version:  %s (expected %s)\n' "${image_version}" "${DENTOBOT_TAG}" >&2
  printf 'Rebuild Workspace/Dockerfile.slicerros2 with the pinned release metadata.\n' >&2
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
printf 'Keep published git tag %s immutable with this image.\n' "${DENTOBOT_TAG}"
