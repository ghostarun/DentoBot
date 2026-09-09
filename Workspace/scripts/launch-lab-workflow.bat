@echo off
REM Launch Linux SlicerROS2 DENTO Workflow in WSL2 (full Steps 0-6 WSLg profile).
setlocal EnableExtensions
call "%~dp0resolve-wsl-distribution.bat"
if errorlevel 1 exit /b 1
echo Using WSL distro: %DENTOBOT_WSL_DISTRIBUTION%
wsl.exe -d %DENTOBOT_WSL_DISTRIBUTION% --exec bash -lc "if [ -x \"$HOME/dentobot/scripts/launch-dentoworkflow.bash\" ]; then exec \"$HOME/dentobot/scripts/launch-dentoworkflow.bash\" %*; elif [ -x \"$HOME/dentobot/ros2_ws/src/DentoBot/Workspace/scripts/launch-dentoworkflow.bash\" ]; then exec \"$HOME/dentobot/ros2_ws/src/DentoBot/Workspace/scripts/launch-dentoworkflow.bash\" %*; else echo Lab overlay is missing. Run install-lab-wsl.bat first. >&2; exit 2; fi"
exit /b %ERRORLEVEL%
