#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python pressure_monitor.py "$@"
fi
exec python3 pressure_monitor.py "$@"
