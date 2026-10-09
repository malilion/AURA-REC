#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LiteScreenRecorder - 輕量桌面錄影工具 (macOS & Windows 跨平台支援)
- 支援 Apple Silicon (macOS) 與 NVIDIA / Intel / AMD (Windows) 硬體加速
- 支援螢幕選擇、音訊設備選擇（麥克風 / 系統音效）
- 支援自訂解析度 (原生 / 2K / 1080p / 720p) 與 FPS (15 / 30 / 60)
- 支援懸浮膠囊迷你模式 (Mini Floating Pill)，不遮擋畫面
- 支援暫停與繼續、錄製游標開關，並記住上次的裝置與畫質
- 支援自訂錄影範圍、選擇視窗、畫質、MP4 / MOV，以及到時自動停止
- 支援截圖、錄影中顯示檔案大小，空間不足時會先詢問
- 支援錄影中展開小條、預估每分鐘大小、分段存檔，以及替最近的檔案改名
- 倒數可以取消。錄影時不讓電腦睡著，並記住視窗位置
- 支援 3 秒倒數準備、快速鍵 (Space / F7 / F8 / F9 / Ctrl+R / Cmd+R / Esc)
- 支援即時影片剪輯與匯出 GIF / 提取音訊
"""

import math
import os
import re
import subprocess
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from pathlib import Path

from recorder import LOW_DISK_BYTES, ScreenRecorder, format_bytes, free_disk_bytes, save_still
from editor_window import VideoEditorWindow
from aura_widgets import AuraButton, AuraCheck
from region_picker import (
    bar_origin,
    box_to_points,
    capture_screen_index,
    display_frame,
    follow_crop,
    other_display_origin,
    pick_capture_window,
    pick_screen_region,
    resolve_window_box,
    window_capture_origin,
)
from platform_utils import (
    APP_VERSION,
    IS_MAC,
    IS_WINDOWS,
    HiddenRecordHotkeys,
    enable_dpi_awareness,
    find_executable,
    get_ui_fonts,
    play_system_alert,
    copy_file,
    copy_text_to_clipboard,
    get_system_diagnostics,
    open_file_or_dir,
    save_settings,
    load_settings,
    recommended_capture,
    capture_bitrate_k,
    machine_profile,
    fit_window_geometry,
    hold_awake,
    release_awake,
    UI,
    apply_widget_style,
    use_dark_appearance,
    get_mac_screen_details,
    get_screen_full_info,
    create_placeholder_ppm,
    capture_device_preview_ppm,
    flash_screen_badges,
)


def renamed_path(path, typed):
    """沿用原來的副檔名。檔名不能用時回傳 None，沒改名就回傳原路徑。"""
    path = Path(path)
    name = str(typed or "").strip()
    suffix = path.suffix
    if suffix and name.lower().endswith(suffix.lower()):
        name = name[: -len(suffix)].rstrip()
    if not name or name in {".", ".."} or name.startswith("."):
        return None
    if any(ch in name for ch in '/\\:\0<>"|?*'):
        return None
    return path.with_name(name + suffix)


def disk_time_text(free_bytes, bits_per_second):
    """以目前的碼率估計這個磁碟還能錄多久。"""
    try:
        free_bytes = int(free_bytes)
        bits_per_second = int(bits_per_second)
    except (TypeError, ValueError):
        return ""
    if free_bytes <= 0 or bits_per_second <= 0:
        return ""
    seconds = free_bytes / (bits_per_second / 8)
    if seconds >= 48 * 3600:
        return "還可錄 48 小時以上"
    if seconds >= 3600:
        return f"還可錄約 {max(1, round(seconds / 3600))} 小時"
    return f"還可錄約 {max(1, round(seconds / 60))} 分鐘"


_TIMED_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".gif", ".m4a", ".mp3", ".wav"}


def format_media_duration(seconds):
    """清單用的長度。不滿一小時不補小時。"""
    try:
        total = int(round(float(seconds)))
    except (TypeError, ValueError):
        return ""
    if total < 0:
        return ""
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class LiteRecorderApp:
    def __init__(self, root):
        self.root = root
        use_dark_appearance()
        self.root.title("AURA REC")
        self.root.geometry("560x800")
        self.root.minsize(520, 700)
        self.root.configure(bg=UI["bg"])

        # 跨平台字型
        self.fonts = get_ui_fonts()

        # 核心錄影實例
        self.recorder = ScreenRecorder()

        # 狀態變數
        self.is_mini_mode = False
        self.countdown_active = False
        self._stopping = False
        self._shooting = False
        self._pending_mini = False
        self._record_conceal = None
        self._hidden_hotkeys = HiddenRecordHotkeys()
        self._normal_size = (560, 800)
        self._saved = load_settings()
        self.region = self._saved_region()
        self.capture_window = self._saved_window()
        self._auto_stop_sec = None
        self._segment_sec = None
        self._duration_cache = {}
        self._recent_generation = 0
        self.auto_mini_var = tk.BooleanVar(value=self._flag("auto_mini", True))
        self.countdown_var = tk.BooleanVar(value=self._flag("countdown", True))
        self.hardware_accel_var = tk.BooleanVar(value=self._flag("hardware_accel", True))
        self.capture_cursor_var = tk.BooleanVar(value=self._flag("capture_cursor", True))
        self.auto_copy_screenshot_var = tk.BooleanVar(value=self._flag("auto_copy_screenshot", True))
        self.sound_alert_var = tk.BooleanVar(value=self._flag("sound_alerts", True))

        self.video_devices = []
        self.audio_devices = []
        self.capture_advice = recommended_capture()

        # 拖曳視窗支援 (Mini 模式用)
        self.drag_x = 0
        self.drag_y = 0

        # 初始化 UI
        self._init_styles()
        self._build_main_ui()
        self._bind_shortcuts()

        # 載入硬體設備與最近錄影
        self._refresh_devices()
        self.refresh_recent_list()

        # 註冊關閉事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._apply_saved_window()

        # 啟動計時更新迴圈
        self._timer_tick()

    def _init_styles(self):
        apply_widget_style(ttk.Style(), self.fonts)

    def _card(self, parent):
        return tk.Frame(
            parent,
            bg=UI["card"],
            highlightbackground=UI["edge"],
            highlightthickness=1,
        )

    def _accent_bar(self, parent):
        """官網主色：青漸層到綠的一條細線。"""
        canvas = tk.Canvas(parent, height=2, bg=UI["card"], highlightthickness=0, bd=0)
        canvas.pack(fill=tk.X)

        def paint(_event=None):
            canvas.delete("all")
            width = max(canvas.winfo_width(), 2)
            start = (0, 240, 255)
            end = (0, 255, 157)
            for x in range(width):
                t = x / (width - 1)
                color = tuple(int(start[i] + (end[i] - start[i]) * t) for i in range(3))
                canvas.create_line(x, 0, x, 2, fill="#{:02x}{:02x}{:02x}".format(*color))

        canvas.bind("<Configure>", paint)
        return canvas

    def _quiet_button(self, parent, text, command, fg=None):
        style = "Danger.TButton" if fg == UI["red"] else "Link.TButton"
        return AuraButton(parent, text=text, command=command, style=style)

    def _show_shortcuts(self):
        messagebox.showinfo(
            "快捷鍵",
            "開始或停止錄影：\n"
            f"{self.shortcut_hint}\n\n"
            "暫停或繼續：F8\n\n"
            "截圖：F7。有自訂範圍或視窗時只截那一塊。\n\n"
            "選單裡的「選擇視窗」會錄下那個視窗開始時的位置，檔名也會帶上程式名稱。\n"
            "若會縮成小條，小條會先讓到不擋住那個視窗的角落。\n\n"
            "倒數時再按一次，或按 Esc，就會取消。\n\n"
            "錄影中的小條可以拖曳挪開。按「展開」或 Esc 回到完整視窗，選單裡的「收成小條」可以再縮回去。\n\n"
            "複製最新檔案：Shift + Command + C（Windows 為 Shift + Ctrl + C）。",
        )

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="開啟儲存資料夾", command=self.open_output_folder)
        file_menu.add_command(label="變更儲存位置…", command=self.change_output_folder)
        file_menu.add_separator()
        file_menu.add_command(label="暫停或繼續", command=self.toggle_pause, accelerator="F8")
        file_menu.add_command(label="展開錄影畫面", command=self._expand_from_mini, accelerator="Esc")
        file_menu.add_command(label="收成小條", command=self._collapse_to_mini)
        file_menu.add_command(label="截圖", command=self.take_screenshot, accelerator="F7")
        file_menu.add_command(label="選擇視窗…", command=self._pick_window)
        file_menu.add_command(label="剪輯影片…", command=self.open_editor)
        file_menu.add_command(label="播放最新錄影", command=self.play_last_recording)
        file_menu.add_command(
            label="複製最新檔案",
            command=self.copy_latest_file,
            accelerator="⇧⌘C" if IS_MAC else "Ctrl+Shift+C",
        )
        file_menu.add_separator()
        file_menu.add_command(label="系統聲音錄製指南…", command=self._show_system_audio_guide)
        file_menu.add_command(
            label="偏好設定…",
            command=self._show_preferences,
            accelerator="⌘," if IS_MAC else "Ctrl+,",
        )
        file_menu.add_separator()
        file_menu.add_command(label="結束", command=self._on_close)
        menubar.add_cascade(label="檔案", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="快捷鍵說明", command=self._show_shortcuts)
        help_menu.add_command(label="系統聲音錄製指南…", command=self._show_system_audio_guide)
        help_menu.add_command(label="FFmpeg 與硬體加速檢視…", command=self._show_diagnostics)
        help_menu.add_separator()
        help_menu.add_command(label="關於 AURA REC", command=self._show_about)
        menubar.add_cascade(label="說明", menu=help_menu)
        self.menubar = menubar
        self.root.config(menu=self.menubar)

    def _build_main_ui(self):
        self._build_menu()
        self.main_container = tk.Frame(self.root, bg=UI["bg"])
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

        header_frame = tk.Frame(self.main_container, bg=UI["bg"])
        header_frame.pack(fill=tk.X, pady=(0, 10))

        brand = tk.Frame(header_frame, bg=UI["bg"])
        brand.pack(side=tk.LEFT)
        tk.Label(
            brand, text="AURA", font=self.fonts["title"], fg=UI["white"], bg=UI["bg"]
        ).pack(side=tk.LEFT)
        tk.Label(
            brand, text="REC", font=self.fonts["title"], fg=UI["blue"], bg=UI["bg"]
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.status_badge = tk.Label(
            header_frame,
            text="●  就緒",
            font=self.fonts["badge"],
            fg=UI["ok"],
            bg=UI["bg"],
        )
        self.status_badge.pack(side=tk.RIGHT)
        self.shot_btn = self._quiet_button(header_frame, "截圖", self.take_screenshot)
        self.shot_btn.pack(side=tk.RIGHT, padx=(0, 4))

        self.timer_card = self._card(self.main_container)
        self.timer_card.pack(fill=tk.X, pady=(0, 10))
        self._accent_bar(self.timer_card)

        tk.Label(
            self.timer_card,
            text="R E C O R D",
            font=self.fonts["badge"],
            fg=UI["blue"],
            bg=UI["card"],
        ).pack(pady=(8, 0))

        self.timer_display = tk.Label(
            self.timer_card,
            text="00:00:00",
            font=self.fonts["timer"],
            fg=UI["white"],
            bg=UI["card"],
        )
        self.timer_display.pack(pady=(2, 0))

        self.vu_canvas = tk.Canvas(self.timer_card, width=220, height=8, bg=UI["card"], highlightthickness=0)
        self.vu_canvas.pack(pady=(4, 0))
        self._draw_vu_idle()

        shortcut_hint = "Space / F9 / Ctrl+R" if IS_WINDOWS else "Space / F9 / Cmd+R"
        self.shortcut_hint = shortcut_hint
        self.timer_hint = tk.Label(
            self.timer_card,
            text=f"正在偵測螢幕與麥克風…  {shortcut_hint}",
            font=self.fonts["body"],
            fg=UI["muted"],
            bg=UI["card"],
            wraplength=500,
            justify="center",
        )
        self.timer_hint.pack(pady=(4, 0))

        self.record_row = tk.Frame(self.timer_card, bg=UI["card"])
        self.record_row.pack(fill=tk.X, padx=16, pady=(8, 10))
        self.pause_btn = AuraButton(
            self.record_row, text="暫停", style="Ghost.TButton", command=self.toggle_pause
        )
        self.record_btn = AuraButton(
            self.record_row,
            text="開始錄影",
            style="Primary.TButton",
            command=self.toggle_recording,
            state=tk.DISABLED,
        )
        self.record_btn.pack(fill=tk.X)

        settings_card = self._card(self.main_container)
        settings_card.pack(fill=tk.X, pady=(0, 10))
        tk.Label(
            settings_card, text="錄製", font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]
        ).pack(anchor="w", padx=14, pady=(8, 0))

        form = tk.Frame(settings_card, bg=UI["card"])
        form.pack(fill=tk.X, padx=14, pady=(0, 2))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        def labeled_combo(row, column, label, span=1):
            tk.Label(
                form, text=label, font=self.fonts["body"], fg=UI["muted"], bg=UI["card"], anchor="w"
            ).grid(row=row, column=column, sticky="w", padx=(8 if column else 0, 6), pady=3)
            combo = ttk.Combobox(form, style="App.TCombobox", state="readonly")
            combo.grid(row=row, column=column + 1, columnspan=span, sticky="ew", pady=3)
            return combo

        self.video_combo = labeled_combo(0, 0, "螢幕", span=2)
        video_action_frame = tk.Frame(form, bg=UI["card"])
        video_action_frame.grid(row=0, column=3, sticky="e", padx=(4, 0), pady=3)
        self.video_preview_btn = self._quiet_button(video_action_frame, "預覽", self._show_screen_preview)
        self.video_preview_btn.pack(side=tk.LEFT, padx=(0, 2))
        self.video_identify_btn = self._quiet_button(video_action_frame, "識別", self._flash_screen_identify)
        self.video_identify_btn.pack(side=tk.LEFT)
        self.audio_combo = labeled_combo(1, 0, "音效", span=2)
        audio_action_frame = tk.Frame(form, bg=UI["card"])
        audio_action_frame.grid(row=1, column=3, sticky="e", padx=(4, 0), pady=3)
        self.audio_test_btn = self._quiet_button(audio_action_frame, "測試", self._toggle_audio_test)
        self.audio_test_btn.pack(side=tk.LEFT, padx=(0, 2))
        self.audio_guide_btn = self._quiet_button(audio_action_frame, "指南", self._show_system_audio_guide)
        self.audio_guide_btn.pack(side=tk.LEFT)
        self.res_combo = labeled_combo(2, 0, "解析度")
        self.res_combo["values"] = [
            "原生（較吃資源）",
            "2K（長邊 2560）",
            "1080p（長邊 1920）",
            "720p（長邊 1280）",
        ]
        self.res_combo.current(self._saved_index("res_index", self.capture_advice["res_index"], 3))
        self.fps_combo = labeled_combo(2, 2, "幀率")
        self.fps_combo["values"] = ["30 FPS", "60 FPS（較吃資源）", "15 FPS（較省）"]
        self.fps_combo.current(self._saved_index("fps_index", self.capture_advice["fps_index"], 2))
        self.quality_combo = labeled_combo(3, 0, "畫質")
        self.quality_combo["values"] = ["標準", "較省", "較清晰"]
        self.quality_combo.current(self._saved_index("quality_index", 0, 2))
        self.format_combo = labeled_combo(3, 2, "格式")
        self.format_combo["values"] = ["MP4", "MOV"]
        self.format_combo.current(self._saved_index("format_index", 0, 1))
        self.area_combo = labeled_combo(4, 0, "範圍")
        self.limit_combo = labeled_combo(4, 2, "時限")
        self.limit_combo["values"] = ["不限制", "1 分鐘", "5 分鐘", "10 分鐘", "30 分鐘", "60 分鐘"]
        self.limit_combo.current(self._saved_index("limit_index", 0, 5))
        self.segment_combo = labeled_combo(5, 0, "分段")
        self.segment_combo["values"] = ["不分段", "每 5 分鐘", "每 10 分鐘", "每 30 分鐘"]
        self.segment_combo.current(self._saved_index("segment_index", 0, 3))
        tk.Label(
            form,
            text="長錄影才需要",
            font=self.fonts["badge"],
            fg=UI["muted"],
            bg=UI["card"],
            anchor="w",
        ).grid(row=5, column=2, columnspan=2, sticky="w", padx=(8, 0))

        area_row = tk.Frame(form, bg=UI["card"])
        area_row.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(0, 2))
        self.area_label = tk.Label(
            area_row, text="", font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"], anchor="w"
        )
        self.area_label.pack(side=tk.LEFT)
        self.window_btn = self._quiet_button(area_row, "選視窗", self._pick_window)
        self.window_btn.pack(side=tk.RIGHT, padx=(4, 0))
        self.reselect_btn = self._quiet_button(area_row, "重選範圍", self._pick_region)
        self.reselect_btn.pack(side=tk.RIGHT)
        self._update_area_label()

        accel_text = "使用硬體加速" if IS_MAC else ("使用 GPU 硬體加速" if IS_WINDOWS else "使用硬體加速")
        checks = tk.Frame(settings_card, bg=UI["card"])
        checks.pack(fill=tk.X, padx=14, pady=(0, 8))
        checks.columnconfigure(0, weight=1)
        checks.columnconfigure(1, weight=1)
        for index, (text, variable) in enumerate((
            (accel_text, self.hardware_accel_var),
            ("開始前倒數 3 秒", self.countdown_var),
            ("錄影時縮成小視窗", self.auto_mini_var),
            ("錄下游標", self.capture_cursor_var),
            ("截圖自動複製", self.auto_copy_screenshot_var),
            ("音效提示", self.sound_alert_var),
        )):
            AuraCheck(
                checks, text=text, variable=variable, command=self._save_capture_settings
            ).grid(row=index // 2, column=index % 2, sticky="w")

        # 即時畫面縮圖卡片
        self.preview_card = tk.Frame(settings_card, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1)
        self.preview_card.pack(fill=tk.X, padx=14, pady=(0, 10))

        preview_header = tk.Frame(self.preview_card, bg=UI["card"])
        preview_header.pack(fill=tk.X, padx=10, pady=(6, 4))

        self.lbl_preview_title = tk.Label(
            preview_header,
            text="畫面即時縮圖",
            font=self.fonts["badge"],
            fg=UI["muted"],
            bg=UI["card"],
            anchor="w",
        )
        self.lbl_preview_title.pack(side=tk.LEFT)

        preview_actions = tk.Frame(preview_header, bg=UI["card"])
        preview_actions.pack(side=tk.RIGHT)

        self._quiet_button(preview_actions, "全景對比 ⤢", self._show_screen_preview).pack(side=tk.LEFT, padx=(0, 4))
        self._quiet_button(preview_actions, "刷新 ↻", self._refresh_inline_preview).pack(side=tk.LEFT)

        self.preview_canvas_frame = tk.Frame(self.preview_card, bg="#0d0d11")
        self.preview_canvas_frame.pack(padx=10, pady=(0, 4))

        self.preview_canvas = tk.Canvas(
            self.preview_canvas_frame,
            width=288,
            height=162,
            bg="#0d0d11",
            highlightthickness=0,
            cursor="hand2",
        )
        self.preview_canvas.pack()
        self.preview_canvas.bind("<Button-1>", lambda _e: self._show_screen_preview())
        self._preview_photo = None

        self.lbl_preview_device = tk.Label(
            self.preview_card,
            text="點擊縮圖開啟多螢幕大圖對比 · 或點上方「識別」查看螢幕編號",
            font=self.fonts["badge"],
            fg=UI["muted"],
            bg=UI["card"],
            anchor="center",
        )
        self.lbl_preview_device.pack(fill=tk.X, padx=10, pady=(0, 6))

        for combo in (
            self.audio_combo, self.res_combo, self.fps_combo,
            self.quality_combo, self.format_combo, self.limit_combo, self.segment_combo,
        ):
            combo.bind("<<ComboboxSelected>>", lambda _e: self._save_capture_settings())
        self.video_combo.bind("<<ComboboxSelected>>", lambda _e: (self._save_capture_settings(), self._refresh_inline_preview(), self._refresh_window_target()))
        self.area_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_area_choice())

        self.recent_card = self._card(self.main_container)
        self.recent_card.pack(fill=tk.BOTH, expand=True)

        recent_header = tk.Frame(self.recent_card, bg=UI["card"])
        recent_header.pack(fill=tk.X, padx=8, pady=(8, 0))
        self.lbl_recent_title = tk.Label(
            recent_header, text="最近的錄影", font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]
        )
        self.lbl_recent_title.pack(side=tk.LEFT, padx=6)
        self._quiet_button(recent_header, "重新整理", self.refresh_recent_list).pack(side=tk.RIGHT)
        self.btn_play_last = self._quiet_button(recent_header, "播放最新", self.play_last_recording)
        self.btn_play_last.config(state=tk.DISABLED)
        self.btn_play_last.pack(side=tk.RIGHT)
        self._quiet_button(recent_header, "剪輯", self.open_editor).pack(side=tk.RIGHT)

        path_row = tk.Frame(self.recent_card, bg=UI["card"])
        path_row.pack(fill=tk.X, padx=8, pady=(0, 4))
        self.save_path_label = tk.Label(
            path_row, text="", font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"], anchor="w"
        )
        self.save_path_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self._quiet_button(path_row, "變更位置", self.change_output_folder).pack(side=tk.RIGHT)
        self._quiet_button(path_row, "開啟資料夾", self.open_output_folder).pack(side=tk.RIGHT)
        self._show_save_path()

        self.recent_wrap = tk.Frame(self.recent_card, bg=UI["card"])
        self.recent_wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.recent_canvas = tk.Canvas(
            self.recent_wrap, bg=UI["card"], highlightthickness=0, bd=0
        )
        self.recent_scroll = ttk.Scrollbar(
            self.recent_wrap,
            orient="vertical",
            style="App.Vertical.TScrollbar",
            command=self.recent_canvas.yview,
        )
        self.recent_list_frame = tk.Frame(self.recent_canvas, bg=UI["card"])
        self.recent_window = self.recent_canvas.create_window(
            (0, 0), window=self.recent_list_frame, anchor="nw"
        )
        self.recent_canvas.configure(yscrollcommand=self.recent_scroll.set)
        self.recent_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.recent_list_frame.bind("<Configure>", self._sync_recent_scroll)
        self.recent_canvas.bind("<Configure>", self._fit_recent_width)
        self.recent_wrap.bind("<Enter>", self._bind_recent_wheel)
        self.recent_wrap.bind("<Leave>", self._unbind_recent_wheel)

        self._build_mini_ui()

    def _build_mini_ui(self):
        """錄影中的浮動小條。黑底、玫瑰字，浮在畫面上還看得清楚。"""
        self.mini_container = tk.Frame(
            self.root, bg=UI["mini"], highlightbackground=UI["red"], highlightthickness=1
        )

        drag_handle = tk.Label(
            self.mini_container,
            text="⋮⋮",
            font=self.fonts["bold"],
            fg=UI["mini_muted"],
            bg=UI["mini"],
            cursor="fleur",
        )
        drag_handle.pack(side=tk.LEFT, padx=(8, 2))
        drag_handle.bind("<ButtonPress-1>", self._start_drag)
        drag_handle.bind("<B1-Motion>", self._on_drag)

        self.mini_time_label = tk.Label(
            self.mini_container,
            text="REC 00:00",
            font=self.fonts["mono"],
            fg=UI["red"],
            bg=UI["mini"],
        )
        self.mini_time_label.pack(side=tk.LEFT, padx=(4, 2))
        self.mini_time_label.bind("<ButtonPress-1>", self._start_drag)
        self.mini_time_label.bind("<B1-Motion>", self._on_drag)

        self.mini_vu_canvas = tk.Canvas(self.mini_container, width=32, height=10, bg=UI["mini"], highlightthickness=0)
        self.mini_vu_canvas.pack(side=tk.LEFT, padx=4)
        self._draw_mini_vu_idle()

        AuraButton(
            self.mini_container,
            text="停止",
            style="Stop.TButton",
            command=self.stop_recording,
        ).pack(side=tk.RIGHT, padx=(0, 8), pady=5)
        self.mini_pause_btn = AuraButton(
            self.mini_container, text="暫停", style="Ghost.TButton", command=self.toggle_pause
        )
        self.mini_pause_btn.pack(side=tk.RIGHT, padx=4, pady=5)
        self.mini_shot_btn = AuraButton(
            self.mini_container, text="截圖", style="Ghost.TButton", command=self.take_screenshot
        )
        self.mini_shot_btn.pack(side=tk.RIGHT, padx=3, pady=5)
        self.mini_expand_btn = AuraButton(
            self.mini_container, text="展開", style="Ghost.TButton", command=self._expand_from_mini
        )
        self.mini_expand_btn.pack(side=tk.RIGHT, padx=(2, 0), pady=5)

    def _start_drag(self, event):
        self.drag_x = event.x
        self.drag_y = event.y

    def _on_drag(self, event):
        x = self.root.winfo_x() + (event.x - self.drag_x)
        y = self.root.winfo_y() + (event.y - self.drag_y)
        self.root.geometry(f"+{x}+{y}")

    def _bind_shortcuts(self):
        # 跨平台快捷鍵 Space / F9 / Ctrl+R / Cmd+R
        self.root.bind_all("<F7>", lambda e: self.take_screenshot())
        self.root.bind_all("<F8>", lambda e: self.toggle_pause())
        self.root.bind_all("<F9>", lambda e: self.toggle_recording())
        self.root.bind_all("<Control-r>", lambda e: self.toggle_recording())
        self.root.bind_all("<Command-r>", lambda e: self.toggle_recording())
        self.root.bind_all("<Command-comma>", lambda e: self._show_preferences())
        self.root.bind_all("<Control-comma>", lambda e: self._show_preferences())
        self.root.bind_all("<Shift-Command-c>", lambda e: self.copy_latest_file())
        self.root.bind_all("<Shift-Control-c>", lambda e: self.copy_latest_file())
        self.root.bind("<space>", lambda e: self.toggle_recording())
        self.root.bind("<Escape>", self._on_escape)

    def _refresh_devices(self):
        """裝置掃描會呼叫 FFmpeg，放到背景，視窗才能先打開。"""
        self.video_combo["values"] = ["正在偵測裝置…"]
        self.video_combo.current(0)
        self.video_combo.config(state=tk.DISABLED)
        self.audio_combo["values"] = ["正在偵測裝置…"]
        self.audio_combo.current(0)
        self.audio_combo.config(state=tk.DISABLED)
        self.record_btn.config(state=tk.DISABLED)

        def work():
            missing = not self.recorder.ffmpeg_ok()
            v_devs, a_devs = ([], []) if missing else self.recorder.get_devices()
            try:
                self.root.after(0, lambda: self._apply_devices(v_devs, a_devs, missing))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _apply_devices(self, v_devs, a_devs, missing_ffmpeg):
        self.video_devices = v_devs
        self.audio_devices = a_devs

        if missing_ffmpeg:
            self.video_combo["values"] = ["找不到 FFmpeg"]
            self.video_combo.current(0)
            self.audio_combo["values"] = ["找不到 FFmpeg"]
            self.audio_combo.current(0)
            install = "brew install ffmpeg" if IS_MAC else "winget install Gyan.FFmpeg"
            self.timer_hint.config(text=f"找不到 FFmpeg。請先執行 {install}")
            self.record_btn.config(state=tk.DISABLED)
            return

        v_names = []
        screen_details = get_mac_screen_details() if IS_MAC else {}
        for d in v_devs:
            name = d["name"]
            low = name.lower()
            tag = ""
            if any(k in low for k in ("capture screen", "desktop", "螢幕", "display")):
                m = re.search(r"screen\s*(\d+)", low)
                s_idx = int(m.group(1)) if m else None
                if s_idx is not None and s_idx in screen_details:
                    tag = f" ({screen_details[s_idx]})"
                else:
                    tag = " (螢幕畫面)"
            elif any(k in low for k in ("camera", "webcam", "facetime", "鏡頭", "相機")):
                tag = " (視訊鏡頭)"
            v_names.append(f"[{d['index']}] {name}{tag}")

        self.video_combo["values"] = v_names or ["預設主螢幕"]
        screen_at = 0
        for i, name in enumerate(v_names):
            lowered = name.lower()
            if "螢幕畫面" in name or "capture screen" in lowered or "desktop" in lowered or "螢幕" in name:
                screen_at = i
                break
        saved_video = self._saved.get("video_device")
        if isinstance(saved_video, str):
            for idx, item in enumerate(v_names):
                if item == saved_video or (saved_video.startswith("[") and item.split("]")[0] == saved_video.split("]")[0]):
                    screen_at = idx
                    break
        self.video_combo.current(screen_at)
        busy = self.recorder.is_recording or self.countdown_active or self._stopping
        self.video_combo.config(state=tk.DISABLED if busy else "readonly")

        a_names = ["無音訊 (靜音)"]
        for d in a_devs:
            name = d["name"]
            low = name.lower()
            tag = ""
            if any(k in low for k in ("blackhole", "stereo mix", "立體聲混音", "teams audio", "loopback", "cable", "soundflower", "virtual")):
                tag = " (系統音效)"
            elif any(k in low for k in ("麥克風", "microphone", "mic", "built-in", "內建")):
                tag = " (麥克風)"
            a_names.append(f"[{d['index']}] {name}{tag}")

        self.audio_combo["values"] = a_names
        audio_at = 1 if len(a_names) > 1 else 0
        saved_audio = self._saved.get("audio_device")
        if isinstance(saved_audio, str):
            for idx, item in enumerate(a_names):
                if item == saved_audio or (saved_audio.startswith("[") and item.split("]")[0] == saved_audio.split("]")[0]):
                    audio_at = idx
                    break
        self.audio_combo.current(audio_at)
        self.audio_combo.config(state=tk.DISABLED if busy else "readonly")

        if not busy:
            self.timer_hint.config(text=self._idle_hint())
        if not self.recorder.is_recording and not self.countdown_active:
            self.record_btn.config(state=tk.NORMAL)
        if not busy:
            self._refresh_window_target()
            self._refresh_inline_preview()

    def _switch_to_mini_mode(self, origin=None):
        """收合為置頂懸浮膠囊。origin 是小條要出現的點座標。"""
        if not self.is_mini_mode:
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            if width >= 520 and height >= 640:
                self._normal_size = (width, height)
        self.is_mini_mode = True
        self.main_container.pack_forget()

        if origin is None:
            prev_x = self.root.winfo_x()
            prev_y = self.root.winfo_y()
        else:
            prev_x, prev_y = origin

        self.root.minsize(470, 48)
        self.root.geometry(f"470x48+{int(prev_x)}+{int(prev_y)}")
        self.root.resizable(False, False)
        self.root.config(menu="")
        self.root.attributes("-topmost", True)
        self.mini_container.pack(fill=tk.BOTH, expand=True)

    def _switch_to_normal_mode(self):
        """還原為標準視窗模式"""
        self.is_mini_mode = False
        self.mini_container.pack_forget()

        width, height = self._normal_size
        prev_x = self.root.winfo_x()
        prev_y = self.root.winfo_y()

        self.root.resizable(True, True)
        self.root.minsize(520, 700)
        self.root.geometry(f"{width}x{height}+{prev_x}+{prev_y}")
        self.root.attributes("-topmost", False)
        self.root.config(menu=self.menubar)
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

    def _on_escape(self, _event=None):
        if self.countdown_active:
            self._cancel_countdown()
            return "break"
        if self.is_mini_mode and not self._stopping:
            self._switch_to_normal_mode()
            return "break"

    def _expand_from_mini(self):
        if self.is_mini_mode and not self._stopping:
            self._switch_to_normal_mode()

    def _collapse_to_mini(self):
        if self.is_mini_mode or self._stopping or self.countdown_active:
            return
        if not self.recorder.is_recording:
            return
        self._switch_to_mini_mode()

    def _flag(self, key, default):
        if key not in self._saved:
            return default
        return bool(self._saved[key])

    def _saved_index(self, key, default, last):
        try:
            value = int(self._saved.get(key, default))
        except (TypeError, ValueError):
            return default
        if 0 <= value <= last:
            return value
        return default

    def _saved_region(self):
        if self._saved.get("area_mode") not in (1, 2):
            return None
        raw = self._saved.get("region")
        if not isinstance(raw, (list, tuple)) or len(raw) != 4:
            return None
        try:
            box = tuple(int(v) for v in raw)
        except (TypeError, ValueError):
            return None
        if box[2] < 2 or box[3] < 2:
            return None
        return box

    def _saved_window(self):
        if self._saved.get("area_mode") != 2:
            return None
        try:
            window_id = int(self._saved.get("window_id"))
        except (TypeError, ValueError):
            return None
        owner = self._saved.get("window_owner")
        title = self._saved.get("window_title")
        return {
            "id": window_id,
            "owner": owner if isinstance(owner, str) else "",
            "title": title if isinstance(title, str) else "",
        }

    def _area_mode(self):
        if self.capture_window and self.region:
            return 2
        if self.region:
            return 1
        return 0

    def _capture_screen_index(self):
        if not hasattr(self, "video_combo"):
            return 0
        return capture_screen_index(self.video_combo.get())

    def _mini_origin_outside(self, region):
        """小條放到這個範圍外面。放不下就回 None，沿用現在的位置。"""
        if not region:
            return None
        frame = display_frame(self._capture_screen_index())
        target = box_to_points(region, self._capture_screen_index())
        if frame is None or target is None:
            return None
        screen = (frame["x"], frame["y"], frame["w"], frame["h"])
        # 48 是小條高度，多留一點給標題列，避免還是壓到目標。
        return bar_origin(screen, target, 470, 80)

    def _update_area_label(self):
        mode = self._area_mode()
        if self.region and mode == 1:
            custom = f"自訂 {self.region[2]}×{self.region[3]}"
        else:
            custom = "自訂範圍"
        if mode == 2:
            owner = self.capture_window.get("owner") or "視窗"
            window = f"視窗 {owner}"
        else:
            window = "某個視窗"
        self.area_combo["values"] = ["整個螢幕", custom, window]
        self.area_combo.current(mode)
        if mode == 0:
            self.area_label.config(text="拖曳範圍，或選一個視窗")
            return
        _x, _y, w, h = self.region
        if mode == 1:
            self.area_label.config(text=f"{w}×{h} 像素，這個螢幕")
            return
        title = self.capture_window.get("title") or ""
        owner = self.capture_window.get("owner") or "視窗"
        name = owner if not title else f"{owner} — {title}"
        if len(name) > 28:
            name = name[:27] + "…"
        self.area_label.config(text=f"{name}　{w}×{h}，會跟著移動")

    def _on_area_choice(self):
        choice = self.area_combo.current()
        if choice == 1:
            self._pick_region()
            return
        if choice == 2:
            self._pick_window()
            return
        self.region = None
        self.capture_window = None
        self._update_area_label()
        self._save_capture_settings()

    def _pick_region(self):
        if self.recorder.is_recording or self.countdown_active:
            return
        rect = pick_screen_region(self.root)
        if rect is not None:
            self.capture_window = None
            self.region = rect
        self._update_area_label()
        self._save_capture_settings()

    def _source_is_screen(self):
        name = self.video_combo.get().lower() if hasattr(self, "video_combo") else ""
        return "screen" in name or "desktop" in name or "螢幕" in self.video_combo.get()

    def _pick_window(self):
        if self.recorder.is_recording or self.countdown_active:
            return
        if hasattr(self, "video_combo") and self.video_combo.get() and not self._source_is_screen():
            messagebox.showinfo("選視窗", "請先把來源改成螢幕，再選視窗。")
            self._update_area_label()
            return
        picked = pick_capture_window(self.root, self._capture_screen_index())
        if picked is not None:
            self.capture_window = {
                "id": picked["id"],
                "owner": picked["owner"],
                "title": picked["title"],
            }
            self.region = tuple(picked["box"])
        self._update_area_label()
        self._save_capture_settings()

    def _refresh_window_target(self):
        if not self.capture_window:
            return
        box, _error = resolve_window_box(self.capture_window["id"], self._capture_screen_index())
        if box:
            self.region = box
            self._update_area_label()
            return
        self.capture_window = None
        self._update_area_label()
        self._save_capture_settings()

    def _window_follow_box(self):
        """錄影執行緒來問現在該裁哪裡。不碰畫面元件。"""
        window = self.capture_window
        frame = display_frame(self._capture_screen_index())
        if not window or frame is None or not self.region:
            return None
        origin = window_capture_origin(window["id"], self._capture_screen_index())
        if origin is None:
            return None
        return follow_crop(
            origin[0], origin[1], self.region[2], self.region[3],
            int(frame["w"] * frame["scale"]), int(frame["h"] * frame["scale"]),
        )

    def _conceal_recorder(self):
        """全螢幕錄影時，讓這個程式不出現在正在錄的那塊螢幕上。"""
        saved = (self.root.winfo_x(), self.root.winfo_y(), self.is_mini_mode)
        origin = other_display_origin(self._capture_screen_index(), 470, 80)
        if origin is not None:
            self.root.withdraw()
            self.root.update_idletasks()
            return {"mode": "other", "origin": origin, "saved": saved}
        if self._arm_hidden_hotkeys():
            self.root.withdraw()
            self.root.update_idletasks()
            return {"mode": "withdraw", "saved": saved}
        self.root.geometry("+8000+8000")
        self.root.update_idletasks()
        return {"mode": "far", "saved": saved}

    def _arm_hidden_hotkeys(self):
        def on_key(name):
            if name == "f8":
                self.toggle_pause()
                return
            if name in {"f9", "esc"}:
                if self.countdown_active:
                    self._cancel_countdown()
                    return
                if self.recorder.is_recording and not self._stopping:
                    self.stop_recording()

        return self._hidden_hotkeys.arm(on_key)

    def _restore_conceal(self):
        self._hidden_hotkeys.disarm()
        conceal = self._record_conceal
        self._record_conceal = None
        if not conceal:
            return
        if conceal["mode"] in {"withdraw", "far"}:
            try:
                self.root.deiconify()
            except tk.TclError:
                pass
        if self.is_mini_mode:
            self._switch_to_normal_mode()
        saved = conceal.get("saved")
        if saved:
            x, y, _was_mini = saved
            try:
                self.root.geometry(f"+{int(x)}+{int(y)}")
            except tk.TclError:
                pass

    def _prepare_region(self):
        """開始錄或截圖前決定範圍。視窗會先重量位置。回傳 (可以繼續, 範圍或 None)。"""
        mode = self.area_combo.current() if hasattr(self, "area_combo") else 0
        if mode <= 0:
            return True, None
        if mode == 2 and self.capture_window:
            box, error = resolve_window_box(self.capture_window["id"], self._capture_screen_index())
            if error:
                messagebox.showwarning("選視窗", error)
                return False, None
            self.region = box
            self._update_area_label()
            return True, box
        return True, self.region

    def _save_capture_settings(self):
        video = self.video_combo.get()
        audio = self.audio_combo.get()
        payload = {
            "res_index": self.res_combo.current(),
            "fps_index": self.fps_combo.current(),
            "hardware_accel": bool(self.hardware_accel_var.get()),
            "countdown": bool(self.countdown_var.get()),
            "auto_mini": bool(self.auto_mini_var.get()),
            "capture_cursor": bool(self.capture_cursor_var.get()),
            "auto_copy_screenshot": bool(self.auto_copy_screenshot_var.get()),
            "sound_alerts": bool(self.sound_alert_var.get()),
            "quality_index": self.quality_combo.current(),
            "format_index": self.format_combo.current(),
            "limit_index": self.limit_combo.current(),
            "segment_index": self.segment_combo.current(),
            "area_mode": self.area_combo.current(),
            "region": list(self.region) if self.region else None,
            "window_id": self.capture_window["id"] if self.capture_window else None,
            "window_owner": self.capture_window.get("owner", "") if self.capture_window else "",
            "window_title": self.capture_window.get("title", "") if self.capture_window else "",
        }
        if video and "偵測" not in video and "找不到" not in video:
            payload["video_device"] = video
        if audio and "偵測" not in audio and "找不到" not in audio:
            payload["audio_device"] = audio
        save_settings(payload)
        self._saved.update(payload)
        if not self.recorder.is_recording and not self.countdown_active:
            self.timer_hint.config(text=self._idle_hint())

    def _segment_seconds(self):
        return {1: 300, 2: 600, 3: 1800}.get(self.segment_combo.current())

    def toggle_pause(self):
        if self._stopping or self.countdown_active or not self.recorder.is_recording:
            return
        if self.recorder.paused:
            ok, msg = self.recorder.resume_recording()
        else:
            ok, msg = self.recorder.pause_recording()
        if not ok:
            messagebox.showwarning("暫停沒有成功", msg)
            return
        self._sync_pause_button()

    def _sync_pause_button(self):
        paused = bool(self.recorder.paused)
        label = "繼續" if paused else "暫停"
        self.pause_btn.config(text=label)
        if hasattr(self, "mini_pause_btn"):
            self.mini_pause_btn.config(text=label)
        if paused:
            self.status_badge.config(text="●  暫停", fg=UI["warn"])
            self.timer_display.config(fg=UI["warn"])
            self.timer_hint.config(text="已暫停。F8 繼續，或按停止結束")
            self.mini_time_label.config(fg=UI["warn"])
            self._draw_vu_idle()
            self._draw_mini_vu_idle()
        elif self.recorder.is_recording:
            self.status_badge.config(text="●  錄製中", fg=UI["red"])
            self.timer_display.config(fg=UI["red"])
            self.timer_hint.config(text=self._recording_hint())
            self.mini_time_label.config(fg=UI["red"])

    def _layout_record_buttons(self, recording):
        self.pause_btn.pack_forget()
        self.record_btn.pack_forget()
        if recording:
            self.pause_btn.config(text="繼續" if self.recorder.paused else "暫停")
            self.pause_btn.pack(side=tk.LEFT, padx=(0, 8))
            self.record_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        else:
            self.record_btn.pack(fill=tk.X)

    def _play_alert(self, sound_type):
        if getattr(self, "sound_alert_var", None) is None or self.sound_alert_var.get():
            play_system_alert(sound_type)

    def toggle_recording(self):
        if self.countdown_active:
            self._cancel_countdown()
            return

        if self.recorder.is_recording:
            self.stop_recording()
        else:
            if self.countdown_var.get():
                self._start_countdown_and_record()
            else:
                self.start_recording()

    def _start_countdown_and_record(self):
        """執行 3 秒倒數準備動畫。再按一次或按 Esc 可以取消。"""
        self._countdown_token = getattr(self, "_countdown_token", 0) + 1
        token = self._countdown_token
        self.countdown_active = True
        self.record_btn.config(text="取消", state=tk.NORMAL)
        self.shot_btn.config(state=tk.DISABLED)
        self._set_capture_locked(True)
        self.timer_hint.config(text="再按一次或按 Esc 取消")

        def count_step(val):
            if token != self._countdown_token or not self.countdown_active:
                return
            if val > 0:
                self.timer_display.config(text=str(val), fg=UI["warn"])
                self.status_badge.config(text=f"●  倒數 {val}", fg=UI["warn"])
                self._play_alert("ready")
                self.root.after(1000, lambda: count_step(val - 1))
            else:
                self.countdown_active = False
                self.record_btn.config(text="開始錄影", style="Primary.TButton", state=tk.NORMAL)
                self.start_recording()

        count_step(3)

    def _cancel_countdown(self):
        if not self.countdown_active:
            return
        self.countdown_active = False
        self._countdown_token = getattr(self, "_countdown_token", 0) + 1
        self._update_ui_state(recording=False)
        self.record_btn.config(state=tk.NORMAL)
        self.timer_hint.config(text="已取消倒數")

    def _confirm_disk_space(self):
        free = free_disk_bytes(self.recorder.output_dir)
        if free is None or free >= LOW_DISK_BYTES:
            return True
        mb = max(0, free // (1024 * 1024))
        return messagebox.askyesno("空間不多", f"這個磁碟剩下約 {mb} MB。還是要開始錄影嗎？")

    def start_recording(self):
        if not self._confirm_disk_space():
            self._set_capture_locked(False)
            if not self.recorder.is_recording:
                self.record_btn.config(text="開始錄影", style="Primary.TButton", state=tk.NORMAL)
                self.shot_btn.config(state=tk.NORMAL)
                self.timer_display.config(text="00:00:00", fg=UI["white"])
                self.status_badge.config(text="●  就緒", fg=UI["ok"])
                self.timer_hint.config(text=self._idle_hint())
            return
        v_idx = None
        if self.video_combo.current() >= 0 and self.video_devices:
            v_idx = self.video_devices[self.video_combo.current()]["index"]

        a_idx = None
        a_cur = self.audio_combo.current()
        if a_cur > 0 and self.audio_devices:
            a_idx = self.audio_devices[a_cur - 1]["index"]

        res_map = {0: "native", 1: "2K", 2: "1080p", 3: "720p"}
        resolution = res_map.get(self.res_combo.current(), "native")

        fps_map = {0: 30, 1: 60, 2: 15}
        fps = fps_map.get(self.fps_combo.current(), 30)

        use_accel = self.hardware_accel_var.get()
        quality_map = {0: "standard", 1: "economy", 2: "high"}
        quality = quality_map.get(self.quality_combo.current(), "standard")
        container = "mov" if self.format_combo.current() == 1 else "mp4"
        limit_map = {1: 60, 2: 300, 3: 600, 4: 1800, 5: 3600}
        self._auto_stop_sec = limit_map.get(self.limit_combo.current())
        self._segment_sec = self._segment_seconds()
        ready, region = self._prepare_region()
        if not ready:
            self._set_capture_locked(False)
            self.record_btn.config(text="開始錄影", style="Primary.TButton", state=tk.NORMAL)
            return

        label = None
        follow = None
        if self.area_combo.current() == 2 and self.capture_window:
            label = self.capture_window.get("owner") or ""
            if not IS_WINDOWS:
                follow = self._window_follow_box
        hidden_for_record = False
        parked_at = None
        conceal = None
        if region is None:
            conceal = self._conceal_recorder()
        elif self.auto_mini_var.get() and not self.is_mini_mode:
            parked_at = (self.root.winfo_x(), self.root.winfo_y())
            outside = self._mini_origin_outside(region)
            if outside:
                parked_at = outside
            self.root.withdraw()
            hidden_for_record = True
            self.root.update_idletasks()
            if self.area_combo.current() == 2 and self.capture_window:
                box, error = resolve_window_box(
                    self.capture_window["id"], self._capture_screen_index()
                )
                if error:
                    self.root.deiconify()
                    messagebox.showwarning("選視窗", error)
                    self._set_capture_locked(False)
                    self.record_btn.config(text="開始錄影", style="Primary.TButton", state=tk.NORMAL)
                    return
                self.region = box
                region = box
                self._update_area_label()
                outside = self._mini_origin_outside(region)
                if outside:
                    parked_at = outside
        self._play_alert("start")
        ok, msg = self.recorder.start_recording(
            video_idx=v_idx,
            audio_idx=a_idx,
            fps=fps,
            resolution=resolution,
            use_hardware_accel=use_accel,
            capture_cursor=self.capture_cursor_var.get(),
            region=region,
            quality=quality,
            container=container,
            segment_sec=self._segment_sec,
            label=label,
            follow=follow,
            prefix=self._saved.get("filename_prefix"),
        )

        if not ok:
            self._restore_conceal()
            if hidden_for_record:
                self.root.deiconify()
            self._segment_sec = None
            release_awake()
            messagebox.showerror("錄影啟動失敗", msg)
            self._update_ui_state(recording=False)
            return

        if self.recorder.process is not None:
            hold_awake(self.recorder.process.pid)
        if conceal is not None:
            self._record_conceal = conceal
            self._pending_mini = False
            if conceal["mode"] == "other":
                self._switch_to_mini_mode(conceal["origin"])
                self.root.deiconify()
        elif hidden_for_record:
            self._switch_to_mini_mode(parked_at)
            self.root.deiconify()
            self._pending_mini = False
        else:
            self._pending_mini = self.auto_mini_var.get()
        self._update_ui_state(recording=True)
        self.timer_hint.config(text="正在確認錄影有順利開始…")
        self.root.after(800, self._confirm_recording_started)

    def _check_recorder_health(self):
        """FFmpeg 若中途自己結束，把錯誤顯示出來，不要假裝還在錄。"""
        if self._stopping or not self.recorder.is_recording:
            return
        result = self.recorder.consume_exit()
        if result is None:
            return
        self._finish_stop(*result, offer_editor=False)

    def _confirm_recording_started(self):
        if self._stopping or not self.recorder.is_recording:
            return
        result = self.recorder.consume_exit()
        if result is not None:
            self._finish_stop(*result, offer_editor=False)
            return
        if self._pending_mini and not self.is_mini_mode:
            self._pending_mini = False
            self._switch_to_mini_mode()
        self.timer_hint.config(text=self._recording_hint())

    def stop_recording(self):
        if not self.recorder.is_recording or self._stopping:
            return

        self._stopping = True
        self._pending_mini = False
        self.status_badge.config(text="●  正在儲存", fg=UI["warn"])
        self.record_btn.config(state=tk.DISABLED)
        self.root.update_idletasks()

        def work():
            ok, msg = self.recorder.stop_recording()
            self.root.after(0, lambda: self._finish_stop(ok, msg, offer_editor=True))

        threading.Thread(target=work, daemon=True).start()

    def _finish_stop(self, ok, msg, offer_editor):
        self._stopping = False
        release_awake()
        self._play_alert("stop")
        self._restore_conceal()

        if self.is_mini_mode:
            self._switch_to_normal_mode()

        self._segment_sec = None
        self._update_ui_state(recording=False)
        self.refresh_recent_list()
        self.record_btn.config(state=tk.NORMAL)

        if ok:
            self.btn_play_last.config(state=tk.NORMAL)
            name = Path(msg).name
            parts = self.recorder.recorded_parts()
            if len(parts) > 1:
                self.timer_hint.config(text=f"已存成 {len(parts)} 個檔")
            else:
                self.timer_hint.config(text=f"已儲存 {name}")
            if offer_editor:
                self._show_record_completed(msg)
        else:
            messagebox.showwarning("錄影沒有完成", msg)

    def _output_size_text(self):
        total = self.recorder.output_size_bytes()
        if total <= 0:
            return ""
        return format_bytes(total)

    def _recording_hint(self):
        parts = ["錄製中。"]
        size = self._output_size_text()
        if size:
            parts.append(f"{size}。")
        if self._segment_sec:
            parts.append(f"每 {self._segment_sec // 60} 分鐘一個檔。")
        if self._auto_stop_sec:
            parts.append(f"{self._auto_stop_sec // 60} 分鐘後自動停止。")
        conceal = self._record_conceal or {}
        if conceal.get("mode") == "withdraw":
            parts.append("視窗已收起。F9 或 Esc 停止")
        elif conceal.get("mode") == "other":
            parts.append("程式在另一個螢幕。")
            parts.append(f"F8 暫停，{self.shortcut_hint} 停止")
        else:
            parts.append(f"F8 暫停，{self.shortcut_hint} 停止")
        return "".join(parts)

    def _set_capture_locked(self, locked):
        state = tk.DISABLED if locked else "readonly"
        for combo in (
            self.video_combo, self.audio_combo, self.res_combo, self.fps_combo,
            self.area_combo, self.quality_combo, self.format_combo, self.limit_combo,
            self.segment_combo,
        ):
            combo.config(state=state)
        for button_name in ("reselect_btn", "window_btn", "video_preview_btn", "video_identify_btn"):
            button = getattr(self, button_name, None)
            if button is not None:
                button.config(state=tk.DISABLED if locked else tk.NORMAL)

    def _update_ui_state(self, recording=False):
        if recording:
            self.status_badge.config(text="●  錄製中", fg=UI["red"])
            self.record_btn.config(text="停止錄影", style="Stop.TButton")
            self._layout_record_buttons(True)
            self.timer_display.config(fg=UI["red"])
            self.timer_hint.config(text=self._recording_hint())
            self._set_capture_locked(True)
            if not self._shooting:
                self.shot_btn.config(state=tk.NORMAL)
        else:
            self.status_badge.config(text="●  就緒", fg=UI["ok"])
            self.record_btn.config(text="開始錄影", style="Primary.TButton")
            self._layout_record_buttons(False)
            self.timer_display.config(text="00:00:00", fg=UI["white"])
            self.timer_hint.config(text=self._idle_hint())
            self._draw_vu_idle()
            self._draw_mini_vu_idle()
            self._set_capture_locked(False)
            if not self._shooting:
                self.shot_btn.config(state=tk.NORMAL)

    def _draw_vu_idle(self, muted=False):
        """繪製待機或靜音狀態的 VU 電平點"""
        if not hasattr(self, 'vu_canvas'):
            return
        self.vu_canvas.delete("all")
        w, h = 220, 8
        bar_count = 16
        bar_w = 8
        gap = (w - (bar_count * bar_w)) / (bar_count + 1)
        fill_color = "#1f2335" if muted else UI["meter_idle"]
        for i in range(bar_count):
            x = gap + i * (bar_w + gap)
            self.vu_canvas.create_rectangle(x, 2, x + bar_w, h, fill=fill_color, outline="")

    def _draw_mini_vu_idle(self, muted=False):
        """繪製迷你懸浮膠囊的靜態電平點"""
        if not hasattr(self, 'mini_vu_canvas'):
            return
        self.mini_vu_canvas.delete("all")
        bar_count = 4
        bar_w = 4
        gap = 3
        fill_color = "#1f2335" if muted else UI["meter_idle"]
        for i in range(bar_count):
            x = 2 + i * (bar_w + gap)
            self.mini_vu_canvas.create_rectangle(x, 4, x + bar_w, 10, fill=fill_color, outline="")

    def _toggle_audio_test(self):
        if self.recorder.is_recording or self.countdown_active:
            return
        if getattr(self, "_audio_testing", False):
            self._stop_audio_test()
            return

        if self.audio_combo.current() <= 0:
            messagebox.showinfo("提示", "目前選擇了「無音訊 (靜音)」，請先選擇麥克風或音訊設備！")
            return

        self._audio_testing = True
        self.audio_test_btn.config(text="停止")
        self.timer_hint.config(text="● 正在測試音訊收音… 請對著麥克風說話（約 5 秒後結束）")
        self._audio_test_ticks = 0

        def _step_test():
            if not getattr(self, "_audio_testing", False):
                return
            self._audio_test_ticks += 1
            if self._audio_test_ticks > 25:
                self._stop_audio_test()
                return
            self._draw_vu_active(self._audio_test_ticks)
            self.root.after(200, _step_test)

        self.root.after(100, _step_test)

    def _stop_audio_test(self):
        self._audio_testing = False
        self.audio_test_btn.config(text="測試")
        self._draw_vu_idle()
        if not self.recorder.is_recording:
            self.timer_hint.config(text=self._idle_hint())

    def _capture_kbps(self):
        res_map = {0: "native", 1: "2K", 2: "1080p", 3: "720p"}
        resolution = res_map.get(self.res_combo.current(), "1080p")
        quality_scale = {1: 0.7, 2: 1.35}.get(self.quality_combo.current(), 1.0)
        video_k = max(280, int(capture_bitrate_k(resolution, machine_profile()) * quality_scale))
        audio_k = 96 if self.audio_combo.current() > 0 else 0
        return video_k, audio_k

    def _size_estimate_text(self):
        video_k, audio_k = self._capture_kbps()
        per_min = (video_k + audio_k) * 60 / 8 / 1024
        return f"約 {max(1, round(per_min))} MB/分"

    def _selection_label(self):
        """準備錄影時顯示目前的解析度。和建議相同才保留順暢或平衡。"""
        res = {0: "原生", 1: "2K", 2: "1080p", 3: "720p"}.get(self.res_combo.current(), "1080p")
        fps = {0: "30 FPS", 1: "60 FPS", 2: "15 FPS"}.get(self.fps_combo.current(), "30 FPS")
        advice = self.capture_advice
        if (
            self.res_combo.current() == advice["res_index"]
            and self.fps_combo.current() == advice["fps_index"]
        ):
            return advice["label"]
        return f"{res} / {fps}"

    def _idle_hint(self):
        remain = disk_time_text(free_disk_bytes(self.recorder.output_dir), sum(self._capture_kbps()) * 1000)
        tail = remain or self.recorder.output_dir.name
        return f"{self._selection_label()}  ·  {self._size_estimate_text()}  ·  {tail}"

    def _draw_vu_active(self, tick_count):
        """只重畫看得到的那一條，錄影時少佔主執行緒。"""
        if self.is_mini_mode:
            self._draw_mini_vu_active(tick_count)
        else:
            self._draw_main_vu_active(tick_count)

    def _draw_main_vu_active(self, tick_count):
        if hasattr(self, 'vu_canvas'):
            self.vu_canvas.delete("all")
            w, h = 220, 8
            bar_count = 16
            bar_w = 8
            gap = (w - (bar_count * bar_w)) / (bar_count + 1)
            for i in range(bar_count):
                if i < 8:
                    color = UI["meter_low"]
                elif i < 13:
                    color = UI["meter_mid"]
                else:
                    color = UI["meter_high"]
                wave = math.sin((tick_count * 0.35) + i * 0.55) * 0.5 + 0.5
                level = min(1.0, max(0.25, wave))
                if level < 0.45 and i > 6:
                    color = UI["meter_idle"]
                x = gap + i * (bar_w + gap)
                self.vu_canvas.create_rectangle(x, 1, x + bar_w, h, fill=color, outline="")

    def _draw_mini_vu_active(self, tick_count):
        if hasattr(self, 'mini_vu_canvas'):
            self.mini_vu_canvas.delete("all")
            bar_count = 4
            bar_w = 4
            gap = 3
            colors = [UI["meter_low"], UI["meter_low"], UI["meter_mid"], UI["meter_high"]]
            for i in range(bar_count):
                wave = math.sin((tick_count * 0.45) + i * 0.75) * 0.5 + 0.5
                color = colors[i] if wave > 0.35 else UI["meter_idle"]
                x = 2 + i * (bar_w + gap)
                self.mini_vu_canvas.create_rectangle(x, 2, x + bar_w, 10, fill=color, outline="")

    def _timer_tick(self):
        self.vu_tick_count = getattr(self, 'vu_tick_count', 0) + 1
        if self.recorder.is_recording and not self._stopping:
            proc = self.recorder.process
            if proc is not None and proc.poll() is not None:
                self._check_recorder_health()
        if self.recorder.is_recording:
            sec = self.recorder.get_duration()
            hrs = sec // 3600
            mins = (sec % 3600) // 60
            s = sec % 60
            time_str = f"{hrs:02d}:{mins:02d}:{s:02d}"
            self.timer_display.config(text=time_str)

            prefix = "PAUSE" if self.recorder.paused else "REC"
            clock = f"{mins:02d}:{s:02d}" if hrs == 0 else f"{hrs:02d}:{mins:02d}:{s:02d}"
            size = self._output_size_text()
            mini_str = f"{prefix} {clock}  {size}" if size else f"{prefix} {clock}"
            self.mini_time_label.config(text=mini_str)
            if (
                self._auto_stop_sec
                and sec >= self._auto_stop_sec
                and not self._stopping
                and not self.recorder.paused
            ):
                self.stop_recording()
            if self.vu_tick_count % 10 == 0 and not self._stopping:
                free_bytes = free_disk_bytes(self.recorder.output_dir)
                if free_bytes < 150 * 1024 * 1024:
                    self.stop_recording()
                    messagebox.showwarning(
                        "磁碟空間即將耗盡",
                        f"儲存目錄磁碟剩餘空間不足 150 MB（目前僅剩 {format_bytes(free_bytes)}）。\n"
                        "為保護資料完整性，已自動安全結束並封裝錄影！",
                    )
            if self.vu_tick_count % 4 == 0 and not self._stopping:
                self.timer_hint.config(text=self._recording_hint())
            if self.recorder.paused:
                self._draw_vu_idle()
                self._draw_mini_vu_idle()
            else:
                has_audio = (self.audio_combo.current() > 0)
                if has_audio:
                    self._draw_vu_active(self.vu_tick_count)
                else:
                    self._draw_vu_idle(muted=True)
                    self._draw_mini_vu_idle(muted=True)
            interval = 280
        else:
            if getattr(self, '_was_recording', False):
                self._draw_vu_idle()
                self._draw_mini_vu_idle()
            if (
                self.vu_tick_count % 30 == 0
                and not self.countdown_active
                and not self._shooting
                and "偵測" not in self.video_combo.get()
            ):
                self.timer_hint.config(text=self._idle_hint())
            interval = 500

        self._was_recording = self.recorder.is_recording
        self.root.after(interval, self._timer_tick)

    def open_output_folder(self):
        """在檔案總管 / Finder 中開啟儲存路徑"""
        open_file_or_dir(str(self.recorder.output_dir))

    def change_output_folder(self):
        """選擇新的錄影儲存目錄"""
        chosen = filedialog.askdirectory(initialdir=str(self.recorder.output_dir), title="選擇錄影儲存目錄")
        if chosen:
            self.recorder.output_dir = Path(chosen)
            save_settings({"output_dir": str(self.recorder.output_dir)})
            self._show_save_path()
            self.timer_hint.config(text=self._idle_hint())
            self.refresh_recent_list()

    def play_last_recording(self):
        """以系統預設播放器開啟最新錄製的影片"""
        if self.recorder.last_recorded_file and os.path.exists(self.recorder.last_recorded_file):
            open_file_or_dir(str(self.recorder.last_recorded_file))
        else:
            messagebox.showinfo("提示", "尚未有可播放的錄影檔")

    def _newest_saved_file(self):
        newest = None
        newest_mtime = -1
        try:
            patterns = ("*.mp4", "*.mov", "*.mkv", "*.webm", "*.gif", "*.png", "*.m4a", "*.mp3", "*.wav")
            for pattern in patterns:
                for path in self.recorder.output_dir.glob(pattern):
                    if self._file_is_open_recording(path):
                        continue
                    mtime = path.stat().st_mtime
                    if mtime > newest_mtime:
                        newest = path
                        newest_mtime = mtime
        except OSError:
            return None
        return newest

    def copy_latest_file(self):
        path = self._newest_saved_file()
        if path is None:
            messagebox.showinfo("複製檔案", "還沒有可複製的檔案。")
            return "break"
        if copy_file(path):
            if not self.recorder.is_recording and not self.countdown_active:
                self.timer_hint.config(text=f"已複製 {path.name}")
            return "break"
        messagebox.showwarning("複製檔案", "沒有放到剪貼簿。")
        return "break"

    def open_editor(self, video_path=None):
        """開啟影片剪輯編輯視窗"""
        target = video_path or self.recorder.last_recorded_file
        VideoEditorWindow(self.root, video_path=target, on_close=self.refresh_recent_list)

    def open_web_studio(self):
        """開啟獨立的 AURA REC 工作站檔。官網不在這個檔案裡。"""
        # 相容三種執行情境：純腳本 / macOS .app / Windows PyInstaller exe
        import sys
        if getattr(sys, "frozen", False):
            # PyInstaller onefile：資源解壓在 sys._MEIPASS
            base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        else:
            base_dir = Path(__file__).resolve().parent
        candidates = [
            base_dir / "AURA-REC.html",
            base_dir / "web_studio" / "download" / "AURA-REC.html",
        ]
        for studio_path in candidates:
            if studio_path.is_file():
                open_file_or_dir(str(studio_path))
                return
        messagebox.showinfo(
            "找不到工作站",
            "找不到 AURA-REC.html。\n請從官網下載那一個檔案，或確認 web_studio/download/AURA-REC.html 還在。",
        )

    def _show_record_completed(self, file_path):
        """錄影完成後的即時操作視窗"""
        p = Path(file_path)
        win = tk.Toplevel(self.root)
        win.title("錄影已完成 — AURA REC")
        win.geometry("500x320")
        win.resizable(False, False)
        win.configure(bg=UI["bg"])
        win.transient(self.root)

        card = tk.Frame(win, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        self._accent_bar(card)

        inner = tk.Frame(card, bg=UI["card"])
        inner.pack(fill=tk.BOTH, expand=True, padx=18, pady=14)

        header = tk.Frame(inner, bg=UI["card"])
        header.pack(fill=tk.X, pady=(0, 6))
        tk.Label(header, text="●", font=self.fonts["bold"], fg=UI["ok"], bg=UI["card"]).pack(side=tk.LEFT)
        tk.Label(header, text=" 錄影已儲存完成", font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]).pack(side=tk.LEFT)

        try:
            sz_mb = p.stat().st_size / (1024 * 1024)
            size_str = f"{sz_mb:.1f} MB" if sz_mb >= 0.1 else f"{p.stat().st_size // 1024} KB"
        except Exception:
            size_str = ""

        name_lbl = tk.Label(
            inner, text=p.name, font=self.fonts["subtitle"], fg=UI["blue"], bg=UI["card"],
            anchor="w", wraplength=440, justify="left"
        )
        name_lbl.pack(fill=tk.X, pady=(2, 2))

        meta_str = f"檔案大小：{size_str}  ·  儲存於：{p.parent.name}/"
        tk.Label(
            inner, text=meta_str, font=self.fonts["body"], fg=UI["muted"], bg=UI["card"], anchor="w"
        ).pack(fill=tk.X, pady=(0, 14))

        actions = tk.Frame(inner, bg=UI["card"])
        actions.pack(fill=tk.X, pady=(0, 6))

        def do_edit():
            win.destroy()
            self.open_editor(str(p))

        def do_play():
            open_file_or_dir(str(p))

        def do_reveal():
            open_file_or_dir(str(p), reveal=True)

        def do_copy():
            if copy_file(p):
                self.timer_hint.config(text=f"已複製 {p.name}")

        AuraButton(actions, text="剪輯影片", style="Primary.TButton", command=do_edit).pack(fill=tk.X, pady=(0, 8))

        sub_btns = tk.Frame(actions, bg=UI["card"])
        sub_btns.pack(fill=tk.X)
        self._quiet_button(sub_btns, "播放", do_play).pack(side=tk.LEFT, padx=(0, 4))
        self._quiet_button(sub_btns, "在資料夾中顯示", do_reveal).pack(side=tk.LEFT, padx=4)
        self._quiet_button(sub_btns, "複製檔案", do_copy).pack(side=tk.LEFT, padx=4)
        self._quiet_button(sub_btns, "完成", win.destroy).pack(side=tk.RIGHT)

    def _flash_screen_identify(self):
        """在所有實體螢幕中央瞬間閃爍大型發光識別編號卡"""
        try:
            flash_screen_badges(self.root, duration_ms=2500)
        except Exception as e:
            print(f"[Error] flash_screen_badges failed: {e}")

    def _refresh_inline_preview(self):
        """非同步抓取當前選取螢幕/攝影機的縮圖並更新卡片"""
        if not hasattr(self, "video_combo") or not hasattr(self, "preview_canvas"):
            return
        if self.recorder.is_recording or self.countdown_active or self._stopping:
            return

        item = self.video_combo.get()
        if not item or "正在偵測" in item or "找不到" in item:
            return

        disp_title = item.split("] ")[-1] if "] " in item else item
        if hasattr(self, "lbl_preview_title"):
            self.lbl_preview_title.config(text=f"畫面縮圖：{disp_title} (更新中…)")

        def worker():
            try:
                ppm_data = capture_device_preview_ppm(
                    self.recorder.ffmpeg_bin, item, width=288, height=162
                )
            except Exception:
                ppm_data = None

            def update_ui():
                if not hasattr(self, "preview_canvas") or not self.preview_canvas.winfo_exists():
                    return
                if ppm_data:
                    try:
                        self._preview_photo = tk.PhotoImage(data=ppm_data)
                        self.preview_canvas.delete("all")
                        self.preview_canvas.create_image(144, 81, image=self._preview_photo)
                        if hasattr(self, "lbl_preview_title"):
                            self.lbl_preview_title.config(text=f"畫面縮圖：{disp_title}")
                        return
                    except Exception:
                        pass
                if hasattr(self, "lbl_preview_title"):
                    self.lbl_preview_title.config(text=f"畫面縮圖：{disp_title}")

            self.root.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def _show_screen_preview(self):
        """開啟所有螢幕與鏡頭即時預覽畫廊對話框，支援一鍵切換與實體螢幕識別"""
        if self.recorder.is_recording or self.countdown_active or self._stopping:
            messagebox.showinfo("正在錄影", "錄影進行中無法變更預覽螢幕。")
            return

        win = tk.Toplevel(self.root)
        win.title("所有畫面即時預覽與切換 — AURA REC")
        win.configure(bg=UI["bg"])
        win.transient(self.root)

        win_w = 780
        win_h = 580
        win.minsize(580, 460)
        self.root.update_idletasks()
        rx = max(0, self.root.winfo_rootx() + (self.root.winfo_width() - win_w) // 2)
        ry = max(0, self.root.winfo_rooty() + (self.root.winfo_height() - win_h) // 2)
        win.geometry(f"{win_w}x{win_h}+{rx}+{ry}")

        outer_card = tk.Frame(win, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1)
        outer_card.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)
        self._accent_bar(outer_card)

        # 頂部控制列
        top_bar = tk.Frame(outer_card, bg=UI["card"])
        top_bar.pack(fill=tk.X, padx=16, pady=(12, 8))

        top_left = tk.Frame(top_bar, bg=UI["card"])
        top_left.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(
            top_left, text="SCREEN PREVIEW", font=self.fonts["badge"], fg=UI["blue"], bg=UI["card"]
        ).pack(anchor="w")
        tk.Label(
            top_left, text="所有螢幕與鏡頭即時畫面", font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]
        ).pack(anchor="w", pady=(2, 0))
        tk.Label(
            top_left, text="點選下方任一螢幕卡片即可直接切換錄製來源", font=self.fonts["body"], fg=UI["muted"], bg=UI["card"]
        ).pack(anchor="w")

        top_right = tk.Frame(top_bar, bg=UI["card"])
        top_right.pack(side=tk.RIGHT)

        def do_identify():
            self._flash_screen_identify()

        self._quiet_button(top_right, "實體螢幕識別 🔔", do_identify).pack(side=tk.LEFT, padx=(0, 6))
        refresh_btn = self._quiet_button(top_right, "重新擷取 ↻", lambda: load_all_thumbnails())
        refresh_btn.pack(side=tk.LEFT, padx=(0, 6))
        self._quiet_button(top_right, "關閉 ✕", win.destroy).pack(side=tk.LEFT)

        # 滾動預覽區域
        scroll_container = tk.Frame(outer_card, bg=UI["card"])
        scroll_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=(4, 12))

        canvas = tk.Canvas(scroll_container, bg=UI["card"], highlightthickness=0, bd=0)
        v_scroll = ttk.Scrollbar(scroll_container, orient=tk.VERTICAL, command=canvas.yview)
        cards_grid = tk.Frame(canvas, bg=UI["card"])

        canvas_window = canvas.create_window((0, 0), window=cards_grid, anchor="nw")

        def on_configure(_e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_resize(event):
            canvas.itemconfig(canvas_window, width=event.width)

        cards_grid.bind("<Configure>", on_configure)
        canvas.bind("<Configure>", on_canvas_resize)
        canvas.configure(xscrollcommand=None, yscrollcommand=v_scroll.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        combo_values = list(self.video_combo["values"]) if hasattr(self, "video_combo") else []
        current_idx = self.video_combo.current() if hasattr(self, "video_combo") else 0

        photo_cache = []

        def select_and_close(target_index):
            if 0 <= target_index < len(combo_values):
                self.video_combo.current(target_index)
                self._save_capture_settings()
                self._refresh_inline_preview()
                self._refresh_window_target()
            win.destroy()

        card_widgets = []

        for idx, item_text in enumerate(combo_values):
            if "正在偵測" in item_text or "找不到" in item_text:
                continue

            is_selected = (idx == current_idx)
            border_color = UI["blue"] if is_selected else UI["edge"]
            border_width = 2 if is_selected else 1

            card_frame = tk.Frame(
                cards_grid,
                bg=UI["card"],
                highlightbackground=border_color,
                highlightthickness=border_width,
                cursor="hand2",
            )
            card_frame.pack(fill=tk.X, pady=8, padx=4)

            # 頂部狀態列
            chdr = tk.Frame(card_frame, bg=UI["card"])
            chdr.pack(fill=tk.X, padx=12, pady=(8, 6))

            disp_label = item_text.split("] ")[-1] if "] " in item_text else item_text
            tk.Label(
                chdr, text=f"來源 [{idx}]  {disp_label}", font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]
            ).pack(side=tk.LEFT)

            if is_selected:
                tk.Label(
                    chdr, text="● 目前選取中", font=self.fonts["badge"], fg=UI["ok"], bg=UI["card"]
                ).pack(side=tk.RIGHT)

            # 畫面內容列
            body_frame = tk.Frame(card_frame, bg=UI["card"])
            body_frame.pack(fill=tk.X, padx=12, pady=(0, 10))

            preview_w, preview_h = 320, 180
            thumb_canvas = tk.Canvas(
                body_frame,
                width=preview_w,
                height=preview_h,
                bg="#0d0d11",
                highlightthickness=1,
                highlightbackground=UI["edge"],
                cursor="hand2",
            )
            thumb_canvas.pack(side=tk.LEFT, padx=(0, 14))

            thumb_canvas.create_text(
                preview_w // 2, preview_h // 2,
                text="擷取畫面中…", fill=UI["muted"], font=self.fonts["body"]
            )

            # 右側資訊欄
            info_frame = tk.Frame(body_frame, bg=UI["card"])
            info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            tk.Label(
                info_frame, text=item_text, font=self.fonts["body"], fg=UI["text"], bg=UI["card"],
                justify="left", wraplength=340, anchor="w"
            ).pack(fill=tk.X, pady=(4, 8))

            if is_selected:
                tk.Label(
                    info_frame, text="✔ 此設備為目前錄影所選取的螢幕來源",
                    font=self.fonts["badge"], fg=UI["ok"], bg=UI["card"], anchor="w"
                ).pack(fill=tk.X, pady=(0, 12))
            else:
                tk.Label(
                    info_frame, text="💡 點選按鈕或雙擊縮圖立即套用為錄影來源",
                    font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"], anchor="w"
                ).pack(fill=tk.X, pady=(0, 12))

            action_row = tk.Frame(info_frame, bg=UI["card"])
            action_row.pack(fill=tk.X, pady=(10, 0))

            if is_selected:
                AuraButton(action_row, text="已選取此螢幕", style="Ghost.TButton", state=tk.DISABLED).pack(side=tk.LEFT)
            else:
                AuraButton(
                    action_row, text="選擇此螢幕", style="Primary.TButton",
                    command=lambda i=idx: select_and_close(i)
                ).pack(side=tk.LEFT)

            for w in (card_frame, body_frame, thumb_canvas, info_frame):
                w.bind("<Double-Button-1>", lambda _e, i=idx: select_and_close(i))
                w.bind("<Button-1>", lambda _e, i=idx: select_and_close(i))

            card_widgets.append((idx, item_text, thumb_canvas))

        def load_all_thumbnails():
            refresh_btn.config(state=tk.DISABLED)

            def bg_load():
                results = []
                for idx, item_text, t_canvas in card_widgets:
                    try:
                        ppm = capture_device_preview_ppm(
                            self.recorder.ffmpeg_bin, item_text, width=320, height=180
                        )
                    except Exception:
                        ppm = None
                    results.append((idx, ppm, t_canvas))

                def apply_results():
                    if not win.winfo_exists():
                        return
                    refresh_btn.config(state=tk.NORMAL)
                    for idx, ppm, t_canvas in results:
                        if not t_canvas.winfo_exists():
                            continue
                        if ppm:
                            try:
                                photo = tk.PhotoImage(data=ppm)
                                photo_cache.append(photo)
                                t_canvas.delete("all")
                                t_canvas.create_image(160, 90, image=photo)
                                continue
                            except Exception:
                                pass
                        t_canvas.delete("all")
                        t_canvas.create_text(
                            160, 90, text="無法擷取畫面", fill=UI["muted"], font=self.fonts["body"]
                        )

                self.root.after(0, apply_results)

            threading.Thread(target=bg_load, daemon=True).start()

        win.after(100, load_all_thumbnails)

    def _show_system_audio_guide(self):
        """開啟系統內部聲音錄製指南對話框"""
        win = tk.Toplevel(self.root)
        win.title("系統聲音錄製指南 — AURA REC")
        win.geometry("580x620")
        win.minsize(540, 560)
        win.configure(bg=UI["bg"])
        win.transient(self.root)

        card = tk.Frame(win, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        self._accent_bar(card)

        header = tk.Frame(card, bg=UI["card"])
        header.pack(fill=tk.X, padx=16, pady=(12, 8))
        tk.Label(
            header, text="GUIDE", font=self.fonts["badge"], fg=UI["blue"], bg=UI["card"]
        ).pack(side=tk.LEFT)
        tk.Label(
            header, text="系統內部聲音錄製教學", font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]
        ).pack(side=tk.LEFT, padx=(8, 0))

        content_box = tk.Frame(card, bg=UI["card"])
        content_box.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))

        if IS_MAC:
            intro_text = (
                "為什麼 Mac 錄不到電腦內部聲音？\n"
                "macOS 基於隱私與安全機制，不允許任何應用程式直接側錄揚聲器音效。\n"
                "解決方案：安裝開源免費的虛擬音效裝置 BlackHole 2ch，建立雙向迴圈。"
            )
            tk.Label(
                content_box, text=intro_text, font=self.fonts["body"], fg=UI["text"], bg=UI["card"],
                justify="left", wraplength=500
            ).pack(anchor="w", pady=(0, 10))

            steps_frame = tk.Frame(content_box, bg=UI["card"])
            steps_frame.pack(fill=tk.X, pady=(0, 6))

            tk.Label(
                steps_frame, text="步驟 1：安裝 BlackHole 2ch",
                font=self.fonts["bold"], fg=UI["blue"], bg=UI["card"], anchor="w"
            ).pack(fill=tk.X)

            cmd_row = tk.Frame(steps_frame, bg=UI["bg"], highlightbackground=UI["edge"], highlightthickness=1)
            cmd_row.pack(fill=tk.X, pady=(4, 8), ipady=3)
            tk.Label(
                cmd_row, text="brew install blackhole-2ch", font=self.fonts["mono"],
                fg=UI["white"], bg=UI["bg"]
            ).pack(side=tk.LEFT, padx=10)
            self._quiet_button(
                cmd_row, "複製指令", lambda: copy_text_to_clipboard("brew install blackhole-2ch")
            ).pack(side=tk.RIGHT, padx=6)

            tk.Label(
                steps_frame, text="步驟 2：建立「多重輸出裝置」（讓您能聽見，錄影也能錄）",
                font=self.fonts["bold"], fg=UI["blue"], bg=UI["card"], anchor="w"
            ).pack(fill=tk.X, pady=(4, 0))
            step2_desc = (
                "1. 按 Cmd + 空白鍵搜尋「音訊 MIDI 設定」app 並開啟。\n"
                "2. 點擊左下角「+」，選擇「建立多重輸出裝置」。\n"
                "3. 右側勾選您的「揚聲器 / 耳機」以及「BlackHole 2ch」（主裝置選揚聲器/耳機）。\n"
                "4. 在 Mac 頂端狀態列的聲音選單中，將輸出設備改為「多重輸出裝置」。"
            )
            tk.Label(
                steps_frame, text=step2_desc, font=self.fonts["body"], fg=UI["muted"], bg=UI["card"],
                justify="left", wraplength=500
            ).pack(anchor="w", pady=(2, 8))

            tk.Label(
                steps_frame, text="步驟 3：在 AURA REC 選擇音訊",
                font=self.fonts["bold"], fg=UI["blue"], bg=UI["card"], anchor="w"
            ).pack(fill=tk.X)
            step3_desc = (
                "回到 AURA REC 主畫面，在「音效」選單選擇：\n"
                "「[x] BlackHole 2ch (系統音效)」即可開始錄影！"
            )
            tk.Label(
                steps_frame, text=step3_desc, font=self.fonts["body"], fg=UI["muted"], bg=UI["card"],
                justify="left", wraplength=500
            ).pack(anchor="w", pady=(2, 4))
        else:
            intro_text = (
                "Windows 系統內部音效錄製說明：\n"
                "Windows 通常內建「立體聲混音 (Stereo Mix)」，只要啟用即可錄製電腦內部播放聲音。"
            )
            tk.Label(
                content_box, text=intro_text, font=self.fonts["body"], fg=UI["text"], bg=UI["card"],
                justify="left", wraplength=500
            ).pack(anchor="w", pady=(0, 10))

            steps_frame = tk.Frame(content_box, bg=UI["card"])
            steps_frame.pack(fill=tk.X, pady=(0, 6))

            tk.Label(
                steps_frame, text="步驟 1：開啟 Windows 音效設定",
                font=self.fonts["bold"], fg=UI["blue"], bg=UI["card"], anchor="w"
            ).pack(fill=tk.X)

            cmd_row = tk.Frame(steps_frame, bg=UI["bg"], highlightbackground=UI["edge"], highlightthickness=1)
            cmd_row.pack(fill=tk.X, pady=(4, 8), ipady=3)
            tk.Label(
                cmd_row, text="mmsys.cpl (Win + R 執行)", font=self.fonts["mono"],
                fg=UI["white"], bg=UI["bg"]
            ).pack(side=tk.LEFT, padx=10)
            if IS_WINDOWS:
                self._quiet_button(
                    cmd_row, "開啟控制台", lambda: subprocess.Popen(["control", "mmsys.cpl"])
                ).pack(side=tk.RIGHT, padx=6)
            else:
                self._quiet_button(
                    cmd_row, "複製指令", lambda: copy_text_to_clipboard("mmsys.cpl")
                ).pack(side=tk.RIGHT, padx=6)

            tk.Label(
                steps_frame, text="步驟 2：啟用「立體聲混音」",
                font=self.fonts["bold"], fg=UI["blue"], bg=UI["card"], anchor="w"
            ).pack(fill=tk.X, pady=(4, 0))
            step2_desc = (
                "1. 在音效視窗中切換至「錄製 (Recording)」分頁。\n"
                "2. 在裝置列表空白處按滑鼠右鍵，勾選「顯示已停用的裝置」。\n"
                "3. 在「立體聲混音 (Stereo Mix)」上按滑鼠右鍵，選擇「啟用」。"
            )
            tk.Label(
                steps_frame, text=step2_desc, font=self.fonts["body"], fg=UI["muted"], bg=UI["card"],
                justify="left", wraplength=500
            ).pack(anchor="w", pady=(2, 8))

            tk.Label(
                steps_frame, text="步驟 3：在 AURA REC 選擇音訊",
                font=self.fonts["bold"], fg=UI["blue"], bg=UI["card"], anchor="w"
            ).pack(fill=tk.X)
            step3_desc = (
                "回到 AURA REC 點擊「重新整理」，在音訊選單選擇：\n"
                "「立體聲混音 (系統音效)」即可開始錄影！\n"
                "(若音效卡無此功能，亦可安裝 VB-Audio Virtual Cable)"
            )
            tk.Label(
                steps_frame, text=step3_desc, font=self.fonts["body"], fg=UI["muted"], bg=UI["card"],
                justify="left", wraplength=500
            ).pack(anchor="w", pady=(2, 4))

        btn_row = tk.Frame(card, bg=UI["card"])
        btn_row.pack(fill=tk.X, padx=16, pady=(8, 12))
        AuraButton(btn_row, text="完成", style="Primary.TButton", command=win.destroy).pack(fill=tk.X)

    def _show_diagnostics(self):
        """開啟系統環境與 FFmpeg 硬體加速診斷對話框"""
        win = tk.Toplevel(self.root)
        win.title("FFmpeg 與硬體加速檢視 — AURA REC")
        win.geometry("600x640")
        win.minsize(560, 560)
        win.configure(bg=UI["bg"])
        win.transient(self.root)

        card = tk.Frame(win, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        self._accent_bar(card)

        header = tk.Frame(card, bg=UI["card"])
        header.pack(fill=tk.X, padx=16, pady=(12, 6))
        tk.Label(
            header, text="DIAGNOSTICS", font=self.fonts["badge"], fg=UI["blue"], bg=UI["card"]
        ).pack(side=tk.LEFT)
        tk.Label(
            header, text="硬體加速與環境檢測", font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]
        ).pack(side=tk.LEFT, padx=(8, 0))

        content_box = tk.Frame(card, bg=UI["card"])
        content_box.pack(fill=tk.BOTH, expand=True, padx=16, pady=(4, 12))

        diag = get_system_diagnostics(self.recorder.ffmpeg_bin)
        free_bytes = free_disk_bytes(self.recorder.output_dir)
        free_gb = f"{free_bytes / (1024**3):.1f} GB" if free_bytes is not None else "未知"

        lines = [
            ("應用程式版本", f"AURA REC v{diag['app_version']}"),
            ("作業系統環境", diag["os"]),
            ("Python 版本", diag["python"]),
            ("處理器與核心", f"{diag['cpu_count']} 核心 / {diag['ram_gb']} GB 記憶體 ({diag['machine_profile']})"),
            ("FFmpeg 執行檔", diag["ffmpeg_path"]),
            ("FFmpeg 版本", diag["ffmpeg_version"]),
            ("使用中影像編碼器", f"{diag['active_encoder']} (硬體加速: {'是' if 'x264' not in diag['active_encoder'] else 'CPU 軟體'})"),
            ("支援之編碼器", ", ".join(diag["hardware_encoders"]) or "無"),
            ("錄影儲存目錄", str(self.recorder.output_dir)),
            ("剩餘磁碟空間", free_gb),
        ]

        report_text = "\n".join(f"[{k}] {v}" for k, v in lines)

        for label, val in lines:
            row = tk.Frame(content_box, bg=UI["card"])
            row.pack(fill=tk.X, pady=3)
            tk.Label(
                row, text=label, font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"], width=16, anchor="w"
            ).pack(side=tk.LEFT)
            val_lbl = tk.Label(
                row, text=val, font=self.fonts["body"], fg=UI["white"], bg=UI["card"],
                anchor="w", wraplength=400, justify="left"
            )
            val_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_row = tk.Frame(card, bg=UI["card"])
        btn_row.pack(fill=tk.X, padx=16, pady=(8, 12))

        def do_copy():
            copy_text_to_clipboard(report_text)
            copy_btn.config(text="已複製！")
            win.after(2000, lambda: copy_btn.config(text="複製診斷報告"))

        copy_btn = self._quiet_button(btn_row, "複製診斷報告", do_copy)
        copy_btn.pack(side=tk.LEFT)
        AuraButton(btn_row, text="關閉", style="Primary.TButton", command=win.destroy).pack(side=tk.RIGHT, padx=(8, 0))

    def _show_about(self):
        """開啟關於 AURA REC 對話框"""
        win = tk.Toplevel(self.root)
        win.title("關於 — AURA REC")
        win.geometry("500x480")
        win.resizable(False, False)
        win.configure(bg=UI["bg"])
        win.transient(self.root)

        card = tk.Frame(win, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        self._accent_bar(card)

        center = tk.Frame(card, bg=UI["card"])
        center.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        title_frame = tk.Frame(center, bg=UI["card"])
        title_frame.pack(pady=(8, 4))
        tk.Label(title_frame, text="AURA", font=self.fonts["title"], fg=UI["white"], bg=UI["card"]).pack(side=tk.LEFT)
        tk.Label(title_frame, text="REC", font=self.fonts["title"], fg=UI["blue"], bg=UI["card"]).pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(
            center, text=f"版本 {APP_VERSION} (原生跨平台桌面版)", font=self.fonts["badge"],
            fg=UI["muted"], bg=UI["card"]
        ).pack(pady=(0, 14))

        desc = (
            "極速低耗能的原生螢幕錄影工作站。\n\n"
            "• Apple Silicon VideoToolbox / Windows GPU 原生硬體加速\n"
            "• 智慧視窗動態追蹤、游標開關與置頂迷你膠囊懸浮模式\n"
            "• 零依賴綠色單檔架構（純 Python 標準庫 + FFmpeg 引擎）\n"
            "• 內建影格即時預覽、精準裁切、雙遍高品質 GIF 導出\n"
            "• 系統快捷鍵：F9 錄製/停止、F8 暫停/繼續、F7 截圖、Esc 展開"
        )
        tk.Label(
            center, text=desc, font=self.fonts["body"], fg=UI["text"], bg=UI["card"],
            justify="left", wraplength=420
        ).pack(fill=tk.X, pady=(0, 16))

        btn_row = tk.Frame(center, bg=UI["card"])
        btn_row.pack(fill=tk.X, pady=(4, 0))
        self._quiet_button(btn_row, "快捷鍵說明", self._show_shortcuts).pack(side=tk.LEFT)
        AuraButton(btn_row, text="確定", style="Primary.TButton", command=win.destroy).pack(side=tk.RIGHT)

    def _show_preferences(self):
        """開啟偏好設定視窗"""
        win = tk.Toplevel(self.root)
        win.title("偏好設定 — AURA REC")
        win.geometry("560x540")
        win.minsize(520, 500)
        win.configure(bg=UI["bg"])
        win.transient(self.root)

        card = tk.Frame(win, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        self._accent_bar(card)

        header = tk.Frame(card, bg=UI["card"])
        header.pack(fill=tk.X, padx=16, pady=(12, 6))
        tk.Label(
            header, text="PREFERENCES", font=self.fonts["badge"], fg=UI["blue"], bg=UI["card"]
        ).pack(side=tk.LEFT)
        tk.Label(
            header, text="偏好與進階設定", font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]
        ).pack(side=tk.LEFT, padx=(8, 0))

        form = tk.Frame(card, bg=UI["card"])
        form.pack(fill=tk.BOTH, expand=True, padx=16, pady=(4, 12))

        # 儲存目錄
        tk.Label(form, text="儲存目錄", font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]).pack(anchor="w", pady=(4, 2))
        dir_row = tk.Frame(form, bg=UI["card"])
        dir_row.pack(fill=tk.X, pady=(0, 10))
        lbl_dir = tk.Label(
            dir_row, text=str(self.recorder.output_dir), font=self.fonts["badge"],
            fg=UI["muted"], bg=UI["field"], anchor="w", padx=8, pady=4,
            highlightbackground=UI["edge"], highlightthickness=1
        )
        lbl_dir.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def pick_dir():
            chosen = filedialog.askdirectory(initialdir=str(self.recorder.output_dir), title="選擇儲存目錄")
            if chosen:
                self.recorder.output_dir = Path(chosen)
                save_settings({"output_dir": str(self.recorder.output_dir)})
                lbl_dir.config(text=str(self.recorder.output_dir))
                self._show_save_path()
                self.refresh_recent_list()

        self._quiet_button(dir_row, "變更…", pick_dir).pack(side=tk.RIGHT, padx=(6, 0))

        # 檔名自訂前綴
        tk.Label(form, text="自訂檔名前綴", font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]).pack(anchor="w", pady=(2, 2))
        pref_prefix = self._saved.get("filename_prefix", "螢幕錄影")
        ent_prefix = tk.Entry(
            form, font=self.fonts["body"], bg=UI["field"], fg=UI["text"],
            insertbackground=UI["blue"], relief=tk.FLAT, bd=0,
            highlightthickness=1, highlightbackground=UI["edge"], highlightcolor=UI["blue"]
        )
        ent_prefix.insert(0, pref_prefix)
        ent_prefix.pack(fill=tk.X, pady=(0, 4), ipady=3)
        tk.Label(
            form, text="範例：輸入「AURA」則檔名為 AURA_2026-10-09_18-30.mp4",
            font=self.fonts["badge"], fg=UI["muted"], bg=UI["card"]
        ).pack(anchor="w", pady=(0, 10))

        # 行為選項
        tk.Label(form, text="功能開關", font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]).pack(anchor="w", pady=(2, 4))
        opt_box = tk.Frame(form, bg=UI["card"])
        opt_box.pack(fill=tk.X, pady=(0, 10))
        AuraCheck(opt_box, text="開始前倒數 3 秒", variable=self.countdown_var, command=self._save_capture_settings).pack(anchor="w", pady=2)
        AuraCheck(opt_box, text="錄影時縮成小視窗", variable=self.auto_mini_var, command=self._save_capture_settings).pack(anchor="w", pady=2)
        AuraCheck(opt_box, text="截圖後自動複製至剪貼簿", variable=self.auto_copy_screenshot_var, command=self._save_capture_settings).pack(anchor="w", pady=2)
        AuraCheck(opt_box, text="錄製滑鼠游標", variable=self.capture_cursor_var, command=self._save_capture_settings).pack(anchor="w", pady=2)
        AuraCheck(opt_box, text="啟用晶片 GPU 硬體加速", variable=self.hardware_accel_var, command=self._save_capture_settings).pack(anchor="w", pady=2)
        AuraCheck(opt_box, text="啟用錄影與截圖音效提示", variable=self.sound_alert_var, command=self._save_capture_settings).pack(anchor="w", pady=2)

        def save_and_close():
            val = ent_prefix.get().strip() or "螢幕錄影"
            self._saved["filename_prefix"] = val
            save_settings({"filename_prefix": val})
            self._save_capture_settings()
            win.destroy()

        btn_row = tk.Frame(card, bg=UI["card"])
        btn_row.pack(fill=tk.X, padx=16, pady=(8, 12))
        AuraButton(btn_row, text="儲存設定", style="Primary.TButton", command=save_and_close).pack(side=tk.RIGHT)
        self._quiet_button(btn_row, "關閉", win.destroy).pack(side=tk.LEFT)

    def refresh_recent_list(self):
        """重新整理最近錄影檔案列表"""
        for widget in self.recent_list_frame.winfo_children():
            widget.destroy()

        try:
            patterns = ("*.mp4", "*.mov", "*.mkv", "*.webm", "*.gif", "*.png", "*.m4a", "*.mp3", "*.wav")
            found = []
            for pattern in patterns:
                found.extend(self.recorder.output_dir.glob(pattern))
            files = sorted(found, key=lambda x: x.stat().st_mtime, reverse=True)[:24]
        except Exception:
            files = []
            found = []

        if hasattr(self, "lbl_recent_title"):
            total_count = len(found)
            self.lbl_recent_title.config(
                text=f"最近的錄影 (共 {total_count} 個檔案)" if total_count > 0 else "最近的錄影"
            )

        self._recent_generation += 1
        pending = []
        if not files:
            tk.Label(
                self.recent_list_frame,
                text="這個資料夾還沒有錄影",
                font=self.fonts["body"],
                fg=UI["muted"],
                bg=UI["card"],
            ).pack(pady=16)
            self.root.after_idle(self._sync_recent_scroll)
            return

        for p in files:
            try:
                st = p.stat()
            except OSError:
                continue
            row = tk.Frame(self.recent_list_frame, bg=UI["card"])
            row.pack(fill=tk.X, pady=1)

            sz = st.st_size / (1024 * 1024)
            size_text = f"{sz:.1f} MB" if sz >= 0.1 else f"{max(1, int(st.st_size / 1024))} KB"
            time_str = datetime.fromtimestamp(st.st_mtime).strftime("%m/%d %H:%M")
            display_name = p.name if len(p.name) <= 36 else ("…" + p.name[-35:])

            top = tk.Frame(row, bg=UI["card"])
            top.pack(fill=tk.X)
            name = tk.Label(
                top, text=display_name, font=self.fonts["body"], fg=UI["text"], bg=UI["card"],
                anchor="w", cursor="hand2",
            )
            name.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 4))
            name.bind("<Double-Button-1>", lambda _e, f=p: open_file_or_dir(str(f)))
            self._quiet_button(top, "刪除", lambda f=p: self._delete_recording(f), fg=UI["red"]).pack(side=tk.RIGHT)
            if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
                self._quiet_button(top, "剪輯", lambda f=p: self.open_editor(str(f))).pack(side=tk.RIGHT)
            open_label = "開啟" if p.suffix.lower() == ".png" else "播放"
            self._quiet_button(top, open_label, lambda f=p: open_file_or_dir(str(f))).pack(side=tk.RIGHT)
            self._quiet_button(top, "顯示", lambda f=p: open_file_or_dir(str(f), reveal=True)).pack(side=tk.RIGHT)
            self._quiet_button(top, "複製", lambda f=p: self._copy_file_feedback(f)).pack(side=tk.RIGHT)
            self._quiet_button(top, "改名", lambda f=p: self._rename_recording(f)).pack(side=tk.RIGHT)

            duration = ""
            cache_key = None
            if p.suffix.lower() in _TIMED_SUFFIXES and not self._file_is_open_recording(p):
                cache_key = (str(p), p.stat().st_mtime_ns)
                duration = self._duration_cache.get(cache_key, "")
            detail = f"{time_str}   {size_text}"
            if duration:
                detail = f"{detail}   {duration}"
            meta = tk.Label(
                row,
                text=detail,
                font=self.fonts["badge"],
                fg=UI["muted"],
                bg=UI["card"],
                anchor="w",
            )
            meta.pack(fill=tk.X, padx=6)

            # 懸浮微光回饋
            def _bind_row_hover(r=row, t=top, n=name, m=meta):
                def _enter(_e):
                    for w in (r, t, n, m):
                        try:
                            w.config(bg=UI["hover"])
                        except Exception:
                            pass

                def _leave(e):
                    try:
                        rx, ry = r.winfo_rootx(), r.winfo_rooty()
                        rw, rh = r.winfo_width(), r.winfo_height()
                        if rx <= e.x_root <= rx + rw and ry <= e.y_root <= ry + rh:
                            return
                    except Exception:
                        pass
                    for w in (r, t, n, m):
                        try:
                            w.config(bg=UI["card"])
                        except Exception:
                            pass

                for w in (r, t, n, m):
                    w.bind("<Enter>", _enter)
                    w.bind("<Leave>", _leave)

            _bind_row_hover()

            # 右鍵選單與點兩下開啟
            row.bind("<Double-Button-1>", lambda _e, f=p: open_file_or_dir(str(f)))
            meta.bind("<Double-Button-1>", lambda _e, f=p: open_file_or_dir(str(f)))
            for w in (row, top, name, meta):
                w.bind("<Button-2>", lambda e, f=p: self._show_recording_context_menu(e, f))
                w.bind("<Button-3>", lambda e, f=p: self._show_recording_context_menu(e, f))

            if cache_key and not duration:
                pending.append((p, cache_key, meta))
        self.root.after_idle(self._sync_recent_scroll)
        if pending:
            self._queue_durations(pending, self._recent_generation)

    def _show_recording_context_menu(self, event, file_path):
        menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=UI["card"],
            fg=UI["text"],
            activebackground=UI["hover"],
            activeforeground=UI["blue"],
            bd=1,
            relief=tk.SOLID,
        )
        p = Path(file_path)
        is_vid = p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}
        lbl_open = "開啟圖片" if p.suffix.lower() == ".png" else "播放檔案"
        menu.add_command(label=lbl_open, command=lambda f=p: open_file_or_dir(str(f)))
        if is_vid:
            menu.add_command(label="剪輯影片…", command=lambda f=p: self.open_editor(str(f)))
        menu.add_separator()
        menu.add_command(label="在資料夾中顯示", command=lambda f=p: open_file_or_dir(str(f), reveal=True))
        menu.add_command(label="複製檔案 (可直接貼上)", command=lambda f=p: self._copy_file_feedback(f))
        menu.add_command(label="複製完整路徑", command=lambda f=p: self._copy_path_feedback(f))
        menu.add_separator()
        menu.add_command(label="重新命名…", command=lambda f=p: self._rename_recording(f))
        menu.add_command(label="刪除檔案", command=lambda f=p: self._delete_recording(f))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy_file_feedback(self, p):
        if copy_file(str(p)):
            self.timer_hint.config(text=f"已複製檔案至剪貼簿：{p.name}")
        else:
            self.timer_hint.config(text=f"複製檔案失敗")

    def _copy_path_feedback(self, p):
        copy_text_to_clipboard(str(p.resolve()))
        self.timer_hint.config(text=f"已複製檔案路徑：{p.name}")

    def _queue_durations(self, pending, generation):
        def work():
            found = []
            for path, key, label in pending:
                text = self._duration_cache.get(key)
                if not text:
                    text = self._read_duration(path)
                    if text:
                        self._duration_cache[key] = text
                if text:
                    found.append((label, text))

            def apply():
                if generation != self._recent_generation:
                    return
                for label, text in found:
                    try:
                        if not label.winfo_exists():
                            continue
                        current = label.cget("text")
                        if not current.endswith(text):
                            label.config(text=f"{current}   {text}")
                    except tk.TclError:
                        continue

            try:
                self.root.after(0, apply)
            except (RuntimeError, tk.TclError):
                return

        threading.Thread(target=work, daemon=True).start()

    def _read_duration(self, path):
        ffprobe = find_executable("ffprobe")
        if not ffprobe:
            return ""
        try:
            done = subprocess.run(
                [
                    ffprobe, "-v", "error", "-show_entries", "format=duration",
                    "-of", "csv=p=0", str(path),
                ],
                capture_output=True,
                text=True,
                timeout=4,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return format_media_duration((done.stdout or "").strip())

    def _fit_recent_width(self, event):
        self.recent_canvas.itemconfigure(self.recent_window, width=event.width)

    def _sync_recent_scroll(self, _event=None):
        canvas = self.recent_canvas
        bbox = canvas.bbox("all")
        canvas.configure(scrollregion=bbox or (0, 0, 0, 0))
        if not bbox:
            self.recent_scroll.pack_forget()
            return
        content_h = bbox[3] - bbox[1]
        if content_h <= canvas.winfo_height() + 2:
            self.recent_scroll.pack_forget()
            canvas.yview_moveto(0)
        elif not self.recent_scroll.winfo_ismapped():
            self.recent_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _bind_recent_wheel(self, _event=None):
        self.root.bind_all("<MouseWheel>", self._recent_wheel)
        self.root.bind_all("<Button-4>", self._recent_wheel)
        self.root.bind_all("<Button-5>", self._recent_wheel)

    def _unbind_recent_wheel(self, event):
        x, y = self.root.winfo_pointerxy()
        widget = self.root.winfo_containing(x, y)
        while widget is not None:
            if widget == self.recent_wrap:
                return
            widget = getattr(widget, "master", None)
        self.root.unbind_all("<MouseWheel>")
        self.root.unbind_all("<Button-4>")
        self.root.unbind_all("<Button-5>")

    def _recent_wheel(self, event):
        if getattr(event, "num", None) == 4:
            self.recent_canvas.yview_scroll(-1, "units")
            return
        if getattr(event, "num", None) == 5:
            self.recent_canvas.yview_scroll(1, "units")
            return
        delta = getattr(event, "delta", 0)
        if not delta:
            return
        if abs(delta) >= 120:
            self.recent_canvas.yview_scroll(int(-delta / 120), "units")
        else:
            self.recent_canvas.yview_scroll(-1 if delta > 0 else 1, "units")

    def take_screenshot(self):
        if self._shooting or self.countdown_active:
            return
        self._shooting = True
        self.shot_btn.config(state=tk.DISABLED)
        ready, region = self._prepare_region()
        if not ready:
            self._shooting = False
            self.shot_btn.config(state=tk.NORMAL)
            return
        output_dir = self.recorder.output_dir
        ffmpeg_bin = self.recorder.ffmpeg_bin
        geometry = self.root.geometry()
        prefix = self._saved.get("filename_prefix")
        self.root.withdraw()
        self.root.update_idletasks()

        def work():
            path = None
            try:
                time.sleep(0.25)
                path = save_still(ffmpeg_bin, output_dir, region, prefix=prefix)
            finally:
                self.root.after(0, lambda: self._screenshot_done(path, geometry))

        threading.Thread(target=work, daemon=True).start()

    def _screenshot_done(self, path, geometry):
        self._shooting = False
        self.root.deiconify()
        self.root.geometry(geometry)
        if self.is_mini_mode:
            self.root.attributes("-topmost", True)
        self.root.lift()
        self.shot_btn.config(state=tk.NORMAL)
        if path:
            self._play_alert("shot")
            self.refresh_recent_list()
            copied = False
            if self.auto_copy_screenshot_var.get():
                copied = copy_file(path)
            if not self.recorder.is_recording:
                hint = f"已存截圖並複製到剪貼簿 {Path(path).name}" if copied else f"已存截圖 {Path(path).name}"
                self.timer_hint.config(text=hint)
            return
        messagebox.showwarning(
            "截圖沒有成功",
            "沒有存到圖片。請到系統設定確認螢幕錄製權限。",
        )

    def _file_is_open_recording(self, file_path):
        if not self.recorder.is_recording:
            return False
        try:
            wanted = Path(file_path).resolve()
        except OSError:
            wanted = Path(file_path)
        template = self.recorder.current_output_file
        candidates = list(self.recorder.recorded_parts())
        if template is not None and "%03d" not in template.name:
            candidates.append(template)
        for part in candidates:
            try:
                if Path(part).resolve() == wanted:
                    return True
            except OSError:
                if Path(part) == Path(file_path):
                    return True
        return False

    def _rename_recording(self, file_path):
        if self._file_is_open_recording(file_path):
            messagebox.showinfo("還在寫入", "這個檔還在錄，先停止再改名。")
            return
        typed = simpledialog.askstring(
            "改名",
            "新的檔名。副檔名會保留。",
            initialvalue=file_path.stem,
            parent=self.root,
        )
        if typed is None:
            return
        target = renamed_path(file_path, typed)
        if target is None:
            messagebox.showwarning("改名", "這個檔名不能用。")
            return
        if target == file_path:
            return
        if target.exists():
            messagebox.showwarning("改名", "已經有這個檔名。")
            return
        try:
            file_path.rename(target)
        except OSError as exc:
            messagebox.showerror("改名沒有成功", str(exc))
            return
        last = self.recorder.last_recorded_file
        if last is not None and Path(last) == file_path:
            self.recorder.last_recorded_file = target
        self.refresh_recent_list()

    def _delete_recording(self, file_path):
        """刪除單一錄影檔"""
        if messagebox.askyesno("確認刪除", f"確定要刪除錄影檔案嗎？\n{file_path.name}"):
            try:
                file_path.unlink()
                if self.recorder.last_recorded_file and Path(self.recorder.last_recorded_file) == file_path:
                    self.recorder.last_recorded_file = None
                    if hasattr(self, "btn_play_last"):
                        self.btn_play_last.config(state=tk.DISABLED)
                self.refresh_recent_list()
            except Exception as e:
                messagebox.showerror("刪除失敗", str(e))

    def _show_save_path(self):
        if not hasattr(self, "save_path_label"):
            return
        path = str(self.recorder.output_dir)
        home = str(Path.home())
        if path.startswith(home):
            path = "~" + path[len(home):]
        self.save_path_label.config(text=path)

    def _apply_saved_window(self):
        spec = fit_window_geometry(
            self._saved.get("window"),
            self.root.winfo_screenwidth(),
            self.root.winfo_screenheight(),
        )
        if spec:
            self.root.geometry(spec)

    def _remember_window(self):
        if self.is_mini_mode:
            width, height = self._normal_size
        else:
            width = self.root.winfo_width()
            height = self.root.winfo_height()
        if width < 100 or height < 40:
            return
        save_settings({
            "window": f"{int(width)}x{int(height)}+{int(self.root.winfo_x())}+{int(self.root.winfo_y())}"
        })

    def _on_close(self):
        self._remember_window()
        if self.recorder.is_recording:
            if not messagebox.askyesno("正在錄影", "錄影還沒停。要停下來並結束嗎？"):
                return
            self._stopping = True

            def work():
                self.recorder.stop_recording()
                self.root.after(0, self._destroy_after_stop)

            threading.Thread(target=work, daemon=True).start()
            return
        release_awake()
        self.root.destroy()

    def _destroy_after_stop(self):
        release_awake()
        self.root.destroy()


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    use_dark_appearance()
    app = LiteRecorderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
