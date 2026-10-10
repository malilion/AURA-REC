#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
國際化多語系支援模組 (Internationalization / i18n Engine)
==========================================================
支援語系：
  - zh-TW : 繁體中文 (Traditional Chinese)
  - en    : English
  - ja    : 日本語 (Japanese)
  - zh-CN : 简体中文 (Simplified Chinese)

核心特性：
  1. 零外部相依性，自動偵測作業系統語系 (macOS AppleLanguages / Windows UI Language / POSIX LANG)。
  2. 雙向支援「鍵值查詢 tr_key()」與「原文語句翻譯 tr()」，並支援正則動態參數模板（如檔案數量、倒數秒數、遮罩數、字幕數）。
  3. 支援 Tkinter 視窗樹即時無損熱切換 (`translate_widget_tree`)：不需重啟應用程式，一鍵即時切換主視窗、下拉選單、頂部選單列與子對話框之語系。
"""

import locale
import os
import re
import subprocess
import tkinter as tk
from tkinter import ttk

SUPPORTED_LANGUAGES = [
    ("zh-TW", "繁體中文"),
    ("en", "English"),
    ("ja", "日本語"),
    ("zh-CN", "简体中文"),
]

LANGUAGE_LABELS = {code: label for code, label in SUPPORTED_LANGUAGES}
LABEL_TO_LANG = {label: code for code, label in SUPPORTED_LANGUAGES}

_CURRENT_LANG = "zh-TW"


def detect_system_locale():
    """自動偵測作業系統預設語系，回傳 'zh-TW' | 'en' | 'ja' | 'zh-CN'"""
    env_lang = (
        os.environ.get("AURA_LANG")
        or os.environ.get("LC_ALL")
        or os.environ.get("LC_MESSAGES")
        or os.environ.get("LANG")
        or ""
    ).lower()

    if not env_lang or env_lang in ("c", "posix", "c.utf-8"):
        try:
            loc = locale.getlocale()[0] or ""
            env_lang = loc.lower()
        except Exception:
            pass

    if not env_lang and os.uname().sysname == "Darwin":
        try:
            out = subprocess.check_output(
                ["defaults", "read", "-g", "AppleLanguages"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=1.0,
            ).lower()
            env_lang = out
        except Exception:
            pass

    if "ja" in env_lang or "jp" in env_lang:
        return "ja"
    if any(k in env_lang for k in ("zh_cn", "zh-cn", "zh-hans", "hans")):
        return "zh-CN"
    if any(k in env_lang for k in ("zh_tw", "zh-tw", "zh_hk", "zh-hk", "zh-hant", "hant", "zh")):
        return "zh-TW"
    if "en" in env_lang:
        return "en"
    return "zh-TW"


def set_language(lang_code):
    """設定目前作用中的語系代碼"""
    global _CURRENT_LANG
    if not lang_code or lang_code == "auto":
        _CURRENT_LANG = detect_system_locale()
        return _CURRENT_LANG
    code = str(lang_code).strip()
    if code in LABEL_TO_LANG:
        code = LABEL_TO_LANG[code]
    if code not in LANGUAGE_LABELS:
        low = code.lower()
        if low.startswith("en"):
            code = "en"
        elif low.startswith("ja") or low.startswith("jp"):
            code = "ja"
        elif "cn" in low or "hans" in low:
            code = "zh-CN"
        else:
            code = "zh-TW"
    _CURRENT_LANG = code
    return _CURRENT_LANG


def get_language():
    """取得目前作用中的語系代碼"""
    return _CURRENT_LANG


def next_language(current=None):
    """循環切換至下一個語系"""
    cur = current or _CURRENT_LANG
    codes = [c for c, _ in SUPPORTED_LANGUAGES]
    idx = codes.index(cur) if cur in codes else 0
    nxt = codes[(idx + 1) % len(codes)]
    return set_language(nxt)


def get_language_badge(lang_code=None):
    """回傳頂部狀態列簡短語系徽章文字"""
    code = lang_code or _CURRENT_LANG
    return {
        "zh-TW": "🌐 繁中",
        "en": "🌐 EN",
        "ja": "🌐 日本語",
        "zh-CN": "🌐 简中",
    }.get(code, "🌐 繁中")


# ==============================================================================
# 繁體中文 -> English / 日本語 對照詞庫 (Exact Phrase Dictionary)
# ==============================================================================

PHRASE_DICT = {
    # --- 頂部與狀態列 ---
    "●  就緒": {"en": "●  Ready", "ja": "●  準備完了"},
    "●  錄製中": {"en": "●  Recording", "ja": "●  録画中"},
    "●  暫停": {"en": "●  Paused", "ja": "●  一時停止"},
    "●  正在儲存": {"en": "●  Saving", "ja": "●  保存中"},
    "截圖": {"en": "Screenshot", "ja": "スクショ"},
    "開始錄影": {"en": "Start Recording", "ja": "録画開始"},
    "停止錄影": {"en": "Stop Recording", "ja": "録画停止"},
    "暫停": {"en": "Pause", "ja": "一時停止"},
    "繼續": {"en": "Resume", "ja": "再開"},
    "取消": {"en": "Cancel", "ja": "キャンセル"},
    "完成": {"en": "Done", "ja": "完了"},
    "確定": {"en": "OK", "ja": "OK"},
    "關閉": {"en": "Close", "ja": "閉じる"},
    "儲存設定": {"en": "Save Settings", "ja": "設定を保存"},
    "已取消倒數": {"en": "Countdown cancelled", "ja": "カウントダウンを解除しました"},
    "再按一次或按 Esc 取消": {
        "en": "Press again or Esc to cancel",
        "ja": "もう一度押すか Esc でキャンセル",
    },
    "正在確認錄影有順利開始…": {
        "en": "Verifying recording stream...",
        "ja": "録画開始を確認しています…",
    },
    "已暫停。F8 繼續，或按停止結束": {
        "en": "Paused. Press F8 to resume, or Stop to finish",
        "ja": "一時停止中。F8 で再開、停止で終了",
    },

    # --- 主錄製表單 ---
    "錄製": {"en": "Capture Settings", "ja": "キャプチャ設定"},
    "螢幕": {"en": "Screen", "ja": "画面"},
    "預覽": {"en": "Preview", "ja": "プレビュー"},
    "識別": {"en": "Identify", "ja": "識別"},
    "麥克風": {"en": "Mic", "ja": "マイク"},
    "測試": {"en": "Test", "ja": "テスト"},
    "停止": {"en": "Stop", "ja": "停止"},
    "指南": {"en": "Guide", "ja": "ガイド"},
    "系統音": {"en": "System Audio", "ja": "システム音声"},
    "解析度": {"en": "Resolution", "ja": "解像度"},
    "幀率": {"en": "Frame Rate", "ja": "フレームレート"},
    "畫質": {"en": "Quality", "ja": "画質"},
    "格式": {"en": "Format", "ja": "形式"},
    "範圍": {"en": "Area", "ja": "範囲"},
    "時限": {"en": "Time Limit", "ja": "制限時間"},
    "分段": {"en": "Split", "ja": "分割保存"},
    "長錄影才需要": {"en": "For long recordings", "ja": "長時間録画向け"},
    "選視窗": {"en": "Pick Window", "ja": "ウィンドウ選択"},
    "重選範圍": {"en": "Reselect Area", "ja": "範囲を再選択"},

    # --- 下拉選單項目 ---
    "原生（較吃資源）": {"en": "Native (High Load)", "ja": "ネイティブ（高負荷）"},
    "2K（長邊 2560）": {"en": "2K (Max 2560)", "ja": "2K（長辺 2560）"},
    "1080p（長邊 1920）": {"en": "1080p (Max 1920)", "ja": "1080p（長辺 1920）"},
    "720p（長邊 1280）": {"en": "720p (Max 1280)", "ja": "720p（長辺 1280）"},
    "30 FPS": {"en": "30 FPS", "ja": "30 FPS"},
    "60 FPS（流暢高幀率）": {"en": "60 FPS (Smooth)", "ja": "60 FPS（なめらか）"},
    "120 FPS（電競/極限流暢）": {"en": "120 FPS (Ultra Smooth)", "ja": "120 FPS（超なめらか）"},
    "15 FPS（較省空間）": {"en": "15 FPS (Compact)", "ja": "15 FPS（省容量）"},
    "標準": {"en": "Standard", "ja": "標準"},
    "較省": {"en": "Compact", "ja": "省容量"},
    "較清晰": {"en": "High Clarity", "ja": "高画質"},
    "不限制": {"en": "Unlimited", "ja": "無制限"},
    "1 分鐘": {"en": "1 min", "ja": "1 分"},
    "5 分鐘": {"en": "5 min", "ja": "5 分"},
    "10 分鐘": {"en": "10 min", "ja": "10 分"},
    "30 分鐘": {"en": "30 min", "ja": "30 分"},
    "60 分鐘": {"en": "60 min", "ja": "60 分"},
    "不分段": {"en": "No Split", "ja": "分割なし"},
    "每 5 分鐘": {"en": "Every 5 min", "ja": "5 分ごと"},
    "每 10 分鐘": {"en": "Every 10 min", "ja": "10 分ごと"},
    "每 30 分鐘": {"en": "Every 30 min", "ja": "30 分ごと"},
    "整個螢幕": {"en": "Full Screen", "ja": "全画面"},
    "自訂範圍": {"en": "Custom Region", "ja": "カスタム範囲"},
    "指定視窗": {"en": "Specific Window", "ja": "ウィンドウ指定"},

    # --- 勾選框 ---
    "硬體加速（速度優先，檔案較大）": {"en": "Hardware acceleration (faster, larger files)", "ja": "ハードウェア高速化（速度優先・ファイル大）"},
    "使用硬體加速": {"en": "Hardware Acceleration", "ja": "ハードウェア高速化"},
    "使用 GPU 硬體加速": {"en": "GPU Acceleration", "ja": "GPU ハードウェア高速化"},
    "獨立多音軌 (Multi-track)": {"en": "Multi-track Audio", "ja": "マルチトラック音声"},
    "開始前倒數 3 秒": {"en": "3s Countdown", "ja": "3秒カウントダウン"},
    "錄影時縮成小視窗": {"en": "Minimize to Floating Bar", "ja": "録画時にミニバー化"},
    "錄下游標": {"en": "Capture Cursor", "ja": "カーソルを録画"},
    "點擊發光波紋": {"en": "Click Ripple Effect", "ja": "クリック波紋エフェクト"},
    "即時按鍵顯示": {"en": "Keystroke HUD", "ja": "キー入力 HUD 表示"},
    "剪輯影片（選擇檔案）": {"en": "Edit a Video (Choose File)", "ja": "動画を編集（ファイル選択）"},
    "錄完自動開啟剪輯": {"en": "Open Editor After Recording", "ja": "録画後に編集を自動で開く"},
    "開啟影片剪輯…": {"en": "Open Video in Editor…", "ja": "動画を編集で開く…"},
    "剪輯最新錄影": {"en": "Edit Latest Recording", "ja": "最新の録画を編集"},
    "選擇要剪輯的影片": {"en": "Choose a video to edit", "ja": "編集する動画を選択"},
    "影片檔": {"en": "Video files", "ja": "動画ファイル"},
    "所有檔案": {"en": "All files", "ja": "すべてのファイル"},
    "截圖自動複製": {"en": "Auto-Copy Screenshot", "ja": "スクショを自動コピー"},
    "音效提示": {"en": "Sound Alerts", "ja": "効果音通知"},

    # --- 畫中畫 (PiP) 與人像智慧去背/虛化 ---
    "畫中畫相機 (PiP 人臉鏡頭)": {"en": "PiP Camera Overlay", "ja": "ワイプカメラ (PiP)"},
    "Loom / Recordly 風格": {"en": "Loom / Recordly Style", "ja": "Loom / Recordly スタイル"},
    "鏡頭試看 👁": {"en": "Preview Cam 👁", "ja": "カメラ試写 👁"},
    "鏡頭": {"en": "Camera", "ja": "カメラ"},
    "形狀": {"en": "Shape", "ja": "形状"},
    "位置": {"en": "Position", "ja": "位置"},
    "尺寸": {"en": "Size", "ja": "サイズ"},
    "外框": {"en": "Border", "ja": "枠線"},
    "背景": {"en": "Background", "ja": "背景処理"},
    "強度": {"en": "Strength", "ja": "強度"},
    "錄影時顯示桌面小圓圈": {"en": "Show Floating Camera Bubble", "ja": "録画中にカメラバブルを表示"},
    "圓形相機 (Circle)": {"en": "Circle Bubble", "ja": "円形バブル (Circle)"},
    "圓角矩形 (Rect)": {"en": "Rounded Rect", "ja": "角丸長方形 (Rect)"},
    "右下角": {"en": "Bottom-Right", "ja": "右下"},
    "左下角": {"en": "Bottom-Left", "ja": "左下"},
    "右上角": {"en": "Top-Right", "ja": "右上"},
    "左上角": {"en": "Top-Left", "ja": "左上"},
    "中 (260px)": {"en": "Medium (260px)", "ja": "中 (260px)"},
    "小 (200px)": {"en": "Small (200px)", "ja": "小 (200px)"},
    "大 (340px)": {"en": "Large (340px)", "ja": "大 (340px)"},
    "極光霓虹藍 (#00f0ff)": {"en": "Aurora Cyan (#00f0ff)", "ja": "オーロラシアン (#00f0ff)"},
    "純白外框 (#ffffff)": {"en": "Pure White (#ffffff)", "ja": "ピュアホワイト (#ffffff)"},
    "無外框": {"en": "No Border", "ja": "枠線なし"},
    "原始鏡頭 (Original)": {"en": "Original Camera", "ja": "オリジナル (Original)"},
    "人像背景虛化 (Portrait Blur)": {"en": "Portrait Blur (Bokeh)", "ja": "ポートレート 배경ぼかし"},
    "純人像去背透空 (Transparent)": {"en": "Transparent Cutout", "ja": "人物切り抜き (背景透過)"},
    "綠幕扣像 (Green Screen)": {"en": "Green Screen Key", "ja": "グリーンバック合成"},
    "藍幕扣像 (Blue Screen)": {"en": "Blue Screen Key", "ja": "ブルーバック合成"},
    "極光深色背景 (Aurora BG)": {"en": "Aurora Virtual BG", "ja": "オーロラ仮想背景"},
    "標準 (Medium)": {"en": "Medium", "ja": "標準 (Medium)"},
    "輕微 (Subtle)": {"en": "Subtle", "ja": "弱め (Subtle)"},
    "強烈 (Strong)": {"en": "Strong", "ja": "強め (Strong)"},

    # --- 視窗排除與浮水印保護 ---
    "視窗隱私排除": {"en": "Window Exclusion", "ja": "ウィンドウ除外保護"},
    "智慧標示浮水印": {"en": "Attribution Watermark", "ja": "透かし保護 (Watermark)"},
    "🛡️ 保護與浮水印設定": {"en": "🛡️ Protection & Watermark", "ja": "🛡️ 除外・透かし設定"},
    "🛡️ 視窗排除與浮水印版權保護中心": {
        "en": "🛡️ Window Exclusion & Watermark Protection Center",
        "ja": "🛡️ ウィンドウ除外・著作権透かし保護センター",
    },
    "防止敏感對話或密碼外洩 · 為教學與商務錄影加上標示動態浮水印": {
        "en": "Prevent sensitive leaks · Protect recordings with dynamic attribution watermarks",
        "ja": "機密チャットやパスワードの漏洩を防止 · 動的透かしで録画の無断転載を抑止",
    },
    "🔒 1. 視窗排除與敏感應用保護 (Window Exclusion)": {
        "en": "🔒 1. Window Exclusion & Sensitive App Protection",
        "ja": "🔒 1. ウィンドウ除外・機密アプリ保護 (Window Exclusion)",
    },
    "啟用視窗隱私排除保護": {"en": "Enable Window Privacy Exclusion", "ja": "ウィンドウプライバシー除外を有効化"},
    "自身錄影控制列硬體穿透隱藏 (OS Native)": {
        "en": "Hide Recorder Controls from Capture (OS Native)",
        "ja": "録画コントロールバーを透過非表示 (OS ネイティブ)",
    },
    "自動偵測並遮蔽敏感應用 (LINE / 1Password / 密碼 / 無痕視窗)": {
        "en": "Auto-detect & Mask Sensitive Apps (LINE / 1Password / Passwords / Incognito)",
        "ja": "機密アプリを自動検出してマスク (LINE / 1Password / パスワード / シークレット)",
    },
    "錄影時於桌面顯示實體防窺盾牌覆蓋敏感視窗": {
        "en": "Cover Sensitive Windows with Desktop Privacy Shields During Capture",
        "ja": "録画中、機密ウィンドウ上にプライバシールドを重ねて保護",
    },
    "遮蔽方式:": {"en": "Mask Mode:", "ja": "マスク方式:"},
    "自訂排除關鍵字:": {"en": "Custom Keywords:", "ja": "除外キーワード:"},
    "勾選要排除遮蔽的已開啟視窗 (點擊可多選):": {
        "en": "Select Open Windows to Exclude/Mask (Multi-select):",
        "ja": "除外・マスクする開いているウィンドウを選択 (複数選択可):",
    },
    "重新掃描視窗 ↻": {"en": "Rescan Windows ↻", "ja": "再スキャン ↻"},
    "💧 2. 智慧浮水印版權保護 (Watermark Protection)": {
        "en": "💧 2. Smart Watermark Copyright Protection",
        "ja": "💧 2. スマート透かし著作権保護 (Watermark Protection)",
    },
    "浮水印模式:": {"en": "Watermark Mode:", "ja": "透かしモード:"},
    "顯示位置:": {"en": "Position:", "ja": "表示位置:"},
    "視覺風格:": {"en": "Visual Style:", "ja": "スタイル:"},
    "不透明度:": {"en": "Opacity:", "ja": "不透明度:"},
    "浮水印文字:": {"en": "Watermark Text:", "ja": "透かし文字:"},
    "自訂 Logo:": {"en": "Custom Logo:", "ja": "カスタムロゴ:"},
    "選擇 PNG 圖片...": {"en": "Choose Image...", "ja": "画像を選択..."},
    "即時浮水印效果預覽:": {"en": "Live Watermark Preview:", "ja": "透かしリアルタイムプレビュー:"},
    "目前未啟用浮水印 (選擇上方模式即可預覽效果)": {
        "en": "Watermark is currently disabled (Select a mode above to preview)",
        "ja": "現在透かしは無効です（上のモードを選択するとプレビュー表示されます）",
    },
    "套用並儲存保護設定 ✓": {"en": "Apply & Save Settings ✓", "ja": "保護設定を適用して保存 ✓"},

    # --- 預覽與最近錄影卡片 ---
    "畫面即時縮圖": {"en": "Live Screen Thumbnail", "ja": "画面ライブサムネイル"},
    "全景對比 ⤢": {"en": "All Displays ⤢", "ja": "全画面比較 ⤢"},
    "刷新 ↻": {"en": "Refresh ↻", "ja": "更新 ↻"},
    "點擊縮圖開啟多螢幕大圖對比 · 或點上方「識別」查看螢幕編號": {
        "en": "Click thumbnail to compare displays · or click 'Identify' above",
        "ja": "サムネイルをクリックして画面比較 · または上の「識別」で番号表示",
    },
    "最近的錄影": {"en": "Recent Recordings", "ja": "最近の録画"},
    "重新整理": {"en": "Refresh", "ja": "再読み込み"},
    "播放最新": {"en": "Play Latest", "ja": "最新を再生"},
    "剪輯": {"en": "Edit", "ja": "編集"},
    "變更位置": {"en": "Change Folder", "ja": "保存先変更"},
    "開啟資料夾": {"en": "Open Folder", "ja": "フォルダを開く"},
    "這個資料夾還沒有錄影": {"en": "No recordings in this folder yet", "ja": "このフォルダにはまだ録画がありません"},
    "刪除": {"en": "Delete", "ja": "削除"},
    "播放": {"en": "Play", "ja": "再生"},
    "開啟": {"en": "Open", "ja": "開く"},
    "顯示": {"en": "Reveal", "ja": "表示"},
    "複製": {"en": "Copy", "ja": "コピー"},
    "改名": {"en": "Rename", "ja": "名前変更"},

    # --- 迷你懸浮列 (Mini Floating Bar) ---
    "塗鴉": {"en": "Draw", "ja": "描画"},
    "關閉塗鴉": {"en": "Close Draw", "ja": "描画終了"},
    "展開": {"en": "Expand", "ja": "展開"},

    # --- 選單列 (Menu Bar) ---
    "檔案": {"en": "File", "ja": "ファイル"},
    "說明": {"en": "Help", "ja": "ヘルプ"},
    "語言 (Language)": {"en": "Language", "ja": "言語 (Language)"},
    "開啟儲存資料夾": {"en": "Open Output Folder", "ja": "保存フォルダを開く"},
    "變更儲存位置…": {"en": "Change Output Folder…", "ja": "保存先を変更…"},
    "暫停或繼續": {"en": "Pause / Resume", "ja": "一時停止 / 再開"},
    "螢幕塗鴉與聚光燈": {"en": "Screen Annotation & Spotlight", "ja": "画面描画・スポットライト"},
    "展開錄影畫面": {"en": "Expand Window", "ja": "メイン画面を展開"},
    "收成小條": {"en": "Collapse to Mini Bar", "ja": "ミニバーに縮小"},
    "選擇視窗…": {"en": "Pick Window…", "ja": "ウィンドウを選択…"},
    "視窗排除與浮水印保護…": {"en": "Window Exclusion & Watermark…", "ja": "ウィンドウ除外・透かし保護…"},
    "剪輯影片…": {"en": "Video Editor…", "ja": "動画を編集…"},
    "播放最新錄影": {"en": "Play Latest Recording", "ja": "最新の録画を再生"},
    "複製最新檔案": {"en": "Copy Latest File", "ja": "最新のファイルをコピー"},
    "系統聲音錄製指南…": {"en": "System Audio Setup Guide…", "ja": "システム音声録音ガイド…"},
    "檢查更新…": {"en": "Check for Updates…", "ja": "アップデートを確認…"},
    "偏好設定…": {"en": "Preferences…", "ja": "環境設定…"},
    "結束": {"en": "Quit", "ja": "終了"},
    "快捷鍵說明": {"en": "Keyboard Shortcuts", "ja": "ショートカット一覧"},
    "FFmpeg 與硬體加速檢視…": {"en": "FFmpeg & Hardware Diagnostics…", "ja": "FFmpeg・ハードウェア診断…"},
    "關於 AURA REC": {"en": "About AURA REC", "ja": "AURA REC について"},

    # --- 偏好設定 (Preferences) ---
    "偏好設定 — AURA REC": {"en": "Preferences — AURA REC", "ja": "環境設定 — AURA REC"},
    "偏好與進階設定": {"en": "Preferences & Advanced Settings", "ja": "環境設定・詳細オプション"},
    "介面語言 (Language)": {"en": "Interface Language", "ja": "表示言語 (Language)"},
    "儲存目錄": {"en": "Output Directory", "ja": "保存先フォルダ"},
    "變更…": {"en": "Change…", "ja": "変更…"},
    "自訂檔名前綴": {"en": "Filename Prefix", "ja": "ファイル名プレフィックス"},
    "範例：輸入「AURA」則檔名為 AURA_2026-10-09_18-30.mp4": {
        "en": "Example: 'AURA' produces AURA_2026-10-09_18-30.mp4",
        "ja": "例：「AURA」と入力すると AURA_2026-10-09_18-30.mp4 になります",
    },
    "功能開關": {"en": "Feature Toggles", "ja": "機能スイッチ"},
    "截圖後自動複製至剪貼簿": {"en": "Auto-copy screenshot to clipboard", "ja": "スクショ後に自動でクリップボードへコピー"},
    "錄製滑鼠游標": {"en": "Capture mouse cursor", "ja": "マウスカーソルを録画"},
    "滑鼠點擊發光漣漪 (Click Ripple)": {"en": "Mouse Click Ripple Effect", "ja": "マウスクリック波紋 (Click Ripple)"},
    "即時按鍵浮水印 (Keystroke HUD)": {"en": "Live Keystroke HUD", "ja": "キー入力表示 (Keystroke HUD)"},
    "啟用晶片 GPU 硬體加速": {"en": "Enable GPU Hardware Acceleration", "ja": "GPU ハードウェア高速化を有効化"},
    "啟用錄影與截圖音效提示": {"en": "Enable Sound Effects", "ja": "録画・スクショの効果音を有効化"},
    "啟動時自動檢查新版本": {"en": "Automatically check for updates on startup", "ja": "起動時に自動でアップデートを確認"},

    # --- 剪輯工作站 (VideoEditorWindow) ---
    "開啟影片…": {"en": "Open Video…", "ja": "動画を開く…"},
    "💬 智慧字幕…": {"en": "💬 AI Captions…", "ja": "💬 AI 字幕…"},
    "💧 浮水印保護…": {"en": "💧 Watermark…", "ja": "💧 透かし保護…"},
    "播放 [Space]": {"en": "Play [Space]", "ja": "再生 [Space]"},
    "停止 [Space]": {"en": "Stop [Space]", "ja": "停止 [Space]"},
    "未載入影片": {"en": "No Video Loaded", "ja": "動画未読み込み"},
    "點擊右上方「開啟影片」開始編輯": {
        "en": "Click 'Open Video' at top-right to start editing",
        "ja": "右上の「動画を開く」をクリックして編集開始",
    },
    "等待載入影片…": {"en": "Waiting for video…", "ja": "動画を待機中…"},
    "[ 設為起點 (I)": {"en": "[ Set In (I)", "ja": "[ 開始点 (I)"},
    "設為終點 (O) ]": {"en": "Set Out (O) ]", "ja": "終了点 (O) ]"},
    "−1 秒": {"en": "−1s", "ja": "−1秒"},
    "−0.1 秒": {"en": "−0.1s", "ja": "−0.1秒"},
    "+0.1 秒": {"en": "+0.1s", "ja": "+0.1秒"},
    "+1 秒": {"en": "+1s", "ja": "+1秒"},
    "Space 播放 · I/O 設範圍 · ←/→ 微調 · ⌘E 匯出": {
        "en": "Space Play · I/O Range · ←/→ Nudge · ⌘E Export",
        "ja": "Space 再生 · I/O 範囲 · ←/→ 微調整 · ⌘E 書き出し",
    },
    "畫布與視覺風格": {"en": "Canvas & Visual Style", "ja": "キャンバス・スタイル"},
    "畫面比例": {"en": "Aspect Ratio", "ja": "アスペクト比"},
    "背景主題": {"en": "Background Theme", "ja": "背景テーマ"},
    "顯示 macOS 視窗外框 (🔴🟡🟢)": {"en": "Show macOS Window Frame (🔴🟡🟢)", "ja": "macOS ウィンドウ枠を表示 (🔴🟡🟢)"},
    "智慧運鏡與縮放 (Auto Zoom)": {"en": "Smart Auto Zoom & Pan", "ja": "スマート自動ズーム (Auto Zoom)"},
    "運鏡模式": {"en": "Zoom Mode", "ja": "ズームモード"},
    "特寫倍率": {"en": "Zoom Level", "ja": "倍率"},
    "焦點": {"en": "Focus", "ja": "フォーカス"},
    "🎯 智慧偵測焦點": {"en": "🎯 Auto-Detect Focus", "ja": "🎯 フォーカス自動検出"},
    "預覽畫面即時顯示特寫效果": {"en": "Preview Zoom Effect Live", "ja": "プレビューにズームを即時反映"},
    "隱私遮罩 (Blur & Mosaic)": {"en": "Privacy Mask (Blur & Mosaic)", "ja": "プライバシーマスク (ぼかし・モザイク)"},
    "＋ 模糊 (Blur)": {"en": "＋ Blur", "ja": "＋ ぼかし (Blur)"},
    "＋ 馬賽克 (Mosaic)": {"en": "＋ Mosaic", "ja": "＋ モザイク (Mosaic)"},
    "點選上方按鈕後，在預覽畫面上拖曳框選": {
        "en": "Click a button above, then drag on the preview canvas",
        "ja": "上のボタンを押してからプレビュー画面をドラッグして範囲指定",
    },
    "套用:": {"en": "Scope:", "ja": "適用範囲:"},
    "全片": {"en": "Full Video", "ja": "動画全体"},
    "僅選取區段": {"en": "Selected Range", "ja": "選択区間のみ"},
    "全部清空": {"en": "Clear All", "ja": "すべて消去"},
    "智慧字幕 (AI Captions)": {"en": "AI Captions & Subtitles", "ja": "スマート字幕 (AI Captions)"},
    "尚未建立字幕": {"en": "No captions yet", "ja": "字幕未作成"},
    "✨ AI 產生": {"en": "✨ AI Generate", "ja": "✨ AI 自動生成"},
    "📋 編輯": {"en": "📋 Edit", "ja": "📋 編集"},
    "＋ 加句": {"en": "＋ Add", "ja": "＋ 追加"},
    "📥 匯入": {"en": "📥 Import", "ja": "📥 読込"},
    "📤 匯出": {"en": "📤 Export", "ja": "📤 書出"},
    "預覽畫面即時顯示字幕": {"en": "Show Captions on Preview", "ja": "プレビューに字幕を表示"},
    "精準剪輯範圍": {"en": "Trim Range", "ja": "トリミング範囲"},
    "起點 (In)": {"en": "In Point", "ja": "開始点 (In)"},
    "終點 (Out)": {"en": "Out Point", "ja": "終了点 (Out)"},
    "匯出規格": {"en": "Export Settings", "ja": "書き出し設定"},
    "⚡ 極速智慧無損 (Smart Cut 0.5s)": {"en": "⚡ Smart Lossless Cut (0.5s)", "ja": "⚡ スマート無劣化カット (0.5秒)"},
    "🎨 精準重編碼（比例/速度）": {"en": "🎨 Precise Re-encode (Ratio/Speed)", "ja": "🎨 高精度再エンコード（比率/速度）"},
    "🎞️ 高清 GIF 動態圖": {"en": "🎞️ High-Res Animated GIF", "ja": "🎞️ 高画質 GIF アニメ"},
    "🎵 提取音訊 (MP3)": {"en": "🎵 Extract Audio (MP3)", "ja": "🎵 音声抽出 (MP3)"},
    "播放速度": {"en": "Playback Speed", "ja": "再生速度"},
    "音量增益": {"en": "Volume Boost", "ja": "音量ゲイン"},
    "輸出畫質": {"en": "Output Quality", "ja": "出力画質"},
    "靜音輸出": {"en": "Mute Audio", "ja": "ミュート出力"},
    "封裝軟字幕軌至 MP4/MOV": {"en": "Embed Soft Subtitles in MP4/MOV", "ja": "MP4/MOV にソフト字幕を埋め込む"},
    "同時匯出同名 .srt 字幕檔": {"en": "Also Export Companion .srt File", "ja": "同名の .srt 字幕ファイルも書き出す"},
    "匯出時燒錄標示浮水印": {"en": "Burn-in Watermark on Export", "ja": "書き出し時に透かしを焼き込む"},
    "⚡ 一鍵匯出影片": {"en": "⚡ Export Video Now", "ja": "⚡ ワンクリック書き出し"},
    "正在匯出…": {"en": "Exporting…", "ja": "書き出し中…"},
    "螢幕錄影與截圖": {"en": "Screen Recorder & Capture", "ja": "画面録画・スクリーンショット"},
    "開始錄製": {"en": "Start Recording", "ja": "録画開始"},
    "停止錄製": {"en": "Stop Recording", "ja": "録画停止"},
    "畫面截圖": {"en": "Screenshot", "ja": "スクリーンショット"},
    "剪輯工作站": {"en": "Video Studio", "ja": "編集スタジオ"},
    "開啟剪輯工作站": {"en": "Open Video Studio", "ja": "編集スタジオを開く"},
    "全螢幕": {"en": "Full Screen", "ja": "全画面"},
    "個人視訊鏡頭 (畫中畫)": {"en": "Camera Picture-in-Picture (PiP)", "ja": "カメラ ワイプ (PiP)"},
    "原始畫面 (不去背)": {"en": "Original Camera (No Effect)", "ja": "元の映像 (加工なし)"},
    "人像景深虛化 (Blur)": {"en": "Portrait Blur (Bokeh)", "ja": "ポートレート背景ぼかし"},
    "智慧人像去背 (僅保留人像)": {"en": "Smart Cutout (Person Only)", "ja": "スマート人物切り抜き (人物のみ)"},
    "綠幕扣像去背 (Chroma Key)": {"en": "Chroma Key (Green Screen)", "ja": "クロマキー合成 (グリーンバック)"},
    "極光漸層虛擬背景 (Aurora)": {"en": "Aurora Virtual Background", "ja": "オーロラ仮想背景 (Aurora)"},
    "🛡️ 設定視窗排除與浮水印…": {"en": "🛡️ Window Exclusion & Watermark…", "ja": "🛡️ ウィンドウ除外・透かし設定…"},
    "剪輯工作站 — AURA REC": {"en": "Video Studio — AURA REC", "ja": "編集スタジオ — AURA REC"},
    "1.0x (原速)": {"en": "1.0x (Normal)", "ja": "1.0x (標準)"},
    "1.5x (推薦)": {"en": "1.5x (Recommended)", "ja": "1.5x (推奨)"},
    "2.0x (快進)": {"en": "2.0x (Fast)", "ja": "2.0x (高速)"},
    "0.5x (慢速)": {"en": "0.5x (Slow)", "ja": "0.5x (スロー)"},
    "100% 原始": {"en": "100% Original", "ja": "100% 標準"},
    "150% 增強": {"en": "150% Boost", "ja": "150% 増幅"},
    "200% 放大": {"en": "200% Max", "ja": "200% 最大"},
    "50% 降低": {"en": "50% Quiet", "ja": "50% 低減"},
    "原始畫質": {"en": "Original Quality", "ja": "元の画質"},
    "1080p 適合分享": {"en": "1080p Share", "ja": "1080p 共有向け"},
    "720p 節省空間": {"en": "720p Compact", "ja": "720p 省容量"},
    "關閉 (1.0x)": {"en": "Off (1.0x)", "ja": "オフ (1.0x)"},
    "平滑推進與退回": {"en": "Smooth In & Out", "ja": "スムーズ ズームイン・アウト"},
    "平滑推進特寫": {"en": "Smooth Zoom In", "ja": "スムーズ ズームイン"},
    "全程固定特寫": {"en": "Static Close-Up", "ja": "常時固定ズーム"},
    "畫面中心": {"en": "Center", "ja": "中央"},
    "上方中": {"en": "Top-Center", "ja": "上中央"},
    "下方中": {"en": "Bottom-Center", "ja": "下中央"},
    "🎯 自訂 / 點擊畫面": {"en": "🎯 Custom / Click Canvas", "ja": "🎯 カスタム / 画面クリック"},
    "偵測中…": {"en": "Detecting…", "ja": "検出中…"},
}


# 繁簡常用字彙與字元精準轉換表
_TRAD_TO_SIMP_WORDS = {
    "視訊鏡頭": "摄像头",
    "個人視訊鏡頭": "个人摄像头",
    "智慧人像去背": "智能人像抠图",
    "僅保留人像": "仅保留人像",
    "綠幕扣像去背": "绿幕抠像",
    "螢幕錄影": "屏幕录制",
    "錄影": "录影",
    "錄製": "录制",
    "螢幕": "屏幕",
    "視窗": "窗口",
    "畫質": "画质",
    "畫面": "画面",
    "幀率": "帧率",
    "硬體": "硬件",
    "軟體": "软件",
    "加速": "加速",
    "音訊": "音频",
    "麥克風": "麦克风",
    "系統": "系统",
    "偏好設定": "偏好设置",
    "設定": "设定",
    "剪輯": "剪辑",
    "匯出": "导出",
    "匯入": "导入",
    "檔案": "文件",
    "資料夾": "文件夹",
    "開啟": "打开",
    "關閉": "关闭",
    "儲存": "保存",
    "刪除": "删除",
    "複製": "复制",
    "選擇": "选择",
    "選取": "选取",
    "範圍": "范围",
    "倒數": "倒计时",
    "暫停": "暂停",
    "繼續": "继续",
    "開始": "开始",
    "停止": "停止",
    "結束": "结束",
    "預覽": "预览",
    "識別": "识别",
    "測試": "测试",
    "指南": "指南",
    "解析度": "分辨率",
    "時限": "时限",
    "分鐘": "分钟",
    "標準": "标准",
    "較省": "较省",
    "較清晰": "较清晰",
    "游標": "光标",
    "點擊": "点击",
    "波紋": "波纹",
    "按鍵": "按键",
    "顯示": "显示",
    "截圖": "截图",
    "畫中畫": "画中画",
    "人臉": "人脸",
    "鏡頭": "镜头",
    "形狀": "形状",
    "圓形": "圆形",
    "矩形": "矩形",
    "圓角": "圆角",
    "邊框": "边框",
    "外框": "外框",
    "極光": "极光",
    "霓虹": "霓虹",
    "純白": "纯白",
    "虛化": "虚化",
    "透空": "透空",
    "綠幕": "绿幕",
    "藍幕": "蓝幕",
    "強度": "强度",
    "輕微": "轻微",
    "強烈": "强烈",
    "隱私": "隐私",
    "排除": "排除",
    "保護": "保护",
    "浮水印": "水印",
    "防盜": "防盗",
    "版權": "版权",
    "敏感": "敏感",
    "應用": "应用",
    "密碼": "密码",
    "無痕": "无痕",
    "遮蔽": "遮蔽",
    "遮罩": "遮罩",
    "馬賽克": "马赛克",
    "盾牌": "盾牌",
    "關鍵字": "关键字",
    "掃描": "扫描",
    "時間戳記": "时间戳",
    "簽章": "签章",
    "簽名": "签名",
    "動態": "动态",
    "巡航": "巡航",
    "網格": "网格",
    "滿版": "满版",
    "圖片": "图片",
    "透明度": "透明度",
    "縮圖": "缩略图",
    "對比": "对比",
    "刷新": "刷新",
    "重新整理": "刷新",
    "最新": "最新",
    "變更": "更改",
    "改名": "重命名",
    "塗鴉": "涂鸦",
    "聚光燈": "聚光灯",
    "展開": "展开",
    "收成小條": "收起为迷你条",
    "說明": "帮助",
    "檢查更新": "检查更新",
    "關於": "关于",
    "語言": "语言",
    "語音": "语音",
    "字幕": "字幕",
    "軌道": "轨道",
    "時間軸": "时间轴",
    "運鏡": "运镜",
    "縮放": "缩放",
    "焦點": "焦点",
    "座標": "坐标",
    "偵測": "检测",
    "特寫": "特写",
    "無損": "无损",
    "極速": "极速",
    "重編碼": "重编码",
    "靜音": "静音",
    "音量": "音量",
    "燒錄": "烧录",
    "封裝": "封装",
    "請勿外流": "请勿外流",
    "就緒": "就绪",
    "還沒有": "还没有",
    "個檔案": "个文件",
    "確定": "确定",
    "取消": "取消",
    "完成": "完成",
}

_TRAD_CHAR_MAP = str.maketrans(
    "與為進階設訂開關後製執時長寬高點選預覽顯隱視窗螢幕錄製畫質幀數聲軌檔案夾儲刪複變頭鏡圓邊藍綠強輕標準專題範本網格動態簽章標示浮印語系體簡繁離線識別鍵盤標註畫筆塗鴉閃爍診斷報表硬體軟件僅個訊座標",
    "与为进阶设订开关后制执时长宽高点选预览显隐视窗屏幕录制画质帧数声轨文件夹储删复变头镜圆边蓝绿强轻标准专题范本网格动态签章防盗水印语系体简繁离线识别键盘标注画笔涂鸦闪烁诊断报表硬件软件仅个讯坐标",
)


def to_simplified_chinese(text):
    """將繁體中文字串轉為簡體中文"""
    res = str(text)
    for k, v in _TRAD_TO_SIMP_WORDS.items():
        if k in res:
            res = res.replace(k, v)
    return res.translate(_TRAD_CHAR_MAP)


# 動態正則翻譯規則
_REGEX_RULES = [
    (
        re.compile(r"^最近的錄影 \(共 (\d+) 個檔案\)$"),
        {
            "en": lambda m: f"Recent Recordings ({m.group(1)} files)",
            "ja": lambda m: f"最近の録画 (全 {m.group(1)} 件)",
            "zh-CN": lambda m: f"最近的录影 (共 {m.group(1)} 个文件)",
        },
    ),
    (
        re.compile(r"^●  倒數 (\d+)$"),
        {
            "en": lambda m: f"●  Countdown {m.group(1)}",
            "ja": lambda m: f"●  カウントダウン {m.group(1)}",
            "zh-CN": lambda m: f"●  倒计时 {m.group(1)}",
        },
    ),
    (
        re.compile(r"^選取長度 (.+)$"),
        {
            "en": lambda m: f"Selected {m.group(1)}",
            "ja": lambda m: f"選択範囲 {m.group(1)}",
            "zh-CN": lambda m: f"选取长度 {m.group(1)}",
        },
    ),
    (
        re.compile(r"^焦點座標:\s*(.+)$"),
        {
            "en": lambda m: f"Focus: {m.group(1)}",
            "ja": lambda m: f"フォーカス座標: {m.group(1)}",
            "zh-CN": lambda m: f"焦点坐标: {m.group(1)}",
        },
    ),
    (
        re.compile(r"^已建立 (\d+) 個遮罩$"),
        {
            "en": lambda m: f"{m.group(1)} Masks Created",
            "ja": lambda m: f"マスク {m.group(1)} 個作成済み",
            "zh-CN": lambda m: f"已建立 {m.group(1)} 个遮罩",
        },
    ),
    (
        re.compile(r"^已建立 (\d+) 句字幕$"),
        {
            "en": lambda m: f"{m.group(1)} Captions Ready",
            "ja": lambda m: f"字幕 {m.group(1)} 件作成済み",
            "zh-CN": lambda m: f"已建立 {m.group(1)} 句字幕",
        },
    ),
    (
        re.compile(r"^已儲存 (.+)$"),
        {
            "en": lambda m: f"Saved {m.group(1)}",
            "ja": lambda m: f"保存完了: {m.group(1)}",
            "zh-CN": lambda m: f"已保存 {m.group(1)}",
        },
    ),
]


def tr(text, lang=None):
    """
    將繁體中文介面字串翻譯為目標語系 (`zh-TW` / `en` / `ja` / `zh-CN`)。
    若無完全匹配，會嘗試子句替換或正則匹配，確保任何字串都能平滑轉換。
    """
    if text is None:
        return ""
    s = str(text)
    if not s.strip():
        return s

    target = lang or _CURRENT_LANG
    if target == "zh-TW":
        return s

    if target == "zh-CN":
        for pattern, handlers in _REGEX_RULES:
            m = pattern.match(s)
            if m and "zh-CN" in handlers:
                return handlers["zh-CN"](m)
        return to_simplified_chinese(s)

    # 1. 精確字典匹配
    entry = PHRASE_DICT.get(s)
    if entry and target in entry:
        return entry[target]

    # 2. 正則動態規則匹配
    for pattern, handlers in _REGEX_RULES:
        m = pattern.match(s)
        if m and target in handlers:
            return handlers[target](m)

    # 3. 保護摘要與常見複合狀態字串替換
    if "🔒" in s or "💧" in s:
        res = s
        sub_map_en = {
            "🔒 視窗排除: 僅自身穿透隱藏": "🔒 Exclusion: Self-Hide Only",
            "🔒 排除已開啟": "🔒 Exclusion Active",
            "景深模糊": "Blur",
            "馬賽克": "Mosaic",
            "隱私黑盒": "Dark Shield",
            "+自動敏感偵測": "+Auto Sensitive",
            "💧 浮水印: 未啟用": "💧 Watermark: Off",
            "💧 浮水印:": "💧 Watermark:",
            "角落簽名": "Corner Badge",
            "時間戳記": "Timestamp",
            "動態巡航標示": "Floating Attribution",
            "滿版標示網格": "Tiled Grid",
            "Logo 圖片": "Custom Logo",
        }
        sub_map_ja = {
            "🔒 視窗排除: 僅自身穿透隱藏": "🔒 除外保護: 自身の透過のみ",
            "🔒 排除已開啟": "🔒 除外保護: 有効",
            "景深模糊": "ぼかし",
            "馬賽克": "モザイク",
            "隱私黑盒": "ダークシールド",
            "+自動敏感偵測": "+機密自動検出",
            "💧 浮水印: 未啟用": "💧 透かし: 無効",
            "💧 浮水印:": "💧 透かし:",
            "角落簽名": "コーナー署名",
            "時間戳記": "タイムスタンプ",
            "動態巡航標示": "動的巡回透かし",
            "滿版標示網格": "全面グリッド",
            "Logo 圖片": "カスタムロゴ",
        }
        smap = sub_map_en if target == "en" else sub_map_ja
        for k, v in smap.items():
            res = res.replace(k, v)
        return res

    return s


def translate_menu(menu, lang=None):
    """遞迴翻譯 Tkinter Menu 的所有項目"""
    if menu is None:
        return
    target = lang or _CURRENT_LANG
    try:
        end_idx = menu.index("end")
    except Exception:
        return
    if end_idx is None:
        return

    if not hasattr(menu, "_i18n_menu_orig"):
        menu._i18n_menu_orig = {}

    for i in range(end_idx + 1):
        try:
            mtype = menu.type(i)
            if mtype in ("command", "cascade", "checkbutton", "radiobutton"):
                cur_lbl = menu.entrycget(i, "label")
                if i not in menu._i18n_menu_orig:
                    menu._i18n_menu_orig[i] = cur_lbl
                orig_lbl = menu._i18n_menu_orig[i]
                new_lbl = tr(orig_lbl, target)
                if cur_lbl != new_lbl:
                    menu.entryconfigure(i, label=new_lbl)
            if mtype == "cascade":
                sub_name = menu.entrycget(i, "menu")
                if sub_name:
                    sub_widget = menu.nametowidget(sub_name)
                    translate_menu(sub_widget, target)
        except Exception:
            pass


def translate_widget_tree(widget, lang=None):
    """
    遞迴遍歷 Tkinter 元件樹並即時套用多語系翻譯。
    首次遍歷時會自動記錄原始繁體中文文本 `_i18n_orig_text`，
    支援無限次在 `zh-TW` / `en` / `ja` / `zh-CN` 之間無損雙向即時切換。
    """
    if widget is None or getattr(widget, "_i18n_skip", False):
        return
    target = lang or _CURRENT_LANG

    # 1. 若為 Tk / Toplevel 視窗，處理視窗標題與選單
    if isinstance(widget, (tk.Tk, tk.Toplevel)):
        try:
            cur_title = widget.title()
            if not hasattr(widget, "_i18n_orig_title"):
                widget._i18n_orig_title = cur_title
            new_title = tr(widget._i18n_orig_title, target)
            if cur_title != new_title:
                widget.title(new_title)
        except Exception:
            pass

    # 2. 若為自訂 AuraButton / AuraCheck / AuraRadio (Canvas 子類別，具有 _text 與 _redraw 屬性)
    if hasattr(widget, "_text") and (hasattr(widget, "_redraw") or hasattr(widget, "_draw")):
        try:
            cur_t = getattr(widget, "_text", "")
            orig_t = getattr(widget, "_i18n_orig_text", None)
            if orig_t is None or (
                cur_t != orig_t
                and cur_t != tr(orig_t, "en")
                and cur_t != tr(orig_t, "ja")
                and cur_t != tr(orig_t, "zh-CN")
            ):
                widget._i18n_orig_text = cur_t
                orig_t = cur_t
            new_t = tr(orig_t, target)
            if cur_t != new_t:
                widget.config(text=new_t)
        except Exception:
            pass

    # 3. 若為 Combobox，翻譯下拉選單項目並保留目前選取索引
    elif isinstance(widget, ttk.Combobox):
        try:
            cur_vals = list(widget["values"] or [])
            if cur_vals:
                orig_vals = getattr(widget, "_i18n_orig_values", None)
                if orig_vals is None or len(orig_vals) != len(cur_vals):
                    widget._i18n_orig_values = list(cur_vals)
                    orig_vals = widget._i18n_orig_values
                idx = widget.current()
                new_vals = [tr(v, target) for v in orig_vals]
                if list(cur_vals) != new_vals:
                    widget["values"] = new_vals
                    if idx >= 0:
                        widget.current(idx)
        except Exception:
            pass

    # 4. 一般具備 text 屬性的標準元件 (Label, Button, Checkbutton, Radiobutton)
    else:
        try:
            if "text" in widget.keys():
                cur_t = str(widget.cget("text"))
                if cur_t:
                    orig_t = getattr(widget, "_i18n_orig_text", None)
                    # 若元件文字已被外部邏輯動態更新，同步更新 orig_t
                    if orig_t is None or (
                        cur_t != orig_t
                        and cur_t != tr(orig_t, "en")
                        and cur_t != tr(orig_t, "ja")
                        and cur_t != tr(orig_t, "zh-CN")
                    ):
                        widget._i18n_orig_text = cur_t
                        orig_t = cur_t
                    new_t = tr(orig_t, target)
                    if cur_t != new_t:
                        widget.configure(text=new_t)
        except Exception:
            pass

    # 5. 遞迴處理所有子元件
    try:
        for child in widget.winfo_children():
            translate_widget_tree(child, target)
    except Exception:
        pass
