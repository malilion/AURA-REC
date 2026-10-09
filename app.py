#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LiteScreenRecorder - 輕量桌面錄影工具 (macOS & Windows 跨平台支援)
- 支援 Apple Silicon (macOS) 與 NVIDIA / Intel / AMD (Windows) 硬體加速
- 支援螢幕選擇、音訊設備選擇（麥克風 / 系統音效）
- 支援自訂解析度 (原生 / 2K / 1080p / 720p) 與 FPS (15 / 30 / 60)
- 支援懸浮膠囊迷你模式 (Mini Floating Pill)，不遮擋畫面
- 支援暫停與繼續、錄製游標開關，並記住上次的裝置與畫質
- 支援自訂錄影範圍、畫質、MP4 / MOV，以及到時自動停止
- 支援截圖、錄影中顯示檔案大小，空間不足時會先詢問
- 支援錄影中展開小條、預估每分鐘大小、分段存檔，以及替最近的檔案改名
- 倒數可以取消。錄影時不讓電腦睡著，並記住視窗位置
- 支援 3 秒倒數準備、快速鍵 (Space / F7 / F8 / F9 / Ctrl+R / Cmd+R / Esc)
- 支援即時影片剪輯與匯出 GIF / 提取音訊
"""

import math
import os
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from pathlib import Path

from recorder import LOW_DISK_BYTES, ScreenRecorder, format_bytes, free_disk_bytes, save_still
from editor_window import VideoEditorWindow
from aura_widgets import AuraButton, AuraCheck
from region_picker import pick_screen_region
from platform_utils import (
    IS_MAC,
    IS_WINDOWS,
    enable_dpi_awareness,
    get_ui_fonts,
    play_system_alert,
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
        self._normal_size = (560, 800)
        self._saved = load_settings()
        self.region = self._saved_region()
        self._auto_stop_sec = None
        self._segment_sec = None
        self.auto_mini_var = tk.BooleanVar(value=self._flag("auto_mini", True))
        self.countdown_var = tk.BooleanVar(value=self._flag("countdown", True))
        self.hardware_accel_var = tk.BooleanVar(value=self._flag("hardware_accel", True))
        self.capture_cursor_var = tk.BooleanVar(value=self._flag("capture_cursor", True))

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
            "截圖：F7。有自訂範圍時只截那一塊。\n\n"
            "倒數時再按一次，或按 Esc，就會取消。\n\n"
            "錄影中的小條可以拖曳挪開。按「展開」或 Esc 回到完整視窗，選單裡的「收成小條」可以再縮回去。",
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
        file_menu.add_command(label="剪輯影片…", command=self.open_editor)
        file_menu.add_command(label="播放最新錄影", command=self.play_last_recording)
        file_menu.add_separator()
        file_menu.add_command(label="開啟瀏覽器工作站", command=self.open_web_studio)
        file_menu.add_separator()
        file_menu.add_command(label="結束", command=self._on_close)
        menubar.add_cascade(label="檔案", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="快捷鍵", command=self._show_shortcuts)
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

        self.video_combo = labeled_combo(0, 0, "螢幕", span=3)
        self.audio_combo = labeled_combo(1, 0, "麥克風", span=3)
        self.res_combo = labeled_combo(2, 0, "解析度")
        self.res_combo["values"] = [
            "原生（較吃資源）",
            "2K（較吃資源）",
            "1080p（1920×1080）",
            "720p（1280×720）",
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
        )):
            AuraCheck(
                checks, text=text, variable=variable, command=self._save_capture_settings
            ).grid(row=index // 2, column=index % 2, sticky="w")
        for combo in (
            self.video_combo, self.audio_combo, self.res_combo, self.fps_combo,
            self.quality_combo, self.format_combo, self.limit_combo, self.segment_combo,
        ):
            combo.bind("<<ComboboxSelected>>", lambda _e: self._save_capture_settings())
        self.area_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_area_choice())

        self.recent_card = self._card(self.main_container)
        self.recent_card.pack(fill=tk.BOTH, expand=True)

        recent_header = tk.Frame(self.recent_card, bg=UI["card"])
        recent_header.pack(fill=tk.X, padx=8, pady=(8, 0))
        tk.Label(
            recent_header, text="最近的錄影", font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]
        ).pack(side=tk.LEFT, padx=6)
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
            self.root.after(0, lambda: self._apply_devices(v_devs, a_devs, missing))

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

        v_names = [f"[{d['index']}] {d['name']}" for d in v_devs]
        self.video_combo["values"] = v_names or ["預設主螢幕"]
        screen_at = 0
        for i, name in enumerate(v_names):
            lowered = name.lower()
            if "capture screen" in lowered or "desktop" in lowered or "螢幕" in name:
                screen_at = i
                break
        saved_video = self._saved.get("video_device")
        if isinstance(saved_video, str) and saved_video in v_names:
            screen_at = v_names.index(saved_video)
        self.video_combo.current(screen_at)
        busy = self.recorder.is_recording or self.countdown_active or self._stopping
        self.video_combo.config(state=tk.DISABLED if busy else "readonly")

        a_names = ["無音訊 (靜音)"] + [f"[{d['index']}] {d['name']}" for d in a_devs]
        self.audio_combo["values"] = a_names
        audio_at = 1 if len(a_names) > 1 else 0
        saved_audio = self._saved.get("audio_device")
        if isinstance(saved_audio, str) and saved_audio in a_names:
            audio_at = a_names.index(saved_audio)
        self.audio_combo.current(audio_at)
        self.audio_combo.config(state=tk.DISABLED if busy else "readonly")

        if not busy:
            self.timer_hint.config(text=self._idle_hint())
        if not self.recorder.is_recording and not self.countdown_active:
            self.record_btn.config(state=tk.NORMAL)

    def _switch_to_mini_mode(self):
        """收合為置頂懸浮膠囊"""
        self.is_mini_mode = True
        self._normal_size = (max(self.root.winfo_width(), 520), max(self.root.winfo_height(), 640))
        self.main_container.pack_forget()

        prev_x = self.root.winfo_x()
        prev_y = self.root.winfo_y()

        self.root.minsize(430, 48)
        self.root.geometry(f"430x48+{prev_x}+{prev_y}")
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
        if self._saved.get("area_mode") != 1:
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

    def _update_area_label(self):
        if not self.region:
            self.area_combo["values"] = ["整個螢幕", "自訂範圍"]
            self.area_combo.current(0)
            self.area_label.config(text="自訂範圍只錄這個螢幕")
            return
        _x, _y, w, h = self.region
        self.area_combo["values"] = ["整個螢幕", f"自訂 {w}×{h}"]
        self.area_combo.current(1)
        self.area_label.config(text=f"{w}×{h} 像素，這個螢幕")

    def _on_area_choice(self):
        if self.area_combo.current() == 1:
            self._pick_region()
            return
        self.region = None
        self._update_area_label()
        self._save_capture_settings()

    def _pick_region(self):
        if self.recorder.is_recording or self.countdown_active:
            return
        rect = pick_screen_region(self.root)
        if rect is None and not self.region:
            self.area_combo.current(0)
        elif rect is not None:
            self.region = rect
            self.area_combo.current(1)
        self._update_area_label()
        self._save_capture_settings()

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
            "quality_index": self.quality_combo.current(),
            "format_index": self.format_combo.current(),
            "limit_index": self.limit_combo.current(),
            "segment_index": self.segment_combo.current(),
            "area_mode": self.area_combo.current(),
            "region": list(self.region) if self.region else None,
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
                play_system_alert("ready")
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
        region = self.region if self.area_combo.current() == 1 else None

        play_system_alert("start")
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
        )

        if not ok:
            self._segment_sec = None
            release_awake()
            messagebox.showerror("錄影啟動失敗", msg)
            self._update_ui_state(recording=False)
            return

        if self.recorder.process is not None:
            hold_awake(self.recorder.process.pid)
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
        play_system_alert("stop")

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
                question = f"這次分成 {len(parts)} 個檔。\n要剪輯最新的嗎？\n{name}"
            else:
                self.timer_hint.config(text=f"已儲存 {name}")
                question = f"影片已存好。\n{name}\n\n要現在剪輯嗎？"
            if offer_editor and messagebox.askyesno("錄影完成", question):
                self.open_editor(msg)
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
        if hasattr(self, "reselect_btn"):
            self.reselect_btn.config(state=tk.DISABLED if locked else tk.NORMAL)

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

    def _draw_vu_idle(self):
        """繪製待機狀態的靜態 VU 電平點"""
        if not hasattr(self, 'vu_canvas'):
            return
        self.vu_canvas.delete("all")
        w, h = 220, 8
        bar_count = 16
        bar_w = 8
        gap = (w - (bar_count * bar_w)) / (bar_count + 1)
        for i in range(bar_count):
            x = gap + i * (bar_w + gap)
            self.vu_canvas.create_rectangle(x, 2, x + bar_w, h, fill=UI["meter_idle"], outline="")

    def _draw_mini_vu_idle(self):
        """繪製迷你懸浮膠囊的靜態電平點"""
        if not hasattr(self, 'mini_vu_canvas'):
            return
        self.mini_vu_canvas.delete("all")
        bar_count = 4
        bar_w = 4
        gap = 3
        for i in range(bar_count):
            x = 2 + i * (bar_w + gap)
            self.mini_vu_canvas.create_rectangle(x, 4, x + bar_w, 10, fill=UI["meter_idle"], outline="")

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

    def _idle_hint(self):
        label = self.capture_advice["label"]
        remain = disk_time_text(free_disk_bytes(self.recorder.output_dir), sum(self._capture_kbps()) * 1000)
        tail = remain or self.recorder.output_dir.name
        return f"{label}  ·  {self._size_estimate_text()}  ·  {tail}"

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
            if self.vu_tick_count % 4 == 0 and not self._stopping:
                self.timer_hint.config(text=self._recording_hint())
            if self.recorder.paused:
                self._draw_vu_idle()
                self._draw_mini_vu_idle()
            else:
                self._draw_vu_active(self.vu_tick_count)
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

    def refresh_recent_list(self):
        """重新整理最近錄影檔案列表"""
        for widget in self.recent_list_frame.winfo_children():
            widget.destroy()

        try:
            patterns = ("*.mp4", "*.mov", "*.mkv", "*.webm", "*.gif", "*.png", "*.m4a", "*.mp3", "*.wav")
            found = []
            for pattern in patterns:
                found.extend(self.recorder.output_dir.glob(pattern))
            files = sorted(found, key=lambda x: x.stat().st_mtime, reverse=True)[:8]
        except Exception:
            files = []

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
            row = tk.Frame(self.recent_list_frame, bg=UI["card"])
            row.pack(fill=tk.X, pady=1)

            sz = p.stat().st_size / (1024 * 1024)
            size_text = f"{sz:.1f} MB" if sz >= 0.1 else f"{max(1, int(p.stat().st_size / 1024))} KB"
            time_str = datetime.fromtimestamp(p.stat().st_mtime).strftime("%m/%d %H:%M")
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
            self._quiet_button(top, "改名", lambda f=p: self._rename_recording(f)).pack(side=tk.RIGHT)

            tk.Label(
                row,
                text=f"{time_str}   {size_text}",
                font=self.fonts["badge"],
                fg=UI["muted"],
                bg=UI["card"],
                anchor="w",
            ).pack(fill=tk.X, padx=6)
        self.root.after_idle(self._sync_recent_scroll)

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
        region = self.region if self.area_combo.current() == 1 else None
        output_dir = self.recorder.output_dir
        ffmpeg_bin = self.recorder.ffmpeg_bin
        geometry = self.root.geometry()
        self.root.withdraw()
        self.root.update_idletasks()

        def work():
            path = None
            try:
                time.sleep(0.25)
                path = save_still(ffmpeg_bin, output_dir, region)
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
            self.refresh_recent_list()
            if not self.recorder.is_recording:
                self.timer_hint.config(text=f"已存截圖 {Path(path).name}")
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
