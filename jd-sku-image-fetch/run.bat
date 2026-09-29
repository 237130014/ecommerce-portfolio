@echo off
setlocal enabledelayedexpansion
pushd "%~dp0"

set "PY="
for %%D in ("..\jd-shop-audit\venv\Scripts\python.exe") do (
  if not defined PY (
    if exist "%%~fD" (
      set "PY=%%~fD"
    )
  )
)
if not defined PY (
  for %%D in ("..\..\jd-shop-audit\venv\Scripts\python.exe") do (
    if not defined PY (
      if exist "%%~fD" (
        set "PY=%%~fD"
      )
    )
  )
)

if not defined PY (
  echo.
  echo [ERROR] python.exe from jd-shop-audit venv not found.
  echo Keep this project next to jd-shop-audit, or edit run.bat.
  echo.
  pause
  popd
  exit /b 1
)

:menu
echo.
echo ============================================================
echo   JD SKU Main-Image Fetcher
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
echo   6. Export xlsx with images  (report_images.xlsx)
echo   7. Repair report.csv         (check / fix URLs)
echo   8. Exit
echo.

set "choice="
set /p choice=Enter number: 

if "%choice%"=="1" goto fetch_csv
if "%choice%"=="2" goto fetch_xlsx
if "%choice%"=="3" goto bsk_status
if "%choice%"=="4" goto stats
if "%choice%"=="5" goto fetch_force
if "%choice%"=="6" goto export_xlsx
if "%choice%"=="7" goto repair
if "%choice%"=="8" goto end
goto menu

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
"!PY!" fetch_main_images.py . --top 50 --limit !cnt!
echo.
pause
goto menu

:fetch_xlsx
echo.
set "xlsx="
set /p xlsx=Drag the xlsx file here, then press Enter: 
if defined xlsx (
  for %%F in ("!xlsx!") do set "xlsx=%%~fF"
  call :ask_count
  "!PY!" fetch_main_images.py . --from-xlsx "!xlsx!" --top 50 --limit !cnt!
)
echo.
pause
goto menu

:bsk_status
echo.
where bsk >nul 2>nul
if errorlevel 1 (
  echo [WARN] bsk not found in PATH.
  echo Install: irm https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.ps1 ^| iex
  echo.
  pause
  goto menu
)
bsk doctor
echo.
echo If daemon FAIL: double-click start-bsk-daemon.bat and keep it open.
echo If extension FAIL: make sure Chrome has the BrowserSkill extension.
echo.
pause
goto menu

:stats
echo.
"!PY!" fetch_stats.py
echo.
pause
goto menu

:fetch_force
echo.
echo [WARN] This refetches SKUs even if already done.
call :ask_count
echo.
set "y="
set /p y=Type y to confirm: 
if /i "!y!"=="y" (
  "!PY!" fetch_main_images.py . --top 50 --limit !cnt! --force
)
echo.
pause
goto menu

:export_xlsx
echo.
echo Exporting report_images.xlsx (embedded thumbnails in column H) ...
"!PY!" export_images_xlsx.py .
echo.
echo Close the old report_images.xlsx in Excel first, or it will save as _2.
echo.
pause
goto menu

:repair
echo.
echo Checking report.csv ...
"!PY!" fix_report_urls.py .
echo.
echo To apply the fixes, run manually with --apply:
echo   python fix_report_urls.py . --apply
echo.
pause
goto menu

:end
popd
endlocal
