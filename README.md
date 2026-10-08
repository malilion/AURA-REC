# 🎥 LiteScreenRecorder (macOS 輕量桌面螢幕錄製工具)

專為 macOS 打造的高效能、極簡輕量桌面螢幕錄製工具。採用 Python 原生 GUI 與 FFmpeg 原生 Apple Silicon 硬體加速編碼 (`VideoToolbox`)，無額外龐大依賴（無需肥大的 Electron），啟動秒開、錄製極其流暢！

---

## ✨ 核心特色

1. **⚡ Apple Silicon 晶片硬體加速**
   - 預設啟用 `h264_videotoolbox` 硬體編碼，錄製 1080p/4K 幾乎不佔用 CPU，安靜不發熱、省電長續航。
2. **💊 懸浮膠囊模式 (Mini Floating Pill)**
   - 點擊錄影後可自動收合為小巧置頂懸浮條（`● REC 00:01:23 [⏹ 停止]`），不遮擋畫面內容，且可任意拖曳到螢幕角落。
   - 停止錄製時自動恢復面板並提示儲存路徑。
3. **✂️ 內建即時影片剪輯與後製 (Video Trimmer & Editor)**
   - **錄完立即剪輯**：錄製完成自動引導進入剪輯視窗，亦可在主介面點擊「✂️ 剪輯影片」隨時挑選歷史影片。
   - **影格即時預覽**：拉動時間軸即時顯示畫面縮圖，支援 `±0.1s` / `±1s` 精確微調與區段播放。
   - **起點/終點靈活裁切**：一鍵設置起點與終點，即時計算選取長度。
   - **⚡ 無損極速剪裁**：無需重新編碼，0.5 秒瞬間完成，畫質 100% 原始無損！
   - **🎯 精準幀剪輯**：精確至單幀裁切，並支援「🔇 一鍵去除聲音 (靜音剪輯)」。
   - **🎞️ 匯出為 GIF 動畫**：內建雙遍高畫質調色盤演算法，完美轉出流暢 GIF，適合分享至 GitHub、Slack、Notion。
   - **🎵 提取純音訊**：一鍵將影片中的語音單獨提取為 MP3 / M4A 聲音檔。
4. **🎙️ 音訊靈活錄製**
   - **麥克風收音**：錄製語音解說、會議發言。
   - **系統音效錄製**：支援錄製電腦內部播放的聲音（如 YouTube、音樂、會議聲，支援 Microsoft Teams Audio 或 BlackHole 虛擬聲卡）。
   - **靜音模式**：純畫面錄影。
4. **📐 多檔位解析度與幀率 (FPS)**
   - **解析度**：Retina 原生解析度 (免縮放最高清)、2K (2560x1440)、1080p FHD、720p HD。
   - **幀率**：30 FPS (平衡推薦)、60 FPS (高流暢動態)、15 FPS (極度省空間)。
5. **⏱️ 3 秒倒數準備與系統音效回饋**
   - 倒數 3、2、1 提示音，讓您從容切換到想錄製的視窗。
6. **⌨️ 便捷快捷鍵**
   - 按 `Space`（空白鍵）、`F9` 或 `Cmd + R` 即可立即開始或停止錄製。
7. **📁 智慧管理**
   - 一鍵「開啟資料夾 (Reveal in Finder)」。
   - 一鍵「播放最新影片 (QuickTime)」。
   - 支援自由變更儲存目錄。

---

## 🚀 啟動方式

您可以透過以下任意一種方式啟動：

### 方法 1：在 Finder 中滑鼠雙擊（最方便）
直接雙擊專案目錄下的 **`ScreenRecorder.command`** 即可啟動！

### 方法 2：終端機腳本
```bash
./run.sh
```

### 方法 3：Python 指令
```bash
python3 app.py
```

---

## 🎧 如何錄製電腦內部聲音（系統音效）？

macOS 基於隱私與安全機制，預設不允許直接抓取揚聲器輸出聲，需要透過虛擬音訊驅動：

1. **若您已安裝 Microsoft Teams**：
   - 本工具已自動偵測到系統中的 `Microsoft Teams Audio`，直接在下拉選單選擇該設備即可。
2. **若想使用開源標準虛擬音效驅動 (BlackHole)**：
   - 終端機執行安裝：
     ```bash
     brew install blackhole-2ch
     ```
   - 打開 macOS 內建的 **「音訊 MIDI 設定」** (Audio MIDI Setup) 應用程式。
   - 點擊左下角 `+`，選擇 **「建立多重輸出裝置」** (Multi-Output Device)。
   - 同時勾選您的「耳機/Mac 揚聲器」以及「BlackHole 2ch」。
   - 在 Mac 頂部選單將聲音輸出切換到該「多重輸出裝置」（這樣您聽得到聲音，聲卡同時也會送音訊給 BlackHole）。
   - 在本錄影工具中音訊來源選擇 `BlackHole 2ch` 即可完美同步錄製！

---

## 🔒 macOS 隱私權限說明

首次執行錄影時，macOS 系統可能會彈出權限確認對話框：
- **螢幕錄製權限**：至「系統設定」>「隱私權與安全性」>「螢幕錄製」，確保終端機 (Terminal) 或 Python 處於允許狀態。
- **麥克風權限**：若錄製麥克風，首次會提示允許使用麥克風。

---

## 📂 專案檔案結構

- [`app.py`](file://app.py) - 現代深色系 Tkinter GUI 介面、懸浮膠囊視窗、快捷鍵與事件調度。
- [`editor_window.py`](file://editor_window.py) - 影片剪輯視窗，支援即時影格預覽、時間軸精準滑桿、起終點標記與多種匯出。
- [`video_editor.py`](file://video_editor.py) - 剪輯後製引擎（無損極速裁剪、精準重編碼、GIF 雙遍調色盤、音訊分離）。
- [`recorder.py`](file://recorder.py) - 錄影核心引擎，基於 FFmpeg + AVFoundation + VideoToolbox 硬體加速。
- [`ScreenRecorder.command`](file://ScreenRecorder.command) - macOS Finder 雙擊即開執行檔。
- [`run.sh`](file://run.sh) - Shell 啟動腳本。
- `recordings/` - 錄影成品預設儲存目錄。
