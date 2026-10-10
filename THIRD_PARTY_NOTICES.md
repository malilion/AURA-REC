# 第三方元件與授權

AURA REC 本身以 [MIT](LICENSE) 授權。下列元件隨 macOS 發行包一併提供。

## FFmpeg（macOS 與 Windows 發行包內附）

macOS 版 `AURA REC.app`、Windows 版安裝程式與免安裝 zip 都內附 `ffmpeg` 與 `ffprobe` 兩個**獨立的命令列執行檔**，AURA REC 以子程序方式呼叫它們（並非連結成同一個程式）。

- 版本：FFmpeg 7.1.1。macOS 版由 [`tools/build_ffmpeg_macos.sh`](tools/build_ffmpeg_macos.sh) 於 Apple Silicon 上編譯；Windows 版由 [`tools/build_ffmpeg_windows.sh`](tools/build_ffmpeg_windows.sh) 以 mingw-w64 交叉編譯（x64）。皆靜態連結下列函式庫。
- 授權：因啟用 **libx264**，整個 `ffmpeg` / `ffprobe` 執行檔以 **GNU GPL v2 或更新版本** 散布（另啟用 `--enable-version3`）。授權全文見 App 內的 `FFMPEG-COPYING.GPLv2`，或 <https://www.gnu.org/licenses/old-licenses/gpl-2.0.html>。
- 內含函式庫：
  - [FFmpeg](https://ffmpeg.org/) — LGPL/GPL
  - [x264](https://www.videolan.org/developers/x264.html)（commit `b35605ace3dd`）— GPL v2+
  - [LAME](https://lame.sourceforge.io/) 3.100 — LGPL
  - zlib 1.3.1 — zlib 授權
  - macOS：Apple VideoToolbox / AudioToolbox / AVFoundation（系統框架，動態連結）
  - Windows：[nv-codec-headers](https://github.com/FFmpeg/nv-codec-headers) n12.2.72.0（MIT，NVENC）、[AMF](https://github.com/GPUOpen-LibrariesAndSDKs/AMF) v1.4.35（MIT，AMD）、[libvpl](https://github.com/intel/libvpl) v2.15.0（MIT，Intel QSV）

### 對應原始碼（Corresponding Source）

每個 [GitHub Release](https://github.com/malilion/Record/releases) 都附有 `AURA-REC-ffmpeg-source.tar.gz`（macOS）與 `AURA-REC-ffmpeg-win-source.tar.gz`（Windows），內含編譯這些執行檔所用的 FFmpeg、x264、LAME、zlib 等原始碼與建置腳本。你也可以自行從上游取得：

- FFmpeg 7.1.1：<https://ffmpeg.org/releases/ffmpeg-7.1.1.tar.xz>
- x264：<https://code.videolan.org/videolan/x264>（commit `b35605ace3ddf7c1a5d67a2eb553f034aef41d55`）
- LAME 3.100：<https://sourceforge.net/projects/lame/files/lame/3.100/>
- 建置方式：[`tools/build_ffmpeg_macos.sh`](tools/build_ffmpeg_macos.sh)、[`tools/build_ffmpeg_windows.sh`](tools/build_ffmpeg_windows.sh)

如需其他形式的原始碼，請在 <https://github.com/malilion/Record/issues> 提出，我們會在發行日起三年內提供。

你可以自行替換隨附的 FFmpeg：自行重新編譯後取代 App 資料夾內的 `ffmpeg` / `ffprobe`（Windows 為 `ffmpeg.exe` / `ffprobe.exe`）。

## 其他

- 內嵌字型 Inter、JetBrains Mono、Syne：SIL Open Font License 1.1（見 `fonts/OFL.txt`）。
- 網頁版內嵌 [Lucide](https://lucide.dev/)（ISC）、[mp4-muxer](https://github.com/Vanilagy/mp4-muxer)（MIT）、[Tailwind CSS](https://tailwindcss.com/)（MIT）。
- 桌面版以 [PyInstaller](https://pyinstaller.org/) 打包 Python（PSF）、Tk（BSD 類）與 PyObjC（MIT）。
