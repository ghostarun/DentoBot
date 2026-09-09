@echo off
REM First-time WSL2 lab clone. Collaborator GitHub auth in WSL; this file stores no password.
setlocal EnableExtensions
call "%~dp0resolve-wsl-distribution.bat"
if errorlevel 1 exit /b 1
echo Using WSL distro: %DENTOBOT_WSL_DISTRIBUTION%
wsl.exe -d %DENTOBOT_WSL_DISTRIBUTION% --exec bash -lc "set -euo pipefail; REPO=\"$HOME/dentobot/ros2_ws/src/DentoBot\"; if [ ! -x \"$REPO/Workspace/scripts/install-lab-wsl.bash\" ]; then mkdir -p \"$HOME/dentobot/ros2_ws/src\"; git clone https://github.com/ghostarun/DentoBot.git \"$REPO\"; fi; exec \"$REPO/Workspace/scripts/install-lab-wsl.bash\""
exit /b %ERRORLEVEL%
