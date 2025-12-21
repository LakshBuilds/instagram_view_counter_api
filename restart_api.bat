@echo off
echo ========================================
echo Restarting API Server
echo ========================================
echo.

REM Kill any existing Python processes on port 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo Stopping process %%a on port 8000...
    taskkill /F /PID %%a >nul 2>&1
)

timeout /t 2 /nobreak >nul

echo Starting API server...
echo.
echo API will be available at: http://127.0.0.1:8000
echo API docs at: http://127.0.0.1:8000/docs
echo.
echo Press Ctrl+C to stop the server
echo.

python api.py








