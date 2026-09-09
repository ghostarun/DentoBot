@echo off
REM Pull the pinned lab/* tag and GHCR image inside WSL2.
REM Bootstrap updater from origin/main so frozen lab/* pins can upgrade.
setlocal EnableExtensions
call "%~dp0resolve-wsl-distribution.bat"
if errorlevel 1 exit /b 1
echo Using WSL distro: %DENTOBOT_WSL_DISTRIBUTION%
wsl.exe -d %DENTOBOT_WSL_DISTRIBUTION% --exec bash -lc "REPO=\"$HOME/dentobot/ros2_ws/src/DentoBot\"; WORKSPACE=\"$HOME/dentobot\"; set -euo pipefail; test -d \"$REPO/.git\"; git -C \"$REPO\" fetch origin main; git -C \"$REPO\" fetch --tags origin; git -C \"$REPO\" show origin/main:Workspace/scripts/run-update-lab-release-from-main.bash >/tmp/dentobot-run-update-lab-release-from-main.bash; chmod +x /tmp/dentobot-run-update-lab-release-from-main.bash; DENTOBOT_REPO=\"$REPO\" DENTOBOT_WORKSPACE_ROOT=\"$WORKSPACE\" exec bash /tmp/dentobot-run-update-lab-release-from-main.bash"
exit /b %ERRORLEVEL%
