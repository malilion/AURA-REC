# AURA REC

真正把畫面與聲音留下來的原生桌面錄影工作站。

- **桌面應用程式（主要推薦）**：支援 macOS（`AURA REC.app` / DMG / ZIP）與 Windows（`AURA-REC.exe` / ZIP）。晶片級硬體加速（Apple Silicon VideoToolbox / NVIDIA NVENC）、電腦系統聲音內錄、動態視窗追蹤、全域快捷鍵（F8/F9/F7）、錄影避讓收合與離線無損剪輯。
- **瀏覽器工作站（免安裝體驗版）**：輕量單一檔案 `AURA-REC.html`。官網在 [malilion.github.io/Record](https://malilion.github.io/Record/)，可直接在線上或離線雙擊開啟作為快速預覽與時間軸標記工具。

---

## 為什麼選擇桌面版？

1. **晶片級硬體加速**：Apple Silicon (M1~M4) 與 NVIDIA / Intel / AMD 原生編碼，4K 60FPS 錄製依然流暢不發燙，告別瀏覽器轉碼掉幀與 CPU 飆高。
2. **真正的系統聲音內錄**：徹底突破 macOS 瀏覽器無法擷取電腦聲音的限制，支援系統音效與麥克風雙軌混音。
3. **動態視窗追蹤與避讓**：錄製單一視窗時，視窗拖移會即時自動追蹤裁切位置；全螢幕錄影時控制條智慧避讓隱藏。
4. **全域快捷鍵**：F8 暫停/繼續（暫停時間不計入總長）、F9 停止、F7 快速截圖。
5. **串流直出 MP4 / MOV**：直接即時寫入硬碟，長錄影不爆記憶體，具備睡眠防護與斷電安全保護。

---

## 瀏覽器工作站

### 做得到什麼

- 錄整個螢幕、一個視窗，或一個分頁。選哪一塊，由瀏覽器的分享視窗決定。
- 分享時可勾選系統聲音。底部的「麥克風收音」是另外一路，可以和畫面聲音混在一起。
- 按下後先倒數 3 秒。空白鍵可以開始或停止。
- 預覽上可以畫筆、矩形、聚光燈，顏色可換。畫幅導引有 16:9、9:16、1:1。按鍵會浮在畫面上。
- 圓形鏡頭可以拖位置。舞台周圍的光會跟著畫面的顏色走。
- 濾鏡：原色、賽博、黑白、暖調。播放速度 0.5x、1x、1.5x、2x。
- 時間軸有影像條和聲音條。拖綠色起點、紅色終點，播放會在這一段循環。I 標記起點，O 標記終點，J / L 前後一秒，M 靜音，F 全螢幕。
- 「匯出選取片段」只存時間軸起點到終點那一段 WebM。起點和終點就是整段時，直接存原來的檔。「導出精華截圖」把目前這一格連同畫筆存成 PNG。
- 也可以按「匯入既有影片剪輯」，拿一支現成影片來預覽。

瀏覽器會盡量要較高的解析度與 60 FPS。實際大小跟著你選的那塊畫面，不保證每一台都是 4K。

畫筆、鏡頭和濾鏡是預覽上的看法。畫筆會進 PNG 截圖。存成 WebM 的是這次錄到的整段畫面與聲音。

### 怎麼用

1. 打開 [官網](https://malilion.github.io/Record/)，按下載。只會得到 `AURA-REC.html`。
2. 雙擊那個檔。請用 Chrome、Edge 或 Brave，並允許螢幕分享。
3. 按「開始選取並錄製」。要電腦裡的聲音，在分享視窗勾選。要自己的聲音，打開底部的麥克風。
4. 倒數結束後開始。再按空白鍵，或按懸浮條上的「停止錄製」。
5. 用時間軸看。要指出某一格，用左上角的畫筆。要換看法，用右上角的濾鏡和倍速。
6. 在時間軸標好起點和終點，按「匯出選取片段」把這一段存成 WebM。要圖就按「導出精華截圖」。

第一次開啟需要網路，用來載入字型與介面。本機也可以直接雙擊 `open_studio.command`（macOS）或 `open_studio.bat`（Windows），開的是同一個工作站。

---

## 桌面程式

要比較長的錄影、指定一個視窗、硬體編碼，或把影片裁短、轉成直式、做成 GIF 時，用這一支。

### 做得到什麼

- 錄整個螢幕、拖一塊範圍，或錄畫面上的某一個視窗。視窗錄的是按下開始時那個視窗的位置，檔名會帶上那個程式的名稱。
- 解析度有原生、2K、1080p、720p，以長邊對齊並保留比例。直向的範圍不會被拉成橫的。幀率 15、30、60。
- 一般文書電腦會自動用較輕的畫質：8GB 或 4 核心以下是 720p / 15 FPS，並少用一些 CPU。其他電腦預設 1080p / 30 FPS。原生解析度和 60 FPS 仍可自己選。硬體加速預設打開。
- 畫質分較省、標準、較清晰。標準畫質把檔案壓小，1080p 大約一小時 400 MB。準備錄影時會顯示大約每分鐘多大，以及以這個畫質還能錄多久。
- 存成 MP4 或 MOV。可以設 1 到 60 分鐘後自動停止。長錄影可以每 5、10 或 30 分鐘各自存成一個檔，預設不分段。
- 可關掉「錄下游標」。錄影時顯示檔案大小。磁碟剩下不到 500 MB 會先問。錄影時不讓電腦睡著。
- 3 秒倒數。倒數時再按一次或按 `Esc` 可以取消。
- 錄影中可收成小條。若是在錄一個視窗，小條會先移到不擋住那個視窗的角落。`Esc` 或「展開」回到主畫面。
- `F8` 暫停或繼續。暫停的時間不計入長度，分段也不會在暫停時換檔。
- `F7` 截圖，和錄影放在同一個資料夾。有自訂範圍時只截那一塊。
- 最近的檔案可以改名、雙擊播放、剪輯、在資料夾裡顯示或刪除。影片和聲音會顯示長度。剪輯匯出的 GIF、音訊和截圖若在同一個資料夾，也會列出來。
- 「複製最新檔案」把最新一個已完成的檔放到剪貼簿，可以貼到 Finder 或其他資料夾。正在寫入的那一個不會被複製。
- 剪輯：時間軸預覽、起點與終點、無損裁切、智慧自動縮放跟隨運鏡（Auto Zoom 支援平滑推進與退回、平滑推進特寫、全程特寫，畫布即時點擊/拖曳設定焦點與發光十字準星、智慧動態偵測）、靜音、GIF、抽出音訊。橫向影片可放進直式 9:16，整段留在中間，上下用模糊背景補滿；也可以改成只裁左、中或右。有改比例、速度、色彩或靜音時會重新編碼。
- 膠卷時間軸即時滑鼠刷屏 (Scrubbing / Skimming) 與拖曳 In/Out 握把：全新畫布級故事板膠卷（Filmstrip Timeline），滑鼠左右懸浮滑動時即時刷屏（Skimming），黃色微光指針隨游標移動並浮現精確時間戳膠囊，中央預覽區 0ms 快取即時渲染對應影格；膠卷兩側配置翠綠色 In 起點握把 `[` 與珊瑚紅 Out 終點握把 `]`，游標移上自動切換雙向調整箭頭，支援直觀拖曳調整剪輯區間，即時連動輸入框、選取長度與高亮發光遮罩，媲美 Final Cut Pro / Premiere 流暢剪輯體驗。
- 極速精準智慧無損裁切 (Smart Cut)：突破傳統 `-c copy` 只能在關鍵影格（I-Frame）起切導致首尾黑畫面或卡幀卡頓的痛點。透過快速封包分析關鍵影格分佈，實現「首尾非關鍵影格毫秒級精準微編碼、主體骨幹全段 100% 原始位元無損串流複製」的智慧拼接架構（Smart Render）。毫秒級精準剪裁不差一格，同時維持 0.5 秒瞬間直出；若遇單一 GOP 極短片段則自動以高速無損微編碼，兼具極限速度與零失真畫質。
- 畫中畫（PiP）人臉鏡頭覆蓋：可勾選開啟 PiP 人臉鏡頭，支援圓形相機（含極光霓虹藍或純白光暈邊框）與圓角矩形，可自訂擺放於四個角落（右下/左下/右上/左上）與尺寸（小 200px / 中 260px / 大 340px）。錄影期間可在桌面顯示即時浮動小圓圈（可自由拖曳挪開），並提供「鏡頭試看 👁」功能。
- 滑鼠點擊發光波紋與按鍵顯示：錄製時在滑鼠點擊處產生發光水波紋漣漪（Click Ripple，左鍵極光藍、右鍵活力珊瑚紅，~260ms 平滑外擴漸隱），並於畫面底部浮現時尚圓角深色半透明按鍵藥丸條（Keystroke HUD，支援 macOS ⌘/⌥/⌃/⇧ 快捷鍵與連續打字顯示，停留 1.4 秒後優雅隱藏）。教學錄影與展示一目了然，零外部套件依賴。
- 軟體內建自動檢查更新 (Auto Updater)：主選單「說明」與「檔案」內建「檢查更新…」，並支援啟動時非同步靜默檢查。串接 GitHub Releases API 自動比對語意化版本號（Semantic Versioning），若有新版發布即彈出質感更新對話框，展示 Changelog 更新亮點並提供一鍵前往下載。
- 解析度、幀率、裝置、範圍、視窗和視窗位置會記住。
- macOS 用 AVFoundation 與 VideoToolbox。Windows 用 GDI，並可走 NVENC、QSV 或 AMF。

### 怎麼打開

macOS：

- 雙擊 `AURA REC.app`。可拖到「應用程式」或 Dock。
- 首次若出現「無法驗證開發者」：在 `AURA REC.app` 上按右鍵，選「開啟」，再按一次「開啟」（或參閱下方「Apple 程式碼簽名與公證」發行正式版本）。
- 或雙擊 `ScreenRecorder.command`，或在終端機執行 `./run.sh`。

#### macOS 程式碼簽名與 Apple 官方公證 (Notarization)

專案內建一鍵自動化腳本 [`sign_and_notarize.sh`](file://sign_and_notarize.sh) 與 [`entitlements.plist`](file://entitlements.plist)，支援 Hardened Runtime 與 Apple 官方 `notarytool` 公證：

1. **檢查本機簽名證書與工具**：
   ```bash
   ./sign_and_notarize.sh --check
   ```
2. **本機打包與 Ad-hoc 簽名**（預設）：
   ```bash
   ./package_macos.sh
   ```
3. **官方發行：Apple Developer ID 簽名與公證**：
   ```bash
   # 步驟 A：設定一次性公證密鑰至 macOS 鑰匙圈
   xcrun notarytool store-credentials "notary-profile" \
     --apple-id "your-apple-id@example.com" \
     --team-id "TEAMID1234" \
     --password "xxxx-xxxx-xxxx-xxxx"   # Apple App-Specific Password

   # 步驟 B：一鍵完成深度簽名、送審公證與票證裝釘 (Staple)
   ./sign_and_notarize.sh --keychain-profile "notary-profile"
   ```
   公證完成後，系統會自動在 `AURA REC.app` 與 `dist/AURA-REC-macOS.dmg` 上裝釘（Staple）官方票證，任何使用者下載後雙擊即可直接通行，徹底告別 Gatekeeper 阻擋！

Windows：

- 雙擊 `build_windows_exe.bat`，產生 `dist\AURA-REC.exe`。之後雙擊那個 exe。
桌面程式功能選單支援「系統聲音錄製指南…」（內建 macOS BlackHole / Windows 立體聲混音快速設定）與「FFmpeg 與硬體加速檢視…」。

### 怎麼錄

1. 先裝好下面的 FFmpeg。
2. 打開程式。來源選螢幕。音訊可以選麥克風、系統音訊裝置，或選「無音訊」。
3. 範圍選「整個螢幕」、拖一塊，或選畫面上的一個視窗。視窗必須在目前這個螢幕上。
4. 選解析度、幀率、畫質、MP4 或 MOV。需要的話再設自動停止和分段。
5. 空白鍵、`F9`，或 `Cmd + R`（macOS）／`Ctrl + R`（Windows）開始。倒數時再按一次或 `Esc` 會取消。
6. 錄完再按一次停止。檔案出現在最近列表。雙擊檔名播放，或按「剪輯」。

捷徑：

| 動作 | 按鍵 |
| --- | --- |
| 開始或停止 | 空白鍵、`F9`、`Cmd + R` 或 `Ctrl + R` |
| 取消倒數 | 再按一次開始，或 `Esc` |
| 暫停或繼續 | `F8` |
| 截圖 | `F7` |
| 小條回到主畫面 | `Esc` |
| 複製最新檔案 | `Shift + Command + C`（Windows 為 `Shift + Ctrl + C`） |

檔案放哪裡：從專案直接執行時，預設在 `recordings/`。用 `AURA REC.app` 開啟時改存到「影片 / AURA REC」，避免寫進應用程式裡面。Windows 從程式開啟時在「影片 / AURA REC」。改過的路徑會記住。

### 怎麼剪

1. 在最近列表按「剪輯」，或從選單打開剪輯。
2. 在時間軸上設起點和終點。
3. 比例維持原樣，或改成直式 9:16 完整（整段放進直式畫布）。只要其中一塊時，選直式裁切的左、中或右。也可以 16:9 或 1:1。
4. 需要的話靜音、改速度、輸出 GIF，或只抽出音訊。
5. 選存檔位置後匯出。只裁時間、沒有改比例或聲音時，走無損裁切。

### 安裝 FFmpeg

只要桌面程式需要。瀏覽器那個檔案不用裝。

macOS：

```bash
brew install ffmpeg
```

Windows（PowerShell 或 CMD）：

```cmd
winget install Gyan.FFmpeg
```

或到 [gyan.dev/ffmpeg](https://www.gyan.dev/ffmpeg/builds/) 下載，把 `ffmpeg.exe` 放到專案資料夾。

### 錄電腦內部的聲音

這是桌面程式的音訊來源。瀏覽器工作站改由分享視窗裡的「分享音訊」處理。

Windows：

1. 右下角聲音圖示按右鍵，打開「聲音設定」，再進「更多音效設定」。
2. 切到「錄製」。在空白處按右鍵，勾選「顯示已停用的裝置」。
3. 對「立體聲混音 (Stereo Mix)」按右鍵，選「啟用」。
4. 回到桌面程式，音訊來源選 `Stereo Mix`。

macOS：

1. 若已安裝 Microsoft Teams，直接選 `Microsoft Teams Audio`。
2. 或安裝 BlackHole（`brew install blackhole-2ch`），在「音訊 MIDI 設定」建立多重輸出裝置。

---

## 檔案

- `web_studio/index.html` — 官網。
- `web_studio/download/AURA-REC.html` — 官網提供下載的那一個檔案。
- `open_studio.command` / `open_studio.bat` — 雙擊即開那個檔案。
- `AURA REC.app` — macOS 桌面程式。
- `build_windows_exe.bat` — 在 Windows 上編成 `dist\AURA-REC.exe`。編譯時只帶入 `AURA-REC.html`。
- `AURA-REC.ico` — Windows 圖示。
- `app.py` — 桌面程式主介面。
- `platform_utils.py` — 系統判斷、字型、High-DPI、音效、開啟檔案、GPU 編碼器。
- `recorder.py` — 錄影。
- `editor_window.py` — 桌面剪輯視窗。
- `video_editor.py` — 裁切、GIF、音訊分離、直式畫布。
- `region_picker.py` — 拖範圍、選視窗。
- `aura_widgets.py` — 桌面程式的按鈕與外觀。
- `ScreenRecorder.command` / `ScreenRecorder.bat` / `run.sh` — 啟動桌面程式。
