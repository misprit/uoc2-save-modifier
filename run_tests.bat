@echo off
rem UOC2 save modifier —— 自动化测试（标准库 unittest，无需 pytest）
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
rem 双击运行时保留窗口；被脚本调用时不暂停。
if "%~1"=="" pause
exit /b %rc%
