# AURA REC

真正把畫面與聲音留下來的原生桌面錄影與剪輯工作站。

- **桌面應用程式（主要推薦）**：支援 macOS（`AURA REC.app` / DMG / ZIP）與 Windows（`AURA-REC.exe` / ZIP）。具備晶片級硬體加速（Apple Silicon VideoToolbox / Windows Direct3D 11 WGC & NVENC）、電腦系統聲音與麥克風獨立多音軌內錄、動態視窗追蹤、全域快捷鍵（`F9` 錄製/停止、`F8` 暫停/繼續、`F7` 截圖、`F6` 螢幕即時塗鴉與聚光燈）、畫中畫（PiP）人像智慧去背與景深虛化、視窗隱私排除與防盜動態浮水印、AI 離線語音識別智慧字幕軌、0.5 秒極速智慧無損剪輯，以及繁中 / EN / 日本語 / 簡中 4 語系即時熱切換。
- **瀏覽器工作站（免安裝體驗版）**：輕量單一檔案 `AURA-REC.html`。官網在 [malilion.github.io/Record](https://malilion.github.io/Record/)，可直接在線上或離線雙擊開啟，支援 WebRTC 錄製、純前端 WebCodecs MP4 霓虹外框匯出、`.auraproj` 專案預設集、畫中畫鏡頭景深虛化/去背與 4 語系切換。

---

## 核心功能一覽

| 模組領域 | 桌面原生版 (`app.py` / `AURA REC.app`) | 瀏覽器網頁工作站 (`AURA-REC.html`) |
| --- | --- | --- |
| **硬體加速錄影** | Apple Silicon VideoToolbox / Windows WGC (`ddagrab`) + NVENC / QSV / AMF（最高 4K 60/120 FPS） | WebRTC `getDisplayMedia` + 硬體加速 WebCodecs MP4 封裝 |
| **音訊收音架構** | 系統聲音 + 麥克風 **獨立多音軌 (Multi-track)** 或即時混音 (`amix`) | 系統分享音訊 + 麥克風 WebAudio 即時混音 + VU 頻譜儀 |
| **錄影中互動標註** | `F6` 全螢幕透明畫布：**自由畫筆、指向箭頭、重點方框、動態聚光燈 (Spotlight)** + 點擊波紋 & 按鍵 HUD | 畫布畫筆、矩形、聚光燈、點擊物理波紋、按鍵 HUD |
| **畫中畫 (PiP) 鏡頭** | 圓形霓虹泡泡 / 圓角矩形，內建 **6 種背景模式**（原始、人像景深虛化、純人像去背透空、綠/藍幕扣像、極光背景）+ 桌面懸浮小圓圈與即時試看 | 可拖曳圓形視訊泡泡，內建 **原始 / 景深虛化 (Blur) / 人像去背 (Cutout) / 極光虛擬背景** |
| **隱私與版權保護** | **OS 原生控制列穿透隱藏** (`NSWindowSharingNone` / `WDA_EXCLUDEFROMCAPTURE`)、敏感視窗自動偵測模糊/馬賽克/盾牌遮蔽、后製局部模糊遮罩、**5 大模式智慧防盜浮水印**（含動態 Lissajous 巡航防盜與滿版網格） | 本地沙盒零上傳、自訂視窗標題與品牌預設集 (`.auraproj`) |
| **AI 智慧字幕與剪輯** | **AI 離線語音識別字幕軌**（Whisper Metal GPU + 0 依賴離線 Smart VAD）、0.5 秒智慧無損裁切 (Smart Cut)、Auto Zoom 智慧運鏡、膠卷刷屏 (Skimming)、音訊波形軌、直式 9:16 模糊補位、雙遍高清 GIF | 雙軌膠卷與波形時間軸、In/Out 裁切、濾鏡與倍速、WebM / MP4 / WAV / PNG 匯出 |
| **多語系與發佈維護** | **繁體中文 / English / 日本語 / 简体中文** 免重啟即時無損熱切換、GitHub Releases 自動檢查更新、macOS `notarytool` 官方簽名公證腳本 | **繁體中文 / English / 日本語 / 简体中文** 即時切換、`localStorage` 工作階段自動記憶 |

---

## 為什麼選擇桌面版？

1. **晶片級硬體加速**：Apple Silicon (M1~M4) 與 NVIDIA / Intel / AMD 原生編碼，4K 60FPS / 120FPS 錄製依然流暢不發燙，告別瀏覽器轉碼掉幀與 CPU 飆高。
2. **真正的系統聲音內錄與獨立多音軌**：徹底突破 macOS 瀏覽器無法擷取電腦聲音的限制，支援將麥克風寫入 Track 1、系統音效寫入 Track 2，後製可獨立調整人聲與背景音。
3. **動態視窗追蹤與硬體級自身穿透隱藏**：錄製單一視窗時，視窗拖移會即時自動追蹤裁切位置；透過 macOS `NSWindowSharingNone` 與 Windows `WDA_EXCLUDEFROMCAPTURE`，錄影控制條對錄影畫面完全透明隱形，肉眼仍可正常操作。
4. **全域快捷鍵與即時塗鴉聚光燈**：`F8` 暫停/繼續（暫停時間不計入總長）、`F9` 停止、`F7` 快速截圖、`F6` 隨時喚出螢幕塗鴉與動態聚光燈。
5. **串流直出 MP4 / MOV**：直接即時寫入硬碟，長錄影不爆記憶體，具備睡眠防護與斷電安全保護。

---

## 瀏覽器工作站

### 做得到什麼

- 錄整個螢幕、一個視窗，或一個分頁。選哪一塊，由瀏覽器的分享視窗決定。
- 分享時可勾選系統聲音。底部的「麥克風收音」是另外一路，可以和畫面聲音混在一起。
- 按下後先倒數 3 秒。空白鍵可以開始或停止。
- 預覽上可以畫筆、矩形、聚光燈，顏色可換。畫幅導引有 16:9、9:16、1:1。按鍵會浮在畫面上。
- **圓形視訊鏡頭 (Camera PiP) 與智慧背景模式**：鏡頭泡泡可自由拖曳位置，並支援切換 **原始背景、景深虛化 (Blur)、人像去背 (Cutout)、極光虛擬背景**；舞台周圍的環境光會跟著畫面顏色即時律動。
- **多語系即時切換 (`🌐`)**：頂部導航列支援一鍵切換 **繁體中文、English、日本語、简体中文**。
- 濾鏡：原色、賽博、黑白、暖調。播放速度 0.5x、1x、1.5x、2x。
- 「匯出選取片段」只存時間軸起點到終點那一段 WebM。起點和終點就是整段時，直接存原來的檔。「導出精華截圖」把目前這一格連同畫筆存成 PNG。
- 「純前端 WebCodecs MP4 匯出」：整合 WebCodecs API 與 mp4-muxer，免安裝任何軟體即可在瀏覽器端極速封裝帶有自訂極光/暮光漸層背景、macOS 質感視窗外框、陰影深度與圓角的展示 MP4。
- 「專案存檔與預設集 (`.auraproj`)」：支援將選定的漸層背景、視窗陰影（微光/劇院/霓虹）、圓角比例（緊湊/標準/圓潤）與自訂視窗標題儲存為 `.auraproj` 專案檔（JSON）或自訂範本；支援拖曳 `.auraproj` 或 `.json` 檔案直入工作站瞬間套用，並具備工作階段自動儲存與載入恢復。
- 也可以按「匯入本機影片」，拿一支現成影片來預覽；或直接將 MP4/WebM/MOV 影片拖曳入視窗自動載入。

### 怎麼用

1. 打開 [官網](https://malilion.github.io/Record/)，體驗互動展台或按「開啟網頁工作站」/ 下載 `AURA-REC.html`。
2. 雙擊那個檔。請用 Chrome、Edge 或 Brave，並允許螢幕分享。
3. 按「啟動螢幕錄製」。要電腦裡的聲音，在分享視窗勾選。要自己的聲音，打開底部的麥克風。
4. 倒數結束後開始。再按空白鍵，或按懸浮條上的「停止錄製」。
5. 用時間軸看。要指出某一格，用左上角的畫筆。要換看法，用右上角的濾鏡和倍速。
6. 在時間軸標好起點和終點，按「✨ 匯出霓虹外框 (MP4)」或「原始片段 (WebM)」。要圖就按「導出精華截圖」。

第一次開啟需要網路，用來載入字型與介面。本機也可以直接雙擊 `open_studio.command`（macOS）或 `open_studio.bat`（Windows），開的是同一個工作站。

---

## 桌面程式

要比較長的錄影、指定一個視窗、硬體編碼，或使用 AI 智慧字幕、人像去背、視窗排除、防盜浮水印與無損裁切時，用這一支。

### 做得到什麼

- **多範圍與多螢幕擷取**：錄整個螢幕、拖一塊自訂範圍，或錄畫面上的某一個視窗（檔名會自動帶上該程式名稱）。提供畫面即時縮圖、多螢幕全景對比與螢幕編號識別閃爍。
- **彈性畫質與高幀率**：解析度支援原生、2K、1080p、720p，以長邊對齊並保留比例（直向範圍不會被拉成橫向）。幀率支援 15、30、60、120 FPS（電競/極限流暢）。一般文書電腦（8GB RAM 或 4 核心以下）會自動預設較輕量的配置，硬體加速預設開啟。
- **智慧容量預估與自動分段**：畫質分較省、標準、較清晰（標準畫質 1080p 約一小時 400 MB）。準備錄影時即時顯示每分鐘預估大小與剩餘可錄時間。可存成 MP4 或 MOV，支援 1~60 分鐘自動停止，或每 5、10、30 分鐘自動分段存檔。
- **膠卷時間軸即時滑鼠刷屏 (Scrubbing / Skimming) 與拖曳 In/Out 握把**：畫布級故事板膠卷（Filmstrip Timeline），滑鼠左右懸浮滑動時即時刷屏，黃色微光指針隨游標移動並浮現精確時間戳膠囊，中央預覽區 0ms 快取即時渲染對應影格；兩側配置翠綠 `[` 與珊瑚紅 `]` 拖曳握把，直觀調整剪輯區間。
- **極速精準智慧無損裁切 (Smart Cut 0.5s)**：透過快速封包分析關鍵影格（I-Frame）分佈，實現「首尾非關鍵影格毫秒級精準微編碼、主體骨幹全段 100% 原始位元無損串流複製」的智慧拼接架構，毫秒級精準剪裁不差一格，同時維持 0.5 秒瞬間直出。
- **音訊波形圖可視化 (Audio Waveform Track)**：膠卷時間軸下方配備高精準度音訊振幅波形軌道，說話語音處以極光翠綠/青色立體波峰呈現，停頓與空白段落呈平緩基準線，方便一眼識破贅詞段落。
- **麥克風與系統音效獨立多音軌 (Multi-track)**：支援同時指定「麥克風（Track 1）」與「系統音（Track 2）」，附加 QuickTime / Premiere 相容之 Stream Metadata 標籤（`Microphone` 與 `System Audio`）。無損裁切與進階匯出均 100% 完整保留所有獨立音軌。
- **智慧自動縮放運鏡 (Auto Zoom)**：支援平滑推進與退回、平滑推進特寫、全程固定特寫，可在預覽畫布直接點擊/拖曳設定焦點（帶發光十字準星）或使用「🎯 智慧偵測焦點」自動分析畫面動態中心。
- **隱私模糊與局部馬賽克遮罩 (Blur & Mosaic Masks)**：支援在剪輯工作站預覽畫布上直接用滑鼠拖曳框選敏感資訊（API Key、密碼、個資），提供高斯模糊與局部馬賽克兩種模式，支援「全片套用」或「僅選取區段套用」。
- **畫中畫（PiP）人臉鏡頭與人像智慧去背/虛化（Virtual Background & Blur）**：支援圓形相機（極光霓虹藍 / 純白外框）與圓角矩形，可置於四角並調尺寸（小 200px / 中 260px / 大 340px）。內建 **6 種背景模式**：「原始鏡頭」、「人像背景虛化（輕微/標準/強烈三段景深）」、「純人像去背透空」、「綠幕扣像」、「藍幕扣像」與「極光深色背景」，提供「鏡頭試看 👁」即時預覽與可拖曳桌面小圓圈。
- **視窗排除與智慧浮水印保護 (Window Exclusion & Watermark Protection)**：
  - **視窗隱私排除 (Window Exclusion)**：支援 OS 原生硬體級自身錄影控制列穿透隱藏（macOS `NSWindowSharingNone` / Windows `WDA_EXCLUDEFROMCAPTURE`），以及指定開啟視窗或自動偵測敏感應用（LINE、WeChat、1Password、Bitwarden、Keychain、密碼、無痕視窗、網路銀行與自訂關鍵字），自動於錄影中套用高斯模糊、馬賽克或深色隱私盾牌遮蔽，亦可開啟桌面實體防窺盾牌覆蓋。
  - **智慧防盜浮水印 (Watermark Protection)**：零外部依賴高解析度 RGBA PNG 浮水印渲染引擎（macOS CoreText + 純 Python 點陣字型雙引擎），支援 **5 大模式**（角落品牌簽名、錄影時間戳記簽章、沿 Lissajous 曲線平滑移動之動態巡航防盜浮水印、滿版斜紋防盜網格、自訂 PNG Logo 圖片）、5 種視覺風格與 3 段不透明度，支援錄影即時烙印與剪輯工作站後製燒錄。
- **滑鼠點擊發光波紋與按鍵顯示 (Click Ripple & Keystroke HUD)**：錄製時在點擊處產生發光水波紋漣漪（左鍵極光藍、右鍵珊瑚紅），並於底部浮現半透明圓角按鍵藥丸條（支援 macOS `⌘/⌥/⌃/⇧` 組合鍵與連續打字顯示）。
- **螢幕即時塗鴉與聚光燈 (Live Screen Annotation & Spotlight)**：隨時按 `F6`（或 `⇧⌘D` / `⇧Ctrl+D`）或點選迷你條「塗鴉」按鈕，喚出全螢幕置頂透明畫布。具備 **自由手繪畫筆、指向箭頭、重點矩形框、動態聚光燈 (Spotlight)** 4 大工具、5 色霓虹調色盤、3 段粗細、無限步復原 (`Cmd+Z`) 與一鍵清空 (`C`)。
- **AI 離線語音識別與智慧字幕軌 (Speech-to-Text & Subtitles)**：支援 Whisper-CLI（`whisper.cpp` Metal GPU 加速）與內建 0 依賴離線 Smart VAD（語音活動偵測與毫秒級智慧分句），0.1 秒自動識別人聲片段並渲染於時間軸字幕軌與預覽畫布；支援就地編輯、SRT/VTT 雙向匯入匯出、MP4/MOV 軟字幕軌封裝 (`mov_text`) 與同名 `.srt` 檔同步匯出。
- **國際化多語系即時熱切換 (i18n)**：內建 `zh-TW`（繁體中文）、`en`（English）、`ja`（日本語）、`zh-CN`（简体中文）4 大語系，自動偵測系統語言，並支援於主視窗頂部 `🌐` 按鈕、剪輯工作站頂部 `🌐` 按鈕、選單列「語言 (Language)」或「偏好設定」免重啟一鍵即時切換。
- **軟體內建自動檢查更新 (Auto Updater)**：串接 GitHub Releases API 自動比對語意化版本號，支援啟動靜默檢查與手動檢查更新。

---

### 怎麼打開與打包

#### macOS

- 雙擊 `AURA REC.app`（可拖到「應用程式」或 Dock），或雙擊 `ScreenRecorder.command`，或在終端機執行 `./run.sh`。
- 首次若出現「無法驗證開發者」：在 `AURA REC.app` 上按右鍵選「開啟」（或使用下方公證腳本進行官方簽章）。

##### macOS 程式碼簽名與 Apple 官方公證 (Notarization)

專案內建一鍵自動化腳本 [`package_macos.sh`](file://package_macos.sh)、[`sign_and_notarize.sh`](file://sign_and_notarize.sh) 與 [`entitlements.plist`](file://entitlements.plist)：

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

#### Windows

- 雙擊 `build_windows_exe.bat`，產生 `dist\AURA-REC.exe`，或直接雙擊 `ScreenRecorder.bat` 啟動。
- 桌面程式「說明」選單內建「系統聲音錄製指南…」（macOS BlackHole / Windows 立體聲混音圖文步驟）與「FFmpeg 與硬體加速檢視…」。

---

### 快捷鍵一覽

| 動作 | 快捷鍵 |
| --- | --- |
| 開始或停止錄影 | `空白鍵`、`F9`、`Cmd + R`（macOS）或 `Ctrl + R`（Windows） |
| 取消 3 秒倒數 | 再按一次開始，或 `Esc` |
| 暫停或繼續錄影 | `F8` |
| 螢幕即時塗鴉與聚光燈 | `F6`、`Shift + Cmd + D` 或 `Shift + Ctrl + D`（塗鴉中按 `1~4` 換工具、`Cmd+Z` 復原、`C` 清空、`Esc` 退出） |
| 快速截圖 | `F7` |
| 迷你懸浮條展開回主畫面 | `Esc` |
| 複製最新錄影檔案 | `Shift + Cmd + C`（Windows 為 `Shift + Ctrl + C`） |
| 偏好設定 | `Cmd + ,`（Windows 為 `Ctrl + ,`） |
| 剪輯工作站快捷鍵 | `Space` 播放/暫停、`I` 設起點、`O` 設終點、`←/→` 微調時間、`Cmd/Ctrl + E` 匯出 |

---

### 安裝 FFmpeg

桌面程式需要 FFmpeg（`AURA REC.app` 打包時若本機已安裝 FFmpeg 會自動內嵌一份至 `Contents/Resources/bin/ffmpeg`）。

- **macOS**：
  ```bash
  brew install ffmpeg
  ```
- **Windows（PowerShell 或 CMD）**：
  ```cmd
  winget install Gyan.FFmpeg
  ```

---

## 專案檔案結構

- [`web_studio/index.html`](file://web_studio/index.html) — 官方宣傳與互動體驗展台網站（含 Recordly 互動舞台、PiP 去背預覽、8 大核心能力展示與 4 語系切換）。
- [`web_studio/download/AURA-REC.html`](file://web_studio/download/AURA-REC.html) — 免安裝單一檔案瀏覽器錄影與剪輯工作站。
- [`app.py`](file://app.py) — 桌面程式主錄製中心、畫中畫去背設定、多螢幕預覽與偏好設定。
- [`recorder.py`](file://recorder.py) — 跨平台 FFmpeg 硬體加速錄影引擎、多音軌混音與 PiP 去背/虛化濾鏡鏈。
- [`editor_window.py`](file://editor_window.py) — Recordly 風格專業影片剪輯工作站（舞台畫布、膠卷刷屏、波形圖、Auto Zoom、隱私遮罩、AI 字幕與浮水印匯出）。
- [`video_editor.py`](file://video_editor.py) — 0.5 秒智慧無損裁切 (Smart Cut)、動態焦點偵測、濾鏡合成與雙遍高品質 GIF 匯出。
- [`window_exclusion_watermark.py`](file://window_exclusion_watermark.py) — OS 原生視窗錄影穿透排除、敏感視窗自動偵測遮蔽與智慧防盜浮水印引擎。
- [`speech_to_text.py`](file://speech_to_text.py) — AI 離線語音識別（Whisper CLI + 0 依賴 Smart VAD）與 SRT/VTT 智慧字幕軌管理。
- [`screen_annotation.py`](file://screen_annotation.py) — 錄影中全螢幕即時塗鴉畫筆、箭頭、方框與動態聚光燈 (Spotlight) 覆蓋層。
- [`input_overlay.py`](file://input_overlay.py) — 滑鼠點擊發光波紋漣漪 (Click Ripple) 與即時按鍵浮水印 (Keystroke HUD)。
- [`i18n.py`](file://i18n.py) — 零相依性國際化多語系熱切換引擎（`zh-TW` / `en` / `ja` / `zh-CN`）。
- [`auto_updater.py`](file://auto_updater.py) — GitHub Releases 自動檢查更新模組。
- [`region_picker.py`](file://region_picker.py) — 自訂範圍框選器與桌面視窗幾何列舉。
- [`platform_utils.py`](file://platform_utils.py) — 系統環境偵測、字型、High-DPI、GPU 硬體編碼器與診斷工具。
- [`aura_widgets.py`](file://aura_widgets.py) — 極光漸層圓角按鈕、勾選框與雙色範圍滑桿元件。
- [`package_macos.sh`](file://package_macos.sh) / [`sign_and_notarize.sh`](file://sign_and_notarize.sh) — macOS App Bundle 打包、Hardened Runtime 簽名與 Apple `notarytool` 公證腳本。
