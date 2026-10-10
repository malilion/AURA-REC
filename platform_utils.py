#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
platform_utils.py - 跨平台輔助模組 (macOS & Windows & Linux)
處理系統相依的二進制檔案路徑、字型、系統提示音、檔案開啟/資料夾定位與 DPI 縮放設定
"""

import json
import os
import re
import platform
import shutil
import subprocess
import sys
import threading
from pathlib import Path

IS_MAC = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
APP_VERSION = "2.5.1"


def enable_dpi_awareness():
    """Windows 的視窗座標要跟擷取像素同一套。必須在開視窗之前呼叫。"""
    if not IS_WINDOWS:
        return
    try:
        from ctypes import c_void_p, windll
        # -4 是 PER_MONITOR_AWARE_V2。gdigrab 用的是實體像素。
        if windll.user32.SetProcessDpiAwarenessContext(c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            from ctypes import windll
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class HiddenRecordHotkeys:
    """macOS：視窗收起來以後，F8 暫停、F9 或 Esc 停止。"""

    def __init__(self):
        self._on_key = None
        self._proc = None
        self._carbon = None
        self._hot_refs = []
        self._handler_ref = None

    def arm(self, on_key):
        self.disarm()
        if not IS_MAC or on_key is None:
            return False
        try:
            import ctypes
            from ctypes import CFUNCTYPE, POINTER, byref, c_int32, c_uint32, c_void_p
            carbon = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Carbon.framework/Carbon")
        except (OSError, ImportError):
            return False

        class EventTypeSpec(ctypes.Structure):
            _fields_ = [("eventClass", c_uint32), ("eventKind", c_uint32)]

        class EventHotKeyID(ctypes.Structure):
            _fields_ = [("signature", c_uint32), ("id", c_uint32)]

        names = {1: "f9", 2: "f8", 3: "esc", 4: "f6", 5: "f7"}
        proc_type = CFUNCTYPE(c_int32, c_void_p, c_void_p, c_void_p)
        carbon.GetApplicationEventTarget.restype = c_void_p
        carbon.InstallEventHandler.restype = c_int32
        carbon.InstallEventHandler.argtypes = [
            c_void_p, proc_type, c_uint32, POINTER(EventTypeSpec), c_void_p, POINTER(c_void_p)
        ]
        carbon.RegisterEventHotKey.restype = c_int32
        carbon.RegisterEventHotKey.argtypes = [
            c_uint32, c_uint32, EventHotKeyID, c_void_p, c_uint32, POINTER(c_void_p)
        ]
        carbon.UnregisterEventHotKey.restype = c_int32
        carbon.UnregisterEventHotKey.argtypes = [c_void_p]
        carbon.RemoveEventHandler.restype = c_int32
        carbon.RemoveEventHandler.argtypes = [c_void_p]
        carbon.GetEventParameter.restype = c_int32
        carbon.GetEventParameter.argtypes = [
            c_void_p, c_uint32, c_uint32, c_void_p, c_uint32, c_void_p, c_void_p
        ]

        def handle(_next_handler, event, _user):
            ident = EventHotKeyID()
            carbon.GetEventParameter(
                event, 0x2D2D2D2D, 0x686B6964, None,
                ctypes.sizeof(ident), None, byref(ident),
            )
            name = names.get(int(ident.id))
            if name and self._on_key is not None:
                try:
                    self._on_key(name)
                except Exception:
                    pass
            return 0

        proc = proc_type(handle)
        spec = EventTypeSpec(0x6B657962, 5)
        handler_ref = c_void_p()
        if carbon.InstallEventHandler(
            carbon.GetApplicationEventTarget(), proc, 1, byref(spec), None, byref(handler_ref)
        ) != 0:
            return False
        refs = []
        for key_code, ident in ((101, 1), (100, 2), (53, 3), (97, 4), (98, 5)):
            hot = c_void_p()
            status = carbon.RegisterEventHotKey(
                key_code, 0, EventHotKeyID(0x41555241, ident),
                carbon.GetApplicationEventTarget(), 0, byref(hot),
            )
            if status != 0 or not hot.value:
                for ref in refs:
                    carbon.UnregisterEventHotKey(ref)
                if handler_ref.value:
                    carbon.RemoveEventHandler(handler_ref)
                return False
            refs.append(hot)
        self._proc = proc
        self._carbon = carbon
        self._hot_refs = refs
        self._handler_ref = handler_ref
        self._on_key = on_key
        return True

    def disarm(self):
        carbon = self._carbon
        if carbon is not None:
            for ref in self._hot_refs:
                try:
                    carbon.UnregisterEventHotKey(ref)
                except Exception:
                    pass
            if self._handler_ref is not None and self._handler_ref.value:
                try:
                    carbon.RemoveEventHandler(self._handler_ref)
                except Exception:
                    pass
        self._hot_refs = []
        self._handler_ref = None
        self._carbon = None
        self._proc = None
        self._on_key = None


def use_dark_appearance():
    """macOS 標題列與選單跟著官網深色。若為舊版 Tk 8.5 則略過以避免黑屏。沒有 PyObjC 就維持系統外觀。"""
    if not IS_MAC:
        return
    try:
        import tkinter
        if getattr(tkinter, "TkVersion", 0) < 8.6:
            return
        from AppKit import NSAppearance, NSApplication
        appearance = NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua")
        NSApplication.sharedApplication().setAppearance_(appearance)
    except Exception:
        pass


def get_mac_screen_details():
    """取得 macOS 各個 Capture screen 編號對應的顯示器資訊 (主螢幕/內建/外接、解析度)。"""
    if not IS_MAC:
        return {}
    try:
        import ctypes
        class _Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]
        class _Size(ctypes.Structure):
            _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]
        class _Rect(ctypes.Structure):
            _fields_ = [("origin", _Point), ("size", _Size)]

        cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cg.CGMainDisplayID.restype = ctypes.c_uint32
        cg.CGGetActiveDisplayList.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
        cg.CGGetActiveDisplayList.restype = ctypes.c_int32
        cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
        cg.CGDisplayBounds.restype = _Rect
        cg.CGDisplayIsBuiltin.argtypes = [ctypes.c_uint32]
        cg.CGDisplayIsBuiltin.restype = ctypes.c_bool

        count = ctypes.c_uint32(0)
        if cg.CGGetActiveDisplayList(0, None, ctypes.byref(count)) != 0 or not count.value:
            return {}
        id_list = (ctypes.c_uint32 * count.value)()
        if cg.CGGetActiveDisplayList(count.value, id_list, ctypes.byref(count)) != 0:
            return {}
        main_id = int(cg.CGMainDisplayID())
        ordered = sorted((int(id_list[i]) for i in range(count.value)), key=lambda did: (did != main_id, did))

        details = {}
        for idx, did in enumerate(ordered):
            rect = cg.CGDisplayBounds(did)
            is_main = (did == main_id)
            is_builtin = bool(cg.CGDisplayIsBuiltin(did))
            type_str = "內建" if is_builtin else "外接"
            role = f"主螢幕 ({type_str})" if is_main else f"外接螢幕"
            w, h = int(rect.size.width), int(rect.size.height)
            details[idx] = f"{role} {w}x{h}"
        return details
    except Exception:
        return {}


def get_screen_full_info():
    """
    取得所有實體顯示器的詳細幾何資訊、識別編號、名稱與解析度。
    回傳列表，每個元素為 dict：
    {
        "index": 0,           # 0-based 螢幕索引
        "screencapture_id": 1,# screencapture -D 的編號 (1-based)
        "display_id": 1,      # CoreGraphics 或系統 Display ID
        "is_main": True,
        "is_builtin": True,
        "title": "主螢幕 (內建)",
        "width": 1440,
        "height": 900,
        "x": 0.0,
        "y": 0.0,
        "scale": 2.0,
        "label": "主螢幕 (內建) 1440x900",
    }
    """
    screens = []
    if IS_MAC:
        try:
            import ctypes
            class _Point(ctypes.Structure):
                _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]
            class _Size(ctypes.Structure):
                _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]
            class _Rect(ctypes.Structure):
                _fields_ = [("origin", _Point), ("size", _Size)]

            cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
            cg.CGMainDisplayID.restype = ctypes.c_uint32
            cg.CGGetActiveDisplayList.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)]
            cg.CGGetActiveDisplayList.restype = ctypes.c_int32
            cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
            cg.CGDisplayBounds.restype = _Rect
            cg.CGDisplayIsBuiltin.argtypes = [ctypes.c_uint32]
            cg.CGDisplayIsBuiltin.restype = ctypes.c_bool
            cg.CGDisplayCopyDisplayMode.argtypes = [ctypes.c_uint32]
            cg.CGDisplayCopyDisplayMode.restype = ctypes.c_void_p
            cg.CGDisplayModeGetPixelWidth.argtypes = [ctypes.c_void_p]
            cg.CGDisplayModeGetPixelWidth.restype = ctypes.c_size_t
            cg.CGDisplayModeGetWidth.argtypes = [ctypes.c_void_p]
            cg.CGDisplayModeGetWidth.restype = ctypes.c_size_t
            cf.CFRelease.argtypes = [ctypes.c_void_p]

            count = ctypes.c_uint32(0)
            if cg.CGGetActiveDisplayList(0, None, ctypes.byref(count)) == 0 and count.value:
                id_list = (ctypes.c_uint32 * count.value)()
                if cg.CGGetActiveDisplayList(count.value, id_list, ctypes.byref(count)) == 0:
                    main_id = int(cg.CGMainDisplayID())
                    ordered = sorted((int(id_list[i]) for i in range(count.value)), key=lambda did: (did != main_id, did))
                    for idx, did in enumerate(ordered):
                        rect = cg.CGDisplayBounds(did)
                        is_main = (did == main_id)
                        is_builtin = bool(cg.CGDisplayIsBuiltin(did))
                        type_str = "內建" if is_builtin else "外接"
                        role = f"主螢幕 ({type_str})" if is_main else "外接螢幕"
                        w, h = int(rect.size.width), int(rect.size.height)
                        scale = 1.0
                        mode = cg.CGDisplayCopyDisplayMode(did)
                        if mode:
                            try:
                                pw = int(cg.CGDisplayModeGetPixelWidth(mode))
                                lw = int(cg.CGDisplayModeGetWidth(mode))
                                if pw > 0 and lw > 0:
                                    scale = max(1.0, pw / lw)
                            finally:
                                cf.CFRelease(mode)
                        screens.append({
                            "index": idx,
                            "name": f"Capture screen {idx}",
                            "screencapture_id": idx + 1,
                            "display_id": did,
                            "is_main": is_main,
                            "is_builtin": is_builtin,
                            "title": role,
                            "width": w,
                            "height": h,
                            "x": float(rect.origin.x),
                            "y": float(rect.origin.y),
                            "scale": scale,
                            "label": f"{role} {w}x{h}",
                        })
        except Exception:
            pass

    if not screens:
        screens.append({
            "index": 0,
            "name": "預設主螢幕",
            "screencapture_id": 1,
            "display_id": 0,
            "is_main": True,
            "is_builtin": True,
            "title": "主螢幕",
            "width": 1920,
            "height": 1080,
            "x": 0.0,
            "y": 0.0,
            "scale": 1.0,
            "label": "主螢幕 1920x1080",
        })
    return screens


def create_placeholder_ppm(width=288, height=162, bg_rgb=(18, 18, 23), border_rgb=(39, 39, 42)):
    """純 Python 生成深色相容 PPM 點陣圖，避免依賴 PIL。"""
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            if x == 0 or x == width - 1 or y == 0 or y == height - 1:
                pixels.extend(border_rgb)
            elif (y == height // 2 and width // 4 <= x <= 3 * width // 4) or (x == width // 2 and height // 4 <= y <= 3 * height // 4):
                pixels.extend((60, 60, 70))
            else:
                pixels.extend(bg_rgb)
    return header + bytes(pixels)


def capture_device_preview_ppm(ffmpeg_bin, dev_name, width=288, height=162, timeout=4.0, bg_mode="original", bg_strength="medium"):
    """
    擷取指定螢幕或攝影機設備的即時單幀縮圖，回傳 PPM bytes (直接相容 tk.PhotoImage)。
    支援攝影機即時虛擬背景與景深虛化預覽。
    macOS 優先使用 screencapture (極速 ~0.15s)，若失敗則回退 FFmpeg avfoundation。
    Windows 支援 gdigrab 與 dshow。Linux 支援 x11grab。
    失敗時回傳深色佔位 PPM 圖片。
    """
    dev_str = str(dev_name or "").strip()
    low = dev_str.lower()

    if IS_MAC:
        # 1. 判斷是否為螢幕畫面
        m_screen = re.search(r"screen\s*(\d+)", low)
        is_screen = bool(m_screen) or any(k in low for k in ("螢幕", "desktop", "display"))
        if is_screen:
            s_idx = int(m_screen.group(1)) if m_screen else 0
            sc_id = s_idx + 1
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                # screencapture -x (無快門音) -D <顯示器編號>
                r = subprocess.run(["screencapture", "-x", "-D", str(sc_id), tmp_path], timeout=timeout)
                if r.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0 and ffmpeg_bin:
                    conv_cmd = [
                        ffmpeg_bin, "-y", "-i", tmp_path,
                        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
                        "-f", "image2", "-vcodec", "ppm", "-"
                    ]
                    p = subprocess.run(conv_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
                    if p.returncode == 0 and p.stdout:
                        return p.stdout
            except Exception:
                pass
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass

            # 若 screencapture 失敗，回退使用 ffmpeg avfoundation 截螢幕
            if ffmpeg_bin:
                try:
                    ff_input = f"Capture screen {s_idx}:none"
                    ff_cmd = [
                        ffmpeg_bin, "-y", "-f", "avfoundation", "-framerate", "30", "-capture_cursor", "0",
                        "-i", ff_input, "-vframes", "1",
                        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
                        "-f", "image2", "-vcodec", "ppm", "-"
                    ]
                    p = subprocess.run(ff_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
                    if p.returncode == 0 and p.stdout:
                        return p.stdout
                except Exception:
                    pass

        # 2. 判斷是否為攝影機
        is_camera = any(k in low for k in ("相機", "camera", "facetime", "鏡頭", "webcam")) or dev_str.isdigit() or not is_screen
        if is_camera and ffmpeg_bin:
            m_idx = re.search(r"\[(\d+)\]", dev_str)
            if m_idx:
                cam_idx = m_idx.group(1)
            elif dev_str.isdigit():
                cam_idx = dev_str
            else:
                cam_idx = "0"
            try:
                if bg_mode and bg_mode != "original":
                    try:
                        pip_steps = build_pip_filter_steps(
                            cam_input_label="0:v",
                            pip_size=min(width, height),
                            pip_shape="circle" if width == height else "rect",
                            bg_mode=bg_mode,
                            bg_strength=bg_strength,
                            border_rgb=(0, 240, 255),
                            fps=30,
                        )
                        ff_cmd = [
                            ffmpeg_bin, "-y", "-f", "avfoundation", "-framerate", "30",
                            "-i", f"{cam_idx}:none", "-vframes", "1",
                            "-filter_complex", ";".join(pip_steps),
                            "-map", "[cam]",
                            "-f", "image2", "-vcodec", "ppm", "-"
                        ]
                        p = subprocess.run(ff_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
                        if p.returncode == 0 and p.stdout:
                            return p.stdout
                    except Exception:
                        pass

                ff_cmd = [
                    ffmpeg_bin, "-y", "-f", "avfoundation", "-framerate", "30",
                    "-i", f"{cam_idx}:none", "-vframes", "1",
                    "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
                    "-f", "image2", "-vcodec", "ppm", "-"
                ]
                p = subprocess.run(ff_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
                if p.returncode == 0 and p.stdout:
                    return p.stdout
            except Exception:
                pass

    elif IS_WINDOWS and ffmpeg_bin:
        try:
            if "desktop" in low or "全螢幕" in low or "桌面" in low:
                ff_cmd = [
                    ffmpeg_bin, "-y", "-f", "gdigrab", "-framerate", "30",
                    "-i", "desktop", "-vframes", "1",
                    "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
                    "-f", "image2", "-vcodec", "ppm", "-"
                ]
            else:
                m_name = re.search(r"\[.+?\]\s*(.*)", dev_str)
                name = m_name.group(1).strip() if m_name else dev_str
                ff_cmd = [
                    ffmpeg_bin, "-y", "-f", "dshow",
                    "-i", f"video={name}", "-vframes", "1",
                    "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
                    "-f", "image2", "-vcodec", "ppm", "-"
                ]
            p = subprocess.run(ff_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
            if p.returncode == 0 and p.stdout:
                return p.stdout
        except Exception:
            pass

    elif IS_LINUX and ffmpeg_bin:
        try:
            ff_cmd = [
                ffmpeg_bin, "-y", "-f", "x11grab", "-framerate", "30",
                "-i", ":0.0", "-vframes", "1",
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
                "-f", "image2", "-vcodec", "ppm", "-"
            ]
            p = subprocess.run(ff_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
            if p.returncode == 0 and p.stdout:
                return p.stdout
        except Exception:
            pass

    return create_placeholder_ppm(width, height)


def flash_screen_badges(root, screen_infos=None, duration_ms=2500):
    """
    在所有實體螢幕的正中央彈出大型半透明發光編號指示卡 (1, 2...)，
    並於 duration_ms 毫秒後自動關閉，讓使用者清楚明白實體顯示器的編號對應。
    """
    import tkinter as tk
    if not screen_infos:
        screen_infos = get_screen_full_info()

    badge_windows = []

    for screen in screen_infos:
        try:
            win = tk.Toplevel(root)
            win.overrideredirect(True)
            win.configure(bg="#09090b")
            try:
                win.attributes("-topmost", True)
                win.attributes("-alpha", 0.94)
            except Exception:
                pass

            bw, bh = 240, 220
            cx = int(screen["x"] + screen["width"] / 2)
            cy = int(screen["y"] + screen["height"] / 2)
            pos_x = cx - (bw // 2)
            pos_y = cy - (bh // 2)
            win.geometry(f"{bw}x{bh}+{pos_x}+{pos_y}")

            card = tk.Frame(win, bg="#18181b", highlightbackground="#3b82f6", highlightthickness=2)
            card.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

            disp_num = str(screen.get("screencapture_id") or (screen["index"] + 1))

            num_lbl = tk.Label(
                card,
                text=disp_num,
                font=("SF Pro Display", 68, "bold") if IS_MAC else ("Segoe UI", 60, "bold"),
                fg="#ffffff",
                bg="#18181b",
            )
            num_lbl.pack(pady=(10, 0))

            title_text = screen.get("title", f"螢幕 {disp_num}")
            tk.Label(
                card,
                text=title_text,
                font=("SF Pro Text", 13, "bold") if IS_MAC else ("Segoe UI", 12, "bold"),
                fg="#60a5fa",
                bg="#18181b",
            ).pack(pady=(2, 0))

            res_text = f"{screen.get('width', 0)} × {screen.get('height', 0)}"
            if screen.get("scale", 1.0) > 1.0:
                res_text += " Retina"
            tk.Label(
                card,
                text=res_text,
                font=("SF Pro Text", 11) if IS_MAC else ("Segoe UI", 10),
                fg="#a1a1aa",
                bg="#18181b",
            ).pack(pady=(2, 10))

            for widget in (win, card, num_lbl):
                widget.bind("<Button-1>", lambda _e, w=win: w.destroy())

            badge_windows.append(win)
        except Exception:
            pass

    def _close_all():
        for w in badge_windows:
            try:
                w.destroy()
            except Exception:
                pass

    if badge_windows:
        root.after(duration_ms, _close_all)


def find_executable(name, extra_mac_paths=None, extra_win_paths=None):
    """
    跨平台智慧搜尋執行檔 (ffmpeg, ffprobe, ffplay)
    """
    ext = ".exe" if IS_WINDOWS else ""

    # 0. 打包後的 App：優先使用隨附的版本，行為一致，也不受 Finder 精簡 PATH 影響
    if getattr(sys, "frozen", False):
        bundled_dirs = []
        if hasattr(sys, "_MEIPASS"):
            bundled_dirs += [Path(sys._MEIPASS) / "bin", Path(sys._MEIPASS)]
        bundled_dirs += [Path(sys.executable).resolve().parent / "bin", Path(sys.executable).resolve().parent]
        for d in bundled_dirs:
            cand = d / f"{name}{ext}"
            if cand.is_file() and os.access(str(cand), os.X_OK if not IS_WINDOWS else os.F_OK):
                return str(cand)

    # 1. 搜尋系統 PATH
    found = shutil.which(name)
    if found:
        return found

    # 2. 搜尋當前專案與套件內嵌路徑
    local_dir = Path(__file__).resolve().parent
    candidates = [
        local_dir / f"{name}{ext}",
        local_dir / "bin" / f"{name}{ext}",
        Path(sys.executable).resolve().parent / f"{name}{ext}",
        Path(sys.executable).resolve().parent / "bin" / f"{name}{ext}",
    ]
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        candidates.extend([
            meipass / f"{name}{ext}",
            meipass / "bin" / f"{name}{ext}",
        ])
    if IS_MAC:
        # 檢查 .app/Contents/MacOS/ 或 .app/Contents/Resources/bin/
        candidates.extend([
            local_dir.parent / "MacOS" / name,
            local_dir.parent / "Resources" / "bin" / name,
        ])
    for candidate in candidates:
        if candidate.is_file() and os.access(str(candidate), os.X_OK if not IS_WINDOWS else os.F_OK):
            return str(candidate)

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


_ui_font_cache = None


def ensure_brand_fonts():
    """只在這個程式裡註冊官網用的字，不寫進系統字型資料夾。"""
    if not IS_MAC or getattr(ensure_brand_fonts, "_done", False):
        return
    ensure_brand_fonts._done = True
    folder = Path(__file__).resolve().parent / "fonts"
    if not folder.is_dir():
        return
    try:
        import ctypes
        cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        ct = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreText.framework/CoreText")
        cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
        cf.CFURLCreateFromFileSystemRepresentation.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool,
        ]
        ct.CTFontManagerRegisterFontsForURL.restype = ctypes.c_bool
        ct.CTFontManagerRegisterFontsForURL.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        for path in sorted(folder.glob("*.ttf")):
            raw = str(path).encode()
            url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), False)
            if url:
                ct.CTFontManagerRegisterFontsForURL(url, 1, None)
    except Exception:
        pass


def get_ui_fonts():
    """獲取跨平台最適字體設定。Mac 會用官網的 Syne 與 JetBrains Mono。"""
    global _ui_font_cache
    if _ui_font_cache is not None:
        return _ui_font_cache
    ensure_brand_fonts()
    families = set()
    try:
        import tkinter.font as tkfont
        families = set(tkfont.families())
    except Exception:
        pass
    if IS_WINDOWS:
        family = "Microsoft JhengHei"
        mono = "Consolas"
        display = family
        sans = family
    elif IS_MAC:
        sans = "PingFang TC"
        display = "Syne" if "Syne" in families else sans
        mono = "JetBrains Mono" if "JetBrains Mono" in families else "Menlo"
    else:
        sans = "DejaVu Sans"
        display = sans
        mono = "DejaVu Sans Mono" if "DejaVu Sans Mono" in families else "Monospace"
    _ui_font_cache = {
        "title": (display, 22, "bold"),
        "subtitle": (display, 14, "bold"),
        "body": (sans, 12),
        "bold": (sans, 12, "bold"),
        "mono": (mono, 13, "bold"),
        "timer": (mono, 32, "bold"),
        "badge": (mono, 11),
    }
    return _ui_font_cache


# 跟官網同一套：黑底、青字、玫瑰錄影鈕。
UI = {
    "bg": "#060709",
    "card": "#0F1218",
    "line": "#1E2330",
    "text": "#F8FAFC",
    "muted": "#94A3B8",
    "blue": "#00F0FF",
    "blue_hover": "#66F6FF",
    "red": "#FF2A6D",
    "red_hover": "#FF5C8A",
    "ok": "#00FF9D",
    "warn": "#FFB800",
    "field": "#0A0C10",
    "hover": "#151922",
    "preview": "#060709",
    "mini": "#060709",
    "mini_muted": "#64748B",
    "on": "#FFFFFF",
    "white": "#FFFFFF",
    "ink": "#060709",
    "edge": "#2A3244",
    "meter_low": "#00FF9D",
    "meter_mid": "#FFB800",
    "meter_high": "#FF2A6D",
    "meter_idle": "#1E2330",
}


def apply_widget_style(style, fonts=None):
    """官網配色。macOS 原生按鈕不會吃背景色，所以控制項走 clam。"""
    style.theme_use("clam")
    button_font = fonts["subtitle"] if fonts else None
    body_font = fonts["bold"] if fonts else None
    small_font = fonts["body"] if fonts else None

    style.configure(
        ".",
        background=UI["bg"],
        foreground=UI["text"],
        fieldbackground=UI["field"],
        troughcolor=UI["line"],
        bordercolor=UI["edge"],
        arrowcolor=UI["muted"],
    )

    def paint(name, background, hover, font, foreground=None, padding=(14, 10), border=None, disabled_bg=None):
        fg = foreground or UI["on"]
        disabled_bg = disabled_bg or UI["line"]
        opts = dict(
            background=background,
            foreground=fg,
            borderwidth=1 if border else 0,
            focusthickness=0,
            focuscolor=background,
            padding=padding,
            relief="flat",
            anchor="center",
        )
        if border:
            opts["bordercolor"] = border
            opts["lightcolor"] = border
            opts["darkcolor"] = border
        if font:
            opts["font"] = font
        style.configure(name, **opts)
        mapped = dict(
            background=[
                ("pressed", hover),
                ("active", hover),
                ("disabled", disabled_bg),
            ],
            foreground=[("disabled", UI["muted"])],
        )
        if border:
            mapped["bordercolor"] = [("active", UI["blue"]), ("pressed", UI["blue"])]
        style.map(name, **mapped)

    # 主按鈕跟官網下載鈕一樣：青底黑字。錄影中改玫瑰底白字。
    paint("Primary.TButton", UI["blue"], UI["blue_hover"], button_font, UI["ink"], (16, 12))
    paint("Play.TButton", UI["blue"], UI["blue_hover"], body_font, UI["ink"], (14, 6))
    paint("Record.TButton", UI["red"], UI["red_hover"], button_font, UI["on"], (16, 12))
    paint("Stop.TButton", UI["red"], UI["red_hover"], body_font, UI["on"], (12, 6))
    paint(
        "Ghost.TButton", UI["hover"], "#10262C", small_font, UI["text"],
        (10, 5), UI["edge"], UI["hover"],
    )
    paint("Link.TButton", UI["card"], UI["hover"], small_font, UI["blue"], (8, 2), None, UI["card"])
    paint("Danger.TButton", UI["card"], UI["hover"], small_font, UI["red"], (8, 2), None, UI["card"])

    if small_font:
        style.configure("App.TCheckbutton", font=small_font)
        style.configure("App.TRadiobutton", font=small_font)
        style.configure("App.TCombobox", font=small_font)
    indicator = [
        ("selected", UI["blue"]),
        ("pressed", UI["blue_hover"]),
        ("!selected", UI["line"]),
    ]
    for name in ("App.TCheckbutton", "App.TRadiobutton"):
        style.configure(
            name,
            background=UI["card"],
            foreground=UI["text"],
            indicatorcolor=UI["line"],
            indicatorrelief="flat",
            borderwidth=0,
            focusthickness=0,
            focuscolor=UI["card"],
            padding=(2, 2),
        )
        style.map(
            name,
            background=[("active", UI["card"]), ("disabled", UI["card"])],
            foreground=[("active", UI["text"]), ("disabled", UI["muted"])],
            indicatorcolor=indicator,
        )
    style.configure(
        "App.TCombobox",
        fieldbackground=UI["field"],
        background=UI["hover"],
        foreground=UI["text"],
        arrowcolor=UI["blue"],
        bordercolor=UI["edge"],
        lightcolor=UI["field"],
        darkcolor=UI["edge"],
        padding=6,
        relief="flat",
    )
    style.map(
        "App.TCombobox",
        fieldbackground=[("readonly", UI["field"]), ("disabled", UI["hover"])],
        foreground=[("readonly", UI["text"]), ("disabled", UI["muted"])],
        background=[("readonly", UI["hover"]), ("active", UI["hover"]), ("disabled", UI["line"])],
        bordercolor=[("focus", UI["blue"]), ("active", UI["blue"])],
        arrowcolor=[("disabled", UI["muted"])],
    )
    style.configure(
        "Horizontal.TScale",
        background=UI["blue"],
        troughcolor=UI["line"],
        bordercolor=UI["bg"],
        lightcolor=UI["blue"],
        darkcolor=UI["blue"],
        sliderlength=18,
        sliderrelief="flat",
    )
    style.map(
        "Horizontal.TScale",
        background=[("active", UI["blue_hover"])],
        troughcolor=[("active", UI["edge"])],
    )
    root = style.master
    root.option_add("*TCombobox*Listbox.background", UI["field"])
    root.option_add("*TCombobox*Listbox.foreground", UI["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", "#10262C")
    root.option_add("*TCombobox*Listbox.selectForeground", UI["blue"])
    style.configure(
        "App.Vertical.TScrollbar",
        background=UI["line"],
        troughcolor=UI["card"],
        bordercolor=UI["card"],
        arrowcolor=UI["muted"],
        relief="flat",
        gripcount=0,
    )
    style.map(
        "App.Vertical.TScrollbar",
        background=[("active", UI["edge"]), ("pressed", UI["muted"])],
        arrowcolor=[("active", UI["text"])],
    )
    root.option_add("*Menu.background", UI["card"])
    root.option_add("*Menu.foreground", UI["text"])
    root.option_add("*Menu.activeBackground", UI["hover"])
    root.option_add("*Menu.activeForeground", UI["blue"])


def play_system_alert(sound_type="ready"):
    """跨平台系統提示音"""
    def _play():
        try:
            if IS_MAC:
                if sound_type == "start":
                    sound_name = "Hero"
                elif sound_type == "stop":
                    sound_name = "Glass"
                elif sound_type in ("shot", "snap"):
                    sound_name = "Pop"
                elif sound_type == "complete":
                    sound_name = "Ping"
                else:
                    sound_name = "Tink"
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


def copy_file(path):
    """把檔案放到剪貼簿，可以貼到 Finder 或其他資料夾。"""
    target = Path(path)
    try:
        if not target.is_file():
            return False
        target = target.resolve()
    except OSError:
        return False
    try:
        if IS_MAC:
            return _mac_copy_file(target)
        if IS_WINDOWS:
            return _windows_copy_file(target)
        return _copy_text(str(target))
    except Exception:
        return False


def _mac_copy_file(path):
    p_str = str(path)
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString, NSURL

        board = NSPasteboard.generalPasteboard()
        board.clearContents()
        if board.writeObjects_([NSURL.fileURLWithPath_(p_str)]):
            board.setString_forType_(p_str, NSPasteboardTypeString)
            return True
    except Exception:
        pass

    # AppleScript 原生內建備用方案（零依賴，適用所有 macOS）
    try:
        if p_str.lower().endswith(".png"):
            # 優先複製圖片資料至剪貼簿，可直接在通訊軟體/文件貼上影像
            cmd = ["osascript", "-e", f'set the clipboard to (read (POSIX file "{p_str}") as «class PNGf»)']
            if subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4).returncode == 0:
                return True
        cmd = ["osascript", "-e", f'set the clipboard to (POSIX file "{p_str}")']
        if subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4).returncode == 0:
            return True
    except Exception:
        pass
    return False


def _windows_copy_file(path):
    escaped = str(path).replace("'", "''")
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"Set-Clipboard -LiteralPath '{escaped}'"],
        check=True,
        timeout=8,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return True


def _copy_text(text):
    if shutil.which("wl-copy"):
        subprocess.run(["wl-copy"], input=text, text=True, check=True, timeout=5)
        return True
    if shutil.which("xclip"):
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text, text=True, check=True, timeout=5,
        )
        return True
    return False


def copy_text_to_clipboard(text):
    """將文字複製到系統剪貼簿 (跨平台支援 macOS / Windows / Linux)"""
    text = str(text or "")
    try:
        if IS_MAC:
            subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True, timeout=5)
            return True
        elif IS_WINDOWS:
            subprocess.run(["clip"], input=text.encode("utf-8"), check=True, timeout=5)
            return True
        else:
            return _copy_text(text)
    except Exception:
        return False


_ENCODER_CACHE = {}


def _probe_video_encoder(ffmpeg_bin, encoder):
    """實際用該編碼器編一格測試畫面；失敗（無對應 GPU / 驅動）回傳 False。"""
    try:
        res = subprocess.run(
            [
                ffmpeg_bin, "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=256x256:r=10:d=0.2",
                "-frames:v", "1", "-c:v", encoder, "-pix_fmt", "yuv420p",
                "-f", "null", "-",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        return res.returncode == 0
    except Exception:
        return False


def detect_best_video_encoder(ffmpeg_bin):
    """
    偵測系統最佳硬體加速影像編碼器（會實際試編確認可用，否則退回 libx264）。結果會記住，避免每次開錄都再掃一次。
    - macOS: h264_videotoolbox
    - Windows: h264_nvenc (NVIDIA) > h264_qsv (Intel) > h264_amf (AMD) > libx264
    """
    if IS_MAC:
        return "h264_videotoolbox"

    cached = _ENCODER_CACHE.get(ffmpeg_bin)
    if cached:
        return cached

    enc = "libx264"
    try:
        res = subprocess.run(
            [ffmpeg_bin, "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="ignore",
            timeout=8,
        )
        out = res.stdout
        # 只在編碼器清單中出現並不代表可用（ffmpeg 常編入 nvenc，但機器沒有 NVIDIA GPU），
        # 因此逐一實際試編一格，成功才採用；全部失敗則退回軟體 libx264。
        for cand in ("h264_nvenc", "h264_qsv", "h264_amf"):
            if cand in out and _probe_video_encoder(ffmpeg_bin, cand):
                enc = cand
                break
    except Exception:
        pass

    _ENCODER_CACHE[ffmpeg_bin] = enc
    return enc


def running_inside_bundle(script_file=None):
    """從 .app 或 PyInstaller 單檔執行時，不該把錄影寫進套件裡面。"""
    if getattr(sys, "frozen", False):
        return True
    path = str(script_file or Path(__file__).resolve())
    return ".app/Contents/" in path or ".app\\Contents\\" in path


def app_support_dir():
    """使用者設定放在家目錄，不放進專案或 .app。"""
    try:
        if IS_MAC:
            base = Path.home() / "Library" / "Application Support" / "AURA REC"
        elif IS_WINDOWS:
            base = Path(os.environ.get("APPDATA", str(Path.home()))) / "AURA REC"
        else:
            base = Path.home() / ".config" / "aura-rec"
        base.mkdir(parents=True, exist_ok=True)
        return base
    except Exception:
        return Path(__file__).resolve().parent


def load_settings():
    try:
        path = app_support_dir() / "settings.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    try:
        local_path = Path(__file__).resolve().parent / "settings.json"
        if local_path.is_file():
            data = json.loads(local_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def save_settings(updates):
    data = load_settings()
    data.update(updates)
    try:
        path = app_support_dir() / "settings.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception:
        try:
            local_path = Path(__file__).resolve().parent / "settings.json"
            local_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception:
            return False


def default_recordings_dir():
    """系統影片資料夾。macOS 用「影片」，Windows 用 Videos。"""
    if IS_WINDOWS:
        base = Path.home() / "Videos"
    elif IS_MAC:
        base = Path.home() / "Movies"
    else:
        base = Path.home() / "Videos"
    return base / "AURA REC"


def resolve_recordings_dir(script_file):
    """
    已記住的資料夾優先。
    從 .app 啟動時改存到「影片 / AURA REC」，避免寫進應用程式套件。
    從專案目錄直接執行時，仍用專案裡的 recordings/。
    """
    saved = load_settings().get("output_dir")
    if saved:
        chosen = Path(saved).expanduser()
        try:
            chosen.mkdir(parents=True, exist_ok=True)
            return chosen
        except Exception:
            pass

    if running_inside_bundle(script_file):
        dest = default_recordings_dir()
    else:
        dest = Path(script_file).resolve().parent / "recordings"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def ffmpeg_is_available(ffmpeg_bin):
    if not ffmpeg_bin:
        return False
    if os.path.isfile(ffmpeg_bin):
        return True
    return shutil.which(ffmpeg_bin) is not None


def system_memory_gb():
    """讀不到記憶體時當成 8GB 文書電腦，寧可預設輕一點。"""
    try:
        if IS_WINDOWS:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return stat.ullTotalPhys / (1024 ** 3)
        else:
            pages = os.sysconf("SC_PHYS_PAGES")
            page = os.sysconf("SC_PAGE_SIZE")
            return (pages * page) / (1024 ** 3)
    except Exception:
        return 8.0
    return 8.0


def machine_profile():
    """
    light：一般文書電腦（約 4 核心或 8GB）。
    balanced：日常筆電。
    high：核心和記憶體都比較夠。
    """
    cores = os.cpu_count() or 2
    ram = system_memory_gb()
    if cores <= 4 or ram <= 8.5:
        return "light"
    if cores <= 8 or ram <= 16.5:
        return "balanced"
    return "high"


def encode_threads(profile):
    cores = os.cpu_count() or 2
    if profile == "light":
        return max(1, min(2, cores))
    if profile == "balanced":
        return max(1, min(3, max(1, cores // 2)))
    return max(1, min(4, max(1, cores - 2)))


def scale_filter(resolution):
    """長邊對齊，並保留比例。直向範圍不會被拉成超高的橫向畫面。"""
    long_side = {"720p": 1280, "1080p": 1920, "2K": 2560}.get(resolution)
    if not long_side:
        return None
    wide = f"gte(iw\\,ih)"
    return (
        f"scale=w='if({wide}\\,{long_side}\\,-2)':"
        f"h='if({wide}\\,-2\\,{long_side})':flags=fast_bilinear"
    )


def capture_bitrate_k(resolution, profile):
    """畫面錄影用的碼率。靜態桌面不需要影片那種大小。"""
    table = {"720p": 500, "1080p": 800, "2K": 1300, "native": 1000}
    rate = table.get(resolution, 800)
    if profile == "light":
        rate = int(rate * 0.8)
    elif profile == "high":
        rate = int(rate * 1.2)
    return max(400, rate)


def audio_bitrate(profile):
    return "96k" if profile == "light" else "128k"


def recommended_capture(profile=None):
    """文書電腦預設 720p/15，不要一開就抓全螢幕原生。"""
    profile = profile or machine_profile()
    if profile == "light":
        return {"resolution": "720p", "fps": 15, "res_index": 3, "fps_index": 2, "label": "順暢 720p / 15 FPS"}
    if profile == "balanced":
        return {"resolution": "1080p", "fps": 30, "res_index": 2, "fps_index": 0, "label": "平衡 1080p / 30 FPS"}
    return {"resolution": "1080p", "fps": 30, "res_index": 2, "fps_index": 0, "label": "1080p / 30 FPS"}


def build_pip_filter_steps(
    cam_input_label="1:v",
    pip_size=260,
    pip_shape="circle",
    bg_mode="original",
    bg_strength="medium",
    border_rgb=(0, 240, 255),
    fps=30,
):
    """
    產生畫中畫 (PiP 人臉相機) 的 FFmpeg filter_complex 濾鏡步驟清單。
    支援模式：
    - original: 原始相機鏡頭
    - blur: 人像背景虛化 (景深柔焦 Bokeh，支援輕微 12px / 標準 24px / 強烈 40px)
    - transparent: 純人像去背透空 (柔和羽化提取人像輪廓，背景全透明融入桌面)
    - chromakey / greenkey: 綠幕扣像去背 (透明扣除綠色背景)
    - bluekey: 藍幕扣像去背 (透明扣除藍色背景)
    - aurora: 極光深色虛擬漸層背板 (深邃極光紫藍漸層替換雜亂背景)
    形狀支援：
    - circle: 正圓形相機
    - rect: 16:9 圓角矩形相機
    邊框支援：
    - border_rgb: (r, g, b) 或 None (無外框)
    回傳：
    - steps: list[str]，輸出標籤為 [cam]
    """
    try:
        pip_size = int(pip_size or 260)
    except (TypeError, ValueError):
        pip_size = 260
    pip_size = max(64, pip_size)

    pip_shape = "circle" if "circle" in str(pip_shape or "circle").lower() or "圓" in str(pip_shape or "") else "rect"

    if isinstance(border_rgb, str):
        s = border_rgb.lstrip("#")
        if len(s) == 6:
            try:
                border_rgb = (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
            except Exception:
                border_rgb = None
        else:
            border_rgb = None
    elif isinstance(border_rgb, (list, tuple)) and len(border_rgb) == 3:
        try:
            border_rgb = (int(border_rgb[0]), int(border_rgb[1]), int(border_rgb[2]))
        except Exception:
            border_rgb = None
    else:
        border_rgb = None

    if pip_shape == "circle":
        cw = pip_size
        ch = pip_size
    else:
        cw = int(pip_size * 16 / 9)
        cw -= cw % 2
        ch = pip_size
        ch -= ch % 2

    steps = [
        f"[{cam_input_label}]scale={cw}:{ch}:force_original_aspect_ratio=increase,crop={cw}:{ch}[cam_raw]"
    ]

    # 解析強度
    s_low = str(bg_strength or "medium").lower()
    if any(k in s_low for k in ("強", "strong", "high")):
        strength = "strong"
    elif any(k in s_low for k in ("輕", "subtle", "low", "weak")):
        strength = "subtle"
    else:
        strength = "medium"

    # 解析背景模式
    m_low = str(bg_mode or "original").lower()
    if any(k in m_low for k in ("blur", "虛化", "景深", "bokeh")):
        mode = "blur"
    elif any(k in m_low for k in ("trans", "透空", "去背透空", "cutout")):
        mode = "transparent"
    elif any(k in m_low for k in ("green", "綠", "chroma")):
        mode = "chromakey"
    elif any(k in m_low for k in ("blue", "藍")):
        mode = "bluekey"
    elif any(k in m_low for k in ("aurora", "極光")):
        mode = "aurora"
    else:
        mode = "original"

    # 人像中心與橢圓半徑
    cx = cw // 2
    cy = int(ch * 0.48)
    if pip_shape == "circle":
        rx = int(cw * 0.40)
        ry = int(ch * 0.45)
    else:
        rx = int(cw * 0.28)
        ry = int(ch * 0.45)

    if mode == "blur":
        blur_rad = {"subtle": 12, "medium": 24, "strong": 40}.get(strength, 24)
        steps.append(f"[cam_raw]format=yuv420p,split=3[cam_fg][cam_bg][cam_msk]")
        steps.append(f"[cam_bg]boxblur={blur_rad}:2[cam_blurred]")
        steps.append(
            f"[cam_msk]format=yuv420p,geq=lum='clip(255*(1-(hypot((X-{cx})/{rx},(Y-{cy})/{ry})-0.65)/0.35),0,255)'[cam_mask]"
        )
        steps.append(f"[cam_blurred][cam_fg][cam_mask]maskedmerge[cam_proc]")
        proc_label = "cam_proc"

    elif mode == "transparent":
        f_scale = {"subtle": 0.9, "medium": 1.0, "strong": 1.15}.get(strength, 1.0)
        eff_rx = max(10, int(rx * f_scale))
        eff_ry = max(10, int(ry * f_scale))
        steps.append(
            f"[cam_raw]format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
            f"a='clip(255*(1-(hypot((X-{cx})/{eff_rx},(Y-{cy})/{eff_ry})-0.65)/0.35),0,255)'[cam_proc]"
        )
        proc_label = "cam_proc"

    elif mode == "chromakey":
        sim, blend = {
            "subtle": (0.25, 0.08),
            "medium": (0.32, 0.12),
            "strong": (0.40, 0.16),
        }.get(strength, (0.32, 0.12))
        steps.append(f"[cam_raw]format=rgba,colorkey=0x00FF00:{sim}:{blend}[cam_proc]")
        proc_label = "cam_proc"

    elif mode == "bluekey":
        sim, blend = {
            "subtle": (0.25, 0.08),
            "medium": (0.32, 0.12),
            "strong": (0.40, 0.16),
        }.get(strength, (0.32, 0.12))
        steps.append(f"[cam_raw]format=rgba,colorkey=0x0000FF:{sim}:{blend}[cam_proc]")
        proc_label = "cam_proc"

    elif mode == "aurora":
        steps.append(f"gradients=s={cw}x{ch}:c0=0x2b1055:c1=0x0b1f3a:r={fps}[aurora_bg]")
        steps.append(
            f"[cam_raw]format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
            f"a='clip(255*(1-(hypot((X-{cx})/{rx},(Y-{cy})/{ry})-0.65)/0.35),0,255)'[cam_fg_cut]"
        )
        steps.append(f"[aurora_bg][cam_fg_cut]overlay=format=auto:shortest=1[cam_proc]")
        proc_label = "cam_proc"

    else:  # original
        proc_label = "cam_raw"

    # 形狀與外框處理
    if pip_shape == "circle":
        r = pip_size // 2
        b = 4 if border_rgb else 0
        r_in = r - b
        if border_rgb:
            br, bg, bb = border_rgb
            steps.append(
                f"[{proc_label}]format=rgba,"
                f"geq=r='if(gt((X-{r})*(X-{r})+(Y-{r})*(Y-{r}), {r_in*r_in}), {br}, r(X,Y))':"
                f"g='if(gt((X-{r})*(X-{r})+(Y-{r})*(Y-{r}), {r_in*r_in}), {bg}, g(X,Y))':"
                f"b='if(gt((X-{r})*(X-{r})+(Y-{r})*(Y-{r}), {r_in*r_in}), {bb}, b(X,Y))':"
                f"a='if(gt((X-{r})*(X-{r})+(Y-{r})*(Y-{r}), {r*r}), 0, if(gt((X-{r})*(X-{r})+(Y-{r})*(Y-{r}), {r_in*r_in}), 255, alpha(X,Y)))'[cam]"
            )
        else:
            steps.append(
                f"[{proc_label}]format=rgba,"
                f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
                f"a='if(lte((X-{r})*(X-{r})+(Y-{r})*(Y-{r}), {r*r}), alpha(X,Y), 0)'[cam]"
            )
    else:  # rect
        if border_rgb:
            br, bg, bb = border_rgb
            hex_color = f"0x{br:02X}{bg:02X}{bb:02X}"
            steps.append(
                f"[{proc_label}]format=rgba,drawbox=x=0:y=0:w=iw:h=ih:color={hex_color}@1:t=4[cam]"
            )
        else:
            steps.append(f"[{proc_label}]format=rgba[cam]")

    return steps


_VT_FLAGS = {}


def _videotoolbox_speed_flags(ffmpeg_bin):
    cached = _VT_FLAGS.get(ffmpeg_bin)
    if cached is not None:
        return cached
    flags = []
    try:
        res = subprocess.run(
            [ffmpeg_bin, "-h", "encoder=h264_videotoolbox"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="ignore",
            timeout=5,
        )
        text = res.stdout or ""
        if "-realtime" in text:
            flags += ["-realtime", "1"]
        if "prio_speed" in text:
            flags += ["-prio_speed", "1"]
        if "-constant_bit_rate" in text:
            flags += ["-constant_bit_rate", "1"]
    except Exception:
        pass
    _VT_FLAGS[ffmpeg_bin] = flags
    return flags


def video_encode_args(ffmpeg_bin, use_hardware, bitrate_k, profile="balanced", quality="standard"):
    """即時錄影用的編碼參數。文書電腦留一半 CPU 給別的程式。"""
    threads = encode_threads(profile)
    enc = detect_best_video_encoder(ffmpeg_bin) if use_hardware else "libx264"
    rate = f"{int(bitrate_k)}k"
    shift = {"economy": 4, "high": -4}.get(quality, 0)

    def level(base):
        return str(max(16, min(40, int(base) + shift)))

    if enc == "h264_videotoolbox":
        return ["-c:v", "h264_videotoolbox", "-b:v", rate, "-pix_fmt", "yuv420p", *_videotoolbox_speed_flags(ffmpeg_bin)]
    if enc == "h264_nvenc":
        preset = "p1" if profile != "high" else "p4"
        cq = "30" if profile == "light" else "26"
        return ["-c:v", "h264_nvenc", "-preset", preset, "-cq", level(cq), "-b:v", rate, "-pix_fmt", "yuv420p"]
    if enc == "h264_qsv":
        base = "32" if profile == "light" else "26"
        return ["-c:v", "h264_qsv", "-global_quality", level(base), "-pix_fmt", "nv12"]
    if enc == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "speed", "-b:v", rate, "-pix_fmt", "yuv420p"]
    preset = "ultrafast" if profile != "high" else "veryfast"
    crf = "32" if profile == "light" else ("28" if profile == "balanced" else "24")
    return [
        "-c:v", "libx264",
        "-preset", preset,
        "-tune", "zerolatency",
        "-crf", level(crf),
        "-maxrate", rate,
        "-bufsize", f"{int(bitrate_k) * 2}k",
        "-threads", str(threads),
        "-pix_fmt", "yuv420p",
    ]


_WINDOW_GEOM = re.compile(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$")
_awake_proc = None
_awake_windows = False


def fit_window_geometry(spec, screen_w, screen_h, min_w=520, min_h=700):
    """把記住的視窗拉回螢幕裡。不合法則回傳 None。"""
    if not isinstance(spec, str):
        return None
    match = _WINDOW_GEOM.match(spec.strip())
    if not match:
        return None
    try:
        screen_w = int(screen_w)
        screen_h = int(screen_h)
    except (TypeError, ValueError):
        return None
    if screen_w < 320 or screen_h < 240:
        return None
    width, height, x, y = (int(v) for v in match.groups())
    width = min(max(width, min(min_w, screen_w)), screen_w)
    height = min(max(height, min(min_h, screen_h)), screen_h)
    if x + 80 > screen_w:
        x = max(0, screen_w - width)
    if y + 80 > screen_h:
        y = max(0, screen_h - height)
    return f"{width}x{height}+{max(0, x)}+{max(0, y)}"


def hold_awake(pid):
    """錄影這段時間不要讓螢幕或系統睡著。"""
    release_awake()
    global _awake_proc, _awake_windows
    try:
        if IS_WINDOWS:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
            _awake_windows = True
            return
        if IS_MAC and shutil.which("caffeinate"):
            _awake_proc = subprocess.Popen(
                ["caffeinate", "-dims", "-w", str(int(pid))],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        inhibit = shutil.which("systemd-inhibit")
        if inhibit:
            _awake_proc = subprocess.Popen(
                [inhibit, "--what=idle:sleep", "--who=AURA REC", "--why=正在錄影", "sleep", "infinity"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


def release_awake():
    """錄影結束就恢復原本的睡眠。"""
    global _awake_proc, _awake_windows
    proc = _awake_proc
    _awake_proc = None
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass
    if _awake_windows:
        _awake_windows = False
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        except Exception:
            pass


def lower_process_priority(pid):
    """錄影行程讓路，文書軟體才不會被拖卡。"""
    try:
        if IS_WINDOWS:
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x0200, False, int(pid))
            if handle:
                ctypes.windll.kernel32.SetPriorityClass(handle, 0x00004000)
                ctypes.windll.kernel32.CloseHandle(handle)
        else:
            subprocess.run(
                ["renice", "-n", "10", "-p", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


def explain_ffmpeg_failure(tail, code=None):
    """把 FFmpeg 最後幾行錯誤翻成使用者看得懂的話。"""
    text = (tail or "").strip()
    lower = text.lower()
    extra = ""
    if code == "missing" and not text:
        text = "找不到 FFmpeg。"
        lower = text.lower()
    if any(token in lower for token in ("not authorized", "operation not permitted", "permission denied")):
        if IS_MAC:
            extra = "\n\n請打開「系統設定 → 隱私權與安全性 → 螢幕錄製」，允許「終端機」或「AURA REC」，然後重新開啟程式。"
        else:
            extra = "\n\n系統拒絕了螢幕或音訊的存取，請在隱私設定裡允許這個程式。"
    elif "no such file" in lower or code == "missing":
        if IS_MAC:
            extra = "\n\n請先安裝 FFmpeg：brew install ffmpeg"
        elif IS_WINDOWS:
            extra = "\n\n請先安裝 FFmpeg：winget install Gyan.FFmpeg"
        else:
            extra = "\n\n請先安裝 FFmpeg，並確認終端機打得出 ffmpeg。"
    body = text or (f"FFmpeg 已結束（代碼 {code}）。" if code is not None else "FFmpeg 已結束。")
    return body + extra


def check_windows_modern_capture_support(ffmpeg_bin=None):
    """
    檢測 Windows 系統與 FFmpeg 是否支援現代 Direct3D 11 / WGC (ddagrab) 高速低負載桌面擷取。
    相容 Windows 10/11，支援 60/120 FPS 錄製，大幅降低 CPU 負載。
    """
    if not IS_WINDOWS:
        return False
    ffmpeg_bin = ffmpeg_bin or find_executable("ffmpeg")
    if not ffmpeg_bin or not os.path.exists(ffmpeg_bin):
        return False
    try:
        res = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-filters"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="ignore",
            timeout=4,
        )
        return "ddagrab" in (res.stdout or "")
    except Exception:
        return False


def get_system_diagnostics(ffmpeg_bin=None):
    """
    彙整系統硬體環境、FFmpeg 版本、支援之硬體加速編碼器與診斷資料
    """
    ffmpeg_bin = ffmpeg_bin or find_executable("ffmpeg")
    info = {
        "app_version": APP_VERSION,
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python": platform.python_version(),
        "cpu_count": os.cpu_count() or 0,
        "ram_gb": round(system_memory_gb(), 1),
        "machine_profile": machine_profile(),
        "ffmpeg_path": str(ffmpeg_bin) if ffmpeg_bin else "未找到",
        "ffmpeg_version": "未知",
        "hardware_encoders": [],
        "active_encoder": "未指定",
    }
    if ffmpeg_bin and os.path.exists(ffmpeg_bin):
        try:
            res = subprocess.run(
                [ffmpeg_bin, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                errors="ignore",
                timeout=4,
            )
            first_line = (res.stdout or "").splitlines()
            if first_line:
                info["ffmpeg_version"] = first_line[0]
        except Exception:
            pass

        try:
            res = subprocess.run(
                [ffmpeg_bin, "-encoders"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                errors="ignore",
                timeout=4,
            )
            encoders_out = res.stdout or ""
            supported = []
            candidates = [
                ("h264_videotoolbox", "Apple Silicon / Mac GPU VideoToolbox 硬體加速"),
                ("hevc_videotoolbox", "Apple Silicon HEVC VideoToolbox 硬體加速"),
                ("h264_nvenc", "NVIDIA NVENC 硬體加速"),
                ("hevc_nvenc", "NVIDIA HEVC NVENC 硬體加速"),
                ("h264_qsv", "Intel QuickSync (QSV) 硬體加速"),
                ("h264_amf", "AMD AMF 硬體加速"),
                ("libx264", "x264 (CPU 多核心軟體編碼)"),
            ]
            for code, desc in candidates:
                if code in encoders_out:
                    supported.append(f"{code} ({desc})")
            info["hardware_encoders"] = supported
        except Exception:
            pass

        info["active_encoder"] = detect_best_video_encoder(ffmpeg_bin)

        if IS_WINDOWS:
            wgc_ok = check_windows_modern_capture_support(ffmpeg_bin)
            info["win_capture_engine"] = "Direct3D 11 / WGC (ddagrab 支援 60/120 FPS 高幀率)" if wgc_ok else "傳統 GDI Grab (相容模式)"

    return info

