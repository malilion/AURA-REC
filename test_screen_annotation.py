#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for Live Screen Annotation & Spotlight (螢幕即時塗鴉與聚光燈工具)
"""

import sys
import tkinter as tk
import unittest

from screen_annotation import (
    ScreenAnnotationOverlay,
    TOOL_PEN,
    TOOL_ARROW,
    TOOL_RECT,
    TOOL_SPOTLIGHT,
    COLORS,
    WIDTHS,
)


class DummyEvent:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class TestScreenAnnotation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
            cls.has_tk = True
        except Exception:
            cls.has_tk = False

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "has_tk", False) and cls.root:
            try:
                cls.root.destroy()
            except Exception:
                pass

    def setUp(self):
        if not self.has_tk:
            self.skipTest("Tkinter GUI display not available")
        self.closed_called = False

    def _on_close_cb(self):
        self.closed_called = True

    def test_init_state(self):
        overlay = ScreenAnnotationOverlay(self.root, on_close=self._on_close_cb)
        self.assertFalse(overlay.is_active)
        self.assertIsNone(overlay.win)
        self.assertEqual(overlay.active_tool, TOOL_PEN)
        self.assertEqual(overlay.active_color, "#00F0FF")
        self.assertEqual(overlay.active_width, 6)
        self.assertEqual(len(overlay.history), 0)

    def test_open_and_close(self):
        overlay = ScreenAnnotationOverlay(self.root, on_close=self._on_close_cb)
        overlay.open()
        self.assertTrue(overlay.is_active)
        self.assertIsNotNone(overlay.win)
        self.assertIsNotNone(overlay.canvas)
        self.assertIsNotNone(overlay.toolbar_frame)

        # Close
        overlay.close()
        self.assertFalse(overlay.is_active)
        self.assertIsNone(overlay.win)
        self.assertTrue(self.closed_called)

    def test_toggle(self):
        overlay = ScreenAnnotationOverlay(self.root, on_close=self._on_close_cb)
        overlay.toggle()
        self.assertTrue(overlay.is_active)
        overlay.toggle()
        self.assertFalse(overlay.is_active)

    def test_tool_switching(self):
        overlay = ScreenAnnotationOverlay(self.root, on_close=self._on_close_cb)
        overlay.open()

        overlay.set_tool(TOOL_ARROW)
        self.assertEqual(overlay.active_tool, TOOL_ARROW)

        overlay.set_tool(TOOL_RECT)
        self.assertEqual(overlay.active_tool, TOOL_RECT)

        overlay.set_tool(TOOL_SPOTLIGHT)
        self.assertEqual(overlay.active_tool, TOOL_SPOTLIGHT)
        self.assertIsNotNone(overlay._spotlight_mask_item)
        self.assertIsNotNone(overlay._spotlight_ring_item)

        # Switching back to Pen removes spotlight items
        overlay.set_tool(TOOL_PEN)
        self.assertEqual(overlay.active_tool, TOOL_PEN)
        self.assertIsNone(overlay._spotlight_mask_item)
        self.assertIsNone(overlay._spotlight_ring_item)

        overlay.close()

    def test_color_and_width_switching(self):
        overlay = ScreenAnnotationOverlay(self.root, on_close=self._on_close_cb)
        overlay.open()

        for hex_color, _ in COLORS:
            overlay.set_color(hex_color)
            self.assertEqual(overlay.active_color, hex_color)

        for w_val, _ in WIDTHS:
            overlay.set_width(w_val)
            self.assertEqual(overlay.active_width, w_val)

        overlay.close()

    def test_pen_drawing_and_undo(self):
        overlay = ScreenAnnotationOverlay(self.root, on_close=self._on_close_cb)
        overlay.open()
        overlay.set_tool(TOOL_PEN)

        # Draw a stroke
        overlay._on_mouse_down(DummyEvent(100, 100))
        overlay._on_mouse_drag(DummyEvent(120, 130))
        overlay._on_mouse_drag(DummyEvent(150, 160))
        overlay._on_mouse_up(DummyEvent(150, 160))

        self.assertEqual(len(overlay.history), 1)

        # Draw second stroke
        overlay._on_mouse_down(DummyEvent(200, 200))
        overlay._on_mouse_drag(DummyEvent(250, 250))
        overlay._on_mouse_up(DummyEvent(250, 250))

        self.assertEqual(len(overlay.history), 2)

        # Undo one stroke
        overlay.undo()
        self.assertEqual(len(overlay.history), 1)

        # Clear
        overlay.clear()
        self.assertEqual(len(overlay.history), 0)

        overlay.close()

    def test_arrow_and_rect_drawing(self):
        overlay = ScreenAnnotationOverlay(self.root, on_close=self._on_close_cb)
        overlay.open()

        # Arrow
        overlay.set_tool(TOOL_ARROW)
        overlay._on_mouse_down(DummyEvent(50, 50))
        overlay._on_mouse_drag(DummyEvent(150, 150))
        overlay._on_mouse_up(DummyEvent(150, 150))
        self.assertEqual(len(overlay.history), 1)

        # Rect
        overlay.set_tool(TOOL_RECT)
        overlay._on_mouse_down(DummyEvent(200, 200))
        overlay._on_mouse_drag(DummyEvent(300, 300))
        overlay._on_mouse_up(DummyEvent(300, 300))
        self.assertEqual(len(overlay.history), 2)

        # Undo both
        overlay.undo()
        self.assertEqual(len(overlay.history), 1)
        overlay.undo()
        self.assertEqual(len(overlay.history), 0)

        overlay.close()

    def test_spotlight_geometry_update(self):
        overlay = ScreenAnnotationOverlay(self.root, on_close=self._on_close_cb)
        overlay.open()
        overlay.set_tool(TOOL_SPOTLIGHT)

        # Move cursor to 300, 400
        overlay._on_mouse_move(DummyEvent(300, 400))
        self.assertIsNotNone(overlay._spotlight_mask_item)
        self.assertIsNotNone(overlay._spotlight_ring_item)

        ring_coords = overlay.canvas.coords(overlay._spotlight_ring_item)
        r = overlay.spotlight_radius
        # ring oval is [cx-r, cy-r, cx+r, cy+r]
        self.assertEqual(ring_coords, [300 - r, 400 - r, 300 + r, 400 + r])

        overlay.close()


if __name__ == "__main__":
    unittest.main()
