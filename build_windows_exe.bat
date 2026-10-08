@echo off
REM ============================================================
REM   AURA REC - Windows 一鍵編譯器 (Double-click to build .exe)
REM   產生帶 AURA 圖示的單一執行檔 AURA-REC.exe
REM ============================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo.
echo   ============================================
echo      AURA REC  -  Windows EXE 編譯器
echo   ============================================
echo.

REM --- 1. 檢查 Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [X] 找不到 Python。請先安裝 Python 3：https://www.python.org/downloads/
    echo     安裝時請務必勾選 "Add Python to PATH"。
    pause
    exit /b 1
)
echo [1/4] 已偵測到 Python
python --version

REM --- 2. 安裝 / 升級 PyInstaller ---
echo.
echo [2/4] 檢查並安裝 PyInstaller...
python -m pip install --upgrade pip >nul 2>nul
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo [X] PyInstaller 安裝失敗，請檢查網路連線。
    pause
    exit /b 1
)

REM --- 3. 編譯單一 exe（視窗模式、內嵌圖示、附帶 web_studio 資源） ---
echo.
echo [3/4] 正在編譯 AURA-REC.exe（約需 1-2 分鐘）...
pyinstaller --noconfirm --onefile --windowed ^
    --name "AURA-REC" ^
    --icon "AURA-REC.ico" ^
    --add-data "web_studio;web_studio" ^
    app.py
if errorlevel 1 (
    echo [X] 編譯失敗。請把上方錯誤訊息截圖回報。
    pause
    exit /b 1
)

REM --- 4. 完成 ---
echo.
echo [4/4] 完成！
echo.
echo   [OK] 編譯成功！你的應用程式在：
echo        %~dp0dist\AURA-REC.exe
echo.
echo   直接雙擊 dist\AURA-REC.exe 即可使用（可拖到桌面建立捷徑）。
echo.
pause
endlocal
