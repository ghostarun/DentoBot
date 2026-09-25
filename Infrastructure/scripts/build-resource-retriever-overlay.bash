#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
source_dir="$repo_root/Infrastructure/resource_retriever_overlay"
[[ -d "$source_dir" ]] || { printf 'Missing overlay source: %s\n' "$source_dir" >&2; exit 1; }

base_image="${SLICERROS2_BASE_IMAGE:-dentobot/slicerros2:platu06-slicer512-00bb35055611@sha256:8a0eb790fb748d8eed3cb8f9e3749995db200026da97ec5f9de796faf1a01dc6}"
tag="dentobot/slicerros2-resource-retriever-overlay:dev-$(date -u +%Y%m%dT%H%M%SZ)-$$"

docker build \
    --build-arg "SLICERROS2_BASE_IMAGE=$base_image" \
    --build-arg COLCON_BUILD_JOBS=2 \
    --file "$repo_root/Infrastructure/Dockerfile.resource-retriever-overlay" \
    --tag "$tag" \
    "$repo_root"
