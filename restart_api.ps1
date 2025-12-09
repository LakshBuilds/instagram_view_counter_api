# Restart API Server Script for PowerShell
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Restarting API Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Kill any existing Python processes on port 8000
$connections = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" }

if ($connections) {
    foreach ($conn in $connections) {
        $processId = $conn.OwningProcess
        Write-Host "Stopping process $processId on port 8000..." -ForegroundColor Yellow
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "No process found on port 8000" -ForegroundColor Green
}

Write-Host ""
Write-Host "Waiting 2 seconds for port to be released..." -ForegroundColor Gray
Start-Sleep -Seconds 2

Write-Host ""
Write-Host "Starting API server..." -ForegroundColor Green
Write-Host ""
Write-Host "API will be available at: http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "API docs at: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

# Start the API
python api.py








