import unittest
from unittest.mock import patch
import urllib.error

import auto_updater as au

REPO = "malilion/Record"
BASE = f"https://github.com/{REPO}/releases/download/v1.0.0/"


def _assets(*names):
    return [{"name": n, "browser_download_url": BASE + n} for n in names]


class TestUpdaterUrlSafety(unittest.TestCase):
    def test_scheme_and_host_validation(self):
        ok = au.is_safe_github_url
        self.assertTrue(ok("https://github.com/malilion/Record/releases"))
        self.assertFalse(ok("http://github.com/malilion/Record/releases"))
        self.assertFalse(ok("file:///etc/passwd"))
        self.assertFalse(ok("javascript:alert(1)"))
        self.assertFalse(ok("https://github.com.evil.com/x"))
        self.assertFalse(ok("https://evil.com/github.com/x"))
        self.assertFalse(ok("https://github.com@evil.com/x"))
        self.assertFalse(ok("https://user:pw@github.com/x"))
        self.assertFalse(ok("https://github.com:8443/x"))
        self.assertFalse(ok("https://objects.githubusercontent.com/x"))
        self.assertFalse(ok(None))

    def test_asset_exact_allowlist_mac(self):
        with patch.object(au, "IS_MAC", True), patch.object(au, "IS_WINDOWS", False):
            url = au.find_matching_asset(_assets("evil-aura.dmg", "AURA-REC-macOS.zip", "AURA-REC-macOS.dmg"))
            self.assertEqual(url, BASE + "AURA-REC-macOS.dmg")
            self.assertIsNone(au.find_matching_asset(_assets("evil-aura.dmg", "aura-mac.zip")))

    def test_asset_exact_allowlist_windows(self):
        with patch.object(au, "IS_MAC", False), patch.object(au, "IS_WINDOWS", True):
            self.assertEqual(au.find_matching_asset(_assets("AURA-REC-Windows-x64.zip", "AURA-REC-Setup.exe")),
                             BASE + "AURA-REC-Setup.exe")
            self.assertIsNone(au.find_matching_asset(_assets("setup.exe")))

    def test_asset_url_must_be_trusted(self):
        bad = [{"name": "AURA-REC-macOS.dmg", "browser_download_url": "https://evil.com/AURA-REC-macOS.dmg"},
               {"name": "AURA-REC-macOS.zip", "browser_download_url": "http://github.com/malilion/Record/releases/download/v1/AURA-REC-macOS.zip"}]
        other_repo = [{"name": "AURA-REC-macOS.dmg",
                       "browser_download_url": "https://github.com/evil/Other/releases/download/v1/AURA-REC-macOS.dmg"}]
        with patch.object(au, "IS_MAC", True):
            self.assertIsNone(au.find_matching_asset(bad))
            self.assertIsNone(au.find_matching_asset(other_repo))

    def test_redirect_handler_blocks_foreign_hosts(self):
        h = au._LimitedRedirectHandler()
        self.assertEqual(h.max_redirections, au.MAX_REDIRECTS)
        with self.assertRaises(urllib.error.URLError):
            h.redirect_request(None, None, 302, "Found", {}, "https://evil.com/x")
        with self.assertRaises(urllib.error.URLError):
            h.redirect_request(None, None, 302, "Found", {}, "http://api.github.com/x")

    def test_invalid_repo_rejected(self):
        res = au.fetch_latest_release(repo="../../etc")
        self.assertFalse(res["success"])

    def test_fetch_sanitizes_malicious_release_urls(self):
        import io, json
        payload = {"tag_name": "v9.9.9", "html_url": "file:///etc/passwd", "body": None,
                   "assets": [{"name": "AURA-REC-macOS.dmg", "browser_download_url": "https://evil.com/a.dmg"}]}

        class _Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False

        class _Opener:
            def open(self, req, timeout=None):
                return _Resp(json.dumps(payload).encode())

        with patch.object(au, "IS_MAC", True), patch("urllib.request.build_opener", return_value=_Opener()):
            res = au.fetch_latest_release()
        self.assertTrue(res["success"])
        self.assertEqual(res["download_url"], au.GITHUB_RELEASES_URL)
        self.assertEqual(res["release_url"], au.GITHUB_RELEASES_URL)


if __name__ == "__main__":
    unittest.main()
