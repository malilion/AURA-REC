#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for Privacy Blur & Mosaic Masks (隱私模糊與局部馬賽克)
"""

import os
import shutil
import subprocess
import tempfile
import unittest

from video_editor import VideoEditor, build_blur_mask_graph


class TestBlurMask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="aura_test_blur_")
        cls.test_video = os.path.join(cls.temp_dir, "sample.mp4")
        # 建立 3 秒 1280x720 測試影片 (含立體聲音訊)
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=1280x720:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=3",
            "-c:v", "libx264", "-c:a", "aac",
            cls.test_video,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.editor = VideoEditor()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_build_blur_mask_graph_empty(self):
        graph, out = build_blur_mask_graph([], base_label="0:v")
        self.assertEqual(graph, "")
        self.assertEqual(out, "0:v")

    def test_build_blur_mask_graph_single_blur(self):
        masks = [
            {
                "id": 1,
                "type": "blur",
                "norm_rect": (0.1, 0.2, 0.3, 0.4),
                "strength": 20,
                "time_range": None,
            }
        ]
        graph, out = build_blur_mask_graph(masks, base_label="0:v", width=1280, height=720, out_label="outv")
        self.assertEqual(out, "outv")
        self.assertIn("boxblur=20:3", graph)
        self.assertIn("crop=384:288:128:144", graph)
        self.assertIn("overlay=128:144[outv]", graph)

    def test_build_blur_mask_graph_single_mosaic(self):
        masks = [
            {
                "id": 2,
                "type": "mosaic",
                "norm_rect": (0.5, 0.5, 0.25, 0.25),
                "strength": 16,
                "time_range": None,
            }
        ]
        graph, out = build_blur_mask_graph(masks, base_label="0:v", width=1280, height=720, out_label="outv")
        self.assertEqual(out, "outv")
        self.assertIn("flags=neighbor", graph)
        self.assertIn("scale=max(2\\,iw/16)", graph)
        self.assertIn("crop=320:180:640:360", graph)
        self.assertIn("overlay=640:360[outv]", graph)

    def test_build_blur_mask_graph_chained_with_time_range(self):
        masks = [
            {
                "id": 1,
                "type": "blur",
                "norm_rect": (0.1, 0.1, 0.2, 0.2),
                "time_range": (0.5, 2.0),
            },
            {
                "id": 2,
                "type": "mosaic",
                "norm_rect": (0.4, 0.4, 0.3, 0.3),
                "time_range": None,
            },
        ]
        graph, out = build_blur_mask_graph(masks, base_label="0:v", width=1000, height=600, out_label="outv")
        self.assertEqual(out, "outv")
        self.assertIn("m0_out", graph)
        self.assertIn("enable='between(t,0.500,2.000)'", graph)
        self.assertIn("m1_crop", graph)

    def test_trim_advanced_with_blur_masks(self):
        out_path = os.path.join(self.temp_dir, "blur_export.mp4")
        masks = [
            {
                "id": 1,
                "type": "blur",
                "norm_rect": (0.1, 0.1, 0.3, 0.2),
                "strength": 20,
            },
            {
                "id": 2,
                "type": "mosaic",
                "norm_rect": (0.5, 0.5, 0.4, 0.3),
                "strength": 14,
                "time_range": (0.5, 2.5),
            },
        ]
        ok, msg = self.editor.trim_advanced(
            self.test_video,
            out_path,
            start_sec=0.2,
            end_sec=2.8,
            speed=1.0,
            blur_masks=masks,
        )
        self.assertTrue(ok, f"Export failed: {msg}")
        self.assertTrue(os.path.exists(out_path))
        self.assertGreater(os.path.getsize(out_path), 0)

        info = self.editor.get_video_info(out_path)
        self.assertIsNotNone(info)
        self.assertAlmostEqual(info["duration"], 2.6, delta=0.3)
        self.assertTrue(info["has_audio"])

    def test_export_gif_with_masks(self):
        out_gif = os.path.join(self.temp_dir, "blur_export.gif")
        masks = [
            {
                "id": 1,
                "type": "blur",
                "norm_rect": (0.2, 0.2, 0.5, 0.5),
            }
        ]
        ok, msg = self.editor.export_gif(
            self.test_video,
            out_gif,
            start_sec=0.5,
            end_sec=1.8,
            fps=10,
            blur_masks=masks,
        )
        self.assertTrue(ok, f"GIF Export failed: {msg}")
        self.assertTrue(os.path.exists(out_gif))
        self.assertGreater(os.path.getsize(out_gif), 0)


if __name__ == "__main__":
    unittest.main()
