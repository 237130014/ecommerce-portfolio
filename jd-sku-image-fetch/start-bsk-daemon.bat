@echo off
chcp 65001 >nul
title BSK daemon - keep this window OPEN

set PORT=53899

echo ============================================================
echo   BSK daemon launcher
echo ============================================================
echo.

where bsk >nul 2>nul
if errorlevel 1 (
  echo [ERROR] "bsk" was not found on PATH.
  echo.
  echo   Install it first, then re-open this window:
  echo     npm i -g @tencent/browser-skill
  echo   or download the binary and add its folder to PATH.
  echo.
  pause
  exit /b 1
)

echo   bsk found:
where bsk
echo.
echo   Port: %PORT%  (avoids 52800, which is often taken by a VPN)
echo   Keep this window OPEN while grabbing data.
echo   Close it only when you are done.
echo.
echo ------------------------------------------------------------
echo.

bsk daemon start --port %PORT%

echo.
echo [daemon exited]
pause
