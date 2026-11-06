"""
Cầu nối Lịch Google Calendar:
- Hỗ trợ đồng bộ bằng Link iCal (Secret address in iCal format) - phương thức chuẩn, nhanh và ổn định nhất cho người dùng phổ thông.
- Hỗ trợ kéo thả và nhập trực tiếp file .ics hoặc file .zip xuất từ Google Calendar.
- Tự động lưu trữ và phân tích sự kiện lịch, lời nhắc, ngày lễ.
- Hỗ trợ bật/tắt từng loại lịch độc lập.
- Không phụ thuộc vào Playwright hay Node.js.
"""
import os
import re
import json
import time
import shutil
import zipfile
import threading
from datetime import date, datetime, timedelta, timezone
try:
    import zoneinfo
except ImportError:
    zoneinfo = None
from pathlib import Path
import requests

from config import (
    GOOGLE_PREFS_FILE,
    CALENDARS_DIR,
    ACCENT,
    BADGES,
)


def parse_ics_date(s, cal_tz_str=None):
    """Chuyển chuỗi DTSTART/DTEND dạng RFC 5545 thành datetime hoặc date và quy về múi giờ địa phương máy tính.
    
    Hỗ trợ:
    - UTC kết thúc bằng Z (vd 20261110T000000Z) -> chuyển sang múi giờ máy tính (vd GMT+7: 07:00)
    - Kèm TZID=... trong tham số dòng (vd DTSTART;TZID=Asia/Ho_Chi_Minh:20250118T095000)
    - Định dạng ngày cả ngày (vd 20261110)
    """
    raw = s.strip()
    is_utc = raw.endswith("Z")
    cleaned = raw.replace("Z", "")
    if "T" in cleaned:
        try:
            val = cleaned[:15]
            dt = datetime.strptime(val, "%Y%m%dT%H%M%S")
            if is_utc:
                dt = dt.replace(tzinfo=timezone.utc).astimezone()
            elif cal_tz_str and zoneinfo:
                try:
                    tz = zoneinfo.ZoneInfo(cal_tz_str)
                    dt = dt.replace(tzinfo=tz).astimezone()
                except Exception:
                    pass
            # Trả về datetime naive theo giờ địa phương
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return dt, False
        except Exception:
            pass
    try:
        val = cleaned[:8]
        d = datetime.strptime(val, "%Y%m%d").date()
        return d, True
    except Exception:
        return None, True


def parse_ics_content(text, cal_id, default_name, color):
    """Phân tích nội dung file .ics thành danh sách sự kiện gom nhóm theo ngày."""
    m_name = re.search(r"X-WR-CALNAME:(.+)", text)
    cal_name = m_name.group(1).strip() if m_name else default_name

    m_tz = re.search(r"X-WR-TIMEZONE:(.+)", text)
    cal_tz = m_tz.group(1).strip() if m_tz else None

    events_by_date = {}
    raw_events = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, flags=re.DOTALL)
    for raw in raw_events:
        if re.search(r"STATUS:\s*CANCELLED", raw, flags=re.IGNORECASE):
            continue

        m_sum = re.search(r"SUMMARY:(.+)", raw)
        title = m_sum.group(1).strip() if m_sum else "(Không có tiêu đề)"
        title = title.replace(r"\,", ",").replace(r"\;", ";").replace(r"\n", " ").strip()

        m_start_line = re.search(r"DTSTART([^:\r\n]*):([^\r\n]+)", raw)
        if not m_start_line:
            continue
        start_params, start_val = m_start_line.group(1), m_start_line.group(2)
        m_tzid = re.search(r"TZID=([^;:]+)", start_params)
        ev_tz = m_tzid.group(1).strip() if m_tzid else cal_tz

        dt_start, is_allday = parse_ics_date(start_val, ev_tz)
        if not dt_start:
            continue

        m_end_line = re.search(r"DTEND([^:\r\n]*):([^\r\n]+)", raw)
        dt_end = None
        if m_end_line:
            end_params, end_val = m_end_line.group(1), m_end_line.group(2)
            m_end_tzid = re.search(r"TZID=([^;:]+)", end_params)
            end_tz = m_end_tzid.group(1).strip() if m_end_tzid else ev_tz
            dt_end, _ = parse_ics_date(end_val, end_tz)

        if is_allday:
            key = ""
            time_label = "Cả ngày"
            d = dt_start if isinstance(dt_start, date) else dt_start.date()
            end_d = dt_end if isinstance(dt_end, date) else (dt_end.date() if dt_end else d)
            cur_d = d
            while cur_d < end_d and (cur_d - d).days < 62:
                events_by_date.setdefault(cur_d, []).append({
                    "key": key,
                    "time_label": time_label,
                    "title": title,
                    "color": color,
                    "cal_id": cal_id,
                    "cal_name": cal_name,
                })
                cur_d += timedelta(days=1)
            if cur_d == d:
                events_by_date.setdefault(d, []).append({
                    "key": key,
                    "time_label": time_label,
                    "title": title,
                    "color": color,
                    "cal_id": cal_id,
                    "cal_name": cal_name,
                })
        else:
            d = dt_start.date()
            start_hm = dt_start.strftime("%H:%M")
            if dt_end and isinstance(dt_end, datetime) and dt_end.date() == d:
                time_label = f"{start_hm} - {dt_end.strftime('%H:%M')}"
            else:
                time_label = start_hm
            key = start_hm
            events_by_date.setdefault(d, []).append({
                "key": key,
                "time_label": time_label,
                "title": title,
                "color": color,
                "cal_id": cal_id,
                "cal_name": cal_name,
            })

    return cal_name, events_by_date


class GoogleCalendar:
    """Quản lý kết nối và đồng bộ Google Calendar."""

    def __init__(self):
        self.state = "disconnected"          # disconnected | connecting | connected
        self.message = ""                    # thông báo trạng thái hoặc lỗi
        self.month_events = {}               # (năm, tháng) -> {date: [event_dict, ...]}
        self.all_events_by_date = {}         # date -> [event_dict, ...]
        self.calendars = []                  # [{"id", "name", "color", "primary"}, ...]
        self.enabled_cals = None             # set các calendar_id đang bật hiển thị
        self.is_connecting = False
        self.ical_urls = {}                  # {stem -> url} - nhiều link iCal
        self.saved_ical_url = ""             # giữ lại để tương thích file cấu hình cũ
        self.last_sync_time = 0.0

        CALENDARS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_prefs()
        self._load_local_ics()

        # Tự động đồng bộ tất cả link iCal nền khi khởi động
        if self.ical_urls:
            threading.Thread(target=self._sync_all_urls, daemon=True).start()

    # ---------------------------- Tùy chọn Bật/Tắt & Cấu hình ----------------------------
    def _load_prefs(self):
        """Đọc cấu hình bật/tắt lịch và danh sách link iCal đã lưu."""
        try:
            if GOOGLE_PREFS_FILE.exists():
                data = json.loads(GOOGLE_PREFS_FILE.read_text(encoding="utf-8"))
                ids = data.get("enabled_ids")
                if isinstance(ids, list):
                    self.enabled_cals = set(ids)

                # Hỗ trợ cả format mới (ical_urls: dict) lẫn format cũ (ical_url: str)
                if isinstance(data.get("ical_urls"), dict):
                    self.ical_urls = data["ical_urls"]
                    self.saved_ical_url = next(iter(self.ical_urls.values()), "")
                elif data.get("ical_url"):
                    # Tự động nâng cấp format cũ → dict
                    self.ical_urls = {"google_synced": data["ical_url"]}
                    self.saved_ical_url = data["ical_url"]
                else:
                    self.ical_urls = {}
                    self.saved_ical_url = ""
                return
        except Exception:
            pass
        self.enabled_cals = None
        self.ical_urls = {}
        self.saved_ical_url = ""

    def _save_prefs(self):
        """Lưu danh sách ID lịch đang bật và tất cả link iCal."""
        try:
            payload = {
                "enabled_ids": list(self.enabled_cals or set()),
                "ical_urls": self.ical_urls,
                # Giữ trường cũ để tương thích nếu cần downgrade
                "ical_url": next(iter(self.ical_urls.values()), ""),
            }
            GOOGLE_PREFS_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def get_enabled_calendar_ids(self):
        """Lấy tập hợp các ID lịch đang được kích hoạt hiển thị."""
        if self.enabled_cals is None:
            self.get_calendars()
        return set(self.enabled_cals or set())

    def toggle_calendar(self, cal_id):
        """Bật/tắt một loại lịch và lưu cấu hình."""
        if self.enabled_cals is None:
            self.get_calendars()
        if self.enabled_cals is None:
            self.enabled_cals = set()

        if cal_id in self.enabled_cals:
            self.enabled_cals.remove(cal_id)
        else:
            self.enabled_cals.add(cal_id)
        self._save_prefs()

    def set_all_calendars(self, enable_all=True):
        """Bật hoặc tắt tất cả các loại lịch."""
        cals = self.get_calendars()
        if enable_all:
            self.enabled_cals = {c["id"] for c in cals}
        else:
            self.enabled_cals = set()
        self._save_prefs()

    # ---------------------------- Nạp Lịch Bằng Link iCal (Khuyên dùng) ----------------------------
    def _make_stem(self, url):
        """Tạo tên file (stem) duy nhất cho một URL iCal mới."""
        # Nếu URL đã có stem tương ứng thì tái sử dụng
        for stem, u in self.ical_urls.items():
            if u == url:
                return stem
        # Tạo stem mới: google_synced, google_synced_1, google_synced_2, ...
        base = "google_synced"
        if base not in self.ical_urls:
            return base
        i = 1
        while f"{base}_{i}" in self.ical_urls:
            i += 1
        return f"{base}_{i}"

    def _sync_all_urls(self):
        """Đồng bộ lại tất cả các link iCal đã lưu (chạy trong nền)."""
        for stem, url in list(self.ical_urls.items()):
            self.import_ical_url(url, silent=True, stem=stem)

    def import_ical_url(self, url, silent=False, stem=None):
        """Tải và đồng bộ lịch trực tiếp từ link iCal (Secret address in iCal format).
        
        - url  : địa chỉ iCal (https:// hoặc webcal://)
        - stem : tên file để lưu (tự động tạo nếu không truyền)
        """
        if not url:
            return False
        url = url.strip()

        # Xác định stem (tên file lưu .ics)
        if stem is None:
            stem = self._make_stem(url)

        self.is_connecting = True
        if not silent:
            self.state = "connecting"
            self.message = "Đang tải dữ liệu từ Google Calendar..."

        try:
            # Hỗ trợ cả webcal:// bằng cách đổi thành https://
            fetch_url = url
            if fetch_url.startswith("webcal://"):
                fetch_url = "https://" + fetch_url[9:]

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            r = requests.get(fetch_url, timeout=15, headers=headers)
            if not r.ok or "BEGIN:VCALENDAR" not in r.text:
                if not silent:
                    self.state = "disconnected" if not self.calendars else "connected"
                    self.message = f"Link không hợp lệ hoặc lỗi kết nối (HTTP {r.status_code})."
                self.is_connecting = False
                return False

            dest = CALENDARS_DIR / f"{stem}.ics"
            dest.write_text(r.text, encoding="utf-8", errors="ignore")

            self.ical_urls[stem] = url
            self.saved_ical_url = url   # giữ compat (URL đầu tiên/mới nhất)
            self.last_sync_time = time.monotonic()
            self._save_prefs()
            self._load_local_ics()

            self.state = "connected"
            self.message = ""
            self.is_connecting = False
            return True
        except Exception as ex:
            print("[Dynamic Island] Lỗi tải link iCal:", ex)
            if not silent:
                self.state = "disconnected" if not self.calendars else "connected"
                self.message = f"Lỗi tải iCal: {str(ex)[:60]}"
            self.is_connecting = False
            return False

    # ---------------------------- Đọc Dữ Liệu Lịch Cục Bộ (.ics) ----------------------------
    def _load_local_ics(self):
        """Đọc và phân tích toàn bộ các file .ics có trong thư mục CALENDARS_DIR."""
        if not CALENDARS_DIR.exists():
            return

        cals = []
        all_events = {}
        month_events = {}

        ics_files = list(CALENDARS_DIR.glob("*.ics"))
        if not ics_files:
            return

        for idx, p in enumerate(ics_files):
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                cal_id = p.stem
                color = BADGES[idx % len(BADGES)]
                default_name = "Lịch Google" if p.stem == "google_synced" else p.stem.replace("_", " ").title()
                cal_name, events = parse_ics_content(content, cal_id, default_name, color)

                cals.append({
                    "id": cal_id,
                    "name": cal_name,
                    "color": color,
                    "primary": (idx == 0)
                })

                for d, ev_list in events.items():
                    all_events.setdefault(d, []).extend(ev_list)
                    key_month = (d.year, d.month)
                    month_events.setdefault(key_month, {}).setdefault(d, []).extend(ev_list)
            except Exception as ex:
                print(f"[Dynamic Island] Lỗi đọc file ics {p.name}: {ex}")

        # Sắp xếp các sự kiện trong từng ngày
        for d, lst in all_events.items():
            lst.sort(key=lambda e: (e["key"], e["title"]))
        for (y, m), m_dict in month_events.items():
            for d, lst in m_dict.items():
                lst.sort(key=lambda e: (e["key"], e["title"]))

        self.calendars = cals
        self.all_events_by_date = all_events
        self.month_events = month_events

        # Khởi tạo enabled_cals nếu chưa có
        if self.enabled_cals is None:
            self.enabled_cals = {c["id"] for c in cals}
            self._save_prefs()

        if cals:
            self.state = "connected"
            self.message = ""

    def import_ics_file(self, file_path):
        """Nhập trực tiếp một file .ics được kéo thả hoặc chọn từ máy tính."""
        try:
            p = Path(file_path)
            dest = CALENDARS_DIR / p.name
            shutil.copy2(p, dest)
            self._load_local_ics()
            return True
        except Exception as ex:
            print("[Dynamic Island] Không thể nạp file .ics:", ex)
            return False

    def _unpack_zip(self, zip_path):
        """Giải nén file zip xuất từ Google Calendar và lưu các file .ics vào CALENDARS_DIR."""
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                for name in z.namelist():
                    if name.lower().endswith(".ics"):
                        z.extract(name, CALENDARS_DIR)
            self._load_local_ics()
            return True
        except Exception as ex:
            print("[Dynamic Island] Lỗi giải nén file zip lịch:", ex)
            return False

    # ---------------------------- Danh Sách Lịch & Sự Kiện ----------------------------
    def get_calendars(self):
        """Lấy danh sách các lịch đang có."""
        if not self.calendars:
            self._load_local_ics()

        if not self.calendars:
            return [{"id": "primary", "name": "Lịch Google", "color": ACCENT, "primary": True}]

        if self.enabled_cals is None:
            self.enabled_cals = {c["id"] for c in self.calendars}
            self._save_prefs()

        return self.calendars

    def events_on(self, d, enabled_only=True):
        """Lấy các sự kiện trong ngày d. Nếu enabled_only=True thì lọc theo các lịch đang bật."""
        items = self.all_events_by_date.get(d, [])
        if not enabled_only:
            return items
        enabled = self.get_enabled_calendar_ids()
        return [it for it in items if it["cal_id"] in enabled]

    def get_event_colors_on(self, d):
        """Lấy danh sách màu sắc của các sự kiện trong ngày (tối đa 3 màu) để vẽ chấm trạng thái trên lưới lịch."""
        events = self.events_on(d, enabled_only=True)
        colors = []
        for ev in events:
            c = ev["color"]
            if c not in colors:
                colors.append(c)
            if len(colors) >= 3:
                break
        return colors

    def sync_now(self, force=False):
        """Đồng bộ lại tất cả link iCal ngay lập tức trong luồng nền.
        Nếu force=False, chỉ đồng bộ nếu chưa đang kết nối và cách lần sync trước ít nhất 5s để tránh spam.
        """
        now = time.monotonic()
        if not self.ical_urls or self.is_connecting:
            return
        if not force and (now - self.last_sync_time < 5.0):
            return
        self.last_sync_time = now
        threading.Thread(target=self._sync_all_urls, daemon=True).start()

    def request_month(self, y, m):
        """Tự động đồng bộ lại tất cả link iCal sau mỗi 60 giây khi đang ở tab Lịch."""
        if self.ical_urls and time.monotonic() - self.last_sync_time > 60 and not self.is_connecting:
            self.last_sync_time = time.monotonic()
            threading.Thread(target=self._sync_all_urls, daemon=True).start()

    def is_loading(self, y, m):
        return self.is_connecting

    def remove_calendar(self, cal_id):
        """Xóa một lịch cụ thể: xóa file .ics và URL iCal tương ứng (nếu có)."""
        # Xóa file .ics
        try:
            p = CALENDARS_DIR / f"{cal_id}.ics"
            if p.exists():
                p.unlink()
        except Exception as ex:
            print(f"[Dynamic Island] Lỗi xóa file lịch {cal_id}:", ex)

        # Xóa URL iCal tương ứng khỏi danh sách
        self.ical_urls.pop(cal_id, None)

        # Xóa khỏi tập hợp enabled_cals
        if self.enabled_cals:
            self.enabled_cals.discard(cal_id)

        self._save_prefs()
        self._load_local_ics()

        # Nếu không còn lịch nào thì về trạng thái chưa kết nối
        if not self.calendars:
            self.state = "disconnected"
            self.saved_ical_url = ""

    def disconnect(self):
        """Xóa toàn bộ lịch và đặt lại về trạng thái ban đầu."""
        try:
            if CALENDARS_DIR.exists():
                for f in CALENDARS_DIR.glob("*.*"):
                    try:
                        f.unlink()
                    except Exception:
                        pass
            if GOOGLE_PREFS_FILE.exists():
                GOOGLE_PREFS_FILE.unlink()
        except Exception:
            pass

        self.state = "disconnected"
        self.message = ""
        self.calendars = []
        self.all_events_by_date = {}
        self.month_events = {}
        self.enabled_cals = None
        self.saved_ical_url = ""
        self.ical_urls = {}

    def try_install_client(self, path):
        return False
