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
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from platform_utils import (
    IS_MAC,
    IS_WINDOWS,
    IS_LINUX,
    find_executable,
    resolve_recordings_dir,
    ffmpeg_is_available,
    explain_ffmpeg_failure,
    machine_profile,
    encode_threads,
    scale_filter,
    capture_bitrate_k,
    video_encode_args,
    lower_process_priority,
)


class ScreenRecorder:
    def __init__(self, output_dir=None):
        if output_dir:
            self.output_dir = Path(output_dir)
            self.output_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.output_dir = resolve_recordings_dir(__file__)

        self.process = None
        self.is_recording = False
        self.paused = False
        self.pause_started = None
        self.paused_total = 0.0
        self.start_time = None
        self.current_output_file = None
        self.last_recorded_file = None
        self._stderr_lines = []
        self._stderr_lock = threading.Lock()

        # 跨平台尋找 FFmpeg
        self.ffmpeg_bin = find_executable("ffmpeg")

    def ffmpeg_ok(self):
        return ffmpeg_is_available(self.ffmpeg_bin)

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
                p = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors="ignore", timeout=8)
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
                p = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors="ignore", timeout=8)
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

        except subprocess.TimeoutExpired:
            print("[Error] Device scan timed out")
        except Exception as e:
            print(f"[Error] Failed to detect devices: {e}")

        if not video_devs:
            default_idx = "0" if IS_MAC else "desktop"
            video_devs = [{"index": default_idx, "name": "預設主螢幕 (Default Screen)"}]

        return video_devs, audio_devs

    def build_capture_command(
        self,
        video_idx=None,
        audio_idx=None,
        fps=30,
        resolution="native",
        use_hardware_accel=True,
        capture_cursor=True,
        region=None,
        quality="standard",
        output_file=None,
        profile=None,
        segment_sec=None,
    ):
        """組出給文書電腦用的 FFmpeg 指令。不啟動錄影。"""
        profile = profile or machine_profile()
        cmd = [
            self.ffmpeg_bin,
            "-hide_banner", "-loglevel", "error", "-y",
            "-threads", str(encode_threads(profile)),
        ]
        if profile == "light":
            cmd.extend(["-filter_threads", "1"])

        has_audio = audio_idx is not None and str(audio_idx).strip() != "" and str(audio_idx).lower() != "none"

        if IS_MAC:
            if video_idx is None:
                video_idx = "0"
            input_spec = f"{video_idx}:{audio_idx}" if has_audio else f"{video_idx}:none"
            cmd.extend([
                "-f", "avfoundation",
                "-capture_cursor", "1" if capture_cursor else "0",
                "-framerate", str(fps),
                "-i", input_spec,
            ])
        elif IS_WINDOWS:
            if video_idx is None or video_idx == "desktop":
                cmd.extend([
                    "-f", "gdigrab",
                    "-framerate", str(fps),
                    "-draw_mouse", "1" if capture_cursor else "0",
                    "-i", "desktop",
                ])
            else:
                cmd.extend([
                    "-f", "dshow",
                    "-framerate", str(fps),
                    "-i", f"video={video_idx}",
                ])
            if has_audio:
                cmd.extend(["-f", "dshow", "-i", f"audio={audio_idx}"])
        else:
            cmd.extend([
                "-f", "x11grab",
                "-framerate", str(fps),
                "-draw_mouse", "1" if capture_cursor else "0",
                "-i", ":0.0",
            ])
            if has_audio:
                cmd.extend(["-f", "pulse", "-i", "default"])

        filters = []
        if region:
            x, y, w, h = [int(v) for v in region]
            x -= x % 2
            y -= y % 2
            w = max(2, w - w % 2)
            h = max(2, h - h % 2)
            filters.append(f"crop={w}:{h}:{x}:{y}")
        scale = scale_filter(resolution)
        if scale:
            filters.append(scale)
        if filters:
            cmd.extend(["-vf", ",".join(filters)])

        quality_scale = {"economy": 0.7, "high": 1.35}.get(quality, 1.0)
        bitrate = max(280, int(capture_bitrate_k(resolution, profile) * quality_scale))
        cmd.extend(video_encode_args(
            self.ffmpeg_bin, use_hardware_accel, bitrate, profile, quality=quality
        ))
        if has_audio:
            cmd.extend(["-c:a", "aac", "-b:a", "96k"])
        if segment_sec:
            suffix = Path(str(output_file)).suffix.lower().lstrip(".") or "mp4"
            if suffix not in {"mp4", "mov"}:
                suffix = "mp4"
            # 分段只在關鍵畫格切開。約每兩秒一個，才切得準。
            cmd.extend(["-g", str(max(1, int(fps)) * 2)])
            cmd.extend([
                "-f", "segment",
                "-segment_time", str(int(segment_sec)),
                "-segment_format", suffix,
                "-reset_timestamps", "1",
            ])
        cmd.append(str(output_file))
        return cmd

    def start_recording(
        self,
        video_idx=None,
        audio_idx=None,
        fps=30,
        resolution="native",
        use_hardware_accel=True,
        capture_cursor=True,
        region=None,
        quality="standard",
        container="mp4",
        segment_sec=None,
    ):
        """
        跨平台啟動錄影程序
        """
        if self.is_recording:
            return False, "錄影已在進行中"
        if not self.ffmpeg_ok():
            return False, explain_ffmpeg_failure("", code="missing")
        self.paused = False
        self.pause_started = None
        self.paused_total = 0.0

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        suffix = ".mov" if str(container).lower() == "mov" else ".mp4"
        piece = "_%03d" if segment_sec else ""
        self.current_output_file = self.output_dir / f"螢幕錄影_{timestamp}{piece}{suffix}"
        cmd = self.build_capture_command(
            video_idx=video_idx,
            audio_idx=audio_idx,
            fps=fps,
            resolution=resolution,
            use_hardware_accel=use_hardware_accel,
            capture_cursor=capture_cursor,
            region=region,
            quality=quality,
            output_file=self.current_output_file,
            segment_sec=segment_sec,
        )

        try:
            self._stderr_lines = []
            popen_kwargs = dict(
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            if IS_WINDOWS:
                popen_kwargs["creationflags"] = getattr(
                    subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0x00004000
                )
            self.process = subprocess.Popen(cmd, **popen_kwargs)
            lower_process_priority(self.process.pid)
            self.is_recording = True
            self.start_time = time.time()
            threading.Thread(target=self._drain_stderr, daemon=True).start()
            return True, str(self.current_output_file)
        except Exception as e:
            self.is_recording = False
            self.process = None
            return False, explain_ffmpeg_failure(str(e), code="missing")

    def _drain_stderr(self):
        """把 FFmpeg 的紀錄讀走。不讀的話管線塞滿，長時間錄影會停住。"""
        proc = self.process
        if proc is None or proc.stderr is None:
            return
        try:
            for line in proc.stderr:
                with self._stderr_lock:
                    self._stderr_lines.append(line.rstrip())
                    if len(self._stderr_lines) > 80:
                        del self._stderr_lines[:40]
        except Exception:
            pass

    def stderr_tail(self, limit=8):
        with self._stderr_lock:
            lines = [ln for ln in self._stderr_lines if ln.strip()]
        return "\n".join(lines[-limit:])

    def consume_exit(self):
        """FFmpeg 已經自己結束時，收回狀態。還在錄就回傳 None。"""
        proc = self.process
        if proc is None or not self.is_recording:
            return None
        code = proc.poll()
        if code is None:
            return None
        tail = self.stderr_tail()
        self.is_recording = False
        self.paused = False
        self.pause_started = None
        self.last_recorded_file = self.resolved_output()
        self.process = None
        usable = False
        try:
            usable = (
                self.last_recorded_file is not None
                and self.last_recorded_file.is_file()
                and self.last_recorded_file.stat().st_size > 1024
            )
        except Exception:
            usable = False
        if code == 0 and usable:
            return True, str(self.last_recorded_file)
        return False, explain_ffmpeg_failure(tail, code)

    def stop_recording(self):
        """
        停止錄影並正確封裝 MP4 (跨平台安全終止)
        """
        if not self.is_recording or self.process is None:
            return False, "目前未在錄影"

        self._resume_process_if_paused()

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
            self.paused = False
            self.pause_started = None
            self.last_recorded_file = self.resolved_output()
            self.process = None
            target = self.last_recorded_file or self.current_output_file
            return True, str(target)
        except Exception as e:
            self.is_recording = False
            self.paused = False
            self.process = None
            return False, f"停止錄影時出錯: {str(e)}"

    def pause_recording(self):
        """暫停擷取。同一支檔案之後可以繼續，暫停的時間不計入長度。"""
        if not self.is_recording or self.process is None:
            return False, "目前未在錄影"
        if self.paused:
            return True, ""
        if not self._set_process_suspended(True):
            return False, "這個系統沒辦法暫停錄影"
        self.paused = True
        self.pause_started = time.time()
        return True, ""

    def resume_recording(self):
        if not self.is_recording or not self.paused:
            return False, "目前沒有暫停"
        if not self._set_process_suspended(False):
            return False, "沒辦法繼續錄影"
        if self.pause_started is not None:
            self.paused_total += time.time() - self.pause_started
        self.pause_started = None
        self.paused = False
        return True, ""

    def _resume_process_if_paused(self):
        if not self.paused:
            return
        self._set_process_suspended(False)
        self.paused = False
        self.pause_started = None

    def _set_process_suspended(self, suspended):
        proc = self.process
        if proc is None or proc.poll() is not None:
            return False
        try:
            if IS_WINDOWS:
                import ctypes
                access = 0x0800  # PROCESS_SUSPEND_RESUME
                kernel32 = ctypes.windll.kernel32
                ntdll = ctypes.windll.ntdll
                handle = kernel32.OpenProcess(access, False, proc.pid)
                if not handle:
                    return False
                try:
                    fn = ntdll.NtSuspendProcess if suspended else ntdll.NtResumeProcess
                    return int(fn(handle)) == 0
                finally:
                    kernel32.CloseHandle(handle)
            proc.send_signal(signal.SIGSTOP if suspended else signal.SIGCONT)
            return True
        except Exception:
            return False

    def recorded_parts(self):
        """這次錄影寫出的檔案。分段時由舊到新。"""
        path = self.current_output_file
        if path is None:
            return []
        name = path.name
        if "%03d" not in name:
            return [path] if path.is_file() else []
        pattern = name.replace("%03d", "*")
        try:
            parts = [item for item in path.parent.glob(pattern) if item.is_file()]
        except OSError:
            return []
        return sorted(parts, key=lambda item: item.name)

    def resolved_output(self):
        parts = self.recorded_parts()
        if parts:
            return parts[-1]
        path = self.current_output_file
        if path is not None and "%03d" not in path.name:
            return path
        return None

    def output_size_bytes(self):
        total = 0
        for part in self.recorded_parts():
            try:
                total += part.stat().st_size
            except OSError:
                pass
        return total

    def get_duration(self):
        if not self.is_recording or self.start_time is None:
            return 0
        now = self.pause_started if self.paused and self.pause_started is not None else time.time()
        return int(max(0, now - self.start_time - self.paused_total))


LOW_DISK_BYTES = 500 * 1024 * 1024


def format_bytes(size):
    size = max(0, int(size))
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size // 1024} KB"
    return f"{size} B"


def free_disk_bytes(path):
    folder = Path(path)
    if not folder.exists():
        folder = folder.parent
    try:
        return shutil.disk_usage(folder).free
    except OSError:
        return None


def still_path(output_dir, when=None):
    when = when or datetime.now()
    return Path(output_dir) / when.strftime("截圖_%Y-%m-%d_%H-%M-%S.png")


def mac_still_args(region, output_file, scale=1.0):
    """screencapture 的 -R 用點，錄影範圍用的是像素。"""
    cmd = ["screencapture", "-x"]
    if region:
        scale = scale or 1.0
        x, y, w, h = [float(v) / scale for v in region]
        cmd.extend(["-R", f"{x:.0f},{y:.0f},{max(1, round(w)):.0f},{max(1, round(h)):.0f}"])
    cmd.append(str(output_file))
    return cmd


def build_still_command(ffmpeg_bin, output_file, region=None):
    """抓一整張靜態圖。不是錄影。"""
    cmd = [ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y"]
    if IS_WINDOWS:
        cmd.extend(["-f", "gdigrab", "-framerate", "1", "-i", "desktop"])
    else:
        cmd.extend(["-f", "x11grab", "-framerate", "1", "-i", ":0.0"])
    cmd.extend(["-frames:v", "1"])
    if region:
        x, y, w, h = [int(v) for v in region]
        x -= x % 2
        y -= y % 2
        w = max(2, w - w % 2)
        h = max(2, h - h % 2)
        cmd.extend(["-vf", f"crop={w}:{h}:{x}:{y}"])
    cmd.append(str(output_file))
    return cmd


def save_still(ffmpeg_bin, output_dir, region=None):
    path = still_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if IS_MAC:
        from region_picker import display_scale
        cmd = mac_still_args(region, path, display_scale())
    else:
        cmd = build_still_command(ffmpeg_bin, path, region)
    try:
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=12,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        if path.is_file() and path.stat().st_size > 0:
            return path
    except OSError:
        return None
    return None
