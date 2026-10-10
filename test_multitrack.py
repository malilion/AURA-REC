#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for Dual Audio Input & Multi-track Audio Capture & Preservation.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from platform_utils import IS_MAC, IS_WINDOWS
from recorder import ScreenRecorder
from video_editor import VideoEditor


class TestMultiTrackAudio(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="aura_test_mt_")
        self.recorder = ScreenRecorder(output_dir=self.temp_dir)
        self.editor = VideoEditor()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_capture_command_single_audio(self):
        """單一音訊 (僅麥克風) 指令建構測試"""
        cmd = self.recorder.build_capture_command(
            video_idx="0",
            audio_idx="1",
            sys_audio_idx=None,
            output_file=Path(self.temp_dir) / "out.mp4",
        )
        cmd_str = " ".join(cmd)
        self.assertIn("-c:a aac", cmd_str)
        # 不應該出現 System Audio 標籤
        self.assertNotIn("System Audio", cmd_str)

    @unittest.skipUnless(IS_MAC, "macOS-only (avfoundation 多音軌指令)")
    def test_build_capture_command_multitrack_mac(self):
        """macOS 雙路音訊獨立多音軌 (Multi-track) 指令建構測試"""
        cmd = self.recorder.build_capture_command(
            video_idx="0",
            audio_idx="1",
            sys_audio_idx="2",
            multitrack=True,
            output_file=Path(self.temp_dir) / "out.mp4",
        )
        cmd_str = " ".join(cmd)
        if IS_MAC:
            self.assertIn("0:1", cmd_str)
            self.assertIn(":2", cmd_str)
            self.assertIn("-map 0:v -map 0:a -map 1:a", cmd_str)
            self.assertIn('handler_name=Microphone', cmd_str)
            self.assertIn('handler_name=System Audio', cmd_str)
            self.assertIn('Microphone (麥克風)', cmd_str)
            self.assertIn('System Audio (系統音效)', cmd_str)

    @unittest.skipUnless(IS_MAC, "macOS-only (avfoundation 多音軌指令)")
    def test_build_capture_command_multitrack_pip_mac(self):
        """macOS 畫中畫 (PiP) 模式下雙路音訊獨立多音軌指令建構測試"""
        pip_config = {
            "enabled": True,
            "camera_idx": "0",
            "size": 240,
            "shape": "circle",
            "position": "bottom-right",
            "margin": 30,
        }
        cmd = self.recorder.build_capture_command(
            video_idx="1",
            audio_idx="1",
            sys_audio_idx="2",
            multitrack=True,
            pip_config=pip_config,
            output_file=Path(self.temp_dir) / "out.mp4",
        )
        cmd_str = " ".join(cmd)
        if IS_MAC:
            self.assertIn("-map [outv] -map 0:a -map 2:a", cmd_str)
            self.assertIn('handler_name=Microphone', cmd_str)
            self.assertIn('handler_name=System Audio', cmd_str)

    def test_build_capture_command_amix_mix(self):
        """雙路音訊混音 (multitrack=False) 使用 amix 濾鏡合軌測試"""
        cmd = self.recorder.build_capture_command(
            video_idx="0",
            audio_idx="1",
            sys_audio_idx="2",
            multitrack=False,
            output_file=Path(self.temp_dir) / "out.mp4",
        )
        cmd_str = " ".join(cmd)
        self.assertIn("amix=inputs=2:duration=longest", cmd_str)
        self.assertIn("-map [outa]", cmd_str)

    def _generate_synthetic_multitrack_video(self, file_path, duration=3.0):
        """生成合成雙音軌測試影片 (Track 1: 1000Hz, Track 2: 440Hz)"""
        cmd = [
            self.editor.ffmpeg_bin,
            "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x240:rate=30",
            "-f", "lavfi", "-i", f"sine=frequency=1000:duration={duration}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
            "-map", "0:v", "-map", "1:a", "-map", "2:a",
            "-c:v", "libx264", "-g", "30",
            "-c:a", "aac",
            "-metadata:s:a:0", "handler_name=Microphone",
            "-metadata:s:a:0", "title=Microphone (麥克風)",
            "-metadata:s:a:1", "handler_name=System Audio",
            "-metadata:s:a:1", "title=System Audio (系統音效)",
            str(file_path),
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertEqual(res.returncode, 0)
        self.assertTrue(os.path.exists(file_path))

    def test_video_editor_get_video_info_multitrack(self):
        """測試 VideoEditor.get_video_info 解析多音軌能力"""
        src = Path(self.temp_dir) / "multitrack_src.mp4"
        self._generate_synthetic_multitrack_video(src)

        info = self.editor.get_video_info(src)
        self.assertIsNotNone(info)
        self.assertTrue(info["has_audio"])
        self.assertEqual(info["audio_track_count"], 2)
        tracks = info["audio_tracks"]
        self.assertEqual(len(tracks), 2)
        self.assertEqual(tracks[0]["title"], "Microphone")
        self.assertEqual(tracks[1]["title"], "System Audio")

    def test_copy_trim_preserves_multitrack(self):
        """測試純無損串流複製 (_run_copy_trim) 完整保留雙音軌"""
        src = Path(self.temp_dir) / "multitrack_src.mp4"
        out = Path(self.temp_dir) / "copy_trimmed.mp4"
        self._generate_synthetic_multitrack_video(src, duration=3.0)

        ok, result = self.editor._run_copy_trim(src, out, 0.5, 1.5)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(out))

        info = self.editor.get_video_info(out)
        self.assertEqual(info["audio_track_count"], 2)
        tracks = info["audio_tracks"]
        self.assertEqual(tracks[0]["title"], "Microphone")
        self.assertEqual(tracks[1]["title"], "System Audio")

    def test_smart_cut_preserves_multitrack(self):
        """測試極速智慧無損裁切 (trim_smart_cut) 完整保留雙音軌與標籤"""
        src = Path(self.temp_dir) / "multitrack_src.mp4"
        out = Path(self.temp_dir) / "smartcut_trimmed.mp4"
        self._generate_synthetic_multitrack_video(src, duration=4.0)

        ok, result = self.editor.trim_smart_cut(src, out, 0.6, 2.8)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(out))

        info = self.editor.get_video_info(out)
        self.assertEqual(info["audio_track_count"], 2)
        tracks = info["audio_tracks"]
        self.assertEqual(tracks[0]["title"], "Microphone")
        self.assertEqual(tracks[1]["title"], "System Audio")

    def test_advanced_trim_preserves_multitrack_or_mutes(self):
        """測試進階剪輯 (trim_advanced) 保留雙音軌及靜音行為"""
        src = Path(self.temp_dir) / "multitrack_src.mp4"
        out = Path(self.temp_dir) / "advanced_trimmed.mp4"
        out_muted = Path(self.temp_dir) / "advanced_muted.mp4"
        self._generate_synthetic_multitrack_video(src, duration=2.5)

        # 1. 正常導出保留所有音軌
        ok, res = self.editor.trim_advanced(src, out, 0.2, 2.0, mute_audio=False)
        self.assertTrue(ok)
        info = self.editor.get_video_info(out)
        self.assertEqual(info["audio_track_count"], 2)

        # 2. 靜音導出去除所有音軌
        ok_m, res_m = self.editor.trim_advanced(src, out_muted, 0.2, 2.0, mute_audio=True)
        self.assertTrue(ok_m)
        info_m = self.editor.get_video_info(out_muted)
        self.assertFalse(info_m["has_audio"])
        self.assertEqual(info_m["audio_track_count"], 0)


if __name__ == "__main__":
    unittest.main()
