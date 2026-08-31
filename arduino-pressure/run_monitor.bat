@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe pressure_monitor.py %*
) else (
  python pressure_monitor.py %*
)
