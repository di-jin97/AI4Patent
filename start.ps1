$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$env:PYTHONIOENCODING = 'utf-8'
$ROOT = $PSScriptRoot
$PORT = 8001
$venv = "$ROOT\backend\.venv"

# 环境检查
if (-not (Test-Path "$venv\Scripts\python.exe") -or -not (Test-Path "$ROOT\bin\opencode\opencode.exe")) {
    Write-Host "❌ 环境未就绪，请先运行: .\install.ps1" -ForegroundColor Red
    exit 1
}

# 确保目录存在
New-Item -ItemType Directory -Path "$ROOT\logs","$ROOT\workspace\uploads","$ROOT\data\opencode" -Force | Out-Null

# 启动 FastAPI（后台无窗口）
$apiUp = $false
try { $apiUp = (Invoke-RestMethod "http://localhost:$PORT/api/health" -TimeoutSec 2).ok } catch {}
if (-not $apiUp) {
    Write-Host "[1/2] 启动服务..." -ForegroundColor Cyan
    Start-Process -FilePath "$venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","main:app","--port","$PORT" -WorkingDirectory "$ROOT\backend" -WindowStyle Hidden -RedirectStandardOutput "$ROOT\logs\server.log" -RedirectStandardError "$ROOT\logs\server.err"
    Start-Sleep 5
} else {
    Write-Host "[1/2] 服务已在运行" -ForegroundColor Green
}

# 开浏览器
Start-Process "http://localhost:$PORT"
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " AI4P 专利工作台已启动" -ForegroundColor Cyan
Write-Host " 地址: http://localhost:$PORT" -ForegroundColor Yellow
Write-Host " 日志: logs\server.log + logs\ai4p.log" -ForegroundColor Yellow
Write-Host " 停止: .\stop.ps1" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "按回车键退出本窗口（服务继续后台运行）..." -ForegroundColor Gray
Read-Host
