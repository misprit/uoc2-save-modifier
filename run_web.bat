@echo off
rem UOC2 save modifier -- web GUI (U26 route: local HTTP bridge + Edge --app window)
rem Keep this file ASCII + CRLF only: cmd.exe mis-parses UTF-8 comments
rem after "chcp 65001" shifts its read pointer. Chinese docs live in docs\.
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
if "%~1"=="--check" (
    "python\python.exe" -m save_modifier_web.server --check
    pause
    exit /b %errorlevel%
)
rem The GUI window IS the interface: close it and everything exits (no pause here).
"python\python.exe" -m save_modifier_web.server %*
exit /b %errorlevel%
