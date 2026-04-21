@echo off
setlocal enabledelayedexpansion

echo ======================================================
echo      Step 1: Check and release port 9222
echo ======================================================

set "targetPID="
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :9222') do (
    set "targetPID=%%a"
)

if defined targetPID (
    echo [INFO] Port 9222 is used by PID !targetPID!.
    echo [ACTION] Killing process !targetPID!...
    taskkill /F /PID !targetPID! /T >nul 2>&1
    timeout /t 2 /nobreak >nul
) else (
    echo [INFO] Port 9222 is free.
)

echo ======================================================
echo      Step 2: Start Chrome in Debug Mode
echo ======================================================
set CHROME_EXE="C:\Program Files\Google\Chrome\Application\chrome.exe"
set DATA_DIR="C:\boss_automation_profile"

start "" !CHROME_EXE! --remote-debugging-port=9222 --user-data-dir=!DATA_DIR! "https://www.zhipin.com"

echo.
echo [INFO] Debug browser opened.
echo [INFO] Please complete the BOSS Zhipin login in the new window.

echo ======================================================
echo      Step 3: Start AI Backend API & Engine
echo ======================================================

uvicorn webBossAI:app --port 8000

echo.
echo [STATUS] Engine exited.
pause