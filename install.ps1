$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$env:PYTHONIOENCODING = 'utf-8'
$ROOT = $PSScriptRoot

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " AI4P 专利工作台 - 一键安装" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 解压 opencode
$exePath = "$ROOT\bin\opencode\opencode.exe"
$zipPath = "$ROOT\bin\opencode-windows-x64.zip"
if (-not (Test-Path $exePath)) {
    if (Test-Path $zipPath) {
        Write-Host "[1/4] 解压 opencode..." -ForegroundColor Cyan
        Expand-Archive -Path $zipPath -DestinationPath "$ROOT\bin\opencode" -Force
        Write-Host "  ✅ opencode.exe 已解压" -ForegroundColor Green
    } else {
        Write-Host "  ❌ 未找到 opencode-windows-x64.zip，请手动下载" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[1/4] opencode.exe 已存在，跳过" -ForegroundColor Green
}

# 2. 创建虚拟环境 + 安装依赖
$venv = "$ROOT\backend\.venv"
if (-not (Test-Path $venv)) {
    Write-Host "[2/4] 创建 Python 虚拟环境..." -ForegroundColor Cyan
    & python -m venv $venv
}
Write-Host "[2/4] 安装 Python 依赖..." -ForegroundColor Cyan
& "$venv\Scripts\pip.exe" install -q -i https://pypi.tuna.tsinghua.edu.cn/simple -r "$ROOT\backend\requirements.txt" 2>&1 | Out-Null
Write-Host "  ✅ 依赖已安装" -ForegroundColor Green

# 3. 创建必要目录
Write-Host "[3/4] 创建目录..." -ForegroundColor Cyan
@("logs", "data\opencode", "workspace\uploads") | ForEach-Object {
    $p = "$ROOT\$_"
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p -Force | Out-Null }
}
Write-Host "  ✅ 目录已就绪" -ForegroundColor Green

# 4. 检查配置
Write-Host "[4/4] 检查配置..." -ForegroundColor Cyan
$cfgPath = "$ROOT\config\opencode\opencode.json"
$authPath = "$ROOT\data\opencode\auth.json"
if (Test-Path $authPath) {
    Write-Host "  ✅ 已有 API 配置" -ForegroundColor Green
} else {
    Write-Host "  ⚠️ 尚未配置 API Key" -ForegroundColor Yellow
    Write-Host "  启动后在前端界面点击 ⚙️设置 填入 API Key 即可" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " 安装完成！" -ForegroundColor Green
Write-Host " 启动: .\start.ps1" -ForegroundColor Yellow
Write-Host " 开发: .\dev.ps1" -ForegroundColor Yellow
Write-Host " 停止: .\stop.ps1" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
