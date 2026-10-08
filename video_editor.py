#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VideoEditor - 輕量影片剪輯核心 (macOS & Windows 跨平台支援)
支援時長獲取、畫面影格提取 (PPM in-memory)、無損極速裁剪、精確重編碼、GIF 導出、純音訊提取與靜音輸出
"""

import json
import os
import subprocess
from pathlib import Path

from platform_utils import (
    IS_MAC,
    IS_WINDOWS,
    find_executable,
    detect_best_video_encoder
)


class VideoEditor:
    def __init__(self, ffmpeg_bin=None, ffprobe_bin=None, ffplay_bin=None):
        self.ffmpeg_bin = ffmpeg_bin or find_executable("ffmpeg")
        self.ffprobe_bin = ffprobe_bin or find_executable("ffprobe")
        self.ffplay_bin = ffplay_bin or find_executable("ffplay")

    def get_video_info(self, file_path):
        """
        獲取影片詳細資訊：時長、寬高、FPS、檔案大小
        """
        file_path = str(file_path)
        if not os.path.exists(file_path):
            return None

        cmd = [
            self.ffprobe_bin,
            "-v", "error",
            "-show_entries", "format=duration,size,bit_rate:stream=width,height,codec_name,codec_type,r_frame_rate",
            "-of", "json",
            file_path
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="ignore")
            if res.returncode != 0:
                return None
            data = json.loads(res.stdout)
            
            format_info = data.get("format", {})
            duration = float(format_info.get("duration", 0.0))
            size_bytes = int(format_info.get("size", os.path.getsize(file_path)))

            width = 0
            height = 0
            has_audio = False
            video_codec = "h264"

            for s in data.get("streams", []):
                if s.get("codec_type") == "video" and width == 0:
                    width = int(s.get("width", 0))
                    height = int(s.get("height", 0))
                    video_codec = s.get("codec_name", "")
                elif s.get("codec_type") == "audio":
                    has_audio = True

            return {
                "file_path": file_path,
                "file_name": Path(file_path).name,
                "duration": duration,
                "size_mb": round(size_bytes / (1024 * 1024), 2),
                "width": width,
                "height": height,
                "has_audio": has_audio,
                "video_codec": video_codec
            }
        except Exception as e:
            print(f"[VideoEditor] get_video_info error: {e}")
            return None

    def get_frame_ppm(self, file_path, timestamp_sec, width=480, height=270):
        """
        在指定時間點擷取一幀畫面，以 PPM 格式 byte 串流返回，直接供 Tkinter PhotoImage 使用
        """
        file_path = str(file_path)
        scale_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"

        cmd = [
            self.ffmpeg_bin,
            "-ss", f"{timestamp_sec:.3f}",
            "-i", file_path,
            "-vf", scale_filter,
            "-vframes", "1",
            "-f", "image2pipe",
            "-vcodec", "ppm",
            "-"
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if res.returncode == 0 and res.stdout:
                return res.stdout
        except Exception as e:
            print(f"[VideoEditor] get_frame_ppm error: {e}")
        return None

    def trim_lossless(self, input_file, output_file, start_sec, end_sec):
        """
        無損極速裁剪 (不重新編碼，耗時約 0.5 秒)
        """
        input_file = str(input_file)
        output_file = str(output_file)
        duration = end_sec - start_sec
        if duration <= 0:
            return False, "裁切長度必須大於 0 秒"

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-ss", f"{start_sec:.3f}",
            "-i", input_file,
            "-t", f"{duration:.3f}",
            "-c", "copy",
            "-avoid_negative_ts", "1",
            output_file
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and os.path.exists(output_file):
                return True, output_file
            return False, f"剪輯失敗: {res.stderr}"
        except Exception as e:
            return False, f"剪輯發生異常: {str(e)}"

    def trim_precise(self, input_file, output_file, start_sec, end_sec, mute_audio=False, use_hardware_accel=True):
        """
        精確幀裁剪 (重新編碼，精準至特定毫秒幀，支援靜音)
        """
        input_file = str(input_file)
        output_file = str(output_file)
        duration = end_sec - start_sec
        if duration <= 0:
            return False, "裁切長度必須大於 0 秒"

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-ss", f"{start_sec:.3f}",
            "-i", input_file,
            "-t", f"{duration:.3f}",
        ]

        if use_hardware_accel:
            enc = detect_best_video_encoder(self.ffmpeg_bin)
            if enc == "h264_videotoolbox":
                cmd.extend(["-c:v", "h264_videotoolbox", "-b:v", "8000k"])
            elif enc == "h264_nvenc":
                cmd.extend(["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "22"])
            elif enc == "h264_qsv":
                cmd.extend(["-c:v", "h264_qsv", "-global_quality", "22"])
            else:
                cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "20"])
        else:
            cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "20"])

        if mute_audio:
            cmd.append("-an")
        else:
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])

        cmd.extend(["-movflags", "+faststart", output_file])

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and os.path.exists(output_file):
                return True, output_file
            return False, f"精準剪輯失敗: {res.stderr}"
        except Exception as e:
            return False, f"精準剪輯發生異常: {str(e)}"

    def export_gif(self, input_file, output_file, start_sec, end_sec, fps=12, width=640):
        """
        高畫質 GIF 導出 (雙遍調色盤 palettegen + paletteuse，無雜訊噪點)
        """
        input_file = str(input_file)
        output_file = str(output_file)
        duration = end_sec - start_sec
        if duration <= 0:
            return False, "長度必須大於 0 秒"

        vf = f"fps={fps},scale={width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer"

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-ss", f"{start_sec:.3f}",
            "-i", input_file,
            "-t", f"{duration:.3f}",
            "-vf", vf,
            output_file
        ]

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and os.path.exists(output_file):
                return True, output_file
            return False, f"GIF 匯出失敗: {res.stderr}"
        except Exception as e:
            return False, f"GIF 匯出發生異常: {str(e)}"

    def extract_audio(self, input_file, output_file, start_sec=None, end_sec=None):
        """
        提取純音訊為 MP3 或 M4A
        """
        input_file = str(input_file)
        output_file = str(output_file)

        cmd = [self.ffmpeg_bin, "-y"]
        if start_sec is not None and end_sec is not None and (end_sec > start_sec):
            cmd.extend(["-ss", f"{start_sec:.3f}", "-i", input_file, "-t", f"{end_sec - start_sec:.3f}"])
        else:
            cmd.extend(["-i", input_file])

        cmd.extend(["-vn", "-c:a", "libmp3lame" if output_file.endswith(".mp3") else "aac", output_file])

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and os.path.exists(output_file):
                return True, output_file
            return False, f"音訊提取失敗: {res.stderr}"
        except Exception as e:
            return False, f"音訊提取異常: {str(e)}"

    def play_segment(self, file_path, start_sec, duration_sec):
        """
        使用 ffplay 預覽播放指定區段
        """
        file_path = str(file_path)
        cmd = [
            self.ffplay_bin,
            "-ss", f"{start_sec:.3f}",
            "-t", f"{duration_sec:.3f}",
            "-autoexit",
            "-window_title", "影片區段預覽 (按 Q 或 Esc 關閉)",
            file_path
        ]
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
