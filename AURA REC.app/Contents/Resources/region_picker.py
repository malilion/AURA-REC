#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""拖曳選取要錄的螢幕範圍。座標換成擷取用的像素。"""

import tkinter as tk

from platform_utils import IS_MAC, IS_WINDOWS, UI, get_ui_fonts


def display_scale():
    """點轉成螢幕像素。Retina 通常是 2。"""
    if IS_MAC:
        try:
            from AppKit import NSScreen
            return max(1.0, float(NSScreen.mainScreen().backingScaleFactor()))
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
