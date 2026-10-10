# 開發與打包

給想從原始碼執行、打包或貢獻的人。一般使用請看 [README](../README.md)。

## 從原始碼執行

- 需要 Python 3.9+（含 tkinter）與 FFmpeg。macOS 可再安裝 `pyobjc-framework-Cocoa`（見 [`requirements.txt`](../requirements.txt)）。
- macOS：`./run.sh` 或雙擊 `ScreenRecorder.command`。Windows：雙擊 `ScreenRecorder.bat`。
- 測試：`python3 -m unittest discover -p "test_*.py"`

## 網頁版建置

網頁頁面的 Tailwind CSS 已預編譯並內嵌，CSP 以雜湊放行 inline script。修改 `web_studio/` 的 HTML（class 或 inline script）後必須重建，CI 的 `Check web build` 會檢查：

```bash
cd tools/tailwind && npm install && npm run build
```

## 打包與發行

### macOS

- 雙擊 `AURA REC.app`（可拖到「應用程式」或 Dock），或雙擊 `ScreenRecorder.command`，或在終端機執行 `./run.sh`。
- 首次若出現「無法驗證開發者」：在 `AURA REC.app` 上按右鍵選「開啟」（或使用下方公證腳本進行官方簽章）。

#### macOS 程式碼簽名與 Apple 官方公證 (Notarization)

專案內建一鍵自動化腳本 [`package_macos.sh`](../package_macos.sh)、[`sign_and_notarize.sh`](../sign_and_notarize.sh) 與 [`entitlements.plist`](../entitlements.plist)：

1. **檢查本機簽名證書與工具**：
   ```bash
   ./sign_and_notarize.sh --check
   ```
2. **本機打包與 Ad-hoc 簽名**（自動同步最新程式碼至 `.app` 與 `dist/AURA-REC-macOS.zip`）：
   ```bash
   ./package_macos.sh
   ```
3. **官方發行：Apple Developer ID 簽名與公證**：
   ```bash
   xcrun notarytool store-credentials "notary-profile" \
     --apple-id "your-apple-id@example.com" \
     --team-id "TEAMID1234" \
     --password "xxxx-xxxx-xxxx-xxxx"

   ./sign_and_notarize.sh --keychain-profile "notary-profile"
   ```

### Windows

- 雙擊 `build_windows_exe.bat`，產生 `dist\AURA-REC.exe`，或直接雙擊 `ScreenRecorder.bat` 啟動。
- 桌面程式「說明」選單內建「系統聲音錄製指南…」（macOS BlackHole / Windows 立體聲混音圖文步驟）與「FFmpeg 與硬體加速檢視…」。

### macOS 內嵌 Python

`package_macos.sh` 預設用 PyInstaller 產生自帶 Python 與 Tk 8.6 的獨立 `.app`（輸出在 `dist/bundle/`，再封成 zip / dmg），使用者不需安裝 Python。需要一個 Tk 8.6+ 的 Python（python.org 或 conda 版；系統與 Xcode 內附的 Python 是 Tk 8.5 不行），可用 `PYTHON_BIN=/path/to/python3 ./package_macos.sh` 指定。設 `AURA_PACKAGE_MODE=launcher` 則回到需自備 Python 的輕量啟動器版。目前只產出 arm64（Apple Silicon）。

### 發行流程

推送 `v*` tag 後，CI（`build_desktop.yml`）會在 macOS 與 Windows 上建置並發佈 GitHub Release，附 `SHA256SUMS.txt`。發行包不隨附 FFmpeg（GPL）。

---

## 專案檔案結構

- [`web_studio/index.html`](../web_studio/index.html) — 官方宣傳與互動體驗展台網站（含 Recordly 互動舞台、PiP 去背預覽、9 大核心能力展示與 4 語系切換）。
- [`web_studio/download/AURA-REC.html`](../web_studio/download/AURA-REC.html) — 免安裝單一檔案瀏覽器錄影與剪輯工作站。
- [`app.py`](../app.py) — 桌面程式主錄製中心、畫中畫去背設定、多螢幕預覽與偏好設定。
- [`recorder.py`](../recorder.py) — 跨平台 FFmpeg 硬體加速錄影引擎、多音軌混音與 PiP 去背/虛化濾鏡鏈。
- [`editor_window.py`](../editor_window.py) — Recordly 風格專業影片剪輯工作站（舞台畫布、膠卷刷屏、波形圖、Auto Zoom、隱私遮罩、AI 字幕與浮水印匯出）。
- [`video_editor.py`](../video_editor.py) — 0.5 秒智慧無損裁切 (Smart Cut)、動態焦點偵測、濾鏡合成與雙遍高品質 GIF 匯出。
- [`window_exclusion_watermark.py`](../window_exclusion_watermark.py) — OS 原生視窗錄影穿透排除、敏感視窗自動偵測遮蔽與可視浮水印引擎。
- [`speech_to_text.py`](../speech_to_text.py) — AI 離線語音識別（Whisper CLI + 0 依賴 Smart VAD）與 SRT/VTT 智慧字幕軌管理。
- [`screen_annotation.py`](../screen_annotation.py) — 錄影中全螢幕即時塗鴉畫筆、箭頭、方框與動態聚光燈 (Spotlight) 覆蓋層。
- [`input_overlay.py`](../input_overlay.py) — 滑鼠點擊發光波紋漣漪 (Click Ripple) 與即時按鍵浮水印 (Keystroke HUD)。
- [`i18n.py`](../i18n.py) — 零相依性國際化多語系熱切換引擎（`zh-TW` / `en` / `ja` / `zh-CN`）。
- [`auto_updater.py`](../auto_updater.py) — GitHub Releases 自動檢查更新模組。
- [`region_picker.py`](../region_picker.py) — 自訂範圍框選器與桌面視窗幾何列舉。
- [`platform_utils.py`](../platform_utils.py) — 系統環境偵測、字型、High-DPI、GPU 硬體編碼器與診斷工具。
- [`aura_widgets.py`](../aura_widgets.py) — 極光漸層圓角按鈕、勾選框與雙色範圍滑桿元件。
- [`package_macos.sh`](../package_macos.sh) / [`sign_and_notarize.sh`](../sign_and_notarize.sh) — macOS App Bundle 打包、Hardened Runtime 簽名與 Apple `notarytool` 公證腳本。
