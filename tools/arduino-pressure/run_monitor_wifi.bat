@echo off
REM Board soft-AP: connect Windows WiFi to DENTOBOT-Pressure (or your AP_SSID).
cd /d "%~dp0"
if not defined PRESSURE_WIFI_HOST set PRESSURE_WIFI_HOST=192.168.4.1
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe pressure_monitor.py --wifi --wifi-host %PRESSURE_WIFI_HOST% %*
) else (
  python pressure_monitor.py --wifi --wifi-host %PRESSURE_WIFI_HOST% %*
)
