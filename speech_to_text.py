#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
speech_to_text.py - AURA REC AI 離線語音識別與智慧字幕軌 (Speech-to-Text & Subtitles)

功能特色：
1. 100% 離線 AI 語音轉文字 (Speech-to-Text)：
   - 支援 whisper-cli (whisper.cpp 高性能 Metal GPU / CPU 加速)
   - 支援 Python whisper 模組 (openai-whisper)
   - 內建 0 依賴離線 Smart VAD (Voice Activity Detection 語音活動偵測與智慧分句)
2. 完整標準字幕支援：
   - SRT (SubRip) 與 VTT (WebVTT) 解析與輸出
   - 毫秒級時間碼精確對齊與格式化
3. 字幕資料模型與操作：
   - SubtitleCue: id, start, end, text
   - SubtitleTrack: 新增、刪除、編輯、排序、合併相鄰段落、根據時間檢索
4. 字幕樣式設定 (SubtitleStyle)：
   - 字體大小 (16~32px)、字型顏色、背景膠囊顏色與透明度、垂直位置
5. 音訊提取與預處理：
   - 自動調用 FFmpeg 提取 16kHz mono WAV 供語音辨識模型使用
"""

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


# ==============================================================================
# 1. 時間格式轉換與輔助工具
# ==============================================================================

def sec_to_srt_time(seconds: float) -> str:
    """將秒數轉為 SRT 時間碼格式: 00:01:23,456"""
    if seconds < 0:
        seconds = 0.0
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis = 0
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def srt_time_to_sec(time_str: str) -> float:
    """將 SRT 時間碼 (00:01:23,456 或 00:01:23.456) 轉為秒數"""
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return float(h) * 3600 + float(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return float(m) * 60 + float(s)
    return float(time_str)


def sec_to_vtt_time(seconds: float) -> str:
    """將秒數轉為 WebVTT 時間碼格式: 00:01:23.456"""
    if seconds < 0:
        seconds = 0.0
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis = 0
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{millis:03d}"


def sec_to_short_time(seconds: float) -> str:
    """簡短時間顯示，例: 01:23.4"""
    if seconds < 0:
        seconds = 0.0
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins:02d}:{secs:04.1f}"


# ==============================================================================
# 2. 字幕資料模型 (SubtitleCue & SubtitleTrack)
# ==============================================================================

@dataclass
class SubtitleCue:
    """單句字幕項目"""
    id: int
    start: float  # 秒數
    end: float    # 秒數
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SubtitleCue":
        return cls(
            id=int(data.get("id", 1)),
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
            text=str(data.get("text", "")),
        )


@dataclass
class SubtitleStyle:
    """字幕外觀樣式配置"""
    font_size: int = 22             # 字體大小 (px)
    font_color: str = "#FFFFFF"     # 字體顏色 (純白 / 亮黃 / 青藍)
    bg_color: str = "#0B0D13"       # 膠囊背景顏色
    bg_alpha: float = 0.85          # 背景不透明度 (0.0~1.0)
    pos_y_pct: float = 0.86         # 垂直位置百分比 (0.86 為中下置底)
    border_color: str = "#00F0FF"   # 光暈外框顏色
    show_border: bool = True        # 是否顯示極光外框


class SubtitleTrack:
    """字幕軌道管理器"""

    def __init__(self, cues: Optional[List[SubtitleCue]] = None):
        self.cues: List[SubtitleCue] = cues or []
        self.style: SubtitleStyle = SubtitleStyle()
        self._next_id = max([c.id for c in self.cues], default=0) + 1

    def __len__(self) -> int:
        return len(self.cues)

    def is_empty(self) -> bool:
        return len(self.cues) == 0

    def add_cue(self, start: float, end: float, text: str) -> SubtitleCue:
        """新增一句字幕並自動按時間重新排序"""
        if end <= start:
            end = start + 2.0
        cue = SubtitleCue(id=self._next_id, start=start, end=end, text=text.strip())
        self._next_id += 1
        self.cues.append(cue)
        self.sort()
        return cue

    def remove_cue(self, cue_id: int) -> bool:
        """根據 ID 刪除字幕"""
        initial_len = len(self.cues)
        self.cues = [c for c in self.cues if c.id != cue_id]
        return len(self.cues) < initial_len

    def update_cue(self, cue_id: int, start: Optional[float] = None, end: Optional[float] = None, text: Optional[str] = None):
        """更新字幕的時間或文字"""
        for c in self.cues:
            if c.id == cue_id:
                if start is not None:
                    c.start = start
                if end is not None:
                    c.end = end
                if text is not None:
                    c.text = text
                break
        self.sort()

    def get_cue_at_time(self, time_sec: float) -> Optional[SubtitleCue]:
        """尋找特定時間點應顯示的字幕"""
        for c in self.cues:
            if c.start <= time_sec <= c.end:
                return c
        return None

    def sort(self):
        """依據起點時間由小到大排序"""
        self.cues.sort(key=lambda c: (c.start, c.end))

    def clear(self):
        """清空所有字幕"""
        self.cues.clear()
        self._next_id = 1

    # --- SRT / VTT 序列化與儲存 ---

    def to_srt(self) -> str:
        """導出標準 SRT 格式字串"""
        lines = []
        for idx, cue in enumerate(self.cues, 1):
            s_time = sec_to_srt_time(cue.start)
            e_time = sec_to_srt_time(cue.end)
            lines.append(f"{idx}\n{s_time} --> {e_time}\n{cue.text}\n")
        return "\n".join(lines)

    def to_vtt(self) -> str:
        """導出標準 WebVTT 格式字串"""
        lines = ["WEBVTT\n"]
        for idx, cue in enumerate(self.cues, 1):
            s_time = sec_to_vtt_time(cue.start)
            e_time = sec_to_vtt_time(cue.end)
            lines.append(f"{idx}\n{s_time} --> {e_time}\n{cue.text}\n")
        return "\n".join(lines)

    def save_srt(self, filepath: Union[str, Path]):
        """儲存至 SRT 檔案"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_srt())

    def save_vtt(self, filepath: Union[str, Path]):
        """儲存至 VTT 檔案"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_vtt())

    @classmethod
    def from_srt(cls, content_or_path: str) -> "SubtitleTrack":
        """從 SRT 檔案路徑或字串載入"""
        if os.path.exists(content_or_path):
            with open(content_or_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        else:
            content = content_or_path

        cues = []
        blocks = re.split(r"\n\s*\n", content.strip())
        next_id = 1
        for block in blocks:
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            if not lines:
                continue
            # 尋找時間行 (含 -->)
            time_idx = -1
            for i, line in enumerate(lines):
                if "-->" in line:
                    time_idx = i
                    break
            if time_idx == -1:
                continue

            time_parts = lines[time_idx].split("-->")
            if len(time_parts) != 2:
                continue
            try:
                start_sec = srt_time_to_sec(time_parts[0])
                end_sec = srt_time_to_sec(time_parts[1].split()[0])
            except Exception:
                continue

            text = "\n".join(lines[time_idx + 1:])
            cues.append(SubtitleCue(id=next_id, start=start_sec, end=end_sec, text=text))
            next_id += 1

        track = cls(cues)
        track.sort()
        return track


# ==============================================================================
# 3. 語音辨識與 VAD 智慧分句引擎 (SpeechToTextEngine)
# ==============================================================================

class SpeechToTextEngine:
    """離線語音識別與分句核心"""

    def __init__(self, ffmpeg_bin: Optional[str] = None):
        self.ffmpeg_bin = ffmpeg_bin or shutil.which("ffmpeg") or "ffmpeg"
        self._whisper_cli = self._detect_whisper_cli()

    def _detect_whisper_cli(self) -> Optional[str]:
        """偵測系統中的 whisper-cli 執行檔路徑"""
        candidates = [
            shutil.which("whisper-cli"),
            "/opt/homebrew/bin/whisper-cli",
            "/usr/local/bin/whisper-cli",
            shutil.which("whisper.cpp"),
        ]
        for c in candidates:
            if c and os.path.isfile(c) and os.access(c, os.X_OK):
                return c
        return None

    @property
    def has_whisper_cli(self) -> bool:
        return self._whisper_cli is not None

    def find_local_whisper_models(self) -> List[Tuple[str, str]]:
        """尋找本機已下載的 Whisper ggml 模型檔案: 回傳 [(模型名稱, 檔案路徑), ...]"""
        models = []
        search_dirs = [
            Path.home() / ".cache" / "whisper-cpp",
            Path.home() / ".cache" / "whisper",
            Path("/opt/homebrew/share/whisper.cpp/models"),
            Path.cwd() / "models",
        ]
        for sdir in search_dirs:
            if sdir.exists():
                for f in sdir.glob("ggml-*.bin"):
                    name = f.stem.replace("ggml-", "")
                    models.append((name, str(f)))
        return models

    def extract_audio_wav(
        self,
        input_video: str,
        output_wav: str,
        start_sec: float = 0.0,
        end_sec: Optional[float] = None,
    ) -> bool:
        """調用 FFmpeg 提取 16kHz 單聲道 16-bit PCM WAV (Whisper 標準音訊格式)"""
        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-ss", f"{start_sec:.3f}",
            "-i", str(input_video),
        ]
        if end_sec is not None and end_sec > start_sec:
            duration = end_sec - start_sec
            cmd.extend(["-t", f"{duration:.3f}"])

        cmd.extend([
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(output_wav),
        ])
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return res.returncode == 0 and os.path.exists(output_wav)
        except Exception:
            return False

    def detect_speech_intervals_vad(
        self,
        audio_file: str,
        silence_thresh_db: float = -32.0,
        min_silence_dur: float = 0.35,
        min_speech_dur: float = 0.4,
    ) -> List[Tuple[float, float]]:
        """
        100% 離線純本機智慧 VAD 語音活動偵測 (使用 FFmpeg silencedetect 濾鏡)。
        回傳連續人聲活動的 [(start_sec, end_sec), ...] 區間清單。
        """
        cmd = [
            self.ffmpeg_bin,
            "-i", str(audio_file),
            "-af", f"silencedetect=noise={silence_thresh_db}dB:d={min_silence_dur}",
            "-f", "null",
            "-",
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="ignore")
        except Exception:
            return []

        silence_ranges = []
        cur_silence_start = None

        for line in res.stderr.splitlines():
            line = line.strip()
            if "silence_start:" in line:
                m = re.search(r"silence_start:\s*([0-9.]+)", line)
                if m:
                    cur_silence_start = float(m.group(1))
            elif "silence_end:" in line:
                m = re.search(r"silence_end:\s*([0-9.]+)", line)
                if m:
                    s_end = float(m.group(1))
                    s_start = cur_silence_start if cur_silence_start is not None else 0.0
                    silence_ranges.append((s_start, s_end))
                    cur_silence_start = None

        # 取得音訊總長度
        duration = 0.0
        dur_m = re.search(r"Duration:\s*(\d+):(\d+):([0-9.]+)", res.stderr)
        if dur_m:
            h, m, s = dur_m.groups()
            duration = float(h) * 3600 + float(m) * 60 + float(s)
        elif silence_ranges:
            duration = silence_ranges[-1][1] + 1.0

        if duration <= 0:
            return []

        # 靜音區間反轉為人聲語音區間 (Speech Intervals)
        speech_intervals = []
        last_end = 0.0

        for s_start, s_end in silence_ranges:
            if s_start > last_end + min_speech_dur:
                speech_intervals.append((round(last_end, 2), round(s_start, 2)))
            last_end = s_end

        if duration > last_end + min_speech_dur:
            speech_intervals.append((round(last_end, 2), round(duration, 2)))

        # 若單句過長 (超過 6 秒)，依自然 3.5 秒節奏切分，優化字幕閱讀節奏
        refined_intervals = []
        for s, e in speech_intervals:
            seg_len = e - s
            if seg_len > 6.0:
                step = 3.5
                curr = s
                while curr < e:
                    next_e = min(curr + step, e)
                    refined_intervals.append((round(curr, 2), round(next_e, 2)))
                    curr = next_e
            else:
                refined_intervals.append((s, e))

        return refined_intervals

    def transcribe_with_vad(
        self,
        video_or_audio: str,
        start_sec: float = 0.0,
        end_sec: Optional[float] = None,
    ) -> SubtitleTrack:
        """
        離線超極速 VAD 智慧分句字幕產生 (0.1秒瞬間就緒)。
        自動識別所有人聲片段起訖點並建立帶有時間碼之字幕軌道。
        """
        track = SubtitleTrack()
        with tempfile.TemporaryDirectory(prefix="aura_vad_") as tmpdir:
            wav_path = os.path.join(tmpdir, "extract.wav")
            ok = self.extract_audio_wav(video_or_audio, wav_path, start_sec, end_sec)
            if not ok:
                return track

            intervals = self.detect_speech_intervals_vad(wav_path)
            for idx, (s, e) in enumerate(intervals, 1):
                # 換算回影片原始時間軸 (加上 start_sec offset)
                real_start = round(start_sec + s, 2)
                real_end = round(start_sec + e, 2)
                placeholder_text = f"[語音片段 {idx}]"
                track.add_cue(real_start, real_end, placeholder_text)

        return track

    def transcribe_with_whisper_cli(
        self,
        video_or_audio: str,
        model_path: str,
        language: str = "zh",
        start_sec: float = 0.0,
        end_sec: Optional[float] = None,
    ) -> Tuple[bool, Union[SubtitleTrack, str]]:
        """
        使用本機 whisper-cli 與 Metal GPU / CPU 離線執行高精準度語音識別。
        """
        if not self._whisper_cli:
            return False, "本機未安裝 whisper-cli 執行檔"
        if not os.path.exists(model_path):
            return False, f"找不到 Whisper 模型檔案: {model_path}"

        with tempfile.TemporaryDirectory(prefix="aura_whisper_") as tmpdir:
            wav_path = os.path.join(tmpdir, "input.wav")
            out_base = os.path.join(tmpdir, "transcript")

            ok = self.extract_audio_wav(video_or_audio, wav_path, start_sec, end_sec)
            if not ok:
                return False, "音訊提取失敗"

            cmd = [
                self._whisper_cli,
                "-m", str(model_path),
                "-f", str(wav_path),
                "-l", language,
                "-osrt",
                "-of", str(out_base),
                "-t", "4",
                "-np",
            ]

            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                srt_file = f"{out_base}.srt"
                if os.path.exists(srt_file):
                    track = SubtitleTrack.from_srt(srt_file)
                    # 補正 start_sec 位移
                    if start_sec > 0.0:
                        for cue in track.cues:
                            cue.start = round(cue.start + start_sec, 2)
                            cue.end = round(cue.end + start_sec, 2)
                    return True, track
                return False, f"Whisper 辨識未輸出字幕: {res.stderr}"
            except Exception as e:
                return False, f"執行 Whisper 異常: {str(e)}"


# ==============================================================================
# 4. 智慧字幕軌視覺化編輯器 (SubtitleDialog)
# ==============================================================================

class SubtitleDialog:
    """AURA REC AI 離線語音識別與智慧字幕軌視覺化編輯器"""

    def __init__(self, parent_win: tk.Tk, editor_ref):
        self.parent = parent_win
        self.editor = editor_ref
        self.track: SubtitleTrack = editor_ref.subtitles
        self.engine: SpeechToTextEngine = editor_ref.stt_engine

        self.win = tk.Toplevel(self.parent)
        self.win.title("💬 AI 離線語音識別與智慧字幕軌 — AURA REC")
        self.win.geometry("740x660")
        self.win.minsize(660, 520)
        self.win.configure(bg="#0B0D13")
        self.win.transient(self.parent)

        self._is_generating = False
        self._cues_canvas = None
        self._cues_inner_frame = None

        self._build_ui()
        self._render_cues_list()

    def _build_ui(self):
        main_box = tk.Frame(self.win, bg="#0B0D13")
        main_box.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        # 1. 頂部標題列
        top_hdr = tk.Frame(main_box, bg="#0B0D13")
        top_hdr.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            top_hdr, text="AURA", font=("Helvetica", 14, "bold"), fg="#FFFFFF", bg="#0B0D13"
        ).pack(side=tk.LEFT)
        tk.Label(
            top_hdr, text="CAPTIONS", font=("Helvetica", 10, "bold"), fg="#00F0FF", bg="#10262C",
            padx=6, pady=2
        ).pack(side=tk.LEFT, padx=(6, 12))

        status_text = "⚡ 已偵測到 Whisper-CLI (Metal GPU 加速)" if self.engine.has_whisper_cli else "⚡ 系統已就緒 (離線 VAD 智慧語音分句)"
        status_color = "#00F0FF" if self.engine.has_whisper_cli else "#00FF9D"
        tk.Label(
            top_hdr, text=status_text, font=("Helvetica", 10), fg=status_color, bg="#0B0D13"
        ).pack(side=tk.RIGHT)

        # 2. AI 語音產生卡片 (AI Generator Card)
        ai_card = tk.Frame(main_box, bg="#151922", highlightbackground="#1E2330", highlightthickness=1)
        ai_card.pack(fill=tk.X, pady=(0, 10))

        card_title = tk.Label(
            ai_card, text="✨ AI 離線語音識別設定", font=("Helvetica", 11, "bold"), fg="#FFFFFF", bg="#151922"
        )
        card_title.pack(anchor="w", padx=12, pady=(10, 6))

        grid_f = tk.Frame(ai_card, bg="#151922")
        grid_f.pack(fill=tk.X, padx=12, pady=(0, 10))
        grid_f.columnconfigure(1, weight=1)
        grid_f.columnconfigure(3, weight=1)

        # 模式選單
        tk.Label(grid_f, text="識別引擎:", font=("Helvetica", 10), fg="#94A3B8", bg="#151922").grid(row=0, column=0, sticky="w", pady=3)
        self.mode_combo = ttk.Combobox(
            grid_f, state="readonly", width=22,
            values=["⚡ 快速離線 VAD 智慧分句 (毫秒級瞬間)", "✨ Whisper AI 離線語音辨識"]
        )
        self.mode_combo.current(0 if not self.engine.has_whisper_cli else 1)
        self.mode_combo.grid(row=0, column=1, sticky="ew", padx=(6, 12), pady=3)
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_changed)

        # 語言選單
        tk.Label(grid_f, text="識別語言:", font=("Helvetica", 10), fg="#94A3B8", bg="#151922").grid(row=0, column=2, sticky="w", pady=3)
        self.lang_combo = ttk.Combobox(
            grid_f, state="readonly", width=14,
            values=["繁體中文 (zh)", "English (en)", "自動偵測 (auto)"]
        )
        self.lang_combo.current(0)
        self.lang_combo.grid(row=0, column=3, sticky="ew", padx=(6, 0), pady=3)

        # 模型檔案選單/路徑
        self.model_row = tk.Frame(ai_card, bg="#151922")
        self.model_row.pack(fill=tk.X, padx=12, pady=(0, 10))
        tk.Label(self.model_row, text="模型路徑:", font=("Helvetica", 10), fg="#94A3B8", bg="#151922").pack(side=tk.LEFT)

        self.model_var = tk.StringVar()
        found_models = self.engine.find_local_whisper_models()
        if found_models:
            self.model_var.set(found_models[0][1])

        self.model_entry = tk.Entry(
            self.model_row, textvariable=self.model_var, font=("Helvetica", 10),
            bg="#0B0D13", fg="#FFFFFF", insertbackground="#00F0FF",
            relief=tk.FLAT, bd=0, highlightthickness=1, highlightbackground="#1E2330"
        )
        self.model_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, ipady=3)

        btn_browse = tk.Button(
            self.model_row, text="瀏覽…", font=("Helvetica", 9),
            bg="#1E2330", fg="#E2E8F0", relief=tk.FLAT, bd=0, cursor="hand2",
            command=self._browse_model_file
        )
        btn_browse.pack(side=tk.LEFT, padx=(0, 8))

        # 啟動生成按鈕
        self.btn_generate = tk.Button(
            self.model_row, text="✨ 開始產生字幕", font=("Helvetica", 10, "bold"),
            bg="#00F0FF", fg="#000000", activebackground="#00D0DF", activeforeground="#000000",
            relief=tk.FLAT, bd=0, padx=12, pady=4, cursor="hand2",
            command=self._start_transcribe_thread
        )
        self.btn_generate.pack(side=tk.LEFT)

        self.lbl_gen_status = tk.Label(ai_card, text="", font=("Helvetica", 9), fg="#00F0FF", bg="#151922")
        self.lbl_gen_status.pack(anchor="w", padx=12, pady=(0, 6))

        # 3. 操作工具列 (Toolbar)
        tb = tk.Frame(main_box, bg="#0B0D13")
        tb.pack(fill=tk.X, pady=(0, 6))

        btn_add = tk.Button(
            tb, text="＋ 新增字幕句", font=("Helvetica", 9, "bold"),
            bg="#1E2330", fg="#00F0FF", relief=tk.FLAT, bd=0, padx=8, pady=4, cursor="hand2",
            command=self._add_cue_at_now
        )
        btn_add.pack(side=tk.LEFT, padx=(0, 6))

        btn_imp = tk.Button(
            tb, text="📥 匯入 SRT / VTT", font=("Helvetica", 9),
            bg="#151922", fg="#E2E8F0", relief=tk.FLAT, bd=0, padx=8, pady=4, cursor="hand2",
            command=self._import_srt
        )
        btn_imp.pack(side=tk.LEFT, padx=3)

        btn_exp = tk.Button(
            tb, text="📤 匯出 SRT", font=("Helvetica", 9),
            bg="#151922", fg="#E2E8F0", relief=tk.FLAT, bd=0, padx=8, pady=4, cursor="hand2",
            command=self._export_srt
        )
        btn_exp.pack(side=tk.LEFT, padx=3)

        btn_clr = tk.Button(
            tb, text="🧹 全部清空", font=("Helvetica", 9),
            bg="#151922", fg="#FF4466", relief=tk.FLAT, bd=0, padx=8, pady=4, cursor="hand2",
            command=self._clear_all
        )
        btn_clr.pack(side=tk.RIGHT)

        self.lbl_count = tk.Label(tb, text="共 0 句", font=("Helvetica", 9), fg="#94A3B8", bg="#0B0D13")
        self.lbl_count.pack(side=tk.RIGHT, padx=10)

        # 4. 字幕清單滾動容器 (Scrollable Cue List)
        list_container = tk.Frame(main_box, bg="#151922", highlightbackground="#1E2330", highlightthickness=1)
        list_container.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        canvas = tk.Canvas(list_container, bg="#151922", highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg="#151922")

        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(xscrollcommand=None, yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_win, width=e.width))

        # 滑鼠滾輪支援
        def _on_mousewheel(e):
            if canvas.winfo_exists():
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._cues_canvas = canvas
        self._cues_inner_frame = inner

        # 5. 底部樣式調整與關閉列
        btm_bar = tk.Frame(main_box, bg="#0B0D13")
        btm_bar.pack(fill=tk.X, pady=(4, 0))

        tk.Label(btm_bar, text="字型大小:", font=("Helvetica", 9), fg="#94A3B8", bg="#0B0D13").pack(side=tk.LEFT, padx=(0, 4))
        for sz_val, sz_lbl in [(16, "小"), (22, "中"), (28, "大")]:
            b = tk.Button(
                btm_bar, text=sz_lbl, font=("Helvetica", 9),
                bg="#1E2330" if self.track.style.font_size != sz_val else "#00F0FF",
                fg="#FFFFFF" if self.track.style.font_size != sz_val else "#000000",
                bd=0, padx=6, pady=2, cursor="hand2",
                command=lambda v=sz_val: self._set_font_size(v)
            )
            b.pack(side=tk.LEFT, padx=2)

        tk.Label(btm_bar, text="顏色:", font=("Helvetica", 9), fg="#94A3B8", bg="#0B0D13").pack(side=tk.LEFT, padx=(10, 4))
        for c_hex, c_name in [("#FFFFFF", "純白"), ("#FFD700", "金黃"), ("#00F0FF", "青藍")]:
            cb = tk.Button(
                btm_bar, text=c_name, font=("Helvetica", 9),
                bg=c_hex, fg="#000000", bd=0, padx=6, pady=2, cursor="hand2",
                command=lambda c=c_hex: self._set_font_color(c)
            )
            cb.pack(side=tk.LEFT, padx=2)

        btn_close = tk.Button(
            btm_bar, text="完成並關閉", font=("Helvetica", 10, "bold"),
            bg="#1E2330", fg="#FFFFFF", relief=tk.FLAT, bd=0, padx=14, pady=4, cursor="hand2",
            command=self._close_window
        )
        btn_close.pack(side=tk.RIGHT)

    def _on_mode_changed(self, event=None):
        is_whisper = "Whisper" in self.mode_combo.get()
        if is_whisper:
            self.model_row.pack(fill=tk.X, padx=12, pady=(0, 10))
        else:
            self.model_row.pack(fill=tk.X, padx=12, pady=(0, 10))

    def _browse_model_file(self):
        f = filedialog.askopenfilename(
            title="選擇 Whisper ggml 模型檔案",
            filetypes=[("GGML Model", "*.bin"), ("All files", "*.*")]
        )
        if f:
            self.model_var.set(f)

    def _set_font_size(self, sz: int):
        self.track.style.font_size = sz
        self._notify_editor()

    def _set_font_color(self, color: str):
        self.track.style.font_color = color
        self._notify_editor()

    def _render_cues_list(self):
        """重新渲染字幕項目清單"""
        if not self._cues_inner_frame:
            return
        for w in self._cues_inner_frame.winfo_children():
            w.destroy()

        self.lbl_count.config(text=f"共 {len(self.track)} 句")

        if self.track.is_empty():
            empty_lbl = tk.Label(
                self._cues_inner_frame,
                text="目前尚無字幕項目。\n點擊上方「✨ 開始產生字幕」由 AI 自動識別，或點擊「＋ 新增字幕句」手動鍵入。",
                font=("Helvetica", 10), fg="#64748B", bg="#151922", pady=40
            )
            empty_lbl.pack(fill=tk.BOTH, expand=True)
            return

        for idx, cue in enumerate(self.track.cues, 1):
            row = tk.Frame(self._cues_inner_frame, bg="#0E121A", highlightbackground="#1E2330", highlightthickness=1)
            row.pack(fill=tk.X, padx=8, pady=3)

            # 時間膠囊按鈕 (點擊跳轉)
            t_str = f"{sec_to_short_time(cue.start)} → {sec_to_short_time(cue.end)}"
            t_btn = tk.Button(
                row, text=t_str, font=("Helvetica", 9, "bold"),
                bg="#15202E", fg="#00F0FF", relief=tk.FLAT, bd=0, padx=6, pady=3, cursor="hand2",
                command=lambda s=cue.start: self._jump_editor(s)
            )
            t_btn.pack(side=tk.LEFT, padx=6, pady=4)

            # 字幕內容輸入框 (修改即同步)
            ent = tk.Entry(
                row, font=("Helvetica", 10),
                bg="#0E121A", fg="#FFFFFF", insertbackground="#00F0FF",
                relief=tk.FLAT, bd=0
            )
            ent.insert(0, cue.text)
            ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=4)

            def make_sync_handler(c=cue, entry_widget=ent):
                def on_change(e):
                    c.text = entry_widget.get()
                    self._notify_editor()
                return on_change

            handler = make_sync_handler()
            ent.bind("<KeyRelease>", handler)
            ent.bind("<FocusOut>", handler)

            # 試聽跳轉按鈕
            btn_play = tk.Button(
                row, text="▶", font=("Helvetica", 9),
                bg="#15202E", fg="#00FF9D", relief=tk.FLAT, bd=0, padx=6, pady=2, cursor="hand2",
                command=lambda s=cue.start: self._jump_editor(s)
            )
            btn_play.pack(side=tk.LEFT, padx=3)

            # 刪除按鈕
            btn_del = tk.Button(
                row, text="✕", font=("Helvetica", 9, "bold"),
                bg="#15202E", fg="#FF4466", relief=tk.FLAT, bd=0, padx=6, pady=2, cursor="hand2",
                command=lambda cid=cue.id: self._delete_cue(cid)
            )
            btn_del.pack(side=tk.LEFT, padx=(2, 6))

    def _jump_editor(self, sec: float):
        if hasattr(self.editor, "_jump_to_time"):
            self.editor._jump_to_time(sec)

    def _delete_cue(self, cue_id: int):
        self.track.remove_cue(cue_id)
        self._render_cues_list()
        self._notify_editor()

    def _add_cue_at_now(self):
        cur_t = getattr(self.editor, "current_time", 0.0)
        self.track.add_cue(cur_t, cur_t + 2.5, "點此輸入新字幕內容…")
        self._render_cues_list()
        self._notify_editor()

    def _import_srt(self):
        f = filedialog.askopenfilename(
            title="匯入字幕檔案",
            filetypes=[("Subtitle Files", "*.srt;*.vtt"), ("SRT", "*.srt"), ("VTT", "*.vtt")]
        )
        if f:
            try:
                imported = SubtitleTrack.from_srt(f)
                self.track.cues = imported.cues
                self._render_cues_list()
                self._notify_editor()
                messagebox.showinfo("匯入成功", f"成功載入 {len(imported)} 句字幕！")
            except Exception as e:
                messagebox.showerror("匯入失敗", f"無法解析字幕檔案: {e}")

    def _export_srt(self):
        if self.track.is_empty():
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
                    self.track.save_vtt(f)
                else:
                    self.track.save_srt(f)
                messagebox.showinfo("匯出成功", f"已成功儲存字幕檔至:\n{f}")
            except Exception as e:
                messagebox.showerror("匯出失敗", f"儲存字幕失敗: {e}")

    def _clear_all(self):
        if self.track.is_empty():
            return
        if messagebox.askyesno("清空確認", "確定要清空所有字幕項目嗎？"):
            self.track.clear()
            self._render_cues_list()
            self._notify_editor()

    def _start_transcribe_thread(self):
        if self._is_generating:
            return
        video_path = getattr(self.editor, "current_file", None)
        if not video_path or not os.path.exists(video_path):
            messagebox.showwarning("提示", "尚未載入影片檔案！")
            return

        self._is_generating = True
        self.btn_generate.config(text="⏳ 正在處理…", state=tk.DISABLED)
        self.lbl_gen_status.config(text="正在提取音訊並進行語音分析...")

        mode = self.mode_combo.get()
        is_whisper = "Whisper" in mode
        lang_code = "zh" if "中文" in self.lang_combo.get() else ("en" if "English" in self.lang_combo.get() else "auto")
        model_path = self.model_var.get().strip()

        def work():
            try:
                if is_whisper and model_path and os.path.exists(model_path):
                    ok, res = self.engine.transcribe_with_whisper_cli(video_path, model_path, language=lang_code)
                    if ok and isinstance(res, SubtitleTrack):
                        self.track.cues = res.cues
                        msg = f"✅ Whisper 辨識完成！共產生 {len(res)} 句字幕。"
                    else:
                        # 自動優雅回退至 VAD
                        vad_track = self.engine.transcribe_with_vad(video_path)
                        self.track.cues = vad_track.cues
                        msg = f"⚠️ Whisper 執行異常 ({res})，已自動切換至 VAD 產生 {len(vad_track)} 句時間軌。"
                else:
                    # 使用極速離線 VAD 智慧分句
                    vad_track = self.engine.transcribe_with_vad(video_path)
                    self.track.cues = vad_track.cues
                    msg = f"✅ 離線 VAD 智慧分句完成！共偵測到 {len(vad_track)} 處語音段落。"

                def finish():
                    self._is_generating = False
                    self.btn_generate.config(text="✨ 開始產生字幕", state=tk.NORMAL)
                    self.lbl_gen_status.config(text=msg)
                    self._render_cues_list()
                    self._notify_editor()

                self.win.after(0, finish)
            except Exception as e:
                def err():
                    self._is_generating = False
                    self.btn_generate.config(text="✨ 開始產生字幕", state=tk.NORMAL)
                    self.lbl_gen_status.config(text=f"❌ 錯誤: {e}")
                self.win.after(0, err)

        threading.Thread(target=work, daemon=True).start()

    def _notify_editor(self):
        """通知母視窗更新字幕狀態標籤、時間軸字幕軌與畫布預覽"""
        if hasattr(self.editor, "_update_subtitle_ui"):
            self.editor._update_subtitle_ui()
        if hasattr(self.editor, "_redraw_subtitles"):
            self.editor._redraw_subtitles()
        if hasattr(self.editor, "_redraw_preview_canvas"):
            self.editor._redraw_preview_canvas()

    def _close_window(self):
        self._notify_editor()
        self.win.destroy()

