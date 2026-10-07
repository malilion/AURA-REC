#!/usr/bin/env bash

# 輕量桌面錄製工具啟動腳本
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# 檢查 ffmpeg
if ! command -v ffmpeg &> /dev/null && [ ! -f "/opt/homebrew/bin/ffmpeg" ]; then
    echo "⚠️ 警告: 未偵測到 FFmpeg，請先安裝 FFmpeg (例如: brew install ffmpeg)"
fi

echo "🚀 正在啟動輕量桌面錄製工具..."
python3 app.py
