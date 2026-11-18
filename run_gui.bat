@echo off
rem UOC2 save modifier -- GUI entry (Windows, no installation required)
rem Keep this file ASCII + CRLF only: cmd.exe mis-parses UTF-8 comments
rem after "chcp 65001" shifts its read pointer. Chinese docs live in docs\.
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
rem Tcl/Tk script libraries. Tcl auto-discovers them under <package root>\lib,
rem but set them explicitly so the GUI also works if the package is relocated.
set "TCL_LIBRARY=%~dp0lib\tcl8.6"
set "TK_LIBRARY=%~dp0lib\tk8.6"
if not exist "python\python.exe" (
    echo [ERROR] python\python.exe is missing - the package is incomplete.
    echo Please re-extract the whole zip.
    pause
    exit /b 1
)
if not exist "lib\tcl8.6\init.tcl" (
    echo [ERROR] lib\tcl8.6\init.tcl is missing - the Tcl/Tk runtime is incomplete.
    echo Please re-extract the whole zip.
    pause
    exit /b 1
)
if "%~1"=="--check" (
    "python\python.exe" -m save_modifier_gui.main --check
    pause
    exit /b %errorlevel%
)
"python\python.exe" -m save_modifier_gui.main %*
set "rc=%errorlevel%"
rem Keep the window open only when launched by double-click (no arguments).
if "%~1"=="" pause
exit /b %rc%
