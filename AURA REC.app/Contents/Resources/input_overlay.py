"""
input_overlay.py - AURA REC 滑鼠點擊發光波紋 (Click Ripple) 與即時按鍵顯示 (Keystroke HUD)

功能說明：
1. 滑鼠點擊水波紋 (Click Ripple)：
   - 錄製時在使用者點擊位置 (x, y) 即時產生向外擴散漸變的霓虹發光漣漪 (Neon Aura Ripple)。
   - 左鍵呈現經典極光青藍色 (#00f0ff)，右鍵呈現活力珊瑚橘紅色 (#ff4d4f)。
   - 動畫約 260ms 平滑 ease-out 擴散並淡出，零延遲、不佔 CPU、自動銷毀。
2. 即時按鍵顯示 (Keystroke HUD)：
   - 錄製時於螢幕底部中央 (或自訂錄製區域底部) 浮現深色半透明膠囊藥丸條。
   - 支援 macOS 符號 (⌘, ⌥, ⌃, ⇧) 與 Windows 快捷鍵 (Ctrl, Alt, Shift, Win)。
   - 智慧顯示快捷鍵組合 (如 ⌘ C, ⇧ ⌘ 4) 與連續鍵盤輸入文字。
   - 停留約 1.4 秒後優雅隱藏。
3. 零外部依賴：
   - macOS 採用系統內建 CoreGraphics/CoreFoundation (ctypes)，
   - Windows 採用系統內建 user32 LowLevel Hooks (ctypes)，
   - 完全不需要第三方庫 (如 pynput、PyObjC)。
"""

import sys
import time
import math
import logging
import threading
import tkinter as tk
from typing import Optional, Tuple, Set

logger = logging.getLogger("AuraInputOverlay")

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform.startswith("win")

# ==============================================================================
# 鍵盤映射與符號 (macOS & Windows)
# ==============================================================================

MAC_KEYCODE_MAP = {
    0: "A", 1: "S", 2: "D", 3: "F", 4: "H", 5: "G", 6: "Z", 7: "X", 8: "C", 9: "V",
    11: "B", 12: "Q", 13: "W", 14: "E", 15: "R", 16: "Y", 17: "T", 18: "1", 19: "2",
    20: "3", 21: "4", 22: "6", 23: "5", 24: "=", 25: "9", 26: "7", 27: "-", 28: "8",
    29: "0", 30: "]", 31: "O", 32: "U", 33: "[", 34: "I", 35: "P", 36: "⏎", 37: "L",
    38: "J", 39: "'", 40: "K", 41: ";", 42: "\\", 43: ",", 44: "/", 45: "N", 46: "M",
    47: ".", 48: "⇥ Tab", 49: "␣", 50: "`", 51: "⌫", 53: "⎋ Esc",
    65: ".", 67: "*", 69: "+", 71: "Clear", 75: "/", 76: "⏎", 78: "-", 81: "=",
    82: "0", 83: "1", 84: "2", 85: "3", 86: "4", 87: "5", 88: "6", 89: "7", 91: "8", 92: "9",
    96: "F5", 97: "F6", 98: "F7", 99: "F3", 100: "F8", 101: "F9", 103: "F11", 105: "F13",
    107: "F14", 109: "F10", 111: "F12", 114: "Help", 115: "Home", 116: "PgUp",
    117: "⌦", 118: "F4", 119: "End", 120: "F2", 121: "PgDn", 122: "F1",
    123: "←", 124: "→", 125: "↓", 126: "↑",
}

WIN_VK_MAP = {
    0x08: "⌫", 0x09: "⇥ Tab", 0x0D: "⏎", 0x1B: "⎋ Esc", 0x20: "␣",
    0x21: "PgUp", 0x22: "PgDn", 0x23: "End", 0x24: "Home",
    0x25: "←", 0x26: "↑", 0x27: "→", 0x28: "↓", 0x2E: "⌦",
    0x30: "0", 0x31: "1", 0x32: "2", 0x33: "3", 0x34: "4",
    0x35: "5", 0x36: "6", 0x37: "7", 0x38: "8", 0x39: "9",
    0x41: "A", 0x42: "B", 0x43: "C", 0x44: "D", 0x45: "E", 0x46: "F",
    0x47: "G", 0x48: "H", 0x49: "I", 0x4A: "J", 0x4B: "K", 0x4C: "L",
    0x4D: "M", 0x4E: "N", 0x4F: "O", 0x50: "P", 0x51: "Q", 0x52: "R",
    0x53: "S", 0x54: "T", 0x55: "U", 0x56: "V", 0x57: "W", 0x58: "X",
    0x59: "Y", 0x5A: "Z",
    0x70: "F1", 0x71: "F2", 0x72: "F3", 0x73: "F4", 0x74: "F5", 0x75: "F6",
    0x76: "F7", 0x77: "F8", 0x78: "F9", 0x79: "F10", 0x7A: "F11", 0x7B: "F12",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/",
    0xC0: "`", 0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
}


# ==============================================================================
# macOS 原生輸入監聽器 (CoreGraphics CGEventTap + CoreFoundation RunLoop)
# ==============================================================================

class MacInputListener:
    """macOS 輕量級全域滑鼠與按鍵監聽器 (無外部依賴)"""

    def __init__(self, on_click=None, on_key=None):
        self.on_click = on_click
        self.on_key = on_key
        self._thread: Optional[threading.Thread] = None
        self._run_loop = None
        self._port = None
        self._source = None
        self._cb_ref = None
        self._is_running = False

    def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._thread = threading.Thread(target=self._run_loop_worker, daemon=True)
        self._thread.start()

    def stop(self):
        self._is_running = False
        try:
            if self._run_loop:
                import ctypes
                from ctypes import util
                cf = ctypes.cdll.LoadLibrary(util.find_library("CoreFoundation"))
                cf.CFRunLoopStop.argtypes = [ctypes.c_void_p]
                cf.CFRunLoopStop.restype = None
                cf.CFRunLoopWakeUp.argtypes = [ctypes.c_void_p]
                cf.CFRunLoopWakeUp.restype = None
                cf.CFRunLoopStop(self._run_loop)
                cf.CFRunLoopWakeUp(self._run_loop)
        except Exception as e:
            logger.debug("CoreFoundation runloop stop error: %s", e)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.6)
        self._thread = None
        self._run_loop = None

    def _run_loop_worker(self):
        import ctypes
        from ctypes import util

        cg = ctypes.cdll.LoadLibrary(util.find_library("CoreGraphics"))
        cf = ctypes.cdll.LoadLibrary(util.find_library("CoreFoundation"))

        class CGPoint(ctypes.Structure):
            _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

        cg.CGEventGetLocation.restype = CGPoint
        cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]

        cg.CGEventGetFlags.restype = ctypes.c_uint64
        cg.CGEventGetFlags.argtypes = [ctypes.c_void_p]

        cg.CGEventGetIntegerValueField.restype = ctypes.c_int64
        cg.CGEventGetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_uint32]

        cg.CGEventTapEnable.restype = None
        cg.CGEventTapEnable.argtypes = [ctypes.c_void_p, ctypes.c_bool]

        CALLBACK_FUNC = ctypes.CFUNCTYPE(
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p
        )

        def tap_callback(proxy, type_, event, refcon):
            # 自動處理 timeout 導致 tap 被關閉的情況
            if type_ in (0xFFFFFFFE, 0xFFFFFFFF):
                if self._port:
                    cg.CGEventTapEnable(self._port, True)
                return event

            try:
                # 滑鼠左鍵 (1) 與右鍵 (3)
                if type_ == 1 or type_ == 3:
                    if self.on_click:
                        pt = cg.CGEventGetLocation(event)
                        is_right = (type_ == 3)
                        self.on_click(int(pt.x), int(pt.y), is_right)

                # 按鍵事件 (10: kCGEventKeyDown)
                elif type_ == 10:
                    if self.on_key:
                        keycode = int(cg.CGEventGetIntegerValueField(event, 59))  # kCGKeyboardEventKeycode = 59
                        flags = int(cg.CGEventGetFlags(event))
                        mods = []
                        if flags & 0x00040000:  # Control
                            mods.append("⌃")
                        if flags & 0x00080000:  # Option
                            mods.append("⌥")
                        if flags & 0x00020000:  # Shift
                            mods.append("⇧")
                        if flags & 0x00100000:  # Command
                            mods.append("⌘")

                        raw_key = MAC_KEYCODE_MAP.get(keycode)
                        if raw_key:
                            self.on_key(mods, raw_key)
            except Exception as e:
                logger.debug("Tap callback handle error: %s", e)

            return event

        self._cb_ref = CALLBACK_FUNC(tap_callback)

        cg.CGEventTapCreate.restype = ctypes.c_void_p
        cg.CGEventTapCreate.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_uint64, CALLBACK_FUNC, ctypes.c_void_p
        ]

        cf.CFMachPortCreateRunLoopSource.restype = ctypes.c_void_p
        cf.CFMachPortCreateRunLoopSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long]

        cf.CFRunLoopGetCurrent.restype = ctypes.c_void_p
        cf.CFRunLoopGetCurrent.argtypes = []
        cf.CFRunLoopAddSource.restype = None
        cf.CFRunLoopAddSource.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        cf.CFRunLoopRun.restype = None
        cf.CFRunLoopRun.argtypes = []
        cf.CFRunLoopStop.restype = None
        cf.CFRunLoopStop.argtypes = [ctypes.c_void_p]
        cf.CFRunLoopWakeUp.restype = None
        cf.CFRunLoopWakeUp.argtypes = [ctypes.c_void_p]
        cf.CFRelease.restype = None
        cf.CFRelease.argtypes = [ctypes.c_void_p]

        cf.kCFRunLoopCommonModes = ctypes.c_void_p.in_dll(cf, "kCFRunLoopCommonModes")

        # 監聽 LeftMouseDown(1), RightMouseDown(3), KeyDown(10)
        events_mask = (1 << 1) | (1 << 3) | (1 << 10)
        # kCGSessionEventTap = 1, kCGHeadInsertEventTap = 0, kCGEventTapOptionListenOnly = 1
        self._port = cg.CGEventTapCreate(1, 0, 1, events_mask, self._cb_ref, None)

        if not self._port:
            logger.warning("CoreGraphics Event Tap 建立失敗（可能需於「系統設定 -> 隱私權與安全性 -> 輔助使用」授權）")
            self._is_running = False
            return

        self._source = cf.CFMachPortCreateRunLoopSource(None, self._port, 0)
        self._run_loop = cf.CFRunLoopGetCurrent()
        cf.CFRunLoopAddSource(self._run_loop, self._source, cf.kCFRunLoopCommonModes)

        cf.CFRunLoopRun()

        # 清理資源
        try:
            if self._port:
                cg.CGEventTapEnable(self._port, False)
            if self._source:
                cf.CFRelease(self._source)
            if self._port:
                cf.CFRelease(self._port)
        except Exception:
            pass


# ==============================================================================
# Windows 原生輸入監聽器 (SetWindowsHookExW)
# ==============================================================================

class WinInputListener:
    """Windows 輕量級全域滑鼠與按鍵監聽器 (LowLevel Hooks)"""

    def __init__(self, on_click=None, on_key=None):
        self.on_click = on_click
        self.on_key = on_key
        self._thread: Optional[threading.Thread] = None
        self._is_running = False
        self._thread_id = None
        self._mouse_hook = None
        self._kbd_hook = None

    def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self):
        self._is_running = False
        if self._thread_id:
            try:
                import ctypes
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.6)
        self._thread = None

    def _worker(self):
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        self._thread_id = kernel32.GetCurrentThreadId()

        class POINT(ctypes.Structure):
            _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("pt", POINT),
                ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p),
            ]

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p),
            ]

        HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        def mouse_proc(nCode, wParam, lParam):
            if nCode >= 0:
                # WM_LBUTTONDOWN = 0x0201, WM_RBUTTONDOWN = 0x0204
                if wParam == 0x0201 or wParam == 0x0204:
                    if self.on_click:
                        info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                        is_right = (wParam == 0x0204)
                        self.on_click(int(info.pt.x), int(info.pt.y), is_right)
            return user32.CallNextHookEx(self._mouse_hook, nCode, wParam, lParam)

        def kbd_proc(nCode, wParam, lParam):
            if nCode >= 0:
                # WM_KEYDOWN = 0x0100, WM_SYSKEYDOWN = 0x0104
                if wParam == 0x0100 or wParam == 0x0104:
                    if self.on_key:
                        info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                        vk = info.vkCode

                        mods = []
                        if user32.GetAsyncKeyState(0x11) & 0x8000:  # VK_CONTROL
                            mods.append("Ctrl")
                        if user32.GetAsyncKeyState(0x12) & 0x8000:  # VK_MENU (Alt)
                            mods.append("Alt")
                        if user32.GetAsyncKeyState(0x10) & 0x8000:  # VK_SHIFT
                            mods.append("Shift")
                        if (user32.GetAsyncKeyState(0x5B) & 0x8000) or (user32.GetAsyncKeyState(0x5C) & 0x8000):  # Win
                            mods.append("Win")

                        raw_key = WIN_VK_MAP.get(vk)
                        if raw_key:
                            self.on_key(mods, raw_key)
            return user32.CallNextHookEx(self._kbd_hook, nCode, wParam, lParam)

        self._mouse_cb = HOOKPROC(mouse_proc)
        self._kbd_cb = HOOKPROC(kbd_proc)

        # WH_MOUSE_LL = 14, WH_KEYBOARD_LL = 13
        self._mouse_hook = user32.SetWindowsHookExW(14, self._mouse_cb, None, 0)
        self._kbd_hook = user32.SetWindowsHookExW(13, self._kbd_cb, None, 0)

        msg = wintypes.MSG()
        while self._is_running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._mouse_hook:
            user32.UnhookWindowsHookEx(self._mouse_hook)
        if self._kbd_hook:
            user32.UnhookWindowsHookEx(self._kbd_hook)


# ==============================================================================
# 共通 Fallback 監聽器
# ==============================================================================

class DummyInputListener:
    def __init__(self, on_click=None, on_key=None):
        pass
    def start(self):
        pass
    def stop(self):
        pass


def create_platform_input_listener(on_click, on_key):
    """根據當前作業系統建立最合適的原生監聽器"""
    if IS_MAC:
        return MacInputListener(on_click=on_click, on_key=on_key)
    elif IS_WINDOWS:
        return WinInputListener(on_click=on_click, on_key=on_key)
    return DummyInputListener(on_click=on_click, on_key=on_key)


# ==============================================================================
# 滑鼠點擊發光水波紋 (ClickRippleWindow)
# ==============================================================================

class ClickRippleWindow:
    """在螢幕指定座標播放極光發光水波紋漣漪 (Click Ripple)"""

    def __init__(self, parent_root: tk.Tk, x: int, y: int, is_right: bool = False, on_finish=None):
        self.root = parent_root
        self.on_finish = on_finish
        self.size = 96
        self.cx = self.size // 2
        self.cy = self.size // 2
        self.step = 0
        self.total_steps = 11

        self.win = tk.Toplevel(parent_root)
        self.win.overrideredirect(True)
        try:
            if IS_MAC:
                self.win.attributes("-transparent", True)
                self.win.config(bg="systemTransparent")
            elif IS_WINDOWS:
                self.win.attributes("-transparentcolor", "#000001")
                self.win.config(bg="#000001")
        except Exception:
            pass

        try:
            self.win.attributes("-topmost", True)
        except Exception:
            pass

        # 居中放置於點擊座標
        win_x = max(0, x - self.cx)
        win_y = max(0, y - self.cy)
        self.win.geometry(f"{self.size}x{self.size}+{win_x}+{win_y}")

        bg_color = "systemTransparent" if IS_MAC else ("#000001" if IS_WINDOWS else "#111111")
        self.canvas = tk.Canvas(
            self.win,
            width=self.size,
            height=self.size,
            bg=bg_color,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        # 漣漪顏色漸層 (左鍵為極光藍，右鍵為活力珊瑚橙紅)
        if not is_right:
            self.palette = [
                "#00f0ff", "#22d3ee", "#38bdf8", "#0ea5e9",
                "#0284c7", "#0369a1", "#075985", "#0c4a6e"
            ]
        else:
            self.palette = [
                "#ff4d4f", "#fb7185", "#f43f5e", "#e11d48",
                "#be123c", "#9f1239", "#881337", "#4c0519"
            ]

        self._tick()

    def _tick(self):
        if self.step >= self.total_steps:
            self.destroy()
            return

        self.canvas.delete("all")
        # 二次方減速 (Quadratic Ease-out)
        t = self.step / float(self.total_steps)
        eased = 1.0 - (1.0 - t) * (1.0 - t)

        # 擴散半徑：從 8px 擴展至 38px
        r = 8.0 + eased * 30.0
        # 線條寬度：從 3.2px 遞減至 1.0px
        line_w = max(1.0, 3.2 - 2.0 * eased)

        color_idx = min(len(self.palette) - 1, int(eased * len(self.palette)))
        ring_color = self.palette[color_idx]

        # 繪製主漣漪外圈
        self.canvas.create_oval(
            self.cx - r, self.cy - r,
            self.cx + r, self.cy + r,
            outline=ring_color,
            width=line_w,
        )

        # 前幾幀在中心繪製輕微的實心觸發點，增強「點擊下壓」的回饋質感
        if self.step < 4:
            dot_r = max(1.0, 3.8 - self.step * 0.9)
            self.canvas.create_oval(
                self.cx - dot_r, self.cy - dot_r,
                self.cx + dot_r, self.cy + dot_r,
                fill=ring_color,
                outline="",
            )

        self.step += 1
        self.win.after(22, self._tick)

    def destroy(self):
        try:
            self.win.destroy()
        except Exception:
            pass
        if self.on_finish:
            try:
                self.on_finish(self)
            except Exception:
                pass


# ==============================================================================
# 即時按鍵顯示 (KeystrokeHudWindow)
# ==============================================================================

class KeystrokeHudWindow:
    """螢幕底部懸浮半透明膠囊按鍵 HUD (Keystroke Overlay)"""

    def __init__(self, parent_root: tk.Tk):
        self.root = parent_root
        self.win = tk.Toplevel(parent_root)
        self.win.overrideredirect(True)
        self.win.withdraw()  # 預設隱藏

        try:
            if IS_MAC:
                self.win.attributes("-transparent", True)
                self.win.config(bg="systemTransparent")
            elif IS_WINDOWS:
                self.win.attributes("-transparentcolor", "#000001")
                self.win.config(bg="#000001")
        except Exception:
            pass

        try:
            self.win.attributes("-topmost", True)
        except Exception:
            pass

        self.h = 52
        self.w = 220
        bg_color = "systemTransparent" if IS_MAC else ("#00f0ff" if False else ("#000001" if IS_WINDOWS else "#111111"))

        self.canvas = tk.Canvas(
            self.win,
            width=self.w,
            height=self.h,
            bg=bg_color,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self._hide_timer = None
        self._last_time = 0.0
        self._current_buffer = ""
        self._target_region = None

    def set_target_region(self, region: Optional[Tuple[int, int, int, int]]):
        """若正在錄製特定區域或視窗，將 HUD 放置於該區域底部中央"""
        self._target_region = region

    def show_key(self, mods, key: str):
        """接收到按鍵時更新 HUD 顯示並延長停留時間"""
        now = time.time()
        is_combo = bool(mods)

        # 格式化按鍵字串
        if is_combo:
            text = " ".join(mods) + " " + key
            self._current_buffer = ""
        else:
            # 單鍵：判斷是否為連續打字文字
            is_special = len(key) > 1 and key not in ("␣",)
            if is_special:
                text = key
                self._current_buffer = ""
            elif key == "␣":
                if self._current_buffer and (now - self._last_time) < 0.9:
                    self._current_buffer = (self._current_buffer + " ")[-22:]
                    text = self._current_buffer
                else:
                    text = "␣ Space"
                    self._current_buffer = ""
            elif key == "⌫":
                if self._current_buffer:
                    self._current_buffer = self._current_buffer[:-1]
                    text = self._current_buffer or "⌫"
                else:
                    text = "⌫"
            else:
                if (now - self._last_time) < 0.9 and self._current_buffer:
                    self._current_buffer = (self._current_buffer + key)[-22:]
                    text = self._current_buffer
                else:
                    self._current_buffer = key
                    text = key

        self._last_time = now
        self._render(text, is_combo)

    def _render(self, text: str, is_combo: bool):
        # 依字串長度動態調整膠囊寬度
        char_count = len(text)
        new_w = max(180, min(560, int(char_count * 16.5) + 64))
        self.w = new_w

        # 計算螢幕或錄製區域位置
        if self._target_region:
            rx, ry, rw, rh = self._target_region
            pos_x = rx + max(10, (rw - self.w) // 2)
            pos_y = ry + max(20, rh - self.h - 28)
        else:
            sw = self.win.winfo_screenwidth()
            sh = self.win.winfo_screenheight()
            pos_x = (sw - self.w) // 2
            pos_y = sh - self.h - 90

        self.win.geometry(f"{self.w}x{self.h}+{pos_x}+{pos_y}")
        self.canvas.config(width=self.w, height=self.h)
        self.canvas.delete("all")

        # 繪製現代深色圓角膠囊 (Glass Pill)
        r = self.h // 2
        pill_bg = "#111116"
        border_col = "#00f0ff" if is_combo else "#2e2e38"
        border_w = 1.6 if is_combo else 1.2

        # 膠囊背景與邊框
        self.canvas.create_oval(2, 2, self.h - 2, self.h - 2, fill=pill_bg, outline=border_col, width=border_w)
        self.canvas.create_oval(self.w - self.h + 2, 2, self.w - 2, self.h - 2, fill=pill_bg, outline=border_col, width=border_w)
        self.canvas.create_rectangle(r, 2, self.w - r, self.h - 2, fill=pill_bg, outline=pill_bg)
        self.canvas.create_line(r, 2, self.w - r, 2, fill=border_col, width=border_w)
        self.canvas.create_line(r, self.h - 2, self.w - r, self.h - 2, fill=border_col, width=border_w)

        # 快捷鍵時在頂部加入極細極光青色微光條
        if is_combo:
            self.canvas.create_line(r + 10, 4, self.w - r - 10, 4, fill="#00f0ff", width=1.5)

        # 繪製按鍵文字
        font_size = 17 if len(text) <= 12 else (15 if len(text) <= 18 else 13)
        font_tuple = ("SF Pro Display", font_size, "bold") if IS_MAC else ("Segoe UI", font_size, "bold")

        fg_col = "#00f0ff" if is_combo else "#f4f4f5"
        self.canvas.create_text(
            self.w // 2,
            self.h // 2,
            text=text,
            fill=fg_col,
            font=font_tuple,
        )

        try:
            self.win.deiconify()
            self.win.lift()
            self.win.attributes("-topmost", True)
        except Exception:
            pass

        # 重新排定自動淡出計時器 (1.4 秒後隱藏)
        if self._hide_timer:
            try:
                self.root.after_cancel(self._hide_timer)
            except Exception:
                pass
        self._hide_timer = self.root.after(1400, self._hide)

    def _hide(self):
        self._hide_timer = None
        self._current_buffer = ""
        try:
            self.win.withdraw()
        except Exception:
            pass

    def destroy(self):
        if self._hide_timer:
            try:
                self.root.after_cancel(self._hide_timer)
            except Exception:
                pass
            self._hide_timer = None
        try:
            self.win.destroy()
        except Exception:
            pass


# ==============================================================================
# 輸入覆蓋層總管理者 (InputOverlayManager)
# ==============================================================================

class InputOverlayManager:
    """協調整合滑鼠發光水波紋與按鍵顯示的生命週期管理器"""

    def __init__(self, parent_root: tk.Tk, ripple_enabled: bool = True, hud_enabled: bool = True, region=None):
        self.root = parent_root
        self.ripple_enabled = ripple_enabled
        self.hud_enabled = hud_enabled
        self.region = region

        self._active_ripples: Set[ClickRippleWindow] = set()
        self._hud: Optional[KeystrokeHudWindow] = None
        self._listener = None
        self._is_active = False

    def start(self):
        """啟動監聽器與 HUD"""
        if self._is_active:
            return
        self._is_active = True

        if self.hud_enabled:
            self._hud = KeystrokeHudWindow(self.root)
            self._hud.set_target_region(self.region)

        def _on_click_bg(x, y, is_right):
            if not self._is_active or not self.ripple_enabled:
                return
            # 排程至主線程建立水波紋動畫
            self.root.after(0, lambda: self._spawn_ripple(x, y, is_right))

        def _on_key_bg(mods, key):
            if not self._is_active or not self.hud_enabled:
                return
            # 排程至主線程更新 HUD
            self.root.after(0, lambda: self._update_hud(mods, key))

        self._listener = create_platform_input_listener(
            on_click=_on_click_bg,
            on_key=_on_key_bg,
        )
        self._listener.start()
        logger.info("AURA InputOverlayManager 已順利啟動 (Ripple=%s, HUD=%s)", self.ripple_enabled, self.hud_enabled)

    def stop(self):
        """停止監聽器並清理所有懸浮視窗"""
        if not self._is_active:
            return
        self._is_active = False

        if self._listener:
            try:
                self._listener.stop()
            except Exception as e:
                logger.debug("Stop listener error: %s", e)
            self._listener = None

        # 清除所有進行中的水波紋視窗
        for rip in list(self._active_ripples):
            try:
                rip.destroy()
            except Exception:
                pass
        self._active_ripples.clear()

        # 銷毀 HUD 視窗
        if self._hud:
            try:
                self._hud.destroy()
            except Exception:
                pass
            self._hud = None

        logger.info("AURA InputOverlayManager 已乾淨停止")

    def set_region(self, region):
        """更新當前錄影區域"""
        self.region = region
        if self._hud:
            self._hud.set_target_region(region)

    def set_ripple_enabled(self, enabled: bool):
        self.ripple_enabled = bool(enabled)

    def set_hud_enabled(self, enabled: bool):
        self.hud_enabled = bool(enabled)
        if not self.hud_enabled and self._hud:
            self._hud.destroy()
            self._hud = None
        elif self.hud_enabled and not self._hud and self._is_active:
            self._hud = KeystrokeHudWindow(self.root)
            self._hud.set_target_region(self.region)

    def _spawn_ripple(self, x: int, y: int, is_right: bool):
        if not self._is_active or not self.ripple_enabled:
            return
        # 限制同時間最多 6 個水波紋，避免極速連擊造成的負載
        if len(self._active_ripples) >= 6:
            oldest = next(iter(self._active_ripples))
            oldest.destroy()

        def _on_finish(rip):
            self._active_ripples.discard(rip)

        ripple = ClickRippleWindow(self.root, x, y, is_right=is_right, on_finish=_on_finish)
        self._active_ripples.add(ripple)

    def _update_hud(self, mods, key: str):
        if not self._is_active or not self.hud_enabled:
            return
        if not self._hud:
            self._hud = KeystrokeHudWindow(self.root)
            self._hud.set_target_region(self.region)
        self._hud.show_key(mods, key)
