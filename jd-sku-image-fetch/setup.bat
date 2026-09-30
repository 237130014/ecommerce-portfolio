@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title JD SKU Image Fetcher - one-time setup
pushd "%~dp0"

echo ============================================================
echo    JD SKU Main-Image Fetcher  --  one-time setup
echo ============================================================
echo.
echo   This will:
echo     1) find a Python on this PC
echo     2) reuse it if openpyxl + Pillow are already there;
echo        otherwise create a private env .venv\ in this folder
echo     3) make sure openpyxl + Pillow are available
echo     4) create skus.csv from the template (if missing)
echo     5) check the bsk browser service
echo     6) run a full self-test
echo.
echo   Nothing is installed globally.
echo.

REM ---------------------------------------------------------------
REM 1) locate a base Python
REM ---------------------------------------------------------------
REM  Resolve to a real .exe path: a bare "py -3" cannot be quoted later
REM  ("%BASEPY%" x.py would look for a file literally named "py -3").
set "BASEPY="

where py >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "BASEPY=%%P"
)
if not defined BASEPY (
  for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "BASEPY=%%P"
)

if not defined BASEPY (
  echo [ERROR] Python was not found on this PC.
  echo.
  echo   Install Python 3.10 or newer from:
  echo     https://www.python.org/downloads/
  echo.
  echo   IMPORTANT: on the first screen of the installer tick
  echo     [x] Add python.exe to PATH
  echo   then run this setup again.
  echo.
  pause
  popd
  exit /b 1
)

for /f "usebackq delims=" %%V in (`"%BASEPY%" -c "import sys;print(sys.version.split()[0])"`) do set "PYVER=%%V"
echo [0/6] Found Python %PYVER%
echo        %BASEPY%
echo.

REM ---------------------------------------------------------------
REM 2) can we just reuse this Python as-is?
REM ---------------------------------------------------------------
set "USE_SYS="
"%BASEPY%" -c "import openpyxl, PIL" >nul 2>nul
if not errorlevel 1 set "USE_SYS=1"

if defined USE_SYS (
  set "RUNPY=%BASEPY%"
  echo [1/6] openpyxl + Pillow already available - no extra env needed.
) else (
  echo [1/6] Dependencies missing - creating a private env .venv\ 
  echo       ^(your system Python is left untouched^)
  set "VPY=%~dp0.venv\Scripts\python.exe"
  if not exist "!VPY!" (
    "%BASEPY%" -m venv "%~dp0.venv"
    if not exist "!VPY!" (
      echo.
      echo [ERROR] Failed to create .venv
      echo   Try running this file as Administrator, or install Python
      echo   from python.org with "Add to PATH" ticked.
      echo.
      pause
      popd
      exit /b 1
    )
  )
  set "RUNPY=%~dp0.venv\Scripts\python.exe"
)
echo.

REM ---------------------------------------------------------------
REM 3) install dependencies (only when needed)
REM ---------------------------------------------------------------
if defined USE_SYS (
  echo [2/6] Skipped - nothing to install.
  goto after_deps
)

echo [2/6] Installing openpyxl + Pillow ...
"%RUNPY%" -m pip install --upgrade pip --quiet --disable-pip-version-check 2>nul

"%RUNPY%" -m pip install openpyxl Pillow --quiet --disable-pip-version-check
if errorlevel 1 (
  echo       default source failed - retrying with a China mirror ...
  "%RUNPY%" -m pip install openpyxl Pillow --quiet --disable-pip-version-check ^
    -i https://pypi.tuna.tsinghua.edu.cn/simple
)
if errorlevel 1 (
  echo.
  echo [ERROR] Could not install openpyxl / Pillow.
  echo   Check your network or proxy, then run setup.bat again.
  echo   Manual command:
  echo     "%RUNPY%" -m pip install openpyxl Pillow
  echo.
  pause
  popd
  exit /b 1
)
echo       done.

:after_deps
echo.

REM ---------------------------------------------------------------
REM 4) skus.csv
REM ---------------------------------------------------------------
if not exist "skus.csv" (
  if exist "skus.example.csv" (
    copy /y "skus.example.csv" "skus.csv" >nul
    echo [3/6] Created skus.csv from the template.
    echo       Edit it later, or just drag a ranking xlsx into run.bat.
  ) else (
    echo [3/6] skus.example.csv missing - skipped.
  )
) else (
  echo [3/6] skus.csv already exists - kept as is.
)
echo.

REM ---------------------------------------------------------------
REM 5) bsk browser service
REM ---------------------------------------------------------------
echo [4/6] Checking the bsk browser service ...
where bsk >nul 2>nul
if errorlevel 1 (
  echo.
  echo       [WARN] "bsk" was NOT found on PATH.
  echo       Grabbing needs it. Install with ONE of these:
  echo.
  echo         PowerShell:  irm https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.ps1 ^| iex
  echo         macOS/Linux: curl -fsSL https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.sh ^| sh
  echo.
  echo       Then re-open this window and run setup.bat again.
) else (
  for /f "tokens=*" %%V in ('bsk --version 2^>nul') do echo       found: %%V
  echo.
  echo       Next: double-click start-bsk-daemon.bat and KEEP IT OPEN.
  echo       Then log in to jd.com once in the connected browser.
  echo       Tip: "bsk install-skill" registers the browser skill for your AI agent.
)
echo.

REM ---------------------------------------------------------------
REM 6) self-test
REM ---------------------------------------------------------------
echo [5/6] Running self-test ...
echo.
"%RUNPY%" doctor.py .
echo.

echo [6/6] Setup finished.
echo.
echo   Python in use: %RUNPY%
echo.
echo ------------------------------------------------------------
echo   Next steps
echo     1. start-bsk-daemon.bat      (keep the window open)
echo     2. log in to jd.com once in the connected browser
echo     3. run.bat                   (pick 1 or 2 to start grabbing)
echo ------------------------------------------------------------
echo.
pause
popd
endlocal
exit /b 0
