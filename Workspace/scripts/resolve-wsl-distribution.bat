@echo off
REM Resolve DENTOBOT_WSL_DISTRIBUTION for lab .bat launchers.
REM Prefer Ubuntu, then Ubuntu-24.04 / 22.04 / 20.04, else the first installed
REM distro from `wsl -l -q`. Override anytime by setting the env var first.
setlocal EnableExtensions
if not "%DENTOBOT_WSL_DISTRIBUTION%"=="" (
  endlocal & set "DENTOBOT_WSL_DISTRIBUTION=%DENTOBOT_WSL_DISTRIBUTION%" & exit /b 0
)
set "_DENTOBOT_WSL_RESOLVED="
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$names = @(& wsl.exe -l -q 2>$null | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ -ne '' }); if (-not $names) { exit 1 }; $prefer = @('Ubuntu','Ubuntu-24.04','Ubuntu-22.04','Ubuntu-20.04'); foreach ($p in $prefer) { if ($names -contains $p) { Write-Output $p; exit 0 } }; Write-Output $names[0]"`) do (
  set "_DENTOBOT_WSL_RESOLVED=%%I"
  goto :resolved
)
echo Could not detect a WSL distro. Install one or set DENTOBOT_WSL_DISTRIBUTION. >&2
endlocal
exit /b 2
:resolved
endlocal & set "DENTOBOT_WSL_DISTRIBUTION=%_DENTOBOT_WSL_RESOLVED%"
exit /b 0
