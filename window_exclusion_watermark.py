"""
視窗排除與浮水印保護模組 (Window Exclusion & Watermark Protection)
==================================================================
提供兩大核心安全與版權保護能力：
1. 視窗排除與隱私遮罩保護 (Window Exclusion & Privacy Shield)
   - 原生作業系統級自身視窗錄影穿透排除：
     * macOS: 透過 Objective-C Runtime 設定 NSWindowSharingNone (0)，使控制視窗對錄影引擎完全隱形，但使用者肉眼仍可正常操作。
     * Windows: 透過 User32 SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE = 0x11) 達成硬體級錄影排除。
   - 第三方指定視窗 / 敏感應用程式排除：
     * 支援勾選目前桌面已開啟之任意視窗（如 LINE、Slack、1Password、無痕瀏覽器）進行錄影自動模糊遮蔽或實體隱私盾牌遮蓋。
     * 支援敏感關鍵字自動偵測（密碼、Keychain、1Password、銀行、私密對話等）。

2. 智慧浮水印版權保護引擎 (Watermark Protection Engine)
   - 零外部相依性之高解析度 RGBA PNG 浮水印渲染器（macOS 原生 CoreText 抗鋸齒中英文字體 + 跨平台純 Python 點陣字型雙引擎回退）。
   - 支援 5 種浮水印模式：
     * corner: 角落品牌簽名浮水印（右下、左下、右上、左上、正中）
     * timestamp: 錄影日期時間與版權簽章浮水印
     * tiled: 滿版標示斜紋平鋪網格浮水印（防止局部裁切盜錄）
     * floating: 動態巡航漂浮標示浮水印（隨時間 Lissajous 曲線平滑移動，防止固定位置抹除）
     * image: 自訂 PNG/JPG 品牌 Logo 圖片浮水印
   - 相容 FFmpeg -filter_complex 與 -vf（使用 movie 濾鏡載入，不影響既有音視訊輸入索引）。
"""

import ctypes
import hashlib
import math
import os
import struct
import tempfile
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import zlib

from platform_utils import IS_LINUX, IS_MAC, IS_WINDOWS
from region_picker import box_to_points, list_capture_windows

# 預設敏感應用程式與視窗標題關鍵字
DEFAULT_SENSITIVE_KEYWORDS = [
    "1password",
    "bitwarden",
    "keychain",
    "鑰匙圈",
    "密碼",
    "password",
    "line",
    "wechat",
    "微信",
    "telegram",
    "slack",
    "discord",
    "signal",
    "whatsapp",
    "private",
    "無痕",
    "incognito",
    "隱私",
    "bank",
    "銀行",
    "機密",
    "confidential",
]

WATERMARK_MODES = [
    ("關閉浮水印 (Off)", "none"),
    ("角落品牌簽名 (Corner Badge)", "corner"),
    ("錄影時間戳記簽章 (Timestamp)", "timestamp"),
    ("動態巡航標示浮水印 (Floating Attribution)", "floating"),
    ("滿版標示網格浮水印 (Tiled Grid)", "tiled"),
    ("自訂 Logo 圖片浮水印 (Custom Logo)", "image"),
]

WATERMARK_POSITIONS = [
    ("右下角 (Bottom-Right)", "bottom-right"),
    ("左下角 (Bottom-Left)", "bottom-left"),
    ("右上角 (Top-Right)", "top-right"),
    ("左上角 (Top-Left)", "top-left"),
    ("畫面正中央 (Center)", "center"),
]

WATERMARK_STYLES = [
    ("極光青霓虹膠囊 (Aurora Cyan)", "aurora"),
    ("純白防偽陰影字 (Pure White)", "white"),
    ("尊爵琥珀金標章 (Amber Gold)", "gold"),
    ("機密警示紅標章 (Confidential Red)", "crimson"),
    ("極簡半透明標示浮印 (Subtle Ghost)", "subtle"),
]

WATERMARK_OPACITIES = [
    ("標準 (55%)", "medium"),
    ("微浮印 (28%)", "subtle"),
    ("醒目 (85%)", "strong"),
]

EXCLUSION_MASK_MODES = [
    ("高斯景深模糊遮蔽 (Gaussian Blur)", "blur"),
    ("像素馬賽克遮蔽 (Pixel Mosaic)", "mosaic"),
    ("深色隱私盾牌遮蓋 (Dark Shield)", "shield"),
]


# ==============================================================================
# 1. 作業系統原生視窗錄影穿透排除 (OS-Level Window Capture Exclusion)
# ==============================================================================

def set_window_excluded_from_capture(tk_win=None, exclude=True):
    """
    將本程式之視窗設定為「螢幕錄影不可見 (Excluded from Capture)」。
    使用者在螢幕上仍可正常看見並點擊視窗，但錄影畫面中該視窗會完全透明穿透。
    回傳 bool 代表是否成功套用原生 API。
    """
    if IS_MAC:
        return _mac_set_app_windows_sharing_type(exclude=exclude)
    if IS_WINDOWS and tk_win is not None:
        return _win_set_window_display_affinity(tk_win, exclude=exclude)
    return False


def _mac_set_app_windows_sharing_type(exclude=True):
    """
    macOS: 透過 Objective-C Runtime 將 NSApplication 下所有 NSWindow 的
    sharingType 設為 NSWindowSharingNone (0) 或 NSWindowSharingReadOnly (1)。
    """
    try:
        ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AppKit.framework/AppKit")
        objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")

        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        msg_ptr = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(("objc_msgSend", objc))
        msg_cnt = ctypes.CFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)(("objc_msgSend", objc))
        msg_idx = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)(("objc_msgSend", objc))
        msg_set = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)(("objc_msgSend", objc))

        cls_app = objc.objc_getClass(b"NSApplication")
        if not cls_app:
            return False

        sel_shared = objc.sel_registerName(b"sharedApplication")
        sel_windows = objc.sel_registerName(b"windows")
        sel_count = objc.sel_registerName(b"count")
        sel_obj = objc.sel_registerName(b"objectAtIndex:")
        sel_set_share = objc.sel_registerName(b"setSharingType:")

        app = msg_ptr(cls_app, sel_shared)
        if not app:
            return False

        win_array = msg_ptr(app, sel_windows)
        if not win_array:
            return False

        count = int(msg_cnt(win_array, sel_count))
        # NSWindowSharingNone = 0, NSWindowSharingReadOnly = 1
        sharing_val = 0 if exclude else 1
        for i in range(count):
            ns_win = msg_idx(win_array, sel_obj, i)
            if ns_win:
                msg_set(ns_win, sel_set_share, sharing_val)
        return count > 0
    except Exception:
        return False


def _win_set_window_display_affinity(tk_win, exclude=True):
    """
    Windows 10 (2004+) / Windows 11:
    呼叫 SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE = 0x11)
    讓視窗從 WGC / DWM / GDI 螢幕錄製中完全隱形。
    """
    try:
        user32 = ctypes.windll.user32
        hwnd = int(tk_win.winfo_id())
        parent = user32.GetParent(hwnd)
        target_hwnd = parent if parent else hwnd
        # WDA_NONE = 0x00, WDA_MONITOR = 0x01, WDA_EXCLUDEFROMCAPTURE = 0x11
        affinity = 0x00000011 if exclude else 0x00000000
        ok = bool(user32.SetWindowDisplayAffinity(target_hwnd, affinity))
        if not ok and exclude:
            ok = bool(user32.SetWindowDisplayAffinity(target_hwnd, 0x00000001))
        return ok
    except Exception:
        return False


# ==============================================================================
# 2. 第三方視窗與敏感應用排除偵測 (Third-Party Window Exclusion)
# ==============================================================================

def is_sensitive_window(owner="", title="", keywords=None):
    """判斷視窗所屬程式或標題是否符合敏感隱私關鍵字"""
    kw_list = keywords if keywords is not None else DEFAULT_SENSITIVE_KEYWORDS
    combined = f"{owner or ''} {title or ''}".lower()
    for kw in kw_list:
        k = str(kw or "").strip().lower()
        if k and k in combined:
            return True
    return False


def resolve_excluded_window_boxes(exclusion_config=None, screen_index=0):
    """
    根據 exclusion_config 掃描指定螢幕上的視窗，回傳需排除遮蔽之視窗清單：
    每一項為 dict: {"id", "owner", "title", "box": (x, y, w, h)} (擷取像素座標)
    """
    if not exclusion_config or not exclusion_config.get("enabled"):
        return []

    excluded_ids = set()
    for wid in exclusion_config.get("excluded_window_ids") or []:
        try:
            excluded_ids.add(int(wid))
        except (TypeError, ValueError):
            pass

    excluded_owners = {
        str(o).strip().lower()
        for o in (exclusion_config.get("excluded_owners") or [])
        if str(o).strip()
    }
    auto_sensitive = bool(exclusion_config.get("auto_sensitive", False))
    custom_kw_str = str(exclusion_config.get("custom_keywords") or "").strip()
    keywords = list(DEFAULT_SENSITIVE_KEYWORDS)
    if custom_kw_str:
        for part in custom_kw_str.replace("，", ",").split(","):
            p = part.strip().lower()
            if p and p not in keywords:
                keywords.append(p)

    matched = []
    windows = list_capture_windows(screen_index)
    for win in windows:
        wid = win.get("id")
        owner = str(win.get("owner") or "").strip()
        title = str(win.get("title") or "").strip()
        box = win.get("box")
        if not box or len(box) != 4:
            continue

        hit = False
        if wid in excluded_ids:
            hit = True
        elif owner.lower() in excluded_owners:
            hit = True
        elif auto_sensitive and is_sensitive_window(owner, title, keywords):
            hit = True

        if hit:
            matched.append({
                "id": wid,
                "owner": owner,
                "title": title,
                "box": tuple(int(v) for v in box),
            })
    return matched


def build_window_exclusion_filter_steps(
    base_label="0:v",
    excluded_boxes=None,
    mask_mode="blur",
    region=None,
):
    """
    將需排除之視窗區域 (x, y, w, h) 轉換為 FFmpeg 濾鏡步驟，在錄影串流中直接遮蔽該視窗。
    支援：
    - blur: 高斯/盒式重度模糊
    - mosaic: 馬賽克像素化遮蔽
    - shield: 深色極光隱私黑盒遮蓋
    回傳 (steps: list[str], out_label: str)
    """
    if not excluded_boxes:
        return [], base_label

    mode = str(mask_mode or "blur").lower()
    steps = []
    curr_label = base_label

    rx, ry, rw, rh = (0, 0, None, None)
    if region and len(region) == 4:
        rx, ry, rw, rh = [int(v) for v in region]

    valid_idx = 0
    for item in excluded_boxes[:6]:  # 最多同時處理前 6 個排除視窗以確保 60FPS 即時效能
        box = item.get("box") if isinstance(item, dict) else item
        if not box or len(box) != 4:
            continue
        x, y, w, h = [int(v) for v in box]

        # 若有局部區域裁切 (region)，換算為相對座標並求交集
        if rw is not None and rh is not None:
            x1 = max(x, rx)
            y1 = max(y, ry)
            x2 = min(x + w, rx + rw)
            y2 = min(y + h, ry + rh)
            x, y, w, h = x1 - rx, y1 - ry, x2 - x1, y2 - y1

        x = max(0, x - (x % 2))
        y = max(0, y - (y % 2))
        w = w - (w % 2)
        h = h - (h % 2)
        if w < 16 or h < 16:
            continue

        valid_idx += 1
        out_lbl = f"excl_{valid_idx}"

        if "shield" in mode or "dark" in mode or "盾" in mode:
            # 直接繪製深色隱私保護區塊與霓虹邊框
            steps.append(
                f"[{curr_label}]drawbox=x={x}:y={y}:w={w}:h={h}:color=0x0D0D12@0.96:t=fill,"
                f"drawbox=x={x}:y={y}:w={w}:h={h}:color=0x00F0FF@0.65:t=2[{out_lbl}]"
            )
        elif "mosaic" in mode or "馬賽克" in mode:
            sw = max(4, (w // 18) - ((w // 18) % 2))
            sh = max(4, (h // 18) - ((h // 18) % 2))
            steps.append(
                f"[{curr_label}]split=2[ex_base_{valid_idx}][ex_src_{valid_idx}];"
                f"[ex_src_{valid_idx}]crop={w}:{h}:{x}:{y},"
                f"scale={sw}:{sh}:flags=neighbor,scale={w}:{h}:flags=neighbor[ex_msk_{valid_idx}];"
                f"[ex_base_{valid_idx}][ex_msk_{valid_idx}]overlay={x}:{y}:format=auto[{out_lbl}]"
            )
        else:
            # 預設高斯/盒式重度模糊
            steps.append(
                f"[{curr_label}]split=2[ex_base_{valid_idx}][ex_src_{valid_idx}];"
                f"[ex_src_{valid_idx}]crop={w}:{h}:{x}:{y},boxblur=28:3[ex_msk_{valid_idx}];"
                f"[ex_base_{valid_idx}][ex_msk_{valid_idx}]overlay={x}:{y}:format=auto[{out_lbl}]"
            )
        curr_label = out_lbl

    return steps, curr_label


class PrivacyShieldOverlayManager:
    """
    在錄影期間於桌面上針對被排除的第三方視窗覆蓋一層「實體隱私保護盾牌視窗」，
    讓螢幕擷取不會拍到敏感視窗內容。
    """

    def __init__(self, root, exclusion_config=None, screen_index=0):
        self.root = root
        self.config = exclusion_config or {}
        self.screen_index = screen_index
        self.shields = []
        self.is_running = False

    def start(self):
        if not self.config or not self.config.get("enabled"):
            return
        if not self.config.get("desktop_shield", False):
            return
        self.stop()
        self.is_running = True
        matched = resolve_excluded_window_boxes(self.config, self.screen_index)
        for item in matched[:6]:
            pts = box_to_points(item["box"], self.screen_index)
            if not pts:
                continue
            px, py, pw, ph = [int(round(v)) for v in pts]
            if pw < 80 or ph < 50:
                continue
            try:
                win = tk.Toplevel(self.root)
                win.overrideredirect(True)
                win.configure(bg="#0d0d12")
                try:
                    win.attributes("-topmost", True)
                    win.attributes("-alpha", 0.96)
                except Exception:
                    pass
                win.geometry(f"{pw}x{ph}+{px}+{py}")

                frame = tk.Frame(
                    win,
                    bg="#0d0d12",
                    highlightbackground="#00f0ff",
                    highlightthickness=2,
                )
                frame.pack(fill=tk.BOTH, expand=True)

                title_str = item.get("owner") or "敏感視窗"
                tk.Label(
                    frame,
                    text=f"🔒 已啟用隱私視窗排除保護\n[{title_str}] 內容不會被錄入影片",
                    font=("SF Pro Text", 13, "bold") if IS_MAC else ("Segoe UI", 11, "bold"),
                    fg="#00f0ff",
                    bg="#0d0d12",
                    justify="center",
                ).place(relx=0.5, rely=0.5, anchor="center")

                self.shields.append(win)
            except Exception:
                pass

    def stop(self):
        self.is_running = False
        for win in self.shields:
            try:
                win.destroy()
            except Exception:
                pass
        self.shields.clear()


# ==============================================================================
# 3. 零相依性高解析度 PNG 浮水印渲染器 (Pure-Python + CoreText PNG Renderer)
# ==============================================================================

# 內建精簡 5x7 ASCII 點陣字庫 (供非 macOS 或無字體環境 100% 離線回退)
_MINI_FONT_5X7 = {
    "A": [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "B": [0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E],
    "C": [0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E],
    "D": [0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C],
    "E": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    "F": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
    "G": [0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F],
    "H": [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "I": [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "J": [0x07, 0x02, 0x02, 0x02, 0x12, 0x12, 0x0C],
    "K": [0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11],
    "L": [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    "M": [0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11],
    "N": [0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11],
    "O": [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "P": [0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10],
    "Q": [0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D],
    "R": [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    "S": [0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E],
    "T": [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    "U": [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "V": [0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04],
    "W": [0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11],
    "X": [0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11],
    "Y": [0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04],
    "Z": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F],
    "0": [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
    "1": [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "2": [0x0E, 0x11, 0x01, 0x06, 0x08, 0x10, 0x1F],
    "3": [0x1F, 0x02, 0x04, 0x06, 0x01, 0x11, 0x0E],
    "4": [0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02],
    "5": [0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E],
    "6": [0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E],
    "7": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08],
    "8": [0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E],
    "9": [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C],
    "-": [0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00],
    ":": [0x00, 0x04, 0x04, 0x00, 0x04, 0x04, 0x00],
    ".": [0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C],
    "@": [0x0E, 0x11, 0x17, 0x15, 0x17, 0x10, 0x0E],
    " ": [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
}


def _encode_rgba_png(width, height, rgba_bytes):
    """將 RGBA bytes (長度 width * height * 4) 編碼為標準 PNG 格式 bytes"""
    stride = width * 4
    raw_rows = bytearray()
    for y in range(height):
        raw_rows.append(0)  # Filter type 0 (None)
        offset = y * stride
        raw_rows.extend(rgba_bytes[offset:offset + stride])

    def make_chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw_rows), level=6)
    return (
        b"\x89PNG\r\n\x1a\n"
        + make_chunk(b"IHDR", ihdr)
        + make_chunk(b"IDAT", idat)
        + make_chunk(b"IEND", b"")
    )


def _render_text_mask_coretext(text, font_size=22):
    """
    macOS 專用：透過 CoreText + CoreGraphics 渲染抗鋸齒中英文文字遮罩。
    回傳 (width, height, gray_alpha_bytes) 或 None。
    """
    if not IS_MAC:
        return None
    try:
        cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        ct = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreText.framework/CoreText")

        UTF8 = 0x08000100
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFDictionaryCreate.restype = ctypes.c_void_p
        cf.CFDictionaryCreate.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
        ]
        cf.CFAttributedStringCreate.restype = ctypes.c_void_p
        cf.CFAttributedStringCreate.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        cf.CFRelease.argtypes = [ctypes.c_void_p]

        ct.CTFontCreateWithName.restype = ctypes.c_void_p
        ct.CTFontCreateWithName.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_void_p]
        ct.CTLineCreateWithAttributedString.restype = ctypes.c_void_p
        ct.CTLineCreateWithAttributedString.argtypes = [ctypes.c_void_p]
        ct.CTLineDraw.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        cg.CGColorSpaceCreateDeviceGray.restype = ctypes.c_void_p
        cg.CGBitmapContextCreate.restype = ctypes.c_void_p
        cg.CGBitmapContextCreate.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t,
            ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_uint32,
        ]
        cg.CGContextSetGrayFillColor.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double]
        cg.CGContextSetTextPosition.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double]
        cg.CGContextRelease.argtypes = [ctypes.c_void_p]
        cg.CGColorSpaceRelease.argtypes = [ctypes.c_void_p]

        # 估算文字寬高
        char_w = sum(font_size * (1.05 if ord(c) > 127 else 0.62) for c in text)
        pad_x = int(font_size * 1.1)
        pad_y = int(font_size * 0.7)
        w = max(80, int(char_w + pad_x * 2))
        w += w % 2
        h = max(36, int(font_size * 1.4 + pad_y * 2))
        h += h % 2

        buf = ctypes.create_string_buffer(w * h)
        cs = cg.CGColorSpaceCreateDeviceGray()
        ctx = cg.CGBitmapContextCreate(buf, w, h, 8, w, cs, 0)
        if not ctx:
            cg.CGColorSpaceRelease(cs)
            return None

        cg.CGContextSetGrayFillColor(ctx, 1.0, 1.0)

        k_font = ctypes.c_void_p.in_dll(ct, "kCTFontAttributeName")
        k_fg = ctypes.c_void_p.in_dll(ct, "kCTForegroundColorFromContextAttributeName")
        k_true = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")

        fname = cf.CFStringCreateWithCString(None, b"PingFangTC-Semibold", UTF8)
        font = ct.CTFontCreateWithName(fname, float(font_size), None)
        keys = (ctypes.c_void_p * 2)(k_font, k_fg)
        vals = (ctypes.c_void_p * 2)(font, k_true)
        attrs = cf.CFDictionaryCreate(None, keys, vals, 2, None, None)

        text_cf = cf.CFStringCreateWithCString(None, text.encode("utf-8"), UTF8)
        astr = cf.CFAttributedStringCreate(None, text_cf, attrs)
        line = ct.CTLineCreateWithAttributedString(astr)

        # CoreGraphics 座標原點在左下角，繪製後上下翻轉即為標準影像座標
        cg.CGContextSetTextPosition(ctx, float(pad_x), float(pad_y + font_size * 0.22))
        ct.CTLineDraw(line, ctx)

        raw = buf.raw
        # CGBitmapContext 的記憶體列順序已為由上而下，檢查是否有非零像素
        for ptr in (line, astr, text_cf, attrs, font, fname):
            if ptr:
                cf.CFRelease(ptr)
        cg.CGContextRelease(ctx)
        cg.CGColorSpaceRelease(cs)

        if not any(raw):
            return None
        return w, h, raw
    except Exception:
        return None


def _render_text_mask_fallback(text, scale=3):
    """純 Python 點陣字型回退渲染器，支援 ASCII 與非 ASCII 幾何圖騰字元"""
    clean = str(text or "AURA").upper()
    char_w = 6 * scale
    char_h = 7 * scale
    pad_x = 6 * scale
    pad_y = 4 * scale
    w = max(80, len(clean) * char_w + pad_x * 2)
    w += w % 2
    h = max(32, char_h + pad_y * 2)
    h += h % 2

    mask = bytearray(w * h)
    for idx, ch in enumerate(clean):
        ox = pad_x + idx * char_w
        oy = pad_y
        rows = _MINI_FONT_5X7.get(ch)
        if rows is None:
            # 非 ASCII 中文字元以精緻幾何印章格紋呈現
            h_code = ord(ch)
            rows = [
                0x1F,
                0x11 | ((h_code >> 1) & 0x0E),
                0x15,
                0x1F,
                0x15,
                0x11 | ((h_code >> 4) & 0x0E),
                0x1F,
            ]
        for r_i, bits in enumerate(rows):
            for c_i in range(5):
                if (bits >> (4 - c_i)) & 1:
                    for sy in range(scale):
                        for sx in range(scale):
                            px = ox + c_i * scale + sx
                            py = oy + r_i * scale + sy
                            if 0 <= px < w and 0 <= py < h:
                                mask[py * w + px] = 255
    return w, h, bytes(mask)


def render_watermark_png(
    output_path=None,
    text="極光錄影 Aura",
    style="aurora",
    opacity="medium",
    font_size=22,
    tiled=False,
    tile_w=1280,
    tile_h=720,
):
    """
    渲染高品質 RGBA PNG 浮水印圖片並寫入 output_path。
    回傳 output_path (str)。
    """
    if not output_path:
        h_key = hashlib.md5(f"{text}|{style}|{opacity}|{font_size}|{tiled}".encode("utf-8")).hexdigest()[:12]
        output_path = os.path.join(tempfile.gettempdir(), f"aura_watermark_{h_key}.png")

    op_map = {"subtle": 0.28, "medium": 0.58, "strong": 0.86}
    alpha_scale = op_map.get(str(opacity or "medium").lower(), 0.58)

    style_key = str(style or "aurora").lower()
    if "white" in style_key or "白" in style_key:
        fg_rgb = (255, 255, 255)
        bg_rgba = (12, 12, 18, int(140 * alpha_scale))
        border_rgb = (255, 255, 255)
        show_pill = True
    elif "gold" in style_key or "金" in style_key:
        fg_rgb = (251, 191, 36)
        bg_rgba = (20, 16, 10, int(185 * alpha_scale))
        border_rgb = (245, 158, 11)
        show_pill = True
    elif "crimson" in style_key or "red" in style_key or "紅" in style_key or "機密" in style_key:
        fg_rgb = (254, 202, 202)
        bg_rgba = (69, 10, 10, int(200 * alpha_scale))
        border_rgb = (239, 68, 68)
        show_pill = True
    elif "subtle" in style_key or "極簡" in style_key or tiled:
        fg_rgb = (240, 244, 255)
        bg_rgba = (0, 0, 0, 0)
        border_rgb = None
        show_pill = False
    else:  # aurora default
        fg_rgb = (0, 240, 255)
        bg_rgba = (13, 15, 23, int(185 * alpha_scale))
        border_rgb = (0, 240, 255)
        show_pill = True

    res = _render_text_mask_coretext(text, font_size=font_size)
    if res is None:
        res = _render_text_mask_fallback(text, scale=max(2, font_size // 8))
    w, h, mask = res

    badge_rgba = bytearray(w * h * 4)
    radius = min(w, h) // 2 if show_pill else 0

    for y in range(h):
        for x in range(w):
            idx = (y * w + x) * 4
            m_val = mask[y * w + x]

            # 膠囊圓角背景判定
            in_pill = True
            on_border = False
            if show_pill:
                if x < radius:
                    dx = radius - x
                elif x >= w - radius:
                    dx = x - (w - radius - 1)
                else:
                    dx = 0
                dy = y - (h // 2)
                dist = math.hypot(dx, dy)
                if dist > radius:
                    in_pill = False
                elif border_rgb and dist >= radius - 1.8:
                    on_border = True
            else:
                in_pill = False

            if m_val > 12:
                # 文字像素
                t_a = int(min(255, m_val * alpha_scale * 1.15))
                badge_rgba[idx] = fg_rgb[0]
                badge_rgba[idx + 1] = fg_rgb[1]
                badge_rgba[idx + 2] = fg_rgb[2]
                badge_rgba[idx + 3] = t_a
            elif on_border and border_rgb:
                badge_rgba[idx] = border_rgb[0]
                badge_rgba[idx + 1] = border_rgb[1]
                badge_rgba[idx + 2] = border_rgb[2]
                badge_rgba[idx + 3] = int(190 * alpha_scale)
            elif in_pill:
                # 檢查文字陰影 (右下方偏移 1px)
                sx, sy = x - 1, y - 1
                shadow_m = mask[sy * w + sx] if (0 <= sx < w and 0 <= sy < h) else 0
                if shadow_m > 30:
                    badge_rgba[idx] = 0
                    badge_rgba[idx + 1] = 0
                    badge_rgba[idx + 2] = 0
                    badge_rgba[idx + 3] = int(min(230, bg_rgba[3] + shadow_m * 0.5))
                else:
                    badge_rgba[idx] = bg_rgba[0]
                    badge_rgba[idx + 1] = bg_rgba[1]
                    badge_rgba[idx + 2] = bg_rgba[2]
                    badge_rgba[idx + 3] = bg_rgba[3]
            elif not show_pill:
                # 無膠囊底板時仍加上微弱文字黑邊陰影以提高可讀性
                sx, sy = x - 1, y - 1
                shadow_m = mask[sy * w + sx] if (0 <= sx < w and 0 <= sy < h) else 0
                if shadow_m > 40:
                    badge_rgba[idx] = 0
                    badge_rgba[idx + 1] = 0
                    badge_rgba[idx + 2] = 0
                    badge_rgba[idx + 3] = int(shadow_m * alpha_scale * 0.65)

    if not tiled:
        png_data = _encode_rgba_png(w, h, badge_rgba)
        with open(output_path, "wb") as f:
            f.write(png_data)
        return output_path

    # 滿版標示網格 (Tiled Grid): 將單一浮印交錯平鋪於透明畫布上
    tw = max(w * 2, int(tile_w))
    th = max(h * 2, int(tile_h))
    canvas_rgba = bytearray(tw * th * 4)
    step_x = max(w + 120, tw // 3)
    step_y = max(h + 100, th // 3)

    row_idx = 0
    for cy in range(40, th - h - 10, step_y):
        offset_x = 60 if (row_idx % 2 == 0) else (step_x // 2 + 40)
        for cx in range(offset_x, tw - w - 10, step_x):
            for by in range(h):
                src_off = by * w * 4
                dst_off = ((cy + by) * tw + cx) * 4
                canvas_rgba[dst_off:dst_off + w * 4] = badge_rgba[src_off:src_off + w * 4]
        row_idx += 1

    png_data = _encode_rgba_png(tw, th, canvas_rgba)
    with open(output_path, "wb") as f:
        f.write(png_data)
    return output_path


def _escape_ffmpeg_filter_path(file_path):
    """將檔案路徑轉義為 FFmpeg movie='...' 濾鏡安全字串"""
    p = str(file_path).replace("\\", "/")
    p = p.replace(":", "\\:").replace("'", "\\'")
    return p


def build_watermark_filter_steps(
    base_label="0:v",
    watermark_config=None,
    out_label="wm_out",
):
    """
    依據 watermark_config 產生 FFmpeg 浮水印疊加濾鏡步驟清單。
    watermark_config 結構:
      {
        "enabled": bool,
        "mode": "none" | "corner" | "timestamp" | "floating" | "tiled" | "image",
        "text": str,
        "position": "bottom-right" | "bottom-left" | "top-right" | "top-left" | "center",
        "style": "aurora" | "white" | "gold" | "crimson" | "subtle",
        "opacity": "subtle" | "medium" | "strong",
        "logo_path": str,
        "margin": int,
      }
    回傳 (steps: list[str], final_label: str)
    """
    if not watermark_config or not watermark_config.get("enabled"):
        return [], base_label

    mode = str(watermark_config.get("mode") or "corner").lower()
    if mode in ("none", "off", ""):
        return [], base_label

    text = str(watermark_config.get("text") or "極光錄影 Aura").strip() or "極光錄影 Aura"
    if mode == "timestamp":
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        text = f"{text} · {now_str}"

    pos = str(watermark_config.get("position") or "bottom-right").lower()
    style = str(watermark_config.get("style") or "aurora").lower()
    opacity = str(watermark_config.get("opacity") or "medium").lower()
    margin = int(watermark_config.get("margin") or 24)
    logo_path = str(watermark_config.get("logo_path") or "").strip()

    if mode == "image" and logo_path and os.path.exists(logo_path):
        png_path = logo_path
    elif mode == "tiled":
        png_path = render_watermark_png(
            text=text,
            style="subtle" if style == "aurora" else style,
            opacity=opacity,
            font_size=20,
            tiled=True,
            tile_w=1280,
            tile_h=720,
        )
    else:
        png_path = render_watermark_png(
            text=text,
            style=style,
            opacity=opacity,
            font_size=22,
            tiled=False,
        )

    esc_path = _escape_ffmpeg_filter_path(png_path)

    if mode == "floating":
        # 動態標示巡航曲線：平滑在畫面四處巡航且絕不超出邊界
        x_expr = "'(W-w)*(0.5+0.42*sin(t*0.65))'"
        y_expr = "'(H-h)*(0.5+0.42*cos(t*0.48))'"
        steps = [
            f"movie='{esc_path}',format=rgba[wm_src]",
            f"[{base_label}][wm_src]overlay=x={x_expr}:y={y_expr}:format=auto[{out_label}]",
        ]
        return steps, out_label

    if mode == "tiled":
        steps = [
            f"movie='{esc_path}',format=rgba[wm_src]",
            f"[{base_label}][wm_src]overlay=x='(W-w)/2':y='(H-h)/2':format=auto[{out_label}]",
        ]
        return steps, out_label

    pos_map = {
        "bottom-right": f"W-w-{margin}:H-h-{margin}",
        "bottom-left": f"{margin}:H-h-{margin}",
        "top-right": f"W-w-{margin}:{margin}",
        "top-left": f"{margin}:{margin}",
        "center": "(W-w)/2:(H-h)/2",
    }
    coords = pos_map.get(pos, f"W-w-{margin}:H-h-{margin}")

    if mode == "image":
        op_val = {"subtle": 0.35, "medium": 0.65, "strong": 0.92}.get(opacity, 0.65)
        steps = [
            f"movie='{esc_path}',scale=180:-1,format=rgba,"
            f"colorchannelmixer=aa={op_val}[wm_src]",
            f"[{base_label}][wm_src]overlay={coords}:format=auto[{out_label}]",
        ]
        return steps, out_label

    steps = [
        f"movie='{esc_path}',format=rgba[wm_src]",
        f"[{base_label}][wm_src]overlay={coords}:format=auto[{out_label}]",
    ]
    return steps, out_label


# ==============================================================================
# 4. 視窗排除與浮水印設定對話框 (GUI Dialog)
# ==============================================================================

class WindowExclusionWatermarkDialog:
    """
    視窗排除與浮水印保護設定面板。
    同時管理：
    1. 原生作業系統自身視窗穿透排除 + 第三方敏感視窗智慧模糊/盾牌排除
    2. 品牌簽名 / 時間戳 / 動態巡航標示 / 滿版網格 / Logo 浮水印與即時預覽
    """

    def __init__(self, parent, initial_exclusion=None, initial_watermark=None, screen_index=0, on_save=None):
        self.parent = parent
        self.screen_index = screen_index
        self.on_save = on_save
        self.excl_cfg = dict(initial_exclusion or {})
        self.wm_cfg = dict(initial_watermark or {})

        self.win = tk.Toplevel(parent)
        self.win.title("🛡️ 視窗排除與浮水印保護 (Window Exclusion & Watermark)")
        self.win.geometry("680x720")
        self.win.configure(bg="#09090b")
        self.win.transient(parent)

        self._preview_photo = None
        self._window_items = []
        self._selected_win_ids = set(int(x) for x in (self.excl_cfg.get("excluded_window_ids") or []) if str(x).isdigit())

        self._build_ui()
        self._refresh_window_list()
        try:
            from i18n import get_language, translate_widget_tree
            translate_widget_tree(self.win, get_language())
        except Exception:
            pass
        self._update_watermark_preview()

    def _build_ui(self):
        # 頂部標題列
        header = tk.Frame(self.win, bg="#121217", padx=18, pady=14)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text="🛡️ 視窗排除與浮水印版權保護中心",
            font=("SF Pro Display", 16, "bold") if IS_MAC else ("Segoe UI", 14, "bold"),
            fg="#f4f4f5",
            bg="#121217",
        ).pack(anchor="w")
        tk.Label(
            header,
            text="防止敏感對話或密碼外洩 · 為教學與商務錄影加上標示動態浮水印",
            font=("SF Pro Text", 11) if IS_MAC else ("Segoe UI", 9),
            fg="#a1a1aa",
            bg="#121217",
        ).pack(anchor="w", pady=(2, 0))

        body = tk.Frame(self.win, bg="#09090b", padx=16, pady=10)
        body.pack(fill=tk.BOTH, expand=True)

        # ---------------- 區塊 1: 視窗排除與隱私保護 ----------------
        excl_card = tk.Frame(body, bg="#141419", highlightbackground="#27272a", highlightthickness=1, padx=14, pady=10)
        excl_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            excl_card,
            text="🔒 1. 視窗排除與敏感應用保護 (Window Exclusion)",
            font=("SF Pro Text", 13, "bold") if IS_MAC else ("Segoe UI", 11, "bold"),
            fg="#00f0ff",
            bg="#141419",
        ).pack(anchor="w")

        self.excl_enabled_var = tk.BooleanVar(value=bool(self.excl_cfg.get("enabled", True)))
        self.self_exclude_var = tk.BooleanVar(value=bool(self.excl_cfg.get("exclude_self_window", True)))
        self.auto_sensitive_var = tk.BooleanVar(value=bool(self.excl_cfg.get("auto_sensitive", True)))
        self.desktop_shield_var = tk.BooleanVar(value=bool(self.excl_cfg.get("desktop_shield", False)))

        chk_frame = tk.Frame(excl_card, bg="#141419")
        chk_frame.pack(fill=tk.X, pady=(6, 4))

        tk.Checkbutton(
            chk_frame,
            text="啟用視窗隱私排除保護",
            variable=self.excl_enabled_var,
            bg="#141419", fg="#f4f4f5", selectcolor="#27272a", activebackground="#141419",
        ).grid(row=0, column=0, sticky="w", padx=(0, 14))

        tk.Checkbutton(
            chk_frame,
            text="自身錄影控制列硬體穿透隱藏 (OS Native)",
            variable=self.self_exclude_var,
            bg="#141419", fg="#f4f4f5", selectcolor="#27272a", activebackground="#141419",
        ).grid(row=0, column=1, sticky="w")

        tk.Checkbutton(
            chk_frame,
            text="自動偵測並遮蔽敏感應用 (LINE / 1Password / 密碼 / 無痕視窗)",
            variable=self.auto_sensitive_var,
            bg="#141419", fg="#f4f4f5", selectcolor="#27272a", activebackground="#141419",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

        tk.Checkbutton(
            chk_frame,
            text="錄影時於桌面顯示實體防窺盾牌覆蓋敏感視窗",
            variable=self.desktop_shield_var,
            bg="#141419", fg="#a1a1aa", selectcolor="#27272a", activebackground="#141419",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # 遮蔽樣式與關鍵字
        mask_row = tk.Frame(excl_card, bg="#141419")
        mask_row.pack(fill=tk.X, pady=(4, 4))

        tk.Label(mask_row, text="遮蔽方式:", fg="#a1a1aa", bg="#141419").pack(side=tk.LEFT)
        self.mask_mode_var = tk.StringVar()
        init_m = self.excl_cfg.get("mask_mode", "blur")
        default_m_label = EXCLUSION_MASK_MODES[0][0]
        for lbl, val in EXCLUSION_MASK_MODES:
            if val == init_m:
                default_m_label = lbl
        self.mask_mode_var.set(default_m_label)
        self.mask_combo = ttk.Combobox(
            mask_row, textvariable=self.mask_mode_var, state="readonly", width=26,
            values=[lbl for lbl, _ in EXCLUSION_MASK_MODES],
        )
        self.mask_combo.pack(side=tk.LEFT, padx=(6, 12))

        tk.Label(mask_row, text="自訂排除關鍵字:", fg="#a1a1aa", bg="#141419").pack(side=tk.LEFT)
        self.custom_kw_var = tk.StringVar(value=str(self.excl_cfg.get("custom_keywords") or ""))
        tk.Entry(
            mask_row, textvariable=self.custom_kw_var, bg="#1f1f26", fg="#f4f4f5",
            insertbackground="#00f0ff", relief=tk.FLAT, width=18,
        ).pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)

        # 目前桌面開啟視窗勾選清單
        list_hdr = tk.Frame(excl_card, bg="#141419")
        list_hdr.pack(fill=tk.X, pady=(4, 2))
        tk.Label(
            list_hdr, text="勾選要排除遮蔽的已開啟視窗 (點擊可多選):",
            fg="#a1a1aa", bg="#141419", font=("SF Pro Text", 10) if IS_MAC else ("Segoe UI", 9),
        ).pack(side=tk.LEFT)
        tk.Button(
            list_hdr, text="重新掃描視窗 ↻", command=self._refresh_window_list,
            bg="#27272a", fg="#f4f4f5", relief=tk.FLAT, padx=8, pady=1,
        ).pack(side=tk.RIGHT)

        self.win_listbox = tk.Listbox(
            excl_card, selectmode=tk.MULTIPLE, height=4,
            bg="#0d0d11", fg="#e4e4e7", selectbackground="#0284c7",
            highlightthickness=1, highlightbackground="#27272a", relief=tk.FLAT,
        )
        self.win_listbox.pack(fill=tk.X, pady=(2, 2))

        # ---------------- 區塊 2: 浮水印版權保護 ----------------
        wm_card = tk.Frame(body, bg="#141419", highlightbackground="#27272a", highlightthickness=1, padx=14, pady=10)
        wm_card.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            wm_card,
            text="💧 2. 智慧浮水印版權保護 (Watermark Protection)",
            font=("SF Pro Text", 13, "bold") if IS_MAC else ("Segoe UI", 11, "bold"),
            fg="#a855f7",
            bg="#141419",
        ).pack(anchor="w")

        wm_grid = tk.Frame(wm_card, bg="#141419")
        wm_grid.pack(fill=tk.X, pady=(6, 4))
        wm_grid.columnconfigure(1, weight=1)
        wm_grid.columnconfigure(3, weight=1)

        # Row 0: 模式、位置
        tk.Label(wm_grid, text="浮水印模式:", fg="#a1a1aa", bg="#141419").grid(row=0, column=0, sticky="w", pady=3)
        self.wm_mode_var = tk.StringVar()
        init_wm_mode = self.wm_cfg.get("mode", "none") if self.wm_cfg.get("enabled") else "none"
        mode_lbl = WATERMARK_MODES[0][0]
        for lbl, val in WATERMARK_MODES:
            if val == init_wm_mode:
                mode_lbl = lbl
        self.wm_mode_var.set(mode_lbl)
        self.wm_mode_combo = ttk.Combobox(
            wm_grid, textvariable=self.wm_mode_var, state="readonly",
            values=[lbl for lbl, _ in WATERMARK_MODES],
        )
        self.wm_mode_combo.grid(row=0, column=1, sticky="ew", padx=(6, 12), pady=3)

        tk.Label(wm_grid, text="顯示位置:", fg="#a1a1aa", bg="#141419").grid(row=0, column=2, sticky="w", pady=3)
        self.wm_pos_var = tk.StringVar()
        init_pos = self.wm_cfg.get("position", "bottom-right")
        pos_lbl = WATERMARK_POSITIONS[0][0]
        for lbl, val in WATERMARK_POSITIONS:
            if val == init_pos:
                pos_lbl = lbl
        self.wm_pos_var.set(pos_lbl)
        self.wm_pos_combo = ttk.Combobox(
            wm_grid, textvariable=self.wm_pos_var, state="readonly",
            values=[lbl for lbl, _ in WATERMARK_POSITIONS],
        )
        self.wm_pos_combo.grid(row=0, column=3, sticky="ew", padx=(6, 0), pady=3)

        # Row 1: 視覺樣式、透明度
        tk.Label(wm_grid, text="視覺風格:", fg="#a1a1aa", bg="#141419").grid(row=1, column=0, sticky="w", pady=3)
        self.wm_style_var = tk.StringVar()
        init_style = self.wm_cfg.get("style", "aurora")
        style_lbl = WATERMARK_STYLES[0][0]
        for lbl, val in WATERMARK_STYLES:
            if val == init_style:
                style_lbl = lbl
        self.wm_style_var.set(style_lbl)
        self.wm_style_combo = ttk.Combobox(
            wm_grid, textvariable=self.wm_style_var, state="readonly",
            values=[lbl for lbl, _ in WATERMARK_STYLES],
        )
        self.wm_style_combo.grid(row=1, column=1, sticky="ew", padx=(6, 12), pady=3)

        tk.Label(wm_grid, text="不透明度:", fg="#a1a1aa", bg="#141419").grid(row=1, column=2, sticky="w", pady=3)
        self.wm_opacity_var = tk.StringVar()
        init_op = self.wm_cfg.get("opacity", "medium")
        op_lbl = WATERMARK_OPACITIES[0][0]
        for lbl, val in WATERMARK_OPACITIES:
            if val == init_op:
                op_lbl = lbl
        self.wm_opacity_var.set(op_lbl)
        self.wm_opacity_combo = ttk.Combobox(
            wm_grid, textvariable=self.wm_opacity_var, state="readonly",
            values=[lbl for lbl, _ in WATERMARK_OPACITIES],
        )
        self.wm_opacity_combo.grid(row=1, column=3, sticky="ew", padx=(6, 0), pady=3)

        # Row 2: 浮水印文字
        tk.Label(wm_grid, text="浮水印文字:", fg="#a1a1aa", bg="#141419").grid(row=2, column=0, sticky="w", pady=3)
        self.wm_text_var = tk.StringVar(value=str(self.wm_cfg.get("text") or "© 極光錄影 Aura · 請勿外流"))
        text_entry = tk.Entry(
            wm_grid, textvariable=self.wm_text_var, bg="#1f1f26", fg="#f4f4f5",
            insertbackground="#00f0ff", relief=tk.FLAT,
        )
        text_entry.grid(row=2, column=1, columnspan=3, sticky="ew", padx=(6, 0), pady=3)
        text_entry.bind("<KeyRelease>", lambda _e: self._update_watermark_preview())

        # Row 3: 自訂圖片路徑
        tk.Label(wm_grid, text="自訂 Logo:", fg="#a1a1aa", bg="#141419").grid(row=3, column=0, sticky="w", pady=3)
        self.wm_logo_var = tk.StringVar(value=str(self.wm_cfg.get("logo_path") or ""))
        tk.Entry(
            wm_grid, textvariable=self.wm_logo_var, bg="#1f1f26", fg="#a1a1aa",
            insertbackground="#00f0ff", relief=tk.FLAT,
        ).grid(row=3, column=1, columnspan=2, sticky="ew", padx=(6, 6), pady=3)
        tk.Button(
            wm_grid, text="選擇 PNG 圖片...", command=self._pick_logo,
            bg="#27272a", fg="#f4f4f5", relief=tk.FLAT, padx=8,
        ).grid(row=3, column=3, sticky="ew", pady=3)

        for cb in (self.wm_mode_combo, self.wm_pos_combo, self.wm_style_combo, self.wm_opacity_combo):
            cb.bind("<<ComboboxSelected>>", lambda _e: self._update_watermark_preview())

        # 浮水印即時預覽畫布
        tk.Label(
            wm_card, text="即時浮水印效果預覽:", fg="#a1a1aa", bg="#141419",
            font=("SF Pro Text", 10) if IS_MAC else ("Segoe UI", 9),
        ).pack(anchor="w", pady=(6, 2))

        self.preview_canvas = tk.Canvas(
            wm_card, width=600, height=110, bg="#0b0c12",
            highlightthickness=1, highlightbackground="#27272a",
        )
        self.preview_canvas.pack(fill=tk.X, pady=(0, 4))

        # 底部操作按鈕
        footer = tk.Frame(self.win, bg="#121217", padx=18, pady=12)
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        tk.Button(
            footer, text="取消", command=self.win.destroy,
            bg="#27272a", fg="#f4f4f5", relief=tk.FLAT, padx=16, pady=6,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        tk.Button(
            footer, text="套用並儲存保護設定 ✓", command=self._save_and_close,
            bg="#0284c7", fg="#ffffff", relief=tk.FLAT, padx=18, pady=6,
            font=("SF Pro Text", 11, "bold") if IS_MAC else ("Segoe UI", 10, "bold"),
        ).pack(side=tk.RIGHT)

    def _refresh_window_list(self):
        self.win_listbox.delete(0, tk.END)
        self._window_items = list_capture_windows(self.screen_index)
        for idx, w in enumerate(self._window_items):
            wid = w.get("id")
            owner = w.get("owner") or "視窗"
            title = w.get("title") or ""
            sens = is_sensitive_window(owner, title)
            tag = " [⚠️ 敏感應用]" if sens else ""
            disp = f"[{owner}] {title}{tag}" if title else f"[{owner}]{tag}"
            self.win_listbox.insert(tk.END, disp)
            if wid in self._selected_win_ids:
                self.win_listbox.selection_set(idx)

    def _pick_logo(self):
        path = filedialog.askopenfilename(
            parent=self.win,
            title="選擇浮水印 Logo 圖片",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp"), ("All Files", "*.*")],
        )
        if path:
            self.wm_logo_var.set(path)
            self.wm_mode_var.set(WATERMARK_MODES[5][0])
            self._update_watermark_preview()

    def _collect_configs(self):
        # 收集視窗排除設定
        sel_indices = self.win_listbox.curselection()
        sel_ids = []
        sel_owners = []
        for idx in sel_indices:
            if 0 <= idx < len(self._window_items):
                item = self._window_items[idx]
                sel_ids.append(item["id"])
                if item.get("owner"):
                    sel_owners.append(item["owner"])

        mask_val = "blur"
        m_idx = self.mask_combo.current()
        if 0 <= m_idx < len(EXCLUSION_MASK_MODES):
            mask_val = EXCLUSION_MASK_MODES[m_idx][1]
        else:
            for lbl, val in EXCLUSION_MASK_MODES:
                if lbl == self.mask_mode_var.get():
                    mask_val = val
                    break

        excl = {
            "enabled": bool(self.excl_enabled_var.get()),
            "exclude_self_window": bool(self.self_exclude_var.get()),
            "auto_sensitive": bool(self.auto_sensitive_var.get()),
            "desktop_shield": bool(self.desktop_shield_var.get()),
            "mask_mode": mask_val,
            "custom_keywords": self.custom_kw_var.get().strip(),
            "excluded_window_ids": sel_ids,
            "excluded_owners": sel_owners,
        }

        # 收集浮水印設定
        wm_mode = "none"
        wm_m_idx = self.wm_mode_combo.current()
        if 0 <= wm_m_idx < len(WATERMARK_MODES):
            wm_mode = WATERMARK_MODES[wm_m_idx][1]
        else:
            for lbl, val in WATERMARK_MODES:
                if lbl == self.wm_mode_var.get():
                    wm_mode = val
                    break

        wm_pos = "bottom-right"
        wm_p_idx = self.wm_pos_combo.current()
        if 0 <= wm_p_idx < len(WATERMARK_POSITIONS):
            wm_pos = WATERMARK_POSITIONS[wm_p_idx][1]
        else:
            for lbl, val in WATERMARK_POSITIONS:
                if lbl == self.wm_pos_var.get():
                    wm_pos = val
                    break

        wm_style = "aurora"
        wm_s_idx = self.wm_style_combo.current()
        if 0 <= wm_s_idx < len(WATERMARK_STYLES):
            wm_style = WATERMARK_STYLES[wm_s_idx][1]
        else:
            for lbl, val in WATERMARK_STYLES:
                if lbl == self.wm_style_var.get():
                    wm_style = val
                    break

        wm_op = "medium"
        wm_o_idx = self.wm_opacity_combo.current()
        if 0 <= wm_o_idx < len(WATERMARK_OPACITIES):
            wm_op = WATERMARK_OPACITIES[wm_o_idx][1]
        else:
            for lbl, val in WATERMARK_OPACITIES:
                if lbl == self.wm_opacity_var.get():
                    wm_op = val
                    break

        wm = {
            "enabled": wm_mode != "none",
            "mode": wm_mode,
            "position": wm_pos,
            "style": wm_style,
            "opacity": wm_op,
            "text": self.wm_text_var.get().strip() or "© 極光錄影 Aura",
            "logo_path": self.wm_logo_var.get().strip(),
            "margin": 24,
        }
        return excl, wm

    def _update_watermark_preview(self):
        self.preview_canvas.delete("all")
        _excl, wm = self._collect_configs()
        cw = 600
        ch = 110

        # 繪製深色模擬桌面背景格線
        for gx in range(0, cw, 40):
            self.preview_canvas.create_line(gx, 0, gx, ch, fill="#161822")
        for gy in range(0, ch, 30):
            self.preview_canvas.create_line(0, gy, cw, gy, fill="#161822")

        if not wm["enabled"]:
            self.preview_canvas.create_text(
                cw // 2, ch // 2,
                text="目前未啟用浮水印 (選擇上方模式即可預覽效果)",
                fill="#71717a",
                font=("SF Pro Text", 11) if IS_MAC else ("Segoe UI", 10),
            )
            return

        try:
            disp_text = wm["text"]
            if wm["mode"] == "timestamp":
                disp_text = f"{disp_text} · {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            png_path = render_watermark_png(
                text=disp_text,
                style=wm["style"],
                opacity=wm["opacity"],
                font_size=18,
                tiled=(wm["mode"] == "tiled"),
                tile_w=cw,
                tile_h=ch,
            )
            self._preview_photo = tk.PhotoImage(file=png_path)
            if wm["mode"] == "tiled":
                self.preview_canvas.create_image(cw // 2, ch // 2, image=self._preview_photo)
            elif wm["mode"] == "floating":
                self.preview_canvas.create_image(cw // 2, ch // 2 - 8, image=self._preview_photo)
                self.preview_canvas.create_text(
                    cw // 2, ch - 16,
                    text="↝ 錄影時將於畫面四周平滑巡航移動，防止固定位置裁切抹除",
                    fill="#00f0ff",
                    font=("SF Pro Text", 9) if IS_MAC else ("Segoe UI", 8),
                )
            else:
                pos = wm["position"]
                pos_xy = {
                    "bottom-right": (cw - 16, ch - 14, "se"),
                    "bottom-left": (16, ch - 14, "sw"),
                    "top-right": (cw - 16, 14, "ne"),
                    "top-left": (16, 14, "nw"),
                    "center": (cw // 2, ch // 2, "center"),
                }
                px, py, anc = pos_xy.get(pos, (cw - 16, ch - 14, "se"))
                self.preview_canvas.create_image(px, py, image=self._preview_photo, anchor=anc)
        except Exception as e:
            self.preview_canvas.create_text(
                cw // 2, ch // 2, text=f"預覽載入中 ({e})", fill="#a1a1aa"
            )

    def _save_and_close(self):
        excl, wm = self._collect_configs()
        if callable(self.on_save):
            self.on_save(excl, wm)
        self.win.destroy()
