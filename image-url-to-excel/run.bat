@echo off
chcp 65001 >nul
setlocal
title 表格图片链接转图片
cd /d "%~dp0"

set "SCRIPT=%~dp0url2img.py"
if not exist "%SCRIPT%" (
    echo [错误] 找不到 url2img.py
    echo 请把本 BAT 文件和 url2img.py 放在同一个文件夹里。
    goto :end
)

rem ---- 找一个能用的 Python ----
set "PYCMD="
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 set PYCMD=py -3

if not defined PYCMD (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 set PYCMD=python
)

if not defined PYCMD (
    python3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set PYCMD=python3
)

if not defined PYCMD (
    echo [错误] 没有找到 Python，脚本无法运行。
    echo.
    echo 请到 https://www.python.org/downloads/ 下载安装，
    echo 安装时务必勾选 "Add python.exe to PATH"。
    goto :end
)

rem ---- 依赖检查，缺了就自动装一次 ----
%PYCMD% -c "import openpyxl, PIL, requests" >nul 2>nul
if errorlevel 1 (
    echo 首次使用，正在安装所需组件（openpyxl / pillow / requests）……
    echo.
    %PYCMD% -m pip install --quiet --disable-pip-version-check openpyxl pillow requests
    %PYCMD% -c "import openpyxl, PIL, requests" >nul 2>nul
    if errorlevel 1 (
        echo.
        echo [错误] 组件安装失败，请联网后手动执行下面这行命令：
        echo     %PYCMD% -m pip install openpyxl pillow requests
        goto :end
    )
)

if not "%~2"=="" echo [提示] 一次只处理一个文件，本次忽略第一个以外的文件。
echo.

rem ---- 带了文件就直接处理，没带就进去问路径 ----
if "%~1"=="" (
    %PYCMD% "%SCRIPT%" --open
) else (
    %PYCMD% "%SCRIPT%" "%~1" --open
)

if errorlevel 1 (
    echo.
    echo [提示] 处理没有完成，请查看上面的错误信息。
)

:end
echo.
pause
