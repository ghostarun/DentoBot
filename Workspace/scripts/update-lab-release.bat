@echo off
REM Pull the pinned lab/* tag and GHCR image inside WSL2. Auth via gh/SSH; no password here.
setlocal EnableExtensions
call "%~dp0resolve-wsl-distribution.bat"
if errorlevel 1 exit /b 1
echo Using WSL distro: %DENTOBOT_WSL_DISTRIBUTION%
wsl.exe -d %DENTOBOT_WSL_DISTRIBUTION% --exec bash -lc "if [ -x \"$HOME/dentobot/scripts/update-lab-release.bash\" ]; then exec \"$HOME/dentobot/scripts/update-lab-release.bash\"; elif [ -x \"$HOME/dentobot/ros2_ws/src/DentoBot/Workspace/scripts/update-lab-release.bash\" ]; then exec \"$HOME/dentobot/ros2_ws/src/DentoBot/Workspace/scripts/update-lab-release.bash\"; else echo Lab overlay is missing. Run install-lab-wsl.bat first. >&2; exit 2; fi"
exit /b %ERRORLEVEL%
