@echo off
REM Launch the Linux SlicerROS2 DENTO Workflow inside WSL2.
REM Do not use launch-dentoworkflow.ps1 (native Windows Slicer, ROS profile none).
setlocal
if "%DENTOBOT_WSL_DISTRIBUTION%"=="" set "DENTOBOT_WSL_DISTRIBUTION=Ubuntu-24.04"
wsl.exe -d %DENTOBOT_WSL_DISTRIBUTION% -- bash -lc "if [ -x \"$HOME/dentobot/scripts/launch-dentoworkflow.bash\" ]; then exec \"$HOME/dentobot/scripts/launch-dentoworkflow.bash\"; elif [ -x \"$HOME/dentobot/ros2_ws/src/DentoBot/Workspace/scripts/launch-dentoworkflow.bash\" ]; then exec \"$HOME/dentobot/ros2_ws/src/DentoBot/Workspace/scripts/launch-dentoworkflow.bash\"; else echo Lab overlay is missing. Run install-lab-wsl.bat first. >&2; exit 2; fi"
exit /b %ERRORLEVEL%
