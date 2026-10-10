#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
國際化多語系引擎 (i18n) 與跨語系畫中畫去背/剪輯工作站相容性單元測試
"""

import unittest
import tkinter as tk
from tkinter import ttk

from i18n import (
    SUPPORTED_LANGUAGES,
    detect_system_locale,
    set_language,
    get_language,
    get_language_badge,
    next_language,
    to_simplified_chinese,
    tr,
    translate_widget_tree,
    translate_menu,
)
from aura_widgets import AuraButton, AuraCheck, AuraRadio


class TestI18nEngine(unittest.TestCase):
    def setUp(self):
        set_language("zh-TW")

    def tearDown(self):
        set_language("zh-TW")

    def test_supported_languages_and_cycling(self):
        """驗證支援的 4 種語系與循環切換邏輯"""
        self.assertEqual([c for c, _ in SUPPORTED_LANGUAGES], ["zh-TW", "en", "ja", "zh-CN"])
        self.assertEqual(set_language("en"), "en")
        self.assertEqual(get_language(), "en")
        self.assertEqual(get_language_badge("en"), "🌐 EN")
        self.assertEqual(get_language_badge("ja"), "🌐 日本語")
        self.assertEqual(get_language_badge("zh-CN"), "🌐 简中")
        self.assertEqual(get_language_badge("zh-TW"), "🌐 繁中")

        # 循環切換順序
        c1 = next_language("zh-TW")
        c2 = next_language(c1)
        c3 = next_language(c2)
        c4 = next_language(c3)
        self.assertEqual([c1, c2, c3, c4], ["en", "ja", "zh-CN", "zh-TW"])

    def test_detect_system_locale(self):
        """驗證系統語系偵測回傳合法語系代碼"""
        loc = detect_system_locale()
        self.assertIn(loc, dict(SUPPORTED_LANGUAGES))

    def test_phrase_translations_all_languages(self):
        """驗證核心 UI、畫中畫去背、視窗排除與剪輯工作站詞彙於 4 種語系之翻譯"""
        key_phrases = [
            "螢幕錄影與截圖",
            "開始錄製",
            "停止錄製",
            "畫面截圖",
            "剪輯工作站",
            "個人視訊鏡頭 (畫中畫)",
            "原始畫面 (不去背)",
            "人像景深虛化 (Blur)",
            "智慧人像去背 (僅保留人像)",
            "綠幕扣像去背 (Chroma Key)",
            "極光漸層虛擬背景 (Aurora)",
            "🛡️ 設定視窗排除與浮水印…",
            "⚡ 一鍵匯出影片",
            "💬 智慧字幕…",
        ]
        for phrase in key_phrases:
            self.assertEqual(tr(phrase, "zh-TW"), phrase)
            en_val = tr(phrase, "en")
            ja_val = tr(phrase, "ja")
            cn_val = tr(phrase, "zh-CN")
            self.assertTrue(len(en_val) > 0)
            self.assertTrue(len(ja_val) > 0)
            self.assertTrue(len(cn_val) > 0)
            self.assertNotEqual(en_val, phrase, f"English translation missing for: {phrase}")
            self.assertNotEqual(ja_val, phrase, f"Japanese translation missing for: {phrase}")

    def test_dynamic_regex_translations(self):
        """驗證動態數值字串之正則翻譯規則"""
        s1 = "選取長度 01:23.4 (85%)"
        self.assertEqual(tr(s1, "en"), "Selected 01:23.4 (85%)")
        self.assertEqual(tr(s1, "ja"), "選択範囲 01:23.4 (85%)")
        self.assertEqual(tr(s1, "zh-CN"), "选取长度 01:23.4 (85%)")

        s2 = "最近的錄影 (共 15 個檔案)"
        self.assertEqual(tr(s2, "en"), "Recent Recordings (15 files)")
        self.assertEqual(tr(s2, "ja"), "最近の録画 (全 15 件)")
        self.assertEqual(tr(s2, "zh-CN"), "最近的录影 (共 15 个文件)")

        s3 = "焦點座標: X 50% · Y 50%"
        self.assertEqual(tr(s3, "en"), "Focus: X 50% · Y 50%")
        self.assertEqual(tr(s3, "ja"), "フォーカス座標: X 50% · Y 50%")
        self.assertEqual(tr(s3, "zh-CN"), "焦点坐标: X 50% · Y 50%")

    def test_traditional_to_simplified_fallback(self):
        """驗證未列入詞庫之繁體句子可自動轉換為簡體中文"""
        raw = "錄影與視訊鏡頭設定"
        simp = to_simplified_chinese(raw)
        self.assertEqual(simp, "录影与摄像头设定")

    def test_tkinter_widget_tree_and_menu_lossless_switching(self):
        """驗證 Tkinter 元件樹、Aura 自訂元件與 Combobox 支援無限次多語系無損切換"""
        try:
            root = tk.Tk()
            root.withdraw()
        except tk.TclError:
            self.skipTest("Tkinter display unavailable in headless environment")
            return

        try:
            frame = tk.Frame(root)
            lbl = tk.Label(frame, text="螢幕錄影與截圖")
            lbl.pack()

            aura_btn = AuraButton(frame, text="開始錄製")
            aura_btn.pack()

            chk_var = tk.BooleanVar(value=True)
            aura_chk = AuraCheck(frame, text="個人視訊鏡頭 (畫中畫)", variable=chk_var)
            aura_chk.pack()

            rad_var = tk.StringVar(value="full")
            aura_rad = AuraRadio(frame, text="全螢幕", variable=rad_var, value="full")
            aura_rad.pack()

            pip_values = [
                "原始畫面 (不去背)",
                "人像景深虛化 (Blur)",
                "智慧人像去背 (僅保留人像)",
                "綠幕扣像去背 (Chroma Key)",
                "極光漸層虛擬背景 (Aurora)",
            ]
            combo = ttk.Combobox(frame, values=pip_values, state="readonly")
            combo.current(2)  # 選中第 3 項「智慧人像去背 (僅保留人像)」
            combo.pack()

            menu = tk.Menu(root, tearoff=0)
            menu.add_command(label="偏好設定…")
            menu.add_command(label="開啟剪輯工作站")

            # 1. 切換至英文 (en)
            translate_widget_tree(frame, "en")
            translate_menu(menu, "en")
            self.assertEqual(lbl.cget("text"), "Screen Recorder & Capture")
            self.assertEqual(aura_btn._text, "Start Recording")
            self.assertEqual(aura_chk._label.cget("text"), "Camera Picture-in-Picture (PiP)")
            self.assertEqual(aura_rad.winfo_children()[1].cget("text"), "Full Screen")
            self.assertEqual(combo.current(), 2)
            self.assertEqual(combo.get(), "Smart Cutout (Person Only)")
            self.assertEqual(menu.entrycget(0, "label"), "Preferences…")

            # 2. 切換至日文 (ja)
            translate_widget_tree(frame, "ja")
            translate_menu(menu, "ja")
            self.assertEqual(lbl.cget("text"), "画面録画・スクリーンショット")
            self.assertEqual(aura_btn._text, "録画開始")
            self.assertEqual(combo.current(), 2)
            self.assertEqual(combo.get(), "スマート人物切り抜き (人物のみ)")
            self.assertEqual(menu.entrycget(0, "label"), "環境設定…")

            # 3. 切換至簡體中文 (zh-CN)
            translate_widget_tree(frame, "zh-CN")
            translate_menu(menu, "zh-CN")
            self.assertEqual(lbl.cget("text"), "屏幕录制与截图")
            self.assertEqual(aura_btn._text, "开始录制")
            self.assertEqual(combo.current(), 2)
            self.assertEqual(combo.get(), "智能人像抠图 (仅保留人像)")

            # 4. 切換回繁體中文 (zh-TW)，驗證 100% 還原原始字串與索引
            translate_widget_tree(frame, "zh-TW")
            translate_menu(menu, "zh-TW")
            self.assertEqual(lbl.cget("text"), "螢幕錄影與截圖")
            self.assertEqual(aura_btn._text, "開始錄製")
            self.assertEqual(aura_chk._label.cget("text"), "個人視訊鏡頭 (畫中畫)")
            self.assertEqual(aura_rad.winfo_children()[1].cget("text"), "全螢幕")
            self.assertEqual(combo.current(), 2)
            self.assertEqual(combo.get(), "智慧人像去背 (僅保留人像)")
            self.assertEqual(menu.entrycget(0, "label"), "偏好設定…")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
