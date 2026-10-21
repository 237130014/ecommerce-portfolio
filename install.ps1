param(
    [string]$Skill = 'all'
)

# ============================================================
#  电商工具 · 一键安装
#  仓库：https://github.com/237130014/ecommerce-portfolio
#  默认安装全部技能；也可在本地指定单个技能：
#      .\install.ps1 -Skill dewu-hot-track-report
# ============================================================

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$RepoOwner = '237130014'
$RepoName  = 'ecommerce-portfolio'
$Branch    = 'main'

# ---- 技能清单：新增可一键安装的技能在这里加一行 ----
$Catalog = @(
    @{
        Name    = 'dewu-hot-track-report'
        Title   = '得物商机推荐趋势报告'
        Deps    = @('pandas', 'jieba', 'pillow')
        RunHint = '跑一次得物商机推荐报告'
    }
)

# ---- 目标目录（可用环境变量 MT_SKILLS_DIR 覆盖，便于测试）----
if ($env:MT_SKILLS_DIR -and $env:MT_SKILLS_DIR.Trim() -ne '') {
    $SkillsRoot = $env:MT_SKILLS_DIR
} else {
    $SkillsRoot = Join-Path $env:USERPROFILE '.workbuddy\skills'
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$tmpRoot = Join-Path $env:TEMP ('ec-install-' + $stamp)
$zipPath = Join-Path $tmpRoot 'pkg.zip'

function Write-Step($msg) { Write-Host ('  -> ' + $msg) -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host ('  OK  ' + $msg) -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host ('  !!  ' + $msg) -ForegroundColor Yellow }

Write-Host ''
Write-Host '========================================' -ForegroundColor White
Write-Host ' 电商工具 · 一键安装' -ForegroundColor White
Write-Host '========================================' -ForegroundColor White
Write-Host ''

# ---- 找 Python（优先 WorkBuddy 托管版）----
function Find-Python {
    $cands = @(
        (Join-Path $env:USERPROFILE '.workbuddy\binaries\python\envs\default\Scripts\python.exe'),
        (Join-Path $env:USERPROFILE '.workbuddy\binaries\python\envs\default\bin\python')
    )
    foreach ($c in $cands) {
        if (Test-Path $c) { return $c }
    }
    $verRoot = Join-Path $env:USERPROFILE '.workbuddy\binaries\python\versions'
    if (Test-Path $verRoot) {
        $found = Get-ChildItem -Path $verRoot -Recurse -Filter 'python.exe' -ErrorAction SilentlyContinue |
                 Where-Object { $_.FullName -notmatch '\\Scripts\\' } |
                 Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$installed = New-Object System.Collections.ArrayList
$failed    = New-Object System.Collections.ArrayList

try {
    # ---------- 1. 下载 + 解压（所有技能共用一次下载）----------
    Write-Step "下载技能包 ($RepoOwner/$RepoName@$Branch)"
    New-Item -ItemType Directory -Path $tmpRoot -Force | Out-Null
    $zipUrl = "https://github.com/$RepoOwner/$RepoName/archive/refs/heads/$Branch.zip"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
    $sizeKb = [math]::Round((Get-Item $zipPath).Length / 1KB, 1)
    Write-Ok "已下载 $sizeKb KB"

    Write-Step '解压'
    $expandDir = Join-Path $tmpRoot 'x'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $expandDir)
    Write-Ok '解压完成'

    if (-not (Test-Path $SkillsRoot)) {
        New-Item -ItemType Directory -Path $SkillsRoot -Force | Out-Null
        Write-Ok "已创建技能目录 $SkillsRoot"
    }

    $pyExe = Find-Python

    # ---------- 2. 逐个安装 ----------
    foreach ($item in $Catalog) {
        $name = $item.Name
        if ($Skill -ne 'all' -and $Skill -ne $name) { continue }

        Write-Host ''
        Write-Host ('--- ' + $item.Title + ' (' + $name + ') ---') -ForegroundColor White

        try {
            Write-Step "定位 $name"
            $candidates = Get-ChildItem -Path $expandDir -Recurse -Directory -Filter $name -ErrorAction SilentlyContinue
            $srcDir = $null
            foreach ($c in $candidates) {
                if (Test-Path (Join-Path $c.FullName 'SKILL.md')) { $srcDir = $c.FullName; break }
            }
            if (-not $srcDir) { throw "压缩包里没找到有效的 $name/SKILL.md" }
            Write-Ok "找到：$srcDir"

            $dest = Join-Path $SkillsRoot $name
            Write-Step "安装到 $dest"
            if (Test-Path $dest) {
                $bak = "$dest.bak-$stamp"
                Move-Item -Path $dest -Destination $bak -Force
                Write-Warn2 "检测到旧版本，已备份为 $(Split-Path $bak -Leaf)"
            }
            Copy-Item -Path $srcDir -Destination $dest -Recurse -Force

            $skillMd = Join-Path $dest 'SKILL.md'
            if (-not (Test-Path $skillMd)) {
                throw "校验失败：$skillMd 不存在（可能多套了一层目录）"
            }
            $fileCount = (Get-ChildItem -Path $dest -Recurse -File).Count
            Write-Ok "SKILL.md 就位，共 $fileCount 个文件"

            # ---- 依赖检查 ----
            $deps = $item.Deps
            if ($deps -and $deps.Count -gt 0) {
                if (-not $pyExe) {
                    Write-Warn2 '没找到 Python，跳过依赖检查（首次运行时会自行处理）'
                } else {
                    $depList = ($deps -join ',')
                    $probe = & $pyExe -c "import $depList" 2>&1
                    if ($LASTEXITCODE -eq 0) {
                        Write-Ok "依赖已就绪（$depList）"
                    } else {
                        $depArgs = ($deps -join ' ')
                        Write-Step "正在安装依赖 $depArgs（首次约 20 秒）"
                        & $pyExe -m pip install --quiet --disable-pip-version-check $deps 2>&1 | Out-Null
                        & $pyExe -c "import $depList" 2>&1 | Out-Null
                        if ($LASTEXITCODE -eq 0) {
                            Write-Ok "依赖安装成功（$depList）"
                        } else {
                            Write-Warn2 "自动安装失败，请手动执行：$pyExe -m pip install $depArgs"
                        }
                    }
                }
            }

            [void]$installed.Add($item)
            Write-Ok '该技能安装完成'
        }
        catch {
            Write-Warn2 ("该技能安装失败：" + $_.Exception.Message)
            [void]$failed.Add($item.Title)
        }
    }

    if ($Skill -ne 'all' -and $installed.Count -eq 0 -and $failed.Count -eq 0) {
        $names = ($Catalog | ForEach-Object { $_.Name }) -join ', '
        Write-Warn2 "没有匹配到技能 '$Skill'，可用：$names"
    }

    # ---------- 3. 收尾 ----------
    Write-Host ''
    if ($installed.Count -gt 0) {
        Write-Host '========================================' -ForegroundColor Green
        Write-Host (' 安装成功 ' + $installed.Count + ' 个技能') -ForegroundColor Green
        Write-Host '========================================' -ForegroundColor Green
        Write-Host ''
        foreach ($it in $installed) {
            Write-Host ('  · ' + $it.Title + '  ->  ' + (Join-Path $SkillsRoot $it.Name))
        }
        Write-Host ''
        Write-Host '  下一步：完全退出 WorkBuddy 再重新打开' -ForegroundColor Yellow
        Write-Host '         （右下角托盘图标也要退出，不是只关窗口）' -ForegroundColor Yellow
        Write-Host ''
        Write-Host '  重开后新建对话，按下面的句子直接说：' -ForegroundColor White
        foreach ($it in $installed) {
            Write-Host ('         ' + $it.RunHint) -ForegroundColor White
        }
        Write-Host ''
    }
    if ($failed.Count -gt 0) {
        Write-Host (' 失败 ' + $failed.Count + ' 个：' + ($failed -join '、')) -ForegroundColor Red
        Write-Host ' 可单独重试：.\install.ps1 -Skill <技能名>' -ForegroundColor Yellow
        Write-Host ''
    }
}
catch {
    Write-Host ''
    Write-Host '========================================' -ForegroundColor Red
    Write-Host ' 安装失败' -ForegroundColor Red
    Write-Host '========================================' -ForegroundColor Red
    Write-Host ('  原因：' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ''
    Write-Host '  常见处理：' -ForegroundColor Yellow
    Write-Host '   1) 网络不通 / 公司代理拦截 -> 换手机热点重试'
    Write-Host '   2) 目标目录被占用 -> 先退出 WorkBuddy 再装'
    Write-Host '   3) 仍失败 -> 手动下载 ZIP：'
    Write-Host "      https://github.com/$RepoOwner/$RepoName" -ForegroundColor Cyan
    Write-Host ''
}
finally {
    if (Test-Path $tmpRoot) {
        Remove-Item -Path $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
