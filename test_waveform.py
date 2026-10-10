"""
Tests for Audio Waveform extraction and Canvas rendering in VideoEditor and VideoEditorWindow.
"""

import os
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import tkinter as tk

from video_editor import VideoEditor

class MockEvent:
    def __init__(self, x, y):
        self.x = x
        self.y = y

class TestAudioWaveform(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

        cls.editor = VideoEditor()
        cls.temp_dir = tempfile.mkdtemp(prefix="aura_test_wf_")

        # 1. Video with speech burst (1s-3s burst, silence elsewhere)
        cls.test_audio_video = os.path.join(cls.temp_dir, "with_audio.mp4")
        cmd1 = [
            cls.editor.ffmpeg_bin, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=6:size=320x180:rate=30",
            "-filter_complex", "aevalsrc=0:d=1[sil1]; sine=f=440:d=2[s1]; aevalsrc=0:d=3[sil2]; [sil1][s1][sil2]concat=n=3:v=0:a=1[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
            cls.test_audio_video,
        ]
        subprocess.run(cmd1, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # 2. Silent video (no audio track)
        cls.test_silent_video = os.path.join(cls.temp_dir, "silent.mp4")
        cmd2 = [
            cls.editor.ffmpeg_bin, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=4:size=320x180:rate=30",
            "-c:v", "libx264", "-preset", "ultrafast", "-an",
            cls.test_silent_video,
        ]
        subprocess.run(cmd2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.temp_dir, ignore_errors=True)
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_extract_audio_waveform_with_audio(self):
        peaks = self.editor.extract_audio_waveform(self.test_audio_video, num_bins=60)
        self.assertEqual(len(peaks), 60)
        # All values should be between 0.0 and 1.0
        self.assertTrue(all(0.0 <= p <= 1.0 for p in peaks))
        # There should be loud peaks in speech section and near zero in silent section
        self.assertTrue(max(peaks) > 0.4)
        self.assertTrue(min(peaks) == 0.0)

    def test_extract_audio_waveform_silent_video(self):
        peaks = self.editor.extract_audio_waveform(self.test_silent_video, num_bins=60)
        self.assertEqual(peaks, [])

    def test_waveform_canvas_ui(self):
        with patch("os.path.exists", return_value=True), patch("editor_window.VideoEditor") as mock_ve_cls:
            mock_editor = MagicMock()
            mock_editor.get_video_info.return_value = (60.0, 1920, 1080, 60.0)
            mock_editor.get_frame_ppm.return_value = None
            mock_ve_cls.return_value = mock_editor

            from editor_window import VideoEditorWindow
            with patch.object(VideoEditorWindow, "load_video", return_value=None):
                app = VideoEditorWindow(self.root, video_path="/dummy/test.mp4")
                app.total_duration = 60.0
                app.start_sec = 10.0
                app.end_sec = 50.0
                app.current_time = 20.0

                # 1. Dimensions check
                w, h = app._get_waveform_dimensions()
                self.assertTrue(w >= 30)
                self.assertTrue(h >= 20)

                # 2. Loading state redraw
                app._waveform_loading = True
                app._redraw_waveform()

                # 3. Silent state redraw
                app._waveform_loading = False
                app.audio_waveform = []
                app._redraw_waveform()

                # 4. Populated peaks redraw
                app.audio_waveform = [0.1 * (i % 10) for i in range(100)]
                app._redraw_waveform()

                # 5. Motion on waveform
                app._on_waveform_motion(MockEvent(400, 22))
                self.assertIsNotNone(app._skimmer_x)
                self.assertAlmostEqual(app._skimmer_time, 30.0, delta=0.5)

                # 6. Click on waveform jumps playhead
                app._on_waveform_press(MockEvent(200, 22))
                self.assertAlmostEqual(app.current_time, 15.0, delta=0.5)

                # 7. Drag on waveform scrubs playhead
                app._on_waveform_drag(MockEvent(300, 22))
                self.assertAlmostEqual(app.current_time, 22.5, delta=0.5)

                # 8. Leave waveform clears skimmer
                app._on_waveform_leave(MockEvent(0, 0))
                self.assertIsNone(app._skimmer_x)

if __name__ == "__main__":
    unittest.main()
