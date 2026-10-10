"""APP_VERSION 與 Windows 安裝程式版本號必須一致。"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class TestVersionSync(unittest.TestCase):
    def test_installer_version_matches_app_version(self):
        app = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', (ROOT / "platform_utils.py").read_text(encoding="utf-8")).group(1)
        iss = re.search(r'#define MyAppVersion "([^"]+)"', (ROOT / "installer" / "AURA-REC-Setup.iss").read_text(encoding="utf-8")).group(1)
        self.assertEqual(app, iss)


if __name__ == "__main__":
    unittest.main()
