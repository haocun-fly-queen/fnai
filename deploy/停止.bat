@echo off
chcp 65001 >nul
title FNAI - Stopping...

echo.
echo  ======================================
echo    Stopping FNAI Services
echo  ======================================
echo.

cd /d "%~dp0"
docker-compose down

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Failed to stop services.
    pause
    exit /b 1
)

echo.
echo  ======================================
echo   All services stopped.
echo.
echo   Your data is safe (stored in Docker volumes).
echo   Run 启动.bat to start again.
echo  ======================================
echo.
pause
