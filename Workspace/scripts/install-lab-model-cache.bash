#!/usr/bin/env bash
# Explicit TotalSegmentator model-cache install for lab/Ubuntu overlays.
# Idempotent. Never run as a Slicer launch side effect.
# TotalSegmentator 2.16 does not accept CLI -t teeth|craniofacial_structures;
# download by numeric task id through the Python API instead.

set -euo pipefail

canonical_script="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_directory="$(cd -- "$(dirname -- "${canonical_script}")" && pwd -P)"
repository_root="$(cd -- "${script_directory}/../.." && pwd -P)"
default_workspace_root="$(cd -- "${repository_root}/../../.." && pwd -P)"
workspace_root="${DENTOBOT_WORKSPACE_ROOT:-${default_workspace_root}}"
workspace_config="${DENTOBOT_WORKSPACE_CONFIG:-${workspace_root}/.dentobot.env}"
check_only=false

usage() {
  printf '%s\n' \
    "Usage: install-lab-model-cache.bash [--workspace-root DIR] [--check-only]" \
    "" \
    "Downloads TotalSegmentator tasks 298, 115, and 113 into" \
    "  <workspace>/data/model-cache/totalsegmentator" \
    "using DENTOBOT_BACKEND_PYTHON from .dentobot.env (or the environment)." \
    "Skips tasks that already have dataset.json, plans.json, and" \
    "checkpoint_final.pth. Simulation/preview software only."
}

while (( $# > 0 )); do
  case "$1" in
    --workspace-root)
      workspace_root="${2:?--workspace-root requires a directory}"
      shift 2
      ;;
    --check-only)
      check_only=true
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

if [[ ${workspace_root} == ~* ]]; then
  workspace_root="${HOME}${workspace_root:1}"
fi
workspace_root="$(cd -- "${workspace_root}" && pwd -P)"
cache_root="${workspace_root}/data/model-cache/totalsegmentator"

if [[ -f ${workspace_config} ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${workspace_config}"
  set +a
fi

backend_python="${DENTOBOT_BACKEND_PYTHON:-}"
if [[ -z ${backend_python} ]]; then
  for candidate in \
    "${HOME}/miniconda3/envs/dentobot/bin/python" \
    "${HOME}/miniconda3/envs/dentobot-cpu/bin/python"
  do
    if [[ -x ${candidate} ]]; then
      backend_python="${candidate}"
      break
    fi
  done
fi
if [[ -z ${backend_python} || ! -x ${backend_python} ]]; then
  printf '%s\n' \
    'No DENTOBOT_BACKEND_PYTHON found.' \
    "Set it in ${workspace_config} after creating the Conda env, then rerun:" \
    "  ${canonical_script}" >&2
  exit 2
fi

export TOTALSEG_HOME_DIR="${cache_root}"
mkdir -p "${cache_root}"

printf '%s\n' \
  "Backend Python: ${backend_python}" \
  "Model cache: ${cache_root}" \
  "TOTALSEG_HOME_DIR=${TOTALSEG_HOME_DIR}"

if ! "${backend_python}" -c 'import totalsegmentator' >/dev/null 2>&1; then
  printf '%s\n' \
    "TotalSegmentator is not importable in ${backend_python}." \
    'Install the Inference pin first (see Inference/README.md).' >&2
  exit 2
fi

set +e
status="$("${backend_python}" - <<'PY'
from pathlib import Path
import os
import sys

cache_root = Path(os.environ["TOTALSEG_HOME_DIR"]).expanduser()
results = cache_root / "nnunet" / "results"
required = (298, 115, 113)

def complete(task_id: int) -> bool:
    if not results.is_dir():
        return False
    for path in results.glob(f"Dataset{task_id:03d}_*"):
        if not path.is_dir():
            continue
        if (
            any(p.is_file() and p.stat().st_size > 0 for p in path.rglob("dataset.json"))
            and any(p.is_file() and p.stat().st_size > 0 for p in path.rglob("plans.json"))
            and any(
                p.is_file() and p.stat().st_size > 0
                for p in path.rglob("checkpoint_final.pth")
            )
        ):
            return True
    return False

missing = [task_id for task_id in required if not complete(task_id)]
present = [task_id for task_id in required if complete(task_id)]
print("present=" + ",".join(str(t) for t in present))
print("missing=" + ",".join(str(t) for t in missing))
sys.exit(0 if not missing else 3)
PY
)"
status_rc=$?
set -e
printf '%s\n' "${status}"

if [[ ${check_only} == true ]]; then
  if [[ ${status_rc} -eq 0 ]]; then
    printf 'Model cache check passed (tasks 113, 115, 298 complete).\n'
    exit 0
  fi
  printf 'Model cache check failed: required weights are incomplete.\n' >&2
  exit 2
fi

if [[ ${status_rc} -eq 0 ]]; then
  printf 'Model cache already complete; nothing to download.\n'
  exit 0
fi

printf 'Downloading missing TotalSegmentator tasks (explicit setup only)...\n'
"${backend_python}" - <<'PY'
from pathlib import Path
import os
from totalsegmentator.python_api import download_pretrained_weights
from totalsegmentator.config import get_weights_dir

cache_root = Path(os.environ["TOTALSEG_HOME_DIR"]).expanduser()
results = cache_root / "nnunet" / "results"
required = (298, 115, 113)

def complete(task_id: int) -> bool:
    if not results.is_dir():
        return False
    for path in results.glob(f"Dataset{task_id:03d}_*"):
        if not path.is_dir():
            continue
        if (
            any(p.is_file() and p.stat().st_size > 0 for p in path.rglob("dataset.json"))
            and any(p.is_file() and p.stat().st_size > 0 for p in path.rglob("plans.json"))
            and any(
                p.is_file() and p.stat().st_size > 0
                for p in path.rglob("checkpoint_final.pth")
            )
        ):
            return True
    return False

print("weights_dir", get_weights_dir(), flush=True)
for task_id in required:
    if complete(task_id):
        print(f"skip task {task_id} (already complete)", flush=True)
        continue
    print(f"download task {task_id} ...", flush=True)
    download_pretrained_weights(task_id)
    if not complete(task_id):
        raise SystemExit(f"Task {task_id} download finished but cache is incomplete")
    print(f"done task {task_id}", flush=True)
print("model_cache_ready", flush=True)
PY

printf '%s\n' \
  "Model cache ready at ${cache_root}." \
  'Bridge C / DENTOWorkflow segmentation can use the cache-only guard.'
