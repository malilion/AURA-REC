#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for AI Speech-to-Text & Subtitles (AI 離線語音識別與智慧字幕軌)
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from speech_to_text import (
    SubtitleCue,
    SubtitleTrack,
    SubtitleStyle,
    SpeechToTextEngine,
    sec_to_srt_time,
    srt_time_to_sec,
    sec_to_vtt_time,
    sec_to_short_time,
)
from video_editor import VideoEditor


class TestSpeechToText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="aura_test_stt_")
        cls.editor = VideoEditor()

        # 建立 4 秒測試音訊與影片: 0~1.5s (1000Hz 聲音), 1.5~2.5s (靜音), 2.5~4.0s (800Hz 聲音)
        cls.test_wav = os.path.join(cls.temp_dir, "speech_sample.wav")
        cls.test_mp4 = os.path.join(cls.temp_dir, "video_sample.mp4")

        cmd_wav = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=1.5",
            "-f", "lavfi", "-i", "anullsrc=duration=1.0",
            "-f", "lavfi", "-i", "sine=frequency=800:duration=1.5",
            "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[outa]",
            "-map", "[outa]",
            "-c:a", "pcm_s16le",
            cls.test_wav,
        ]
        subprocess.run(cmd_wav, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        cmd_mp4 = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=10",
            "-i", cls.test_wav,
            "-c:v", "libx264", "-c:a", "aac",
            cls.test_mp4,
        ]
        subprocess.run(cmd_mp4, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_time_conversions(self):
        # 秒數轉 SRT 時間碼
        self.assertEqual(sec_to_srt_time(0.0), "00:00:00,000")
        self.assertEqual(sec_to_srt_time(65.123), "00:01:05,123")
        self.assertEqual(sec_to_srt_time(3661.5), "01:01:01,500")

        # SRT 時間碼轉秒數
        self.assertAlmostEqual(srt_time_to_sec("00:00:00,000"), 0.0)
        self.assertAlmostEqual(srt_time_to_sec("00:01:05,123"), 65.123, places=3)
        self.assertAlmostEqual(srt_time_to_sec("01:01:01.500"), 3661.5, places=3)

        # VTT 時間碼
        self.assertEqual(sec_to_vtt_time(65.123), "00:01:05.123")

        # Short time
        self.assertEqual(sec_to_short_time(65.4), "01:05.4")

    def test_subtitle_cue_and_track_basics(self):
        track = SubtitleTrack()
        self.assertTrue(track.is_empty())
        self.assertEqual(len(track), 0)

        # 新增字幕
        cue1 = track.add_cue(1.0, 3.5, "第一句測試字幕")
        cue2 = track.add_cue(4.0, 6.0, "第二句測試字幕")
        self.assertFalse(track.is_empty())
        self.assertEqual(len(track), 2)
        self.assertEqual(cue1.duration, 2.5)

        # 檢索特定時間點的字幕
        self.assertIsNone(track.get_cue_at_time(0.5))
        self.assertEqual(track.get_cue_at_time(2.0), cue1)
        self.assertIsNone(track.get_cue_at_time(3.8))
        self.assertEqual(track.get_cue_at_time(4.5), cue2)

        # 修改字幕
        track.update_cue(cue1.id, text="修改後的第一句")
        self.assertEqual(cue1.text, "修改後的第一句")

        # 刪除字幕
        self.assertTrue(track.remove_cue(cue1.id))
        self.assertEqual(len(track), 1)
        self.assertEqual(track.cues[0], cue2)

        # 清空
        track.clear()
        self.assertTrue(track.is_empty())

    def test_srt_and_vtt_serialization_and_parsing(self):
        track = SubtitleTrack()
        track.add_cue(1.2, 3.4, "歡迎使用 AURA REC")
        track.add_cue(4.0, 6.5, "離線 AI 語音轉文字功能")

        # 導出 SRT
        srt_content = track.to_srt()
        self.assertIn("00:00:01,200 --> 00:00:03,400", srt_content)
        self.assertIn("歡迎使用 AURA REC", srt_content)
        self.assertIn("離線 AI 語音轉文字功能", srt_content)

        # 導出 VTT
        vtt_content = track.to_vtt()
        self.assertTrue(vtt_content.startswith("WEBVTT"))
        self.assertIn("00:00:01.200 --> 00:00:03.400", vtt_content)

        # 儲存與重新載入 SRT
        srt_file = os.path.join(self.temp_dir, "test.srt")
        track.save_srt(srt_file)
        self.assertTrue(os.path.exists(srt_file))

        loaded_track = SubtitleTrack.from_srt(srt_file)
        self.assertEqual(len(loaded_track), 2)
        self.assertAlmostEqual(loaded_track.cues[0].start, 1.2, places=2)
        self.assertAlmostEqual(loaded_track.cues[0].end, 3.4, places=2)
        self.assertEqual(loaded_track.cues[0].text, "歡迎使用 AURA REC")
        self.assertEqual(loaded_track.cues[1].text, "離線 AI 語音轉文字功能")

    def test_speech_to_text_engine_audio_extraction(self):
        engine = SpeechToTextEngine()
        out_wav = os.path.join(self.temp_dir, "extracted.wav")
        ok = engine.extract_audio_wav(self.test_mp4, out_wav)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(out_wav))
        self.assertGreater(os.path.getsize(out_wav), 0)

    def test_vad_speech_intervals_detection(self):
        engine = SpeechToTextEngine()
        # 測試音訊為 0~1.5s 有聲，1.5~2.5s 靜音，2.5~4.0s 有聲
        intervals = engine.detect_speech_intervals_vad(self.test_wav, silence_thresh_db=-30.0, min_silence_dur=0.4)
        self.assertGreaterEqual(len(intervals), 2)
        # 第一區間大約為 0 到 1.5 秒
        self.assertAlmostEqual(intervals[0][0], 0.0, delta=0.3)
        self.assertAlmostEqual(intervals[0][1], 1.5, delta=0.3)
        # 第二區間大約為 2.5 到 4.0 秒
        self.assertAlmostEqual(intervals[1][0], 2.5, delta=0.3)
        self.assertAlmostEqual(intervals[1][1], 4.0, delta=0.3)

    def test_transcribe_with_vad(self):
        engine = SpeechToTextEngine()
        track = engine.transcribe_with_vad(self.test_mp4)
        self.assertGreaterEqual(len(track), 2)
        for cue in track.cues:
            self.assertGreater(cue.duration, 0.2)
            self.assertTrue(cue.text.startswith("[語音片段"))

    def test_video_export_with_soft_subtitles_and_companion_srt(self):
        # 建立測試 SRT
        srt_file = os.path.join(self.temp_dir, "export_sample.srt")
        track = SubtitleTrack()
        track.add_cue(0.5, 2.0, "畫面與聲音同步測試")
        track.save_srt(srt_file)

        out_mp4 = os.path.join(self.temp_dir, "trimmed_with_subs.mp4")

        # 執行 trim_advanced 並傳入字幕
        ok, res_file = self.editor.trim_advanced(
            self.test_mp4, out_mp4,
            start_sec=0.0, end_sec=3.0,
            subtitles_srt_path=srt_file,
            soft_subtitles=True,
            export_srt_file=True,
        )
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(out_mp4))

        # 驗證伴隨同名 .srt 檔案存在
        companion_srt = Path(out_mp4).with_suffix(".srt")
        self.assertTrue(companion_srt.exists())

        # 驗證輸出影片中含有 mov_text 字幕軌
        info = self.editor.get_video_info(out_mp4)
        self.assertIsNotNone(info)

        # 透過 ffprobe 檢查 subtitle stream
        cmd_probe = [
            self.editor.ffprobe_bin,
            "-v", "error",
            "-show_entries", "stream=codec_type,codec_name",
            "-of", "json",
            out_mp4
        ]
        probe_res = subprocess.run(cmd_probe, stdout=subprocess.PIPE, text=True)
        probe_data = json.loads(probe_res.stdout)
        codecs = [s.get("codec_name") for s in probe_data.get("streams", [])]
        self.assertIn("mov_text", codecs)


if __name__ == "__main__":
    unittest.main()
