# 京东 SKU 主图抓取 - 交互菜单（PowerShell 版）
# 用法：在本目录右键「使用 PowerShell 运行」，或执行
#   powershell -ExecutionPolicy Bypass -File .\run.ps1

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

# 定位 venv python（不硬编码中文路径，向上查找同级项目）
$candidates = @(
    (Join-Path $here '..\jd-shop-audit\venv\Scripts\python.exe'),
    (Join-Path $here '..\..\jd-shop-audit\venv\Scripts\python.exe')
)
$py = $null
foreach ($c in $candidates) {
    if (Test-Path $c) { $py = (Resolve-Path $c).Path; break }
}
if (-not $py) {
    Write-Host "[错误] 找不到 jd-shop-audit 的 venv python。" -ForegroundColor Red
    Write-Host "请确保本项目与 jd-shop-audit 在同一目录下。"
    Read-Host "按回车退出"
    exit 1
}

function Show-Menu {
    Clear-Host
    Write-Host "============================================================"
    Write-Host "  京东 SKU 主图抓取 - 菜单"
    Write-Host "============================================================"
    Write-Host ""
    Write-Host "  1. 扫码登录（首次使用 / 登录态失效时）"
    Write-Host "  2. 检查登录态是否有效"
    Write-Host "  3. 跑探针（拖入榜单 xlsx）"
    Write-Host "  4. 退出"
    Write-Host ""
}

while ($true) {
    Show-Menu
    $choice = Read-Host "请输入序号后回车"

    switch ($choice) {
        '1' {
            Write-Host ""
            & $py "login.py"
            Write-Host ""
            Read-Host "按回车返回菜单"
        }
        '2' {
            Write-Host ""
            & $py "login.py" "--check"
            Write-Host ""
            Read-Host "按回车返回菜单"
        }
        '3' {
            Write-Host ""
            $xlsx = Read-Host "把榜单 xlsx 文件拖到这里，再回车"
            $xlsx = $xlsx.Trim('"').Trim("'")
            if ($xlsx -and (Test-Path $xlsx)) {
                & $py "probe.py" "--from-xlsx" $xlsx
            } else {
                Write-Host "[跳过] 文件路径无效：$xlsx" -ForegroundColor Yellow
            }
            Write-Host ""
            Read-Host "按回车返回菜单"
        }
        '4' { exit 0 }
        default { }
    }
}
