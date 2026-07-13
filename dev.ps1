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

# 延迟开浏览器
Start-Job -Command { Start-Sleep -Seconds 4; Start-Process "http://localhost:$PORT" } | Out-Null

# 前台启动 FastAPI（日志实时显示 + 写 logs/ai4p.log）
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " AI4P 专利工作台 (opencode run 引擎)" -ForegroundColor Cyan
Write-Host " 工作台:   http://localhost:$PORT" -ForegroundColor Yellow
Write-Host " 日志:     本终端实时 + logs\ai4p.log" -ForegroundColor Yellow
Write-Host " 退出:     Ctrl+C" -ForegroundColor Cyan
Write-Host " 停止:     .\stop.ps1" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
& "$venv\Scripts\python.exe" -m uvicorn main:app --port $PORT --app-dir "$ROOT\backend"
