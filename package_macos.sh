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

echo "[2/6] FFmpeg 不隨附 (GPL 授權)，請使用者自行安裝 (brew install ffmpeg)..."
rm -rf "$RESOURCES_DIR/bin"

# --- 內嵌 Python：用 PyInstaller 產生自帶 Python 與 Tk 的獨立 .app（預設）---
# 設 AURA_PACKAGE_MODE=launcher 則沿用需要使用者自備 Python 的輕量啟動器版 .app。
PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ "${AURA_PACKAGE_MODE:-bundle}" = "bundle" ]; then
    echo "[2b/6] 以 PyInstaller 內嵌 Python 與 Tk（$PYTHON_BIN）..."
    "$PYTHON_BIN" - <<'PYCHECK'
import sys, tkinter
assert tkinter.TkVersion >= 8.6, f"需要 Tk 8.6+，目前為 {tkinter.TkVersion}（請改用 python.org 或 conda 的 Python，並以 PYTHON_BIN 指定）"
PYCHECK
    "$PYTHON_BIN" -m pip install --quiet pyinstaller pyobjc-framework-Cocoa
    BUNDLE_DIR="$DIST_DIR/bundle"
    rm -rf "$BUNDLE_DIR" "$DIST_DIR/pyi-work"
    "$PYTHON_BIN" -m PyInstaller --noconfirm --windowed --name "AURA REC" \
        --icon "$SCRIPT_DIR/$APP_BUNDLE/Contents/Resources/icon.icns" \
        --osx-bundle-identifier com.aura.rec \
        --add-data "$SCRIPT_DIR/fonts:fonts" \
        --add-data "$SCRIPT_DIR/web_studio/download/AURA-REC.html:." \
        --add-data "$SCRIPT_DIR/README.md:." \
        --distpath "$BUNDLE_DIR" --workpath "$DIST_DIR/pyi-work" --specpath "$DIST_DIR/pyi-work" \
        app.py
    # 把隱私權限說明等鍵值合併進 PyInstaller 產生的 Info.plist
    "$PYTHON_BIN" - "$SCRIPT_DIR/$APP_BUNDLE/Contents/Info.plist" "$BUNDLE_DIR/AURA REC.app/Contents/Info.plist" <<'PYPLIST'
import plistlib, re, sys
src = plistlib.load(open(sys.argv[1], "rb"))
dst = plistlib.load(open(sys.argv[2], "rb"))
for k, v in src.items():
    if k.startswith("NS") or k in ("LSMinimumSystemVersion", "LSApplicationCategoryType", "ITSAppUsesNonExemptEncryption"):
        dst[k] = v
ver = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', open("platform_utils.py", encoding="utf8").read()).group(1)
dst["CFBundleShortVersionString"] = dst["CFBundleVersion"] = ver
plistlib.dump(dst, open(sys.argv[2], "wb"))
PYPLIST
    APP_BUNDLE="$BUNDLE_DIR/AURA REC.app"
fi

echo "[3/6] 清除 macOS 擴展屬性與快取..."
find "$APP_BUNDLE" -name ".DS_Store" -delete 2>/dev/null || true
find "$APP_BUNDLE" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
xattr -cr "$APP_BUNDLE" 2>/dev/null || true

echo "[4/6] 執行程式碼簽名 (Code Signing & Hardened Runtime)..."
if [ -x "./sign_and_notarize.sh" ]; then
    APP_BUNDLE="$APP_BUNDLE" ./sign_and_notarize.sh --sign-only
else
    echo "      (提示: 找不到 sign_and_notarize.sh，跳過簽名)"
fi

echo "[5/6] 產生 ZIP 封裝包..."
ZIP_NAME="AURA-REC-macOS.zip"
rm -f "$DIST_DIR/$ZIP_NAME"
COPYFILE_DISABLE=1 ditto -c -k --norsrc --keepParent "$APP_BUNDLE" "$DIST_DIR/$ZIP_NAME"
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


echo "=================================================="
echo "   打包完成！產出檔案如下："
echo "=================================================="
ls -lh "$DIST_DIR"/*.zip "$DIST_DIR"/*.dmg 2>/dev/null || ls -lh "$DIST_DIR"/*.zip
echo "=================================================="
