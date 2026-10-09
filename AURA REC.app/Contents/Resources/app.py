#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LiteScreenRecorder - 輕量桌面錄影工具 (macOS & Windows 跨平台支援)
- 支援 Apple Silicon (macOS) 與 NVIDIA / Intel / AMD (Windows) 硬體加速
- 支援螢幕選擇、音訊設備選擇（麥克風 / 系統音效）
- 支援自訂解析度 (原生 / 2K / 1080p / 720p) 與 FPS (15 / 30 / 60)
- 支援懸浮膠囊迷你模式 (Mini Floating Pill)，不遮擋畫面
- 支援 3 秒倒數準備、快速鍵 (Space / F9 / Ctrl+R / Cmd+R)
- 支援即時影片剪輯與匯出 GIF / 提取音訊
"""

import math
import os
import random
import subprocess
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

from recorder import ScreenRecorder
from editor_window import VideoEditorWindow
from platform_utils import (
    IS_MAC,
    IS_WINDOWS,
    enable_dpi_awareness,
    get_ui_fonts,
    play_system_alert,
    open_file_or_dir,
    save_settings,
    recommended_capture,
)


class LiteRecorderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AURA REC")
        self.root.geometry("520x760")
        self.root.minsize(500, 700)
        self.root.configure(bg="#0A0C10")

        # 跨平台字型
        self.fonts = get_ui_fonts()

        # 核心錄影實例
        self.recorder = ScreenRecorder()

        # 狀態變數
        self.is_mini_mode = False
        self.countdown_active = False
        self._stopping = False
        self._pending_mini = False
        self._normal_size = (520, 760)
        self.auto_mini_var = tk.BooleanVar(value=True)
        self.countdown_var = tk.BooleanVar(value=True)
        self.hardware_accel_var = tk.BooleanVar(value=True)

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

        # 啟動計時更新迴圈
        self._timer_tick()

    def _init_styles(self):
        style = ttk.Style()
        style.theme_use("default")

        # 設定 ttk 下拉選單樣式
        style.configure(
            "Dark.TCombobox",
            fieldbackground="#151922",
            background="#1E2330",
            foreground="#FFFFFF",
            arrowcolor="#94A3B8",
            darkcolor="#0A0C10",
            lightcolor="#1E2330",
            insertcolor="#FFFFFF",
        )
        style.map("Dark.TCombobox", fieldbackground=[("readonly", "#151922")])

    def _add_hover(self, widget, normal_bg, hover_bg, normal_fg=None, hover_fg=None):
        """為按鈕加入 hover 微互動（進入變亮、離開還原）—— AURA 獲獎級質感。"""
        def on_enter(_e):
            widget.config(bg=hover_bg)
            if hover_fg:
                widget.config(fg=hover_fg)
        def on_leave(_e):
            widget.config(bg=normal_bg)
            if normal_fg:
                widget.config(fg=normal_fg)
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def _build_main_ui(self):
        # 主容器
        self.main_container = tk.Frame(self.root, bg="#0A0C10")
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        # 標題欄
        header_frame = tk.Frame(self.main_container, bg="#0A0C10")
        header_frame.pack(fill=tk.X, pady=(0, 14))

        title_label = tk.Label(
            header_frame,
            text="AURA REC",
            font=self.fonts["title"],
            fg="#FFFFFF",
            bg="#0A0C10"
        )
        title_label.pack(side=tk.LEFT)

        self.status_badge = tk.Label(
            header_frame,
            text="● 就緒",
            font=self.fonts["badge"],
            fg="#00FF9D",
            bg="#151922",
            padx=10,
            pady=3
        )
        self.status_badge.pack(side=tk.RIGHT)

        btn_web = tk.Button(
            header_frame,
            text="工作站",
            font=self.fonts["badge"],
            bg="#151922",
            fg="#00F0FF",
            relief=tk.FLAT,
            command=self.open_web_studio,
            padx=8,
            pady=2
        )
        btn_web.pack(side=tk.RIGHT, padx=(0, 8))
        self._add_hover(btn_web, "#151922", "#1E2330", normal_fg="#00F0FF", hover_fg="#5AF7FF")

        # 計時器卡片
        self.timer_card = tk.Frame(self.main_container, bg="#0F1218", highlightbackground="#1E2330", highlightthickness=1)
        self.timer_card.pack(fill=tk.X, pady=(0, 16), ipady=12)

        self.timer_display = tk.Label(
            self.timer_card,
            text="00:00:00",
            font=self.fonts["timer"],
            fg="#64748B",
            bg="#0F1218"
        )
        self.timer_display.pack()

        # 動態音訊電平視覺儀表 (Live VU Meter)
        self.vu_canvas = tk.Canvas(self.timer_card, width=280, height=14, bg="#0F1218", highlightthickness=0)
        self.vu_canvas.pack(pady=(4, 2))
        self._draw_vu_idle()

        shortcut_hint = "Space / F9 / Ctrl+R" if IS_WINDOWS else "Space / F9 / Cmd+R"
        self.shortcut_hint = shortcut_hint
        self.timer_hint = tk.Label(
            self.timer_card,
            text=f"正在偵測螢幕與麥克風…  {shortcut_hint}",
            font=self.fonts["body"],
            fg="#64748B",
            bg="#0F1218",
            wraplength=480,
            justify="center",
        )
        self.timer_hint.pack(pady=(2, 0))

        # 設定面板卡片
        settings_card = tk.Frame(self.main_container, bg="#0F1218", highlightbackground="#1E2330", highlightthickness=1)
        settings_card.pack(fill=tk.X, pady=(0, 16), padx=0)

        # 1. 螢幕來源
        f1 = tk.Frame(settings_card, bg="#0F1218")
        f1.pack(fill=tk.X, padx=14, pady=(12, 6))
        tk.Label(f1, text="🖥 錄製螢幕", font=self.fonts["body"], fg="#E2E8F0", bg="#0F1218").pack(side=tk.LEFT)
        self.video_combo = ttk.Combobox(f1, style="Dark.TCombobox", state="readonly", width=22)
        self.video_combo.pack(side=tk.RIGHT)

        # 2. 音訊來源
        f2 = tk.Frame(settings_card, bg="#0F1218")
        f2.pack(fill=tk.X, padx=14, pady=6)
        tk.Label(f2, text="🎙 音訊來源", font=self.fonts["body"], fg="#E2E8F0", bg="#0F1218").pack(side=tk.LEFT)
        self.audio_combo = ttk.Combobox(f2, style="Dark.TCombobox", state="readonly", width=22)
        self.audio_combo.pack(side=tk.RIGHT)

        # 3. 畫質與解析度
        f3 = tk.Frame(settings_card, bg="#0F1218")
        f3.pack(fill=tk.X, padx=14, pady=6)
        tk.Label(f3, text="📐 畫質解析度", font=self.fonts["body"], fg="#E2E8F0", bg="#0F1218").pack(side=tk.LEFT)
        self.res_combo = ttk.Combobox(f3, style="Dark.TCombobox", state="readonly", width=22)
        self.res_combo["values"] = [
            "原生（較吃資源）",
            "2K（較吃資源）",
            "1080p（1920×1080）",
            "720p（1280×720）",
        ]
        self.res_combo.current(self.capture_advice["res_index"])
        self.res_combo.pack(side=tk.RIGHT)

        # 4. 幀率 (FPS)
        f4 = tk.Frame(settings_card, bg="#0F1218")
        f4.pack(fill=tk.X, padx=14, pady=6)
        tk.Label(f4, text="⚡ 錄製幀率 (FPS)", font=self.fonts["body"], fg="#E2E8F0", bg="#0F1218").pack(side=tk.LEFT)
        self.fps_combo = ttk.Combobox(f4, style="Dark.TCombobox", state="readonly", width=22)
        self.fps_combo["values"] = ["30 FPS", "60 FPS（較吃資源）", "15 FPS（較省）"]
        self.fps_combo.current(self.capture_advice["fps_index"])
        self.fps_combo.pack(side=tk.RIGHT)

        # 5. 核取選項。直向排，避免窄視窗把三個選項擠到外面。
        f5 = tk.Frame(settings_card, bg="#0F1218")
        f5.pack(fill=tk.X, padx=14, pady=(4, 12))

        accel_text = "Apple 晶片硬體加速" if IS_MAC else ("GPU 硬體加速 (NVENC/QSV/AMF)" if IS_WINDOWS else "硬體加速編碼")
        check_opts = dict(
            font=self.fonts["body"],
            selectcolor="#151922",
            bg="#0F1218",
            activebackground="#0F1218",
            anchor="w",
        )
        tk.Checkbutton(
            f5, text=accel_text, variable=self.hardware_accel_var,
            fg="#00FF9D", activeforeground="#00FF9D", **check_opts
        ).pack(fill=tk.X)
        tk.Checkbutton(
            f5, text="開始前倒數 3 秒", variable=self.countdown_var,
            fg="#94A3B8", activeforeground="#FFFFFF", **check_opts
        ).pack(fill=tk.X)
        tk.Checkbutton(
            f5, text="錄影時收合成懸浮膠囊", variable=self.auto_mini_var,
            fg="#94A3B8", activeforeground="#FFFFFF", **check_opts
        ).pack(fill=tk.X)

        # 錄製主按鈕
        self.record_btn = tk.Button(
            self.main_container,
            text="開始錄影",
            font=self.fonts["title"],
            bg="#FF2A6D",
            fg="#FFFFFF",
            activebackground="#E11D5B",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            cursor="hand2",
            command=self.toggle_recording,
            pady=10,
            state=tk.DISABLED,
        )
        self.record_btn.pack(fill=tk.X, pady=(0, 10))

        # 最近錄影列表卡片 (Recent Recordings Gallery)
        self.recent_card = tk.Frame(self.main_container, bg="#0F1218", highlightbackground="#1E2330", highlightthickness=1)
        self.recent_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        recent_header = tk.Frame(self.recent_card, bg="#0F1218")
        recent_header.pack(fill=tk.X, padx=12, pady=(6, 2))
        tk.Label(recent_header, text="最近錄影", font=self.fonts["bold"], fg="#FFFFFF", bg="#0F1218").pack(side=tk.LEFT)
        btn_refresh = tk.Button(recent_header, text="重新整理", font=self.fonts["body"], bg="#151922", fg="#94A3B8", relief=tk.FLAT, command=self.refresh_recent_list, padx=4)
        btn_refresh.pack(side=tk.RIGHT)
        self._add_hover(btn_refresh, "#151922", "#1E2330")

        self.save_path_label = tk.Label(
            self.recent_card,
            text="",
            font=self.fonts["badge"],
            fg="#64748B",
            bg="#0F1218",
            anchor="w",
        )
        self.save_path_label.pack(fill=tk.X, padx=12, pady=(0, 2))
        self._show_save_path()

        self.recent_list_frame = tk.Frame(self.recent_card, bg="#0F1218")
        self.recent_list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

        # 底部快捷工具列 (開啟資料夾、剪輯影片、播放最新、變更目錄)
        footer_frame = tk.Frame(self.main_container, bg="#0A0C10")
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM)

        btn_folder = tk.Button(
            footer_frame,
            text="📁 資料夾",
            font=self.fonts["body"],
            bg="#151922",
            fg="#E2E8F0",
            relief=tk.FLAT,
            command=self.open_output_folder,
            padx=6,
            pady=5
        )
        btn_folder.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        self._add_hover(btn_folder, "#151922", "#1E2330")

        self.btn_trim = tk.Button(
            footer_frame,
            text="✂️ 剪輯影片",
            font=self.fonts["bold"],
            bg="#00F0FF",
            fg="#060709",
            relief=tk.FLAT,
            command=self.open_editor,
            padx=6,
            pady=5
        )
        self.btn_trim.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self._add_hover(self.btn_trim, "#00F0FF", "#5AF7FF")

        self.btn_play_last = tk.Button(
            footer_frame,
            text="▶️ 播放最新",
            font=self.fonts["body"],
            bg="#151922",
            fg="#E2E8F0",
            relief=tk.FLAT,
            state=tk.DISABLED,
            command=self.play_last_recording,
            padx=6,
            pady=5
        )
        self.btn_play_last.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self._add_hover(self.btn_play_last, "#151922", "#1E2330")

        btn_change = tk.Button(
            footer_frame,
            text="⚙️ 路徑",
            font=self.fonts["body"],
            bg="#151922",
            fg="#E2E8F0",
            relief=tk.FLAT,
            command=self.change_output_folder,
            padx=6,
            pady=5
        )
        btn_change.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))
        self._add_hover(btn_change, "#151922", "#1E2330")

        # 建立懸浮迷你膠囊容器 (平常隱藏)
        self._build_mini_ui()

    def _build_mini_ui(self):
        """建立極簡懸浮膠囊 UI"""
        self.mini_container = tk.Frame(self.root, bg="#060709", highlightbackground="#FF2A6D", highlightthickness=1)

        # 拖曳手柄
        drag_handle = tk.Label(
            self.mini_container,
            text="⋮⋮",
            font=self.fonts["bold"],
            fg="#64748B",
            bg="#060709",
            cursor="fleur"
        )
        drag_handle.pack(side=tk.LEFT, padx=(6, 2))
        drag_handle.bind("<ButtonPress-1>", self._start_drag)
        drag_handle.bind("<B1-Motion>", self._on_drag)

        # 錄製紅點與時間
        self.mini_time_label = tk.Label(
            self.mini_container,
            text="● REC 00:00",
            font=self.fonts["subtitle"],
            fg="#FF2A6D",
            bg="#060709"
        )
        self.mini_time_label.pack(side=tk.LEFT, padx=(6, 2))
        self.mini_time_label.bind("<ButtonPress-1>", self._start_drag)
        self.mini_time_label.bind("<B1-Motion>", self._on_drag)

        # 迷你音訊電平視覺儀表 (Mini VU Meter)
        self.mini_vu_canvas = tk.Canvas(self.mini_container, width=32, height=14, bg="#060709", highlightthickness=0)
        self.mini_vu_canvas.pack(side=tk.LEFT, padx=4)
        self._draw_mini_vu_idle()

        # 停止按鈕
        mini_stop_btn = tk.Button(
            self.mini_container,
            text="⏹ 停止",
            font=self.fonts["bold"],
            bg="#FF2A6D",
            fg="#FFFFFF",
            relief=tk.FLAT,
            command=self.stop_recording,
            padx=8,
            pady=2
        )
        mini_stop_btn.pack(side=tk.RIGHT, padx=6, pady=4)

    def _start_drag(self, event):
        self.drag_x = event.x
        self.drag_y = event.y

    def _on_drag(self, event):
        x = self.root.winfo_x() + (event.x - self.drag_x)
        y = self.root.winfo_y() + (event.y - self.drag_y)
        self.root.geometry(f"+{x}+{y}")

    def _bind_shortcuts(self):
        # 跨平台快捷鍵 Space / F9 / Ctrl+R / Cmd+R
        self.root.bind_all("<F9>", lambda e: self.toggle_recording())
        self.root.bind_all("<Control-r>", lambda e: self.toggle_recording())
        self.root.bind_all("<Command-r>", lambda e: self.toggle_recording())
        self.root.bind("<space>", lambda e: self.toggle_recording())

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
        self.video_combo.current(screen_at)
        self.video_combo.config(state="readonly")

        a_names = ["無音訊 (靜音)"] + [f"[{d['index']}] {d['name']}" for d in a_devs]
        self.audio_combo["values"] = a_names
        self.audio_combo.current(1 if len(a_names) > 1 else 0)
        self.audio_combo.config(state="readonly")

        self.timer_hint.config(text=self._idle_hint())
        if not self.recorder.is_recording and not self.countdown_active:
            self.record_btn.config(state=tk.NORMAL)

    def _switch_to_mini_mode(self):
        """收合為置頂懸浮膠囊"""
        self.is_mini_mode = True
        self._normal_size = (max(self.root.winfo_width(), 500), max(self.root.winfo_height(), 700))
        self.main_container.pack_forget()

        prev_x = self.root.winfo_x()
        prev_y = self.root.winfo_y()

        self.root.geometry(f"300x48+{prev_x}+{prev_y}")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.mini_container.pack(fill=tk.BOTH, expand=True)

    def _switch_to_normal_mode(self):
        """還原為標準視窗模式"""
        self.is_mini_mode = False
        self.mini_container.pack_forget()

        width, height = self._normal_size
        prev_x = self.root.winfo_x()
        prev_y = self.root.winfo_y()

        self.root.geometry(f"{width}x{height}+{prev_x}+{prev_y}")
        self.root.resizable(True, True)
        self.root.attributes("-topmost", False)
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

    def toggle_recording(self):
        if self.countdown_active:
            return

        if self.recorder.is_recording:
            self.stop_recording()
        else:
            if self.countdown_var.get():
                self._start_countdown_and_record()
            else:
                self.start_recording()

    def _start_countdown_and_record(self):
        """執行 3 秒倒數準備動畫"""
        self.countdown_active = True
        self.record_btn.config(state=tk.DISABLED)
        count = 3

        def count_step(val):
            if val > 0:
                self.timer_display.config(text=f"準備: {val}", fg="#FFB800")
                self.status_badge.config(text=f"● 倒數 {val}", fg="#FFB800")
                play_system_alert("ready")
                self.root.after(1000, lambda: count_step(val - 1))
            else:
                self.countdown_active = False
                self.record_btn.config(state=tk.NORMAL)
                self.start_recording()

        count_step(count)

    def start_recording(self):
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

        play_system_alert("start")
        ok, msg = self.recorder.start_recording(
            video_idx=v_idx,
            audio_idx=a_idx,
            fps=fps,
            resolution=resolution,
            use_hardware_accel=use_accel
        )

        if not ok:
            messagebox.showerror("錄影啟動失敗", msg)
            self._update_ui_state(recording=False)
            return

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

    def stop_recording(self):
        if not self.recorder.is_recording or self._stopping:
            return

        self._stopping = True
        self._pending_mini = False
        self.status_badge.config(text="● 正在儲存…", fg="#FFB800")
        self.record_btn.config(state=tk.DISABLED)
        self.root.update_idletasks()

        def work():
            ok, msg = self.recorder.stop_recording()
            self.root.after(0, lambda: self._finish_stop(ok, msg, offer_editor=True))

        threading.Thread(target=work, daemon=True).start()

    def _finish_stop(self, ok, msg, offer_editor):
        self._stopping = False
        play_system_alert("stop")

        if self.is_mini_mode:
            self._switch_to_normal_mode()

        self._update_ui_state(recording=False)
        self.refresh_recent_list()
        self.record_btn.config(state=tk.NORMAL)

        if ok:
            self.btn_play_last.config(state=tk.NORMAL)
            self.timer_hint.config(text=f"已儲存 {Path(msg).name}")
            if offer_editor:
                ans = messagebox.askyesno(
                    "錄影完成",
                    f"影片已存好。\n{Path(msg).name}\n\n要現在剪輯嗎？"
                )
                if ans:
                    self.open_editor(msg)
        else:
            messagebox.showwarning("錄影沒有完成", msg)

    def _update_ui_state(self, recording=False):
        if recording:
            self.status_badge.config(text="● 錄製中", fg="#FF2A6D")
            self.record_btn.config(
                text="停止錄影",
                bg="#E11D5B",
                activebackground="#C01450"
            )
            self.timer_display.config(fg="#FF2A6D")
            self.timer_hint.config(text="正在錄製中... 隨時可按快捷鍵停止")
            self.video_combo.config(state=tk.DISABLED)
            self.audio_combo.config(state=tk.DISABLED)
            self.res_combo.config(state=tk.DISABLED)
            self.fps_combo.config(state=tk.DISABLED)
        else:
            self.status_badge.config(text="● 就緒", fg="#00FF9D")
            self.record_btn.config(
                text="開始錄影",
                bg="#FF2A6D",
                activebackground="#E11D5B"
            )
            self.timer_display.config(text="00:00:00", fg="#64748B")
            self.timer_hint.config(text=self._idle_hint())
            self._draw_vu_idle()
            self._draw_mini_vu_idle()
            self.video_combo.config(state="readonly")
            self.audio_combo.config(state="readonly")
            self.res_combo.config(state="readonly")
            self.fps_combo.config(state="readonly")

    def _draw_vu_idle(self):
        """繪製待機狀態的靜態 VU 電平點"""
        if not hasattr(self, 'vu_canvas'):
            return
        self.vu_canvas.delete("all")
        w, h = 280, 14
        bar_count = 14
        bar_w = 12
        gap = (w - (bar_count * bar_w)) / (bar_count + 1)
        for i in range(bar_count):
            x = gap + i * (bar_w + gap)
            y = h - 3
            self.vu_canvas.create_rectangle(x, y, x + bar_w, h, fill="#1E2330", outline="")

    def _draw_mini_vu_idle(self):
        """繪製迷你懸浮膠囊的靜態電平點"""
        if not hasattr(self, 'mini_vu_canvas'):
            return
        self.mini_vu_canvas.delete("all")
        w, h = 32, 14
        bar_count = 4
        bar_w = 4
        gap = 3
        for i in range(bar_count):
            x = 2 + i * (bar_w + gap)
            y = h - 3
            self.mini_vu_canvas.create_rectangle(x, y, x + bar_w, h, fill="#1E2330", outline="")

    def _idle_hint(self):
        folder = self.recorder.output_dir.name
        label = self.capture_advice["label"]
        return f"{label}  ·  存到 {folder}  ·  {self.shortcut_hint}"

    def _draw_vu_active(self, tick_count):
        """只重畫看得到的那一條，錄影時少佔主執行緒。"""
        if self.is_mini_mode:
            self._draw_mini_vu_active(tick_count)
        else:
            self._draw_main_vu_active(tick_count)

    def _draw_main_vu_active(self, tick_count):
        if hasattr(self, 'vu_canvas'):
            self.vu_canvas.delete("all")
            w, h = 280, 14
            bar_count = 14
            bar_w = 12
            gap = (w - (bar_count * bar_w)) / (bar_count + 1)
            colors = [
                "#00FF9D", "#00FF9D", "#00FF9D", "#00FF9D",
                "#00F0FF", "#00F0FF", "#00F0FF", "#00F0FF",
                "#FFB800", "#FFB800", "#FFB800", "#FFB800",
                "#FF2A6D", "#FF2A6D"
            ]
            for i in range(bar_count):
                wave = math.sin((tick_count * 0.35) + i * 0.55) * 0.5 + 0.5
                noise = random.uniform(0.08, 0.35)
                level = min(1.0, max(0.18, wave * 0.7 + noise))
                bar_h = max(2, int(h * level))
                x = gap + i * (bar_w + gap)
                y = h - bar_h
                self.vu_canvas.create_rectangle(x, y, x + bar_w, h, fill=colors[i], outline="")

    def _draw_mini_vu_active(self, tick_count):
        if hasattr(self, 'mini_vu_canvas'):
            self.mini_vu_canvas.delete("all")
            h = 14
            bar_count = 4
            bar_w = 4
            gap = 3
            mini_colors = ["#00FF9D", "#00F0FF", "#FFB800", "#FF2A6D"]
            for i in range(bar_count):
                wave = math.sin((tick_count * 0.45) + i * 0.75) * 0.5 + 0.5
                noise = random.uniform(0.08, 0.3)
                level = min(1.0, max(0.2, wave * 0.65 + noise))
                bar_h = max(2, int(h * level))
                x = 2 + i * (bar_w + gap)
                y = h - bar_h
                self.mini_vu_canvas.create_rectangle(x, y, x + bar_w, h, fill=mini_colors[i], outline="")

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

            mini_str = f"● REC {mins:02d}:{s:02d}" if hrs == 0 else f"● REC {hrs:02d}:{mins:02d}:{s:02d}"
            self.mini_time_label.config(text=mini_str)

            self._draw_vu_active(self.vu_tick_count)
            interval = 280
        else:
            if getattr(self, '_was_recording', False):
                self._draw_vu_idle()
                self._draw_mini_vu_idle()
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
        VideoEditorWindow(self.root, video_path=target)

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
            files = sorted(
                list(self.recorder.output_dir.glob("*.mp4")) + list(self.recorder.output_dir.glob("*.mov")),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )[:8]
        except Exception:
            files = []

        if not files:
            lbl = tk.Label(
                self.recent_list_frame,
                text="這個資料夾還沒有錄影",
                font=self.fonts["body"],
                fg="#64748B",
                bg="#0F1218",
            )
            lbl.pack(pady=10)
            return

        for p in files:
            row = tk.Frame(self.recent_list_frame, bg="#0F1218", highlightbackground="#1E2330", highlightthickness=1)
            row.pack(fill=tk.X, pady=2, padx=2, ipady=2)

            sz = p.stat().st_size / (1024 * 1024)
            size_text = f"{sz:.1f} MB" if sz >= 0.1 else f"{max(1, int(p.stat().st_size / 1024))} KB"
            time_str = datetime.fromtimestamp(p.stat().st_mtime).strftime("%m/%d %H:%M")
            display_name = p.name if len(p.name) <= 34 else ("…" + p.name[-33:])

            tk.Label(row, text=time_str, font=self.fonts["badge"], fg="#00F0FF", bg="#0F1218").pack(side=tk.LEFT, padx=(6, 4))
            tk.Label(row, text=display_name, font=self.fonts["body"], fg="#E2E8F0", bg="#0F1218").pack(side=tk.LEFT, padx=2)
            tk.Label(row, text=size_text, font=self.fonts["badge"], fg="#64748B", bg="#0F1218").pack(side=tk.LEFT, padx=2)

            btn_del = tk.Button(row, text="🗑", font=self.fonts["bold"], bg="#151922", fg="#FF2A6D", relief=tk.FLAT, command=lambda f=p: self._delete_recording(f), padx=4)
            btn_del.pack(side=tk.RIGHT, padx=2)

            btn_trim = tk.Button(row, text="✂", font=self.fonts["bold"], bg="#151922", fg="#00F0FF", relief=tk.FLAT, command=lambda f=p: self.open_editor(str(f)), padx=4)
            btn_trim.pack(side=tk.RIGHT, padx=2)

            btn_play = tk.Button(row, text="▶", font=self.fonts["bold"], bg="#151922", fg="#00FF9D", relief=tk.FLAT, command=lambda f=p: open_file_or_dir(str(f)), padx=4)
            btn_play.pack(side=tk.RIGHT, padx=2)

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

    def _on_close(self):
        if self.recorder.is_recording:
            if not messagebox.askyesno("正在錄影", "錄影還沒停。要停下來並結束嗎？"):
                return
            self._stopping = True

            def work():
                self.recorder.stop_recording()
                self.root.after(0, self.root.destroy)

            threading.Thread(target=work, daemon=True).start()
            return
        self.root.destroy()


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    app = LiteRecorderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
