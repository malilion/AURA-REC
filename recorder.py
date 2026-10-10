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
    hold_awake,
)


def recording_label(text):
    """檔名用的程式名稱。拿掉路徑和不能用的符號。"""
    cleaned = []
    for ch in str(text or ""):
        if ch in '\\/:*?"<>|' or ord(ch) < 32:
            cleaned.append(" ")
        else:
            cleaned.append(ch)
    return " ".join("".join(cleaned).split()).strip(" .")[:24]


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
        self._rotate_lock = threading.Lock()
        self._rotating = False
        self._stop_rotate = None
        self._segment_seconds = None
        self._segment_index = 0
        self._segment_started_at = None
        self._segment_paused_at = None
        self._pending_result = None
        self._capture_kwargs = None
        self._follow = None
        self._follow_stop = None
        self._cmd_fd = None
        self._cmd_lock = threading.Lock()

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
        sys_audio_idx=None,
        multitrack=True,
        fps=30,
        resolution="native",
        use_hardware_accel=True,
        capture_cursor=True,
        region=None,
        quality="standard",
        output_file=None,
        profile=None,
        segment_sec=None,
        pip_config=None,
    ):
        """組出給文書電腦用的 FFmpeg 指令。不啟動錄影。支援麥克風與系統音效獨立多音軌 (Multi-track) 錄製。"""
        profile = profile or machine_profile()
        cmd = [
            self.ffmpeg_bin,
            "-hide_banner", "-loglevel", "error", "-y",
            "-threads", str(encode_threads(profile)),
        ]
        if profile == "light":
            cmd.extend(["-filter_threads", "1"])

        has_mic = audio_idx is not None and str(audio_idx).strip() != "" and str(audio_idx).lower() != "none"
        has_sys = sys_audio_idx is not None and str(sys_audio_idx).strip() != "" and str(sys_audio_idx).lower() != "none"
        if has_mic and has_sys and str(audio_idx).strip() == str(sys_audio_idx).strip():
            has_sys = False
        has_dual = has_mic and has_sys
        has_any_audio = has_mic or has_sys
        pip_enabled = bool(pip_config and pip_config.get("enabled"))

        if pip_enabled:
            pip_camera_idx = str(pip_config.get("camera_idx", "0")).strip()
            pip_size = int(pip_config.get("size", 260))
            pip_shape = str(pip_config.get("shape", "circle")).lower()
            pip_pos = str(pip_config.get("position", "bottom-right")).lower()
            border_rgb = pip_config.get("border_color", (0, 240, 255))
            margin = int(pip_config.get("margin", 32))

            # 1. 主畫面、相機與音訊輸入
            if IS_MAC:
                if video_idx is None:
                    video_idx = "0"
                input_spec = f"{video_idx}:{audio_idx}" if has_mic else f"{video_idx}:none"
                cmd.extend([
                    "-f", "avfoundation",
                    "-capture_cursor", "1" if capture_cursor else "0",
                    "-framerate", str(fps),
                    "-i", input_spec,
                    "-f", "avfoundation",
                    "-framerate", str(fps),
                    "-i", f"{pip_camera_idx}:none",
                ])
                if has_sys:
                    cmd.extend([
                        "-f", "avfoundation",
                        "-framerate", str(fps),
                        "-i", f":{sys_audio_idx}",
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
                cmd.extend([
                    "-f", "dshow",
                    "-framerate", str(fps),
                    "-i", f"video={pip_camera_idx}",
                ])
                if has_mic:
                    cmd.extend(["-f", "dshow", "-i", f"audio={audio_idx}"])
                if has_sys:
                    cmd.extend(["-f", "dshow", "-i", f"audio={sys_audio_idx}"])
            else:
                cam_dev = pip_camera_idx if pip_camera_idx.startswith("/dev") else f"/dev/video{pip_camera_idx}"
                cmd.extend([
                    "-f", "x11grab",
                    "-framerate", str(fps),
                    "-draw_mouse", "1" if capture_cursor else "0",
                    "-i", ":0.0",
                    "-f", "v4l2",
                    "-framerate", str(fps),
                    "-i", str(cam_dev),
                ])
                if has_mic:
                    cmd.extend(["-f", "pulse", "-i", "default"])
                if has_sys:
                    cmd.extend(["-f", "pulse", "-i", str(sys_audio_idx)])

            # 2. 濾鏡圖 (filter_complex)
            filter_parts = []
            base_label = "0:v"
            if region:
                x, y, w, h = [int(v) for v in region]
                x -= x % 2
                y -= y % 2
                w = max(2, w - w % 2)
                h = max(2, h - h % 2)
                filter_parts.append(f"[{base_label}]crop@aura={w}:{h}:{x}:{y}[cropped]")
                base_label = "cropped"
            scale = scale_filter(resolution)
            if scale:
                filter_parts.append(f"[{base_label}]{scale}[scaled]")
                base_label = "scaled"

            if pip_shape == "circle":
                r = pip_size // 2
                b = 4 if border_rgb else 0
                r_in = r - b
                if border_rgb:
                    br, bg, bb = border_rgb
                    cam_branch = (
                        f"[1:v]scale={pip_size}:{pip_size}:force_original_aspect_ratio=increase,"
                        f"crop={pip_size}:{pip_size},"
                        f"format=rgba,"
                        f"geq=r='if(gt((X-{r})*(X-{r})+(Y-{r})*(Y-{r}), {r_in*r_in}), {br}, r(X,Y))':"
                        f"g='if(gt((X-{r})*(X-{r})+(Y-{r})*(Y-{r}), {r_in*r_in}), {bg}, g(X,Y))':"
                        f"b='if(gt((X-{r})*(X-{r})+(Y-{r})*(Y-{r}), {r_in*r_in}), {bb}, b(X,Y))':"
                        f"a='if(lte((X-{r})*(X-{r})+(Y-{r})*(Y-{r}), {r*r}), 255, 0)'[cam]"
                    )
                else:
                    cam_branch = (
                        f"[1:v]scale={pip_size}:{pip_size}:force_original_aspect_ratio=increase,"
                        f"crop={pip_size}:{pip_size},"
                        f"format=rgba,"
                        f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
                        f"a='if(lte((X-{r})*(X-{r})+(Y-{r})*(Y-{r}), {r*r}), 255, 0)'[cam]"
                    )
                filter_parts.append(cam_branch)
            else:
                w_cam = int(pip_size * 16 / 9)
                w_cam -= w_cam % 2
                h_cam = pip_size
                h_cam -= h_cam % 2
                drawbox_str = ""
                if border_rgb:
                    hex_color = f"0x{border_rgb[0]:02X}{border_rgb[1]:02X}{border_rgb[2]:02X}"
                    drawbox_str = f",drawbox=x=0:y=0:w=iw:h=ih:color={hex_color}@1:t=4"
                filter_parts.append(
                    f"[1:v]scale={w_cam}:{h_cam}:force_original_aspect_ratio=increase,"
                    f"crop={w_cam}:{h_cam}{drawbox_str}[cam]"
                )

            pos_map = {
                "bottom-right": f"W-w-{margin}:H-h-{margin}",
                "bottom-left": f"{margin}:H-h-{margin}",
                "top-right": f"W-w-{margin}:{margin}",
                "top-left": f"{margin}:{margin}",
            }
            overlay_coords = pos_map.get(pip_pos, f"W-w-{margin}:H-h-{margin}")
            filter_parts.append(f"[{base_label}][cam]overlay={overlay_coords}:format=auto[outv]")

            if has_dual:
                mic_label = "0:a" if IS_MAC else "2:a"
                sys_label = "2:a" if IS_MAC else "3:a"
                if multitrack:
                    cmd.extend(["-filter_complex", ";".join(filter_parts)])
                    cmd.extend(["-map", "[outv]", "-map", mic_label, "-map", sys_label])
                    cmd.extend([
                        "-metadata:s:a:0", "handler_name=Microphone",
                        "-metadata:s:a:0", "title=Microphone (麥克風)",
                        "-metadata:s:a:1", "handler_name=System Audio",
                        "-metadata:s:a:1", "title=System Audio (系統音效)",
                    ])
                else:
                    filter_parts.append(f"[{mic_label}][{sys_label}]amix=inputs=2:duration=longest[outa]")
                    cmd.extend(["-filter_complex", ";".join(filter_parts)])
                    cmd.extend(["-map", "[outv]", "-map", "[outa]"])
            elif has_mic:
                mic_label = "0:a" if IS_MAC else "2:a"
                cmd.extend(["-filter_complex", ";".join(filter_parts)])
                cmd.extend(["-map", "[outv]", "-map", mic_label])
                cmd.extend([
                    "-metadata:s:a:0", "handler_name=Microphone",
                    "-metadata:s:a:0", "title=Microphone (麥克風)",
                ])
            elif has_sys:
                sys_label = "2:a" if IS_MAC else "2:a"
                cmd.extend(["-filter_complex", ";".join(filter_parts)])
                cmd.extend(["-map", "[outv]", "-map", sys_label])
                cmd.extend([
                    "-metadata:s:a:0", "handler_name=System Audio",
                    "-metadata:s:a:0", "title=System Audio (系統音效)",
                ])
            else:
                cmd.extend(["-filter_complex", ";".join(filter_parts)])
                cmd.extend(["-map", "[outv]"])

        else:
            if IS_MAC:
                if video_idx is None:
                    video_idx = "0"
                input_spec = f"{video_idx}:{audio_idx}" if has_mic else f"{video_idx}:none"
                cmd.extend([
                    "-f", "avfoundation",
                    "-capture_cursor", "1" if capture_cursor else "0",
                    "-framerate", str(fps),
                    "-i", input_spec,
                ])
                if has_sys:
                    cmd.extend([
                        "-f", "avfoundation",
                        "-framerate", str(fps),
                        "-i", f":{sys_audio_idx}",
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
                if has_mic:
                    cmd.extend(["-f", "dshow", "-i", f"audio={audio_idx}"])
                if has_sys:
                    cmd.extend(["-f", "dshow", "-i", f"audio={sys_audio_idx}"])
            else:
                cmd.extend([
                    "-f", "x11grab",
                    "-framerate", str(fps),
                    "-draw_mouse", "1" if capture_cursor else "0",
                    "-i", ":0.0",
                ])
                if has_mic:
                    cmd.extend(["-f", "pulse", "-i", "default"])
                if has_sys:
                    cmd.extend(["-f", "pulse", "-i", str(sys_audio_idx)])

            filters = []
            if region:
                x, y, w, h = [int(v) for v in region]
                x -= x % 2
                y -= y % 2
                w = max(2, w - w % 2)
                h = max(2, h - h % 2)
                filters.append(f"crop@aura={w}:{h}:{x}:{y}")
            scale = scale_filter(resolution)
            if scale:
                filters.append(scale)

            if has_dual:
                mic_label = "0:a" if IS_MAC else "1:a"
                sys_label = "1:a" if IS_MAC else "2:a"
                if multitrack:
                    if filters:
                        cmd.extend(["-vf", ",".join(filters)])
                    cmd.extend(["-map", "0:v", "-map", mic_label, "-map", sys_label])
                    cmd.extend([
                        "-metadata:s:a:0", "handler_name=Microphone",
                        "-metadata:s:a:0", "title=Microphone (麥克風)",
                        "-metadata:s:a:1", "handler_name=System Audio",
                        "-metadata:s:a:1", "title=System Audio (系統音效)",
                    ])
                else:
                    if filters:
                        cmd.extend([
                            "-filter_complex",
                            f"[0:v]{','.join(filters)}[outv];[{mic_label}][{sys_label}]amix=inputs=2:duration=longest[outa]",
                            "-map", "[outv]", "-map", "[outa]"
                        ])
                    else:
                        cmd.extend([
                            "-filter_complex",
                            f"[{mic_label}][{sys_label}]amix=inputs=2:duration=longest[outa]",
                            "-map", "0:v", "-map", "[outa]"
                        ])
            elif has_mic:
                if filters:
                    cmd.extend(["-vf", ",".join(filters)])
                mic_label = "0:a" if IS_MAC else "1:a"
                cmd.extend(["-map", "0:v", "-map", mic_label])
                cmd.extend([
                    "-metadata:s:a:0", "handler_name=Microphone",
                    "-metadata:s:a:0", "title=Microphone (麥克風)",
                ])
            elif has_sys:
                if filters:
                    cmd.extend(["-vf", ",".join(filters)])
                sys_label = "1:a" if IS_MAC else "1:a"
                cmd.extend(["-map", "0:v", "-map", sys_label])
                cmd.extend([
                    "-metadata:s:a:0", "handler_name=System Audio",
                    "-metadata:s:a:0", "title=System Audio (系統音效)",
                ])
            else:
                if filters:
                    cmd.extend(["-vf", ",".join(filters)])

        quality_scale = {"economy": 0.7, "high": 1.35}.get(quality, 1.0)
        bitrate = max(280, int(capture_bitrate_k(resolution, profile) * quality_scale))
        cmd.extend(video_encode_args(
            self.ffmpeg_bin, use_hardware_accel, bitrate, profile, quality=quality
        ))
        if has_any_audio:
            bitrate_a = "192k" if quality == "high" else ("128k" if quality == "standard" else "96k")
            cmd.extend(["-c:a", "aac", "-b:a", bitrate_a])
        del segment_sec
        cmd.append(str(output_file))
        return cmd

    def start_recording(
        self,
        video_idx=None,
        audio_idx=None,
        sys_audio_idx=None,
        multitrack=True,
        fps=30,
        resolution="native",
        use_hardware_accel=True,
        capture_cursor=True,
        region=None,
        quality="standard",
        container="mp4",
        segment_sec=None,
        label=None,
        follow=None,
        prefix=None,
        pip_config=None,
    ):
        """
        跨平台啟動錄影程序 (支援麥克風與系統音效獨立多音軌)
        """
        if self.is_recording:
            return False, "錄影已在進行中"
        if not self.ffmpeg_ok():
            return False, explain_ffmpeg_failure("", code="missing")
        self.paused = False
        self.pause_started = None
        self.paused_total = 0.0
        self._rotating = False
        self._pending_result = None
        self._segment_index = 0
        self._segment_paused_at = None
        try:
            self._segment_seconds = int(segment_sec) if segment_sec else None
        except (TypeError, ValueError):
            self._segment_seconds = None
        if self._segment_seconds is not None and self._segment_seconds < 1:
            self._segment_seconds = None
        if self._stop_rotate is not None:
            self._stop_rotate.set()
        self._stop_rotate = threading.Event() if self._segment_seconds else None
        if self._follow_stop is not None:
            self._follow_stop.set()
        self._follow_stop = threading.Event()
        # Windows 的 ffmpeg 不從 stdin 讀指令，位置跟不了。Mac 與 Linux 用終端機指令。
        self._follow = follow if callable(follow) and not IS_WINDOWS else None

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        suffix = ".mov" if str(container).lower() == "mov" else ".mp4"
        piece = "_%03d" if self._segment_seconds else ""
        stamp = recording_label(label)
        base_prefix = str(prefix).strip() if prefix else "螢幕錄影"
        if not base_prefix.endswith("_") and not base_prefix.endswith("-"):
            base_prefix += "_"
        file_prefix = f"{base_prefix}{stamp}_" if stamp else base_prefix
        self.current_output_file = self.output_dir / f"{file_prefix}{timestamp}{piece}{suffix}"
        self._capture_kwargs = {
            "video_idx": video_idx,
            "audio_idx": audio_idx,
            "sys_audio_idx": sys_audio_idx,
            "multitrack": multitrack,
            "fps": fps,
            "resolution": resolution,
            "use_hardware_accel": use_hardware_accel,
            "capture_cursor": capture_cursor,
            "region": region,
            "quality": quality,
            "pip_config": pip_config,
        }
        actual = self._segment_file(0) if self._segment_seconds else self.current_output_file
        self._stderr_lines = []
        ok, msg = self._spawn(actual)
        if not ok:
            self.is_recording = False
            self.process = None
            self._segment_seconds = None
            return False, msg
        self.is_recording = True
        self.start_time = time.time()
        self._segment_started_at = self.start_time
        if self._follow is not None and self._cmd_fd is not None:
            threading.Thread(
                target=self._follow_loop,
                args=(self._follow_stop,),
                daemon=True,
            ).start()
        if self._stop_rotate is not None:
            threading.Thread(
                target=self._watch_segments,
                args=(self._stop_rotate,),
                daemon=True,
            ).start()
        return True, str(self.current_output_file)

    def _segment_file(self, index):
        path = self.current_output_file
        return path.with_name(path.name.replace("%03d", f"{int(index):03d}"))

    def _spawn(self, output_file):
        """開一支新的 ffmpeg，寫進這一個檔。"""
        cmd = self.build_capture_command(
            output_file=output_file,
            segment_sec=None,
            **(self._capture_kwargs or {}),
        )
        use_pty = self._follow is not None and not IS_WINDOWS
        slave = None
        popen_kwargs = dict(
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if use_pty:
            import pty
            master, slave = pty.openpty()
            popen_kwargs["stdin"] = slave
            popen_kwargs["close_fds"] = True
        if IS_WINDOWS:
            popen_kwargs["creationflags"] = getattr(
                subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0x00004000
            )
        try:
            proc = subprocess.Popen(cmd, **popen_kwargs)
        except Exception as exc:
            if slave is not None:
                os.close(slave)
                os.close(master)
            self.process = None
            self._follow = None
            return False, explain_ffmpeg_failure(str(exc), code="missing")
        if slave is not None:
            os.close(slave)
            self._cmd_fd = master
        self.process = proc
        lower_process_priority(proc.pid)
        threading.Thread(target=self._drain_stderr, args=(proc,), daemon=True).start()
        if self._segment_seconds:
            hold_awake(proc.pid)
        return True, str(output_file)

    def _watch_segments(self, stop_event):
        """每段時間到了就封存這個檔，再接著錄下一個。"""
        while not stop_event.wait(0.4):
            try:
                self._rotate_if_due(stop_event)
            except Exception:
                continue

    def _rotate_if_due(self, stop_event):
        if stop_event.is_set() or self._rotating or self.paused or not self.is_recording:
            return
        limit = self._segment_seconds
        started = self._segment_started_at
        if not limit or started is None or time.time() - started < limit:
            return
        with self._rotate_lock:
            if stop_event.is_set() or self._rotating or self.paused or not self.is_recording:
                return
            proc = self.process
            if proc is None or proc.poll() is not None:
                return
            self._rotating = True
        try:
            self._close_ffmpeg(proc)
            with self._rotate_lock:
                if stop_event.is_set() or not self.is_recording:
                    self.process = None
                    return
                self._segment_index += 1
                self._segment_started_at = time.time()
                ok, err = self._spawn(self._segment_file(self._segment_index))
                if not ok:
                    self._pending_result = (False, err or "下一段錄影沒有開始")
                    self.process = None
        finally:
            self._rotating = False

    def _send_crop(self, x, y):
        """叫正在錄的 crop 換位置。寬高不動，編碼器才不會被打斷。"""
        fd = self._cmd_fd
        if fd is None:
            return False
        payload = f"ccrop@aura -1 x {int(x)}\nccrop@aura -1 y {int(y)}\n".encode()
        with self._cmd_lock:
            if self._cmd_fd != fd:
                return False
            try:
                os.write(fd, payload)
            except OSError:
                return False
        return True

    def _close_cmd_fd(self):
        with self._cmd_lock:
            fd = self._cmd_fd
            self._cmd_fd = None
        if fd is None:
            return
        try:
            os.close(fd)
        except OSError:
            pass

    def _follow_loop(self, stop_event):
        """視窗移動時，讓裁切框跟著走。"""
        while not stop_event.wait(0.25):
            if not self.is_recording or self.paused or self._rotating or self._follow is None:
                continue
            try:
                box = self._follow()
            except Exception:
                continue
            if not box or len(box) != 4:
                continue
            try:
                x, y = int(box[0]), int(box[1])
            except (TypeError, ValueError):
                continue
            x -= x % 2
            y -= y % 2
            current = (self._capture_kwargs or {}).get("region")
            if not current or len(current) != 4:
                continue
            cx, cy, cw, ch = current
            if abs(x - int(cx)) < 2 and abs(y - int(cy)) < 2:
                continue
            if self._send_crop(x, y):
                self._capture_kwargs["region"] = (x, y, cw, ch)

    def _close_ffmpeg(self, proc):
        """送 q 讓這支 ffmpeg 把 mp4 封好。還沒結束才改送中斷。"""
        if proc is None:
            return
        wrote = False
        with self._cmd_lock:
            fd = self._cmd_fd
            if fd is not None:
                try:
                    os.write(fd, b"q")
                    wrote = True
                except OSError:
                    wrote = False
        if not wrote:
            try:
                if proc.stdin:
                    proc.stdin.write("q\n")
                    proc.stdin.flush()
            except Exception:
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if IS_WINDOWS:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            else:
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=2)
                    except Exception:
                        pass
        self._close_cmd_fd()
        if self.process is proc:
            self.process = None

    def _drain_stderr(self, proc):
        """把 FFmpeg 的紀錄讀走。不讀的話管線塞滿，長時間錄影會停住。"""
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
        with self._rotate_lock:
            if self._rotating:
                return None
            if self._pending_result is not None:
                result = self._pending_result
                self._pending_result = None
                self.is_recording = False
                self.paused = False
                self.pause_started = None
                self.last_recorded_file = self.resolved_output()
                self.process = None
                return result
            proc = self.process
            if proc is None or not self.is_recording:
                return None
            code = proc.poll()
            if code is None or self._rotating or proc is not self.process:
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
        if self._stop_rotate is not None:
            self._stop_rotate.set()
        if self._follow_stop is not None:
            self._follow_stop.set()
        deadline = time.time() + 12
        while self._rotating and time.time() < deadline:
            time.sleep(0.05)
        with self._rotate_lock:
            pending = self._pending_result
            self._pending_result = None
            proc = self.process
            if not self.is_recording and proc is None and pending is None:
                return False, "目前未在錄影"
            self._rotating = True
            if proc is not None and self.paused:
                self._resume_process_if_paused()
        try:
            if proc is not None:
                self._close_ffmpeg(proc)
            self.last_recorded_file = self.resolved_output()
            if pending is not None and self.last_recorded_file is None:
                return pending
            target = self.last_recorded_file or self.current_output_file
            if target is not None:
                return True, str(target)
            if pending is not None:
                return pending
            return False, "目前未在錄影"
        except Exception as exc:
            return False, f"停止錄影時出錯: {exc}"
        finally:
            with self._rotate_lock:
                self.is_recording = False
                self.paused = False
                self.pause_started = None
                self._rotating = False
                if self.process is proc:
                    self.process = None

    def pause_recording(self):
        """暫停擷取。同一支檔案之後可以繼續，暫停的時間不計入長度。"""
        if self._rotating or (self._stop_rotate is not None and self._stop_rotate.is_set()):
            return False, "正在儲存這一段，請再按一次"
        with self._rotate_lock:
            if self._rotating or not self.is_recording or self.process is None:
                return False, "目前未在錄影"
            if self.paused:
                return True, ""
            if not self._set_process_suspended(True):
                return False, "這個系統沒辦法暫停錄影"
            now = time.time()
            self.paused = True
            self.pause_started = now
            self._segment_paused_at = now
            return True, ""

    def resume_recording(self):
        with self._rotate_lock:
            if not self.is_recording or not self.paused:
                return False, "目前沒有暫停"
            if not self._set_process_suspended(False):
                return False, "沒辦法繼續錄影"
            now = time.time()
            if self.pause_started is not None:
                self.paused_total += now - self.pause_started
            if self._segment_paused_at is not None and self._segment_started_at is not None:
                self._segment_started_at += now - self._segment_paused_at
            self._segment_paused_at = None
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


def still_path(output_dir, when=None, prefix=None):
    when = when or datetime.now()
    base = str(prefix).strip() if prefix else "截圖"
    if not base.endswith("_") and not base.endswith("-"):
        base += "_"
    return Path(output_dir) / when.strftime(f"{base}%Y-%m-%d_%H-%M-%S.png")


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


def save_still(ffmpeg_bin, output_dir, region=None, prefix=None):
    path = still_path(output_dir, prefix=prefix)
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
