#!/usr/bin/env bash

# 輕量桌面錄製工具啟動腳本
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 檢查 ffmpeg
if ! command -v ffmpeg &> /dev/null && [ ! -f "/opt/homebrew/bin/ffmpeg" ]; then
    echo "⚠️ 警告: 未偵測到 FFmpeg，請先安裝 FFmpeg (例如: brew install ffmpeg)"
fi

echo "🚀 正在啟動輕量桌面錄製工具..."
CHOSEN_PY=""
for py in "/opt/homebrew/bin/python3.13" "/opt/homebrew/bin/python3.12" "/opt/homebrew/bin/python3.11" "/opt/homebrew/bin/python3" "/usr/local/bin/python3" "$(command -v python3 2>/dev/null)" "/usr/bin/python3"; do
    if [ -x "$py" ] && "$py" -c "import tkinter; assert getattr(tkinter, 'TkVersion', 0) >= 8.6" 2>/dev/null; then
        CHOSEN_PY="$py"
        break
    fi
done

if [ -z "$CHOSEN_PY" ]; then
    for py in "/opt/homebrew/bin/python3.13" "/opt/homebrew/bin/python3.12" "/opt/homebrew/bin/python3.11" "/opt/homebrew/bin/python3" "/usr/local/bin/python3" "$(command -v python3 2>/dev/null)" "/usr/bin/python3"; do
        if [ -x "$py" ] && "$py" -c "import tkinter" 2>/dev/null; then
            CHOSEN_PY="$py"
            break
        fi
    done
fi

if [ -z "$CHOSEN_PY" ]; then
    CHOSEN_PY="python3"
fi

"$CHOSEN_PY" app.py
