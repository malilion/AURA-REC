#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LiteScreenRecorder - 錄影核心引擎 (macOS & Windows 跨平台支援)
- macOS: AVFoundation + VideoToolbox 硬體加速
- Windows: GDI Grab / DirectShow + NVENC / QSV / x264 硬體加速
- 支援麥克風與系統音效 (立體聲混音 / 虛擬聲卡)
"""

import os
import re
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

from platform_utils import (
    IS_MAC,
    IS_WINDOWS,
    IS_LINUX,
    find_executable,
    detect_best_video_encoder
)


class ScreenRecorder:
    def __init__(self, output_dir=None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            # 優先使用專案底下的 recordings 目錄
            self.output_dir = Path(__file__).resolve().parent / "recordings"

        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.output_dir = Path("./recordings").resolve()
            self.output_dir.mkdir(parents=True, exist_ok=True)

        self.process = None
        self.is_recording = False
        self.start_time = None
        self.current_output_file = None
        self.last_recorded_file = None

        # 跨平台尋找 FFmpeg
        self.ffmpeg_bin = find_executable("ffmpeg")

    def get_devices(self):
        """
        跨平台掃描可用螢幕 (Video) 與音訊設備 (Audio)
        """
        video_devs = []
        audio_devs = []

        try:
            if IS_MAC:
                # macOS AVFoundation
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

            elif IS_WINDOWS:
                # Windows DirectShow 設備掃描
                video_devs.append({"index": "desktop", "name": "全螢幕桌面 (Primary Desktop)"})

                cmd = [self.ffmpeg_bin, "-list_devices", "true", "-f", "dshow", "-i", "dummy"]
                p = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors="ignore")
                output = p.stderr

                mode = None
                for line in output.splitlines():
                    if "DirectShow video devices" in line:
                        mode = "video"
                        continue
                    elif "DirectShow audio devices" in line:
                        mode = "audio"
                        continue

                    # 匹配名稱引號內的字串，例如 "Microphone (Realtek Audio)"
                    m = re.search(r'"([^"]+)"', line)
                    if m:
                        name = m.group(1).strip()
                        if mode == "video" and name not in [v["name"] for v in video_devs]:
                            video_devs.append({"index": name, "name": name})
                        elif mode == "audio" and name not in [a["name"] for a in audio_devs]:
                            audio_devs.append({"index": name, "name": name})

            else:
                # Linux 回退
                video_devs.append({"index": ":0.0", "name": "X11 Display :0.0"})
                audio_devs.append({"index": "default", "name": "預設音訊 (PulseAudio/ALSA)"})

        except Exception as e:
            print(f"[Error] Failed to detect devices: {e}")

        if not video_devs:
            default_idx = "0" if IS_MAC else "desktop"
            video_devs = [{"index": default_idx, "name": "預設主螢幕 (Default Screen)"}]

        return video_devs, audio_devs

    def start_recording(self, video_idx=None, audio_idx=None, fps=30, resolution="native", use_hardware_accel=True):
        """
        跨平台啟動錄影程序
        """
        if self.is_recording:
            return False, "錄影已在進行中"

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.current_output_file = self.output_dir / f"螢幕錄影_{timestamp}.mp4"

        cmd = [self.ffmpeg_bin, "-y"]

        has_audio = False
        if audio_idx is not None and str(audio_idx).strip() != "" and str(audio_idx).lower() != "none":
            has_audio = True

        # 跨平台設定輸入源
        if IS_MAC:
            if video_idx is None:
                video_idx = "0"
            input_spec = f"{video_idx}:{audio_idx}" if has_audio else f"{video_idx}:none"
            cmd.extend([
                "-f", "avfoundation",
                "-capture_cursor", "1",
                "-framerate", str(fps),
                "-i", input_spec,
            ])
        elif IS_WINDOWS:
            # Windows 影像輸入 (預設 gdigrab 擷取整面桌面)
            if video_idx is None or video_idx == "desktop":
                cmd.extend([
                    "-f", "gdigrab",
                    "-framerate", str(fps),
                    "-draw_mouse", "1",
                    "-i", "desktop"
                ])
            else:
                cmd.extend([
                    "-f", "dshow",
                    "-framerate", str(fps),
                    "-i", f"video={video_idx}"
                ])

            # Windows 音訊輸入 (DirectShow)
            if has_audio:
                cmd.extend([
                    "-f", "dshow",
                    "-i", f"audio={audio_idx}"
                ])
        else:
            # Linux
            cmd.extend([
                "-f", "x11grab",
                "-framerate", str(fps),
                "-draw_mouse", "1",
                "-i", ":0.0"
            ])
            if has_audio:
                cmd.extend(["-f", "pulse", "-i", "default"])

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

        # 影像編碼器 (偵測硬體加速)
        if use_hardware_accel:
            enc = detect_best_video_encoder(self.ffmpeg_bin)
            if enc == "h264_videotoolbox":
                cmd.extend(["-c:v", "h264_videotoolbox", "-b:v", "8000k", "-pix_fmt", "yuv420p"])
            elif enc == "h264_nvenc":
                cmd.extend(["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "22", "-pix_fmt", "yuv420p"])
            elif enc == "h264_qsv":
                cmd.extend(["-c:v", "h264_qsv", "-global_quality", "22", "-pix_fmt", "nv12"])
            elif enc == "h264_amf":
                cmd.extend(["-c:v", "h264_amf", "-quality", "speed", "-pix_fmt", "yuv420p"])
            else:
                cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"])
        else:
            cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"])

        # 音訊編碼
        if has_audio:
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])

        cmd.extend([
            "-movflags", "+faststart",
            str(self.current_output_file)
        ])

        try:
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
        停止錄影並正確封裝 MP4 (跨平台安全終止)
        """
        if not self.is_recording or self.process is None:
            return False, "目前未在錄影"

        try:
            # 發送 'q' 進行優雅關閉
            try:
                self.process.stdin.write("q\n")
                self.process.stdin.flush()
            except Exception:
                pass

            # 等待完成
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if IS_WINDOWS:
                    try:
                        self.process.terminate()
                        self.process.wait(timeout=2)
                    except Exception:
                        subprocess.run(
                            ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                else:
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
        if not self.is_recording or self.start_time is None:
            return 0
        return int(time.time() - self.start_time)
