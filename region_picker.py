#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""拖曳選取範圍，或改錄畫面上的某一個視窗。座標換成擷取用的像素。"""

import os
import re
import tkinter as tk

from aura_widgets import AuraButton
from platform_utils import IS_LINUX, IS_MAC, IS_WINDOWS, UI, get_ui_fonts


def _mac_pixel_scale(display_id):
    """視窗開啟後 AppKit 的倍率會變成 1，改問螢幕模式才對得上錄影像素。"""
    import ctypes

    cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cg.CGDisplayCopyDisplayMode.argtypes = [ctypes.c_uint32]
    cg.CGDisplayCopyDisplayMode.restype = ctypes.c_void_p
    cg.CGDisplayModeGetPixelWidth.argtypes = [ctypes.c_void_p]
    cg.CGDisplayModeGetPixelWidth.restype = ctypes.c_size_t
    cg.CGDisplayModeGetWidth.argtypes = [ctypes.c_void_p]
    cg.CGDisplayModeGetWidth.restype = ctypes.c_size_t
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    mode = cg.CGDisplayCopyDisplayMode(ctypes.c_uint32(int(display_id)))
    if not mode:
        return 1.0
    try:
        points = int(cg.CGDisplayModeGetWidth(mode))
        pixels = int(cg.CGDisplayModeGetPixelWidth(mode))
    finally:
        cf.CFRelease(mode)
    if points <= 0 or pixels <= 0:
        return 1.0
    return max(1.0, pixels / points)


def display_scale():
    """點轉成螢幕像素。Retina 通常是 2。"""
    if IS_MAC:
        try:
            import ctypes
            cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            cg.CGMainDisplayID.restype = ctypes.c_uint32
            return _mac_pixel_scale(int(cg.CGMainDisplayID()))
        except Exception:
            return 2.0
    if IS_WINDOWS:
        try:
            import ctypes
            factor = ctypes.windll.shcore.GetScaleFactorForDevice(0)
            if factor:
                return max(1.0, factor / 100.0)
        except Exception:
            pass
    return 1.0


def even_box(x, y, w, h):
    """影像編碼要求寬高是偶數。"""
    x = max(0, int(x) - int(x) % 2)
    y = max(0, int(y) - int(y) % 2)
    w = max(2, int(w) - int(w) % 2)
    h = max(2, int(h) - int(h) % 2)
    return x, y, w, h


def pick_screen_region(parent):
    """
    蓋一層在目前這個螢幕上，讓使用者拖出範圍。
    成功回傳 (x, y, w, h) 像素。取消回傳 None。
    """
    chosen = {"rect": None}
    fonts = get_ui_fonts()
    win = tk.Toplevel(parent)
    win.title("選取範圍")
    win.configure(bg="#000000")
    win.attributes("-topmost", True)
    try:
        win.attributes("-alpha", 0.45)
    except tk.TclError:
        pass
    try:
        win.attributes("-fullscreen", True)
    except tk.TclError:
        win.geometry(f"{win.winfo_screenwidth()}x{win.winfo_screenheight()}+0+0")
    win.configure(cursor="crosshair")

    canvas = tk.Canvas(win, bg="#000000", highlightthickness=0, cursor="crosshair")
    canvas.pack(fill=tk.BOTH, expand=True)
    hint = canvas.create_text(
        40, 36, anchor="w",
        text="拖曳選取  ·  Shift 正方形  ·  按 1 [16:9]  2 [9:16]  3 [1:1]  A [全螢幕]  ·  Esc 取消",
        fill=UI["blue"],
        font=fonts["subtitle"],
    )
    size_text = canvas.create_text(40, 64, anchor="w", text="", fill=UI["white"], font=fonts["badge"])
    origin = {"x": 0, "y": 0, "item": None, "last_x": 0, "last_y": 0}

    def clear_band():
        if origin["item"] is not None:
            canvas.delete(origin["item"])
            origin["item"] = None

    def on_press(event):
        origin["x"] = event.x
        origin["y"] = event.y
        origin["last_x"] = event.x
        origin["last_y"] = event.y
        chosen["pending"] = None
        clear_band()

    def on_drag(event):
        clear_band()
        x1, y1 = origin["x"], origin["y"]
        dx = event.x - x1
        dy = event.y - y1
        if (event.state & 0x0001) or (getattr(event, 'keysym', '') == 'Shift_L'):
            side = max(abs(dx), abs(dy))
            cur_x = x1 + (side if dx >= 0 else -side)
            cur_y = y1 + (side if dy >= 0 else -side)
        else:
            cur_x = event.x
            cur_y = event.y

        origin["last_x"] = cur_x
        origin["last_y"] = cur_y
        origin["item"] = canvas.create_rectangle(
            x1, y1, cur_x, cur_y, outline=UI["blue"], width=2
        )
        scale = display_scale()
        width = int(abs(cur_x - x1) * scale)
        height = int(abs(cur_y - y1) * scale)
        canvas.coords(size_text, cur_x + 14, cur_y + 14)
        canvas.itemconfigure(size_text, text=f"{width} × {height}")

    def on_release(event):
        x1, y1 = origin["x"], origin["y"]
        last_x = origin.get("last_x", event.x)
        last_y = origin.get("last_y", event.y)
        width = abs(last_x - x1)
        height = abs(last_y - y1)
        if width < 32 or height < 32:
            clear_band()
            canvas.itemconfigure(size_text, text="拖曳範圍過小，請重新拖曳")
            return
        scale = display_scale()
        rx = min(x1, last_x) * scale
        ry = min(y1, last_y) * scale
        chosen["rect"] = even_box(rx, ry, width * scale, height * scale)
        win.destroy()

    def apply_preset(w_ratio, h_ratio):
        clear_band()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        if w_ratio >= h_ratio:
            tw = int(sw * 0.70)
            th = int(tw * h_ratio / w_ratio)
        else:
            th = int(sh * 0.75)
            tw = int(th * w_ratio / h_ratio)
        x1 = (sw - tw) // 2
        y1 = (sh - th) // 2
        x2 = x1 + tw
        y2 = y1 + th
        origin["x"], origin["y"] = x1, y1
        origin["last_x"], origin["last_y"] = x2, y2
        origin["item"] = canvas.create_rectangle(x1, y1, x2, y2, outline=UI["ok"], width=3)
        scale = display_scale()
        canvas.coords(size_text, x2 - 120, y2 + 18)
        canvas.itemconfigure(size_text, text=f"{int(tw * scale)} × {int(th * scale)}（按 Enter 確認）")
        chosen["pending"] = (x1, y1, tw, th)

    def on_enter_key(_event=None):
        if chosen.get("pending"):
            x1, y1, tw, th = chosen["pending"]
            scale = display_scale()
            chosen["rect"] = even_box(x1 * scale, y1 * scale, tw * scale, th * scale)
            win.destroy()
        else:
            on_full_screen()

    def on_full_screen(_event=None):
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        scale = display_scale()
        chosen["rect"] = even_box(0, 0, sw * scale, sh * scale)
        win.destroy()

    def on_cancel(_event=None):
        chosen["rect"] = None
        win.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    win.bind("<Key-1>", lambda _e: apply_preset(16, 9))
    win.bind("<Key-2>", lambda _e: apply_preset(9, 16))
    win.bind("<Key-3>", lambda _e: apply_preset(1, 1))
    win.bind("<Key-4>", lambda _e: apply_preset(4, 3))
    win.bind("<a>", on_full_screen)
    win.bind("<A>", on_full_screen)
    win.bind("<Return>", on_enter_key)
    win.bind("<Escape>", on_cancel)
    win.protocol("WM_DELETE_WINDOW", on_cancel)
    win.grab_set()
    win.focus_force()
    canvas.coords(hint, 40, 36)
    parent.wait_window(win)
    return chosen["rect"]


def capture_screen_index(device_name):
    """從裝置名稱取出 Capture screen 0 這種編號。沒有就用主螢幕。"""
    text = device_name or ""
    match = re.search(r"screen\s+(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"螢幕\s*(\d+)", text)
    if match:
        return int(match.group(1))
    return 0


def _short_name(text, limit=22):
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _mac_displays():
    """每個螢幕在左上原點的點座標，以及像素倍率。順序對齊 Capture screen。"""
    import ctypes

    class _Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    class _Size(ctypes.Structure):
        _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]

    class _Rect(ctypes.Structure):
        _fields_ = [("origin", _Point), ("size", _Size)]

    cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cg.CGMainDisplayID.restype = ctypes.c_uint32
    cg.CGGetActiveDisplayList.argtypes = [
        ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)
    ]
    cg.CGGetActiveDisplayList.restype = ctypes.c_int32
    cg.CGDisplayBounds.argtypes = [ctypes.c_uint32]
    cg.CGDisplayBounds.restype = _Rect

    count = ctypes.c_uint32(0)
    if cg.CGGetActiveDisplayList(0, None, ctypes.byref(count)) != 0 or not count.value:
        return []
    id_list = (ctypes.c_uint32 * count.value)()
    if cg.CGGetActiveDisplayList(count.value, id_list, ctypes.byref(count)) != 0:
        return []
    main_id = int(cg.CGMainDisplayID())
    ordered = sorted((int(id_list[i]) for i in range(count.value)), key=lambda did: (did != main_id, did))

    displays = []
    for did in ordered:
        rect = cg.CGDisplayBounds(did)
        displays.append({
            "x": float(rect.origin.x),
            "y": float(rect.origin.y),
            "w": float(rect.size.width),
            "h": float(rect.size.height),
            "scale": _mac_pixel_scale(did),
        })
    return displays


def _box_on_display(win_x, win_y, win_w, win_h, display):
    """視窗和這個螢幕重疊的部分，換成擷取用的偶數像素。"""
    x1 = max(win_x, display["x"])
    y1 = max(win_y, display["y"])
    x2 = min(win_x + win_w, display["x"] + display["w"])
    y2 = min(win_y + win_h, display["y"] + display["h"])
    if x2 - x1 < 80 or y2 - y1 < 80:
        return None
    scale = display["scale"]
    max_w = int(display["w"] * scale)
    max_h = int(display["h"] * scale)
    box = even_box((x1 - display["x"]) * scale, (y1 - display["y"]) * scale, (x2 - x1) * scale, (y2 - y1) * scale)
    x, y, w, h = box
    x = min(x, max(0, max_w - 2))
    y = min(y, max(0, max_h - 2))
    w = min(w, max_w - x)
    h = min(h, max_h - y)
    return even_box(x, y, w, h)


def _mac_window_rows():
    import ctypes

    cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    cf.CFRelease.argtypes = [ctypes.c_void_p]

    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]

    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFDictionaryGetValue.restype = ctypes.c_void_p
    cf.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    cf.CFNumberGetValue.restype = ctypes.c_bool
    cf.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]

    class _Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    class _Size(ctypes.Structure):
        _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]

    class _Rect(ctypes.Structure):
        _fields_ = [("origin", _Point), ("size", _Size)]

    cg.CGRectMakeWithDictionaryRepresentation.restype = ctypes.c_bool
    cg.CGRectMakeWithDictionaryRepresentation.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Rect)]

    UTF8 = 0x08000100

    def cf_str(cf_val):
        if not cf_val:
            return ""
        buf = ctypes.create_string_buffer(512)
        if cf.CFStringGetCString(cf_val, buf, 512, UTF8):
            return buf.value.decode("utf-8", errors="ignore")
        return ""

    def cf_int(cf_val):
        if not cf_val:
            return 0
        val = ctypes.c_longlong(0)
        if cf.CFNumberGetValue(cf_val, 4, ctypes.byref(val)):
            return val.value
        return 0

    ptr = cg.CGWindowListCopyWindowInfo(1 | 16, 0)
    if not ptr:
        return []

    k_owner = cf.CFStringCreateWithCString(None, b"kCGWindowOwnerName", UTF8)
    k_name = cf.CFStringCreateWithCString(None, b"kCGWindowName", UTF8)
    k_pid = cf.CFStringCreateWithCString(None, b"kCGWindowOwnerPID", UTF8)
    k_layer = cf.CFStringCreateWithCString(None, b"kCGWindowLayer", UTF8)
    k_num = cf.CFStringCreateWithCString(None, b"kCGWindowNumber", UTF8)
    k_bounds = cf.CFStringCreateWithCString(None, b"kCGWindowBounds", UTF8)

    rows = []
    my_pid = os.getpid()
    try:
        count = int(cf.CFArrayGetCount(ptr))
        for index in range(count):
            d = cf.CFArrayGetValueAtIndex(ptr, index)
            layer = cf_int(cf.CFDictionaryGetValue(d, k_layer))
            owner_pid = cf_int(cf.CFDictionaryGetValue(d, k_pid))
            if layer != 0 or owner_pid == my_pid:
                continue
            bounds_dict = cf.CFDictionaryGetValue(d, k_bounds)
            r = _Rect()
            if not cg.CGRectMakeWithDictionaryRepresentation(bounds_dict, ctypes.byref(r)):
                continue
            win_w = float(r.size.width)
            win_h = float(r.size.height)
            if win_w < 160 or win_h < 100:
                continue
            owner = cf_str(cf.CFDictionaryGetValue(d, k_owner)).strip()
            title = cf_str(cf.CFDictionaryGetValue(d, k_name)).strip()
            if not owner or owner in {"Window Server", "Dock"}:
                continue
            window_id = cf_int(cf.CFDictionaryGetValue(d, k_num))
            rows.append({
                "id": window_id,
                "owner": owner,
                "title": title,
                "x": float(r.origin.x),
                "y": float(r.origin.y),
                "w": win_w,
                "h": win_h,
            })
    finally:
        for k in (k_owner, k_name, k_pid, k_layer, k_num, k_bounds):
            if k:
                cf.CFRelease(k)
        cf.CFRelease(ptr)
    return rows


def follow_crop(origin_x, origin_y, width, height, frame_w, frame_h):
    """大小維持開始時的那一塊，只把左上角跟著視窗走，並留在畫面裡。"""
    w = max(2, int(width) - int(width) % 2)
    h = max(2, int(height) - int(height) % 2)
    max_x = max(0, int(frame_w) - w)
    max_y = max(0, int(frame_h) - h)
    x = min(max(int(round(origin_x)), 0), max_x)
    y = min(max(int(round(origin_y)), 0), max_y)
    x -= x % 2
    y -= y % 2
    if x > max_x:
        x = max_x - (max_x % 2)
    if y > max_y:
        y = max_y - (max_y % 2)
    return x, y, w, h


def _load_x11():
    import ctypes

    try:
        return ctypes.cdll.LoadLibrary("libX11.so.6")
    except OSError:
        return None


def _linux_displays():
    """X11 預設畫面的大小。沒有函式庫或沒有 DISPLAY 就回空的。"""
    import ctypes

    lib = _load_x11()
    if lib is None:
        return []
    lib.XOpenDisplay.restype = ctypes.c_void_p
    lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    lib.XDefaultScreen.restype = ctypes.c_int
    lib.XDefaultScreen.argtypes = [ctypes.c_void_p]
    lib.XDisplayWidth.restype = ctypes.c_int
    lib.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.XDisplayHeight.restype = ctypes.c_int
    lib.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
    display = lib.XOpenDisplay(None)
    if not display:
        return []
    try:
        screen = int(lib.XDefaultScreen(display))
        width = int(lib.XDisplayWidth(display, screen))
        height = int(lib.XDisplayHeight(display, screen))
    except Exception:
        return []
    finally:
        lib.XCloseDisplay(display)
    if width < 2 or height < 2:
        return []
    return [{"x": 0.0, "y": 0.0, "w": float(width), "h": float(height), "scale": 1.0}]


def _x11_ready(lib):
    import ctypes

    lib.XOpenDisplay.restype = ctypes.c_void_p
    lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    lib.XDefaultRootWindow.restype = ctypes.c_ulong
    lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    lib.XInternAtom.restype = ctypes.c_ulong
    lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.XGetWindowProperty.restype = ctypes.c_int
    lib.XGetWindowProperty.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_long,
        ctypes.c_long,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    lib.XFree.argtypes = [ctypes.c_void_p]
    lib.XGetGeometry.restype = ctypes.c_int
    lib.XGetGeometry.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
        ctypes.POINTER(ctypes.c_uint),
    ]
    lib.XTranslateCoordinates.restype = ctypes.c_int
    lib.XTranslateCoordinates.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong),
    ]


def _x11_property(lib, display, window, atom):
    import ctypes

    actual_type = ctypes.c_ulong()
    actual_format = ctypes.c_int()
    count = ctypes.c_ulong()
    after = ctypes.c_ulong()
    data = ctypes.c_void_p()
    status = lib.XGetWindowProperty(
        display,
        window,
        atom,
        0,
        2048,
        0,
        0,
        ctypes.byref(actual_type),
        ctypes.byref(actual_format),
        ctypes.byref(count),
        ctypes.byref(after),
        ctypes.byref(data),
    )
    if status != 0 or not data.value:
        return b"", 0, 0
    try:
        size = int(count.value)
        if int(actual_format.value) == 8:
            raw = ctypes.string_at(data.value, size)
        elif int(actual_format.value) == 32:
            raw = ctypes.string_at(data.value, size * ctypes.sizeof(ctypes.c_ulong))
        else:
            raw = b""
        return raw, int(actual_format.value), size
    finally:
        lib.XFree(data)


def _linux_window_rows():
    """X11 上的一般視窗。沒有 libX11 或沒有畫面就回空的。"""
    import ctypes

    lib = _load_x11()
    if lib is None or not os.environ.get("DISPLAY"):
        return []
    try:
        _x11_ready(lib)
    except Exception:
        return []
    display = lib.XOpenDisplay(None)
    if not display:
        return []
    rows = []
    try:
        root = lib.XDefaultRootWindow(display)
        client_atom = lib.XInternAtom(display, b"_NET_CLIENT_LIST", 1)
        name_atom = lib.XInternAtom(display, b"_NET_WM_NAME", 1)
        class_atom = lib.XInternAtom(display, b"WM_CLASS", 1)
        if not client_atom:
            return []
        raw, fmt, count = _x11_property(lib, display, root, client_atom)
        if fmt != 32 or count <= 0:
            return []
        ident_size = ctypes.sizeof(ctypes.c_ulong)
        for index in range(count):
            window = int.from_bytes(raw[index * ident_size:(index + 1) * ident_size], "little")
            if window <= 0:
                continue
            root_ret = ctypes.c_ulong()
            gx = ctypes.c_int()
            gy = ctypes.c_int()
            width = ctypes.c_uint()
            height = ctypes.c_uint()
            border = ctypes.c_uint()
            depth = ctypes.c_uint()
            if not lib.XGetGeometry(
                display, window, ctypes.byref(root_ret),
                ctypes.byref(gx), ctypes.byref(gy),
                ctypes.byref(width), ctypes.byref(height),
                ctypes.byref(border), ctypes.byref(depth),
            ):
                continue
            child = ctypes.c_ulong()
            rx = ctypes.c_int()
            ry = ctypes.c_int()
            if not lib.XTranslateCoordinates(
                display, window, root, 0, 0, ctypes.byref(rx), ctypes.byref(ry), ctypes.byref(child)
            ):
                continue
            win_w = int(width.value)
            win_h = int(height.value)
            if win_w < 160 or win_h < 100:
                continue
            title = ""
            if name_atom:
                blob, name_fmt, _name_count = _x11_property(lib, display, window, name_atom)
                if name_fmt == 8 and blob:
                    title = blob.split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
            owner = ""
            if class_atom:
                blob, class_fmt, _class_count = _x11_property(lib, display, window, class_atom)
                if class_fmt == 8 and blob:
                    parts = [part.decode("utf-8", "replace").strip() for part in blob.split(b"\x00") if part]
                    owner = parts[-1] if parts else ""
            if not owner:
                owner = title or "視窗"
            rows.append({
                "id": window,
                "owner": owner,
                "title": title if title != owner else "",
                "x": float(rx.value),
                "y": float(ry.value),
                "w": float(win_w),
                "h": float(win_h),
            })
    except Exception:
        return []
    finally:
        lib.XCloseDisplay(display)
    return rows


def _windows_physical_box(hwnd, left, top, width, height):
    """系統 DPI 模式下，把別台螢幕的視窗換算成實體像素。已是每台螢幕感知就不動。"""
    import ctypes

    try:
        awareness = ctypes.c_int()
        if ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness)) != 0:
            return left, top, width, height
        if int(awareness.value) >= 2:
            return left, top, width, height
        window_dpi = int(ctypes.windll.user32.GetDpiForWindow(hwnd) or 0)
        system_dpi = int(ctypes.windll.user32.GetDpiForSystem() or 0)
    except Exception:
        return left, top, width, height
    if window_dpi <= 0 or system_dpi <= 0 or window_dpi == system_dpi:
        return left, top, width, height
    ratio = window_dpi / system_dpi
    return (
        int(round(left * ratio)),
        int(round(top * ratio)),
        max(2, int(round(width * ratio))),
        max(2, int(round(height * ratio))),
    )


def _windows_window_rows():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    vx = int(user32.GetSystemMetrics(76))
    vy = int(user32.GetSystemMetrics(77))
    rows = []

    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetWindow(hwnd, 4):  # GW_OWNER，跳過附屬小窗
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        rect = wintypes.RECT()
        got_frame = False
        try:
            # 9 是可見範圍，不含四周的陰影。
            if ctypes.windll.dwmapi.DwmGetWindowAttribute(
                hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)
            ) == 0:
                got_frame = True
        except Exception:
            got_frame = False
        if not got_frame and not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        left, top, width, height = _windows_physical_box(
            hwnd,
            int(rect.left),
            int(rect.top),
            int(rect.right - rect.left),
            int(rect.bottom - rect.top),
        )
        if width < 160 or height < 100:
            return True
        title = buf.value.strip()
        if not title:
            return True
        rows.append({
            "id": int(hwnd),
            "owner": title,
            "title": "",
            "x": left - vx,
            "y": top - vy,
            "w": width,
            "h": height,
        })
        return True

    callback = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(visit)
    user32.EnumWindows(callback, 0)
    return rows


def _window_rows():
    try:
        if IS_MAC:
            return _mac_window_rows()
        if IS_WINDOWS:
            return _windows_window_rows()
        if IS_LINUX:
            return _linux_window_rows()
    except Exception:
        return []
    return []


def _display_for(screen_index):
    if IS_MAC:
        displays = _mac_displays()
        if screen_index < 0 or screen_index >= len(displays):
            return None
        return displays[screen_index]
    if IS_WINDOWS:
        if screen_index != 0:
            return None
        import ctypes
        user32 = ctypes.windll.user32
        return {
            "x": 0,
            "y": 0,
            "w": int(user32.GetSystemMetrics(78)),
            "h": int(user32.GetSystemMetrics(79)),
            "scale": 1.0,
        }
    if IS_LINUX:
        displays = _linux_displays()
        if screen_index != 0 or not displays:
            return None
        return displays[0]
    return None


def list_displays():
    """每個螢幕的點座標與像素倍率。"""
    if IS_MAC:
        return _mac_displays()
    if IS_WINDOWS:
        frame = _display_for(0)
        return [frame] if frame else []
    if IS_LINUX:
        return _linux_displays()
    return []


def other_display_origin(capture_index, bar_w, bar_h, margin=40):
    """另一個螢幕上放得下這條的左上角。沒有就回 None。"""
    try:
        chosen = int(capture_index)
    except (TypeError, ValueError):
        chosen = 0
    margin = max(0.0, float(margin))
    width = float(bar_w)
    height = float(bar_h)
    for index, frame in enumerate(list_displays()):
        if index == chosen:
            continue
        if frame["w"] < width + margin or frame["h"] < height + margin:
            continue
        return (int(frame["x"] + margin), int(frame["y"] + margin))
    return None


def window_capture_origin(window_id, screen_index=0):
    """視窗左上角在這個螢幕擷取像素裡的位置。可以是負的。關掉了就回 None。"""
    try:
        target = int(window_id)
    except (TypeError, ValueError):
        return None
    display = _display_for(screen_index)
    if display is None:
        return None
    scale = display["scale"] or 1
    for row in _window_rows():
        if row["id"] != target:
            continue
        return ((row["x"] - display["x"]) * scale, (row["y"] - display["y"]) * scale)
    return None


def window_list_hint():
    """選不到視窗時給使用者的那一句。"""
    if IS_LINUX:
        if _load_x11() is None:
            return "這台沒有 libX11，列不出視窗。\n可以改拖一塊範圍。"
        if not os.environ.get("DISPLAY"):
            return "沒有畫面階段，列不出視窗。\n可以改拖一塊範圍。"
    return "這個螢幕上沒有可錄的視窗。\n可以改用拖曳範圍。"


def display_frame(screen_index=0):
    """這個螢幕的點座標與像素倍率。沒有就回 None。"""
    return _display_for(screen_index)


def box_to_points(box, screen_index=0):
    """擷取像素 (x, y, w, h) 換成這個螢幕上的點。"""
    frame = _display_for(screen_index)
    if frame is None or not box or len(box) != 4:
        return None
    try:
        x, y, w, h = (float(v) for v in box)
    except (TypeError, ValueError):
        return None
    scale = frame["scale"] or 1
    return (frame["x"] + x / scale, frame["y"] + y / scale, w / scale, h / scale)


def _rects_overlap(one, other):
    ax, ay, aw, ah = one
    bx, by, bw, bh = other
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def bar_origin(screen, target, bar_w, bar_h, margin=40):
    """小條放在這個螢幕上，盡量不要壓到目標。座標都是點，回傳 (x, y)。"""
    sx, sy, sw, sh = (float(v) for v in screen)
    bw = min(max(float(bar_w), 2), sw)
    bh = min(max(float(bar_h), 2), sh)
    margin = max(0.0, float(margin))

    def clamp(x, y):
        return (
            min(max(x, sx), sx + max(0.0, sw - bw)),
            min(max(y, sy), sy + max(0.0, sh - bh)),
        )

    right = sx + sw - bw - margin
    bottom = sy + sh - bh - margin
    candidates = []
    for point in ((right, sy + margin), (sx + margin, sy + margin), (right, bottom), (sx + margin, bottom)):
        clamped = clamp(*point)
        if clamped not in candidates:
            candidates.append(clamped)
    for x, y in candidates:
        if target is None or not _rects_overlap((x, y, bw, bh), target):
            return (int(round(x)), int(round(y)))
    return (int(round(candidates[0][0])), int(round(candidates[0][1])))


def list_capture_windows(screen_index=0):
    """這個螢幕上可以錄的視窗。box 是擷取像素 (x, y, w, h)。"""
    display = _display_for(screen_index)
    if display is None:
        return []
    found = []
    for row in _window_rows():
        box = _box_on_display(row["x"], row["y"], row["w"], row["h"], display)
        if box is None:
            continue
        found.append({
            "id": row["id"],
            "owner": row["owner"],
            "title": row["title"],
            "box": box,
        })
    found.sort(key=lambda item: (item["owner"].lower(), item["title"].lower()))
    return found


def resolve_window_box(window_id, screen_index=0):
    """再量一次視窗位置。回傳 (box, 錯誤訊息)。"""
    try:
        target = int(window_id)
    except (TypeError, ValueError):
        return None, "這個視窗已經關掉"
    display = _display_for(screen_index)
    if display is None:
        return None, "目前的來源不是這個螢幕"
    for row in _window_rows():
        if row["id"] != target:
            continue
        box = _box_on_display(row["x"], row["y"], row["w"], row["h"], display)
        if box is None:
            return None, "這個視窗不在目前選的螢幕上"
        return box, ""
    return None, "這個視窗已經關掉"


def pick_capture_window(parent, screen_index=0):
    """讓使用者挑一個視窗。取消回傳 None。"""
    windows = list_capture_windows(screen_index)
    chosen = {"window": None, "index": None}
    fonts = get_ui_fonts()
    win = tk.Toplevel(parent)
    win.title("選擇視窗")
    win.configure(bg=UI["bg"])
    win.minsize(420, 320)
    win.transient(parent)
    try:
        win.attributes("-topmost", True)
    except tk.TclError:
        pass
    parent.update_idletasks()
    origin_x = max(0, parent.winfo_rootx() + 36)
    origin_y = max(0, parent.winfo_rooty() + 36)
    win.geometry(f"460x420+{origin_x}+{origin_y}")

    shell = tk.Frame(win, bg=UI["bg"])
    shell.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)
    tk.Label(
        shell, text="選擇視窗", font=fonts["bold"], fg=UI["white"], bg=UI["bg"], anchor="w"
    ).pack(fill=tk.X)
    tk.Label(
        shell,
        text="錄影時會跟著這個視窗移動。畫面大小維持按下開始時的那一塊。",
        font=fonts["body"],
        fg=UI["muted"],
        bg=UI["bg"],
        anchor="w",
        wraplength=420,
        justify="left",
    ).pack(fill=tk.X, pady=(2, 8))

    list_card = tk.Frame(shell, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1)
    list_card.pack(fill=tk.BOTH, expand=True)
    if not windows:
        tk.Label(
            list_card,
            text=window_list_hint(),
            font=fonts["body"],
            fg=UI["muted"],
            bg=UI["card"],
            justify="center",
        ).pack(expand=True, pady=24)
    else:
        canvas = tk.Canvas(list_card, bg=UI["card"], highlightthickness=0, bd=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        inner = tk.Frame(canvas, bg=UI["card"])
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        row_widgets = []

        def paint_rows():
            for index, row in enumerate(row_widgets):
                selected = chosen["index"] == index
                color = UI["blue"] if selected else UI["edge"]
                row.configure(highlightbackground=color, highlightthickness=1)

        def select(index, close=False):
            chosen["index"] = index
            paint_rows()
            use_btn.config(state=tk.NORMAL)
            if close:
                accept()

        for index, item in enumerate(windows):
            row = tk.Frame(inner, bg=UI["card"], highlightbackground=UI["edge"], highlightthickness=1, cursor="hand2")
            row.pack(fill=tk.X, padx=6, pady=3)
            owner = tk.Label(
                row, text=_short_name(item["owner"], 28), font=fonts["bold"],
                fg=UI["white"], bg=UI["card"], anchor="w", cursor="hand2",
            )
            owner.pack(fill=tk.X, padx=8, pady=(4, 0))
            detail = item["title"] or "沒有標題"
            width, height = item["box"][2], item["box"][3]
            tk.Label(
                row, text=f"{_short_name(detail, 36)}   {width}×{height}",
                font=fonts["badge"], fg=UI["muted"], bg=UI["card"], anchor="w",
            ).pack(fill=tk.X, padx=8, pady=(0, 4))
            row.bind("<Button-1>", lambda _e, i=index: select(i))
            row.bind("<Double-Button-1>", lambda _e, i=index: select(i, True))
            for child in row.winfo_children():
                child.bind("<Button-1>", lambda _e, i=index: select(i))
                child.bind("<Double-Button-1>", lambda _e, i=index: select(i, True))
            row_widgets.append(row)

        def fit_width(event):
            canvas.itemconfigure(window_id, width=event.width)

        def sync_scroll(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all") or (0, 0, 0, 0))

        canvas.bind("<Configure>", fit_width)
        inner.bind("<Configure>", sync_scroll)

        def on_wheel(event):
            delta = getattr(event, "delta", 0)
            if getattr(event, "num", None) == 4 or delta > 0:
                canvas.yview_scroll(-1, "units")
            else:
                canvas.yview_scroll(1, "units")

        canvas.bind("<MouseWheel>", on_wheel)
        canvas.bind("<Button-4>", on_wheel)
        canvas.bind("<Button-5>", on_wheel)

    buttons = tk.Frame(shell, bg=UI["bg"])
    buttons.pack(fill=tk.X, pady=(10, 0))

    def cancel():
        chosen["window"] = None
        win.destroy()

    def accept():
        index = chosen["index"]
        if index is None or not windows:
            return
        chosen["window"] = windows[index]
        win.destroy()

    use_btn = AuraButton(buttons, text="使用這個視窗", style="Primary.TButton", command=accept, state=tk.DISABLED)
    if windows:
        use_btn.pack(side=tk.RIGHT)
    AuraButton(buttons, text="取消", style="Ghost.TButton", command=cancel).pack(side=tk.RIGHT, padx=(0, 8))

    win.bind("<Escape>", lambda _e: cancel())
    win.protocol("WM_DELETE_WINDOW", cancel)
    win.grab_set()
    win.focus_force()
    parent.wait_window(win)
    return chosen["window"]
