@echo off
REM Launch the Linux SlicerROS2 DENTO Workflow inside WSL2.
REM Full Steps 0-6 WSLg profile. Native Windows fallback is explicitly Steps 0-5 only.
setlocal
if "%DENTOBOT_WSL_DISTRIBUTION%"=="" set "DENTOBOT_WSL_DISTRIBUTION=Ubuntu"
wsl.exe -d %DENTOBOT_WSL_DISTRIBUTION% --exec bash -lc "if [ -x \"$HOME/dentobot/scripts/launch-dentoworkflow.bash\" ]; then exec \"$HOME/dentobot/scripts/launch-dentoworkflow.bash\" %*; elif [ -x \"$HOME/dentobot/ros2_ws/src/DentoBot/Workspace/scripts/launch-dentoworkflow.bash\" ]; then exec \"$HOME/dentobot/ros2_ws/src/DentoBot/Workspace/scripts/launch-dentoworkflow.bash\" %*; else echo Lab overlay is missing. Run install-lab-wsl.bat first. >&2; exit 2; fi"
exit /b %ERRORLEVEL%
