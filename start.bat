@echo off
:: 设置 UTF-8 编码，解决控制台中文乱码
chcp 65001 >nul
setlocal enabledelayedexpansion
title BOSS助手-精准环境重置

echo ======================================================
echo           第一步：精准检测并清理 9222 端口
echo ======================================================

:: 查找占用 9222 端口的 PID
set "targetPID="
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :9222') do (
    set "targetPID=%%a"
)

if defined targetPID (
    echo [发现] 端口 9222 被进程 !targetPID! 占用。
    echo [动作] 正在强制关闭该特定进程，不影响其他浏览器窗口...
    taskkill /F /PID !targetPID! /T >nul 2>&1
    :: 给系统一点点释放端口的时间
    timeout /t 2 /nobreak >nul
) else (
    echo [清理] 端口 9222 当前是空闲的，无需干扰其他进程。
)

echo ======================================================
echo           第二步：启动调试模式 Chrome
echo ======================================================
set CHROME_EXE="C:\Program Files\Google\Chrome\Application\chrome.exe"
set DATA_DIR="C:\boss_automation_profile"

:: 启动 Chrome 调试端口，注意：因为使用了独立的 --user-data-dir，
:: 它会作为一个独立的 Chrome 实例运行，不会干扰你现有的 Chrome。
start "" !CHROME_EXE! --remote-debugging-port=9222 --user-data-dir=!DATA_DIR! "https://www.zhipin.com"

echo.
echo [提示] 调试浏览器已打开。
echo [提示] 请在【该新窗口】中完成 BOSS 扫码登录。
echo [提示] 登录完成后，回到这里按任意键开启 AI 引擎。
pause

echo ======================================================
echo           第三步：启动 AI 招聘引擎
echo ======================================================
python webBossAI.py

if !errorlevel! neq 0 (
    echo.
    echo [!!!] AI 引擎运行中断。
)
pause