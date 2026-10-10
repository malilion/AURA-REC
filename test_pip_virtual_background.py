import unittest
import subprocess
import tempfile
import os
from pathlib import Path

from platform_utils import build_pip_filter_steps
from recorder import ScreenRecorder, ffmpeg_is_available


class TestPipVirtualBackground(unittest.TestCase):
    """測試畫中畫 (PiP 人像相機) 智慧去背、背景虛化與虛擬背景功能"""

    def test_build_pip_filter_steps_defaults(self):
        steps = build_pip_filter_steps(
            cam_input_label="1:v",
            pip_size=260,
            pip_shape="circle",
            bg_mode="original",
            border_rgb=(0, 240, 255),
        )
        self.assertTrue(len(steps) >= 2)
        full = ";".join(steps)
        self.assertIn("[1:v]scale=260:260", full)
        self.assertIn("[cam]", full)

    def test_build_pip_filter_steps_blur_modes(self):
        # Subtle (12px)
        steps_subtle = build_pip_filter_steps(
            pip_size=200, pip_shape="circle", bg_mode="blur", bg_strength="subtle"
        )
        full_subtle = ";".join(steps_subtle)
        self.assertIn("boxblur=12:2", full_subtle)
        self.assertIn("maskedmerge", full_subtle)

        # Medium (24px)
        steps_med = build_pip_filter_steps(
            pip_size=200, pip_shape="circle", bg_mode="blur", bg_strength="medium"
        )
        full_med = ";".join(steps_med)
        self.assertIn("boxblur=24:2", full_med)
        self.assertIn("maskedmerge", full_med)

        # Strong (40px)
        steps_strong = build_pip_filter_steps(
            pip_size=200, pip_shape="circle", bg_mode="blur", bg_strength="strong"
        )
        full_strong = ";".join(steps_strong)
        self.assertIn("boxblur=40:2", full_strong)
        self.assertIn("maskedmerge", full_strong)

    def test_build_pip_filter_steps_transparent_cutout(self):
        steps = build_pip_filter_steps(
            pip_size=260, pip_shape="circle", bg_mode="transparent", bg_strength="medium"
        )
        full = ";".join(steps)
        self.assertIn("format=rgba", full)
        self.assertIn("hypot", full)
        self.assertIn("[cam]", full)

    def test_build_pip_filter_steps_chromakey_and_bluekey(self):
        # 綠幕
        steps_green = build_pip_filter_steps(
            pip_size=260, pip_shape="circle", bg_mode="chromakey", bg_strength="medium"
        )
        full_green = ";".join(steps_green)
        self.assertIn("colorkey=0x00FF00:0.32:0.12", full_green)

        # 藍幕
        steps_blue = build_pip_filter_steps(
            pip_size=260, pip_shape="circle", bg_mode="bluekey", bg_strength="strong"
        )
        full_blue = ";".join(steps_blue)
        self.assertIn("colorkey=0x0000FF:0.4:0.16", full_blue)

    def test_build_pip_filter_steps_aurora(self):
        steps = build_pip_filter_steps(
            pip_size=260, pip_shape="circle", bg_mode="aurora", fps=30
        )
        full = ";".join(steps)
        self.assertIn("gradients=s=260x260", full)
        self.assertIn("c0=0x2b1055", full)
        self.assertIn("c1=0x0b1f3a", full)
        self.assertIn("overlay=format=auto:shortest=1[cam_proc]", full)

    def test_build_pip_filter_steps_shapes_and_borders(self):
        # 矩形相機 16:9 + 霓虹藍邊框
        steps_rect = build_pip_filter_steps(
            pip_size=260, pip_shape="rect", bg_mode="original", border_rgb=(0, 240, 255)
        )
        full_rect = ";".join(steps_rect)
        self.assertIn("scale=462:260", full_rect)  # 260 * 16 / 9 = 462.22 -> 462
        self.assertIn("drawbox=", full_rect)
        self.assertIn("0x00F0FF", full_rect)

        # 圓形無邊框
        steps_noborder = build_pip_filter_steps(
            pip_size=260, pip_shape="circle", bg_mode="original", border_rgb=None
        )
        full_noborder = ";".join(steps_noborder)
        self.assertIn("alpha(X,Y)", full_noborder)

        # 十六進位顏色字串支援
        steps_hex = build_pip_filter_steps(
            pip_size=260, pip_shape="rect", bg_mode="original", border_rgb="#FFFFFF"
        )
        full_hex = ";".join(steps_hex)
        self.assertIn("0xFFFFFF", full_hex)

    def test_recorder_build_capture_command_with_pip_bg(self):
        rec = ScreenRecorder()
        pip_cfg = {
            "enabled": True,
            "camera_idx": "0",
            "size": 260,
            "shape": "circle",
            "position": "bottom-right",
            "border_color": (0, 240, 255),
            "margin": 32,
            "bg_mode": "blur",
            "bg_strength": "strong",
        }
        cmd = rec.build_capture_command(
            video_idx="0",
            audio_idx=None,
            pip_config=pip_cfg,
            output_file="/tmp/dummy.mp4",
        )
        cmd_str = " ".join(cmd)
        self.assertIn("-filter_complex", cmd_str)
        self.assertIn("boxblur=40:2", cmd_str)
        self.assertIn("maskedmerge", cmd_str)
        self.assertIn("overlay=W-w-32:H-h-32", cmd_str)

    def test_ffmpeg_end_to_end_rendering_all_modes(self):
        if not ffmpeg_is_available("ffmpeg"):
            self.skipTest("FFmpeg 未安裝，略過端對端渲染測試")

        test_cases = [
            ("blur", "circle"),
            ("transparent", "circle"),
            ("chromakey", "circle"),
            ("aurora", "circle"),
            ("blur", "rect"),
            ("original", "rect"),
        ]

        for mode, shape in test_cases:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                out_path = tmp.name

            try:
                pip_size = 160
                steps = build_pip_filter_steps(
                    cam_input_label="1:v",
                    pip_size=pip_size,
                    pip_shape=shape,
                    bg_mode=mode,
                    bg_strength="medium",
                    border_rgb=(0, 240, 255),
                    fps=25,
                )
                steps.append("[0:v][cam]overlay=W-w-10:H-h-10:format=auto,format=yuv420p[outv]")
                fc = ";".join(steps)

                cmd = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=black:s=320x180:d=0.2:r=25",
                    "-f", "lavfi", "-i", "testsrc=s=160x120:d=0.2:r=25",
                    "-filter_complex", fc,
                    "-map", "[outv]",
                    "-c:v", "libx264", "-preset", "ultrafast",
                    out_path,
                ]

                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.assertEqual(
                    res.returncode, 0,
                    f"FFmpeg 渲染失敗 ({mode}, {shape}): {res.stderr.decode()}"
                )
                self.assertTrue(os.path.exists(out_path))
                self.assertGreater(
                    os.path.getsize(out_path), 0,
                    f"輸出檔案為空 ({mode}, {shape})"
                )
            finally:
                if os.path.exists(out_path):
                    try:
                        os.remove(out_path)
                    except Exception:
                        pass


if __name__ == "__main__":
    unittest.main()
