#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""官網樣式的圓角按鈕、勾選、選項與時間軸。macOS 原生控制項畫不出這套顏色。"""

import math
import tkinter as tk
from tkinter import font as tkfont

from platform_utils import UI, get_ui_fonts


def _parent_bg(parent):
    try:
        return parent.cget("bg")
    except tk.TclError:
        return UI["bg"]


def _hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _round_points(x1, y1, x2, y2, radius):
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]


def _fill_round(canvas, x1, y1, x2, y2, radius, color):
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    canvas.create_polygon(
        _round_points(x1, y1, x2, y2, radius),
        smooth=True, splinesteps=24, fill=color, outline="",
    )


def _cap_inset(x, width, radius):
    if radius <= 0:
        return 0.0
    if x < radius:
        dx = radius - x
    elif x > width - radius:
        dx = x - (width - radius)
    else:
        return 0.0
    inside = radius * radius - dx * dx
    if inside <= 0:
        return float(radius)
    return radius - math.sqrt(inside)


_CYAN = (0, 240, 255)
_EMERALD = (0, 255, 157)
_ROSE = (255, 42, 109)
_ROSE_END = (255, 92, 138)

_BUTTONS = {
    "Primary.TButton": {"kind": "gradient", "height": 46, "radius": 14, "font": "subtitle"},
    "Play.TButton": {"kind": "gradient", "height": 34, "radius": 10, "font": "subtitle"},
    "Stop.TButton": {"kind": "rose", "height": 34, "radius": 10, "font": "bold"},
    "Record.TButton": {"kind": "rose", "height": 46, "radius": 14, "font": "subtitle"},
    "Ghost.TButton": {"kind": "ghost", "height": 32, "radius": 8, "font": "body"},
    "Link.TButton": {"kind": "link", "height": 26, "radius": 0, "font": "body", "fg": "blue"},
    "Danger.TButton": {"kind": "link", "height": 26, "radius": 0, "font": "body", "fg": "red"},
}


class AuraButton(tk.Canvas):
    """圓角按鈕。主按鈕是青到綠的漸層、黑字，跟官網下載鈕一樣。"""

    def __init__(self, parent, text="", command=None, style="Primary.TButton", state=tk.NORMAL, **_ignored):
        self._bg = _parent_bg(parent)
        self._text = text
        self._command = command
        self._style = style if style in _BUTTONS else "Primary.TButton"
        self._state = "disabled" if state in (tk.DISABLED, "disabled") else "normal"
        self._hot = False
        spec = _BUTTONS[self._style]
        super().__init__(
            parent, height=spec["height"], width=48, bg=self._bg,
            highlightthickness=0, bd=0, cursor="hand2" if self._state == "normal" else "arrow",
        )
        self._fit_width()
        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)
        self.after_idle(self._redraw)

    def _spec(self):
        return _BUTTONS.get(self._style, _BUTTONS["Primary.TButton"])

    def _font(self):
        return get_ui_fonts()[self._spec()["font"]]

    def _fit_width(self):
        spec = self._spec()
        tk.Canvas.configure(self, height=spec["height"])
        if spec["kind"] in ("link", "ghost"):
            measured = tkfont.Font(font=self._font()).measure(self._text)
            pad = 28 if spec["kind"] == "ghost" else 16
            tk.Canvas.configure(self, width=max(measured + pad, 36))

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs = {**cnf, **kwargs}
        elif cnf is not None:
            return self.cget(cnf)
        if "text" in kwargs:
            self._text = kwargs.pop("text")
        if "style" in kwargs:
            style = kwargs.pop("style")
            if style in _BUTTONS:
                self._style = style
        if "state" in kwargs:
            state = kwargs.pop("state")
            self._state = "disabled" if state in (tk.DISABLED, "disabled") else "normal"
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        self._fit_width()
        tk.Canvas.configure(
            self, cursor="hand2" if self._state == "normal" else "arrow", **kwargs
        )
        self._redraw()

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        if key == "state":
            return self._state
        if key == "style":
            return self._style
        return tk.Canvas.cget(self, key)

    def _enter(self, _event):
        if self._state == "normal":
            self._hot = True
            self._redraw()

    def _leave(self, _event):
        self._hot = False
        self._redraw()

    def _click(self, _event):
        if self._state == "normal" and self._command:
            self._command()

    def _redraw(self):
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 8 or height < 8:
            return
        spec = self._spec()
        kind = spec["kind"]
        radius = spec["radius"]
        disabled = self._state != "normal"
        if kind == "link":
            color = UI["muted"] if disabled else UI[spec.get("fg", "blue")]
            self.create_text(width / 2, height / 2, text=self._text, fill=color, font=self._font())
            return
        if disabled:
            _fill_round(self, 1, 1, width - 1, height - 1, radius, UI["line"])
            fg = UI["muted"]
        elif kind == "gradient":
            start = _mix(_CYAN, (255, 255, 255), 0.18) if self._hot else _CYAN
            end = _mix(_EMERALD, (255, 255, 255), 0.12) if self._hot else _EMERALD
            self._paint_gradient(width, height, radius, start, end)
            fg = UI["ink"]
        elif kind == "rose":
            start = _ROSE_END if self._hot else _ROSE
            end = _mix(_ROSE_END, (255, 255, 255), 0.2) if self._hot else _ROSE_END
            self._paint_gradient(width, height, radius, start, end)
            fg = UI["white"]
        else:
            border = UI["blue"] if self._hot else UI["edge"]
            fill = "#10262C" if self._hot else UI["hover"]
            _fill_round(self, 1, 1, width - 1, height - 1, radius, border)
            _fill_round(self, 2, 2, width - 2, height - 2, max(0, radius - 1), fill)
            fg = UI["white"] if self._hot else UI["text"]
        self.create_text(width / 2, height / 2, text=self._text, fill=fg, font=self._font())

    def _paint_gradient(self, width, height, radius, start, end):
        for x in range(1, width - 1):
            inset = _cap_inset(x, width - 2, radius)
            y1 = 1 + inset
            y2 = height - 1 - inset
            if y2 <= y1:
                continue
            t = (x - 1) / max(width - 3, 1)
            self.create_line(x, y1, x, y2, fill=_hex(_mix(start, end, t)))


class AuraCheck(tk.Frame):
    def __init__(self, parent, text, variable, command=None, **_ignored):
        bg = _parent_bg(parent)
        super().__init__(parent, bg=bg)
        self._var = variable
        self._command = command
        self._bg = bg
        self._box = tk.Canvas(self, width=18, height=18, bg=bg, highlightthickness=0, bd=0)
        self._box.pack(side=tk.LEFT, padx=(2, 0), pady=3)
        self._label = tk.Label(
            self, text=text, bg=bg, fg=UI["text"], font=get_ui_fonts()["body"], cursor="hand2"
        )
        self._label.pack(side=tk.LEFT, padx=(8, 2))
        for widget in (self, self._box, self._label):
            widget.bind("<Button-1>", self._toggle)
        self._box.configure(cursor="hand2")
        self._var.trace_add("write", lambda *_: self._draw())
        self._draw()

    def _toggle(self, _event=None):
        self._var.set(not bool(self._var.get()))
        if self._command:
            self._command()

    def _draw(self):
        box = self._box
        try:
            if not box.winfo_exists():
                return
        except tk.TclError:
            return
        box.delete("all")
        if bool(self._var.get()):
            _fill_round(box, 1, 1, 17, 17, 4, UI["blue"])
            box.create_line(
                4, 9, 7, 12, 13, 5,
                fill=UI["ink"], width=2, capstyle=tk.ROUND, joinstyle=tk.ROUND,
            )
        else:
            _fill_round(box, 1, 1, 17, 17, 4, UI["edge"])
            _fill_round(box, 3, 3, 15, 15, 3, self._bg)


class AuraRadio(tk.Frame):
    def __init__(self, parent, text, variable, value, command=None, **_ignored):
        bg = _parent_bg(parent)
        super().__init__(parent, bg=bg)
        self._var = variable
        self._value = value
        self._command = command
        self._box = tk.Canvas(self, width=18, height=18, bg=bg, highlightthickness=0, bd=0)
        self._box.pack(side=tk.LEFT, padx=(2, 0), pady=2)
        label = tk.Label(
            self, text=text, bg=bg, fg=UI["text"], font=get_ui_fonts()["body"], cursor="hand2"
        )
        label.pack(side=tk.LEFT, padx=(8, 2))
        for widget in (self, self._box, label):
            widget.bind("<Button-1>", self._select)
        self._box.configure(cursor="hand2")
        self._var.trace_add("write", lambda *_: self._draw())
        self._draw()

    def _select(self, _event=None):
        self._var.set(self._value)
        if self._command:
            self._command()

    def _draw(self):
        box = self._box
        try:
            if not box.winfo_exists():
                return
        except tk.TclError:
            return
        box.delete("all")
        selected = self._var.get() == self._value
        ring = UI["blue"] if selected else UI["edge"]
        box.create_oval(1, 1, 16, 16, outline=ring, width=2)
        if selected:
            box.create_oval(5, 5, 12, 12, fill=UI["blue"], outline=UI["blue"])


class AuraScale(tk.Canvas):
    """深色軌道、青色已播放段、圓形播放頭。"""

    def __init__(self, parent, from_=0.0, to=100.0, command=None, orient=tk.HORIZONTAL, **_ignored):
        bg = _parent_bg(parent)
        super().__init__(parent, height=22, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self._from = float(from_)
        self._to = float(to)
        self._value = self._from
        self._command = command
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Button-1>", self._pointer)
        self.bind("<B1-Motion>", self._pointer)
        self.after_idle(self._draw)

    def set(self, value):
        self._value = self._clamp(float(value))
        self._draw()

    def get(self):
        return self._value

    def configure(self, cnf=None, **kwargs):
        if isinstance(cnf, dict):
            kwargs = {**cnf, **kwargs}
        if "from_" in kwargs:
            self._from = float(kwargs.pop("from_"))
        if "from" in kwargs:
            self._from = float(kwargs.pop("from"))
        if "to" in kwargs:
            self._to = float(kwargs.pop("to"))
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if kwargs:
            tk.Canvas.configure(self, **kwargs)
        self._draw()

    config = configure

    def _clamp(self, value):
        low, high = self._from, self._to
        if high < low:
            low, high = high, low
        return min(high, max(low, value))

    def _pointer(self, event):
        pad = 9
        span = max(self.winfo_width() - pad * 2, 1)
        portion = min(1.0, max(0.0, (event.x - pad) / span))
        self._value = self._from + (self._to - self._from) * portion
        self._draw()
        if self._command:
            self._command(self._value)

    def _draw(self):
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 8 or height < 8:
            return
        pad = 9
        center = height / 2
        portion = (self._value - self._from) / max(self._to - self._from, 1e-6)
        portion = min(1.0, max(0.0, portion))
        head = pad + portion * (width - pad * 2)
        self.create_line(pad, center, width - pad, center, fill=UI["line"], width=4, capstyle=tk.ROUND)
        if head > pad + 1:
            self.create_line(pad, center, head, center, fill=UI["blue"], width=4, capstyle=tk.ROUND)
        self.create_oval(head - 7, center - 7, head + 7, center + 7, fill=UI["blue"], outline=self["bg"], width=2)
