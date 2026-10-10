#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
screen_annotation.py - AURA REC 錄影中螢幕即時塗鴉與聚光燈工具 (Live Screen Annotation & Spotlight)

功能特色：
1. 錄影進行時（或任何演說教學時）按下快捷鍵 F6 (或 Cmd+Shift+D / Ctrl+Shift+D) 瞬間喚出全螢幕置頂透明塗鴉畫布。
2. 自由手繪畫筆 (Pen)：平滑 B-spline 曲線，支援圓角端點與多種粗細。
3. 箭頭指示器 (Arrow)：指向重點功能、程式碼或介面元素的銳利箭頭。
4. 矩形高亮框 (Rectangle)：框選重要彈窗或關鍵資訊。
5. 聚光燈模式 (Spotlight Focus)：螢幕外圍半透明暗化遮罩，中央以動態發光圓環圈出焦點，隨滑鼠游標平滑移動。
6. 極光霓虹調色盤：極光青藍 (#00F0FF)、活力珊瑚紅 (#FF2A6D)、螢光金黃 (#FFD700)、翡翠綠 (#00FF9D)、純白 (#FFFFFF)。
7. 懸浮可拖曳時尚工具欄 (Draggable Floating Toolbar)：嵌入於畫布頂部，可隨意拖移，點擊不穿透。
8. 支援無限步復原 (Undo, Ctrl+Z / Cmd+Z)、一鍵清空 (Clear, C) 與快速關閉 (Esc)。
9. 跨平台支援 (macOS systemTransparent / Windows transparentcolor / Linux alpha)。
"""

import math
import sys
import tkinter as tk
from typing import Optional, Callable

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform.startswith("win")

# 顏色定義
COLORS = [
    ("#00F0FF", "極光青"),
    ("#FF2A6D", "活力紅"),
    ("#FFD700", "螢光黃"),
    ("#00FF9D", "翡翠綠"),
    ("#FFFFFF", "純白"),
]

WIDTHS = [
    (3, "細"),
    (6, "中"),
    (10, "粗"),
]

TOOL_PEN = "pen"
TOOL_ARROW = "arrow"
TOOL_RECT = "rect"
TOOL_SPOTLIGHT = "spotlight"


class ScreenAnnotationOverlay:
    """螢幕即時塗鴉與聚光燈全螢幕覆蓋層"""

    def __init__(self, parent_root: tk.Tk, on_close: Optional[Callable] = None):
        self.root = parent_root
        self.on_close_cb = on_close

        self.win = None
        self.canvas = None
        self._is_active = False

        # 當前工具與樣式狀態
        self.active_tool = TOOL_PEN
        self.active_color = "#00F0FF"
        self.active_width = 6
        self.spotlight_radius = 130

        # 繪圖歷程 (用於 Undo)
        self.history = []  # 存放每一筆操作產生的 canvas item id 列表

        # 當前操作暫存
        self._start_x = 0
        self._start_y = 0
        self._current_points = []
        self._current_item = None
        self._spotlight_mask_item = None
        self._spotlight_ring_item = None

        # 懸浮工具列元素
        self.toolbar_frame = None
        self.toolbar_win_id = None
        self._tb_drag_start_x = 0
        self._tb_drag_start_y = 0
        self._tool_btns = {}
        self._color_indicators = {}
        self._width_btns = {}

    @property
    def is_active(self) -> bool:
        return self._is_active

    def toggle(self):
        """切換顯示或關閉塗鴉模式"""
        if self._is_active:
            self.close()
        else:
            self.open()

    def open(self):
        """開啟全螢幕塗鴉與聚光燈畫布"""
        if self._is_active and self.win is not None:
            try:
                self.win.deiconify()
                self.win.lift()
                return
            except Exception:
                pass

        self._is_active = True
        self._build_overlay_window()

    def close(self):
        """關閉塗鴉畫布並還原桌面控制權"""
        if not self._is_active:
            return
        self._is_active = False

        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None
            self.canvas = None
            self.toolbar_frame = None
            self.toolbar_win_id = None

        if self.on_close_cb:
            try:
                self.on_close_cb()
            except Exception:
                pass

    def _build_overlay_window(self):
        """建立全螢幕透明置頂視窗"""
        win = tk.Toplevel(self.root)
        self.win = win
        win.title("AURA REC — 螢幕即時塗鴉與聚光燈")

        bg_color = "#000000"
        if IS_MAC:
            try:
                win.wm_attributes("-transparent", 1)
                win.config(bg="systemTransparent")
                bg_color = "systemTransparent"
            except Exception:
                pass
        elif IS_WINDOWS:
            try:
                win.wm_attributes("-transparentcolor", "#010101")
                win.config(bg="#010101")
                bg_color = "#010101"
            except Exception:
                pass
        else:
            try:
                win.attributes("-alpha", 0.90)
                win.config(bg="#121214")
                bg_color = "#121214"
            except Exception:
                pass

        try:
            win.attributes("-topmost", True)
        except Exception:
            pass

        try:
            win.attributes("-fullscreen", True)
        except Exception:
            w = win.winfo_screenwidth()
            h = win.winfo_screenheight()
            win.geometry(f"{w}x{h}+0+0")

        # 畫布建立
        canvas = tk.Canvas(win, bg=bg_color, highlightthickness=0, cursor="crosshair")
        canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas = canvas

        # 滑鼠事件綁定
        canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        canvas.bind("<B1-Motion>", self._on_mouse_drag)
        canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        canvas.bind("<Motion>", self._on_mouse_move)

        # 鍵盤事件綁定
        win.bind("<Escape>", lambda e: self.close())
        win.bind("<Control-z>", lambda e: self.undo())
        win.bind("<Command-z>", lambda e: self.undo())
        win.bind("<c>", lambda e: self.clear())
        win.bind("<C>", lambda e: self.clear())
        win.bind("<Delete>", lambda e: self.clear())
        win.bind("<Key-1>", lambda e: self.set_tool(TOOL_PEN))
        win.bind("<Key-2>", lambda e: self.set_tool(TOOL_ARROW))
        win.bind("<Key-3>", lambda e: self.set_tool(TOOL_RECT))
        win.bind("<Key-4>", lambda e: self.set_tool(TOOL_SPOTLIGHT))

        # 建立嵌入式懸浮工具列
        self._build_floating_toolbar()

        # 若初始工具為聚光燈，立刻初始化聚光燈
        if self.active_tool == TOOL_SPOTLIGHT:
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            self._update_spotlight(sw // 2, sh // 2)

    def _build_floating_toolbar(self):
        """在畫布頂部建立 Recordly 霓虹風格之懸浮工具列"""
        tb = tk.Frame(
            self.canvas,
            bg="#0B0D13",
            highlightbackground="#1E2330",
            highlightthickness=1,
            padx=8,
            pady=5,
        )
        self.toolbar_frame = tb

        # 1. 拖曳握把
        grip = tk.Label(
            tb,
            text="⋮⋮ 塗鴉工具",
            font=("Helvetica", 10, "bold"),
            fg="#00F0FF",
            bg="#0B0D13",
            cursor="fleur",
            padx=6,
        )
        grip.pack(side=tk.LEFT, padx=(0, 6))
        grip.bind("<ButtonPress-1>", self._start_toolbar_drag)
        grip.bind("<B1-Motion>", self._on_toolbar_drag)

        def make_sep():
            sep = tk.Frame(tb, bg="#1E2330", width=1, height=22)
            sep.pack(side=tk.LEFT, padx=6)
            return sep

        # 2. 核心工具按鈕 (畫筆, 箭頭, 矩形, 聚光燈)
        tool_defs = [
            (TOOL_PEN, "🖌️ 畫筆 [1]"),
            (TOOL_ARROW, "➔ 箭頭 [2]"),
            (TOOL_RECT, "▢ 矩形 [3]"),
            (TOOL_SPOTLIGHT, "🔦 聚光燈 [4]"),
        ]

        self._tool_btns = {}
        for code, label in tool_defs:
            btn = tk.Button(
                tb,
                text=label,
                font=("Helvetica", 10, "bold"),
                bg="#151922" if self.active_tool != code else "#00F0FF",
                fg="#E2E8F0" if self.active_tool != code else "#000000",
                activebackground="#00F0FF",
                activeforeground="#000000",
                bd=0,
                padx=8,
                pady=3,
                cursor="hand2",
                command=lambda c=code: self.set_tool(c),
            )
            btn.pack(side=tk.LEFT, padx=2)
            self._tool_btns[code] = btn

        make_sep()

        # 3. 顏色選擇球
        self._color_indicators = {}
        for hex_code, name in COLORS:
            is_sel = (self.active_color == hex_code)
            c_box = tk.Frame(
                tb,
                bg="#00F0FF" if is_sel else "#0B0D13",
                padx=2,
                pady=2,
                cursor="hand2",
            )
            c_box.pack(side=tk.LEFT, padx=3)
            c_dot = tk.Label(
                c_box,
                bg=hex_code,
                width=2,
                height=1,
                cursor="hand2",
            )
            c_dot.pack()
            c_dot.bind("<Button-1>", lambda e, c=hex_code: self.set_color(c))
            c_box.bind("<Button-1>", lambda e, c=hex_code: self.set_color(c))
            self._color_indicators[hex_code] = c_box

        make_sep()

        # 4. 筆觸粗細選擇
        self._width_btns = {}
        for w_val, w_label in WIDTHS:
            is_w_sel = (self.active_width == w_val)
            w_btn = tk.Button(
                tb,
                text=w_label,
                font=("Helvetica", 9, "bold"),
                bg="#1E2330" if not is_w_sel else "#00F0FF",
                fg="#E2E8F0" if not is_w_sel else "#000000",
                activebackground="#00F0FF",
                activeforeground="#000000",
                bd=0,
                padx=6,
                pady=2,
                cursor="hand2",
                command=lambda wv=w_val: self.set_width(wv),
            )
            w_btn.pack(side=tk.LEFT, padx=1)
            self._width_btns[w_val] = w_btn

        make_sep()

        # 5. 操作按鈕 (復原, 清除, 關閉)
        btn_undo = tk.Button(
            tb,
            text="↩ 復原",
            font=("Helvetica", 9),
            bg="#151922",
            fg="#94A3B8",
            activebackground="#1E2330",
            activeforeground="#FFFFFF",
            bd=0,
            padx=6,
            pady=3,
            cursor="hand2",
            command=self.undo,
        )
        btn_undo.pack(side=tk.LEFT, padx=2)

        btn_clear = tk.Button(
            tb,
            text="🧹 清空",
            font=("Helvetica", 9),
            bg="#151922",
            fg="#FF2A6D",
            activebackground="#FF2A6D",
            activeforeground="#FFFFFF",
            bd=0,
            padx=6,
            pady=3,
            cursor="hand2",
            command=self.clear,
        )
        btn_clear.pack(side=tk.LEFT, padx=2)

        btn_exit = tk.Button(
            tb,
            text="✕ 退出 [Esc]",
            font=("Helvetica", 9, "bold"),
            bg="#221118",
            fg="#FF2A6D",
            activebackground="#FF2A6D",
            activeforeground="#FFFFFF",
            bd=0,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self.close,
        )
        btn_exit.pack(side=tk.LEFT, padx=(4, 0))

        # 將工具列嵌入 Canvas 頂部中央
        sw = self.win.winfo_screenwidth()
        init_x = max(380, sw // 2)
        init_y = 52
        self.toolbar_win_id = self.canvas.create_window(init_x, init_y, window=tb)

    def _start_toolbar_drag(self, event):
        self._tb_drag_start_x = event.x
        self._tb_drag_start_y = event.y

    def _on_toolbar_drag(self, event):
        if not self.toolbar_win_id or not self.canvas:
            return
        cur_coords = self.canvas.coords(self.toolbar_win_id)
        if not cur_coords:
            return
        cx, cy = cur_coords
        dx = event.x - self._tb_drag_start_x
        dy = event.y - self._tb_drag_start_y
        self.canvas.coords(self.toolbar_win_id, cx + dx, cy + dy)

    def set_tool(self, tool_name: str):
        """切換繪圖工具"""
        self.active_tool = tool_name
        for code, btn in self._tool_btns.items():
            if code == tool_name:
                btn.config(bg="#00F0FF", fg="#000000")
            else:
                btn.config(bg="#151922", fg="#E2E8F0")

        if tool_name == TOOL_SPOTLIGHT:
            if self.canvas and self.win:
                sw = self.win.winfo_screenwidth()
                sh = self.win.winfo_screenheight()
                self._update_spotlight(sw // 2, sh // 2)
        else:
            self._clear_spotlight()

    def set_color(self, hex_color: str):
        """切換塗鴉顏色"""
        self.active_color = hex_color
        for c_code, frame in self._color_indicators.items():
            if c_code == hex_color:
                frame.config(bg="#00F0FF")
            else:
                frame.config(bg="#0B0D13")

        if self.active_tool == TOOL_SPOTLIGHT and self._spotlight_ring_item:
            try:
                self.canvas.itemconfig(self._spotlight_ring_item, outline=hex_color)
            except Exception:
                pass

    def set_width(self, width_val: int):
        """切換筆觸粗細"""
        self.active_width = width_val
        for wv, btn in self._width_btns.items():
            if wv == width_val:
                btn.config(bg="#00F0FF", fg="#000000")
            else:
                btn.config(bg="#1E2330", fg="#E2E8F0")

    def _on_mouse_down(self, event):
        self._start_x = event.x
        self._start_y = event.y
        self._current_points = [event.x, event.y]

        if self.active_tool == TOOL_PEN:
            self._current_item = self.canvas.create_line(
                event.x, event.y, event.x, event.y,
                fill=self.active_color,
                width=self.active_width,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND,
                smooth=True,
            )
        elif self.active_tool == TOOL_ARROW:
            self._current_item = self.canvas.create_line(
                event.x, event.y, event.x, event.y,
                fill=self.active_color,
                width=self.active_width,
                arrow=tk.LAST,
                arrowshape=(16 + self.active_width, 20 + self.active_width, 6 + self.active_width // 2),
                capstyle=tk.ROUND,
            )
        elif self.active_tool == TOOL_RECT:
            self._current_item = self.canvas.create_rectangle(
                event.x, event.y, event.x, event.y,
                outline=self.active_color,
                width=self.active_width,
            )
        elif self.active_tool == TOOL_SPOTLIGHT:
            self._update_spotlight(event.x, event.y)

        if self.toolbar_win_id:
            self.canvas.tag_raise(self.toolbar_win_id)

    def _on_mouse_drag(self, event):
        if self.active_tool == TOOL_PEN and self._current_item:
            self._current_points.extend([event.x, event.y])
            self.canvas.coords(self._current_item, *self._current_points)
        elif self.active_tool == TOOL_ARROW and self._current_item:
            self.canvas.coords(self._current_item, self._start_x, self._start_y, event.x, event.y)
        elif self.active_tool == TOOL_RECT and self._current_item:
            self.canvas.coords(self._current_item, self._start_x, self._start_y, event.x, event.y)
        elif self.active_tool == TOOL_SPOTLIGHT:
            self._update_spotlight(event.x, event.y)

        if self.toolbar_win_id:
            self.canvas.tag_raise(self.toolbar_win_id)

    def _on_mouse_up(self, event):
        if self._current_item:
            self.history.append([self._current_item])
            self._current_item = None
            self._current_points = []
        if self.toolbar_win_id:
            self.canvas.tag_raise(self.toolbar_win_id)

    def _on_mouse_move(self, event):
        if self.active_tool == TOOL_SPOTLIGHT:
            self._update_spotlight(event.x, event.y)

    def _update_spotlight(self, cx: int, cy: int):
        """更新動態聚光燈遮罩與霓虹光環"""
        if not self.canvas or not self.win:
            return

        w = self.win.winfo_screenwidth()
        h = self.win.winfo_screenheight()
        r = self.spotlight_radius

        # 計算外環 (順時針全螢幕) + 內環 (逆時針圓形開孔) 之多邊形點集合
        pts = [0, 0, w, 0, w, h, 0, h, 0, cy]
        num_segments = 32
        for i in range(num_segments + 1):
            angle = 2 * math.pi * i / num_segments
            pts.append(cx + r * math.cos(angle))
            pts.append(cy - r * math.sin(angle))
        pts.extend([0, cy, 0, 0])

        if not self._spotlight_mask_item:
            self._spotlight_mask_item = self.canvas.create_polygon(
                pts,
                fill="#000000",
                stipple="gray50",
            )
            self._spotlight_ring_item = self.canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                outline=self.active_color,
                width=3,
            )
        else:
            self.canvas.coords(self._spotlight_mask_item, *pts)
            self.canvas.coords(self._spotlight_ring_item, cx - r, cy - r, cx + r, cy + r)
            self.canvas.itemconfig(self._spotlight_ring_item, outline=self.active_color)

        # 確保聚光燈在筆記線條下層，但工具列在最頂層
        if self._spotlight_mask_item:
            self.canvas.tag_lower(self._spotlight_mask_item)
        if self._spotlight_ring_item:
            self.canvas.tag_raise(self._spotlight_ring_item)
        if self.toolbar_win_id:
            self.canvas.tag_raise(self.toolbar_win_id)

    def _clear_spotlight(self):
        """移除聚光燈遮罩"""
        if self.canvas:
            if self._spotlight_mask_item:
                try:
                    self.canvas.delete(self._spotlight_mask_item)
                except Exception:
                    pass
                self._spotlight_mask_item = None
            if self._spotlight_ring_item:
                try:
                    self.canvas.delete(self._spotlight_ring_item)
                except Exception:
                    pass
                self._spotlight_ring_item = None

    def undo(self):
        """復原上一筆繪製項目"""
        if not self.history or not self.canvas:
            return
        last_items = self.history.pop()
        for item_id in last_items:
            try:
                self.canvas.delete(item_id)
            except Exception:
                pass

    def clear(self):
        """清空畫面上所有自訂塗鴉筆記 (保留聚光燈與工具列)"""
        if not self.canvas:
            return
        while self.history:
            self.undo()
        self._current_item = None
        self._current_points = []
