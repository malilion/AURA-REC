#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""拖曳選取範圍，或改錄畫面上的某一個視窗。座標換成擷取用的像素。"""

import os
import re
import tkinter as tk

from aura_widgets import AuraButton
from platform_utils import IS_MAC, IS_WINDOWS, UI, get_ui_fonts


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
        text="拖曳選取範圍    Esc 取消",
        fill=UI["blue"],
        font=fonts["subtitle"],
    )
    size_text = canvas.create_text(40, 64, anchor="w", text="", fill=UI["white"], font=fonts["badge"])
    origin = {"x": 0, "y": 0, "item": None}

    def clear_band():
        if origin["item"] is not None:
            canvas.delete(origin["item"])
            origin["item"] = None

    def on_press(event):
        origin["x"] = event.x
        origin["y"] = event.y
        clear_band()

    def on_drag(event):
        clear_band()
        x1, y1 = origin["x"], origin["y"]
        origin["item"] = canvas.create_rectangle(
            x1, y1, event.x, event.y, outline=UI["blue"], width=2
        )
        width = abs(event.x - x1)
        height = abs(event.y - y1)
        canvas.coords(size_text, event.x + 12, event.y + 12)
        canvas.itemconfigure(size_text, text=f"{width} × {height}")

    def on_release(event):
        width = abs(event.x - origin["x"])
        height = abs(event.y - origin["y"])
        if width < 48 or height < 48:
            clear_band()
            canvas.itemconfigure(size_text, text="再拖大一點")
            return
        scale = display_scale()
        x = min(origin["x"], event.x) * scale
        y = min(origin["y"], event.y) * scale
        chosen["rect"] = even_box(x, y, width * scale, height * scale)
        win.destroy()

    def on_cancel(_event=None):
        chosen["rect"] = None
        win.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
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
    import objc

    cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    cg.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    # 畫面上的一般視窗，不含桌布。
    ptr = cg.CGWindowListCopyWindowInfo(1 | 16, 0)
    if not ptr:
        return []
    rows = []
    try:
        array = objc.objc_object(c_void_p=ptr)
        for index in range(int(array.count())):
            item = array.objectAtIndex_(index)
            try:
                layer = int(item["kCGWindowLayer"])
                owner_pid = int(item["kCGWindowOwnerPID"])
                window_id = int(item["kCGWindowNumber"])
                bounds = item["kCGWindowBounds"]
                win_x = float(bounds["X"])
                win_y = float(bounds["Y"])
                win_w = float(bounds["Width"])
                win_h = float(bounds["Height"])
            except (KeyError, TypeError, ValueError):
                continue
            if layer != 0 or owner_pid == os.getpid() or win_w < 160 or win_h < 100:
                continue
            owner = str(item["kCGWindowOwnerName"] or "").strip()
            title = str(item["kCGWindowName"] or "").strip()
            if not owner or owner in {"Window Server", "Dock"}:
                continue
            rows.append({
                "id": window_id,
                "owner": owner,
                "title": title,
                "x": win_x,
                "y": win_y,
                "w": win_w,
                "h": win_h,
            })
    finally:
        cf.CFRelease(ptr)
    return rows


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
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width < 160 or height < 100:
            return True
        title = buf.value.strip()
        if not title:
            return True
        rows.append({
            "id": int(hwnd),
            "owner": title,
            "title": "",
            "x": int(rect.left) - vx,
            "y": int(rect.top) - vy,
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
    return None


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
        text="錄的是按下開始時，這個視窗在畫面上的位置。",
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
            text="這個螢幕上沒有可錄的視窗。\n可以改用拖曳範圍。",
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
