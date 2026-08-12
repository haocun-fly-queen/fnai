@echo off
chcp 65001 >nul
echo ========================================
echo    FNAI 服务重启脚本
echo ========================================
echo.

echo [1/3] 停止旧的后端进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo 找到进程 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 >nul

echo [2/3] 启动后端服务...
cd /d "%~dp0backend"
start "FNAI后端" cmd /k ".venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"
timeout /t 8 >nul

echo [3/3] 检查服务状态...
curl -s http://localhost:8000/api/v1/health >nul 2>&1
if %errorlevel%==0 (
    echo ✅ 后端启动成功！
) else (
    echo ⚠️  后端启动中，请等待10-20秒...
)

echo.
echo ========================================
echo ✅ 重启完成
echo ========================================
echo.
echo 📝 下一步:
echo 1. 等待后端完全启动 (约15秒)
echo 2. 访问: http://localhost:5173
echo 3. 清除缓存: F12 → Console → localStorage.clear()
echo 4. 刷新页面
echo.
pause
