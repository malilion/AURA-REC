# AURA REC

跨平台螢幕錄製與剪輯。對外是兩件分開的東西：

- **官網** `web_studio/index.html`：只做介紹。下載按鈕只會給出下面那一個檔案。
- **那一個檔案** `web_studio/download/AURA-REC.html`：雙擊就用瀏覽器打開工作站。Mac 與 Windows 都是這同一個檔。

桌面原生程式（`AURA REC.app`、Windows 的 `AURA-REC.exe`）是另外一套。它需要 Python 3 與 FFmpeg，不在官網的下載裡。

---

## 給別人用

1. 用瀏覽器打開官網 `web_studio/index.html`。
2. 按下載。只會得到 `AURA-REC.html`。
3. 雙擊那個檔案。請用 Chrome 或 Edge，並允許螢幕分享。

不用解壓縮，也不用安裝 Python。第一次開啟需要網路，用來載入字型與介面。

本機可以直接雙擊：

- macOS：`open_studio.command`
- Windows：`open_studio.bat`

工作站可以做這些事：

- 瀏覽器裡錄螢幕，支援畫筆、矩形、聚光燈、畫幅導引與按鍵投影。
- 原色、賽博、黑白、暖調濾鏡，以及 0.5x 到 2x 播放。
- 可拖曳的視訊鏡頭，與隨畫面變色的環境光。
- 影像軌與音訊波形兩條時間軸，可裁一段再匯出。

---

## 桌面原生程式

要系統音訊、硬體編碼與離線剪輯時用這一支。

### macOS

- 雙擊 `AURA REC.app`。可拖到「應用程式」或 Dock。
- 首次若出現「無法驗證開發者」：在 `AURA REC.app` 上按右鍵，選「開啟」，再按一次「開啟」。
- 或雙擊 `ScreenRecorder.command`，或在終端機執行 `./run.sh`。

### Windows

- 雙擊 `build_windows_exe.bat`，產生 `dist\AURA-REC.exe`。之後雙擊那個 exe。
- 或雙擊 `ScreenRecorder.bat`。

桌面程式可以做這些事：

- 最近錄影列表：改名、播放、剪輯、在資料夾中顯示、刪除。
- 懸浮膠囊。開始錄影後收成小條。錄影中按「展開」或 `Esc` 回到主畫面，也可以再收成小條。停止後回到主面板。
- 3 秒倒數。倒數時再按一次或按 `Esc` 可以取消。空白鍵、`F9`、`Cmd + R`（macOS）或 `Ctrl + R`（Windows）開始或停止。錄影中按 `F8` 暫停或繼續，暫停的時間不計入長度。錄影時不會讓電腦睡著。
- 可關掉「錄下游標」。可改畫質、存成 MP4 或 MOV，也能設 1 到 60 分鐘後自動停止。標準畫質把檔案壓小，1080p 大約一小時 400 MB。要更清楚再選較清晰。準備錄影時會顯示大約每分鐘多大，以及以這個畫質還能錄多久。長錄影可以每 5、10 或 30 分鐘存成一個檔，預設不分段。視窗位置會記住。
- 按 `F7` 截圖，存進同一個資料夾。有自訂範圍時只截那一塊。錄影時會顯示檔案大小。磁碟剩下不到 500 MB 會先詢問。
- 範圍可以拖曳選取，只錄現在這個螢幕的一塊。解析度、幀率、裝置和這些選項會記住。
- 最近的檔案可以改名、雙擊播放、剪輯、在資料夾裡顯示或刪除，清單可以捲動。剪輯匯出的 GIF、音訊和截圖若在同一個資料夾，也會列出來。
- 解析度：原生、2K、1080p、720p，以長邊對齊並保留畫面比例。直向的自訂範圍不會被拉寬。幀率：15、30、60。一般文書電腦會自動用較輕的畫質：8GB 或 4 核心以下是 720p / 15 FPS，編碼也限制只用一部分 CPU，避免拖慢 Word 這類程式。原生解析度和 60 FPS 仍可手動選。
- 剪輯：時間軸預覽、起點與終點、無損裁切、靜音、GIF、抽出音訊。橫向影片可轉成直式 9:16，整段畫面留在中間，上下用模糊背景補滿。也可以改成只裁左、中或右。有改比例、速度、色彩或靜音時會重新編碼。
- macOS 用 AVFoundation 與 VideoToolbox。Windows 用 GDI，並可走 NVENC、QSV 或 AMF。

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

這是桌面程式的音訊來源，不是瀏覽器那個檔案。

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
- `AURA REC.app` — macOS 桌面程式。裡面的「Web 工作站」按鈕開的是 `AURA-REC.html`，不是官網。
- `build_windows_exe.bat` — 在 Windows 上編成 `dist\AURA-REC.exe`。編譯時只帶入 `AURA-REC.html`。
- `AURA-REC.ico` — Windows 圖示。
- `app.py` — 桌面程式主介面。
- `platform_utils.py` — 系統判斷、字型、High-DPI、音效、開啟檔案、GPU 編碼器。
- `recorder.py` — 錄影。
- `editor_window.py` — 桌面剪輯視窗。
- `video_editor.py` — 裁切、GIF、音訊分離。
- `ScreenRecorder.command` / `ScreenRecorder.bat` / `run.sh` — 啟動桌面程式。
- `recordings/` — 從專案直接執行時的預設儲存目錄。用 `AURA REC.app` 開啟時改存到「影片 / AURA REC」，避免寫進應用程式裡面。改過的路徑會記住。
