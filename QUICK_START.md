# Quick Start Guide

## Starting the API Server

### Option 1: PowerShell Script (Recommended)
```powershell
.\restart_api.ps1
```

If you get an execution policy error, run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Option 2: Batch File
```powershell
.\restart_api.bat
```

### Option 3: Manual Start
```powershell
python api.py
```

## Stopping the API Server

Press `Ctrl+C` in the terminal where the API is running.

Or kill the process:
```powershell
# Find process on port 8000
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess

# Kill it (replace PID with actual process ID)
Stop-Process -Id <PID> -Force
```

## Access the API

- **API Root**: http://127.0.0.1:8000
- **API Docs**: http://127.0.0.1:8000/docs
- **Health Check**: http://127.0.0.1:8000/health
- **Scrape Endpoint**: http://127.0.0.1:8000/scrape?url=INSTAGRAM_URL

## Example Usage

```bash
# Scrape a reel
curl "http://127.0.0.1:8000/scrape?url=https://www.instagram.com/reel/ABC123/"
```








