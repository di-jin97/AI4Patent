$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$env:PYTHONIOENCODING = 'utf-8'
$ROOT = $PSScriptRoot
$PORT = 8001
$venv = "$ROOT\backend\.venv"

# 0. 确保必要目录存在
New-Item -ItemType Directory -Path "$ROOT\logs","$ROOT\workspace\uploads","$ROOT\data\opencode" -Force | Out-Null

# 1. 虚拟环境 + 依赖
if (-not (Test-Path $venv)) {
    Write-Host "[1/3] 创建虚拟环境..." -ForegroundColor Cyan
    & python -m venv $venv
}
Write-Host "[2/3] 检查依赖..." -ForegroundColor Cyan
& "$venv\Scripts\pip.exe" install -q -i https://pypi.tuna.tsinghua.edu.cn/simple -r "$ROOT\backend\requirements.txt" 2>&1 | Out-Null

# 2. 启动 FastAPI（后台无窗口）
$apiUp = $false
try { $apiUp = (Invoke-RestMethod "http://localhost:$PORT/api/health" -TimeoutSec 2).ok } catch {}
if (-not $apiUp) {
    Write-Host "[3/3] 启动服务..." -ForegroundColor Cyan
    Start-Process -FilePath "$venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","main:app","--port","$PORT" -WorkingDirectory "$ROOT\backend" -WindowStyle Hidden -RedirectStandardOutput "$ROOT\logs\server.log" -RedirectStandardError "$ROOT\logs\server.err"
    Start-Sleep 5
} else {
    Write-Host "[3/3] 服务已在运行" -ForegroundColor Green
}

# 3. 开浏览器
Start-Process "http://localhost:$PORT"
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " AI4P 专利工作台已启动" -ForegroundColor Cyan
Write-Host " 地址: http://localhost:$PORT" -ForegroundColor Yellow
Write-Host " 日志: logs\server.log + logs\ai4p.log" -ForegroundColor Yellow
Write-Host " 停止: 任务管理器结束 python.exe" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "按回车键退出本窗口（服务继续后台运行）..." -ForegroundColor Gray
Read-Host
