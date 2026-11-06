"""
Cầu nối kiểm tra và tự động cập nhật Dynamic Notch từ GitHub Releases.
Kho lưu trữ: https://github.com/Masonnica/Dynamic-Notch
"""
import os
import sys
import tempfile
import threading
import subprocess
import requests
from pathlib import Path
from config import APP_VERSION, GITHUB_REPO


class UpdaterBridge:
    def __init__(self, island):
        self.island = island
        self.status = "idle"         # idle | checking | update_available | up_to_date | downloading | ready | error
        self.message = ""
        self.latest_version = APP_VERSION
        self.download_url = None
        self.release_notes = ""
        self.download_progress = 0   # 0..100 %
        self._lock = threading.Lock()

    def check_for_updates(self, auto_download=False):
        """Kiểm tra bản cập nhật mới trên GitHub Releases trong luồng nền."""
        with self._lock:
            if self.status in ("checking", "downloading"):
                return
            self.status = "checking"
            self.message = "Đang kiểm tra bản cập nhật mới..."

        threading.Thread(target=self._run_check, args=(auto_download,), daemon=True).start()

    def _run_check(self, auto_download):
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "DynamicNotch-App"}
            resp = requests.get(url, headers=headers, timeout=10)

            if resp.status_code == 404:
                with self._lock:
                    self.status = "up_to_date"
                    self.message = f"Phiên bản v{APP_VERSION} là mới nhất (chưa có release)."
                return

            if not resp.ok:
                with self._lock:
                    self.status = "error"
                    self.message = f"Lỗi máy chủ GitHub ({resp.status_code})"
                return

            data = resp.json()
            # Xử lý cả 'v', 'V' hoặc chuỗi version thuần túy
            raw_tag = data.get("tag_name", "").strip()
            clean_tag = raw_tag.lstrip("vV").strip()
            self.release_notes = data.get("body", "")

            # Tìm file cài đặt .exe trong assets
            assets = data.get("assets", [])
            download_url = None
            for asset in assets:
                name = asset.get("name", "").lower()
                if name.endswith(".exe"):
                    download_url = asset.get("browser_download_url")
                    break

            is_newer = self._compare_versions(clean_tag, APP_VERSION) > 0

            with self._lock:
                self.latest_version = clean_tag
                self.download_url = download_url

                if is_newer:
                    self.status = "update_available"
                    self.message = f"Đã có phiên bản mới: V{clean_tag}!"
                else:
                    self.status = "up_to_date"
                    self.message = "Phiên bản mới nhất đã được cài đặt"

            if is_newer and auto_download and download_url:
                self.download_and_install()

        except Exception as ex:
            with self._lock:
                self.status = "error"
                self.message = "Không thể kết nối tới GitHub."

    def download_and_install(self):
        """Tải bản cập nhật và khởi chạy trình cài đặt."""
        with self._lock:
            if not self.download_url or self.status == "downloading":
                return
            self.status = "downloading"
            self.download_progress = 0
            self.message = "Đang tải bản cập nhật..."

        threading.Thread(target=self._run_download, daemon=True).start()

    def _run_download(self):
        try:
            headers = {"User-Agent": "DynamicNotch-App"}
            with requests.get(self.download_url, headers=headers, stream=True, timeout=30) as r:
                r.raise_for_status()
                total_size = int(r.headers.get("content-length", 0))
                temp_dir = tempfile.gettempdir()
                installer_path = Path(temp_dir) / f"DynamicNotch_Update_{self.latest_version}.exe"

                downloaded = 0
                with open(installer_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                prog = int(downloaded * 100 / total_size)
                                with self._lock:
                                    self.download_progress = prog
                                    self.message = f"Đang tải... {prog}%"

            with self._lock:
                self.status = "ready"
                self.message = "Đang chuẩn bị cài đặt..."

            # Khởi chạy installer và đóng app hiện tại
            # Tham số /SILENT hoặc /VERYSILENT có thể dùng nếu muốn cài âm thầm
            subprocess.Popen([str(installer_path)])
            self.island.quit = True

        except Exception as ex:
            with self._lock:
                self.status = "error"
                self.message = "Tải bản cập nhật thất bại."

    @staticmethod
    def _compare_versions(v1, v2):
        """So sánh version dạng semantic (ví dụ 1.0.1 với 1.0.0). Trả về > 0 nếu v1 > v2."""
        try:
            p1 = [int(x) for x in v1.split(".")]
            p2 = [int(x) for x in v2.split(".")]
            for a, b in zip(p1, p2):
                if a != b:
                    return 1 if a > b else -1
            return len(p1) - len(p2)
        except Exception:
            return 1 if v1 != v2 else 0
