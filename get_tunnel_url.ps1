# Get or Create Cloudflare Tunnel URL
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Cloudflare Tunnel URL Helper" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if API is running
$apiRunning = Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue

if (-not $apiRunning) {
    Write-Host "❌ API server is not running on port 8000!" -ForegroundColor Red
    Write-Host "Please start the API server first: python api.py" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ API server is running on port 8000" -ForegroundColor Green
Write-Host ""

# Check for running tunnels
$tunnels = Get-Process -Name cloudflared -ErrorAction SilentlyContinue | Where-Object {
    $_.MainWindowTitle -ne "" -or $_.CommandLine -like "*tunnel*"
}

if ($tunnels) {
    Write-Host "Found $($tunnels.Count) cloudflared tunnel process(es)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To find your tunnel URL:" -ForegroundColor Cyan
    Write-Host "1. Look at the terminal window where you ran 'cloudflared tunnel'" -ForegroundColor White
    Write-Host "2. Find the line: 'Your quick Tunnel has been created! Visit it at:'" -ForegroundColor White
    Write-Host "3. Copy the URL shown (format: https://[name].trycloudflare.com)" -ForegroundColor White
    Write-Host ""
    Write-Host "If you can't find it, we can create a new tunnel..." -ForegroundColor Yellow
    Write-Host ""
    $createNew = Read-Host "Create a new tunnel? (y/n)"
    
    if ($createNew -eq 'y' -or $createNew -eq 'Y') {
        Write-Host ""
        Write-Host "Starting new tunnel..." -ForegroundColor Green
        Write-Host "This will open in a new window. Look for the URL in the output." -ForegroundColor Yellow
        Write-Host ""
        
        $scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
        $cloudflaredPath = Join-Path $scriptPath "cloudflared.exe"
        
        if (Test-Path $cloudflaredPath) {
            Start-Process -FilePath $cloudflaredPath -ArgumentList "tunnel", "--config", "quick_tunnel.yml", "--url", "http://127.0.0.1:8000" -WorkingDirectory $scriptPath
            Write-Host "✅ Tunnel started! Check the new window for your URL." -ForegroundColor Green
        } else {
            Write-Host "❌ cloudflared.exe not found in current directory" -ForegroundColor Red
        }
    }
} else {
    Write-Host "No active tunnel found. Creating a new one..." -ForegroundColor Yellow
    Write-Host ""
    
    $scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
    $cloudflaredPath = Join-Path $scriptPath "cloudflared.exe"
    
    if (Test-Path $cloudflaredPath) {
        Write-Host "Starting tunnel in new window..." -ForegroundColor Green
        Start-Process -FilePath $cloudflaredPath -ArgumentList "tunnel", "--config", "quick_tunnel.yml", "--url", "http://127.0.0.1:8000" -WorkingDirectory $scriptPath
        Write-Host ""
        Write-Host "✅ Tunnel started! Look for the URL in the new window:" -ForegroundColor Green
        Write-Host "   Format: https://[random-name].trycloudflare.com" -ForegroundColor Cyan
    } else {
        Write-Host "❌ cloudflared.exe not found in current directory" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Once you have the URL, use it like this:" -ForegroundColor Cyan
Write-Host "https://[YOUR-URL].trycloudflare.com/scrape?url=INSTAGRAM_REEL_URL" -ForegroundColor White
Write-Host ""




