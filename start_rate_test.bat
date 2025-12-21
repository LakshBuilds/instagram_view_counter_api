@echo off
title Instagram Rate Limit Tester
cd /d "%~dp0"

echo.
echo ========================================
echo   INSTAGRAM RATE LIMIT TESTER
echo ========================================
echo.
echo This tool tests how many requests your
echo account can handle before rate limiting.
echo.
echo It will detect:
echo   - Rate limits (429 errors)
echo   - CAPTCHA requirements
echo   - Account blocks
echo   - Response time patterns
echo.
echo ========================================
echo.

python rate_limit_tester.py

pause