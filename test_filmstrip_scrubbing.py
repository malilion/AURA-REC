"""
Tests for filmstrip timeline hover scrubbing and draggable In/Out handles.
"""

import os
import unittest
from unittest.mock import MagicMock, patch
import tkinter as tk

class MockEvent:
    def __init__(self, x, y):
        self.x = x
        self.y = y

class TestFilmstripScrubbing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        with patch('os.path.exists', return_value=True), patch('editor_window.VideoEditor') as mock_ve_cls:
            mock_editor = MagicMock()
            mock_editor.get_video_info.return_value = (100.0, 1920, 1080, 60.0)
            mock_editor.get_frame_ppm.return_value = None
            mock_ve_cls.return_value = mock_editor

            from editor_window import VideoEditorWindow
            with patch.object(VideoEditorWindow, 'load_video', return_value=None):
                self.app = VideoEditorWindow(self.root, video_path='/dummy/test.mp4')
                self.app.total_duration = 100.0
                self.app.start_sec = 10.0
                self.app.end_sec = 90.0
                self.app.current_time = 25.0
                self.app.filmstrip_canvas.config(width=800, height=76)

    def test_dimensions(self):
        w, h = self.app._get_filmstrip_dimensions()
        self.assertEqual(w, 800)
        self.assertEqual(h, 76)

    def test_hover_handles_and_track(self):
        # In handle is at x = 10/100 * 800 = 80
        self.app._on_filmstrip_motion(MockEvent(80, 38))
        self.assertEqual(self.app._hover_target, "in_handle")

        # Out handle is at x = 90/100 * 800 = 720
        self.app._on_filmstrip_motion(MockEvent(720, 38))
        self.assertEqual(self.app._hover_target, "out_handle")

        # Track hover at x = 400 (50s)
        self.app._on_filmstrip_motion(MockEvent(400, 38))
        self.assertEqual(self.app._hover_target, "track")
        self.assertAlmostEqual(self.app._skimmer_time, 50.0, delta=0.1)

    def test_drag_in_handle(self):
        # Press on in handle (x=80)
        self.app._on_filmstrip_press(MockEvent(80, 38))
        self.assertEqual(self.app._drag_target, "in_handle")

        # Drag to x=240 (30.0s)
        self.app._on_filmstrip_drag(MockEvent(240, 38))
        self.assertAlmostEqual(self.app.start_sec, 30.0, delta=0.2)

        # Release
        self.app._on_filmstrip_release(MockEvent(240, 38))
        self.assertIsNone(self.app._drag_target)

    def test_drag_out_handle(self):
        # Press on out handle (x=720)
        self.app._on_filmstrip_press(MockEvent(720, 38))
        self.assertEqual(self.app._drag_target, "out_handle")

        # Drag to x=560 (70.0s)
        self.app._on_filmstrip_drag(MockEvent(560, 38))
        self.assertAlmostEqual(self.app.end_sec, 70.0, delta=0.2)

        # Release
        self.app._on_filmstrip_release(MockEvent(560, 38))
        self.assertIsNone(self.app._drag_target)

    def test_leave_resets_skimmer(self):
        self.app._on_filmstrip_motion(MockEvent(400, 38))
        self.assertIsNotNone(self.app._skimmer_x)
        self.app._on_filmstrip_leave(MockEvent(0, 0))
        self.assertIsNone(self.app._skimmer_x)
        self.assertIsNone(self.app._hover_target)

if __name__ == '__main__':
    unittest.main()
