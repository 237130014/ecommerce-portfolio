@echo off
setlocal
chcp 65001 >nul
echo ============================================================
echo   XiaoHongShu Hot Notes - One-click Setup
echo   (Only need to run this ONCE)
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Please install Python 3.9+ from:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANT: during install, check the box:
    echo   "Add Python to PATH"
    echo.
    echo After installing Python, double-click this setup.bat again.
    echo.
    pause
    exit /b 1
)

if not exist .venv (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
) else (
    echo [1/3] Virtual environment already exists, skip.
)

echo [2/3] Installing dependencies...
.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [3/3] Downloading browser core (about 100MB, please wait)...
.venv\Scripts\python.exe -m playwright install chromium

echo.
echo ============================================================
echo   Setup done!
echo   Next step: double-click run.bat to start.
echo ============================================================
echo.
pause
