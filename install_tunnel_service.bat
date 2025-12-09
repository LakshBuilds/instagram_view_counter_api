@echo off
echo ========================================
echo Install Tunnel Service
echo ========================================
echo.
echo Tunnel ID: ee50ec28-749a-4ed4-8888-0b1d837a7ada
echo.
echo You need a token from Cloudflare dashboard:
echo 1. Go to your tunnel in Cloudflare dashboard
echo 2. Copy the installation token
echo 3. Paste it below
echo.
echo.

set /p TOKEN="Paste your tunnel token here: "

if "%TOKEN%"=="" (
    echo [ERROR] Token is required!
    pause
    exit /b 1
)

echo.
echo Installing tunnel service...
echo.

if not exist "cloudflared.exe" (
    echo [ERROR] cloudflared.exe not found!
    pause
    exit /b 1
)

.\cloudflared.exe service install %TOKEN%

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo [SUCCESS] Service installed!
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








