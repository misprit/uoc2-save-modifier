@echo off
rem UOC2 save modifier launcher (Windows, no installation required)
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if not exist "python\python.exe" (
    echo [ERROR] python\python.exe is missing - the package is incomplete.
    echo Please re-extract the whole zip.
    pause
    exit /b 1
)
"python\python.exe" -m save_modifier.main %*
set "rc=%errorlevel%"
rem Keep the window open only when launched by double-click (no arguments).
rem When called by a hotkey tool, e.g. "run.bat qs", return immediately.
if "%~1"=="" pause
exit /b %rc%
