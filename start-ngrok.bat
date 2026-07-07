@echo off
chcp 65001 >nul
echo ========================================
echo    FNAI 一键启动脚本 (Ngrok 版本)
echo ========================================
echo.

:: 检查 ngrok 是否存在
if not exist "C:\ngrok\ngrok.exe" (
    echo ❌ 错误: 未找到 ngrok.exe
    echo 请先下载并解压 ngrok 到 C:\ngrok\
    echo 下载地址: https://ngrok.com/download
    pause
    exit
)

echo [1/4] 启动后端服务...
start "后端服务" cmd /k "cd /d %~dp0fnai-monorepo\backend && .venv\Scripts\activate && echo 后端正在启动... && uvicorn app.main:app --reload --port 8000"
timeout /t 8 >nul

echo [2/4] 启动前端服务...
start "前端服务" cmd /k "cd /d %~dp0fnai-monorepo\frontend && echo 前端正在启动... && npm run dev"
timeout /t 15 >nul

echo [3/4] 启动 Ngrok 穿透...
start "Ngrok穿透" cmd /k "cd C:\ngrok && echo 正在启动 Ngrok... && ngrok http 5173"
timeout /t 5 >nul

echo.
echo ========================================
echo ✅ 所有服务已启动！
echo ========================================
echo.
echo 📝 下一步:
echo 1. 在 Ngrok 窗口中找到 "Forwarding" 行
echo 2. 复制 https://xxxxx.ngrok-free.app 链接
echo 3. 发送给同事即可访问
echo.
echo ⚠️  注意事项:
echo - 首次访问会显示警告页，点击 "Visit Site" 继续
echo - 需要保持此窗口和所有服务窗口打开
echo - 关闭任一窗口都会停止服务
echo.
echo 📞 遇到问题？查看文档:
echo    docs\ngrok-detailed-guide.md
echo.
pause
