@echo off
chcp 65001 > nul
title 輕量桌面錄影工具 (Lite Screen Recorder)

cd /d "%~dp0"

echo ========================================================
echo   🎥 輕量桌面螢幕錄製與剪輯工具 (Windows / macOS)
echo ========================================================

:: 檢查 Python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    where py >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo ❌ 錯誤: 未偵測到 Python，請先至 https://python.org 安裝 Python。
        pause
        exit /b 1
    ) else (
        set PY_CMD=py
    )
) else (
    set PY_CMD=python
)

:: 檢查 FFmpeg
where ffmpeg >nul 2>nul
if %ERRORLEVEL% neq 0 (
    if not exist "%~dp0ffmpeg.exe" (
        echo ⚠️ 提示: 系統 PATH 未偵測到 FFmpeg。
        echo   建議在命令提示字元執行: winget install Gyan.FFmpeg
        echo   或將 ffmpeg.exe 複製到此專案資料夾內。
        echo.
    )
)

echo 🚀 正在啟動桌面錄製工具...
%PY_CMD% app.py

if %ERRORLEVEL% neq 0 (
    pause
)
