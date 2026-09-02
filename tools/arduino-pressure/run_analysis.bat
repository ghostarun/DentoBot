@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe pressure_analysis.py %*
) else (
  python pressure_analysis.py %*
)
