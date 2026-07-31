#!/usr/bin/env bash
set -euo pipefail

repository_root="${1:-/workspace/ros2_ws/src/DentoBot}"
environment_root="${DENTOBOT_VENV_PATH:-/opt/dentobot-venv}"
python_command="${DENTOBOT_SYSTEM_PYTHON:-python3}"

if [[ ! -f "${repository_root}/Inference/pyproject.toml" ]]; then
  echo "DENTOBOT Inference package not found below ${repository_root}" >&2
  exit 2
fi

if ! "${python_command}" -c "import venv" >/dev/null 2>&1; then
  echo "Python venv support is missing. Install python3-venv first." >&2
  exit 3
fi

"${python_command}" -m venv "${environment_root}"
"${environment_root}/bin/python" -m pip install --upgrade pip setuptools wheel
"${environment_root}/bin/python" -m pip install \
  --index-url https://download.pytorch.org/whl/cpu \
  "torch==2.10.0+cpu"
"${environment_root}/bin/python" -m pip install \
  --constraint "${repository_root}/Inference/requirements/ubuntu-cpu-constraints.txt" \
  --requirement "${repository_root}/Inference/requirements/ubuntu-cpu.txt"
"${environment_root}/bin/python" -m pip install \
  --no-deps \
  --editable "${repository_root}/Inference"
"${environment_root}/bin/python" -m pip check
"${environment_root}/bin/python" -m pytest -q \
  "${repository_root}/Inference/tests"
"${environment_root}/bin/python" -m dentobot_inference health \
  --json \
  --require-device cpu
