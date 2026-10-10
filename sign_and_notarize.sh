#!/bin/bash
# ==============================================================================
#   AURA REC - macOS 應用程式程式碼簽名與 Apple Notary 公證腳本
#   (Code Signing & Apple Notarization Automation)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_BUNDLE="${APP_BUNDLE:-AURA REC.app}"
DIST_DIR="$SCRIPT_DIR/dist"
ENTITLEMENTS="$SCRIPT_DIR/entitlements.plist"
DMG_PATH="$DIST_DIR/AURA-REC-macOS.dmg"
ZIP_PATH="$DIST_DIR/AURA-REC-macOS.zip"

# 參數預設值 (支援環境變數注入)
SIGN_IDENTITY="${DEVELOPER_ID:-}"
KEYCHAIN_PROFILE="${KEYCHAIN_PROFILE:-${NOTARY_PROFILE:-}}"
APPLE_ID="${APPLE_ID:-}"
APP_SPECIFIC_PWD="${APP_SPECIFIC_PASSWORD:-}"
TEAM_ID="${TEAM_ID:-}"
API_KEY_PATH="${API_KEY_PATH:-}"
API_KEY_ID="${API_KEY_ID:-}"
API_ISSUER_ID="${API_ISSUER_ID:-}"
SIGN_ONLY=false
CHECK_MODE=false

# ==============================================================================
# 輔助提示函式
# ==============================================================================
show_help() {
    cat << 'EOF'
使用方式: ./sign_and_notarize.sh [選項]

【主要功能】
  自動對 AURA REC.app 進行 Apple Hardened Runtime 深度程式碼簽名，
  並透過 Apple notarytool 服務進行官方公證 (Notarization) 與票證裝釘 (Staple)。
  完成後使用者雙擊即可直接執行，不再彈出 Gatekeeper「無法驗證開發者」警告。

【選項說明】
  -i, --identity <ID>         指定 Developer ID Application 簽名證書名稱或 SHA-1
                              (預設: 自動從系統鑰匙圈偵測有效證書)
  -p, --keychain-profile <名> 指定已存於鑰匙圈的 notarytool 憑證設定檔 (推薦)
      --apple-id <email>      Apple Developer 帳號 Email
      --password <pwd>        Apple 專用應用程式密碼 (App-Specific Password)
      --team-id <TeamID>      Apple 10 碼團隊識別碼 (Team ID)
      --api-key <path>        App Store Connect API Key (.p8 檔案路徑)
      --key-id <id>           API Key ID
      --issuer <uuid>         API Issuer UUID
  -s, --sign-only             僅執行程式碼簽名，不向 Apple 伺服器提交公證
  -c, --check                 檢查當前系統簽名工具、證書與公證環境
  -h, --help                  顯示此說明文件

【快速使用範例】
  1. 檢查本機憑證與工具：
     ./sign_and_notarize.sh --check

  2. 第一次設定公證憑證 (只需設定一次，金鑰安全儲存於 macOS 鑰匙圈)：
     xcrun notarytool store-credentials "notary-profile" \
       --apple-id "your-apple-id@example.com" \
       --team-id "TEAMID1234" \
       --password "xxxx-xxxx-xxxx-xxxx"

  3. 一鍵簽名、公證與裝釘：
     ./sign_and_notarize.sh --keychain-profile "notary-profile"

  4. 本地測試無正式證書時 (Ad-hoc 簽名測試)：
     ./sign_and_notarize.sh --sign-only
EOF
    exit 0
}

# ==============================================================================
# 解析命令行參數
# ==============================================================================
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_help
            ;;
        -i|--identity)
            SIGN_IDENTITY="$2"
            shift 2
            ;;
        -p|--keychain-profile)
            KEYCHAIN_PROFILE="$2"
            shift 2
            ;;
        --apple-id)
            APPLE_ID="$2"
            shift 2
            ;;
        --password)
            APP_SPECIFIC_PWD="$2"
            shift 2
            ;;
        --team-id)
            TEAM_ID="$2"
            shift 2
            ;;
        --api-key)
            API_KEY_PATH="$2"
            shift 2
            ;;
        --key-id)
            API_KEY_ID="$2"
            shift 2
            ;;
        --issuer)
            API_ISSUER_ID="$2"
            shift 2
            ;;
        -s|--sign-only)
            SIGN_ONLY=true
            shift
            ;;
        -c|--check)
            CHECK_MODE=true
            shift
            ;;
        *)
            echo "❌ 未知選項: $1 (輸入 ./sign_and_notarize.sh --help 查看使用說明)"
            exit 1
            ;;
    esac
done

echo "=================================================="
echo "   AURA REC - macOS 簽名與公證服務 (Notarization)"
echo "=================================================="

# ==============================================================================
# 檢查工具可用性
# ==============================================================================
if ! command -v codesign &>/dev/null; then
    echo "❌ 找不到 codesign 工具，請確保已安裝 macOS Command Line Tools (xcode-select --install)"
    exit 1
fi

if ! command -v xcrun &>/dev/null; then
    echo "❌ 找不到 xcrun 工具"
    exit 1
fi

# ==============================================================================
# 診斷與檢查模式 (--check)
# ==============================================================================
if [ "$CHECK_MODE" = true ]; then
    echo "🔍 正在檢查 macOS 簽名與公證環境..."
    echo "--------------------------------------------------"
    echo "▸ codesign: $(command -v codesign)"
    echo "▸ xcrun:    $(command -v xcrun)"
    if xcrun notarytool --version &>/dev/null; then
        echo "▸ notarytool: 已就緒 (版本: $(xcrun notarytool --version 2>&1 | head -n 1))"
    else
        echo "⚠️ notarytool: 未安裝或 Xcode 版本過舊"
    fi
    if command -v stapler &>/dev/null || xcrun stapler &>/dev/null; then
        echo "▸ stapler:    已就緒"
    else
        echo "⚠️ stapler:    未安裝"
    fi
    echo "--------------------------------------------------"
    echo "▸ 鑰匙圈中可用的程式碼簽名證書："
    security find-identity -p codesigning -v || true
    echo "--------------------------------------------------"
    exit 0
fi

# ==============================================================================
# 驗證目標檔案
# ==============================================================================
if [ ! -d "$APP_BUNDLE" ]; then
    echo "⚠️ 尚未找到 $APP_BUNDLE，正在先執行 ./package_macos.sh 打包應用..."
    ./package_macos.sh
fi

if [ ! -f "$ENTITLEMENTS" ]; then
    echo "❌ 找不到 entitlements.plist 檔案: $ENTITLEMENTS"
    exit 1
fi

# ==============================================================================
# 自動偵測簽名證書 (Developer ID Application)
# ==============================================================================
if [ -z "$SIGN_IDENTITY" ]; then
    echo "[1/4] 搜尋鑰匙圈中的 Developer ID Application 證書..."
    # 搜尋有效之 Developer ID Application 憑證
    DETECTED_ID="$(security find-identity -p codesigning -v 2>/dev/null | grep "Developer ID Application:" | head -n 1 | sed -E 's/.*"([^"]+)".*/\1/' || true)"
    if [ -n "$DETECTED_ID" ]; then
        SIGN_IDENTITY="$DETECTED_ID"
        echo "      已自動偵測並選用: $SIGN_IDENTITY"
    else
        echo "      ⚠️ 未在鑰匙圈中找到「Developer ID Application」正式簽名證書。"
        echo "      將切換至 Ad-hoc 本地簽名模式（含 Hardened Runtime 與 Entitlements）。"
        echo "      (提示: 若需發行供他人雙擊無警報開啟之官方版本，需使用 Apple Developer 帳號所頒發之證書)"
        SIGN_IDENTITY="-"
        SIGN_ONLY=true
    fi
else
    echo "[1/4] 使用指定簽名身分: $SIGN_IDENTITY"
fi

# ==============================================================================
# 執行深度程式碼簽名 (Deep Code Signing with Hardened Runtime)
# ==============================================================================
echo "[2/4] 執行深度程式碼簽名 (Hardened Runtime)..."

# 清除 macOS 隔離屬性與暫存快取
xattr -cr "$APP_BUNDLE" 2>/dev/null || true
find "$APP_BUNDLE" -name ".DS_Store" -delete 2>/dev/null || true
find "$APP_BUNDLE" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# 優先簽名巢狀二進位檔 (如內嵌的 ffmpeg)
RESOURCES_BIN="$APP_BUNDLE/Contents/Resources/bin"
if [ -d "$RESOURCES_BIN" ]; then
    for binary in "$RESOURCES_BIN"/*; do
        if [ -f "$binary" ] && [ -x "$binary" ]; then
            echo "      簽名內嵌執行檔: $(basename "$binary")..."
            codesign --force --options runtime --timestamp \
                     --entitlements "$ENTITLEMENTS" \
                     --sign "$SIGN_IDENTITY" "$binary" 2>/dev/null || \
            codesign --force --options runtime \
                     --entitlements "$ENTITLEMENTS" \
                     --sign "$SIGN_IDENTITY" "$binary"
        fi
    done
fi

# 簽名動態函式庫與模組 (.dylib, .so)
find "$APP_BUNDLE" -type f \( -name "*.dylib" -o -name "*.so" \) 2>/dev/null | while read -r dylib; do
    echo "      簽名動態庫: $(basename "$dylib")..."
    codesign --force --options runtime --sign "$SIGN_IDENTITY" "$dylib" 2>/dev/null || true
done

# 簽名主執行檔 AURARec
MAIN_EXEC="$APP_BUNDLE/Contents/MacOS/$(/usr/libexec/PlistBuddy -c "Print :CFBundleExecutable" "$APP_BUNDLE/Contents/Info.plist" 2>/dev/null || echo AURARec)"
if [ -f "$MAIN_EXEC" ]; then
    echo "      簽名主啟動器: AURARec..."
    codesign --force --options runtime --timestamp \
             --entitlements "$ENTITLEMENTS" \
             --sign "$SIGN_IDENTITY" "$MAIN_EXEC" 2>/dev/null || \
    codesign --force --options runtime \
             --entitlements "$ENTITLEMENTS" \
             --sign "$SIGN_IDENTITY" "$MAIN_EXEC"
fi

# 簽名整個 App Bundle
echo "      簽名主 App Bundle: $APP_BUNDLE..."
if [ "$SIGN_IDENTITY" = "-" ]; then
    # Ad-hoc 簽名不支援 Apple 時間戳伺服器
    codesign --force --deep --options runtime \
             --entitlements "$ENTITLEMENTS" \
             --sign "-" "$APP_BUNDLE"
else
    codesign --force --deep --options runtime --timestamp \
             --entitlements "$ENTITLEMENTS" \
             --sign "$SIGN_IDENTITY" "$APP_BUNDLE"
fi

echo "      驗證簽名完整性..."
codesign --verify --deep --strict --verbose=1 "$APP_BUNDLE"
echo "      ✅ 程式碼簽名驗證成功！"

# 若僅要求簽名，在此處結束
if [ "$SIGN_ONLY" = true ]; then
    echo "=================================================="
    if [ "$SIGN_IDENTITY" = "-" ]; then
        echo "   Ad-hoc 簽名完成！本機可正常測試執行。"
    else
        echo "   Developer ID 簽名完成！(--sign-only 略過公證流程)"
    fi
    echo "=================================================="
    exit 0
fi

# ==============================================================================
# Apple 公證流程 (Apple Notarization via notarytool)
# ==============================================================================
echo "[3/4] 準備向 Apple Notary 伺服器提交公證..."

# 決定上傳檔案：優先使用 DMG，若無則打包 ZIP
UPLOAD_FILE=""
if [ -f "$DMG_PATH" ]; then
    UPLOAD_FILE="$DMG_PATH"
else
    UPLOAD_FILE="$ZIP_PATH"
    echo "      建立用於公證的 ZIP 封裝包..."
    mkdir -p "$DIST_DIR"
    rm -f "$UPLOAD_FILE"
    ditto -c -k --sequesterRsrc --keepParent "$APP_BUNDLE" "$UPLOAD_FILE"
fi

echo "      準備提交檔案: $UPLOAD_FILE"

# 組合 notarytool 授權參數
NOTARY_AUTH_ARGS=()
if [ -n "$KEYCHAIN_PROFILE" ]; then
    echo "      使用 Keychain Profile 進行公證驗證: $KEYCHAIN_PROFILE"
    NOTARY_AUTH_ARGS=(--keychain-profile "$KEYCHAIN_PROFILE")
elif [ -n "$API_KEY_PATH" ] && [ -n "$API_KEY_ID" ] && [ -n "$API_ISSUER_ID" ]; then
    echo "      使用 App Store Connect API Key 進行公證驗證"
    NOTARY_AUTH_ARGS=(--key "$API_KEY_PATH" --key-id "$API_KEY_ID" --issuer "$API_ISSUER_ID")
elif [ -n "$APPLE_ID" ] && [ -n "$APP_SPECIFIC_PWD" ] && [ -n "$TEAM_ID" ]; then
    echo "      使用 Apple ID 與 App-Specific 密碼進行公證驗證: $APPLE_ID"
    NOTARY_AUTH_ARGS=(--apple-id "$APPLE_ID" --password "$APP_SPECIFIC_PWD" --team-id "$TEAM_ID")
else
    echo "❌ 缺少公證憑證！請提供以下其中一種憑證組合："
    echo "   1. --keychain-profile <profile_name> (推薦)"
    echo "   2. --apple-id <email> --password <pwd> --team-id <team>"
    echo "   3. --api-key <path> --key-id <id> --issuer <uuid>"
    echo ""
    echo "💡 建立 Keychain Profile 的方法："
    echo "   xcrun notarytool store-credentials \"notary-profile\" \\"
    echo "     --apple-id \"your-apple-id@example.com\" \\"
    echo "     --team-id \"XXXXXXXXXX\" \\"
    echo "     --password \"app-specific-password\""
    exit 1
fi

echo "      正在上傳至 Apple 伺服器並等待公證核准 (可能需 1~3 分鐘)..."
SUBMISSION_OUTPUT=$(xcrun notarytool submit "$UPLOAD_FILE" "${NOTARY_AUTH_ARGS[@]}" --wait 2>&1)
echo "$SUBMISSION_OUTPUT"

# 檢查是否通過公證
if echo "$SUBMISSION_OUTPUT" | grep -q "status: Accepted"; then
    echo "      🎉 Apple 公證成功通過 (status: Accepted)！"
else
    echo "❌ Apple 公證未能通過，請檢視上方日誌輸出或執行日誌查詢："
    SUBMISSION_ID=$(echo "$SUBMISSION_OUTPUT" | grep "id:" | head -n 1 | awk '{print $2}' || true)
    if [ -n "$SUBMISSION_ID" ]; then
        echo "   xcrun notarytool log $SUBMISSION_ID ${NOTARY_AUTH_ARGS[*]}"
    fi
    exit 1
fi

# ==============================================================================
# 票證裝釘 (Staple Notarization Ticket)
# ==============================================================================
echo "[4/4] 裝釘公證票證 (Staple Ticket)..."
if xcrun stapler staple "$APP_BUNDLE" 2>&1; then
    echo "      ✅ 已成功將公證票證裝釘至 $APP_BUNDLE"
else
    echo "      ⚠️ 裝釘至 App Bundle 失敗或暫不可用"
fi

if [ -f "$DMG_PATH" ]; then
    if xcrun stapler staple "$DMG_PATH" 2>&1; then
        echo "      ✅ 已成功將公證票證裝釘至 $DMG_PATH"
    fi
fi

# 更新最終同步 ZIP
if [ -f "$ZIP_PATH" ]; then
    echo "      重新生成含裝釘票證之發行版 ZIP..."
    rm -f "$ZIP_PATH"
    ditto -c -k --sequesterRsrc --keepParent "$APP_BUNDLE" "$ZIP_PATH"
    if [ -d "web_studio/download" ]; then
        cp -f "$ZIP_PATH" "web_studio/download/$(basename "$ZIP_PATH")"
    fi
fi

# Gatekeeper 終端模擬驗證
echo "      執行 Gatekeeper 模擬檢查..."
spctl --assess --type execute --verbose "$APP_BUNDLE" 2>&1 || true

echo "=================================================="
echo "   🎊 簽名與公證全數順利完成！"
echo "   使用者雙擊開啟時將直接通行，無任何安全阻擋警報。"
echo "=================================================="
