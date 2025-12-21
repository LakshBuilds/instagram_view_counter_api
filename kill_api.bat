@echo off
echo ========================================
echo Killing API Server on Port 8000
echo ========================================
echo.

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo Found process %%a on port 8000
    echo Killing process...
    taskkill /F /PID %%a
    if errorlevel 1 (
        echo [ERROR] Could not kill process %%a
    ) else (
        echo [OK] Process %%a killed successfully
    )
)

echo.
echo Done!
pause








