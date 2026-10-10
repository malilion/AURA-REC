#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
單元測試：視窗排除與智慧浮水印保護 (Window Exclusion & Watermark Protection)
"""

import os
import struct
import subprocess
import tempfile
import unittest

from platform_utils import find_executable
from recorder import ScreenRecorder
from window_exclusion_watermark import (
    build_watermark_filter_steps,
    build_window_exclusion_filter_steps,
    is_sensitive_window,
    render_watermark_png,
    set_window_excluded_from_capture,
)


class TestWindowExclusionAndWatermark(unittest.TestCase):
    def test_sensitive_window_detection(self):
        self.assertTrue(is_sensitive_window("1Password", "Vault"))
        self.assertTrue(is_sensitive_window("LINE", "聊天室"))
        self.assertTrue(is_sensitive_window("Google Chrome", "無痕視窗 - 登入"))
        self.assertTrue(is_sensitive_window("Safari", "網路銀行轉帳"))
        self.assertFalse(is_sensitive_window("Visual Studio Code", "app.py — Record"))
        # 自訂關鍵字
        self.assertTrue(
            is_sensitive_window("Notion", "Q4 薪資表", keywords=["薪資", "客戶名單"])
        )

    def test_window_exclusion_filter_steps_all_modes(self):
        boxes = [
            {"id": 101, "owner": "LINE", "box": (120, 80, 400, 300)},
            {"id": 102, "owner": "1Password", "box": (600, 200, 360, 260)},
        ]

        # 1. 高斯/盒式景深模糊 (blur)
        steps_blur, lbl_blur = build_window_exclusion_filter_steps(
            base_label="0:v", excluded_boxes=boxes, mask_mode="blur"
        )
        self.assertEqual(lbl_blur, "excl_2")
        self.assertEqual(len(steps_blur), 2)
        self.assertIn("boxblur=28:3", steps_blur[0])
        self.assertIn("crop=400:300:120:80", steps_blur[0])

        # 2. 馬賽克像素化 (mosaic)
        steps_mosaic, lbl_mosaic = build_window_exclusion_filter_steps(
            base_label="0:v", excluded_boxes=boxes, mask_mode="mosaic"
        )
        self.assertEqual(lbl_mosaic, "excl_2")
        self.assertIn("flags=neighbor", steps_mosaic[0])

        # 3. 深色隱私黑盒盾牌 (shield)
        steps_shield, lbl_shield = build_window_exclusion_filter_steps(
            base_label="0:v", excluded_boxes=boxes, mask_mode="shield"
        )
        self.assertEqual(lbl_shield, "excl_2")
        self.assertIn("drawbox=x=120:y=80:w=400:h=300", steps_shield[0])

    def test_window_exclusion_region_intersection(self):
        # 當有局部區域錄影 (region = 100, 100, 500, 400) 時，排除框應轉換為區域相對座標
        boxes = [{"id": 201, "owner": "Slack", "box": (200, 150, 300, 200)}]
        steps, out_lbl = build_window_exclusion_filter_steps(
            base_label="0:v",
            excluded_boxes=boxes,
            mask_mode="shield",
            region=(100, 100, 500, 400),
        )
        self.assertEqual(out_lbl, "excl_1")
        self.assertIn("drawbox=x=100:y=50:w=300:h=200", steps[0])

    def test_render_watermark_png_badge_and_tiled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            badge_path = os.path.join(tmpdir, "badge.png")
            out = render_watermark_png(
                text="© 極光錄影 Aura · Confidential",
                style="aurora",
                opacity="medium",
                font_size=22,
                tiled=False,
                output_path=badge_path,
            )
            self.assertTrue(os.path.exists(out))
            with open(out, "rb") as f:
                data = f.read()
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            w, h = struct.unpack(">II", data[16:24])
            self.assertGreater(w, 80)
            self.assertGreater(h, 24)

            tiled_path = os.path.join(tmpdir, "tiled.png")
            out_tiled = render_watermark_png(
                text="DO NOT DISTRIBUTE",
                style="subtle",
                opacity="subtle",
                font_size=18,
                tiled=True,
                tile_w=640,
                tile_h=360,
                output_path=tiled_path,
            )
            self.assertTrue(os.path.exists(out_tiled))
            with open(out_tiled, "rb") as f:
                tdata = f.read()
            tw, th = struct.unpack(">II", tdata[16:24])
            self.assertEqual(tw, 640)
            self.assertEqual(th, 360)

    def test_build_watermark_filter_steps_modes(self):
        # Corner mode
        steps_c, lbl_c = build_watermark_filter_steps(
            base_label="0:v",
            watermark_config={
                "enabled": True,
                "mode": "corner",
                "position": "bottom-right",
                "style": "aurora",
                "opacity": "medium",
                "text": "Aura Brand",
            },
        )
        self.assertEqual(lbl_c, "wm_out")
        self.assertEqual(len(steps_c), 2)
        self.assertIn("movie=", steps_c[0])
        self.assertIn("W-w-24:H-h-24", steps_c[1])

        # Floating anti-piracy mode
        steps_f, lbl_f = build_watermark_filter_steps(
            base_label="0:v",
            watermark_config={
                "enabled": True,
                "mode": "floating",
                "style": "gold",
                "opacity": "strong",
                "text": "ID-9527",
            },
        )
        self.assertEqual(lbl_f, "wm_out")
        self.assertIn("sin(t*0.65)", steps_f[1])
        self.assertIn("cos(t*0.48)", steps_f[1])

    def test_recorder_build_capture_command_with_watermark_and_pip(self):
        rec = ScreenRecorder(output_dir=tempfile.gettempdir())
        cmd = rec.build_capture_command(
            output_file="/tmp/test_wm_out.mp4",
            video_idx="1",
            audio_idx=None,
            fps=30,
            resolution="1080p",
            use_hardware_accel=False,
            pip_config={
                "enabled": True,
                "camera_idx": "0",
                "shape": "circle",
                "position": "bottom-right",
                "size": 240,
                "bg_mode": "blur",
                "bg_strength": "medium",
            },
            watermark_config={
                "enabled": True,
                "mode": "floating",
                "style": "aurora",
                "opacity": "medium",
                "text": "© Aura Studio",
            },
        )
        self.assertIn("-filter_complex", cmd)
        fc_idx = cmd.index("-filter_complex")
        fc_str = cmd[fc_idx + 1]
        self.assertIn("movie=", fc_str)
        self.assertIn("sin(t*0.65)", fc_str)
        self.assertIn("[outv]", cmd)

        # Standalone watermark without PiP
        cmd_no_pip = rec.build_capture_command(
            output_file="/tmp/test_wm_only.mp4",
            video_idx="1",
            audio_idx=None,
            fps=30,
            resolution="1080p",
            use_hardware_accel=False,
            watermark_config={
                "enabled": True,
                "mode": "corner",
                "style": "aurora",
                "opacity": "medium",
                "text": "© Aura Studio",
            },
        )
        self.assertIn("-filter_complex", cmd_no_pip)
        self.assertIn("[outv]", cmd_no_pip)

    def test_os_window_exclusion_api_safe_return(self):
        # 驗證呼叫原生 API 不會拋出未捕獲例外
        res = set_window_excluded_from_capture(None, exclude=False)
        self.assertIsInstance(res, bool)

    def test_ffmpeg_end_to_end_exclusion_and_watermark_render(self):
        ffmpeg_bin = find_executable("ffmpeg")
        if not ffmpeg_bin:
            self.skipTest("FFmpeg not installed")

        boxes = [{"id": 1, "owner": "LINE", "box": (40, 30, 120, 80)}]
        excl_steps, excl_lbl = build_window_exclusion_filter_steps(
            base_label="0:v", excluded_boxes=boxes, mask_mode="blur"
        )
        wm_steps, final_lbl = build_watermark_filter_steps(
            base_label=excl_lbl,
            watermark_config={
                "enabled": True,
                "mode": "floating",
                "style": "aurora",
                "opacity": "strong",
                "text": "AURA PROTECTION",
            },
            out_label="v_out",
        )
        fc = ";".join(excl_steps + wm_steps)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_mp4 = os.path.join(tmpdir, "out_protected.mp4")
            cmd = [
                ffmpeg_bin,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=320x180:rate=15:duration=1",
                "-filter_complex",
                fc,
                "-map",
                f"[{final_lbl}]",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                out_mp4,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            self.assertEqual(
                proc.returncode,
                0,
                f"FFmpeg render failed: {proc.stderr[-500:]}",
            )
            self.assertTrue(os.path.exists(out_mp4))
            self.assertGreater(os.path.getsize(out_mp4), 1000)


if __name__ == "__main__":
    unittest.main()
