@echo off
rem UOC2 save modifier -- automated tests (stdlib unittest, no pytest needed)
rem Keep this file ASCII + CRLF only: cmd.exe mis-parses UTF-8 comments
rem after "chcp 65001" shifts its read pointer. Chinese docs live in docs\.
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if not exist "python\python.exe" (
    echo [ERROR] python\python.exe is missing - the package is incomplete.
    pause
    exit /b 1
)
"python\python.exe" -m unittest discover -s tests -t . -v
set "rc=%errorlevel%"
rem Keep the window open only when launched by double-click (no arguments).
if "%~1"=="" pause
exit /b %rc%
