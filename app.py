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

import os
import subprocess
import threading
import time
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
    open_file_or_dir
)


class LiteRecorderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("輕量桌面錄影 (Lite Screen Recorder)")
        self.root.geometry("470x590")
        self.root.minsize(450, 530)
        self.root.configure(bg="#1E1E24")

        # 跨平台字型
        self.fonts = get_ui_fonts()

        # 核心錄影實例
        self.recorder = ScreenRecorder()

        # 狀態變數
        self.is_mini_mode = False
        self.countdown_active = False
        self.auto_mini_var = tk.BooleanVar(value=True)
        self.countdown_var = tk.BooleanVar(value=True)
        self.hardware_accel_var = tk.BooleanVar(value=True)

        self.video_devices = []
        self.audio_devices = []

        # 拖曳視窗支援 (Mini 模式用)
        self.drag_x = 0
        self.drag_y = 0

        # 初始化 UI
        self._init_styles()
        self._build_main_ui()
        self._bind_shortcuts()

        # 載入硬體設備
        self._refresh_devices()

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
            fieldbackground="#2B2B36",
            background="#3A3A4A",
            foreground="#FFFFFF",
            arrowcolor="#A0A0B0",
            darkcolor="#1E1E24",
            lightcolor="#3A3A4A",
            insertcolor="#FFFFFF",
        )
        style.map("Dark.TCombobox", fieldbackground=[("readonly", "#2B2B36")])

    def _build_main_ui(self):
        # 主容器
        self.main_container = tk.Frame(self.root, bg="#1E1E24")
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        # 標題欄
        header_frame = tk.Frame(self.main_container, bg="#1E1E24")
        header_frame.pack(fill=tk.X, pady=(0, 14))

        title_label = tk.Label(
            header_frame,
            text="🎥 輕量螢幕錄製",
            font=self.fonts["title"],
            fg="#FFFFFF",
            bg="#1E1E24"
        )
        title_label.pack(side=tk.LEFT)

        self.status_badge = tk.Label(
            header_frame,
            text="● 就緒",
            font=self.fonts["badge"],
            fg="#30D158",
            bg="#2A2A34",
            padx=10,
            pady=3
        )
        self.status_badge.pack(side=tk.RIGHT)

        # 計時器卡片
        self.timer_card = tk.Frame(self.main_container, bg="#262630", highlightbackground="#363644", highlightthickness=1)
        self.timer_card.pack(fill=tk.X, pady=(0, 16), ipady=12)

        self.timer_display = tk.Label(
            self.timer_card,
            text="00:00:00",
            font=self.fonts["timer"],
            fg="#8E8E93",
            bg="#262630"
        )
        self.timer_display.pack()

        shortcut_hint = "Space / F9 / Ctrl+R" if IS_WINDOWS else "Space / F9 / Cmd+R"
        self.timer_hint = tk.Label(
            self.timer_card,
            text=f"點擊下方按鈕或按 {shortcut_hint} 開始錄製",
            font=self.fonts["body"],
            fg="#6E6E78",
            bg="#262630"
        )
        self.timer_hint.pack(pady=(4, 0))

        # 設定面板卡片
        settings_card = tk.Frame(self.main_container, bg="#262630", highlightbackground="#363644", highlightthickness=1)
        settings_card.pack(fill=tk.X, pady=(0, 16), padx=0)

        # 1. 螢幕來源
        f1 = tk.Frame(settings_card, bg="#262630")
        f1.pack(fill=tk.X, padx=14, pady=(12, 6))
        tk.Label(f1, text="🖥 錄製螢幕", font=self.fonts["body"], fg="#D1D1D6", bg="#262630").pack(side=tk.LEFT)
        self.video_combo = ttk.Combobox(f1, style="Dark.TCombobox", state="readonly", width=22)
        self.video_combo.pack(side=tk.RIGHT)

        # 2. 音訊來源
        f2 = tk.Frame(settings_card, bg="#262630")
        f2.pack(fill=tk.X, padx=14, pady=6)
        tk.Label(f2, text="🎙 音訊來源", font=self.fonts["body"], fg="#D1D1D6", bg="#262630").pack(side=tk.LEFT)
        self.audio_combo = ttk.Combobox(f2, style="Dark.TCombobox", state="readonly", width=22)
        self.audio_combo.pack(side=tk.RIGHT)

        # 3. 畫質與解析度
        f3 = tk.Frame(settings_card, bg="#262630")
        f3.pack(fill=tk.X, padx=14, pady=6)
        tk.Label(f3, text="📐 畫質解析度", font=self.fonts["body"], fg="#D1D1D6", bg="#262630").pack(side=tk.LEFT)
        self.res_combo = ttk.Combobox(f3, style="Dark.TCombobox", state="readonly", width=22)
        self.res_combo["values"] = ["原生解析度 (Native)", "2K (2560x1440)", "1080p FHD (1920x1080)", "720p HD (1280x720)"]
        self.res_combo.current(0)
        self.res_combo.pack(side=tk.RIGHT)

        # 4. 幀率 (FPS)
        f4 = tk.Frame(settings_card, bg="#262630")
        f4.pack(fill=tk.X, padx=14, pady=6)
        tk.Label(f4, text="⚡ 錄製幀率 (FPS)", font=self.fonts["body"], fg="#D1D1D6", bg="#262630").pack(side=tk.LEFT)
        self.fps_combo = ttk.Combobox(f4, style="Dark.TCombobox", state="readonly", width=22)
        self.fps_combo["values"] = ["30 FPS (推薦平衡)", "60 FPS (高流暢動態)", "15 FPS (極省空間)"]
        self.fps_combo.current(0)
        self.fps_combo.pack(side=tk.RIGHT)

        # 5. 核取選項 (硬體加速、倒數、自動縮小)
        f5 = tk.Frame(settings_card, bg="#262630")
        f5.pack(fill=tk.X, padx=14, pady=(8, 12))

        accel_text = "Apple 晶片硬體加速" if IS_MAC else ("GPU 硬體加速 (NVENC/QSV/AMF)" if IS_WINDOWS else "硬體加速編碼")
        cb_accel = tk.Checkbutton(
            f5, text=accel_text, variable=self.hardware_accel_var,
            font=self.fonts["body"], fg="#30D158", selectcolor="#2B2B36", bg="#262630", activebackground="#262630", activeforeground="#30D158"
        )
        cb_accel.pack(side=tk.LEFT, padx=(0, 10))

        cb_countdown = tk.Checkbutton(
            f5, text="3秒倒數", variable=self.countdown_var,
            font=self.fonts["body"], fg="#A0A0B0", selectcolor="#2B2B36", bg="#262630", activebackground="#262630", activeforeground="#FFFFFF"
        )
        cb_countdown.pack(side=tk.LEFT, padx=(0, 10))

        cb_mini = tk.Checkbutton(
            f5, text="收合為懸浮膠囊", variable=self.auto_mini_var,
            font=self.fonts["body"], fg="#A0A0B0", selectcolor="#2B2B36", bg="#262630", activebackground="#262630", activeforeground="#FFFFFF"
        )
        cb_mini.pack(side=tk.LEFT)

        # 錄製主按鈕
        self.record_btn = tk.Button(
            self.main_container,
            text=f"🔴 開始錄影 ({shortcut_hint})",
            font=self.fonts["title"],
            bg="#FF453A",
            fg="#FFFFFF",
            activebackground="#D32F2F",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            cursor="hand2",
            command=self.toggle_recording,
            pady=10
        )
        self.record_btn.pack(fill=tk.X, pady=(0, 12))

        # 底部快捷工具列 (開啟資料夾、剪輯影片、播放最新、變更目錄)
        footer_frame = tk.Frame(self.main_container, bg="#1E1E24")
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM)

        btn_folder = tk.Button(
            footer_frame,
            text="📁 資料夾",
            font=self.fonts["body"],
            bg="#2E2E3A",
            fg="#E0E0E0",
            relief=tk.FLAT,
            command=self.open_output_folder,
            padx=6,
            pady=5
        )
        btn_folder.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

        self.btn_trim = tk.Button(
            footer_frame,
            text="✂️ 剪輯影片",
            font=self.fonts["bold"],
            bg="#0A84FF",
            fg="#FFFFFF",
            relief=tk.FLAT,
            command=self.open_editor,
            padx=6,
            pady=5
        )
        self.btn_trim.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        self.btn_play_last = tk.Button(
            footer_frame,
            text="▶️ 播放最新",
            font=self.fonts["body"],
            bg="#2E2E3A",
            fg="#E0E0E0",
            relief=tk.FLAT,
            state=tk.DISABLED,
            command=self.play_last_recording,
            padx=6,
            pady=5
        )
        self.btn_play_last.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        btn_change = tk.Button(
            footer_frame,
            text="⚙️ 路徑",
            font=self.fonts["body"],
            bg="#2E2E3A",
            fg="#E0E0E0",
            relief=tk.FLAT,
            command=self.change_output_folder,
            padx=6,
            pady=5
        )
        btn_change.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))

        # 建立懸浮迷你膠囊容器 (平常隱藏)
        self._build_mini_ui()

    def _build_mini_ui(self):
        """建立極簡懸浮膠囊 UI"""
        self.mini_container = tk.Frame(self.root, bg="#18181E", highlightbackground="#FF453A", highlightthickness=1)

        # 拖曳手柄
        drag_handle = tk.Label(
            self.mini_container,
            text="⋮⋮",
            font=self.fonts["bold"],
            fg="#6E6E78",
            bg="#18181E",
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
            fg="#FF453A",
            bg="#18181E"
        )
        self.mini_time_label.pack(side=tk.LEFT, padx=6)
        self.mini_time_label.bind("<ButtonPress-1>", self._start_drag)
        self.mini_time_label.bind("<B1-Motion>", self._on_drag)

        # 停止按鈕
        mini_stop_btn = tk.Button(
            self.mini_container,
            text="⏹ 停止",
            font=self.fonts["bold"],
            bg="#FF453A",
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
        v_devs, a_devs = self.recorder.get_devices()
        self.video_devices = v_devs
        self.audio_devices = a_devs

        v_names = [f"[{d['index']}] {d['name']}" for d in v_devs]
        self.video_combo["values"] = v_names
        if v_names:
            self.video_combo.current(0)

        a_names = ["無音訊 (靜音)"] + [f"[{d['index']}] {d['name']}" for d in a_devs]
        self.audio_combo["values"] = a_names
        if len(a_names) > 1:
            self.audio_combo.current(1)
        else:
            self.audio_combo.current(0)

    def _switch_to_mini_mode(self):
        """收合為置頂懸浮膠囊"""
        self.is_mini_mode = True
        self.main_container.pack_forget()

        prev_x = self.root.winfo_x()
        prev_y = self.root.winfo_y()

        self.root.geometry(f"250x44+{prev_x}+{prev_y}")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.mini_container.pack(fill=tk.BOTH, expand=True)

    def _switch_to_normal_mode(self):
        """還原為標準視窗模式"""
        self.is_mini_mode = False
        self.mini_container.pack_forget()

        prev_x = self.root.winfo_x()
        prev_y = self.root.winfo_y()

        self.root.geometry(f"470x590+{prev_x}+{prev_y}")
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
                self.timer_display.config(text=f"準備: {val}", fg="#FF9F0A")
                self.status_badge.config(text=f"● 倒數 {val}", fg="#FF9F0A")
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

        self._update_ui_state(recording=True)

        if self.auto_mini_var.get():
            self._switch_to_mini_mode()

    def stop_recording(self):
        if not self.recorder.is_recording:
            return

        self.status_badge.config(text="● 正在儲存封裝...", fg="#FF9F0A")
        self.root.update_idletasks()

        ok, msg = self.recorder.stop_recording()
        play_system_alert("stop")

        if self.is_mini_mode:
            self._switch_to_normal_mode()

        self._update_ui_state(recording=False)

        if ok:
            self.btn_play_last.config(state=tk.NORMAL)
            self.timer_hint.config(text=f"已儲存: {Path(msg).name}")
            # 詢問是否進入編輯剪輯
            ans = messagebox.askyesno(
                "錄影完成！🎉",
                f"影片已成功儲存！\n檔名：{Path(msg).name}\n\n是否立即開啟【剪輯編輯器】進行裁剪或轉為 GIF？"
            )
            if ans:
                self.open_editor(msg)
        else:
            messagebox.showwarning("錄影提示", msg)

    def _update_ui_state(self, recording=False):
        shortcut_hint = "Space / F9 / Ctrl+R" if IS_WINDOWS else "Space / F9 / Cmd+R"
        if recording:
            self.status_badge.config(text="● 錄製中 (REC)", fg="#FF453A")
            self.record_btn.config(
                text=f"⏹ 停止錄影 ({shortcut_hint})",
                bg="#D32F2F",
                activebackground="#B71C1C"
            )
            self.timer_display.config(fg="#FF453A")
            self.timer_hint.config(text="正在錄製中... 隨時可按快捷鍵停止")
            self.video_combo.config(state=tk.DISABLED)
            self.audio_combo.config(state=tk.DISABLED)
            self.res_combo.config(state=tk.DISABLED)
            self.fps_combo.config(state=tk.DISABLED)
        else:
            self.status_badge.config(text="● 就緒", fg="#30D158")
            self.record_btn.config(
                text=f"🔴 開始錄影 ({shortcut_hint})",
                bg="#FF453A",
                activebackground="#D32F2F"
            )
            self.timer_display.config(fg="#8E8E93")
            self.video_combo.config(state="readonly")
            self.audio_combo.config(state="readonly")
            self.res_combo.config(state="readonly")
            self.fps_combo.config(state="readonly")

    def _timer_tick(self):
        if self.recorder.is_recording:
            sec = self.recorder.get_duration()
            hrs = sec // 3600
            mins = (sec % 3600) // 60
            s = sec % 60
            time_str = f"{hrs:02d}:{mins:02d}:{s:02d}"
            self.timer_display.config(text=time_str)

            mini_str = f"● REC {mins:02d}:{s:02d}" if hrs == 0 else f"● REC {hrs:02d}:{mins:02d}:{s:02d}"
            self.mini_time_label.config(text=mini_str)

        self.root.after(500, self._timer_tick)

    def open_output_folder(self):
        """在檔案總管 / Finder 中開啟儲存路徑"""
        open_file_or_dir(str(self.recorder.output_dir))

    def change_output_folder(self):
        """選擇新的錄影儲存目錄"""
        chosen = filedialog.askdirectory(initialdir=str(self.recorder.output_dir), title="選擇錄影儲存目錄")
        if chosen:
            self.recorder.output_dir = Path(chosen)
            self.timer_hint.config(text=f"儲存路徑已設定至: {Path(chosen).name}")
            messagebox.showinfo("目錄已變更", f"錄影檔案將儲存至：\n{chosen}")

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

    def _on_close(self):
        if self.recorder.is_recording:
            if messagebox.askyesno("正在錄影", "目前錄影尚未停止，是否要停止錄影並結束程式？"):
                self.recorder.stop_recording()
                self.root.destroy()
        else:
            self.root.destroy()


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    app = LiteRecorderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
