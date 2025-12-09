# Quick script to get tunnel URL automatically
$ErrorActionPreference = "SilentlyContinue"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Getting Tunnel URL..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if tunnel is running
$tunnelRunning = Get-Process cloudflared -ErrorAction SilentlyContinue

if (-not $tunnelRunning) {
    Write-Host "Tunnel is not running. Starting it now..." -ForegroundColor Yellow
    Write-Host ""
    python start_tunnel.py
    Start-Sleep -Seconds 15
}

# Function to test if URL works
function Test-TunnelUrl {
    param([string]$url)
    try {
        $response = Invoke-WebRequest -Uri "$url/health" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

# Get URL from log
$url = $null
if (Test-Path tunnel_output.log) {
    $url = python get_tunnel_url.py 2>$null
}

# If URL found, test it
if ($url) {
    Write-Host "Found URL: $url" -ForegroundColor Yellow
    Write-Host "Testing connection..." -ForegroundColor Yellow
    
    if (Test-TunnelUrl -url $url) {
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Green
        Write-Host "YOUR TUNNEL URL:" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
        Write-Host ""
        Write-Host $url -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Test Endpoints:" -ForegroundColor Yellow
        Write-Host "  Health: $url/health" -ForegroundColor White
        Write-Host "  Scrape: $url/scrape?url=INSTAGRAM_REEL_URL" -ForegroundColor White
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Green
        Write-Host ""
        
        # Copy to clipboard
        $url | Set-Clipboard
        Write-Host "URL copied to clipboard!" -ForegroundColor Green
        Write-Host ""
    } else {
        Write-Host "URL expired or not working. Restarting tunnel..." -ForegroundColor Red
        Write-Host ""
        taskkill /F /IM cloudflared.exe 2>$null
        Start-Sleep -Seconds 2
        Remove-Item tunnel_output.log -ErrorAction SilentlyContinue
        Start-Process python -ArgumentList "start_tunnel.py" -WindowStyle Hidden
        Write-Host "Waiting for new tunnel to start (20 seconds)..." -ForegroundColor Yellow
        Start-Sleep -Seconds 20
        
        # Try to get new URL
        if (Test-Path tunnel_output.log) {
            $url = python get_tunnel_url.py 2>$null
            if ($url -and (Test-TunnelUrl -url $url)) {
                Write-Host ""
                Write-Host "========================================" -ForegroundColor Green
                Write-Host "NEW TUNNEL URL:" -ForegroundColor Green
                Write-Host "========================================" -ForegroundColor Green
                Write-Host ""
                Write-Host $url -ForegroundColor Cyan
                Write-Host ""
                Write-Host "Test Endpoints:" -ForegroundColor Yellow
                Write-Host "  Health: $url/health" -ForegroundColor White
                Write-Host "  Scrape: $url/scrape?url=INSTAGRAM_REEL_URL" -ForegroundColor White
                Write-Host ""
                $url | Set-Clipboard
                Write-Host "URL copied to clipboard!" -ForegroundColor Green
                Write-Host ""
            } else {
                Write-Host "Still waiting for tunnel. Run this script again in 10 seconds." -ForegroundColor Yellow
            }
        } else {
            Write-Host "Tunnel log not created yet. Run this script again in 10 seconds." -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "URL not found. Starting tunnel..." -ForegroundColor Yellow
    Write-Host ""
    taskkill /F /IM cloudflared.exe 2>$null
    Start-Sleep -Seconds 2
    Remove-Item tunnel_output.log -ErrorAction SilentlyContinue
    Start-Process python -ArgumentList "start_tunnel.py" -WindowStyle Hidden
    Write-Host "Waiting for tunnel to start (20 seconds)..." -ForegroundColor Yellow
    Start-Sleep -Seconds 20
    
    if (Test-Path tunnel_output.log) {
        $url = python get_tunnel_url.py 2>$null
        if ($url -and (Test-TunnelUrl -url $url)) {
            Write-Host ""
            Write-Host "========================================" -ForegroundColor Green
            Write-Host "TUNNEL URL:" -ForegroundColor Green
            Write-Host "========================================" -ForegroundColor Green
            Write-Host ""
            Write-Host $url -ForegroundColor Cyan
            Write-Host ""
            $url | Set-Clipboard
            Write-Host "URL copied to clipboard!" -ForegroundColor Green
            Write-Host ""
        } else {
            Write-Host "Tunnel started but URL not ready yet. Run this script again in 10 seconds." -ForegroundColor Yellow
        }
    } else {
        Write-Host "Tunnel log not created yet. Run this script again in 10 seconds." -ForegroundColor Yellow
    }
}

