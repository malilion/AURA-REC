#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
platform_utils.py - 跨平台輔助模組 (macOS & Windows & Linux)
處理系統相依的二進制檔案路徑、字型、系統提示音、檔案開啟/資料夾定位與 DPI 縮放設定
"""

import os
import platform
import shutil
import subprocess
import sys
import threading
from pathlib import Path

IS_MAC = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"


def enable_dpi_awareness():
    """在 Windows 上啟用 High-DPI 支援，避免字體模糊"""
    if IS_WINDOWS:
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def find_executable(name, extra_mac_paths=None, extra_win_paths=None):
    """
    跨平台智慧搜尋執行檔 (ffmpeg, ffprobe, ffplay)
    """
    # 1. 優先搜尋系統 PATH
    found = shutil.which(name)
    if found:
        return found

    # 2. 搜尋當前專案資料夾底下
    local_dir = Path(__file__).resolve().parent
    ext = ".exe" if IS_WINDOWS else ""
    local_bin = local_dir / f"{name}{ext}"
    if local_bin.exists():
        return str(local_bin)

    # 3. macOS 常見路徑
    if IS_MAC:
        mac_paths = extra_mac_paths or [
            f"/opt/homebrew/bin/{name}",
            f"/usr/local/bin/{name}",
            f"/usr/bin/{name}"
        ]
        for p in mac_paths:
            if os.path.exists(p):
                return p

    # 4. Windows 常見路徑
    elif IS_WINDOWS:
        win_paths = extra_win_paths or [
            rf"C:\ffmpeg\bin\{name}.exe",
            rf"C:\Program Files\ffmpeg\bin\{name}.exe",
            os.path.expandvars(rf"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*\{name}.exe"),
            os.path.expandvars(rf"%USERPROFILE%\scoop\shims\{name}.exe"),
            os.path.expandvars(rf"%PROGRAMDATA%\chocolatey\bin\{name}.exe"),
        ]
        for p in win_paths:
            if "*" in p:
                import glob
                matches = glob.glob(p)
                if matches:
                    return matches[0]
            elif os.path.exists(p):
                return p

    return f"{name}{ext}"


def get_ui_fonts():
    """獲取跨平台最適字體設定"""
    if IS_WINDOWS:
        # Windows 優選微軟正黑體或 Segoe UI
        family = "Microsoft JhengHei"
        return {
            "title": (family, 16, "bold"),
            "subtitle": (family, 12, "bold"),
            "body": (family, 10),
            "bold": (family, 10, "bold"),
            "timer": ("Consolas", 32, "bold"),
            "badge": (family, 9, "bold")
        }
    elif IS_MAC:
        return {
            "title": ("SF Pro Display", 18, "bold"),
            "subtitle": ("SF Pro Text", 12, "bold"),
            "body": ("SF Pro Text", 11),
            "bold": ("SF Pro Text", 11, "bold"),
            "timer": ("SF Pro Display", 34, "bold"),
            "badge": ("SF Pro Text", 10, "bold")
        }
    else:
        return {
            "title": ("DejaVu Sans", 16, "bold"),
            "subtitle": ("DejaVu Sans", 12, "bold"),
            "body": ("DejaVu Sans", 10),
            "bold": ("DejaVu Sans", 10, "bold"),
            "timer": ("Monospace", 30, "bold"),
            "badge": ("DejaVu Sans", 9, "bold")
        }


def play_system_alert(sound_type="ready"):
    """跨平台系統提示音"""
    def _play():
        try:
            if IS_MAC:
                sound_name = "Hero" if sound_type == "start" else ("Glass" if sound_type == "stop" else "Tink")
                sound_path = f"/System/Library/Sounds/{sound_name}.aiff"
                if os.path.exists(sound_path):
                    subprocess.run(["afplay", sound_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif IS_WINDOWS:
                import winsound
                if sound_type == "start":
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                elif sound_type == "stop":
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                else:
                    winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass

    threading.Thread(target=_play, daemon=True).start()


def open_file_or_dir(path, reveal=False):
    """
    跨平台在檔案總管 / Finder 中開啟或選取檔案
    """
    path = str(path)
    if not os.path.exists(path):
        return

    try:
        if IS_MAC:
            if reveal and os.path.isfile(path):
                subprocess.run(["open", "-R", path])
            else:
                subprocess.run(["open", path])
        elif IS_WINDOWS:
            norm_path = os.path.normpath(path)
            if reveal and os.path.isfile(norm_path):
                subprocess.run(["explorer", f"/select,{norm_path}"])
            else:
                os.startfile(norm_path)
        else:
            subprocess.run(["xdg-open", path])
    except Exception as e:
        print(f"[open_file_or_dir] Error: {e}")


def detect_best_video_encoder(ffmpeg_bin):
    """
    偵測系統最佳硬體加速影像編碼器
    - macOS: h264_videotoolbox
    - Windows: h264_nvenc (NVIDIA) > h264_qsv (Intel) > h264_amf (AMD) > libx264
    """
    if IS_MAC:
        return "h264_videotoolbox"

    # Windows / Linux 檢查支援的硬體編碼器
    try:
        res = subprocess.run([ffmpeg_bin, "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="ignore")
        out = res.stdout
        if "h264_nvenc" in out:
            return "h264_nvenc"
        elif "h264_qsv" in out:
            return "h264_qsv"
        elif "h264_amf" in out:
            return "h264_amf"
    except Exception:
        pass

    return "libx264"
