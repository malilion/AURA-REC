"""
auto_updater.py - AURA REC 軟體自動檢查更新模組 (Auto Updater)

功能特色：
1. 串接 GitHub Releases API (https://api.github.com/repos/malilion/Record/releases/latest)
2. 跨平台非同步背景線程檢查，零 UI 卡頓、零外部依賴 (純 Python 標準庫 urllib + json)。
3. 嚴謹的語意化版本號比對 (Semantic Versioning)，支援 v 前綴與預發行版本。
4. 現代暗色系更新提示對話框，具備新版特性說明 (Changelog)、版本對照徽章、以及一鍵直連下載。
5. 支援「啟動時自動檢查」與「主選單手動檢查更新」。
"""

import re
import sys
import json
import logging
import threading
import webbrowser
import urllib.request
import urllib.error
import urllib.parse
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger("AuraUpdater")

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform.startswith("win")

DEFAULT_REPO = "malilion/Record"
GITHUB_RELEASES_URL = f"https://github.com/{DEFAULT_REPO}/releases"

# 安全限制：只允許 https，且 host 必須在白名單內。
# - api.github.com：Releases API。
# - github.com：release 頁面與 browser_download_url
#   (https://github.com/<owner>/<repo>/releases/download/<tag>/<asset>)。
# 不加入 objects.githubusercontent.com：本模組只「開啟瀏覽器」而不下載檔案，
# github.com -> objects.githubusercontent.com 的資產轉址是由瀏覽器自己處理，
# 程式端不會 follow 該轉址；若日後改成程式內下載才需要加入並再審查。
ALLOWED_API_HOSTS = frozenset({"api.github.com"})
ALLOWED_DOWNLOAD_HOSTS = frozenset({"github.com"})
MAX_REDIRECTS = 2
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# 精確的 Release 資產檔名白名單（需與 .github/workflows/build_desktop.yml 產物一致），依偏好順序。
MAC_ASSET_NAMES = ("AURA-REC-macOS.dmg", "AURA-REC-macOS.zip")
WINDOWS_ASSET_NAMES = ("AURA-REC-Setup.exe", "AURA-REC.exe", "AURA-REC-Windows-x64.zip")


def is_safe_github_url(url, allowed_hosts=ALLOWED_DOWNLOAD_HOSTS, path_prefix: str = "") -> bool:
    """URL 必須是 https、host 精確位於白名單、無 userinfo / 非預設 port，且 path 符合前綴。"""
    try:
        u = urllib.parse.urlsplit(str(url))
        if u.scheme != "https" or u.hostname not in allowed_hosts:
            return False
        if u.username or u.password or u.port not in (None, 443):
            return False
        return u.path.startswith(path_prefix)
    except Exception:
        return False


class _LimitedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """限制轉址次數，且每次轉址目標都必須是 https + API host 白名單。"""

    max_redirections = MAX_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_safe_github_url(newurl, ALLOWED_API_HOSTS):
            raise urllib.error.URLError(f"拒絕不安全的轉址目標: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def parse_version(v: str) -> tuple:
    """解析版本號字串為整數元組，例如 'v2.5.1' -> (2, 5, 1)"""
    cleaned = re.sub(r"^[vV]", "", str(v or "0.0.0").strip())
    parts = []
    for token in re.split(r"[-._]", cleaned):
        if token.isdigit():
            parts.append(int(token))
        else:
            break
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer_version(remote_ver: str, local_ver: str) -> bool:
    """判斷遠端版本是否高於本地版本"""
    return parse_version(remote_ver) > parse_version(local_ver)


def find_matching_asset(assets: list, repo: str = DEFAULT_REPO) -> Optional[str]:
    """依當前作業系統，以「精確檔名白名單」尋找下載連結；URL 亦須通過 https + host + 路徑驗證。"""
    if not isinstance(assets, list):
        return None

    if IS_MAC:
        wanted = MAC_ASSET_NAMES
    elif IS_WINDOWS:
        wanted = WINDOWS_ASSET_NAMES
    else:
        return None

    prefix = f"/{repo}/releases/download/"
    by_name = {}
    for a in assets:
        if isinstance(a, dict):
            by_name.setdefault(str(a.get("name", "")), a.get("browser_download_url"))

    for name in wanted:
        url = by_name.get(name)
        if url and is_safe_github_url(url, ALLOWED_DOWNLOAD_HOSTS, prefix) and url.rsplit("/", 1)[-1] == name:
            return url
    return None


def fetch_latest_release(repo: str = DEFAULT_REPO, timeout: float = 6.0) -> Dict[str, Any]:
    """
    透過 GitHub REST API 取得最新 Release 資料 (同步阻塞函式，請於背景線程呼叫)
    """
    if not _REPO_RE.match(str(repo)):
        return {"success": False, "error": "無效的更新來源設定"}
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "AURA-REC-Desktop-App",
            "Accept": "application/vnd.github.v3+json",
        },
    )

    try:
        opener = urllib.request.build_opener(_LimitedRedirectHandler)
        with opener.open(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            tag = payload.get("tag_name", "")
            assets = payload.get("assets", [])
            # API 回傳的 URL 不可信：僅接受 https://github.com/<repo>/releases...，否則退回預設發布頁
            safe_releases = f"https://github.com/{repo}/releases"
            release_url = payload.get("html_url", "")
            if not is_safe_github_url(release_url, ALLOWED_DOWNLOAD_HOSTS, f"/{repo}/releases"):
                release_url = safe_releases
            download_url = find_matching_asset(assets, repo) or release_url

            return {
                "success": True,
                "latest_version": tag,
                "release_name": payload.get("name") or tag,
                "release_notes": (payload.get("body") or "").strip(),
                "release_url": release_url,
                "download_url": download_url,
                "published_at": payload.get("published_at", ""),
                "assets_count": len(assets),
                "error": None,
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # 倉庫尚未公開或尚未建立 Release
            err_msg = "目前尚未發布公開更新版本或暫無新版本。"
        elif e.code == 403:
            err_msg = "GitHub API 請求次數已達限制，請稍候重試或手動開啟發布頁面。"
        else:
            err_msg = f"GitHub 伺服器回應異常 (HTTP {e.code})"
        return {"success": False, "error": err_msg, "error_code": e.code}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"無法連線至更新伺服器，請檢查網路連線 ({e.reason})"}
    except Exception as e:
        return {"success": False, "error": f"檢查更新時發生錯誤: {e}"}


class UpdateDialog:
    """發現新版本時彈出的現代質感暗色對話框"""

    def __init__(self, parent_root: tk.Tk, update_info: Dict[str, Any], current_ver: str, ui_theme: dict, fonts: dict):
        self.root = parent_root
        self.info = update_info
        self.current_ver = current_ver
        self.ui = ui_theme
        self.fonts = fonts

        self.win = tk.Toplevel(parent_root)
        self.win.title("軟體更新 — AURA REC")
        self.win.geometry("540x520")
        self.win.minsize(480, 440)
        self.win.configure(bg=self.ui["bg"])
        self.win.transient(parent_root)
        self.win.grab_set()

        self._build_ui()

    def _build_ui(self):
        card = tk.Frame(self.win, bg=self.ui["card"], highlightbackground=self.ui["edge"], highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        # 頂部極光青微光飾條
        accent_bar = tk.Frame(card, bg=self.ui["blue"], height=3)
        accent_bar.pack(fill=tk.X)

        content = tk.Frame(card, bg=self.ui["card"])
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)

        # 標題
        title_row = tk.Frame(content, bg=self.ui["card"])
        title_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            title_row,
            text="✨ 發現新版本 AURA REC！",
            font=self.fonts.get("bold", ("Helvetica", 14, "bold")),
            fg=self.ui["white"],
            bg=self.ui["card"],
        ).pack(side=tk.LEFT)

        # 版本對照標籤
        latest_tag = self.info.get("latest_version", "")
        ver_box = tk.Frame(content, bg=self.ui["field"], highlightbackground=self.ui["edge"], highlightthickness=1)
        ver_box.pack(fill=tk.X, pady=(4, 14), ipady=6, ipadx=10)

        tk.Label(
            ver_box,
            text=f"目前版本：v{self.current_ver}   ➔   最新版本：{latest_tag}",
            font=self.fonts.get("bold", ("Helvetica", 12, "bold")),
            fg=self.ui["blue"],
            bg=self.ui["field"],
        ).pack(anchor="w", padx=6)

        # 發布名稱
        rel_name = self.info.get("release_name", "")
        if rel_name and rel_name != latest_tag:
            tk.Label(
                content,
                text=rel_name,
                font=self.fonts.get("bold", ("Helvetica", 12, "bold")),
                fg=self.ui["text"],
                bg=self.ui["card"],
            ).pack(anchor="w", pady=(0, 6))

        # 更新內容說明區
        tk.Label(
            content,
            text="新版功能與更新說明：",
            font=self.fonts.get("badge", ("Helvetica", 10)),
            fg=self.ui["muted"],
            bg=self.ui["card"],
        ).pack(anchor="w", pady=(0, 4))

        notes_frame = tk.Frame(content, bg=self.ui["field"], highlightbackground=self.ui["edge"], highlightthickness=1)
        notes_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 16))

        notes_text = tk.Text(
            notes_frame,
            wrap=tk.WORD,
            bg=self.ui["field"],
            fg=self.ui["text"],
            font=self.fonts.get("body", ("Helvetica", 11)),
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=8,
        )
        notes_scroll = ttk.Scrollbar(notes_frame, orient="vertical", command=notes_text.yview)
        notes_text.configure(yscrollcommand=notes_scroll.set)
        notes_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        notes_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        raw_notes = self.info.get("release_notes") or "本次更新包含效能提升、功能優化與穩定性修復。"
        notes_text.insert("1.0", raw_notes)
        notes_text.configure(state=tk.DISABLED)

        # 按鈕列
        btn_row = tk.Frame(content, bg=self.ui["card"])
        btn_row.pack(fill=tk.X, pady=(4, 0))

        def _on_download():
            target_url = self.info.get("download_url") or self.info.get("release_url") or GITHUB_RELEASES_URL
            if not is_safe_github_url(target_url, ALLOWED_DOWNLOAD_HOSTS):
                target_url = GITHUB_RELEASES_URL
            try:
                webbrowser.open(target_url)
            except Exception:
                pass
            self.win.destroy()

        def _on_remind_later():
            self.win.destroy()

        # 稍後提醒
        btn_cancel = tk.Button(
            btn_row,
            text="稍後提醒",
            command=_on_remind_later,
            bg=self.ui.get("field", "#0A0C10"),
            fg=self.ui.get("text", "#F8FAFC"),
            activebackground=self.ui.get("hover", "#151922"),
            activeforeground=self.ui.get("white", "#FFFFFF"),
            bd=0,
            relief=tk.FLAT,
            padx=14,
            pady=6,
            font=self.fonts.get("bold", ("Helvetica", 11, "bold")),
            cursor="hand2",
        )
        btn_cancel.pack(side=tk.LEFT)

        # 前往下載 (主要按鈕)
        btn_download = tk.Button(
            btn_row,
            text="前往下載更新",
            command=_on_download,
            bg=self.ui.get("blue", "#00F0FF"),
            fg="#000000",
            activebackground=self.ui.get("blue_hover", "#66F6FF"),
            activeforeground="#000000",
            bd=0,
            relief=tk.FLAT,
            padx=18,
            pady=6,
            font=self.fonts.get("bold", ("Helvetica", 11, "bold")),
            cursor="hand2",
        )
        btn_download.pack(side=tk.RIGHT)


class AutoUpdater:
    """負責檢查更新排程與對話框協調的管理者"""

    def __init__(self, parent_root: tk.Tk, current_version: str, ui_theme: dict, fonts: dict, repo: str = DEFAULT_REPO):
        self.root = parent_root
        self.current_version = current_version
        self.ui = ui_theme
        self.fonts = fonts
        self.repo = repo
        self._is_checking = False

    def check_now(self, is_manual: bool = True, on_finish: Optional[Callable] = None):
        """非同步向 GitHub 檢查更新"""
        if self._is_checking:
            return
        self._is_checking = True

        def _worker():
            res = fetch_latest_release(repo=self.repo)
            # 調度回主線程處理 UI
            self.root.after(0, lambda: self._handle_result(res, is_manual, on_finish))

        threading.Thread(target=_worker, daemon=True).start()

    def _handle_result(self, res: Dict[str, Any], is_manual: bool, on_finish: Optional[Callable]):
        self._is_checking = False

        if on_finish:
            try:
                on_finish(res)
            except Exception:
                pass

        if res.get("success"):
            remote_ver = res.get("latest_version", "")
            has_update = is_newer_version(remote_ver, self.current_version)
            res["has_update"] = has_update

            if has_update:
                UpdateDialog(
                    self.root,
                    update_info=res,
                    current_ver=self.current_version,
                    ui_theme=self.ui,
                    fonts=self.fonts,
                )
            elif is_manual:
                messagebox.showinfo(
                    "軟體已是最新版本",
                    f"🎉 您目前使用的已是最新版本！\n\n"
                    f"目前版本：v{self.current_version}\n"
                    f"GitHub 最新發布：{remote_ver}\n\n"
                    f"所有功能與效能皆保持最新最佳狀態。",
                )
        else:
            if is_manual:
                err_msg = res.get("error", "未知網路錯誤")
                if messagebox.askyesno(
                    "檢查更新提示",
                    f"{err_msg}\n\n是否直接開啟 AURA REC GitHub 發布頁面手動檢查？",
                ):
                    try:
                        webbrowser.open(f"https://github.com/{self.repo}/releases")
                    except Exception:
                        pass
