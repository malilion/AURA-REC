#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VideoEditorWindow - Recordly / Screen Studio 風格專業影片剪輯工作站
- 舞台式畫布即時預覽 (Canvas Stage Preview)
- 擬真 macOS 視窗外框模型 (🔴🟡🟢 Window Mockup)
- 5 大頂級設計師背景主題 (極光霓虹、薄暮紫霞、深海琉璃、黑曜玄武、極簡純黑)
- 一鍵比例切換 (16:9 YouTube 橫式 / 9:16 Shorts 直式 / 1:1 方形 / 原始)
- 全寬膠卷故事板縮圖列 (Filmstrip Storyboard)
- 雙色高亮範圍時間軸 (In/Out 裁切標記與發光指針)
- 專業屬性檢查器側邊欄 (Inspector Panel)
- 0.5秒極速無損裁切、精準轉碼、倍速、音量增益、高畫質 GIF 導出
"""

import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from platform_utils import (
    UI,
    IS_MAC,
    get_ui_fonts,
    play_system_alert,
    copy_file,
    open_file_or_dir,
    apply_widget_style,
    load_settings,
    save_settings,
)
from aura_widgets import AuraButton, AuraCheck, AuraRadio, AuraScale
from video_editor import (
    VideoEditor,
    parse_aspect_choice,
    preview_video_filter,
)
from speech_to_text import (
    SubtitleTrack,
    SubtitleCue,
    SubtitleStyle,
    SpeechToTextEngine,
    SubtitleDialog,
    sec_to_short_time,
)
from window_exclusion_watermark import (
    WindowExclusionWatermarkDialog,
    render_watermark_png,
)
from i18n import (
    tr,
    get_language,
    get_language_badge,
    next_language,
    translate_widget_tree,
)


def sec_to_time_str(seconds):
    """秒數轉分:秒.毫秒 (例如 01:23.4)"""
    if seconds is None:
        return "00:00.0"
    seconds = max(0.0, float(seconds))
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:04.1f}"


def time_str_to_sec(time_str):
    """時間字串 (mm:ss.s 或 hh:mm:ss.s) 轉秒數"""
    if not time_str:
        return None
    time_str = str(time_str).strip()
    try:
        parts = time_str.split(":")
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except Exception:
        pass
    return None


THEMES = {
    "aurora": {
        "name": "極光",
        "icon": "🌌",
        "stage_bg": "#061a22",
        "frame_border": "#00f0ff",
        "frame_header": "#0c2630",
        "accent": "#00ff9d",
    },
    "sunset": {
        "name": "薄暮",
        "icon": "🌆",
        "stage_bg": "#1c0d24",
        "frame_border": "#ff2a6d",
        "frame_header": "#281335",
        "accent": "#f43f5e",
    },
    "ocean": {
        "name": "深海",
        "icon": "🌊",
        "stage_bg": "#081628",
        "frame_border": "#38bdf8",
        "frame_header": "#0f233d",
        "accent": "#38bdf8",
    },
    "obsidian": {
        "name": "黑曜",
        "icon": "🌑",
        "stage_bg": "#0d1117",
        "frame_border": "#30363d",
        "frame_header": "#161b22",
        "accent": "#58a6ff",
    },
    "studio": {
        "name": "純黑",
        "icon": "🎬",
        "stage_bg": "#000000",
        "frame_border": "#222222",
        "frame_header": "#111111",
        "accent": "#ffffff",
    },
}

RATIO_CONFIGS = {
    "16:9": {
        "label": "16:9",
        "sub": "橫式桌面",
        "aspect": "16:9",
        "anchor": "center",
        "preview_w": 480,
        "preview_h": 270,
    },
    "9:16": {
        "label": "9:16",
        "sub": "直式短影音",
        "aspect": "9:16",
        "anchor": "fit",
        "preview_w": 180,
        "preview_h": 320,
    },
    "1:1": {
        "label": "1:1",
        "sub": "方形社群",
        "aspect": "1:1",
        "anchor": "center",
        "preview_w": 280,
        "preview_h": 280,
    },
    "original": {
        "label": "原始",
        "sub": "原生無裁切",
        "aspect": "original",
        "anchor": "center",
        "preview_w": 480,
        "preview_h": 270,
    },
}


class VideoEditorWindow:
    def __init__(self, parent, video_path=None, on_close=None):
        self.parent = parent
        self._after_close = on_close
        self.editor = VideoEditor()

        self.window = tk.Toplevel(parent)
        self.window.title("剪輯工作站 — AURA REC")
        self.window.geometry("1060x820")
        self.window.minsize(960, 720)
        self.window.configure(bg=UI["bg"])
        self.fonts = get_ui_fonts()
        apply_widget_style(ttk.Style(self.window), self.fonts)

        # 狀態
        self.video_info = None
        self.current_file = str(video_path) if video_path else None
        self.total_duration = 0.0
        self.current_time = 0.0
        self.start_sec = 0.0
        self.end_sec = 0.0

        # Recordly 舞台風格狀態
        self.current_theme = "aurora"
        self.current_ratio = "original"
        self.show_mockup_header = tk.BooleanVar(value=True)

        # 智慧運鏡與自動縮放 (Auto Zoom) 狀態
        self.zoom_mode_var = tk.StringVar(value="關閉 (1.0x)")
        self.zoom_level_var = tk.StringVar(value="1.5x (推薦)")
        self.zoom_pos_var = tk.StringVar(value="畫面中心")
        self.zoom_focus_x = 0.5
        self.zoom_focus_y = 0.5
        self.preview_zoom_var = tk.BooleanVar(value=False)

        # 預覽執行緒與影像
        self.preview_image = None
        self._preview_lock = threading.Lock()
        self._preview_thread = None
        self._preview_pending = None
        self._playing_process = None
        self._scrub_cache = {}

        # 膠卷時間軸即時刷屏與拖曳握把 (Scrubbing / Skimming & In/Out Handles)
        self._skimmer_x = None
        self._skimmer_time = None
        self._hover_target = None
        self._drag_target = None
        self.filmstrip_thumbs = []

        # 聲音音量波形圖 (Audio Waveform Track)
        self.audio_waveform = []
        self._waveform_loading = False

        # 隱私模糊與局部馬賽克 (Blur & Mosaic Masks)
        self.blur_masks = []
        self._mask_mode = None
        self._mask_drag_start = None
        self._mask_drag_curr = None
        self._mask_apply_scope = tk.StringVar(value="full")
        self._mask_counter = 1
        self._mask_del_targets = {}

        # AI 離線語音識別與智慧字幕軌 (Speech-to-Text & Subtitles)
        self.subtitles = SubtitleTrack()
        self.stt_engine = SpeechToTextEngine()
        self.preview_subtitles_var = tk.BooleanVar(value=True)
        self.soft_subtitles_var = tk.BooleanVar(value=True)
        self.export_srt_var = tk.BooleanVar(value=True)
        self._subtitle_dialog = None

        # 智慧浮水印版權保護 (Watermark Protection)
        saved_settings = load_settings()
        saved_wm = saved_settings.get("watermark_config")
        self.watermark_config = dict(saved_wm) if isinstance(saved_wm, dict) else {
            "enabled": False,
            "mode": "none",
            "position": "bottom-right",
            "style": "aurora",
            "opacity": "medium",
            "text": "© 極光錄影 Aura · 請勿外流",
            "logo_path": "",
            "margin": 24,
        }
        self.watermark_enabled_var = tk.BooleanVar(value=bool(self.watermark_config.get("enabled", False)))
        self._preview_wm_photo = None

        self._build_ui()
        self._bind_shortcuts()

        if self.current_file and os.path.exists(self.current_file):
            self.load_video(self.current_file)
        else:
            self.select_video_file()

        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

    def _tool_button(self, parent, text, command):
        return AuraButton(parent, text=text, command=command, style="Ghost.TButton")

    def _build_ui(self):
        self.main_frame = tk.Frame(self.window, bg=UI["bg"])
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        # 1. 頂部工具列 (Top Header)
        top_bar = tk.Frame(self.main_frame, bg=UI["bg"])
        top_bar.pack(fill=tk.X, pady=(0, 10))

        brand_frame = tk.Frame(top_bar, bg=UI["bg"])
        brand_frame.pack(side=tk.LEFT)

        tk.Label(
            brand_frame, text="AURA", font=self.fonts["title"], fg=UI["white"], bg=UI["bg"]
        ).pack(side=tk.LEFT)
        tk.Label(
            brand_frame, text="STUDIO", font=self.fonts["badge"], fg=UI["blue"], bg="#10262C",
            padx=6, pady=2
        ).pack(side=tk.LEFT, padx=(6, 12))

        file_meta_col = tk.Frame(top_bar, bg=UI["bg"])
        file_meta_col.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_filename = tk.Label(
            file_meta_col, text="未載入影片", font=self.fonts["bold"], fg=UI["white"], bg=UI["bg"], anchor="w"
        )
        self.lbl_filename.pack(anchor="w")
        self.lbl_meta = tk.Label(
            file_meta_col, text="點擊右上方「開啟影片」開始編輯", font=self.fonts["badge"], fg=UI["muted"], bg=UI["bg"], anchor="w"
        )
        self.lbl_meta.pack(anchor="w", pady=(1, 0))

        # 頂部操作按鈕群
        top_actions = tk.Frame(top_bar, bg=UI["bg"])
        top_actions.pack(side=tk.RIGHT)

        self.lang_btn = self._tool_button(top_actions, get_language_badge(get_language()), self._cycle_editor_language)
        self.lang_btn._i18n_skip = True
        self.lang_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._tool_button(top_actions, "開啟影片…", self.select_video_file).pack(side=tk.LEFT, padx=(0, 8))
        self._tool_button(top_actions, "💬 智慧字幕…", self._open_subtitle_manager).pack(side=tk.LEFT, padx=(0, 8))
        self._tool_button(top_actions, "💧 浮水印保護…", self._open_watermark_dialog).pack(side=tk.LEFT, padx=(0, 8))
        self.btn_play_seg = AuraButton(
            top_actions, text="播放 [Space]", style="Play.TButton", command=self.preview_play_selection
        )
        self.btn_play_seg.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_export = AuraButton(
            top_actions, text=self._export_btn_label(), style="Primary.TButton", command=self.perform_export
        )
        self.btn_export.pack(side=tk.LEFT)

        # 2. 雙欄工作區 (Workspace: Left Canvas + Right Inspector)
        workspace = tk.Frame(self.main_frame, bg=UI["bg"])
        workspace.pack(fill=tk.BOTH, expand=True)

        # === 左側欄：Recordly 舞台預覽與時間軸 (70% 寬度) ===
        left_col = tk.Frame(workspace, bg=UI["bg"])
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        # (A) 舞台畫布容器 (Stage Canvas Stage)
        theme = THEMES[self.current_theme]
        self.stage_container = tk.Frame(
            left_col,
            bg=theme["stage_bg"],
            highlightbackground=theme["frame_border"],
            highlightthickness=1,
            height=370,
        )
        self.stage_container.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.stage_container.pack_propagate(False)

        # 擬真 macOS 視窗模型 (Mockup Window Frame)
        self.mockup_frame = tk.Frame(
            self.stage_container,
            bg=theme["frame_header"],
            highlightbackground=theme["frame_border"],
            highlightthickness=1,
        )
        self.mockup_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # 視窗頂部標題列 (紅黃綠三圓點 🔴🟡🟢)
        self.mockup_header = tk.Frame(self.mockup_frame, bg=theme["frame_header"], height=24)
        self.mockup_header.pack(fill=tk.X)
        self.mockup_header.pack_propagate(False)

        self.mockup_dots_canvas = tk.Canvas(
            self.mockup_header, width=48, height=14, bg=theme["frame_header"], highlightthickness=0, bd=0
        )
        self.mockup_dots_canvas.pack(side=tk.LEFT, padx=(8, 4), pady=5)
        self._draw_traffic_dots()

        self.mockup_title_lbl = tk.Label(
            self.mockup_header, text="AURA STAGE", font=self.fonts["badge"], fg=UI["muted"], bg=theme["frame_header"]
        )
        self.mockup_title_lbl.pack(side=tk.LEFT, padx=4)

        # 影片預覽畫面本體 (支援畫布點擊/拖曳設定運鏡焦點與十字發光準星)
        self.preview_canvas = tk.Canvas(
            self.mockup_frame,
            bg=UI["preview"],
            highlightthickness=0,
            bd=0,
            cursor="crosshair",
        )
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)
        self.preview_canvas.bind("<Button-1>", self._on_canvas_click)
        self.preview_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        # (B) 數位碼錶與選取範圍資訊
        time_row = tk.Frame(left_col, bg=UI["bg"])
        time_row.pack(fill=tk.X, pady=(2, 4))

        self.lbl_cur_time = tk.Label(
            time_row, text="00:00.0 / 00:00.0", font=self.fonts["bold"], fg=UI["white"], bg=UI["bg"]
        )
        self.lbl_cur_time.pack(side=tk.LEFT)

        self.lbl_selected_len = tk.Label(
            time_row, text="選取長度 00:00.0", font=self.fonts["badge"], fg=UI["ok"], bg=UI["card"], padx=8, pady=2
        )
        self.lbl_selected_len.pack(side=tk.RIGHT)

        # (C) 故事板膠卷縮圖預覽列與即時刷屏時間軸 (Filmstrip Timeline & Scrubber)
        self.filmstrip_frame = tk.Frame(left_col, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1, height=76)
        self.filmstrip_frame.pack(fill=tk.X, pady=(0, 4))
        self.filmstrip_frame.pack_propagate(False)

        self.filmstrip_canvas = tk.Canvas(
            self.filmstrip_frame,
            bg=UI["card"],
            highlightthickness=0,
            cursor="crosshair",
            width=800,
            height=76,
        )
        self.filmstrip_canvas.pack(fill=tk.BOTH, expand=True)
        self.filmstrip_canvas.bind("<Configure>", lambda _e: self._redraw_filmstrip())
        self.filmstrip_canvas.bind("<Motion>", self._on_filmstrip_motion)
        self.filmstrip_canvas.bind("<Leave>", self._on_filmstrip_leave)
        self.filmstrip_canvas.bind("<Button-1>", self._on_filmstrip_press)
        self.filmstrip_canvas.bind("<B1-Motion>", self._on_filmstrip_drag)
        self.filmstrip_canvas.bind("<ButtonRelease-1>", self._on_filmstrip_release)

        # (C.2) 聲音音量波形圖時間軸 (Audio Waveform Track)
        self.waveform_frame = tk.Frame(left_col, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1, height=44)
        self.waveform_frame.pack(fill=tk.X, pady=(0, 4))
        self.waveform_frame.pack_propagate(False)

        self.waveform_canvas = tk.Canvas(
            self.waveform_frame,
            bg=UI["card"],
            highlightthickness=0,
            cursor="crosshair",
            width=800,
            height=44,
        )
        self.waveform_canvas.pack(fill=tk.BOTH, expand=True)
        self.waveform_canvas.bind("<Configure>", lambda _e: self._redraw_waveform())
        self.waveform_canvas.bind("<Motion>", self._on_waveform_motion)
        self.waveform_canvas.bind("<Leave>", self._on_waveform_leave)
        self.waveform_canvas.bind("<Button-1>", self._on_waveform_press)
        self.waveform_canvas.bind("<B1-Motion>", self._on_waveform_drag)

        # (C.3) 智慧字幕軌時間軸 (Subtitle Track)
        self.subtitle_frame = tk.Frame(left_col, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1, height=34)
        self.subtitle_frame.pack(fill=tk.X, pady=(0, 4))
        self.subtitle_frame.pack_propagate(False)

        self.subtitle_canvas = tk.Canvas(
            self.subtitle_frame,
            bg=UI["card"],
            highlightthickness=0,
            cursor="hand2",
            width=800,
            height=34,
        )
        self.subtitle_canvas.pack(fill=tk.BOTH, expand=True)
        self.subtitle_canvas.bind("<Configure>", lambda _e: self._redraw_subtitles())
        self.subtitle_canvas.bind("<Button-1>", self._on_subtitle_canvas_click)

        # (D) 時間軸滑桿 (Aura Timeline Scale)
        self.time_slider = AuraScale(
            left_col, from_=0.0, to=100.0, command=self._on_slider_move
        )
        self.time_slider.pack(fill=tk.X, pady=(0, 6))

        # (E) 傳輸微調與範圍按鈕列 (Transport Controls)
        ctrl_row = tk.Frame(left_col, bg=UI["bg"])
        ctrl_row.pack(fill=tk.X)

        self._tool_button(ctrl_row, "−1 秒", lambda: self._nudge_time(-1.0)).pack(side=tk.LEFT, padx=(0, 4))
        self._tool_button(ctrl_row, "−0.1 秒", lambda: self._nudge_time(-0.1)).pack(side=tk.LEFT, padx=2)

        self.btn_in_quick = AuraButton(ctrl_row, text="[ 設為起點 (I)", style="Ghost.TButton", command=self.set_in_point)
        self.btn_in_quick.pack(side=tk.LEFT, padx=6)
        self.btn_out_quick = AuraButton(ctrl_row, text="設為終點 (O) ]", style="Ghost.TButton", command=self.set_out_point)
        self.btn_out_quick.pack(side=tk.LEFT, padx=2)

        self._tool_button(ctrl_row, "+0.1 秒", lambda: self._nudge_time(0.1)).pack(side=tk.LEFT, padx=2)
        self._tool_button(ctrl_row, "+1 秒", lambda: self._nudge_time(1.0)).pack(side=tk.LEFT, padx=4)

        hint_lbl = tk.Label(
            ctrl_row, text="Space 播放 · I/O 設範圍 · ←/→ 微調 · ⌘E 匯出",
            font=self.fonts["badge"], fg=UI["muted"], bg=UI["bg"]
        )
        hint_lbl.pack(side=tk.RIGHT)

        # === 右側欄：Recordly 屬性檢查器 Inspector (310px 寬度) ===
        right_col = tk.Frame(workspace, bg=UI["bg"], width=310)
        right_col.pack(side=tk.RIGHT, fill=tk.Y)
        right_col.pack_propagate(False)

        # 卡片 1：【畫布與比例 (Canvas & Ratio)】
        style_card = self._inspector_card(right_col, "畫布與視覺風格")

        # (1-1) 比例快捷切換
        tk.Label(style_card, text="畫面比例", font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"]).pack(anchor="w", padx=10, pady=(4, 2))
        ratio_btn_row = tk.Frame(style_card, bg=UI["card"])
        ratio_btn_row.pack(fill=tk.X, padx=10, pady=(0, 6))

        self.ratio_buttons = {}
        for r_key, r_info in RATIO_CONFIGS.items():
            btn = tk.Button(
                ratio_btn_row,
                text=r_info["label"],
                font=self.fonts["badge"],
                bg=UI["field"],
                fg=UI["text"],
                activebackground=UI["hover"],
                activeforeground=UI["white"],
                relief=tk.FLAT,
                bd=0,
                cursor="hand2",
                command=lambda k=r_key: self._set_ratio(k),
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
            self.ratio_buttons[r_key] = btn

        # (1-2) 背景桌布主題
        tk.Label(style_card, text="背景主題", font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"]).pack(anchor="w", padx=10, pady=(2, 2))
        theme_btn_row = tk.Frame(style_card, bg=UI["card"])
        theme_btn_row.pack(fill=tk.X, padx=10, pady=(0, 6))

        self.theme_buttons = {}
        for t_key, t_info in THEMES.items():
            t_btn = tk.Button(
                theme_btn_row,
                text=f"{t_info['icon']} {t_info['name']}",
                font=self.fonts["badge"],
                bg=UI["field"],
                fg=UI["text"],
                relief=tk.FLAT,
                bd=0,
                cursor="hand2",
                command=lambda k=t_key: self._set_theme(k),
            )
            t_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=1)
            self.theme_buttons[t_key] = t_btn

        # (1-3) 視窗外框開關
        AuraCheck(
            style_card,
            text="顯示 macOS 視窗外框 (🔴🟡🟢)",
            variable=self.show_mockup_header,
            command=self._toggle_mockup_header,
        ).pack(anchor="w", padx=10, pady=(2, 8))

        # 卡片 2：【智慧運鏡與自動縮放 (Auto Zoom & Pan)】
        zoom_card = self._inspector_card(right_col, "智慧運鏡與縮放 (Auto Zoom)")

        # 運鏡模式
        tk.Label(zoom_card, text="運鏡模式", font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"]).pack(anchor="w", padx=10, pady=(2, 2))
        self.zoom_mode_combo = ttk.Combobox(
            zoom_card, style="App.TCombobox", state="readonly", textvariable=self.zoom_mode_var,
            values=["關閉 (1.0x)", "平滑推進與退回 (In & Out 推薦)", "平滑推進特寫 (Smooth In)", "全程特寫 (Static Zoom)"]
        )
        self.zoom_mode_combo.pack(fill=tk.X, padx=10, pady=(0, 4))
        self.zoom_mode_combo.bind("<<ComboboxSelected>>", self._on_zoom_mode_or_level_changed)

        zoom_sub_grid = tk.Frame(zoom_card, bg=UI["card"])
        zoom_sub_grid.pack(fill=tk.X, padx=10, pady=(0, 4))
        zoom_sub_grid.columnconfigure(1, weight=1)
        zoom_sub_grid.columnconfigure(3, weight=1)

        # 縮放倍率
        tk.Label(zoom_sub_grid, text="特寫倍率", font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"]).grid(row=0, column=0, sticky="w", padx=(0, 4), pady=2)
        self.zoom_level_combo = ttk.Combobox(
            zoom_sub_grid, style="App.TCombobox", state="readonly", width=11, textvariable=self.zoom_level_var,
            values=["1.5x (推薦)", "1.25x (微距)", "1.8x (深層)", "2.0x (高倍)"]
        )
        self.zoom_level_combo.grid(row=0, column=1, sticky="ew", pady=2)
        self.zoom_level_combo.bind("<<ComboboxSelected>>", self._on_zoom_mode_or_level_changed)

        # 焦點位置
        tk.Label(zoom_sub_grid, text="焦點", font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"]).grid(row=0, column=2, sticky="w", padx=(6, 4), pady=2)
        self.zoom_pos_combo = ttk.Combobox(
            zoom_sub_grid, style="App.TCombobox", state="readonly", width=11, textvariable=self.zoom_pos_var,
            values=["畫面中心", "左上角", "右上角", "左下角", "右下角", "上方中", "下方中", "🎯 自訂 / 點擊畫面"]
        )
        self.zoom_pos_combo.grid(row=0, column=3, sticky="ew", pady=2)
        self.zoom_pos_combo.bind("<<ComboboxSelected>>", self._on_zoom_pos_changed)

        # 焦點座標與智慧偵測按鈕
        coord_row = tk.Frame(zoom_card, bg=UI["card"])
        coord_row.pack(fill=tk.X, padx=10, pady=(2, 4))
        self.lbl_zoom_coords = tk.Label(
            coord_row, text="焦點座標: X 50% · Y 50%", font=self.fonts["badge"], fg=UI["blue"], bg=UI["card"]
        )
        self.lbl_zoom_coords.pack(side=tk.LEFT)

        self.btn_detect_focus = self._tool_button(coord_row, "🎯 智慧偵測焦點", self._detect_action_focus)
        self.btn_detect_focus.pack(side=tk.RIGHT)

        # 即時預覽特寫開關
        AuraCheck(
            zoom_card,
            text="預覽畫面即時顯示特寫效果",
            variable=self.preview_zoom_var,
            command=self._on_zoom_mode_or_level_changed,
        ).pack(anchor="w", padx=10, pady=(2, 6))

        # 卡片 3：【隱私模糊與馬賽克 (Privacy Mask)】
        mask_card = self._inspector_card(right_col, "隱私遮罩 (Blur & Mosaic)")

        # 模式按鈕列
        mask_btn_row = tk.Frame(mask_card, bg=UI["card"])
        mask_btn_row.pack(fill=tk.X, padx=10, pady=(2, 4))

        self.btn_mask_blur = tk.Button(
            mask_btn_row,
            text="＋ 模糊 (Blur)",
            font=self.fonts["badge"],
            bg=UI["field"],
            fg=UI["text"],
            activebackground=UI["hover"],
            activeforeground=UI["white"],
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            command=lambda: self._toggle_mask_mode("blur"),
        )
        self.btn_mask_blur.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2), ipady=3)

        self.btn_mask_mosaic = tk.Button(
            mask_btn_row,
            text="＋ 馬賽克 (Mosaic)",
            font=self.fonts["badge"],
            bg=UI["field"],
            fg=UI["text"],
            activebackground=UI["hover"],
            activeforeground=UI["white"],
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            command=lambda: self._toggle_mask_mode("mosaic"),
        )
        self.btn_mask_mosaic.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0), ipady=3)

        # 提示標籤
        self.lbl_mask_hint = tk.Label(
            mask_card,
            text="點選上方按鈕後，在預覽畫面上拖曳框選",
            font=self.fonts["badge"],
            fg=UI["muted"],
            bg=UI["card"],
            anchor="w",
            wraplength=280,
            justify=tk.LEFT,
        )
        self.lbl_mask_hint.pack(fill=tk.X, padx=10, pady=(0, 4))

        # 套用時段設定
        scope_row = tk.Frame(mask_card, bg=UI["card"])
        scope_row.pack(fill=tk.X, padx=10, pady=(0, 4))
        tk.Label(scope_row, text="套用:", font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"]).pack(side=tk.LEFT, padx=(0, 4))
        AuraRadio(scope_row, text="全片", variable=self._mask_apply_scope, value="full").pack(side=tk.LEFT, padx=(0, 6))
        AuraRadio(scope_row, text="僅選取區段", variable=self._mask_apply_scope, value="selection").pack(side=tk.LEFT)

        # 遮罩計數與清空列
        cnt_row = tk.Frame(mask_card, bg=UI["card"])
        cnt_row.pack(fill=tk.X, padx=10, pady=(2, 4))
        self.lbl_mask_count = tk.Label(
            cnt_row, text="已建立 0 個遮罩", font=self.fonts["badge"], fg=UI["white"], bg=UI["card"]
        )
        self.lbl_mask_count.pack(side=tk.LEFT)
        self.btn_clear_masks = tk.Button(
            cnt_row,
            text="全部清空",
            font=self.fonts["badge"],
            bg=UI["field"],
            fg=UI["muted"],
            activebackground=UI["hover"],
            activeforeground=UI["red"],
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            state=tk.DISABLED,
            command=self._clear_all_masks,
        )
        self.btn_clear_masks.pack(side=tk.RIGHT)

        # 遮罩列表容器
        self.mask_list_frame = tk.Frame(mask_card, bg=UI["card"])
        self.mask_list_frame.pack(fill=tk.X, padx=10, pady=(0, 6))

        # 卡片：【AI 智慧字幕軌 (AI Captions & Subtitles)】
        sub_card = self._inspector_card(right_col, "智慧字幕 (AI Captions)")

        sub_top_row = tk.Frame(sub_card, bg=UI["card"])
        sub_top_row.pack(fill=tk.X, padx=10, pady=(2, 4))
        self.lbl_subtitle_status = tk.Label(
            sub_top_row, text="尚未建立字幕", font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"]
        )
        self.lbl_subtitle_status.pack(side=tk.LEFT)

        self.btn_gen_subs = self._tool_button(sub_top_row, "✨ AI 產生", self._open_subtitle_manager)
        self.btn_gen_subs.pack(side=tk.RIGHT)

        sub_action_row = tk.Frame(sub_card, bg=UI["card"])
        sub_action_row.pack(fill=tk.X, padx=10, pady=(0, 4))

        self._tool_button(sub_action_row, "📋 編輯", self._open_subtitle_manager).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        self._tool_button(sub_action_row, "＋ 加句", self._add_cue_at_current_time).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self._tool_button(sub_action_row, "📥 匯入", self._import_subtitles_file).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self._tool_button(sub_action_row, "📤 匯出", self._export_subtitles_file).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))

        AuraCheck(
            sub_card,
            text="預覽畫面即時顯示字幕",
            variable=self.preview_subtitles_var,
            command=self._redraw_preview_canvas,
        ).pack(anchor="w", padx=10, pady=(2, 6))

        # 卡片 4：【剪輯範圍數值 (Trim Points)】
        trim_card = self._inspector_card(right_col, "精準剪輯範圍")
        time_edit_frame = tk.Frame(trim_card, bg=UI["card"])
        time_edit_frame.pack(fill=tk.X, padx=10, pady=(4, 8))

        def create_time_input(parent, col, label_text):
            f = tk.Frame(parent, bg=UI["card"])
            f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
            tk.Label(f, text=label_text, font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"]).pack(anchor="w")
            ent = tk.Entry(
                f, font=self.fonts["badge"], width=10, bg=UI["field"], fg=UI["text"],
                insertbackground=UI["blue"], relief=tk.FLAT, bd=0,
                highlightthickness=1, highlightbackground=UI["edge"], highlightcolor=UI["blue"],
            )
            ent.insert(0, "00:00.0")
            ent.pack(fill=tk.X, pady=(2, 0), ipady=3)
            ent.bind("<FocusOut>", lambda e: self._update_times_from_entries())
            ent.bind("<Return>", lambda e: self._update_times_from_entries())
            return ent

        self.ent_start = create_time_input(time_edit_frame, 0, "起點 (In)")
        self.ent_end = create_time_input(time_edit_frame, 1, "終點 (Out)")

        # 卡片 3：【匯出規格與選項 (Export Settings)】
        export_card = self._inspector_card(right_col, "匯出規格")

        self.export_mode_var = tk.StringVar(value="lossless")
        self.mute_var = tk.BooleanVar(value=False)

        modes = [
            ("⚡ 極速智慧無損 (Smart Cut 0.5s)", "lossless"),
            ("🎨 精準重編碼（比例/速度）", "precise"),
            ("🎞️ 高清 GIF 動態圖", "gif"),
            ("🎵 提取音訊 (MP3)", "audio"),
        ]
        for text, value in modes:
            AuraRadio(
                export_card, text=text, variable=self.export_mode_var, value=value
            ).pack(anchor="w", padx=10, pady=1)

        opt_grid = tk.Frame(export_card, bg=UI["card"])
        opt_grid.pack(fill=tk.X, padx=10, pady=(6, 8))

        def make_combo_row(parent, row, label, values, default_idx=0):
            tk.Label(parent, text=label, font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"]).grid(
                row=row, column=0, sticky="w", pady=3
            )
            cb = ttk.Combobox(parent, style="App.TCombobox", state="readonly", width=14, values=values)
            cb.current(default_idx)
            cb.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
            return cb

        self.speed_combo = make_combo_row(opt_grid, 0, "播放速度", ["1.0x (原速)", "1.5x (推薦)", "2.0x (快進)", "0.5x (慢速)"], 0)
        self.volume_combo = make_combo_row(opt_grid, 1, "音量增益", ["100% 原始", "150% 增強", "200% 放大", "50% 降低"], 0)
        self.scale_combo = make_combo_row(opt_grid, 2, "輸出畫質", ["原始畫質", "1080p 適合分享", "720p 節省空間"], 0)

        AuraCheck(export_card, text="靜音輸出", variable=self.mute_var).pack(anchor="w", padx=10, pady=(2, 2))
        AuraCheck(export_card, text="封裝軟字幕軌至 MP4/MOV", variable=self.soft_subtitles_var).pack(anchor="w", padx=10, pady=(0, 2))
        AuraCheck(export_card, text="同時匯出同名 .srt 字幕檔", variable=self.export_srt_var).pack(anchor="w", padx=10, pady=(0, 2))
        AuraCheck(
            export_card,
            text="匯出時燒錄防盜浮水印",
            variable=self.watermark_enabled_var,
            command=self._on_editor_watermark_toggle,
        ).pack(anchor="w", padx=10, pady=(0, 6))

        # 側邊欄底部大按鈕
        self.btn_export_side = AuraButton(
            right_col, text="⚡ 一鍵匯出影片", style="Primary.TButton", command=self.perform_export
        )
        self.btn_export_side.pack(fill=tk.X, pady=(6, 0))

        # 初始化選中外觀
        self._update_ratio_buttons_ui()
        self._update_theme_buttons_ui()
        self._update_mockup_geometry()
        translate_widget_tree(self.window, get_language())

    def _cycle_editor_language(self):
        from i18n import set_language
        new_lang = next_language(get_language())
        set_language(new_lang)
        save_settings({"language": new_lang})
        if hasattr(self, "lang_btn"):
            self.lang_btn.config(text=get_language_badge(new_lang))
        translate_widget_tree(self.window, new_lang)
        self._update_selection_length_label()
        self._update_focus_coord_label()

    def _inspector_card(self, parent, title):
        card = tk.Frame(parent, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 8))
        tk.Label(card, text=title, font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]).pack(
            anchor="w", padx=10, pady=(8, 4)
        )
        return card

    def _draw_traffic_dots(self):
        c = self.mockup_dots_canvas
        c.delete("all")
        dots = [("#ff5f56", 7), ("#ffbd2e", 21), ("#27c93f", 35)]
        for color, x in dots:
            c.create_oval(x - 4, 3, x + 4, 11, fill=color, outline="")

    def _set_ratio(self, ratio_key):
        if ratio_key not in RATIO_CONFIGS:
            return
        self.current_ratio = ratio_key
        self._update_ratio_buttons_ui()
        self._update_mockup_geometry()
        self._request_preview(self.current_time)

    def _update_ratio_buttons_ui(self):
        for k, btn in self.ratio_buttons.items():
            if k == self.current_ratio:
                btn.config(bg=UI["blue"], fg=UI["ink"])
            else:
                btn.config(bg=UI["field"], fg=UI["text"])

    def _set_theme(self, theme_key):
        if theme_key not in THEMES:
            return
        self.current_theme = theme_key
        theme = THEMES[theme_key]

        # 更新舞台與視窗模型顏色
        self.stage_container.config(bg=theme["stage_bg"], highlightbackground=theme["frame_border"])
        self.mockup_frame.config(bg=theme["frame_header"], highlightbackground=theme["frame_border"])
        self.mockup_header.config(bg=theme["frame_header"])
        self.mockup_dots_canvas.config(bg=theme["frame_header"])
        self.mockup_title_lbl.config(bg=theme["frame_header"])
        self._draw_traffic_dots()

        self._update_theme_buttons_ui()

    def _update_theme_buttons_ui(self):
        for k, btn in self.theme_buttons.items():
            if k == self.current_theme:
                btn.config(bg=THEMES[k]["frame_border"], fg=UI["ink"])
            else:
                btn.config(bg=UI["field"], fg=UI["text"])

    def _toggle_mockup_header(self):
        if self.show_mockup_header.get():
            self.mockup_header.pack(fill=tk.X, before=self.preview_canvas)
        else:
            self.mockup_header.pack_forget()

    def _update_mockup_geometry(self):
        cfg = RATIO_CONFIGS[self.current_ratio]
        w, h = cfg["preview_w"], cfg["preview_h"]
        header_h = 24 if self.show_mockup_header.get() else 0
        self.mockup_frame.config(width=w, height=h + header_h)

    def _export_btn_label(self):
        return "⚡ 匯出 (⌘E)" if IS_MAC else "⚡ 匯出 (Ctrl+E)"

    def _bind_shortcuts(self):
        w = self.window

        def _in_entry(event):
            return isinstance(event.widget, (tk.Entry, ttk.Entry))

        def on_space(event):
            if not _in_entry(event):
                self.preview_play_selection()
                return "break"

        def on_in_key(event):
            if not _in_entry(event):
                self.set_in_point()
                return "break"

        def on_out_key(event):
            if not _in_entry(event):
                self.set_out_point()
                return "break"

        def on_left(event):
            if not _in_entry(event):
                self._nudge_time(-0.1)
                return "break"

        def on_right(event):
            if not _in_entry(event):
                self._nudge_time(0.1)
                return "break"

        def on_shift_left(event):
            if not _in_entry(event):
                self._nudge_time(-1.0)
                return "break"

        def on_shift_right(event):
            if not _in_entry(event):
                self._nudge_time(1.0)
                return "break"

        def on_export(event):
            self.perform_export()
            return "break"

        def on_escape(event):
            if self._playing_process and self._playing_process.poll() is None:
                self._playing_process.terminate()
                self._playing_process = None
                self.btn_play_seg.config(text="播放 [Space]", style="Play.TButton")
                return "break"

        w.bind("<space>", on_space)
        w.bind("<i>", on_in_key)
        w.bind("<I>", on_in_key)
        w.bind("<o>", on_out_key)
        w.bind("<O>", on_out_key)
        w.bind("<Left>", on_left)
        w.bind("<Right>", on_right)
        w.bind("<Shift-Left>", on_shift_left)
        w.bind("<Shift-Right>", on_shift_right)
        w.bind("<j>", on_shift_left)
        w.bind("<J>", on_shift_left)
        w.bind("<k>", on_space)
        w.bind("<K>", on_space)
        w.bind("<l>", on_shift_right)
        w.bind("<L>", on_shift_right)
        w.bind("<Command-e>", on_export)
        w.bind("<Control-e>", on_export)
        w.bind("<Escape>", on_escape)

    def select_video_file(self):
        file_path = filedialog.askopenfilename(
            title="選擇要剪輯的影片",
            filetypes=[("Video files", "*.mp4 *.mov *.mkv *.webm"), ("All files", "*.*")]
        )
        if file_path:
            self.load_video(file_path)

    def load_video(self, file_path):
        self.current_file = file_path
        info = self.editor.get_video_info(file_path)
        if not info or info["duration"] <= 0:
            messagebox.showerror("載入失敗", "無法讀取該影片檔案或時長為 0。")
            return

        self.video_info = info
        self.total_duration = info["duration"]
        self.current_time = 0.0
        self.start_sec = 0.0
        self.end_sec = self.total_duration

        self.lbl_filename.config(text=info["file_name"])
        track_count = info.get("audio_track_count", 1 if info["has_audio"] else 0)
        if track_count > 1:
            titles = [t.get("title", f"Track {i+1}") for i, t in enumerate(info.get("audio_tracks", []))]
            audio = f"獨立多音軌 ({track_count} 軌: {' / '.join(titles)})"
        elif info["has_audio"]:
            audio = "單音軌 (主音效)"
        else:
            audio = "無音訊"
        meta_str = (
            f"{info['width']}×{info['height']}  ·  {sec_to_time_str(self.total_duration)}"
            f"  ·  {info['size_mb']} MB  ·  {audio}"
        )
        self.lbl_meta.config(text=meta_str)

        self.time_slider.config(from_=0.0, to=self.total_duration)
        self.time_slider.set(0.0)
        self.time_slider.set_range(self.start_sec, self.end_sec)

        self.ent_start.delete(0, tk.END)
        self.ent_start.insert(0, sec_to_time_str(0.0))

        self.ent_end.delete(0, tk.END)
        self.ent_end.insert(0, sec_to_time_str(self.total_duration))

        self._update_selection_length_label()
        self._scrub_cache.clear()
        self.filmstrip_thumbs = []
        self.audio_waveform = []
        self.blur_masks = []
        self._mask_mode = None
        self._mask_drag_start = None
        self._mask_drag_curr = None
        self._update_mask_ui()
        # 檢查是否有同目錄伴隨的 .srt 字幕檔
        companion_srt = Path(file_path).with_suffix(".srt")
        if companion_srt.exists():
            try:
                self.subtitles = SubtitleTrack.from_srt(str(companion_srt))
            except Exception:
                self.subtitles = SubtitleTrack()
        else:
            self.subtitles = SubtitleTrack()
        self._update_subtitle_ui()
        self._redraw_subtitles()

        self._redraw_filmstrip()
        self._request_preview(0.0)
        self._load_filmstrip()
        self._load_waveform()

    def _jump_to_time(self, sec):
        sec = max(0.0, min(self.total_duration, float(sec)))
        self.current_time = sec
        self.time_slider.set(sec)
        self.lbl_cur_time.config(
            text=f"{sec_to_time_str(sec)} / {sec_to_time_str(self.total_duration)}"
        )
        self._request_preview(sec)
        self._redraw_filmstrip()
        self._redraw_subtitles()

    def _load_filmstrip(self):
        if not self.current_file or self.total_duration <= 0:
            return
        video_path = self.current_file
        duration = self.total_duration

        def work():
            # 取 8 個跨全片的關鍵影格作為膠卷故事板縮圖
            fractions = [0.03, 0.16, 0.30, 0.44, 0.58, 0.72, 0.86, 0.97]
            thumbs = []
            for frac in fractions:
                t = duration * frac
                ppm = self.editor.get_frame_ppm(video_path, t, width=160, height=72)
                if ppm:
                    thumbs.append((t, ppm))

            def apply():
                if self.current_file != video_path:
                    return
                self.filmstrip_thumbs = []
                for t, ppm in thumbs:
                    try:
                        img = tk.PhotoImage(data=ppm)
                        self.filmstrip_thumbs.append((t, img))
                    except Exception:
                        pass
                self._redraw_filmstrip()

            try:
                self.window.after(0, apply)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _load_waveform(self):
        if not self.current_file or self.total_duration <= 0:
            return
        video_path = self.current_file
        self._waveform_loading = True
        self._redraw_waveform()

        def work():
            peaks = self.editor.extract_audio_waveform(video_path, num_bins=320)

            def apply():
                if self.current_file != video_path:
                    return
                self.audio_waveform = peaks
                self._waveform_loading = False
                self._redraw_waveform()

            try:
                self.window.after(0, apply)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _get_filmstrip_dimensions(self):
        canvas = getattr(self, "filmstrip_canvas", None)
        if canvas is None:
            return 800, 76
        W = canvas.winfo_width()
        H = canvas.winfo_height()
        if W <= 1:
            try:
                c_w = int(canvas.cget("width"))
                if c_w > 1:
                    W = c_w
                elif hasattr(self, "filmstrip_frame"):
                    W = self.filmstrip_frame.winfo_width()
            except Exception:
                W = 800
            if W <= 1:
                W = 800
        if H <= 1:
            try:
                c_h = int(canvas.cget("height"))
                if c_h > 1:
                    H = c_h
                elif hasattr(self, "filmstrip_frame"):
                    H = self.filmstrip_frame.winfo_height()
            except Exception:
                H = 76
            if H <= 1:
                H = 76
        return max(30, W), max(20, H)

    def _redraw_filmstrip(self):
        canvas = getattr(self, "filmstrip_canvas", None)
        if canvas is None:
            return
        try:
            if not canvas.winfo_exists():
                return
        except (tk.TclError, AttributeError):
            return

        W, H = self._get_filmstrip_dimensions()
        canvas.delete("all")

        # 1. 繪製縮圖列背景 (Storyboard Thumbnails)
        if self.filmstrip_thumbs:
            n = len(self.filmstrip_thumbs)
            step_w = W / float(n)
            for i, (_t, img) in enumerate(self.filmstrip_thumbs):
                cx = int(i * step_w + step_w / 2)
                cy = H // 2
                canvas.create_image(cx, cy, image=img)
                if i > 0:
                    canvas.create_line(int(i * step_w), 0, int(i * step_w), H, fill="#1E2330", width=1)
        else:
            # 尚未載入完成時的精緻膠卷軌道佔位
            canvas.create_rectangle(0, 0, W, H, fill="#0A0C10", outline="")
            for tx in range(0, W, 40):
                canvas.create_rectangle(tx + 4, 3, tx + 14, 9, fill="#1E2330", outline="")
                canvas.create_rectangle(tx + 4, H - 9, tx + 14, H - 3, fill="#1E2330", outline="")
            canvas.create_text(
                W // 2, H // 2,
                text="🎞 載入膠卷預覽中…",
                fill=UI["muted"],
                font=self.fonts["badge"],
            )

        # 2. 裁切選取區遮罩 (Dimmed Scrim outside Selection)
        dur = max(self.total_duration, 0.001)
        in_x = int(max(0.0, min(1.0, self.start_sec / dur)) * W)
        out_x = int(max(0.0, min(1.0, self.end_sec / dur)) * W)

        # 未選取區暗色遮罩
        if in_x > 0:
            canvas.create_rectangle(0, 0, in_x, H, fill="#000000", stipple="gray50", outline="")
        if out_x < W:
            canvas.create_rectangle(out_x, 0, W, H, fill="#000000", stipple="gray50", outline="")

        # 選取區高亮上下邊界發光線
        if out_x > in_x:
            canvas.create_line(in_x, 1, out_x, 1, fill=UI["ok"], width=2)
            canvas.create_line(in_x, H - 1, out_x, H - 1, fill=UI["ok"], width=2)

        tab_h = 36
        tab_y1 = (H - tab_h) // 2
        tab_y2 = tab_y1 + tab_h

        # 3. 起點握把 (In Handle) - 翠綠色
        is_hover_in = (self._hover_target == "in_handle" or self._drag_target == "in_handle")
        in_color = "#66FFAA" if is_hover_in else UI["ok"]
        canvas.create_line(in_x, 0, in_x, H, fill=in_color, width=3 if is_hover_in else 2)

        # In 握把徽章 (Grip Tab) - 靠選取區內側
        tab_in_x1 = max(0, in_x - 3)
        tab_in_x2 = min(W, in_x + 13)
        canvas.create_rectangle(tab_in_x1, tab_y1, tab_in_x2, tab_y2, fill=in_color, outline=UI["ink"], width=1)
        canvas.create_text((tab_in_x1 + tab_in_x2) // 2, H // 2, text="[", fill=UI["ink"], font=("Helvetica", 11, "bold"))

        # 4. 終點握把 (Out Handle) - 珊瑚粉/寶石紅
        is_hover_out = (self._hover_target == "out_handle" or self._drag_target == "out_handle")
        out_color = "#FF6688" if is_hover_out else UI["red"]
        canvas.create_line(out_x, 0, out_x, H, fill=out_color, width=3 if is_hover_out else 2)

        # Out 握把徽章 (Grip Tab) - 靠選取區內側
        tab_out_x1 = max(0, out_x - 13)
        tab_out_x2 = min(W, out_x + 3)
        canvas.create_rectangle(tab_out_x1, tab_y1, tab_out_x2, tab_y2, fill=out_color, outline=UI["ink"], width=1)
        canvas.create_text((tab_out_x1 + tab_out_x2) // 2, H // 2, text="]", fill=UI["white"], font=("Helvetica", 11, "bold"))

        # 5. 當前播放指針 (Playhead Indicator)
        cur_x = int(max(0.0, min(1.0, self.current_time / dur)) * W)
        canvas.create_line(cur_x, 0, cur_x, H, fill=UI["blue"], width=2)
        # 播放指針頭 (Diamond Head)
        canvas.create_polygon(
            cur_x - 5, 0,
            cur_x + 5, 0,
            cur_x, 8,
            fill=UI["blue"], outline="",
        )

        # 6. 即時 Hover 刷屏指針與懸浮時間膠囊 (Skimmer Needle & Time Bubble)
        if self._skimmer_x is not None and self._drag_target is None and self._hover_target == "track":
            sx = self._skimmer_x
            canvas.create_line(sx, 0, sx, H, fill=UI["warn"], width=1.5, dash=(3, 2))

            # 懸浮時間藥丸
            t_str = sec_to_time_str(getattr(self, "_skimmer_time", 0.0))
            badge_w = 64
            badge_h = 18
            bx1 = max(4, min(W - badge_w - 4, sx - badge_w // 2))
            bx2 = bx1 + badge_w
            by1 = 2
            by2 = by1 + badge_h

            canvas.create_rectangle(bx1, by1, bx2, by2, fill="#060709", outline=UI["warn"], width=1)
            canvas.create_text((bx1 + bx2) // 2, (by1 + by2) // 2, text=t_str, fill=UI["warn"], font=("Helvetica", 9, "bold"))

        # 同步重繪音訊波形軌道
        self._redraw_waveform()

    def _get_waveform_dimensions(self):
        canvas = getattr(self, "waveform_canvas", None)
        if canvas is None:
            return 800, 44
        W = canvas.winfo_width()
        H = canvas.winfo_height()
        if W <= 1:
            try:
                c_w = int(canvas.cget("width"))
                if c_w > 1:
                    W = c_w
                elif hasattr(self, "waveform_frame"):
                    W = self.waveform_frame.winfo_width()
            except Exception:
                W = 800
            if W <= 1:
                W = 800
        if H <= 1:
            try:
                c_h = int(canvas.cget("height"))
                if c_h > 1:
                    H = c_h
                elif hasattr(self, "waveform_frame"):
                    H = self.waveform_frame.winfo_height()
            except Exception:
                H = 44
            if H <= 1:
                H = 44
        return max(30, W), max(20, H)

    def _redraw_waveform(self):
        canvas = getattr(self, "waveform_canvas", None)
        if canvas is None:
            return
        try:
            if not canvas.winfo_exists():
                return
        except (tk.TclError, AttributeError):
            return

        W, H = self._get_waveform_dimensions()
        canvas.delete("all")

        # 1. 軌道底色與中心對齊線
        canvas.create_rectangle(0, 0, W, H, fill="#08090D", outline="")
        mid_y = H // 2
        canvas.create_line(0, mid_y, W, mid_y, fill="#141822", width=1)

        dur = max(self.total_duration, 0.001)
        in_x = int(max(0.0, min(1.0, self.start_sec / dur)) * W)
        out_x = int(max(0.0, min(1.0, self.end_sec / dur)) * W)

        # 2. 狀態標記與波形繪製
        if getattr(self, "_waveform_loading", False):
            canvas.create_text(
                W // 2, mid_y,
                text="🎙 正在分析音訊波形…",
                fill=UI["muted"],
                font=self.fonts["badge"],
            )
        elif not getattr(self, "audio_waveform", None):
            canvas.create_text(
                W // 2, mid_y,
                text="🔇 無音訊軌道 (靜音影片)",
                fill=UI["muted"],
                font=self.fonts["badge"],
            )
        else:
            peaks = self.audio_waveform
            n = len(peaks)
            step_w = W / float(n)

            for i, p in enumerate(peaks):
                x1 = int(i * step_w)
                x2 = int((i + 1) * step_w)
                bw = max(1, x2 - x1 - 1)
                bh = max(2, int(p * ((H - 8) / 2.0)))

                is_selected = (in_x <= x1 <= out_x) or (in_x <= (x1 + bw) <= out_x)
                if is_selected:
                    color = UI["ok"] if p > 0.05 else "#124B3C"
                else:
                    color = "#2E3646" if p > 0.05 else "#151B26"

                canvas.create_rectangle(x1, mid_y - bh, x1 + bw, mid_y + bh, fill=color, outline="")

        # 3. 未選取區暗色遮罩
        if in_x > 0:
            canvas.create_rectangle(0, 0, in_x, H, fill="#000000", stipple="gray50", outline="")
        if out_x < W:
            canvas.create_rectangle(out_x, 0, W, H, fill="#000000", stipple="gray50", outline="")

        # 4. 選取區起迄端點指示線
        if out_x > in_x:
            canvas.create_line(in_x, 0, in_x, H, fill=UI["ok"], width=2)
            canvas.create_line(out_x, 0, out_x, H, fill=UI["red"], width=2)

        # 5. 當前播放指針
        cur_x = int(max(0.0, min(1.0, self.current_time / dur)) * W)
        canvas.create_line(cur_x, 0, cur_x, H, fill=UI["blue"], width=2)

        # 6. 即時 Hover 刷屏指針
        if self._skimmer_x is not None:
            sx = self._skimmer_x
            canvas.create_line(sx, 0, sx, H, fill=UI["warn"], width=1.5, dash=(3, 2))

    def _on_waveform_motion(self, event):
        W, H = self._get_waveform_dimensions()
        self._hover_target = "track"
        self._skimmer_x = event.x
        hover_sec = max(0.0, min(self.total_duration, (event.x / float(W)) * self.total_duration))
        self._skimmer_time = hover_sec
        self._redraw_filmstrip()
        self._request_preview(hover_sec)

    def _on_waveform_leave(self, _event):
        if self._drag_target is None:
            self._skimmer_x = None
            self._skimmer_time = None
            self._hover_target = None
            self._redraw_filmstrip()
            self._request_preview(self.current_time)

    def _on_waveform_press(self, event):
        if self._playing_process and self._playing_process.poll() is None:
            self._playing_process.terminate()
            self._playing_process = None

        W, H = self._get_waveform_dimensions()
        click_time = max(0.0, min(self.total_duration, (event.x / float(W)) * self.total_duration))
        self._jump_to_time(click_time)

    def _on_waveform_drag(self, event):
        W, H = self._get_waveform_dimensions()
        drag_time = max(0.0, min(self.total_duration, (event.x / float(W)) * self.total_duration))
        self._jump_to_time(drag_time)

    def _on_filmstrip_motion(self, event):
        if self._drag_target is not None:
            return

        W, H = self._get_filmstrip_dimensions()
        dur = max(self.total_duration, 0.001)
        in_x = int(max(0.0, min(1.0, self.start_sec / dur)) * W)
        out_x = int(max(0.0, min(1.0, self.end_sec / dur)) * W)

        dist_in = abs(event.x - in_x)
        dist_out = abs(event.x - out_x)

        # 偵測是否位於握把上方 (容差 ±12px)
        if dist_in <= 12 and dist_in <= dist_out:
            if self._hover_target != "in_handle":
                self._hover_target = "in_handle"
                self.filmstrip_canvas.config(cursor="sb_h_double_arrow" if IS_MAC else "ew-resize")
                self._skimmer_x = None
                self._redraw_filmstrip()
            return
        elif dist_out <= 12:
            if self._hover_target != "out_handle":
                self._hover_target = "out_handle"
                self.filmstrip_canvas.config(cursor="sb_h_double_arrow" if IS_MAC else "ew-resize")
                self._skimmer_x = None
                self._redraw_filmstrip()
            return

        # 軌道刷屏 (Skimming)
        need_redraw = (self._hover_target != "track") or (self._skimmer_x != event.x)
        self._hover_target = "track"
        self.filmstrip_canvas.config(cursor="crosshair")
        self._skimmer_x = event.x
        hover_sec = max(0.0, min(self.total_duration, (event.x / float(W)) * self.total_duration))
        self._skimmer_time = hover_sec
        if need_redraw:
            self._redraw_filmstrip()

        # 即時刷屏影格預覽 (Live Hover Scrubbing)
        self._request_preview(hover_sec)

    def _on_filmstrip_leave(self, _event):
        if self._drag_target is None:
            self._skimmer_x = None
            self._skimmer_time = None
            self._hover_target = None
            self.filmstrip_canvas.config(cursor="crosshair")
            self._redraw_filmstrip()
            self._request_preview(self.current_time)

    def _on_filmstrip_press(self, event):
        if self._playing_process and self._playing_process.poll() is None:
            self._playing_process.terminate()
            self._playing_process = None

        W, H = self._get_filmstrip_dimensions()
        dur = max(self.total_duration, 0.001)
        in_x = int(max(0.0, min(1.0, self.start_sec / dur)) * W)
        out_x = int(max(0.0, min(1.0, self.end_sec / dur)) * W)

        dist_in = abs(event.x - in_x)
        dist_out = abs(event.x - out_x)

        if dist_in <= 12 and dist_in <= dist_out:
            self._drag_target = "in_handle"
        elif dist_out <= 12:
            self._drag_target = "out_handle"
        else:
            self._drag_target = "playhead"
            click_time = max(0.0, min(self.total_duration, (event.x / float(W)) * self.total_duration))
            self._jump_to_time(click_time)
        self._redraw_filmstrip()

    def _on_filmstrip_drag(self, event):
        if not self._drag_target:
            return

        W, H = self._get_filmstrip_dimensions()
        dur = max(self.total_duration, 0.001)
        drag_time = max(0.0, min(self.total_duration, (event.x / float(W)) * dur))

        if self._drag_target == "in_handle":
            new_in = max(0.0, min(self.end_sec - 0.1, drag_time))
            self.start_sec = new_in
            self.ent_start.delete(0, tk.END)
            self.ent_start.insert(0, sec_to_time_str(new_in))
            self.time_slider.set_range(self.start_sec, self.end_sec)
            self._update_selection_length_label()
            self._request_preview(new_in)
            self._redraw_filmstrip()
        elif self._drag_target == "out_handle":
            new_out = min(self.total_duration, max(self.start_sec + 0.1, drag_time))
            self.end_sec = new_out
            self.ent_end.delete(0, tk.END)
            self.ent_end.insert(0, sec_to_time_str(new_out))
            self.time_slider.set_range(self.start_sec, self.end_sec)
            self._update_selection_length_label()
            self._request_preview(new_out)
            self._redraw_filmstrip()
        elif self._drag_target == "playhead":
            self._jump_to_time(drag_time)

    def _on_filmstrip_release(self, _event):
        self._drag_target = None
        self._redraw_filmstrip()

    def _on_slider_move(self, val):
        sec = float(val)
        self.current_time = sec
        self.lbl_cur_time.config(
            text=f"{sec_to_time_str(sec)} / {sec_to_time_str(self.total_duration)}"
        )
        self._request_preview(sec)
        self._redraw_filmstrip()
        self._redraw_subtitles()

    def _nudge_time(self, delta):
        new_time = max(0.0, min(self.total_duration, self.current_time + delta))
        self.current_time = new_time
        self.time_slider.set(new_time)
        self.lbl_cur_time.config(
            text=f"{sec_to_time_str(new_time)} / {sec_to_time_str(self.total_duration)}"
        )
        self._request_preview(new_time)
        self._redraw_filmstrip()
        self._redraw_subtitles()

    def _preview_filter(self):
        cfg = RATIO_CONFIGS.get(self.current_ratio, RATIO_CONFIGS["original"])
        zoom_cfg = self._get_zoom_config() if getattr(self, "preview_zoom_var", None) and self.preview_zoom_var.get() else None
        return preview_video_filter(
            cfg["aspect"], cfg["anchor"], width=cfg["preview_w"], height=cfg["preview_h"],
            zoom_config=zoom_cfg,
        )

    def _request_preview(self, sec):
        if not self.current_file:
            return
        self._preview_pending = (sec, self._preview_filter())
        if self._preview_thread is None or not self._preview_thread.is_alive():
            self._preview_thread = threading.Thread(target=self._worker_fetch_preview, daemon=True)
            self._preview_thread.start()

    def _worker_fetch_preview(self):
        while True:
            with self._preview_lock:
                pending = self._preview_pending
                self._preview_pending = None

            if pending is None:
                break
            target_sec, crop = pending

            cache_key = (self.current_file, round(target_sec, 1), crop)
            if hasattr(self, "_scrub_cache") and cache_key in self._scrub_cache:
                ppm_data = self._scrub_cache[cache_key]
            else:
                cfg = RATIO_CONFIGS.get(self.current_ratio, RATIO_CONFIGS["original"])
                ppm_data = self.editor.get_frame_ppm(
                    self.current_file, target_sec, width=cfg["preview_w"], height=cfg["preview_h"], video_filter=crop,
                )
                if ppm_data and hasattr(self, "_scrub_cache"):
                    if len(self._scrub_cache) > 80:
                        self._scrub_cache.pop(next(iter(self._scrub_cache)))
                    self._scrub_cache[cache_key] = ppm_data

            if ppm_data:
                self.window.after(0, lambda data=ppm_data: self._update_preview_image(data))

            time.sleep(0.04)

    def _update_preview_image(self, ppm_data):
        try:
            self.preview_image = tk.PhotoImage(data=ppm_data)
            self._redraw_preview_canvas()
        except Exception as e:
            print("Preview render error:", e)

    def _get_rendered_video_rect(self):
        """計算目前影片在 preview_canvas 上的實際渲染位置與長寬 (扣除黑邊 letterbox)"""
        cfg = RATIO_CONFIGS.get(self.current_ratio, RATIO_CONFIGS["original"])
        cw = max(1, cfg["preview_w"])
        ch = max(1, cfg["preview_h"])
        if not self.video_info:
            return 0, 0, cw, ch
        vw = max(1, self.video_info.get("width", 1920))
        vh = max(1, self.video_info.get("height", 1080))
        scale = min(cw / vw, ch / vh)
        rw = max(1, int(vw * scale))
        rh = max(1, int(vh * scale))
        ox = (cw - rw) // 2
        oy = (ch - rh) // 2
        return ox, oy, rw, rh

    def _canvas_to_norm_rect(self, x1, y1, x2, y2):
        """將 Canvas 像素座標轉換為相對於影片本體的標準化座標 (0.0 ~ 1.0)"""
        ox, oy, rw, rh = self._get_rendered_video_rect()
        bx1 = min(x1, x2)
        bx2 = max(x1, x2)
        by1 = min(y1, y2)
        by2 = max(y1, y2)

        nx1 = max(0.0, min(1.0, (bx1 - ox) / float(rw)))
        ny1 = max(0.0, min(1.0, (by1 - oy) / float(rh)))
        nx2 = max(0.0, min(1.0, (bx2 - ox) / float(rw)))
        ny2 = max(0.0, min(1.0, (by2 - oy) / float(rh)))

        nw = max(0.01, nx2 - nx1)
        nh = max(0.01, ny2 - ny1)
        return (round(nx1, 4), round(ny1, 4), round(nw, 4), round(nh, 4))

    def _norm_to_canvas_rect(self, norm_rect):
        """將標準化座標 (0.0 ~ 1.0) 轉換回目前 Canvas 像素座標"""
        ox, oy, rw, rh = self._get_rendered_video_rect()
        nx, ny, nw, nh = norm_rect
        cx1 = int(ox + nx * rw)
        cy1 = int(oy + ny * rh)
        cx2 = int(ox + (nx + nw) * rw)
        cy2 = int(oy + (ny + nh) * rh)
        return cx1, cy1, cx2, cy2

    def _toggle_mask_mode(self, mode):
        if getattr(self, "_mask_mode", None) == mode:
            self._mask_mode = None
        else:
            self._mask_mode = mode
        self._mask_drag_start = None
        self._mask_drag_curr = None
        self._update_mask_ui()
        self._redraw_preview_canvas()

    def _remove_mask(self, mask_id):
        self.blur_masks = [m for m in self.blur_masks if m.get("id") != mask_id]
        self._update_mask_ui()
        self._redraw_preview_canvas()

    def _clear_all_masks(self):
        self.blur_masks.clear()
        self._mask_mode = None
        self._mask_drag_start = None
        self._mask_drag_curr = None
        self._update_mask_ui()
        self._redraw_preview_canvas()

    def _update_mask_ui(self):
        mode = getattr(self, "_mask_mode", None)
        if hasattr(self, "btn_mask_blur") and hasattr(self, "btn_mask_mosaic"):
            if mode == "blur":
                self.btn_mask_blur.config(bg="#00f0ff", fg=UI["ink"], text="✓ 框選模糊中…")
                self.btn_mask_mosaic.config(bg=UI["field"], fg=UI["text"], text="＋ 馬賽克 (Mosaic)")
                self.lbl_mask_hint.config(text="🎯 請在預覽畫面上按住滑鼠拖曳，框選高斯模糊區域", fg="#00f0ff")
            elif mode == "mosaic":
                self.btn_mask_blur.config(bg=UI["field"], fg=UI["text"], text="＋ 模糊 (Blur)")
                self.btn_mask_mosaic.config(bg="#f59e0b", fg=UI["ink"], text="✓ 框選馬賽克中…")
                self.lbl_mask_hint.config(text="🎯 請在預覽畫面上按住滑鼠拖曳，框選局部馬賽克區域", fg="#f59e0b")
            else:
                self.btn_mask_blur.config(bg=UI["field"], fg=UI["text"], text="＋ 模糊 (Blur)")
                self.btn_mask_mosaic.config(bg=UI["field"], fg=UI["text"], text="＋ 馬賽克 (Mosaic)")
                self.lbl_mask_hint.config(text="點選上方按鈕後，在預覽畫面上拖曳框選", fg=UI["muted"])

        count = len(getattr(self, "blur_masks", []))
        if hasattr(self, "lbl_mask_count"):
            self.lbl_mask_count.config(text=f"已建立 {count} 個遮罩")
        if hasattr(self, "btn_clear_masks"):
            self.btn_clear_masks.config(
                state=tk.NORMAL if count > 0 else tk.DISABLED,
                fg=UI["red"] if count > 0 else UI["muted"],
            )

        if hasattr(self, "mask_list_frame"):
            for w in self.mask_list_frame.winfo_children():
                w.destroy()

            if count == 0:
                tk.Label(
                    self.mask_list_frame, text="(目前尚無遮罩)",
                    font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"]
                ).pack(anchor="w", pady=(1, 2))
            else:
                for idx, m in enumerate(self.blur_masks):
                    row = tk.Frame(self.mask_list_frame, bg=UI["field"])
                    row.pack(fill=tk.X, pady=1)

                    m_id = m.get("id")
                    m_type = m.get("type", "blur")
                    nx, ny, nw, nh = m.get("norm_rect", (0, 0, 0, 0))
                    color = "#00f0ff" if m_type == "blur" else "#f59e0b"
                    icon_text = "🔒 模糊" if m_type == "blur" else "🔲 馬賽克"
                    pos_text = f"#{idx+1} {icon_text} ({int(nw*100)}%×{int(nh*100)}%)"

                    tk.Label(
                        row, text=pos_text, font=self.fonts["badge"],
                        fg=color, bg=UI["field"]
                    ).pack(side=tk.LEFT, padx=(4, 2), pady=2)

                    time_text = "區間" if m.get("time_range") else "全片"
                    tk.Label(
                        row, text=f"[{time_text}]", font=self.fonts["badge"],
                        fg=UI["muted"], bg=UI["field"]
                    ).pack(side=tk.LEFT, padx=2, pady=2)

                    del_btn = tk.Button(
                        row, text="✕", font=("Helvetica", 9, "bold"),
                        bg=UI["field"], fg="#ff4466",
                        activebackground=UI["hover"], activeforeground="#ff4466",
                        relief=tk.FLAT, bd=0, cursor="hand2",
                        command=lambda mid=m_id: self._remove_mask(mid),
                    )
                    del_btn.pack(side=tk.RIGHT, padx=4, pady=1)

    def _update_subtitle_ui(self):
        """更新屬性檢查器中的字幕狀態標籤"""
        count = len(getattr(self, "subtitles", []))
        if hasattr(self, "lbl_subtitle_status"):
            if count == 0:
                self.lbl_subtitle_status.config(text="尚未建立字幕", fg=UI["muted"])
            else:
                self.lbl_subtitle_status.config(text=f"已建立 {count} 句字幕", fg="#00F0FF")

    def _redraw_subtitles(self):
        """重繪時間軸上的智慧字幕軌道"""
        if not hasattr(self, "subtitle_canvas") or not self.subtitle_canvas.winfo_exists():
            return
        self.subtitle_canvas.delete("all")
        sw = self.subtitle_canvas.winfo_width()
        sh = self.subtitle_canvas.winfo_height()
        if sw <= 1 or sh <= 1:
            return

        total_dur = max(0.001, self.total_duration)

        # 軌道背景與左側 CC 徽章
        self.subtitle_canvas.create_rectangle(0, 0, sw, sh, fill="#0E121A", outline="")
        self.subtitle_canvas.create_text(
            26, sh // 2, text="CC 字幕", fill="#64748B", font=self.fonts["badge"]
        )

        if not hasattr(self, "subtitles") or self.subtitles.is_empty():
            self.subtitle_canvas.create_text(
                sw // 2, sh // 2, text="尚未建立字幕軌（點擊右側 ✨ AI 產生或 ＋加句）",
                fill="#475569", font=self.fonts["badge"]
            )
            return

        for cue in self.subtitles.cues:
            x1 = max(54, int(sw * (cue.start / total_dur)))
            x2 = min(sw, max(x1 + 18, int(sw * (cue.end / total_dur))))

            is_active = (cue.start <= self.current_time <= cue.end)
            fill_bg = "#15334D" if is_active else "#151D2A"
            border_c = "#00F0FF" if is_active else "#28374D"
            text_c = "#00F0FF" if is_active else "#CBD5E1"
            border_w = 2 if is_active else 1

            self.subtitle_canvas.create_rectangle(
                x1, 3, x2, sh - 3,
                fill=fill_bg, outline=border_c, width=border_w
            )

            available_w = x2 - x1 - 8
            if available_w > 18:
                snippet = cue.text
                max_chars = max(3, available_w // 11)
                if len(snippet) > max_chars:
                    snippet = snippet[:max_chars - 1] + "…"
                self.subtitle_canvas.create_text(
                    (x1 + x2) // 2, sh // 2,
                    text=snippet, fill=text_c, font=self.fonts["badge"]
                )

        # 繪製目前播放指針線
        cur_x = int(sw * (self.current_time / total_dur))
        self.subtitle_canvas.create_line(cur_x, 0, cur_x, sh, fill=UI["red"], width=1)

    def _on_subtitle_canvas_click(self, event):
        """點擊時間軸字幕軌自動跳轉時間或選取字幕"""
        if not hasattr(self, "subtitle_canvas") or self.total_duration <= 0:
            return
        sw = self.subtitle_canvas.winfo_width()
        if sw <= 1:
            return
        click_sec = (event.x / float(sw)) * self.total_duration
        cue = self.subtitles.get_cue_at_time(click_sec)
        if cue:
            self._jump_to_time(cue.start)
        else:
            self._jump_to_time(click_sec)

    def _open_subtitle_manager(self):
        """開啟 AI 離線語音識別與智慧字幕軌對話框"""
        if not self.current_file or not os.path.exists(self.current_file):
            messagebox.showwarning("提示", "尚未載入影片！")
            return
        if self._subtitle_dialog and self._subtitle_dialog.win.winfo_exists():
            self._subtitle_dialog.win.lift()
            return
        self._subtitle_dialog = SubtitleDialog(self.window, self)

    def _add_cue_at_current_time(self):
        """在目前時間點插入一句字幕"""
        cur = self.current_time
        self.subtitles.add_cue(cur, cur + 2.5, "點此輸入新字幕內容…")
        self._update_subtitle_ui()
        self._redraw_subtitles()
        self._redraw_preview_canvas()

    def _import_subtitles_file(self):
        """匯入外部 SRT/VTT 字幕檔"""
        f = filedialog.askopenfilename(
            title="匯入字幕檔案",
            filetypes=[("Subtitle Files", "*.srt;*.vtt"), ("SRT", "*.srt"), ("VTT", "*.vtt")]
        )
        if f:
            try:
                imported = SubtitleTrack.from_srt(f)
                self.subtitles.cues = imported.cues
                self._update_subtitle_ui()
                self._redraw_subtitles()
                self._redraw_preview_canvas()
                messagebox.showinfo("匯入成功", f"成功載入 {len(imported)} 句字幕！")
            except Exception as e:
                messagebox.showerror("匯入失敗", f"無法解析字幕檔案: {e}")

    def _export_subtitles_file(self):
        """匯出目前字幕為 SRT 檔案"""
        if self.subtitles.is_empty():
            messagebox.showwarning("提示", "目前沒有字幕可供匯出！")
            return
        f = filedialog.asksaveasfilename(
            title="儲存 SRT 字幕檔",
            defaultextension=".srt",
            filetypes=[("SRT Subtitles", "*.srt"), ("WebVTT", "*.vtt")]
        )
        if f:
            try:
                if f.endswith(".vtt"):
                    self.subtitles.save_vtt(f)
                else:
                    self.subtitles.save_srt(f)
                messagebox.showinfo("匯出成功", f"已成功儲存字幕檔至:\n{f}")
            except Exception as e:
                messagebox.showerror("匯出失敗", f"儲存字幕失敗: {e}")

    def _redraw_preview_canvas(self):
        self.preview_canvas.delete("all")
        cfg = RATIO_CONFIGS.get(self.current_ratio, RATIO_CONFIGS["original"])
        cw = cfg["preview_w"]
        ch = cfg["preview_h"]
        if self.preview_image:
            self.preview_canvas.create_image(cw // 2, ch // 2, image=self.preview_image)
        else:
            self.preview_canvas.create_text(
                cw // 2, ch // 2, text="等待載入影片…", fill=UI["muted"], font=self.fonts["body"]
            )

        # 繪製已建立之隱私遮罩
        self._mask_del_targets = {}
        for idx, m in enumerate(getattr(self, "blur_masks", [])):
            cx1, cy1, cx2, cy2 = self._norm_to_canvas_rect(m["norm_rect"])
            m_type = m.get("type", "blur")
            is_blur = m_type == "blur"
            color = "#00f0ff" if is_blur else "#f59e0b"
            tag_name = f"🔒 模糊 #{idx+1}" if is_blur else f"🔲 馬賽克 #{idx+1}"

            # 磨砂半透明填充與高亮邊框
            self.preview_canvas.create_rectangle(
                cx1, cy1, cx2, cy2, fill=color, stipple="gray50", outline=color, width=2
            )

            # 四角標線
            csz = min(8, max(3, (cx2 - cx1) // 4), max(3, (cy2 - cy1) // 4))
            self.preview_canvas.create_line(cx1, cy1, cx1 + csz, cy1, fill=UI["white"], width=2)
            self.preview_canvas.create_line(cx1, cy1, cx1, cy1 + csz, fill=UI["white"], width=2)
            self.preview_canvas.create_line(cx2, cy2, cx2 - csz, cy2, fill=UI["white"], width=2)
            self.preview_canvas.create_line(cx2, cy2, cx2, cy2 - csz, fill=UI["white"], width=2)

            # 頂部標籤膠囊
            badge_h = 16
            badge_y1 = max(0, cy1 - badge_h)
            badge_y2 = cy1
            badge_w = 64
            self.preview_canvas.create_rectangle(
                cx1, badge_y1, min(cw, cx1 + badge_w), badge_y2,
                fill="#07090e", outline=color, width=1
            )
            self.preview_canvas.create_text(
                cx1 + badge_w // 2, (badge_y1 + badge_y2) // 2,
                text=tag_name, fill=color, font=self.fonts["badge"]
            )

            # 刪除按鈕 [✕]
            del_w = 16
            del_x1 = max(cx1 + badge_w + 2, cx2 - del_w)
            del_x2 = cx2
            del_y1 = badge_y1
            del_y2 = badge_y2
            self.preview_canvas.create_rectangle(
                del_x1, del_y1, del_x2, del_y2,
                fill="#161b26", outline="#ff4466", width=1
            )
            self.preview_canvas.create_text(
                (del_x1 + del_x2) // 2, (del_y1 + del_y2) // 2,
                text="✕", fill="#ff4466", font=("Helvetica", 9, "bold")
            )
            self._mask_del_targets[m["id"]] = (del_x1 - 2, del_y1 - 2, del_x2 + 2, del_y2 + 2)

        # 繪製正在拖曳框選中的 Rubberband 預覽矩形
        if (
            getattr(self, "_mask_drag_start", None)
            and getattr(self, "_mask_drag_curr", None)
            and getattr(self, "_mask_mode", None) in ("blur", "mosaic")
        ):
            x1, y1 = self._mask_drag_start
            x2, y2 = self._mask_drag_curr
            bx1, bx2 = min(x1, x2), max(x1, x2)
            by1, by2 = min(y1, y2), max(y1, y2)
            color = "#00f0ff" if self._mask_mode == "blur" else "#f59e0b"
            lbl = "🔒 模糊" if self._mask_mode == "blur" else "🔲 馬賽克"

            self.preview_canvas.create_rectangle(
                bx1, by1, bx2, by2, fill=color, stipple="gray25", outline=color, width=2, dash=(4, 2)
            )
            dim_text = f"{lbl} ({bx2 - bx1}×{by2 - by1})"
            dim_w = 100
            self.preview_canvas.create_rectangle(
                bx1, max(0, by1 - 18), bx1 + dim_w, by1, fill="#07090e", outline=color, width=1
            )
            self.preview_canvas.create_text(
                bx1 + dim_w // 2, max(0, by1 - 9), text=dim_text, fill=color, font=self.fonts["badge"]
            )

        # 若有啟用 Auto Zoom 且非遮罩模式，繪製焦點環
        if self._is_zoom_active() and not self.preview_zoom_var.get() and getattr(self, "_mask_mode", None) is None:
            self._draw_focus_reticle(cw, ch)

        # 繪製即時字幕預覽 (Live Subtitle Overlay)
        if getattr(self, "preview_subtitles_var", None) and self.preview_subtitles_var.get() and hasattr(self, "subtitles"):
            cue = self.subtitles.get_cue_at_time(self.current_time)
            if cue and cue.text.strip():
                ox, oy, rw, rh = self._get_rendered_video_rect()
                scx = ox + rw // 2
                pos_pct = getattr(self.subtitles.style, "pos_y_pct", 0.86)
                scy = oy + int(rh * pos_pct)
                stext = cue.text.strip()
                tlen = len(stext)
                pill_w = max(70, min(rw - 20, tlen * 15 + 26))
                pill_h = 30
                px1 = scx - pill_w // 2
                py1 = scy - pill_h // 2
                px2 = scx + pill_w // 2
                py2 = scy + pill_h // 2
                fsize = getattr(self.subtitles.style, "font_size", 16)
                fcol = getattr(self.subtitles.style, "font_color", "#FFFFFF")

                self.preview_canvas.create_rectangle(
                    px1, py1, px2, py2,
                    fill="#050811", stipple="gray75", outline="#00F0FF", width=1
                )
                self.preview_canvas.create_text(
                    scx, scy, text=stext, fill=fcol, font=("Helvetica", max(10, fsize - 2), "bold")
                )

        # 繪製即時浮水印預覽 (Live Watermark Overlay)
        wm_cfg = self._get_editor_watermark_config()
        if wm_cfg.get("enabled") and wm_cfg.get("mode") not in (None, "", "none", "off"):
            try:
                ox, oy, rw, rh = self._get_rendered_video_rect()
                disp_text = str(wm_cfg.get("text") or "© 極光錄影 Aura")
                if wm_cfg.get("mode") == "timestamp":
                    disp_text = f"{disp_text} · {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                png_path = render_watermark_png(
                    text=disp_text,
                    style=wm_cfg.get("style", "aurora"),
                    opacity=wm_cfg.get("opacity", "medium"),
                    font_size=14,
                    tiled=(wm_cfg.get("mode") == "tiled"),
                    tile_w=max(120, rw),
                    tile_h=max(80, rh),
                )
                self._preview_wm_photo = tk.PhotoImage(file=png_path)
                if wm_cfg.get("mode") in ("tiled", "floating"):
                    self.preview_canvas.create_image(
                        ox + rw // 2, oy + rh // 2, image=self._preview_wm_photo
                    )
                else:
                    pos = wm_cfg.get("position", "bottom-right")
                    pos_xy = {
                        "bottom-right": (ox + rw - 10, oy + rh - 10, "se"),
                        "bottom-left": (ox + 10, oy + rh - 10, "sw"),
                        "top-right": (ox + rw - 10, oy + 10, "ne"),
                        "top-left": (ox + 10, oy + 10, "nw"),
                        "center": (ox + rw // 2, oy + rh // 2, "center"),
                    }
                    wx, wy, wanc = pos_xy.get(pos, (ox + rw - 10, oy + rh - 10, "se"))
                    self.preview_canvas.create_image(wx, wy, image=self._preview_wm_photo, anchor=wanc)
            except Exception:
                pass

    def _on_editor_watermark_toggle(self):
        wm_on = bool(self.watermark_enabled_var.get())
        self.watermark_config["enabled"] = wm_on
        if wm_on and self.watermark_config.get("mode") in (None, "", "none", "off"):
            self.watermark_config["mode"] = "corner"
        self._redraw_preview_canvas()

    def _get_editor_watermark_config(self):
        cfg = dict(getattr(self, "watermark_config", None) or {})
        if hasattr(self, "watermark_enabled_var"):
            wm_on = bool(self.watermark_enabled_var.get())
            cfg["enabled"] = wm_on
            if wm_on and cfg.get("mode") in (None, "", "none", "off"):
                cfg["mode"] = "corner"
        return cfg

    def _open_watermark_dialog(self):
        saved = load_settings()
        excl_cfg = saved.get("exclusion_config") or {}

        def on_saved(new_excl, new_wm):
            self.watermark_config = dict(new_wm)
            self.watermark_enabled_var.set(bool(new_wm.get("enabled", False)))
            save_settings({
                "exclusion_config": new_excl,
                "watermark_config": new_wm,
            })
            self._redraw_preview_canvas()

        WindowExclusionWatermarkDialog(
            self.window,
            initial_exclusion=excl_cfg,
            initial_watermark=self._get_editor_watermark_config(),
            screen_index=0,
            on_save=on_saved,
        )

    def _draw_focus_reticle(self, cw, ch):
        fx = getattr(self, "zoom_focus_x", 0.5)
        fy = getattr(self, "zoom_focus_y", 0.5)
        cx = int(cw * fx)
        cy = int(ch * fy)

        # 外圈發光環 (Neon Cyan)
        self.preview_canvas.create_oval(cx - 20, cy - 20, cx + 20, cy + 20, outline="#00f0ff", width=2)
        # 中心綠點
        self.preview_canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="#00ff9d", outline="")
        # 十字標線
        self.preview_canvas.create_line(cx - 26, cy, cx - 10, cy, fill="#00f0ff", width=1)
        self.preview_canvas.create_line(cx + 10, cy, cx + 26, cy, fill="#00f0ff", width=1)
        self.preview_canvas.create_line(cx, cy - 26, cx, cy - 10, fill="#00f0ff", width=1)
        self.preview_canvas.create_line(cx, cy + 10, cx, cy + 26, fill="#00f0ff", width=1)

        # 標籤泡泡
        badge_text = f"🎯 焦點 ({int(fx * 100)}%, {int(fy * 100)}%)"
        self.preview_canvas.create_rectangle(
            cx - 44, cy + 22, cx + 44, cy + 38, fill="#0a0c10", outline="#00f0ff"
        )
        self.preview_canvas.create_text(
            cx, cy + 30, text=badge_text, fill="#00f0ff", font=self.fonts["badge"]
        )

    def _on_canvas_click(self, event):
        # 1. 檢查是否點擊遮罩的刪除按鈕
        if hasattr(self, "_mask_del_targets"):
            for m_id, (dx1, dy1, dx2, dy2) in list(self._mask_del_targets.items()):
                if dx1 <= event.x <= dx2 and dy1 <= event.y <= dy2:
                    self._remove_mask(m_id)
                    return

        # 2. 若處於遮罩模式，啟動框選
        if getattr(self, "_mask_mode", None) in ("blur", "mosaic"):
            self._mask_drag_start = (event.x, event.y)
            self._mask_drag_curr = (event.x, event.y)
            self._redraw_preview_canvas()
            return

        # 3. 預設模式：更新焦點
        self._update_zoom_focus_from_event(event)

    def _on_canvas_drag(self, event):
        if getattr(self, "_mask_mode", None) in ("blur", "mosaic") and self._mask_drag_start:
            self._mask_drag_curr = (event.x, event.y)
            self._redraw_preview_canvas()
            return

        if getattr(self, "_mask_mode", None) is None:
            self._update_zoom_focus_from_event(event)

    def _on_canvas_release(self, event):
        if getattr(self, "_mask_mode", None) in ("blur", "mosaic") and self._mask_drag_start:
            x1, y1 = self._mask_drag_start
            x2, y2 = event.x, event.y
            bw = abs(x2 - x1)
            bh = abs(y2 - y1)
            if bw >= 8 and bh >= 8:
                norm_rect = self._canvas_to_norm_rect(x1, y1, x2, y2)
                t_range = (self.start_sec, self.end_sec) if self._mask_apply_scope.get() == "selection" else None
                m_type = self._mask_mode
                new_mask = {
                    "id": getattr(self, "_mask_counter", 1),
                    "type": m_type,
                    "norm_rect": norm_rect,
                    "time_range": t_range,
                    "strength": 20 if m_type == "blur" else 16,
                }
                self._mask_counter = getattr(self, "_mask_counter", 1) + 1
                self.blur_masks.append(new_mask)
                self._mask_mode = None
                self._update_mask_ui()

            self._mask_drag_start = None
            self._mask_drag_curr = None
            self._redraw_preview_canvas()

    def _update_zoom_focus_from_event(self, event):
        cfg = RATIO_CONFIGS.get(self.current_ratio, RATIO_CONFIGS["original"])
        cw = max(1, cfg["preview_w"])
        ch = max(1, cfg["preview_h"])
        fx = max(0.05, min(0.95, round(event.x / cw, 2)))
        fy = max(0.05, min(0.95, round(event.y / ch, 2)))
        self.zoom_focus_x = fx
        self.zoom_focus_y = fy
        self.zoom_pos_combo.set("🎯 自訂 / 點擊畫面")
        self._update_focus_coord_label()
        if self.zoom_mode_combo.get().startswith("關閉"):
            self.zoom_mode_combo.current(1)
        self._redraw_preview_canvas()
        if self.preview_zoom_var.get():
            self._request_preview(self.current_time)

    def _update_focus_coord_label(self):
        fx = getattr(self, "zoom_focus_x", 0.5)
        fy = getattr(self, "zoom_focus_y", 0.5)
        if hasattr(self, "lbl_zoom_coords"):
            raw = f"焦點座標: X {int(fx * 100)}% · Y {int(fy * 100)}%"
            self.lbl_zoom_coords._i18n_orig_text = raw
            self.lbl_zoom_coords.config(text=tr(raw, get_language()))

    def _on_zoom_pos_changed(self, _event=None):
        pos_val = self.zoom_pos_combo.get()
        mapping = {
            "畫面中心": (0.50, 0.50),
            "Center": (0.50, 0.50),
            "中央": (0.50, 0.50),
            "画面中心": (0.50, 0.50),
            "左上": (0.25, 0.25),
            "Top-Left": (0.25, 0.25),
            "右上": (0.75, 0.25),
            "Top-Right": (0.75, 0.25),
            "左下": (0.25, 0.75),
            "Bottom-Left": (0.25, 0.75),
            "右下": (0.75, 0.75),
            "Bottom-Right": (0.75, 0.75),
            "上方中": (0.50, 0.25),
            "Top-Center": (0.50, 0.25),
            "上中央": (0.50, 0.25),
            "下方中": (0.50, 0.75),
            "Bottom-Center": (0.50, 0.75),
            "下中央": (0.50, 0.75),
        }
        for k, (x, y) in mapping.items():
            if k in pos_val:
                self.zoom_focus_x = x
                self.zoom_focus_y = y
                break
        self._update_focus_coord_label()
        self._redraw_preview_canvas()
        if self.preview_zoom_var.get():
            self._request_preview(self.current_time)

    def _on_zoom_mode_or_level_changed(self, _event=None):
        self._update_focus_coord_label()
        self._redraw_preview_canvas()
        if self.preview_zoom_var.get() or self._is_zoom_active():
            self._request_preview(self.current_time)

    def _detect_action_focus(self):
        if not self.current_file or self.total_duration <= 0:
            return
        self.btn_detect_focus.config(text=tr("偵測中…", get_language()), state=tk.DISABLED)

        def work():
            fx, fy = self.editor.detect_motion_focus(
                self.current_file, self.start_sec, self.end_sec
            )
            def done():
                self.zoom_focus_x = fx
                self.zoom_focus_y = fy
                self.zoom_pos_combo.set(tr("🎯 自訂 / 點擊畫面", get_language()))
                self._update_focus_coord_label()
                if self.zoom_mode_combo.current() == 0:
                    self.zoom_mode_combo.current(1)
                self.btn_detect_focus.config(text=tr("🎯 智慧偵測焦點", get_language()), state=tk.NORMAL)
                self._redraw_preview_canvas()
                if self.preview_zoom_var.get():
                    self._request_preview(self.current_time)

            self.window.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _get_zoom_config(self):
        if not hasattr(self, "zoom_mode_combo"):
            return {"enabled": False, "mode": "off"}
        mode_val = self.zoom_mode_combo.get()
        if any(k in mode_val for k in ("關閉", "关闭", "Off", "オフ", "1.0x")):
            return {"enabled": False, "mode": "off"}

        mode = "smooth_in_out"
        if any(k in mode_val for k in ("推進特寫", "推进特写", "Smooth Zoom In", "ズームイン")):
            mode = "smooth_in"
        elif any(k in mode_val for k in ("全程", "固定", "Static", "固定ズーム")):
            mode = "static"

        lvl_val = self.zoom_level_combo.get()
        m_lvl = re.search(r"(\d+(\.\d+)?)", lvl_val)
        level = float(m_lvl.group(1)) if m_lvl else 1.5

        return {
            "enabled": True,
            "mode": mode,
            "level": level,
            "focus_x": getattr(self, "zoom_focus_x", 0.5),
            "focus_y": getattr(self, "zoom_focus_y", 0.5),
        }

    def _is_zoom_active(self):
        cfg = self._get_zoom_config()
        return cfg.get("enabled", False)

    def set_in_point(self):
        self.start_sec = self.current_time
        if self.start_sec > self.end_sec:
            self.end_sec = self.total_duration
            self.ent_end.delete(0, tk.END)
            self.ent_end.insert(0, sec_to_time_str(self.end_sec))

        self.ent_start.delete(0, tk.END)
        self.ent_start.insert(0, sec_to_time_str(self.start_sec))
        self.time_slider.set_range(self.start_sec, self.end_sec)
        self._update_selection_length_label()
        self._redraw_filmstrip()

    def set_out_point(self):
        self.end_sec = self.current_time
        if self.end_sec < self.start_sec:
            self.start_sec = 0.0
            self.ent_start.delete(0, tk.END)
            self.ent_start.insert(0, sec_to_time_str(self.start_sec))

        self.ent_end.delete(0, tk.END)
        self.ent_end.insert(0, sec_to_time_str(self.end_sec))
        self.time_slider.set_range(self.start_sec, self.end_sec)
        self._update_selection_length_label()
        self._redraw_filmstrip()

    def _update_times_from_entries(self):
        s = time_str_to_sec(self.ent_start.get())
        e = time_str_to_sec(self.ent_end.get())

        if s is not None and 0.0 <= s <= self.total_duration:
            self.start_sec = s
        if e is not None and 0.0 <= e <= self.total_duration:
            self.end_sec = e

        if self.start_sec > self.end_sec:
            self.start_sec, self.end_sec = self.end_sec, self.start_sec

        self.ent_start.delete(0, tk.END)
        self.ent_start.insert(0, sec_to_time_str(self.start_sec))
        self.ent_end.delete(0, tk.END)
        self.ent_end.insert(0, sec_to_time_str(self.end_sec))
        self.time_slider.set_range(self.start_sec, self.end_sec)
        self._update_selection_length_label()
        self._redraw_filmstrip()

    def _update_selection_length_label(self):
        sel_dur = max(0.0, self.end_sec - self.start_sec)
        pct = (sel_dur / self.total_duration * 100) if self.total_duration > 0 else 100
        raw = f"選取長度 {sec_to_time_str(sel_dur)} ({pct:.0f}%)"
        self.lbl_selected_len._i18n_orig_text = raw
        self.lbl_selected_len.config(
            text=tr(raw, get_language())
        )

    def preview_play_selection(self):
        if self._playing_process and self._playing_process.poll() is None:
            self._playing_process.terminate()
            self._playing_process = None
            self.btn_play_seg.config(text="播放 [Space]", style="Play.TButton")
            return

        if not self.current_file or not os.path.exists(self.current_file):
            messagebox.showwarning("提示", "尚未載入影片！")
            return

        self._update_times_from_entries()
        dur = self.end_sec - self.start_sec
        if dur <= 0:
            messagebox.showwarning("提示", "選取長度需大於 0 秒")
            return

        self._playing_process = self.editor.play_segment(self.current_file, self.start_sec, dur)
        if not self._playing_process:
            open_file_or_dir(self.current_file)
            return

        self.btn_play_seg.config(text="停止 [Space]", style="Stop.TButton")

        def monitor_process():
            if self._playing_process:
                self._playing_process.wait()
            self.window.after(0, lambda: self.btn_play_seg.config(text="播放 [Space]", style="Play.TButton"))

        threading.Thread(target=monitor_process, daemon=True).start()

    def perform_export(self):
        if not self.current_file or not os.path.exists(self.current_file):
            messagebox.showwarning("提示", "尚未載入影片！")
            return

        self._update_times_from_entries()
        dur = self.end_sec - self.start_sec
        if dur <= 0.05:
            messagebox.showwarning("錯誤", "裁切長度過短，請確認起點與終點設定！")
            return

        mode = self.export_mode_var.get()
        if mode == "audio" and self.video_info and not self.video_info.get("has_audio"):
            messagebox.showwarning("提示", "此影片沒有音訊軌，無法提取音訊！")
            return

        p = Path(self.current_file)
        time_tag = f"{int(self.start_sec)}s-{int(self.end_sec)}s"
        default_dir = str(p.parent)

        if mode == "gif":
            default_name = f"{p.stem}_clip_{time_tag}.gif"
            filetypes = [("GIF 動畫", "*.gif")]
        elif mode == "audio":
            default_name = f"{p.stem}_audio_{time_tag}.mp3"
            filetypes = [("MP3 音訊", "*.mp3"), ("AAC 音訊", "*.m4a")]
        else:
            default_name = f"{p.stem}_clip_{time_tag}.mp4"
            filetypes = [("MP4 影片", "*.mp4"), ("MOV 影片", "*.mov")]

        out_path = filedialog.asksaveasfilename(
            initialdir=default_dir,
            initialfile=default_name,
            filetypes=filetypes
        )
        if not out_path:
            return

        self.btn_export.config(text="正在匯出…", state=tk.DISABLED)
        self.btn_export_side.config(text="正在匯出…", state=tk.DISABLED)

        def run_export_thread():
            mute = self.mute_var.get()
            ok = False
            msg = ""

            # 讀取參數
            spd = 1.0
            try:
                spd_str = self.speed_combo.get().split()[0].replace("x", "")
                spd = float(spd_str)
            except Exception:
                pass

            cfg = RATIO_CONFIGS.get(self.current_ratio, RATIO_CONFIGS["original"])
            rat = cfg["aspect"]
            anchor = cfg["anchor"]

            vol = 1.0
            vol_str = self.volume_combo.get()
            if "150%" in vol_str:
                vol = 1.5
            elif "200%" in vol_str:
                vol = 2.0
            elif "50%" in vol_str:
                vol = 0.5

            scale_res = "original"
            scale_str = self.scale_combo.get()
            if "1080p" in scale_str:
                scale_res = "1080p"
            elif "720p" in scale_str:
                scale_res = "720p"

            zoom_cfg = self._get_zoom_config()
            has_masks = bool(self.blur_masks)
            wm_cfg = self._get_editor_watermark_config()
            has_watermark = bool(wm_cfg.get("enabled") and wm_cfg.get("mode") not in (None, "", "none", "off"))
            picture_change = (
                rat != "original"
                or abs(spd - 1.0) > 0.001
                or mute
                or abs(vol - 1.0) > 0.001
                or scale_res != "original"
                or zoom_cfg.get("enabled", False)
                or has_masks
                or has_watermark
            )
            export_mode = mode
            switched = export_mode == "lossless" and picture_change
            if switched:
                export_mode = "precise"

            # 準備字幕
            sub_srt_tmp = None
            tmp_sub_dir = None
            has_subs = not self.subtitles.is_empty() and (self.soft_subtitles_var.get() or self.export_srt_var.get())
            if has_subs:
                try:
                    clip_cues = []
                    clip_dur = self.end_sec - self.start_sec
                    for c in self.subtitles.cues:
                        if c.end > self.start_sec and c.start < self.end_sec:
                            rel_s = max(0.0, c.start - self.start_sec)
                            rel_e = min(clip_dur, c.end - self.start_sec)
                            if rel_e > rel_s:
                                clip_cues.append(SubtitleCue(id=len(clip_cues) + 1, start=rel_s, end=rel_e, text=c.text))
                    if clip_cues:
                        tmp_sub_dir = tempfile.mkdtemp(prefix="aura_clip_sub_")
                        sub_srt_tmp = os.path.join(tmp_sub_dir, "clip.srt")
                        SubtitleTrack(clip_cues).save_srt(sub_srt_tmp)
                except Exception as ex:
                    print("Error preparing clip subtitles:", ex)

            try:
                if export_mode == "lossless":
                    ok, msg = self.editor.trim_smart_cut(
                        self.current_file, out_path, self.start_sec, self.end_sec,
                        subtitles_srt_path=sub_srt_tmp,
                        soft_subtitles=self.soft_subtitles_var.get(),
                        export_srt_file=self.export_srt_var.get(),
                    )
                elif export_mode == "precise":
                    ok, msg = self.editor.trim_advanced(
                        self.current_file, out_path, self.start_sec, self.end_sec,
                        speed=spd, aspect_ratio=rat, anchor=anchor,
                        mute_audio=mute,
                        volume=vol,
                        target_resolution=scale_res,
                        zoom_config=zoom_cfg,
                        blur_masks=self.blur_masks if has_masks else None,
                        subtitles_srt_path=sub_srt_tmp,
                        soft_subtitles=self.soft_subtitles_var.get(),
                        export_srt_file=self.export_srt_var.get(),
                        watermark_config=wm_cfg if has_watermark else None,
                    )
                elif export_mode == "gif":
                    ok, msg = self.editor.export_gif(
                        self.current_file, out_path, self.start_sec, self.end_sec,
                        aspect_ratio=rat, anchor=anchor,
                        zoom_config=zoom_cfg,
                        blur_masks=self.blur_masks if has_masks else None,
                    )
                elif export_mode == "audio":
                    ok, msg = self.editor.extract_audio(
                        self.current_file, out_path, self.start_sec, self.end_sec,
                        volume=vol,
                    )
            except Exception as e:
                ok = False
                msg = str(e)
            finally:
                if tmp_sub_dir and os.path.exists(tmp_sub_dir):
                    shutil.rmtree(tmp_sub_dir, ignore_errors=True)

            self.window.after(
                0,
                lambda ok=ok, msg=msg, out_path=out_path, switched=switched: self._on_export_finished(
                    ok, msg, out_path, switched
                ),
            )

        threading.Thread(target=run_export_thread, daemon=True).start()

    def _on_export_finished(self, ok, msg, out_path, switched=False):
        self.btn_export.config(text=self._export_btn_label(), state=tk.NORMAL)
        self.btn_export_side.config(text="⚡ 一鍵匯出影片", state=tk.NORMAL)
        if ok:
            play_system_alert("complete")
            self._show_export_success_card(out_path, switched)
        else:
            messagebox.showerror("匯出失敗", f"匯出過程發生錯誤：\n{msg}")

    def _show_export_success_card(self, out_path, switched=False):
        card = tk.Toplevel(self.window)
        card.title("匯出完成 — AURA REC")
        card.configure(bg=UI["bg"])
        card.resizable(False, False)
        card.transient(self.window)
        card.grab_set()

        fonts = self.fonts
        p = Path(out_path)
        sz = p.stat().st_size / (1024 * 1024) if p.exists() else 0
        sz_text = f"{sz:.1f} MB" if sz >= 0.1 else f"{max(1, int(p.stat().st_size / 1024))} KB"

        box = tk.Frame(card, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1)
        box.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        hdr = tk.Frame(box, bg=UI["card"])
        hdr.pack(fill=tk.X, padx=16, pady=(16, 6))
        tk.Label(hdr, text="●  匯出成功", font=fonts["subtitle"], fg=UI["ok"], bg=UI["card"]).pack(side=tk.LEFT)

        tk.Label(box, text=p.name, font=fonts["bold"], fg=UI["text"], bg=UI["card"], wraplength=460, justify=tk.LEFT).pack(anchor="w", padx=16, pady=(0, 2))
        tk.Label(box, text=f"大小：{sz_text}   ·   路徑：{p.parent}", font=fonts["body"], fg=UI["muted"], bg=UI["card"], wraplength=460, justify=tk.LEFT).pack(anchor="w", padx=16, pady=(0, 6))

        if switched:
            reason = "包含隱私模糊遮罩" if bool(getattr(self, "blur_masks", None)) else "包含比例裁切或濾鏡調色"
            tk.Label(box, text=f"💡 由於{reason}，已自動為您使用精準重編碼匯出。", font=fonts["badge"], fg=UI["warn"], bg=UI["card"]).pack(anchor="w", padx=16, pady=(0, 6))
        elif getattr(self, "export_mode_var", None) and self.export_mode_var.get() == "lossless":
            tk.Label(box, text="⚡ Smart Cut 智慧無損：首尾毫秒級精準微編碼，主體 100% 無損複製秒出。", font=fonts["badge"], fg=UI["ok"], bg=UI["card"]).pack(anchor="w", padx=16, pady=(0, 6))

        companion_srt = Path(out_path).with_suffix(".srt")
        if companion_srt.exists() and getattr(self, "export_srt_var", None) and self.export_srt_var.get():
            tk.Label(box, text="💬 已同步產生同名 .srt 字幕檔，並已封裝字幕軌至 MP4/MOV。", font=fonts["badge"], fg=UI["blue"], bg=UI["card"]).pack(anchor="w", padx=16, pady=(0, 6))

        sep = tk.Frame(box, bg=UI["line"], height=1)
        sep.pack(fill=tk.X, padx=16, pady=8)

        btn_row = tk.Frame(box, bg=UI["card"])
        btn_row.pack(fill=tk.X, padx=16, pady=(0, 16))

        AuraButton(btn_row, text="播放", style="Play.TButton", command=lambda: open_file_or_dir(out_path)).pack(side=tk.LEFT, padx=(0, 6))
        AuraButton(btn_row, text="在資料夾中顯示", style="Ghost.TButton", command=lambda: open_file_or_dir(out_path, reveal=True)).pack(side=tk.LEFT, padx=6)

        def do_copy(btn):
            if copy_file(out_path):
                btn.config(text="已複製！")
                btn.after(2000, lambda: btn.config(text="複製檔案"))

        copy_btn = AuraButton(btn_row, text="複製檔案", style="Ghost.TButton", command=lambda: do_copy(copy_btn))
        copy_btn.pack(side=tk.LEFT, padx=6)

        AuraButton(btn_row, text="完成", style="Ghost.TButton", command=card.destroy).pack(side=tk.RIGHT, padx=(6, 0))

        card.update_idletasks()
        w = max(500, card.winfo_reqwidth())
        h = max(210, card.winfo_reqheight())
        x = self.window.winfo_x() + (self.window.winfo_width() - w) // 2
        y = self.window.winfo_y() + (self.window.winfo_height() - h) // 2
        card.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

    def _on_close(self):
        if self._playing_process and self._playing_process.poll() is None:
            self._playing_process.terminate()
        self.window.destroy()
        if self._after_close:
            self._after_close()
