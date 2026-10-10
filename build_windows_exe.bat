@echo off
REM ============================================================
REM   AURA REC - Windows 一鍵編譯與打包器
REM   產生單一執行檔 AURA-REC.exe 與免安裝壓縮包 AURA-REC-Windows-x64.zip
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

echo.
echo   ====================================================
echo      AURA REC  -  Windows 桌面應用一鍵打包器
echo   ====================================================
echo.

REM --- 1. 檢查 Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [X] 找不到 Python。請先安裝 Python 3：https://www.python.org/downloads/
    echo     安裝時請務必勾選 "Add Python to PATH"。
    pause
    exit /b 1
)
echo [1/5] 已偵測到 Python 環境
python --version

REM --- 2. 檢查並安裝 PyInstaller ---
echo.
echo [2/5] 檢查 PyInstaller...
python -m pip install --upgrade pip >nul 2>nul
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo [X] PyInstaller 安裝失敗，請檢查網路連線。
    pause
    exit /b 1
)

REM --- 3. 檢查 FFmpeg ---
echo.
echo [3/5] 檢查 FFmpeg 工具...
set "LOCAL_FFMPEG="
if defined AURA_NO_FFMPEG_BUNDLE (
    echo      AURA_NO_FFMPEG_BUNDLE 已設定：不隨附 FFmpeg ^(GPL^)，使用者請自行安裝：winget install Gyan.FFmpeg
    goto :ffmpeg_done
)
if exist "%~dp0ffmpeg.exe" (
    set "LOCAL_FFMPEG=%~dp0ffmpeg.exe"
    echo      找到專案目錄下的 ffmpeg.exe
) else (
    where ffmpeg >nul 2>nul
    if not errorlevel 1 (
        for /f "delims=" %%i in ('where ffmpeg') do set "LOCAL_FFMPEG=%%i"
        echo      找到系統 PATH 中的 FFmpeg: !LOCAL_FFMPEG!
    ) else (
        echo      [提示] 未偵測到 ffmpeg.exe。使用者亦可於 Windows 執行：
        echo             winget install Gyan.FFmpeg
    )
)

:ffmpeg_done
REM --- 4. 編譯單一 EXE ---
echo.
echo [4/5] 正在編譯 AURA-REC.exe（約需 1-2 分鐘）...
pyinstaller --noconfirm --onefile --windowed ^
    --name "AURA-REC" ^
    --icon "AURA-REC.ico" ^
    --add-data "fonts;fonts" ^
    --add-data "web_studio\download\AURA-REC.html;." ^
    app.py

if errorlevel 1 (
    echo [X] 編譯失敗。請把上方錯誤訊息截圖回報。
    pause
    exit /b 1
)

REM --- 5. 複製相依工具並製作 ZIP / 安裝檔 ---
echo.
echo [5/5] 整理發佈檔案與壓縮包...
if not exist "%~dp0dist" mkdir "%~dp0dist"

if defined LOCAL_FFMPEG (
    if exist "!LOCAL_FFMPEG!" (
        copy /y "!LOCAL_FFMPEG!" "%~dp0dist\ffmpeg.exe" >nul
        echo      已將 ffmpeg.exe 複製至 dist 資料夾以供免安裝使用
        REM ffprobe 與授權檔放在 ffmpeg 旁邊
        for %%F in ("!LOCAL_FFMPEG!") do (
            if exist "%%~dpFffprobe.exe" copy /y "%%~dpFffprobe.exe" "%~dp0dist\ffprobe.exe" >nul
            if exist "%%~dpFFFMPEG-COPYING.GPLv2" copy /y "%%~dpFFFMPEG-COPYING.GPLv2" "%~dp0dist\FFMPEG-COPYING.GPLv2" >nul
        )
    )
)

REM 使用 PowerShell 製作免安裝 ZIP 包
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$dist = '%~dp0dist'; $zip = Join-Path $dist 'AURA-REC-Windows-x64.zip'; Remove-Item -Force -ErrorAction SilentlyContinue $zip; $files = @((Join-Path $dist 'AURA-REC.exe')); foreach ($n in 'ffmpeg.exe','ffprobe.exe','FFMPEG-COPYING.GPLv2') { if (Test-Path (Join-Path $dist $n)) { $files += (Join-Path $dist $n) } }; foreach ($n in 'THIRD_PARTY_NOTICES.md','LICENSE') { $files += (Join-Path '%~dp0' $n) }; Compress-Archive -Path $files -DestinationPath $zip; Write-Host '      已建立免安裝 ZIP 包: ' $zip"

REM 檢查是否有 Inno Setup 編譯器 (ISCC.exe)
set "ISCC_PATH="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"

if defined ISCC_PATH (
    echo.
    echo      偵測到 Inno Setup，正在製作 AURA-REC-Setup.exe 安裝精靈...
    "!ISCC_PATH!" "%~dp0installer\AURA-REC-Setup.iss" >nul
    if not errorlevel 1 (
        echo      [OK] 已成功產生安裝精靈：%~dp0dist\AURA-REC-Setup.exe
    )
)

echo.
echo   ====================================================
echo      [OK] Windows 桌面應用打包完成！
echo   ====================================================
echo.
echo   檔案位於 dist 目錄：
echo     1. 執行檔:       dist\AURA-REC.exe
echo     2. 免安裝 ZIP:   dist\AURA-REC-Windows-x64.zip
if exist "%~dp0dist\AURA-REC-Setup.exe" (
echo     3. 安裝精靈:     dist\AURA-REC-Setup.exe
)
echo.
if not defined CI pause
endlocal
exit /b 0
