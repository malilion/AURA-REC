#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EditorWindow - 影片編輯與剪輯視窗
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
        self.window.title("✂️ 影片剪輯與編輯 (Video Trimmer)")
        self.window.geometry("640x780")
        self.window.minsize(600, 720)
        self.window.configure(bg="#1E1E24")

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

    def _build_ui(self):
        # 主外層滾動或邊界容器
        self.main_frame = tk.Frame(self.window, bg="#1E1E24")
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=18, pady=14)

        # 頂部資訊列
        top_bar = tk.Frame(self.main_frame, bg="#262630", highlightbackground="#363644", highlightthickness=1)
        top_bar.pack(fill=tk.X, pady=(0, 12), ipady=6, padx=0)

        self.lbl_filename = tk.Label(
            top_bar, text="未載入影片", font=("SF Pro Display", 13, "bold"), fg="#FFFFFF", bg="#262630"
        )
        self.lbl_filename.pack(anchor="w", padx=12, pady=(4, 2))

        self.lbl_meta = tk.Label(
            top_bar, text="請選擇要編輯的影片檔案", font=("SF Pro Text", 11), fg="#A0A0B0", bg="#262630"
        )
        self.lbl_meta.pack(anchor="w", padx=12, pady=(0, 4))

        btn_choose = tk.Button(
            top_bar, text="📂 載入其他影片", font=("SF Pro Text", 11), bg="#3A3A4A", fg="#FFFFFF", relief=tk.FLAT,
            command=self.select_video_file, padx=8, pady=3
        )
        btn_choose.place(relx=1.0, rely=0.5, anchor="e", x=-12)

        # 影格預覽區
        preview_container = tk.Frame(self.main_frame, bg="#141418", highlightbackground="#363644", highlightthickness=1)
        preview_container.pack(fill=tk.X, pady=(0, 10))

        self.preview_label = tk.Label(
            preview_container,
            text="載入畫面預覽中...",
            font=("SF Pro Text", 12),
            fg="#6E6E78",
            bg="#141418",
            width=58,
            height=14
        )
        self.preview_label.pack(pady=8)

        # 當前時間標籤
        self.lbl_cur_time = tk.Label(
            self.main_frame, text="時間軸位置: 00:00.0 / 00:00.0", font=("SF Pro Display", 13, "bold"), fg="#30D158", bg="#1E1E24"
        )
        self.lbl_cur_time.pack(pady=(0, 4))

        # 時間軸滑桿
        slider_frame = tk.Frame(self.main_frame, bg="#1E1E24")
        slider_frame.pack(fill=tk.X, pady=(0, 6))

        self.time_slider = ttk.Scale(
            slider_frame, from_=0.0, to=100.0, orient=tk.HORIZONTAL, command=self._on_slider_move
        )
        self.time_slider.pack(fill=tk.X)

        # 時間微調控制列 (-1s, -0.1s, 預覽播放, +0.1s, +1s)
        nudge_frame = tk.Frame(self.main_frame, bg="#1E1E24")
        nudge_frame.pack(fill=tk.X, pady=(0, 12))

        btn_nudge_m1 = tk.Button(nudge_frame, text="⏪ -1s", font=("SF Pro Text", 10), bg="#2B2B36", fg="#FFFFFF", relief=tk.FLAT, command=lambda: self._nudge_time(-1.0))
        btn_nudge_m1.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        btn_nudge_m01 = tk.Button(nudge_frame, text="◀ -0.1s", font=("SF Pro Text", 10), bg="#2B2B36", fg="#FFFFFF", relief=tk.FLAT, command=lambda: self._nudge_time(-0.1))
        btn_nudge_m01.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        self.btn_play_seg = tk.Button(
            nudge_frame, text="▶️ 播放選取片段", font=("SF Pro Text", 11, "bold"), bg="#0A84FF", fg="#FFFFFF", relief=tk.FLAT,
            command=self.preview_play_selection, padx=10, pady=4
        )
        self.btn_play_seg.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)

        btn_nudge_p01 = tk.Button(nudge_frame, text="+0.1s ▶", font=("SF Pro Text", 10), bg="#2B2B36", fg="#FFFFFF", relief=tk.FLAT, command=lambda: self._nudge_time(0.1))
        btn_nudge_p01.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        btn_nudge_p1 = tk.Button(nudge_frame, text="+1s ⏩", font=("SF Pro Text", 10), bg="#2B2B36", fg="#FFFFFF", relief=tk.FLAT, command=lambda: self._nudge_time(1.0))
        btn_nudge_p1.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # 區間裁切控制面板 (起點 / 終點 / 片段長度)
        trim_card = tk.Frame(self.main_frame, bg="#262630", highlightbackground="#363644", highlightthickness=1)
        trim_card.pack(fill=tk.X, pady=(0, 14), ipady=8, padx=0)

        # 起點設定行
        r1 = tk.Frame(trim_card, bg="#262630")
        r1.pack(fill=tk.X, padx=12, pady=4)

        btn_set_start = tk.Button(
            r1, text="🚩 設當前為起點", font=("SF Pro Text", 11, "bold"), bg="#30D158", fg="#FFFFFF", relief=tk.FLAT,
            command=self.set_in_point, padx=8, pady=3
        )
        btn_set_start.pack(side=tk.LEFT)

        self.ent_start = tk.Entry(r1, font=("SF Pro Display", 12), width=10, bg="#1E1E24", fg="#FFFFFF", insertbackground="#FFFFFF", relief=tk.FLAT)
        self.ent_start.insert(0, "00:00.0")
        self.ent_start.pack(side=tk.LEFT, padx=8)
        self.ent_start.bind("<FocusOut>", lambda e: self._update_times_from_entries())
        self.ent_start.bind("<Return>", lambda e: self._update_times_from_entries())

        tk.Label(r1, text="(起始位置)", font=("SF Pro Text", 10), fg="#8E8E93", bg="#262630").pack(side=tk.LEFT)

        # 終點設定行
        r2 = tk.Frame(trim_card, bg="#262630")
        r2.pack(fill=tk.X, padx=12, pady=4)

        btn_set_end = tk.Button(
            r2, text="🏁 設當前為終點", font=("SF Pro Text", 11, "bold"), bg="#FF453A", fg="#FFFFFF", relief=tk.FLAT,
            command=self.set_out_point, padx=8, pady=3
        )
        btn_set_end.pack(side=tk.LEFT)

        self.ent_end = tk.Entry(r2, font=("SF Pro Display", 12), width=10, bg="#1E1E24", fg="#FFFFFF", insertbackground="#FFFFFF", relief=tk.FLAT)
        self.ent_end.insert(0, "00:00.0")
        self.ent_end.pack(side=tk.LEFT, padx=8)
        self.ent_end.bind("<FocusOut>", lambda e: self._update_times_from_entries())
        self.ent_end.bind("<Return>", lambda e: self._update_times_from_entries())

        tk.Label(r2, text="(結束位置)", font=("SF Pro Text", 10), fg="#8E8E93", bg="#262630").pack(side=tk.LEFT)

        # 片段總長顯示
        self.lbl_selected_len = tk.Label(
            trim_card, text="✂️ 裁切選取長度: 00:00.0", font=("SF Pro Text", 12, "bold"), fg="#FFD60A", bg="#262630"
        )
        self.lbl_selected_len.pack(anchor="w", padx=12, pady=(6, 0))

        # 匯出選項與模式
        export_card = tk.Frame(self.main_frame, bg="#262630", highlightbackground="#363644", highlightthickness=1)
        export_card.pack(fill=tk.X, pady=(0, 14), ipady=8)

        tk.Label(export_card, text="📦 匯出設定與模式", font=("SF Pro Text", 12, "bold"), fg="#FFFFFF", bg="#262630").pack(anchor="w", padx=12, pady=(4, 6))

        self.export_mode_var = tk.StringVar(value="lossless")
        self.mute_var = tk.BooleanVar(value=False)

        modes_frame = tk.Frame(export_card, bg="#262630")
        modes_frame.pack(fill=tk.X, padx=12, pady=2)

        rb1 = tk.Radiobutton(
            modes_frame, text="⚡ 無損極速剪裁 (0.5秒秒存，無畫質損失)", variable=self.export_mode_var, value="lossless",
            font=("SF Pro Text", 11), fg="#E0E0E0", selectcolor="#1E1E24", bg="#262630", activebackground="#262630", activeforeground="#FFFFFF"
        )
        rb1.pack(anchor="w", pady=2)

        rb2 = tk.Radiobutton(
            modes_frame, text="🎯 精確幀剪輯 (重新編碼)", variable=self.export_mode_var, value="precise",
            font=("SF Pro Text", 11), fg="#E0E0E0", selectcolor="#1E1E24", bg="#262630", activebackground="#262630", activeforeground="#FFFFFF"
        )
        rb2.pack(anchor="w", pady=2)

        rb3 = tk.Radiobutton(
            modes_frame, text="🎞️ 匯出為 GIF 動畫 (適合分享/教學)", variable=self.export_mode_var, value="gif",
            font=("SF Pro Text", 11), fg="#E0E0E0", selectcolor="#1E1E24", bg="#262630", activebackground="#262630", activeforeground="#FFFFFF"
        )
        rb3.pack(anchor="w", pady=2)

        rb4 = tk.Radiobutton(
            modes_frame, text="🎵 提取純音訊 (MP3 / M4A)", variable=self.export_mode_var, value="audio",
            font=("SF Pro Text", 11), fg="#E0E0E0", selectcolor="#1E1E24", bg="#262630", activebackground="#262630", activeforeground="#FFFFFF"
        )
        rb4.pack(anchor="w", pady=2)

        cb_mute = tk.Checkbutton(
            export_card, text="🔇 移除聲音 (靜音剪輯)", variable=self.mute_var,
            font=("SF Pro Text", 11), fg="#A0A0B0", selectcolor="#1E1E24", bg="#262630", activebackground="#262630", activeforeground="#FFFFFF"
        )
        cb_mute.pack(anchor="w", padx=12, pady=(4, 0))

        # 匯出執行大按鈕
        self.btn_export = tk.Button(
            self.main_frame,
            text="🚀 立即匯出選取片段",
            font=("SF Pro Display", 14, "bold"),
            bg="#30D158",
            fg="#FFFFFF",
            activebackground="#28A745",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            cursor="hand2",
            command=self.perform_export,
            pady=10
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

        # 更新 UI 顯示
        self.lbl_filename.config(text=f"📹 {info['file_name']}")
        meta_str = f"解析度: {info['width']}x{info['height']} | 總長: {sec_to_time_str(self.total_duration)} | 大小: {info['size_mb']} MB"
        if info['has_audio']:
            meta_str += " | 🔊 含音軌"
        else:
            meta_str += " | 🔇 無音軌"
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
            text=f"時間軸位置: {sec_to_time_str(sec)} / {sec_to_time_str(self.total_duration)}"
        )
        self._request_preview(sec)

    def _nudge_time(self, delta):
        new_time = max(0.0, min(self.total_duration, self.current_time + delta))
        self.current_time = new_time
        self.time_slider.set(new_time)
        self.lbl_cur_time.config(
            text=f"時間軸位置: {sec_to_time_str(new_time)} / {sec_to_time_str(self.total_duration)}"
        )
        self._request_preview(new_time)

    def _request_preview(self, sec):
        """非同步請求影格預覽 (支援防抖)"""
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

            ppm_data = self.editor.get_frame_ppm(self.current_file, target_sec, width=480, height=270)
            if ppm_data:
                self.window.after(0, lambda data=ppm_data: self._update_preview_image(data))

            time.sleep(0.04)

    def _update_preview_image(self, ppm_data):
        try:
            self.preview_image = tk.PhotoImage(data=ppm_data)
            self.preview_label.config(image=self.preview_image, text="")
        except Exception as e:
            print("Preview render error:", e)

    def set_in_point(self):
        """將當前時間軸位置設為起點"""
        self.start_sec = self.current_time
        if self.start_sec > self.end_sec:
            self.end_sec = self.total_duration
            self.ent_end.delete(0, tk.END)
            self.ent_end.insert(0, sec_to_time_str(self.end_sec))

        self.ent_start.delete(0, tk.END)
        self.ent_start.insert(0, sec_to_time_str(self.start_sec))
        self._update_selection_length_label()

    def set_out_point(self):
        """將當前時間軸位置設為終點"""
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
            text=f"✂️ 裁切片段長度: {sec_to_time_str(sel_dur)}  ({sec_to_time_str(self.start_sec)} ➔ {sec_to_time_str(self.end_sec)})"
        )

    def preview_play_selection(self):
        """使用 ffplay 播放選取的片段"""
        if self._playing_process and self._playing_process.poll() is None:
            self._playing_process.terminate()
            self._playing_process = None
            self.btn_play_seg.config(text="▶️ 播放選取片段", bg="#0A84FF")
            return

        dur = self.end_sec - self.start_sec
        if dur <= 0:
            messagebox.showwarning("提示", "選取長度需大於 0 秒")
            return

        self._playing_process = self.editor.play_segment(self.current_file, self.start_sec, dur)
        self.btn_play_seg.config(text="⏹ 停止預覽播放", bg="#FF453A")

        def monitor_process():
            if self._playing_process:
                self._playing_process.wait()
            self.window.after(0, lambda: self.btn_play_seg.config(text="▶️ 播放選取片段", bg="#0A84FF"))

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

        # 建議檔名
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

        # 禁用按鈕並顯示處理狀態
        self.btn_export.config(text="⏳ 正在處理與匯出中...", state=tk.DISABLED, bg="#FF9F0A")

        def run_export_thread():
            mute = self.mute_var.get()
            ok = False
            msg = ""

            try:
                if mode == "lossless":
                    ok, msg = self.editor.trim_lossless(self.current_file, out_path, self.start_sec, self.end_sec)
                elif mode == "precise":
                    ok, msg = self.editor.trim_precise(self.current_file, out_path, self.start_sec, self.end_sec, mute_audio=mute)
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
        self.btn_export.config(text="🚀 立即匯出選取片段", state=tk.NORMAL, bg="#30D158")
        if ok:
            ans = messagebox.askyesno(
                "匯出成功！🎉",
                f"檔案已成功儲存至：\n{out_path}\n\n是否立即在 Finder 中開啟？"
            )
            if ans:
                subprocess.run(["open", "-R", out_path])
        else:
            messagebox.showerror("匯出失敗", f"匯出過程發生錯誤：\n{msg}")

    def _on_close(self):
        if self._playing_process and self._playing_process.poll() is None:
            self._playing_process.terminate()
        self.window.destroy()
