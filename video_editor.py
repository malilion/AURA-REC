#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VideoEditor - 頂級跨平台影片剪輯核心
支援：
- 時長、解析度、編碼與檔案大小資訊提取
- 記憶體串流影格即時渲染 (PPM to PhotoImage)
- 0.5秒無損極速裁剪 (Stream Copy)
- 精準幀裁切與重編碼 (硬體加速)
- 影片倍速調整 (0.5x, 1.0x, 1.5x, 2.0x)
- 比例裁切 (16:9 橫向, 9:16 直向短影音 Shorts/Reels/TikTok, 1:1 正方形)
- 色彩調整 (亮度、對比度、飽和度微調)
- 雙遍調色盤超高清 GIF 導出
- 純音訊分離提取 (MP3/M4A)
"""

import json
import os
import subprocess
from pathlib import Path

from platform_utils import (
    find_executable,
    machine_profile,
    video_encode_args,
    audio_bitrate,
    encode_threads,
)


def parse_aspect_choice(text):
    """把剪輯視窗的比例選項變成濾鏡用的比例與取景。"""
    text = text or ""
    if "完整" in text:
        return "9:16", "fit"
    if "9:16" in text or "直式" in text or "裁切" in text:
        if "左" in text:
            return "9:16", "left"
        if "右" in text:
            return "9:16", "right"
        if "中" in text or "裁" in text:
            return "9:16", "center"
        return "9:16", "fit"
    if "16:9" in text or "橫式" in text:
        return "16:9", "center"
    if "1:1" in text or "方形" in text:
        return "1:1", "center"
    return "original", "center"


def _even(value):
    number = int(value)
    return max(2, number - number % 2)


def vertical_canvas_size(profile=None):
    """直式畫布。文書電腦用 720×1280，其他用 1080×1920。"""
    profile = profile or machine_profile()
    if profile == "light":
        return 720, 1280
    return 1080, 1920


def vertical_fit_graph(canvas_w, canvas_h):
    """整段畫面放進直式畫布，上下用縮小後模糊的同一畫面補滿。"""
    width = _even(canvas_w)
    height = _even(canvas_h)
    # 先把整張畫面縮小再模糊，避免只剩中間一條顏色。
    small_w = _even(max(32, width // 6))
    return (
        f"split[fg][bg];"
        f"[bg]scale={small_w}:-2:flags=fast_bilinear,boxblur=12:1,"
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=fast_bilinear,"
        f"crop={width}:{height}[bg];"
        f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease:flags=fast_bilinear[fg];"
        f"[bg][fg]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2"
    )


def preview_video_filter(aspect_ratio, anchor="center", width=512, height=288):
    """預覽用的濾鏡。直式完整會先排成直式，再放進橫向預覽格。"""
    pad = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=fast_bilinear,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
    )
    if aspect_ratio == "9:16" and anchor == "fit":
        return vertical_fit_graph(height, width) + "," + pad
    crop = aspect_crop_filter(aspect_ratio, anchor)
    return f"{crop},{pad}" if crop else pad


def aspect_crop_filter(aspect_ratio, anchor="center"):
    """裁成目標比例。寬高與起點都取偶數。已經符合時回傳 None。"""
    if aspect_ratio == "9:16":
        if anchor == "fit":
            return None
        width = r"trunc(min(iw\,ih*9/16)/2)*2"
        height = r"trunc(ih/2)*2"
        if anchor == "left":
            x = "0"
        elif anchor == "right":
            x = f"trunc((iw-({width}))/2)*2"
        else:
            x = f"trunc((iw-({width}))/4)*2"
        return f"crop=w={width}:h={height}:x={x}:y=0"
    if aspect_ratio == "16:9":
        height = r"trunc(min(ih\,iw*9/16)/2)*2"
        return f"crop=w=trunc(iw/2)*2:h={height}:x=0:y=trunc((ih-({height}))/4)*2"
    if aspect_ratio == "1:1":
        side = r"trunc(min(iw\,ih)/2)*2"
        return (
            f"crop=w={side}:h={side}:x=trunc((iw-({side}))/4)*2:"
            f"y=trunc((ih-({side}))/4)*2"
        )
    return None


def gif_export_settings(duration, fps=12, width=640, profile=None):
    """文書電腦用較小的 GIF。超過 15 秒再把幀率壓到 6。"""
    profile = profile or machine_profile()
    if profile == "light":
        fps = min(int(fps), 8)
        width = min(int(width), 480)
        colors = 48
        flags = "fast_bilinear"
    elif profile == "balanced":
        fps = min(int(fps), 10)
        width = min(int(width), 560)
        colors = 80
        flags = "bilinear"
    else:
        fps = int(fps)
        width = int(width)
        colors = 128
        flags = "lanczos"
    if duration > 15:
        fps = min(fps, 6)
    return {
        "fps": max(1, fps),
        "width": max(160, width),
        "colors": colors,
        "flags": flags,
        "profile": profile,
    }


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

    def get_frame_ppm(self, file_path, timestamp_sec, width=360, height=202, crop_filter=None, video_filter=None):
        """
        在指定時間點擷取一幀畫面，以 PPM 格式 byte 串流返回，直接供 Tkinter PhotoImage 使用。
        預覽用小圖和最快的縮放，避免拖時間軸時把 CPU 佔滿。
        """
        file_path = str(file_path)
        scale = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=fast_bilinear,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
        )
        if video_filter:
            scale = video_filter
        elif crop_filter:
            scale = crop_filter + "," + scale

        cmd = [
            self.ffmpeg_bin,
            "-hide_banner", "-loglevel", "error",
            "-threads", "1",
            "-ss", f"{timestamp_sec:.3f}",
            "-i", file_path,
            "-an",
            "-vf", scale,
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

    def trim_advanced(
        self,
        input_file,
        output_file,
        start_sec,
        end_sec,
        speed=1.0,
        aspect_ratio="original",
        anchor="center",
        brightness=0.0,
        contrast=1.0,
        saturation=1.0,
        mute_audio=False,
        use_hardware_accel=True,
        volume=1.0,
        target_resolution="original",
    ):
        """
        高級精準幀剪輯 (支援倍速、比例裁切、色彩增強、音量調整、尺寸縮放、硬體加速)
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

        profile = machine_profile()
        # 速度與色彩接在比例處理後面。直式完整用畫布，不裁掉左右。
        vf_list = []
        if speed != 1.0:
            pts_factor = 1.0 / speed
            vf_list.append(f"setpts={pts_factor:.4f}*PTS")
        if brightness != 0.0 or contrast != 1.0 or saturation != 1.0:
            vf_list.append(f"eq=brightness={brightness:.2f}:contrast={contrast:.2f}:saturation={saturation:.2f}")

        if target_resolution == "1080p":
            vf_list.append("scale='min(1920,iw)':-2:flags=fast_bilinear")
        elif target_resolution == "720p":
            vf_list.append("scale='min(1280,iw)':-2:flags=fast_bilinear")

        if aspect_ratio == "9:16" and anchor == "fit":
            canvas_w, canvas_h = vertical_canvas_size(profile)
            graph = vertical_fit_graph(canvas_w, canvas_h)
            if vf_list:
                graph += "," + ",".join(vf_list)
            cmd.extend(["-filter_complex", graph])
        else:
            crop = aspect_crop_filter(aspect_ratio, anchor)
            if crop:
                vf_list.insert(0, crop)
            if vf_list:
                cmd.extend(["-vf", ",".join(vf_list)])
        export_rate = {"light": 1800, "balanced": 2800, "high": 4500}.get(profile, 2800)
        cmd.extend(["-threads", str(encode_threads(profile))])
        cmd.extend(video_encode_args(self.ffmpeg_bin, use_hardware_accel, export_rate, profile))

        # 音訊處理、倍速與音量增益
        if mute_audio:
            cmd.append("-an")
        else:
            af_list = []
            if speed != 1.0:
                # atempo 支援 0.5 到 2.0
                if 0.5 <= speed <= 2.0:
                    af_list.append(f"atempo={speed:.2f}")
                elif speed > 2.0:
                    af_list.append("atempo=2.0,atempo=" + str(speed / 2.0))
                elif speed < 0.5:
                    af_list.append("atempo=0.5,atempo=" + str(speed / 0.5))

            if volume != 1.0:
                af_list.append(f"volume={volume:.2f}")

            if af_list:
                cmd.extend(["-af", ",".join(af_list)])

            cmd.extend(["-c:a", "aac", "-b:a", audio_bitrate(profile)])

        cmd.extend(["-movflags", "+faststart", output_file])

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and os.path.exists(output_file):
                return True, output_file
            return False, f"剪輯失敗: {res.stderr}"
        except Exception as e:
            return False, f"剪輯發生異常: {str(e)}"

    def export_gif(self, input_file, output_file, start_sec, end_sec, fps=12, width=640, aspect_ratio="original", anchor="center"):
        """
        GIF 導出。文書電腦降低幀率、寬度和調色盤，避免兩遍 lanczos 把機器卡住。
        """
        input_file = str(input_file)
        output_file = str(output_file)
        duration = end_sec - start_sec
        if duration <= 0:
            return False, "長度必須大於 0 秒"

        profile = machine_profile()
        fit = aspect_ratio == "9:16" and anchor == "fit"
        if fit:
            width = 270 if profile == "light" else 360
        elif aspect_ratio == "9:16":
            width = min(int(width), 360)
        budget = gif_export_settings(duration, fps=fps, width=width, profile=profile)
        palette = (
            f"fps={budget['fps']},scale={budget['width']}:-1:flags={budget['flags']},"
            f"split[s0][s1];[s0]palettegen=max_colors={budget['colors']}[p];[s1][p]paletteuse=dither=bayer"
        )
        if fit:
            canvas_w, canvas_h = (270, 480) if profile == "light" else (360, 640)
            vf = vertical_fit_graph(canvas_w, canvas_h) + "," + palette
        else:
            crop = aspect_crop_filter(aspect_ratio, anchor)
            vf = f"{crop},{palette}" if crop else palette

        cmd = [self.ffmpeg_bin, "-y"]
        if budget["profile"] == "light":
            cmd.extend(["-filter_threads", "1"])
        cmd.extend([
            "-threads", str(encode_threads(budget["profile"])),
            "-ss", f"{start_sec:.3f}",
            "-i", input_file,
            "-t", f"{duration:.3f}",
            "-vf", vf,
            output_file,
        ])

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and os.path.exists(output_file):
                return True, output_file
            return False, f"GIF 匯出失敗: {res.stderr}"
        except Exception as e:
            return False, f"GIF 匯出發生異常: {str(e)}"

    def extract_audio(self, input_file, output_file, start_sec=None, end_sec=None, volume=1.0):
        """
        提取純音訊為 MP3 或 M4A (支援音量增益)
        """
        input_file = str(input_file)
        output_file = str(output_file)

        info = self.get_video_info(input_file)
        if info and not info.get("has_audio"):
            return False, "該影片沒有音訊軌道，無法提取音訊"

        cmd = [self.ffmpeg_bin, "-y"]
        if start_sec is not None and end_sec is not None and (end_sec > start_sec):
            cmd.extend(["-ss", f"{start_sec:.3f}", "-i", input_file, "-t", f"{end_sec - start_sec:.3f}"])
        else:
            cmd.extend(["-i", input_file])

        if volume != 1.0:
            cmd.extend(["-af", f"volume={volume:.2f}"])

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
        if not self.ffplay_bin:
            return None
        cmd = [
            self.ffplay_bin,
            "-ss", f"{start_sec:.3f}",
            "-t", f"{duration_sec:.3f}",
            "-autoexit",
            "-window_title", "影片區段預覽 (按 Q 或 Esc 關閉)",
            file_path
        ]
        try:
            return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            return None
