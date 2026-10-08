# 🎥 LiteScreenRecorder (跨平台輕量桌面螢幕錄製與剪輯工具)

專為 **macOS** 與 **Windows** 雙平台打造的高效能、極簡輕量螢幕錄製與剪輯後製工具。採用 Python 原生 GUI 與 FFmpeg 硬體加速編碼，無肥大依賴（無需 500MB+ 的 Electron），秒速啟動、錄製順暢、資源極低！

---

## ✨ 核心特色

1. **🌐 AURA REC // 獲獎級 Web 沈浸式全螢幕錄製與剪輯工作站**
   - **Awwwards / Webby / FWA 標準**：採用深邃黑曜石科技奢華風（Dark Neo-Brutalist & Cyber Elegance），具備 1px 賽博微光邊界與細緻毛玻璃材質。
   - **即時螢幕標註與畫筆系統**：支援自由畫筆、矩形框、霓虹色系切換與一鍵清空，教學與演示無往不利。
   - **電影級色彩濾鏡與倍速播放**：內建原色、賽博極光 (Cyberpunk)、黑白底片 (Noir)、暖調膠片 (Warm Film) 與 0.5x~2.0x 倍速。
   - **自由拖曳視訊鏡頭 (Draggable Facecam PiP)**：鏡頭視窗可隨意拖放於舞台任何位置。
   - **劇院級環境光自適應背光 (Dynamic Ambient Glow)**：即時採樣視訊主色調並柔化擴散至監視窗背景，營造極致劇院沈浸感。
   - **雙軌非線性時間軸 (Non-linear Dual Track)**：包含影像膠卷影格條 (V1) 與 60 FPS 實時跳動的 Web Audio 音訊波形頻譜 (A1)。
   - **合成器微互動音效**：使用純 Web Audio API 合成機械阻尼點擊音、完成弦音與倒數嗶聲。
   - **雙擊即開**：macOS 雙擊 `open_studio.command`、Windows 雙擊 `open_studio.bat` 即刻在瀏覽器中暢享！
2. **🌐 macOS & Windows 雙平台桌面客戶端支援**
   - **📜 最近錄影管理藝廊 (Recent Recordings Gallery)**：主面板即時列出最近錄製檔案，支援一鍵播放 (▶)、一鍵剪輯 (✂)、檔案定位與安全刪除 (🗑)。
   - **⚡ 進階剪輯與社群比例裁切**：支援 0.5x~2.0x 倍速調整、9:16 短影音 (Shorts/Reels/TikTok) / 16:9 / 1:1 比例裁切與色彩增強。
   - **macOS**：原生整合 `AVFoundation` 螢幕音訊捕獲與 Apple Silicon `VideoToolbox` 硬體編碼。
   - **Windows**：原生支援 `GDI Grab` 全螢幕擷取、DirectShow 麥克風與立體聲混音，支援 NVIDIA NVENC / Intel QSV / AMD AMF 硬體加速。
   - **High-DPI 高解析度優化**：Windows 4K/2K 縮放不模糊、macOS Retina 超清晰字體。
3. **💊 懸浮膠囊模式 (Mini Floating Pill)**
   - 開始錄影後可自動收合成小巧置頂懸浮條（`● REC 00:01:23 [⏹ 停止]`），不遮擋畫面，隨意拖曳至螢幕角落。
   - 停止錄製時自動恢復控制面板。
3. **✂️ 內建即時影片剪輯與後製 (Video Trimmer & Editor)**
   - **錄完立即剪輯**：錄製完成自動引導進入剪輯視窗，亦可在主介面點擊「✂️ 剪輯影片」隨時挑選歷史影片。
   - **影格即時預覽**：拖動時間軸即時擷取畫面縮圖，支援 `±0.1s` / `±1s` 精確微調與區段播放。
   - **起點/終點靈活裁切**：一鍵設置起點與終點，即時計算選取長度。
   - **⚡ 無損極速剪裁**：使用 Stream Copy 技術，0.5 秒瞬間完成，畫質 100% 原始無損！
   - **🎯 精準幀剪輯**：精確至單幀裁切，並支援「🔇 一鍵去除聲音 (靜音剪輯)」。
   - **🎞️ 匯出為 GIF 動畫**：內建雙遍高畫質調色盤演算法，完美轉出流暢 GIF，適合分享至 GitHub、Slack、Notion。
   - **🎵 提取純音訊**：一鍵將影片中的語音單獨提取為 MP3 / M4A 聲音檔。
4. **🎙️ 音訊靈活錄製（支援系統聲音）**
   - **麥克風收音**：錄製會議發言、解說旁白。
   - **系統音效錄製**：
     - **Windows**：直接選取「立體聲混音 (Stereo Mix)」或虛擬聲卡。
     - **macOS**：支援 `Microsoft Teams Audio` 或 `BlackHole 2ch` 虛擬聲卡。
   - **靜音模式**：純畫面錄影。
5. **📐 多檔位解析度與幀率 (FPS)**
   - **解析度**：Retina / 4K 原生解析度 (免縮放最高清)、2K (2560x1440)、1080p FHD、720p HD。
   - **幀率**：30 FPS (平衡推薦)、60 FPS (高流暢動態)、15 FPS (極度省空間)。
6. **⏱️ 3 秒倒數準備與系統音效回饋**
   - 倒數 3、2、1 提示音，讓您從容切換到想錄製的視窗。
7. **⌨️ 快捷鍵支援**
   - 按 `Space`（空白鍵）、`F9`、`Cmd + R` (macOS) 或 `Ctrl + R` (Windows) 立即開始 / 停止錄製。
8. **📁 智慧檔案管理**
   - 一鍵「開啟資料夾 (Reveal in Finder / Explorer)」。
   - 一鍵「播放最新影片 (預設播放器)」。
   - 支援自由變更儲存目錄。

---

## 🚀 啟動方式

### 🍎 macOS 使用者：
- **方法 1（最推薦 · 一鍵圖示）**：直接雙擊 **`AURA REC.app`** 應用程式圖示即可開啟。
  - 可拖到「應用程式」資料夾或 Dock，像一般 App 一樣使用。
  - ⚠️ 首次開啟若出現「無法驗證開發者」：在 `AURA REC.app` 上**按右鍵 → 開啟 → 再按一次「開啟」**（因未經 Apple 簽章，僅首次需要）。
- **方法 2**：在 Finder 中雙擊 **`ScreenRecorder.command`**
- **方法 3**：在終端機執行 `./run.sh` 或 `python3 app.py`

### 🪟 Windows 使用者：
- **方法 1（最推薦 · 產生一鍵圖示 .exe）**：雙擊 **`build_windows_exe.bat`**，它會自動安裝 PyInstaller 並編譯出帶 AURA 圖示的 **`dist\AURA-REC.exe`**。
  - 完成後雙擊 `dist\AURA-REC.exe` 即可使用，可拖到桌面建立捷徑。
  - 僅需編譯一次；之後都直接用產生的 `.exe`。
- **方法 2**：在檔案總管中雙擊 **`ScreenRecorder.bat`**
- **方法 3**：在命令提示字元 (CMD) 或 PowerShell 執行 `python app.py`

> 💡 **一鍵圖示 vs 腳本**：macOS 的 `AURA REC.app` 已預先打包好，開箱即點。Windows 的單一 `.exe` 因平台限制必須在 Windows 上編譯一次（這就是 `build_windows_exe.bat` 做的事）。兩者底層都是同一套 Python 引擎。

---

## 🛠️ 前置需求 (FFmpeg 安裝)

本工具為極輕量化設計，僅需系統具備 Python 3 與 FFmpeg：

- **macOS**：
  ```bash
  brew install ffmpeg
  ```
- **Windows**：
  在 PowerShell / CMD 執行：
  ```cmd
  winget install Gyan.FFmpeg
  ```
  *(或至 [gyan.dev/ffmpeg](https://www.gyan.dev/ffmpeg/builds/) 下載並將 `ffmpeg.exe` 放入專案資料夾)*

---

## 🎧 如何錄製電腦內部聲音（系統音效）？

- **Windows**：
  1. 在 Windows 右下角聲音圖示按右鍵 >「聲音設定」>「更多音效設定」。
  2. 切換到「錄製」分頁，在空白處按右鍵勾選「顯示已停用的裝置」。
  3. 將 **「立體聲混音 (Stereo Mix)」** 按右鍵「啟用」。
  4. 回到本工具的音訊來源下拉選單，選擇 `Stereo Mix` 即可錄製電腦內部音樂與系統音！
- **macOS**：
  1. 若已安裝 Microsoft Teams，直接選取 `Microsoft Teams Audio`。
  2. 或安裝 BlackHole (`brew install blackhole-2ch`)，在「音訊 MIDI 設定」建立多重輸出裝置即可。

---

## 📂 專案檔案結構

- [`web_studio/index.html`](file://web_studio/index.html) - **AURA REC 獲獎級沈浸式 Web 錄影與非線性剪輯工作站**（Awwwards / Webby / FWA 標準）。
- `AURA REC.app` - **macOS 一鍵應用程式**（雙擊圖示即開，自包含完整引擎與 Web 工作站）。
- `build_windows_exe.bat` - **Windows 一鍵編譯器**：雙擊自動產生帶 AURA 圖示的 `dist\AURA-REC.exe`。
- `AURA-REC.ico` - Windows 應用程式圖示（內嵌 16–256px 多尺寸）。
- [`open_studio.command`](file://open_studio.command) - macOS 雙擊即開 Web 工作站。
- [`open_studio.bat`](file://open_studio.bat) - Windows 雙擊即開 Web 工作站。
- [`app.py`](file://app.py) - 跨平台桌面客戶端 GUI、懸浮膠囊視窗、快捷鍵調度。
- [`platform_utils.py`](file://platform_utils.py) - 跨平台輔助庫（系統偵測、字體、High-DPI、系統音效、檔案定位、GPU 編碼器探測）。
- [`recorder.py`](file://recorder.py) - 跨平台錄影核心（macOS AVFoundation / Windows GDI & DirectShow / GPU 硬體加速）。
- [`editor_window.py`](file://editor_window.py) - 桌面影片剪輯視窗（即時影格預覽、時間軸微調、起終點標記與多種匯出）。
- [`video_editor.py`](file://video_editor.py) - 剪輯後製引擎（無損極速裁剪、精準重編碼、GIF 雙遍調色盤、音訊分離）。
- [`ScreenRecorder.command`](file://ScreenRecorder.command) - macOS 桌面端雙擊即開執行檔。
- [`ScreenRecorder.bat`](file://ScreenRecorder.bat) - Windows 桌面端雙擊即開批次檔。
- [`run.sh`](file://run.sh) - Linux / macOS Shell 啟動腳本。
- `recordings/` - 錄影成品預設儲存目錄。
