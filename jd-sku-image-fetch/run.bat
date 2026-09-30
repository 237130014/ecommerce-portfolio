@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
pushd "%~dp0"

REM ===============================================================
REM  Script location
REM    Source layout : *.py sits next to this bat
REM    Skill  layout : *.py sits in .\scripts\
REM  Both are supported.
REM ===============================================================
set "SD=%~dp0"
if not exist "%SD%fetch_main_images.py" (
  if exist "%SD%scripts\fetch_main_images.py" set "SD=%~dp0scripts\"
)
if not exist "%SD%fetch_main_images.py" (
  echo [ERROR] fetch_main_images.py not found next to run.bat or in .\scripts\
  pause
  popd
  exit /b 1
)

REM doctor.py normally sits next to this bat; fall back to .\scripts\
set "DD=%~dp0"
if not exist "%DD%doctor.py" if exist "%SD%doctor.py" set "DD=%SD%"

REM ===============================================================
REM  Locate Python
REM    1) .venv\                    (created by setup.bat - preferred)
REM    2) ..\jd-shop-audit\venv\    (legacy layout, kept for compat)
REM    3) py -3 launcher            (official Python install)
REM    4) python on PATH
REM ===============================================================
set "PY="

for %%D in (
  "%~dp0.venv\Scripts\python.exe"
  "%~dp0..\jd-shop-audit\venv\Scripts\python.exe"
  "%~dp0..\..\jd-shop-audit\venv\Scripts\python.exe"
) do (
  if not defined PY if exist "%%~fD" set "PY=%%~fD"
)

REM  Note: must resolve to a real .exe path. A bare "py -3" cannot be
REM  quoted later ("!PY!" script.py would look for a file named "py -3").
if not defined PY (
  where py >nul 2>nul
  if not errorlevel 1 (
    for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
  )
)
if not defined PY (
  for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%P"
)

if not defined PY (
  echo.
  echo [ERROR] No Python found on this PC.
  echo.
  echo   Double-click  setup.bat  once - it finds or guides you through
  echo   installing Python, then sets up everything else.
  echo.
  pause
  popd
  exit /b 1
)

REM --- dependencies present? -------------------------------------
"!PY!" -c "import openpyxl, PIL" >nul 2>nul
if errorlevel 1 (
  echo.
  echo [ERROR] openpyxl / Pillow are missing for:
  echo         !PY!
  echo.
  echo   Double-click  setup.bat  once and it will fix this.
  echo.
  pause
  popd
  exit /b 1
)

REM --- first run: create skus.csv from the template ---------------
if not exist "%~dp0skus.csv" (
  if exist "%~dp0skus.example.csv" copy /y "%~dp0skus.example.csv" "%~dp0skus.csv" >nul
)

REM ===============================================================
REM  Non-interactive entry:
REM     run.bat 1         = same as choosing 1 in the menu
REM     run.bat stats     = named shortcut
REM  Interactive (no argument): just double-click.
REM ===============================================================
set "PAUSEON=1"
set "CLI="
if "%~1"=="" goto menu
set "choice=%~1"
set "PAUSEON="
set "CLI=1"
shift
goto dispatch

REM  Every action ends with:
REM      if defined CLI goto end   --  one-shot mode: quit
REM      goto menu                 --  interactive: back to the menu
REM  Do NOT wrap that in "call :done": a goto issued from inside a
REM  called routine cannot terminate the script reliably.
REM  Also: never put angle brackets in a REM line - cmd still parses
REM  redirection there and will eat the next lines, labels included.
:menu
echo.
echo ============================================================
echo   JD SKU Main-Image Fetcher          python: !PY!
echo ============================================================
echo.
echo   Reads skus.csv, only the TOP 50 SKUs.
echo   Already-done SKUs are skipped automatically.
echo.
echo   1. Fetch from skus.csv  (asks how many)
echo   2. Fetch from xlsx      (drag file)
echo   3. Check bsk daemon status
echo   4. Show progress / stats
echo   5. Force refetch ALL
echo   6. Export embedded-image xlsx  (named after the batch)
echo   7. Repair report.csv         (check / fix URLs)
echo   8. Run self-test (what is missing?)
echo   9. Exit
echo.

set "choice="
set /p choice=Enter number: 

:dispatch
if /i "%choice%"=="1" goto fetch_csv
if /i "%choice%"=="2" goto fetch_xlsx
if /i "%choice%"=="3" goto bsk_status
if /i "%choice%"=="4" goto stats
if /i "%choice%"=="5" goto fetch_force
if /i "%choice%"=="6" goto export_xlsx
if /i "%choice%"=="7" goto repair
if /i "%choice%"=="8" goto selftest
if /i "%choice%"=="9" goto end
if /i "%choice%"=="exit" goto end

REM named shortcuts (for AI / scripts)
if /i "%choice%"=="stats"  goto stats
if /i "%choice%"=="doctor" goto selftest
if /i "%choice%"=="export" goto export_xlsx
if /i "%choice%"=="repair" goto repair
if /i "%choice%"=="bsk"    goto bsk_status

echo [WARN] unknown entry: "%choice%"
if defined PAUSEON pause
goto end

:ask_count
set "cnt="
set /p cnt=How many to fetch this run? [25]: 
if not defined cnt set "cnt=25"
echo !cnt!| findstr /r "^[1-9][0-9]*$" >nul
if errorlevel 1 (
  echo [WARN] invalid number, using 25
  set "cnt=25"
)
goto :eof

:fetch_csv
echo.
call :ask_count
echo.
echo Will fetch !cnt! SKU(s) from skus.csv (top 50).
"!PY!" "%SD%fetch_main_images.py" . --top 50 --limit !cnt!
if defined PAUSEON pause
if defined CLI goto end
goto menu

:fetch_xlsx
echo.
set "xlsx="
set /p xlsx=Drag the xlsx file here, then press Enter: 
if defined xlsx (
  for %%F in ("!xlsx!") do set "xlsx=%%~fF"
  call :ask_count
  "!PY!" "%SD%fetch_main_images.py" . --from-xlsx "!xlsx!" --top 50 --limit !cnt!
)
if defined PAUSEON pause
if defined CLI goto end
goto menu

:bsk_status
echo.
where bsk >nul 2>nul
if errorlevel 1 (
  echo [WARN] bsk not found on PATH.
  echo Install ^(PowerShell^):
  echo   irm https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.ps1 ^| iex
  echo.
  if defined PAUSEON pause
  if defined CLI goto end
goto menu
)
bsk doctor
echo.
echo If daemon FAIL: run start-bsk-daemon.bat and keep the window OPEN.
echo If extension FAIL: open Chrome and check the BrowserSkill extension.
echo.
if defined PAUSEON pause
if defined CLI goto end
goto menu

:stats
echo.
"!PY!" "%SD%fetch_stats.py"
if defined PAUSEON pause
if defined CLI goto end
goto menu

:fetch_force
echo.
echo [WARN] This refetches SKUs even if already done.
call :ask_count
echo.
set "y="
set /p y=Type y to confirm: 
if /i "!y!"=="y" (
  "!PY!" "%SD%fetch_main_images.py" . --top 50 --limit !cnt! --force
)
if defined PAUSEON pause
if defined CLI goto end
goto menu

:export_xlsx
echo.
echo Exporting embedded-image xlsx (thumbnail column: J) ...
"!PY!" "%SD%export_images_xlsx.py" .
echo.
echo Close the old xlsx in Excel first, or it will save as _2.
echo.
if defined PAUSEON pause
if defined CLI goto end
goto menu

:repair
echo.
echo Checking report.csv ...
"!PY!" "%SD%fix_report_urls.py" .
echo.
echo To apply the fixes, run manually with --apply:
echo   python "%SD%fix_report_urls.py" . --apply
echo.
if defined PAUSEON pause
if defined CLI goto end
goto menu

:selftest
echo.
"!PY!" "%DD%doctor.py" .
if defined PAUSEON pause
if defined CLI goto end
goto menu

:end
popd
endlocal
REM Use "exit /b 0" here, not a bare end-of-file: reaching EOF while
REM inside a called routine would just return to the caller.
exit /b 0
