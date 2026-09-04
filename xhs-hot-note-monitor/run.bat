@echo off
setlocal
chcp 65001 >nul
echo ============================================================
echo   XiaoHongShu Hot Notes - Run
echo ============================================================
echo.

if not exist .venv (
    echo [ERROR] Not installed yet.
    echo Please double-click setup.bat first.
    echo.
    pause
    exit /b 1
)

echo Starting... (first time will pop up a QR code, scan with XiaoHongShu App)
echo.
.venv\Scripts\python.exe run.py

echo.
echo ============================================================
echo   Done! Results are in the "xhs-baseline" folder.
echo   (A dashboard page should have opened in your browser.)
echo ============================================================
echo.
pause
