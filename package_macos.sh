#!/bin/bash
# ==============================================================================
#   AURA REC - macOS 一鍵打包腳本 (Package .app & .dmg & .zip)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "   AURA REC - macOS 桌面應用一鍵打包"
echo "=================================================="

APP_BUNDLE="AURA REC.app"
RESOURCES_DIR="$APP_BUNDLE/Contents/Resources"
MACOS_DIR="$APP_BUNDLE/Contents/MacOS"
DIST_DIR="$SCRIPT_DIR/dist"

mkdir -p "$DIST_DIR"
mkdir -p "$RESOURCES_DIR"
mkdir -p "$MACOS_DIR"

echo "[1/6] 同步最新原始碼與資源至 App Bundle..."
# 拷貝核心 Python 程式碼
cp -f app.py "$RESOURCES_DIR/"
cp -f recorder.py "$RESOURCES_DIR/"
cp -f platform_utils.py "$RESOURCES_DIR/"
cp -f region_picker.py "$RESOURCES_DIR/"
cp -f editor_window.py "$RESOURCES_DIR/"
cp -f video_editor.py "$RESOURCES_DIR/"
cp -f aura_widgets.py "$RESOURCES_DIR/"
cp -f input_overlay.py "$RESOURCES_DIR/"
cp -f auto_updater.py "$RESOURCES_DIR/"
cp -f screen_annotation.py "$RESOURCES_DIR/"
cp -f speech_to_text.py "$RESOURCES_DIR/"
cp -f window_exclusion_watermark.py "$RESOURCES_DIR/"
cp -f i18n.py "$RESOURCES_DIR/"
[ -f README.md ] && cp -f README.md "$RESOURCES_DIR/"

# 拷貝字型目錄
if [ -d "fonts" ]; then
    rm -rf "$RESOURCES_DIR/fonts"
    cp -R fonts "$RESOURCES_DIR/"
fi

# 拷貝 Web 工作站檔案（若存在）
if [ -f "web_studio/download/AURA-REC.html" ]; then
    cp -f "web_studio/download/AURA-REC.html" "$RESOURCES_DIR/"
fi

# 確保啟動器具備執行權限
chmod +x "$MACOS_DIR/AURARec"

echo "[2/6] 檢查 FFmpeg 工具支援..."
mkdir -p "$RESOURCES_DIR/bin"
# 若本機已有 ffmpeg，可拷貝或建立連結至 bundle 內供隨身使用
FFMPEG_SYS="$(command -v ffmpeg || true)"
[ -z "$FFMPEG_SYS" ] && [ -x "/opt/homebrew/bin/ffmpeg" ] && FFMPEG_SYS="/opt/homebrew/bin/ffmpeg"
[ -z "$FFMPEG_SYS" ] && [ -x "/usr/local/bin/ffmpeg" ] && FFMPEG_SYS="/usr/local/bin/ffmpeg"

if [ -n "$FFMPEG_SYS" ] && [ -x "$FFMPEG_SYS" ]; then
    echo "      找到本機 FFmpeg: $FFMPEG_SYS"
    # 若 Resources/bin/ffmpeg 尚未存在，複製一份進入 bundle 以確保可攜性
    if [ ! -f "$RESOURCES_DIR/bin/ffmpeg" ]; then
        cp -p "$FFMPEG_SYS" "$RESOURCES_DIR/bin/ffmpeg" 2>/dev/null || true
    fi
    chmod +x "$RESOURCES_DIR/bin/ffmpeg" 2>/dev/null || true
fi

echo "[3/6] 清除 macOS 擴展屬性與快取..."
find "$APP_BUNDLE" -name ".DS_Store" -delete 2>/dev/null || true
find "$APP_BUNDLE" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
xattr -cr "$APP_BUNDLE" 2>/dev/null || true

echo "[4/6] 執行程式碼簽名 (Code Signing & Hardened Runtime)..."
if [ -x "./sign_and_notarize.sh" ]; then
    ./sign_and_notarize.sh --sign-only
else
    echo "      (提示: 找不到 sign_and_notarize.sh，跳過簽名)"
fi

echo "[5/6] 產生 ZIP 封裝包..."
ZIP_NAME="AURA-REC-macOS.zip"
rm -f "$DIST_DIR/$ZIP_NAME"
ditto -c -k --sequesterRsrc --keepParent "$APP_BUNDLE" "$DIST_DIR/$ZIP_NAME"
echo "      已輸出: $DIST_DIR/$ZIP_NAME"

echo "[6/6] 製作 DMG 安裝映象檔 (含 Applications 捷徑)..."
DMG_NAME="AURA-REC-macOS.dmg"
DMG_STAGING="$DIST_DIR/dmg_staging"
rm -rf "$DMG_STAGING" "$DIST_DIR/$DMG_NAME"
mkdir -p "$DMG_STAGING"

# 拷貝 App 與建立 Applications 替身
cp -R "$APP_BUNDLE" "$DMG_STAGING/"
ln -s /Applications "$DMG_STAGING/Applications"

# 寫入簡單指引
cat << 'EOF' > "$DMG_STAGING/安裝說明.txt"
歡迎使用 AURA REC 桌面錄影工作站！

【安裝方法】
1. 將「AURA REC.app」拖曳至右側的「Applications」資料夾。
2. 開啟 Launchpad 或「應用程式」，點擊「AURA REC」即可開始錄影。

【首次開啟注意事項】
若 macOS 提示「無法驗證開發者」：
請在 AURA REC 上按滑鼠右鍵（或按住 Control 鍵點擊），選擇「開啟」，接著在彈出提示中點選「開啟」即可。
EOF

# 使用 macOS 內建 hdiutil 製作 DMG（若在沙盒或受限環境會自動略過）
if hdiutil create -volname "AURA REC" -srcfolder "$DMG_STAGING" -ov -format UDZO "$DIST_DIR/$DMG_NAME" 2>/dev/null; then
    echo "      已輸出: $DIST_DIR/$DMG_NAME"
else
    echo "      (提示: 目前環境下 hdiutil 受安全沙盒限制，於一般終端機或 CI 執行時可正常產出 DMG；已優先生成通用 ZIP 包)"
fi

rm -rf "$DMG_STAGING"

if [ -d "web_studio/download" ]; then
    cp -f "$DIST_DIR/$ZIP_NAME" "web_studio/download/$ZIP_NAME"
    echo "      已同步至官網下載區: web_studio/download/$ZIP_NAME"
fi

echo "=================================================="
echo "   打包完成！產出檔案如下："
echo "=================================================="
ls -lh "$DIST_DIR"/*.zip "$DIST_DIR"/*.dmg 2>/dev/null || ls -lh "$DIST_DIR"/*.zip
echo "=================================================="
