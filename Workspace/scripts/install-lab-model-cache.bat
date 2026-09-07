@echo off
REM Explicit TotalSegmentator model-cache install for the WSL2 lab overlay.
REM Idempotent. Never runs as a Slicer launch side effect.
setlocal
if "%DENTOBOT_WSL_DISTRIBUTION%"=="" set "DENTOBOT_WSL_DISTRIBUTION=Ubuntu"
wsl.exe -d %DENTOBOT_WSL_DISTRIBUTION% --exec bash -lc "if [ -x \"$HOME/dentobot/scripts/install-lab-model-cache.bash\" ]; then exec \"$HOME/dentobot/scripts/install-lab-model-cache.bash\" %*; elif [ -x \"$HOME/dentobot/ros2_ws/src/DentoBot/Workspace/scripts/install-lab-model-cache.bash\" ]; then exec \"$HOME/dentobot/ros2_ws/src/DentoBot/Workspace/scripts/install-lab-model-cache.bash\" %*; else echo Lab overlay/script missing. Run install-lab-wsl.bat first. >&2; exit 2; fi"
exit /b %ERRORLEVEL%
