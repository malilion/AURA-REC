#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EditorWindow - 影片編輯與剪輯視窗 (macOS & Windows 跨平台支援)
包含：畫面影格即時預覽、時間軸精準滑桿、起點/終點設定、無損極速裁剪、精確重編碼、GIF 匯出與音訊提取
"""

import os
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

from video_editor import VideoEditor
from aura_widgets import AuraButton, AuraCheck, AuraRadio, AuraScale
from platform_utils import (
    get_ui_fonts,
    open_file_or_dir,
    UI,
    apply_widget_style,
)


def sec_to_time_str(seconds):
    """將秒數格式化為 HH:MM:SS.s 或 MM:SS.s"""
    if seconds is None:
        return "00:00.0"
    seconds = max(0.0, float(seconds))
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = seconds % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:04.1f}"
    return f"{mins:02d}:{secs:04.1f}"


def time_str_to_sec(time_str):
    """解析 MM:SS.s 或 秒數 字串為 float"""
    try:
        parts = time_str.strip().split(":")
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except Exception:
        pass
    return None


class VideoEditorWindow:
    def __init__(self, parent, video_path=None):
        self.parent = parent
        self.editor = VideoEditor()

        self.window = tk.Toplevel(parent)
        self.window.title("剪輯 — AURA REC")
        self.window.geometry("720x780")
        self.window.minsize(640, 700)
        self.window.configure(bg=UI["bg"])
        self.fonts = get_ui_fonts()
        apply_widget_style(ttk.Style(self.window), self.fonts)

        # 影片資訊與狀態
        self.video_info = None
        self.current_file = str(video_path) if video_path else None
        self.total_duration = 0.0
        self.current_time = 0.0

        self.start_sec = 0.0
        self.end_sec = 0.0

        # 預覽影像快取與更新執行緒鎖
        self.preview_image = None
        self._preview_lock = threading.Lock()
        self._preview_thread = None
        self._preview_pending_time = None

        # 播放進程
        self._playing_process = None

        self._build_ui()

        if self.current_file and os.path.exists(self.current_file):
            self.load_video(self.current_file)
        else:
            self.select_video_file()

        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

    def _tool_button(self, parent, text, command):
        return AuraButton(parent, text=text, command=command, style="Ghost.TButton")

    def _build_ui(self):
        self.main_frame = tk.Frame(self.window, bg=UI["bg"])
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        top_bar = tk.Frame(self.main_frame, bg=UI["bg"])
        top_bar.pack(fill=tk.X, pady=(0, 8))

        name_col = tk.Frame(top_bar, bg=UI["bg"])
        name_col.pack(side=tk.LEFT, fill=tk.X, expand=True)
        title_row = tk.Frame(name_col, bg=UI["bg"])
        title_row.pack(anchor="w", fill=tk.X)
        tk.Label(
            title_row, text="EDIT", font=self.fonts["badge"], fg=UI["blue"], bg=UI["bg"]
        ).pack(side=tk.LEFT, padx=(0, 8))
        self.lbl_filename = tk.Label(
            title_row, text="未載入影片", font=self.fonts["bold"], fg=UI["white"], bg=UI["bg"], anchor="w"
        )
        self.lbl_filename.pack(side=tk.LEFT)
        self.lbl_meta = tk.Label(
            name_col, text="請選擇要編輯的影片", font=self.fonts["body"], fg=UI["muted"], bg=UI["bg"], anchor="w"
        )
        self.lbl_meta.pack(anchor="w", pady=(2, 0))

        self._tool_button(top_bar, "開啟…", self.select_video_file).pack(side=tk.RIGHT, padx=(8, 0))

        preview_container = tk.Frame(
            self.main_frame,
            bg=UI["preview"],
            highlightbackground=UI["edge"],
            highlightthickness=1,
        )
        preview_container.pack(fill=tk.X, pady=(0, 6))
        self.preview_label = tk.Label(
            preview_container,
            text="預覽會顯示在這裡",
            font=self.fonts["body"],
            fg=UI["muted"],
            bg=UI["preview"],
            width=64,
            height=8,
        )
        self.preview_label.pack(pady=4)

        self.lbl_cur_time = tk.Label(
            self.main_frame, text="00:00.0 / 00:00.0", font=self.fonts["body"], fg=UI["muted"], bg=UI["bg"]
        )
        self.lbl_cur_time.pack(anchor="w")

        slider_frame = tk.Frame(self.main_frame, bg=UI["bg"])
        slider_frame.pack(fill=tk.X, pady=(0, 4))
        self.time_slider = AuraScale(
            slider_frame, from_=0.0, to=100.0, command=self._on_slider_move
        )
        self.time_slider.pack(fill=tk.X)

        nudge_frame = tk.Frame(self.main_frame, bg=UI["bg"])
        nudge_frame.pack(fill=tk.X, pady=(0, 6))
        self._tool_button(nudge_frame, "−1 秒", lambda: self._nudge_time(-1.0)).pack(side=tk.LEFT, padx=(0, 4))
        self._tool_button(nudge_frame, "−0.1 秒", lambda: self._nudge_time(-0.1)).pack(side=tk.LEFT, padx=4)
        self.btn_play_seg = AuraButton(
            nudge_frame,
            text="播放",
            style="Play.TButton",
            command=self.preview_play_selection,
        )
        self.btn_play_seg.pack(side=tk.LEFT, padx=8)
        self._tool_button(nudge_frame, "+0.1 秒", lambda: self._nudge_time(0.1)).pack(side=tk.LEFT, padx=4)
        self._tool_button(nudge_frame, "+1 秒", lambda: self._nudge_time(1.0)).pack(side=tk.LEFT, padx=4)

        trim_card = tk.Frame(self.main_frame, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1)
        trim_card.pack(fill=tk.X, pady=(0, 10))
        tk.Label(trim_card, text="選取範圍", font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]).pack(anchor="w", padx=12, pady=(8, 2))

        def time_row(parent, label, command):
            row = tk.Frame(parent, bg=UI["card"])
            row.pack(fill=tk.X, padx=12, pady=2)
            tk.Label(row, text=label, font=self.fonts["body"], fg=UI["muted"], bg=UI["card"], width=4, anchor="w").pack(side=tk.LEFT)
            entry = tk.Entry(
                row, font=self.fonts["badge"], width=12, bg=UI["field"], fg=UI["text"],
                insertbackground=UI["blue"], relief=tk.FLAT, bd=0,
                highlightthickness=1, highlightbackground=UI["edge"], highlightcolor=UI["blue"],
            )
            entry.insert(0, "00:00.0")
            entry.pack(side=tk.LEFT, padx=(4, 8), ipady=3)
            entry.bind("<FocusOut>", lambda e: self._update_times_from_entries())
            entry.bind("<Return>", lambda e: self._update_times_from_entries())
            self._tool_button(row, command[0], command[1]).pack(side=tk.LEFT)
            return entry

        self.ent_start = time_row(trim_card, "起點", ("設為起點", self.set_in_point))
        self.ent_end = time_row(trim_card, "終點", ("設為終點", self.set_out_point))
        self.lbl_selected_len = tk.Label(
            trim_card, text="長度 00:00.0", font=self.fonts["body"], fg=UI["text"], bg=UI["card"]
        )
        self.lbl_selected_len.pack(anchor="w", padx=12, pady=(4, 8))

        export_card = tk.Frame(self.main_frame, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1)
        export_card.pack(fill=tk.X, pady=(0, 10))
        tk.Label(export_card, text="匯出", font=self.fonts["bold"], fg=UI["white"], bg=UI["card"]).pack(anchor="w", padx=12, pady=(8, 2))

        self.export_mode_var = tk.StringVar(value="lossless")
        self.mute_var = tk.BooleanVar(value=False)
        modes = [
            ("無損裁切（不重新編碼）", "lossless"),
            ("重新編碼（可調速度、比例、色彩）", "precise"),
            ("GIF", "gif"),
            ("只輸出音訊", "audio"),
        ]
        for text, value in modes:
            AuraRadio(
                export_card, text=text, variable=self.export_mode_var, value=value
            ).pack(anchor="w", padx=12)

        adv_frame = tk.Frame(export_card, bg=UI["card"])
        adv_frame.pack(fill=tk.X, padx=12, pady=(4, 8))

        def labeled_combo(row, column, label, values, width):
            tk.Label(
                adv_frame, text=label, font=self.fonts["body"], fg=UI["muted"], bg=UI["card"]
            ).grid(row=row, column=column * 2, sticky="w", padx=(0, 4), pady=4)
            combo = ttk.Combobox(adv_frame, style="App.TCombobox", state="readonly", width=width)
            combo["values"] = values
            combo.current(0)
            combo.grid(row=row, column=column * 2 + 1, sticky="w", padx=(0, 16), pady=4)
            return combo

        self.speed_combo = labeled_combo(0, 0, "速度", ["1.0x", "0.5x", "1.5x", "2.0x"], 6)
        self.ratio_combo = labeled_combo(0, 1, "比例", ["原始比例", "9:16 直式", "16:9 橫式", "1:1 方形"], 10)
        self.color_combo = labeled_combo(1, 0, "色彩", ["原色", "鮮豔", "高對比"], 8)
        AuraCheck(adv_frame, text="靜音", variable=self.mute_var).grid(row=1, column=2, sticky="w", pady=4)

        self.btn_export = AuraButton(
            self.main_frame,
            text="匯出",
            style="Primary.TButton",
            command=self.perform_export,
        )
        self.btn_export.pack(fill=tk.X, pady=(0, 4))

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
        audio = "有音訊" if info["has_audio"] else "沒有音訊"
        meta_str = (
            f"{info['width']}×{info['height']}  ·  {sec_to_time_str(self.total_duration)}"
            f"  ·  {info['size_mb']} MB  ·  {audio}"
        )
        self.lbl_meta.config(text=meta_str)

        self.time_slider.config(from_=0.0, to=self.total_duration)
        self.time_slider.set(0.0)

        self.ent_start.delete(0, tk.END)
        self.ent_start.insert(0, sec_to_time_str(0.0))

        self.ent_end.delete(0, tk.END)
        self.ent_end.insert(0, sec_to_time_str(self.total_duration))

        self._update_selection_length_label()
        self._request_preview(0.0)

    def _on_slider_move(self, val):
        sec = float(val)
        self.current_time = sec
        self.lbl_cur_time.config(
            text=f"{sec_to_time_str(sec)} / {sec_to_time_str(self.total_duration)}"
        )
        self._request_preview(sec)

    def _nudge_time(self, delta):
        new_time = max(0.0, min(self.total_duration, self.current_time + delta))
        self.current_time = new_time
        self.time_slider.set(new_time)
        self.lbl_cur_time.config(
            text=f"{sec_to_time_str(new_time)} / {sec_to_time_str(self.total_duration)}"
        )
        self._request_preview(new_time)

    def _request_preview(self, sec):
        self._preview_pending_time = sec
        if self._preview_thread is None or not self._preview_thread.is_alive():
            self._preview_thread = threading.Thread(target=self._worker_fetch_preview, daemon=True)
            self._preview_thread.start()

    def _worker_fetch_preview(self):
        while True:
            with self._preview_lock:
                target_sec = self._preview_pending_time
                self._preview_pending_time = None

            if target_sec is None:
                break

            ppm_data = self.editor.get_frame_ppm(self.current_file, target_sec, width=320, height=180)
            if ppm_data:
                self.window.after(0, lambda data=ppm_data: self._update_preview_image(data))

            time.sleep(0.15)

    def _update_preview_image(self, ppm_data):
        try:
            self.preview_image = tk.PhotoImage(data=ppm_data)
            self.preview_label.config(image=self.preview_image, text="")
        except Exception as e:
            print("Preview render error:", e)

    def set_in_point(self):
        self.start_sec = self.current_time
        if self.start_sec > self.end_sec:
            self.end_sec = self.total_duration
            self.ent_end.delete(0, tk.END)
            self.ent_end.insert(0, sec_to_time_str(self.end_sec))

        self.ent_start.delete(0, tk.END)
        self.ent_start.insert(0, sec_to_time_str(self.start_sec))
        self._update_selection_length_label()

    def set_out_point(self):
        self.end_sec = self.current_time
        if self.end_sec < self.start_sec:
            self.start_sec = 0.0
            self.ent_start.delete(0, tk.END)
            self.ent_start.insert(0, sec_to_time_str(self.start_sec))

        self.ent_end.delete(0, tk.END)
        self.ent_end.insert(0, sec_to_time_str(self.end_sec))
        self._update_selection_length_label()

    def _update_times_from_entries(self):
        s = time_str_to_sec(self.ent_start.get())
        e = time_str_to_sec(self.ent_end.get())

        if s is not None and 0.0 <= s <= self.total_duration:
            self.start_sec = s
        if e is not None and 0.0 <= e <= self.total_duration:
            self.end_sec = e

        self.ent_start.delete(0, tk.END)
        self.ent_start.insert(0, sec_to_time_str(self.start_sec))
        self.ent_end.delete(0, tk.END)
        self.ent_end.insert(0, sec_to_time_str(self.end_sec))
        self._update_selection_length_label()

    def _update_selection_length_label(self):
        sel_dur = max(0.0, self.end_sec - self.start_sec)
        self.lbl_selected_len.config(
            text=f"長度 {sec_to_time_str(sel_dur)}（{sec_to_time_str(self.start_sec)} – {sec_to_time_str(self.end_sec)}）"
        )

    def preview_play_selection(self):
        if self._playing_process and self._playing_process.poll() is None:
            self._playing_process.terminate()
            self._playing_process = None
            self.btn_play_seg.config(text="播放", style="Play.TButton")
            return

        dur = self.end_sec - self.start_sec
        if dur <= 0:
            messagebox.showwarning("提示", "選取長度需大於 0 秒")
            return

        self._playing_process = self.editor.play_segment(self.current_file, self.start_sec, dur)
        self.btn_play_seg.config(text="停止", style="Stop.TButton")

        def monitor_process():
            if self._playing_process:
                self._playing_process.wait()
            self.window.after(0, lambda: self.btn_play_seg.config(text="播放", style="Play.TButton"))

        threading.Thread(target=monitor_process, daemon=True).start()

    def perform_export(self):
        if not self.current_file:
            messagebox.showwarning("提示", "尚未載入影片！")
            return

        self._update_times_from_entries()
        dur = self.end_sec - self.start_sec
        if dur <= 0.05:
            messagebox.showwarning("錯誤", "裁切長度過短，請確認起點與終點設定！")
            return

        mode = self.export_mode_var.get()
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

        def run_export_thread():
            mute = self.mute_var.get()
            ok = False
            msg = ""

            # 讀取進階參數
            spd = 1.0
            try:
                spd = float(self.speed_combo.get().replace("x", ""))
            except Exception:
                pass

            rat_str = self.ratio_combo.get()
            rat = "9:16" if "9:16" in rat_str else ("16:9" if "16:9" in rat_str else ("1:1" if "1:1" in rat_str else "original"))

            col_str = self.color_combo.get()
            br, ct, sat = 0.0, 1.0, 1.0
            if "鮮豔" in col_str:
                sat = 1.3
                ct = 1.05
            elif "高對比" in col_str:
                ct = 1.25
                br = -0.02

            try:
                if mode == "lossless":
                    ok, msg = self.editor.trim_lossless(self.current_file, out_path, self.start_sec, self.end_sec)
                elif mode == "precise":
                    ok, msg = self.editor.trim_advanced(
                        self.current_file, out_path, self.start_sec, self.end_sec,
                        speed=spd, aspect_ratio=rat, brightness=br, contrast=ct, saturation=sat,
                        mute_audio=mute
                    )
                elif mode == "gif":
                    ok, msg = self.editor.export_gif(self.current_file, out_path, self.start_sec, self.end_sec)
                elif mode == "audio":
                    ok, msg = self.editor.extract_audio(self.current_file, out_path, self.start_sec, self.end_sec)
            except Exception as e:
                ok = False
                msg = str(e)

            self.window.after(0, lambda: self._on_export_finished(ok, msg, out_path))

        threading.Thread(target=run_export_thread, daemon=True).start()

    def _on_export_finished(self, ok, msg, out_path):
        self.btn_export.config(text="匯出", state=tk.NORMAL)
        if ok:
            ans = messagebox.askyesno(
                "匯出完成",
                f"已儲存：\n{out_path}\n\n要在資料夾裡顯示嗎？",
            )
            if ans:
                open_file_or_dir(out_path, reveal=True)
        else:
            messagebox.showerror("匯出失敗", f"匯出過程發生錯誤：\n{msg}")

    def _on_close(self):
        if self._playing_process and self._playing_process.poll() is None:
            self._playing_process.terminate()
        self.window.destroy()
