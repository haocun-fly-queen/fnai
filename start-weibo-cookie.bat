@echo off
REM ============================================
REM  Weibo Cookie helper service (port 5001)
REM  Keep this window open. Close it to stop.
REM ============================================
title Weibo Cookie Service (port 5001)
cd /d "%~dp0"
echo Starting Weibo cookie service on http://localhost:5001 ...
echo Keep this window open. Press Ctrl+C or close it to stop.
echo.
python weibo_cookie_service.py
echo.
echo Service stopped. Press any key to close.
pause >nul
