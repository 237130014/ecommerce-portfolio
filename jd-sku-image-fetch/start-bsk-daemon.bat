@echo off
chcp 65001 >nul
title BSK daemon - keep this window OPEN
pushd "%~dp0"

set "PORT=53899"

echo ============================================================
echo   BSK browser service (daemon) - launcher
echo ============================================================
echo.

where bsk >nul 2>nul
if errorlevel 1 (
  echo [ERROR] "bsk" was not found on PATH.
  echo.
  echo   Install it first ^(one line^), then close and re-run this file:
  echo.
  echo     PowerShell:   irm https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.ps1 ^| iex
  echo     macOS/Linux:  curl -fsSL https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.sh ^| sh
  echo.
  echo   After installing, also add the BrowserSkill extension in Chrome/Edge.
  echo.
  pause
  popd
  exit /b 1
)

echo   bsk found:
where bsk
echo.
echo   Port : %PORT%   ^(avoids 52800, which is often taken by a VPN^)
echo.
echo   KEEP THIS WINDOW OPEN while grabbing data.
echo   Close it only when you are done.
echo.
echo   First time only: log in to jd.com once in the connected browser.
echo.
echo ------------------------------------------------------------
echo.

bsk daemon start --port %PORT%

echo.
echo [daemon exited] - the browser service is now OFF.
echo If this was not intentional, just run this file again.
pause
popd
