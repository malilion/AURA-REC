#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
test_windows_wgc.py - Windows 現代錄製 API (WGC / Direct3D 11 Desktop Duplication) 單元測試
驗證：
1. check_windows_modern_capture_support 函數運作
2. Windows 下使用 ddagrab 產生高幀率 (60/120 FPS) 命令
3. 支援桌面索引與滑鼠游標擷取參數
4. ddagrab 下硬體影格自動插入 hwdownload,format=bgra
5. 子母畫面 (PIP) 下之 hwdownload 與 overlay 濾鏡鏈正確串接
6. 支援手動指定 win_capture_mode="gdi" 回退傳統 GDI 模式
"""

import unittest
from unittest.mock import patch, MagicMock
from recorder import ScreenRecorder
import platform_utils


class TestWindowsWGC(unittest.TestCase):

    def setUp(self):
        self.recorder = ScreenRecorder()

    def test_check_windows_modern_capture_support(self):
        # 測試非 Windows 環境回傳 False
        with patch("platform_utils.IS_WINDOWS", False):
            self.assertFalse(platform_utils.check_windows_modern_capture_support("ffmpeg"))

        # 測試 Windows 環境下 ffmpeg -filters 包含 ddagrab
        with patch("platform_utils.IS_WINDOWS", True):
            with patch("platform_utils.find_executable", return_value="/bin/ffmpeg"):
                with patch("os.path.exists", return_value=True):
                    with patch("subprocess.run") as mock_run:
                        mock_run.return_value = MagicMock(stdout="... ddagrab  |->V  Direct3D 11 Desktop Duplication ...")
                        self.assertTrue(platform_utils.check_windows_modern_capture_support("/bin/ffmpeg"))

                        mock_run.return_value = MagicMock(stdout="... only other filters ...")
                        self.assertFalse(platform_utils.check_windows_modern_capture_support("/bin/ffmpeg"))

    def test_windows_wgc_command_generation_high_fps(self):
        """測試 Windows 平台 WGC (ddagrab) 60 FPS 與 120 FPS 指令產生"""
        with patch("recorder.IS_MAC", False), patch("recorder.IS_WINDOWS", True):
            with patch.object(self.recorder, "wgc_supported", True):
                # 測試 60 FPS
                cmd_60 = self.recorder.build_capture_command(
                    video_idx="desktop",
                    audio_idx=None,
                    fps=60,
                    capture_cursor=True,
                    output_file="test_60.mp4",
                    win_capture_mode="wgc",
                )
                cmd_str_60 = " ".join(cmd_60)
                self.assertIn("-f lavfi", cmd_str_60)
                self.assertIn("ddagrab=output_idx=0:framerate=60:draw_mouse=1", cmd_str_60)
                self.assertIn("hwdownload,format=bgra", cmd_str_60)

                # 測試 120 FPS (電競/極限流暢)
                cmd_120 = self.recorder.build_capture_command(
                    video_idx="1",
                    audio_idx=None,
                    fps=120,
                    capture_cursor=False,
                    output_file="test_120.mp4",
                    win_capture_mode="wgc",
                )
                cmd_str_120 = " ".join(cmd_120)
                self.assertIn("ddagrab=output_idx=1:framerate=120:draw_mouse=0", cmd_str_120)

    def test_windows_pip_with_wgc(self):
        """測試 Windows PIP 子母畫面搭配 WGC 時，正確插入 hwdownload 至主畫面"""
        with patch("recorder.IS_MAC", False), patch("recorder.IS_WINDOWS", True):
            with patch.object(self.recorder, "wgc_supported", True):
                pip_config = {
                    "enabled": True,
                    "camera_idx": "0",
                    "shape": "circle",
                    "size": 240,
                    "position": "bottom-right",
                    "margin": 24,
                }
                cmd = self.recorder.build_capture_command(
                    video_idx="desktop",
                    audio_idx=None,
                    fps=60,
                    pip_config=pip_config,
                    output_file="test_pip.mp4",
                    win_capture_mode="wgc",
                )
                cmd_str = " ".join(cmd)
                self.assertIn("ddagrab=output_idx=0:framerate=60", cmd_str)
                self.assertIn("[0:v]hwdownload,format=bgra[main_bgra]", cmd_str)
                self.assertIn("overlay=", cmd_str)

    def test_windows_gdi_fallback_mode(self):
        """測試指定 win_capture_mode='gdi' 時，平滑回退使用傳統 gdigrab"""
        with patch("recorder.IS_MAC", False), patch("recorder.IS_WINDOWS", True):
            with patch.object(self.recorder, "wgc_supported", True):
                cmd = self.recorder.build_capture_command(
                    video_idx="desktop",
                    audio_idx=None,
                    fps=30,
                    output_file="test_gdi.mp4",
                    win_capture_mode="gdi",
                )
                cmd_str = " ".join(cmd)
                self.assertIn("-f gdigrab", cmd_str)
                self.assertIn("-i desktop", cmd_str)
                self.assertNotIn("ddagrab", cmd_str)
                self.assertNotIn("hwdownload", cmd_str)


if __name__ == "__main__":
    unittest.main()
