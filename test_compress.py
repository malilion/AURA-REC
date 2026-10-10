#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""錄完自動壓縮：硬體編碼的大檔要變小，x264 錄的檔不動，多音軌要保留。"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from platform_utils import find_executable
from recorder import compress_recording, needs_compression

FFMPEG = find_executable("ffmpeg")
FFPROBE = find_executable("ffprobe")


def _make_clip(path, video_args, audio_tracks=1):
    """類似桌面錄影的畫面：大部分靜止，只有一小塊在動。"""
    cmd = [
        FFMPEG, "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=3",
    ]
    for _ in range(audio_tracks):
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=3"]
    cmd += ["-map", "0:v"]
    for i in range(audio_tracks):
        cmd += ["-map", f"{i + 1}:a"]
    cmd += [*video_args, "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)]
    subprocess.run(cmd, check=True)


def _audio_streams(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout
    return len([line for line in out.splitlines() if line.strip()])


class TestNeedsCompression(unittest.TestCase):
    def test_skips_x264_and_x265(self):
        self.assertFalse(needs_compression("Lavc62.28.102 libx264"))
        self.assertFalse(needs_compression("Lavc62.28.102 libx265"))

    def test_compresses_hardware_encoders(self):
        for tag in ("Lavc62.28.102 h264_videotoolbox", "Lavc h264_nvenc", "Lavc h264_qsv", "Lavc h264_amf", ""):
            self.assertTrue(needs_compression(tag), tag)


@unittest.skipUnless(FFMPEG and FFPROBE, "需要 ffmpeg / ffprobe")
class TestCompressRecording(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="aura_test_compress_"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_high_bitrate_file_is_replaced_and_keeps_tracks(self):
        # mpeg4 高碼率代替硬體編碼器的固定碼率輸出（CI 機器不一定有硬體編碼器）
        clip = self.dir / "rec.mp4"
        _make_clip(clip, ["-c:v", "mpeg4", "-b:v", "8M"], audio_tracks=2)
        ratios = []
        replaced, old_size, new_size = compress_recording(FFMPEG, clip, progress=ratios.append, ffprobe_bin=FFPROBE)
        self.assertTrue(replaced)
        self.assertLess(new_size, old_size * 0.8)
        self.assertEqual(clip.stat().st_size, new_size)
        self.assertEqual(_audio_streams(clip), 2)
        self.assertTrue(ratios and max(ratios) > 0.5)
        self.assertFalse(any(p.name.endswith(".compressing.mp4") for p in self.dir.iterdir()))

    def test_x264_file_is_left_alone(self):
        clip = self.dir / "rec.mp4"
        _make_clip(clip, ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"])
        before = clip.read_bytes()
        replaced, old_size, new_size = compress_recording(FFMPEG, clip, ffprobe_bin=FFPROBE)
        self.assertFalse(replaced)
        self.assertEqual(old_size, new_size)
        self.assertEqual(clip.read_bytes(), before)

    def test_keeps_original_when_saving_is_small(self):
        # 已經很小的檔：重壓省不到 20% 就不能取代
        clip = self.dir / "rec.mp4"
        _make_clip(clip, ["-c:v", "mpeg4", "-q:v", "31"])
        before = clip.read_bytes()
        replaced, _, _ = compress_recording(FFMPEG, clip, ffprobe_bin=FFPROBE)
        if not replaced:
            self.assertEqual(clip.read_bytes(), before)
        self.assertEqual([p.name for p in self.dir.iterdir()], ["rec.mp4"])


if __name__ == "__main__":
    unittest.main()
