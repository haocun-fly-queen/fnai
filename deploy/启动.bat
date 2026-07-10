@echo off
chcp 65001 >nul
title FNAI - Starting...

echo.
echo  ======================================
echo    FNAI Content Platform
echo  ======================================
echo.

REM Check Docker Desktop is running
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Docker Desktop is not running.
    echo.
    echo  Please start Docker Desktop first, then run this script again.
    echo  Download: https://www.docker.com/products/docker-desktop/
    echo.
    pause
    exit /b 1
)

REM Check .env exists
if not exist "%~dp0.env" (
    echo  [SETUP] First run detected - creating .env from template...
    copy "%~dp0.env.example" "%~dp0.env" >nul
    echo.
    echo  !! ACTION REQUIRED !!
    echo  Please open .env and fill in:
    echo    - OPENAI_API_KEY  (your DashScope API key)
    echo    - JWT_SECRET      (random string for security)
    echo.
    echo  Then run this script again.
    echo.
    start notepad "%~dp0.env"
    pause
    exit /b 0
)

echo  Starting all services (first run will download images, ~5 mins)...
echo.

cd /d "%~dp0"
docker-compose up -d --build

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Failed to start. Check the error above.
    echo  Common fix: make sure Docker Desktop is fully started.
    pause
    exit /b 1
)

echo.
echo  Waiting for services to be ready...
timeout /t 8 >nul

REM Wait for backend health
set /a attempts=0
:wait_loop
set /a attempts+=1
if %attempts% gtr 20 goto start_anyway
curl -s -m 3 http://localhost:8000/api/v1/health >nul 2>&1
if %errorlevel% neq 0 (
    timeout /t 3 >nul
    goto wait_loop
)

:start_anyway
echo.
echo  ======================================
echo   All services started!
echo   Opening browser: http://localhost:3000
echo  ======================================
echo.

start http://localhost:3000
echo  Press any key to close this window.
echo  (Services will keep running in background)
pause >nul
