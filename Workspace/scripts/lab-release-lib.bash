# Shared parser for Workspace/LAB_RELEASE. Source this file; do not execute it.
# shellcheck shell=bash

lab_release_default_path() {
  local lib_directory
  lib_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  printf '%s\n' "${lib_directory}/../LAB_RELEASE"
}

load_lab_release() {
  local release_file="${1:-}"
  local line name value
  if [[ -z ${release_file} ]]; then
    printf 'LAB_RELEASE path is empty.\n' >&2
    return 2
  fi
  if [[ ! -f ${release_file} ]]; then
    printf 'LAB_RELEASE is missing: %s\n' "${release_file}" >&2
    return 2
  fi

  DENTOBOT_TAG=""
  DENTOBOT_GIT_URL=""
  SLICERROS2_GIT_URL=""
  SLICERROS2_SHA=""
  IMAGE=""
  COMPOSE_IMAGE=""

  while IFS= read -r line || [[ -n ${line} ]]; do
    line="${line%%$'\r'}"
    case "${line}" in
      ''|'#'*) continue ;;
    esac
    if [[ ${line} != *=* ]]; then
      printf 'Invalid LAB_RELEASE line: %s\n' "${line}" >&2
      return 2
    fi
    name="${line%%=*}"
    value="${line#*=}"
    name="${name%"${name##*[![:space:]]}"}"
    name="${name#"${name%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    case "${name}" in
      DENTOBOT_TAG) DENTOBOT_TAG="${value}" ;;
      DENTOBOT_GIT_URL) DENTOBOT_GIT_URL="${value}" ;;
      SLICERROS2_GIT_URL) SLICERROS2_GIT_URL="${value}" ;;
      SLICERROS2_SHA) SLICERROS2_SHA="${value}" ;;
      IMAGE) IMAGE="${value}" ;;
      COMPOSE_IMAGE) COMPOSE_IMAGE="${value}" ;;
      *)
        printf 'Unknown LAB_RELEASE key: %s\n' "${name}" >&2
        return 2
        ;;
    esac
  done < "${release_file}"

  if [[ -z ${DENTOBOT_TAG} || -z ${DENTOBOT_GIT_URL} || -z ${SLICERROS2_GIT_URL} \
    || -z ${SLICERROS2_SHA} || -z ${IMAGE} || -z ${COMPOSE_IMAGE} ]]; then
    printf 'LAB_RELEASE is missing one or more required keys.\n' >&2
    return 2
  fi
  if [[ ${DENTOBOT_TAG} != lab/* ]]; then
    printf 'DENTOBOT_TAG must start with lab/: %s\n' "${DENTOBOT_TAG}" >&2
    return 2
  fi
  if [[ ! ${SLICERROS2_SHA} =~ ^[0-9a-fA-F]{7,40}$ ]]; then
    printf 'SLICERROS2_SHA is not a git object name: %s\n' "${SLICERROS2_SHA}" >&2
    return 2
  fi
}

require_clean_git_worktree() {
  local repo="$1"
  local dirty
  dirty="$(git -C "${repo}" status --porcelain --untracked-files=normal)"
  if [[ -n ${dirty} ]]; then
    printf '%s\n' \
      "Refusing to change ${repo} because the worktree is dirty." \
      'Commit, stash, or discard lab-local edits before updating.' >&2
    printf '%s\n' "${dirty}" >&2
    return 2
  fi
}

refuse_maintainer_worktree() {
  local repo="$1"
  local branch
  branch="$(git -C "${repo}" branch --show-current 2>/dev/null || true)"
  if [[ ${branch} == "integration/gui-step6" || ${branch} == "main" || ${branch} == "master" ]]; then
    printf '%s\n' \
      "Refusing to run a lab install/update on branch ${branch}." \
      'This looks like the maintainer checkout. Lab PCs use a detached lab/* tag.' \
      'Override only with DENTOBOT_LAB_ALLOW_MAINTAINER=1 (destroys uncommitted work).' >&2
    return 2
  fi
}

lab_unpublished_tag_message() {
  printf '%s\n' \
    "Lab tag '${DENTOBOT_TAG}' is not on origin yet." \
    'The maintainer must commit the freeze, create this tag, and push it.' \
    'Lab PCs must not follow integration/gui-step6 or a dirty working tree.' >&2
}
