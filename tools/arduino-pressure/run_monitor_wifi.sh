#!/usr/bin/env bash
# Board soft-AP mode: PC WiFi joined to DENTOBOT-Pressure (or your AP_SSID).
set -euo pipefail
cd "$(dirname "$0")"
HOST="${PRESSURE_WIFI_HOST:-192.168.4.1}"
PYTHON="${PRESSURE_PYTHON:-/home/light-tarun/pressure-env/bin/python}"
if [ -x .venv/bin/python ]; then
  PYTHON=".venv/bin/python"
fi
exec "$PYTHON" pressure_monitor.py --wifi --wifi-host "$HOST" "$@"
