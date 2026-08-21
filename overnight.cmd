@echo off
rem Windows entry for the overnight /tdd -p driver (engine: scripts\overnight.py).
rem Bedtime ritual - pick one:
rem   right-click the project folder -> Send to -> overnight  (one-time: create a shortcut
rem     to this file inside shell:sendto) - runs every feature, no prompts
rem   drag the target project folder onto this file   runs every feature, no prompts
rem   double-click                                     asks for the repo root
rem   terminal: overnight.cmd [repo-root] [feat]       feat omitted = all features
setlocal
set "REPO=%~1"
set "FEAT=%~2"
if "%REPO%"=="" set /p "REPO=Target repo root (Enter = current dir): "
if not "%REPO%"=="" if not exist "%REPO%" (
  echo overnight: no such directory "%REPO%"
  goto end
)
if not "%REPO%"=="" pushd "%REPO%" || goto end
where python >nul 2>nul || (
  echo overnight: python not found on PATH
  goto restore
)
if "%FEAT%"=="" (
  python "%~dp0scripts\overnight.py"
) else (
  python "%~dp0scripts\overnight.py" "%FEAT%"
)
:restore
if not "%REPO%"=="" popd
:end
rem keep the window open when started by double-click / drag-drop
if /i "%cmdcmdline:~0,6%"=="cmd /c" pause
endlocal
