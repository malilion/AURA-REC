#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LiteScreenRecorder - 錄影核心引擎
基於 FFmpeg + macOS AVFoundation + Apple Silicon VideoToolbox 硬體加速
"""

import os
import re
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path


class ScreenRecorder:
    def __init__(self, output_dir=None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            # 優先使用專案底下的 recordings 目錄，便於管理且不受沙盒/外層權限限制
            self.output_dir = Path(__file__).resolve().parent / "recordings"

        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # 若無權限則回退到當前工作目錄
            self.output_dir = Path("./recordings").resolve()
            self.output_dir.mkdir(parents=True, exist_ok=True)

        self.process = None
        self.is_recording = False
        self.start_time = None
        self.current_output_file = None
        self.last_recorded_file = None

        # 檢查 ffmpeg
        self.ffmpeg_bin = self._find_ffmpeg()

    def _find_ffmpeg(self):
        for candidate in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "ffmpeg"]:
            try:
                res = subprocess.run([candidate, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if res.returncode == 0:
                    return candidate
            except Exception:
                continue
        return "ffmpeg"

    def get_devices(self):
        """
        掃描 macOS 系統中的可用螢幕 (Video) 與音訊設備 (Audio)
        """
        video_devs = []
        audio_devs = []

        try:
            cmd = [self.ffmpeg_bin, "-f", "avfoundation", "-list_devices", "true", "-i", ""]
            p = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors="ignore")
            output = p.stderr

            mode = None
            for line in output.splitlines():
                if "AVFoundation video devices:" in line:
                    mode = "video"
                    continue
                elif "AVFoundation audio devices:" in line:
                    mode = "audio"
                    continue
                
                m = re.search(r"\[(\d+)\]\s+(.*)", line)
                if m:
                    idx = m.group(1).strip()
                    name = m.group(2).strip()
                    if mode == "video":
                        video_devs.append({"index": idx, "name": name})
                    elif mode == "audio":
                        audio_devs.append({"index": idx, "name": name})
        except Exception as e:
            print(f"[Error] Failed to detect devices: {e}")

        if not video_devs:
            video_devs = [{"index": "0", "name": "主螢幕 (Default Screen 0)"}]
            
        return video_devs, audio_devs

    def start_recording(self, video_idx="0", audio_idx=None, fps=30, resolution="native", use_hardware_accel=True):
        """
        啟動錄影程序
        :param video_idx: 螢幕設備編號 (通常主螢幕為 0)
        :param audio_idx: 音訊設備編號 (None 為不錄音)
        :param fps: 幀率 (15, 30, 60)
        :param resolution: "native", "1080p", "2K", "720p"
        :param use_hardware_accel: 是否啟用 Apple VideoToolbox 硬體編碼 (省電、極低 CPU)
        """
        if self.is_recording:
            return False, "錄影已在進行中"

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.current_output_file = self.output_dir / f"螢幕錄影_{timestamp}.mp4"

        # 構建輸入字串，例如 "0:0" 或 "0:none"
        if audio_idx is not None and str(audio_idx).strip() != "" and str(audio_idx).lower() != "none":
            input_spec = f"{video_idx}:{audio_idx}"
            has_audio = True
        else:
            input_spec = f"{video_idx}:none"
            has_audio = False

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-f", "avfoundation",
            "-capture_cursor", "1",
            "-framerate", str(fps),
            "-i", input_spec,
        ]

        # 解析度濾鏡
        filters = []
        if resolution == "1080p":
            filters.append("scale=1920:-2")
        elif resolution == "2K":
            filters.append("scale=2560:-2")
        elif resolution == "720p":
            filters.append("scale=1280:-2")

        if filters:
            cmd.extend(["-vf", ",".join(filters)])

        # 影像編碼
        if use_hardware_accel:
            # Apple Silicon VideoToolbox 硬體編碼，零負擔
            cmd.extend([
                "-c:v", "h264_videotoolbox",
                "-b:v", "8000k",
                "-pix_fmt", "yuv420p"
            ])
        else:
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "22",
                "-pix_fmt", "yuv420p"
            ])

        # 音訊編碼
        if has_audio:
            cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k"
            ])

        cmd.extend([
            "-movflags", "+faststart",
            str(self.current_output_file)
        ])

        try:
            # 啟動 FFmpeg 子進程，stdin 支援寫入 'q' 以優雅結束並寫入 MP4 索引頭部
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )
            self.is_recording = True
            self.start_time = time.time()
            return True, str(self.current_output_file)
        except Exception as e:
            self.is_recording = False
            self.process = None
            return False, f"啟動錄影失敗: {str(e)}"

    def stop_recording(self):
        """
        停止錄影並正確封裝 MP4
        """
        if not self.is_recording or self.process is None:
            return False, "目前未在錄影"

        try:
            # 發送 'q' 給 FFmpeg 進行優雅關閉
            try:
                self.process.stdin.write("q\n")
                self.process.stdin.flush()
            except Exception:
                pass

            # 等待最多 5 秒讓 FFmpeg 完成封裝 (寫入 moov atom)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # 若逾時則發送 SIGINT
                self.process.send_signal(signal.SIGINT)
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()

            self.is_recording = False
            self.last_recorded_file = self.current_output_file
            self.process = None
            return True, str(self.last_recorded_file)
        except Exception as e:
            self.is_recording = False
            self.process = None
            return False, f"停止錄影時出錯: {str(e)}"

    def get_duration(self):
        """
        取得目前錄製秒數
        """
        if not self.is_recording or self.start_time is None:
            return 0
        return int(time.time() - self.start_time)
