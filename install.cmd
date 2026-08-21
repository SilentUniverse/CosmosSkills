@echo off
setlocal

set "SCRIPT_DIR=%~dp0"

echo [HysSkills] Start one-click install...
rem Prefer pwsh: orphan-link cleanup needs $_.LinkTarget (null on PS 5.1).
set "PS=pwsh"
where pwsh >nul 2>nul || set "PS=powershell"
%PS% -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\install.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [HysSkills] Install failed. ExitCode=%EXIT_CODE%
  echo Please run again in terminal for details:
  echo powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%scripts\install.ps1" -DryRun
  pause
  exit /b %EXIT_CODE%
)

echo.
echo [HysSkills] Install completed successfully.
pause
exit /b 0
