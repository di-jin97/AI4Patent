$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$PORT = 8001

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " AI4P 专利工作台 - 停止服务" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

$stopped = $false
try {
    $conn = Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction Stop
    $procId = $conn.OwningProcess
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host " 找到服务进程 (PID: $procId, $($proc.ProcessName))" -ForegroundColor Yellow
        Stop-Process -Id $procId -Force
        Start-Sleep 1
        $stillRunning = $false
        try {
            $check = Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction Stop
            if ($check) { $stillRunning = $true }
        } catch { }
        if ($stillRunning) {
            Write-Host " ❌ 服务仍在运行，请手动在任务管理器结束进程" -ForegroundColor Red
        } else {
            Write-Host " ✅ 服务已停止" -ForegroundColor Green
            $stopped = $true
        }
    } else {
        Write-Host " 服务未在运行" -ForegroundColor Green
        $stopped = $true
    }
} catch {
    Write-Host " 服务未在运行" -ForegroundColor Green
    $stopped = $true
}

Write-Host ""
Write-Host "按回车键退出..." -ForegroundColor Gray
Read-Host
