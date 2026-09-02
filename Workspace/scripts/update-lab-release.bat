@echo off
REM Pull the pinned lab/* tag and GHCR image inside WSL2.
REM Auth is GitHub collaborator access (gh auth login or SSH). No password in this file.
setlocal
if "%DENTOBOT_WSL_DISTRIBUTION%"=="" set "DENTOBOT_WSL_DISTRIBUTION=Ubuntu-24.04"
wsl.exe -d %DENTOBOT_WSL_DISTRIBUTION% -- bash -lc "if [ -x \"$HOME/dentobot/scripts/update-lab-release.bash\" ]; then exec \"$HOME/dentobot/scripts/update-lab-release.bash\"; elif [ -x \"$HOME/dentobot/ros2_ws/src/DentoBot/Workspace/scripts/update-lab-release.bash\" ]; then exec \"$HOME/dentobot/ros2_ws/src/DentoBot/Workspace/scripts/update-lab-release.bash\"; else echo Lab overlay is missing. Run install-lab-wsl.bat first. >&2; exit 2; fi"
exit /b %ERRORLEVEL%
