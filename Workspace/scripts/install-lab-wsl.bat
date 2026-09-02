@echo off
REM First-time WSL2 lab clone. You must already be a GitHub collaborator.
REM Auth: gh auth login or git SSH in WSL. This file stores no password.
setlocal
if "%DENTOBOT_WSL_DISTRIBUTION%"=="" set "DENTOBOT_WSL_DISTRIBUTION=Ubuntu-24.04"
wsl.exe -d %DENTOBOT_WSL_DISTRIBUTION% -- bash -lc "set -euo pipefail; REPO=\"$HOME/dentobot/ros2_ws/src/DentoBot\"; if [ ! -x \"$REPO/Workspace/scripts/install-lab-wsl.bash\" ]; then mkdir -p \"$HOME/dentobot/ros2_ws/src\"; git clone https://github.com/ghostarun/DentoBot.git \"$REPO\"; fi; exec \"$REPO/Workspace/scripts/install-lab-wsl.bash\""
exit /b %ERRORLEVEL%
