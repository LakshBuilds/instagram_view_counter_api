@echo off
echo ========================================
echo Reinstalling Cloudflare Tunnel Service
echo ========================================
echo.

if not exist "cloudflared.exe" (
    echo [ERROR] cloudflared.exe not found!
    pause
    exit /b 1
)

echo Stopping service (if running)...
net stop cloudflared 2>nul

echo.
echo Uninstalling existing service...
.\cloudflared.exe service uninstall

echo.
echo Installing service with token...
.\cloudflared.exe service install 2f9d6af4-72a9-4c84-a554-2dfd0acf5f2a

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo [SUCCESS] Service reinstalled!
    echo ========================================
    echo.
    echo Starting service...
    net start cloudflared
    echo.
    echo Service status:
    sc query cloudflared
    echo.
    echo Your tunnel should now be running!
    echo Check Cloudflare dashboard for your public URL.
    echo.
) else (
    echo.
    echo [ERROR] Installation failed!
    echo Make sure you're running as Administrator.
    echo.
)

pause




