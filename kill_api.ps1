# Kill API Server Script
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Killing API Server on Port 8000" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$connections = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }

if ($connections) {
    foreach ($conn in $connections) {
        $processId = $conn.OwningProcess
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        
        if ($process) {
            Write-Host "Found process: $($process.ProcessName) (PID: $processId)" -ForegroundColor Yellow
            Write-Host "Killing process..." -ForegroundColor Red
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            Write-Host "✓ Process killed successfully" -ForegroundColor Green
        }
    }
} else {
    Write-Host "No process found on port 8000" -ForegroundColor Green
}

Write-Host ""
Write-Host "Done!" -ForegroundColor Cyan








