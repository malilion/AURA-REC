"""
Tests for Smart Cut (智慧無損裁切) in video_editor.py
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from video_editor import VideoEditor

class TestSmartCut(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.editor = VideoEditor()
        cls.temp_dir = tempfile.mkdtemp(prefix="aura_test_smartcut_")
        cls.test_video = os.path.join(cls.temp_dir, "test_source.mp4")

        # Generate a 10-second test video with keyframes every 2.0s (gop=60 at 30fps)
        cmd = [
            cls.editor.ffmpeg_bin, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=10:size=640x360:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=10",
            "-c:v", "libx264", "-g", "60", "-c:a", "aac",
            cls.test_video,
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_get_keyframes(self):
        kfs = self.editor.get_keyframes(self.test_video)
        self.assertTrue(len(kfs) >= 4, f"Expected >= 4 keyframes, got {kfs}")
        # Keyframes should include approximately 0.0, 2.0, 4.0, 6.0, 8.0
        self.assertAlmostEqual(kfs[0], 0.0, delta=0.1)
        self.assertTrue(any(abs(k - 2.0) < 0.1 for k in kfs))
        self.assertTrue(any(abs(k - 4.0) < 0.1 for k in kfs))

    def test_smart_cut_both_keyframes(self):
        # Case 1: 0.0 to 4.0 (both keyframes) -> pure stream copy
        out = os.path.join(self.temp_dir, "out_both_kf.mp4")
        ok, res = self.editor.trim_smart_cut(self.test_video, out, 0.0, 4.0)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(out))
        info = self.editor.get_video_info(out)
        self.assertIsNotNone(info)
        self.assertAlmostEqual(info["duration"], 4.0, delta=0.2)

    def test_smart_cut_start_kf_end_non_kf(self):
        # Case 2: 2.0 to 5.3 (start is keyframe 2.0, end is 5.3)
        out = os.path.join(self.temp_dir, "out_start_kf.mp4")
        ok, res = self.editor.trim_smart_cut(self.test_video, out, 2.0, 5.3)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(out))
        info = self.editor.get_video_info(out)
        self.assertIsNotNone(info)
        self.assertAlmostEqual(info["duration"], 3.3, delta=0.25)

    def test_smart_cut_start_non_kf_end_kf(self):
        # Case 3: 1.2 to 6.0 (start is 1.2, end is keyframe 6.0)
        out = os.path.join(self.temp_dir, "out_end_kf.mp4")
        ok, res = self.editor.trim_smart_cut(self.test_video, out, 1.2, 6.0)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(out))
        info = self.editor.get_video_info(out)
        self.assertIsNotNone(info)
        self.assertAlmostEqual(info["duration"], 4.8, delta=0.25)

    def test_smart_cut_single_gop(self):
        # Case 4: 2.3 to 3.7 (within single GOP [2.0, 4.0], no intermediate keyframe)
        out = os.path.join(self.temp_dir, "out_single_gop.mp4")
        ok, res = self.editor.trim_smart_cut(self.test_video, out, 2.3, 3.7)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(out))
        info = self.editor.get_video_info(out)
        self.assertIsNotNone(info)
        self.assertAlmostEqual(info["duration"], 1.4, delta=0.1)

    def test_smart_cut_full_three_parts(self):
        # Case 5: 1.1 to 7.3 (Head: 1.1->2.0, Body: 2.0->6.0, Tail: 6.0->7.3)
        out = os.path.join(self.temp_dir, "out_three_parts.mp4")
        ok, res = self.editor.trim_smart_cut(self.test_video, out, 1.1, 7.3)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(out))
        info = self.editor.get_video_info(out)
        self.assertIsNotNone(info)
        self.assertAlmostEqual(info["duration"], 6.2, delta=0.25)

    def test_smart_cut_invalid_duration(self):
        out = os.path.join(self.temp_dir, "out_invalid.mp4")
        ok, res = self.editor.trim_smart_cut(self.test_video, out, 5.0, 4.0)
        self.assertFalse(ok)

if __name__ == "__main__":
    unittest.main()
