"""
Dynamic Island chính: quản lý hình dạng tai thỏ, hoạt ảnh co giãn,
điều hướng các tab, phím tắt và sự kiện chuột/file.
"""
import os
import io
import json
import math
import time
import calendar
import threading
from datetime import datetime, date
from pathlib import Path
import pygame

from config import (
    COMPACT_W, COMPACT_H, EXPAND_W, EXPAND_H, WIN_W, WIN_H, EAR, NAV_H, NAV_EXTRA, CONTENT_DY,
    PAGE_SIZES, MUSIC_COMPACT_W, MUSIC_COMPACT_H, KEY, BLACK, PANEL, PANEL_HOVER, ACCENT, WHITE, GREY, DIM, BADGE_RED, TOP_MARGIN,
    GREEN, ORANGE, CLOSE_RED, CLOSE_RED_HOVER, GEAR_DOT, GEAR_BG, GEAR_BG_HOVER,
    SETTINGS_FILE, DEFAULT_SETTINGS, SHELF_FILE
)
from utils.win32 import (
    cursor_pos, mouse_down, key_down, icon_cache_key, get_system_icon, start_file_drag, battery_status, LayeredPresenter
)
from utils.drawing import (
    draw_text, make_bell, make_ring, make_nav_icon, intro_geometry, outro_geometry, lerp,
    draw_aa_circle, draw_aa_round_rect, draw_capsule, draw_fluid_pill
)
from bridges import MediaBridge, NotifBridge, GoogleCalendar, fetch_synced_lyrics
from bridges.updater import UpdaterBridge
from tabs import MusicTab, CalendarTab, ShelfTab


class Island:
    """Lớp điều khiển chính của Dynamic Island."""

    def __init__(self, win_x, win_y, intro=False, hwnd=None):
        """intro=True: island bắt đầu ở trạng thái ẩn (toàn bộ trong suốt) và chờ begin_intro() để chạy hiệu ứng giọt nước."""
        self.win_x, self.win_y = win_x, win_y                # vị trí cửa sổ trên màn hình (để đổi toạ độ chuột)
        self.hwnd = hwnd
        self.presenter = LayeredPresenter(hwnd, WIN_W, WIN_H) if hwnd else None
        self._render_surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        self._ear_cache = {}
        self._corner_cache = {}
        # Segoe UI hỗ trợ tiếng Việt đầy đủ; thêm Segoe UI Emoji & Segoe UI Symbol để hiển thị trọn vẹn icon/symbol
        font_family = "segoeui,segoeuiemoji,segoeuisymbol"
        self.f_time = pygame.font.SysFont(font_family, 19, bold=True)
        self.f_title = pygame.font.SysFont(font_family, 20, bold=True)
        self.f_text = pygame.font.SysFont(font_family, 15, bold=True)
        self.f_small = pygame.font.SysFont(font_family, 14, bold=True)
        self.f_tiny = pygame.font.SysFont(font_family, 12, bold=True)
        self.f_lyric = pygame.font.SysFont(font_family, 23, bold=True)

        self.cur_w, self.cur_h = float(COMPACT_W), float(COMPACT_H)   # kích thước đang hiển thị (số thực để animate)
        self.animating = False
        self.page = 0                                        # 0: nhạc, 1: lịch, 2: ngăn xếp
        self._prev_page = 0                                  # theo dõi khi đổi tab
        self.nav_cur_x = None                                # toạ độ x của indicator giọt nước đang trôi
        self.nav_tail_x = None                               # toạ độ x của đuôi giọt nước
        self.open_until = 0.0                                # island giữ mở tới thời điểm này
        self.hover = False
        self.mouse_local = (-999, -999)                      # chuột trong toạ độ vùng nội dung (đã trừ EAR)
        self.quit = False
        self.closing = False                                 # True khi đang chạy animation đóng ứng dụng
        self.outro_t0 = 0.0                                  # mốc thời gian bắt đầu outro
        self.outro_start_w = 0.0
        self.outro_start_h = 0.0
        # Hiệu ứng mở đầu: "pending" (chưa hiện, toàn trong suốt) -> "running" (giọt nước lan ra) -> "done"
        self.intro_state = "pending" if intro else "done"
        self.intro_t0 = 0.0                                  # thời điểm bắt đầu hiệu ứng mở đầu
        self.ear_scale = 1.0                                 # tỉ lệ bán kính 2 tai (nhỏ lúc đầu hiệu ứng, 1.0 là đầy đủ)
        self.content_alpha = 1.0                             # độ hiện của nội dung (giờ, chuông...) từ 0 tới 1
        self._layer = None                                   # bề mặt tạm để làm nội dung hiện dần
        self.hits = []                                       # danh sách vùng bấm, dựng lại mỗi khung hình
        self._hit_ox = 0                                     # độ dời ngang vùng bấm (tab hẹp hơn vùng cửa sổ thì căn giữa)
        self._hit_dy = 0                                     # độ dời toạ độ vùng bấm (khi vẽ tab lên lớp nội dung đã dịch lên)
        self.nav_t = 0.0                                     # 0: thanh điều hướng chỉ là các chấm; 1: đã thành icon (island kéo dài)
        self._content = None                                 # lớp nội dung của tab (nền BLACK làm màu trong suốt)
        self.nav_icons = {}                                  # cache icon điều hướng theo (loại, màu)
        self.settings = dict(DEFAULT_SETTINGS)               # cài đặt người dùng (lưu ở SETTINGS_FILE)
        self.settings_win = None                             # cửa sổ Cài đặt (main.py gắn vào)
        self._load_settings()
        self.apply_window_opacity()
        self.battery = None                                  # (% pin, đang sạc) hoặc None
        self._battery_t = 0.0                                # lần cuối đọc pin

        # Cầu nối (Bridges)
        self.media = MediaBridge()
        self.media.start()
        self.notif = NotifBridge()                           # đọc thông báo hệ thống ở luồng nền
        self.notif.start()
        self.updater = UpdaterBridge(self)                   # tự động cập nhật từ GitHub Releases
        if self.settings.get("auto_update", True):
            self.updater.check_for_updates(auto_download=False)
        self.notif_count = 0                                 # số thông báo đang chờ trong Action Center
        self.shake_until = 0.0                               # chuông lắc tới thời điểm này (khi có thông báo mới)
        self.track_key = None                                # (tên bài, nghệ sĩ) hiện tại
        self.title = self.artist = ""
        self.art = None                                      # ảnh bìa bài hát (Surface) hoặc None
        self._art_token = None                               # bytes ảnh đang giữ, để khỏi giải mã lại mỗi khung
        self.playing, self.duration = False, 0.0
        self.play_t = 0.0                                    # tiến trình chuyển động sóng âm (0.0: dừng, 1.0: đang phát)
        self.wave_heights = [5.0] * 5                        # mảng chiều cao 5 thanh sóng để nội suy mượt mà
        self.base_pos, self.base_t = 0.0, time.monotonic()   # mốc nội suy vị trí
        self.lyrics = ([], [])                               # (mốc thời gian, lời)
        self.lyr_state = ""                                  # "loading" | "ok" | "none"

        # Lịch
        today = datetime.now()
        self.today = (today.year, today.month, today.day)
        self.cal_year, self.cal_month = today.year, today.month
        self.sel = self.today                                # ngày đang chọn trên lịch (năm, tháng, ngày)
        self.ev_scroll = 0                                   # số sự kiện đã cuộn trong danh sách bên phải
        self.gcal = GoogleCalendar()                         # kết nối Google Calendar
        calendar.setfirstweekday(self.settings["week_start"])   # tuần bắt đầu từ thứ Hai hoặc Chủ Nhật (theo cài đặt)

        # Ngăn xếp file
        self.files = []                                      # danh sách file
        self.scroll = 0                                      # số hàng đã cuộn
        self.last_click = (-1, 0.0)                          # (chỉ số ô, thời điểm) để nhận diện nhấp đôi
        self.icons = {}                                      # cache icon hệ thống theo icon_cache_key
        self.drag = None                                     # (chỉ số ô, vị trí chuột lúc nhấn) khi có thể bắt đầu kéo ra
        self.prev_l = self.prev_r = False                    # trạng thái chuột ở khung trước (để bắt cạnh nhấn xuống)
        self.prev_k_left = self.prev_k_right = False          # trạng thái phím mũi tên Trái/Phải khung trước
        self.bell_img = make_bell(22)                        # ảnh cái chuông (vẽ một lần, dùng lại)
        self._load_shelf()

        # Khởi tạo các tab
        self.tabs = [MusicTab(self), CalendarTab(self), ShelfTab(self)]

    # ----------------------------- Cập nhật trạng thái -----------------------------
    def island_rect(self):
        """Thân island trong toạ độ vùng nội dung (rộng EXPAND_W, chưa tính 2 tai)."""
        r = pygame.Rect(0, 0, round(self.cur_w), round(self.cur_h))
        r.midtop = (EXPAND_W // 2, 0)                        # căn giữa, sát đỉnh
        return r

    def handle_click_event(self, button, pos=None):
        """Xử lý sự kiện click chuột trực tiếp từ event queue."""
        cx, cy = cursor_pos()
        over_settings = bool(self.settings_win and self.settings_win.covers(cx, cy))
        if over_settings:
            return
        local_pos = (cx - self.win_x - EAR, cy - self.win_y)
        self.prev_l = True
        self.click(local_pos, button)

    def nav_extra(self):
        """Chiều cao kéo dài thêm khi mở rộng thanh điều hướng (đồng bộ cho tất cả các tab)."""
        return NAV_EXTRA

    def update(self):
        now = time.monotonic()

        # --- nhạc ---
        info = self.media.snapshot()
        if info:
            key = (info["title"], info["artist"])
            if key != self.track_key:                        # đổi bài -> tải lyrics mới
                self.track_key = key
                self.lyrics, self.lyr_state = ([], []), "loading"
                self._last_seek_time = 0.0
                threading.Thread(target=self._fetch_lyrics, args=(key,), daemon=True).start()
            self.title, self.artist = info["title"], info["artist"]
            if now - getattr(self, "_last_seek_time", 0.0) > 1.2:
                # Chỉ cập nhật pos từ Windows khi đã qua 1.2s kể từ lần tua gần nhất (tránh Windows gửi vị trí cũ làm giật lùi thanh trượt)
                self.base_pos, self.base_t = info["pos"], info["t"]
            self.playing, self.duration = info["playing"], info["dur"]
            self._apply_art(info.get("thumb"))
        else:
            self.track_key, self.title, self.artist = None, "", ""
            self.playing, self.duration, self.lyr_state = False, 0.0, ""
            self._apply_art(None)

        # --- Google Calendar: khi vừa chuyển sang tab Lịch hoặc đang mở rộng ở tab Lịch ---
        is_expanded = self.cur_h > COMPACT_H + 60
        if self.page == 1 and is_expanded:
            if self._prev_page != 1:
                # Vừa chuyển qua tab Lịch: đồng bộ lại lịch mới ngay lập tức
                self.gcal.sync_now()
            else:
                # Đang ở trong tab Lịch: tự động cập nhật sau mỗi 1 phút (60s)
                self.gcal.request_month(self.cal_year, self.cal_month)
        self._prev_page = self.page

        # --- thông báo: tăng lên thì cho chuông lắc 1.5 giây ---
        n_notif = self.notif.count()
        if n_notif > self.notif_count:
            self.shake_until = now + 1.5
        self.notif_count = n_notif

        # --- pin (đọc mỗi 20 giây là đủ) ---
        if now - self._battery_t > 20:
            self._battery_t = now
            self.battery = battery_status()

        # --- hover: dùng toạ độ chuột toàn màn hình nên không cần cửa sổ có focus ---
        cx, cy = cursor_pos()
        self.mouse_local = (cx - self.win_x - EAR, cy - self.win_y)    # trừ EAR vì vùng nội dung nằm lệch 1 tai
        over_settings = bool(self.settings_win and self.settings_win.covers(cx, cy))   # chuột đang ở trên cửa sổ Cài đặt
        hover = self.island_rect().collidepoint(self.mouse_local) and not over_settings
        left_now, right_now = mouse_down(1), mouse_down(3)   # đọc trạng thái nút chuột trực tiếp từ Windows
        if over_settings:
            left_now = right_now = False                     # cửa sổ Cài đặt tự xử lý chuột của nó
        if hover and not self.hover and left_now and not (self.page == 1 and self.gcal.state == "no_client"):  # chuột vào island khi đang giữ nút = có thể đang kéo file
            self.page = 2                                    # nhảy sang tab Ngăn xếp
        self.hover = hover
        if hover:
            self.open_until = max(self.open_until, now + 0.3)    # rời chuột 0.3s mới thu gọn

        # --- bấm chuột: tự đọc nút chuột từ Windows để bắt cạnh nhấn xuống ---
        if left_now and not self.prev_l:
            self.click(self.mouse_local, 1)                  # nhấn trái: tab, nút nhạc, nhấn ô file (chuẩn bị kéo)...
        if right_now and not self.prev_r:
            self.click(self.mouse_local, 3)                  # nhấn phải: gỡ file khỏi ngăn xếp
        self.prev_l, self.prev_r = left_now, right_now

        # --- phím mũi tên Trái / Phải để chuyển tab khi mở rộng ---
        is_expanded = self.cur_h > COMPACT_H + 60
        input_active = bool(self.settings_win and self.settings_win.input_active)
        if is_expanded and not input_active:
            # VK_LEFT = 0x25, VK_RIGHT = 0x27
            k_left = key_down(0x25)
            k_right = key_down(0x27)
            if k_left and not self.prev_k_left:
                self.prev_tab()
                self.open_until = max(self.open_until, now + 2.0)   # giữ đảo mở khi dùng phím điều hướng
            elif k_right and not self.prev_k_right:
                self.next_tab()
                self.open_until = max(self.open_until, now + 2.0)
            self.prev_k_left, self.prev_k_right = k_left, k_right
        else:
            self.prev_k_left = self.prev_k_right = False

        # --- kéo file từ ngăn xếp ra ngoài: nhấn giữ trên ô rồi di chuyển quá 6px ---
        if self.drag:
            idx, (sx, sy) = self.drag
            if not left_now:
                self.drag = None                             # đã thả chuột, không còn là kéo
            elif math.hypot(cx - sx, cy - sy) > 6 and 0 <= idx < len(self.files):
                path = self.files[idx]
                self.drag = None
                self.open_until = now + 1.0                  # giữ island mở trong lúc kéo
                blob_color = self.get_blob_color()
                start_file_drag(path, (sx, sy), blob_color=blob_color)  # chặn tới khi thả chuột (vòng lặp kéo-thả của Windows)
                self.prev_l, self.prev_r = mouse_down(1), mouse_down(3)   # bỏ qua cạnh nhấn "ảo" sau vòng kéo-thả
                self.open_until = time.monotonic() + 0.3

        # --- animation kích thước ---
        if self.closing:
            self._step_outro(time.monotonic())
            return
        if self.intro_state == "running":
            self._step_intro(time.monotonic())               # hiệu ứng mở đầu thay cho animation co giãn thông thường
            return
        if self.intro_state == "pending":
            return                                           # chưa bắt đầu hiệu ứng: island còn ẩn
        want_open = time.monotonic() < self.open_until
        mx, my = self.mouse_local                            # rê vào dải điều hướng (đáy island) -> chấm thành icon, island kéo dài
        rect = self.island_rect()
        extra_h = self.nav_extra()
        rest = self.cur_h - extra_h * self.nav_t             # chiều cao thân, chưa cộng phần thanh điều hướng kéo dài
        in_nav = (want_open and self.cur_h > COMPACT_H + 60 and rect.left <= mx <= rect.right
                  and rest - NAV_H <= my <= self.cur_h)
        nav_target = 1.0 if in_nav else 0.0
        self.nav_t += (nav_target - self.nav_t) * 0.28
        if abs(nav_target - self.nav_t) < 0.01:
            self.nav_t = nav_target
        bw, bh = self.page_size(self.page) if want_open else (COMPACT_W, COMPACT_H)
        tw, th = bw, bh + extra_h * self.nav_t
        self.cur_w += (tw - self.cur_w) * 0.22               # mỗi khung tiến 22% tới đích (ease-out)
        self.cur_h += (th - self.cur_h) * 0.22
        self.animating = abs(tw - self.cur_w) > 0.5 or abs(th - self.cur_h) > 0.5 or self.nav_t != nav_target
        if not self.animating:
            self.cur_w, self.cur_h = float(tw), float(th)    # chốt đúng kích thước đích
        if not want_open:
            self.nav_t = 0.0

    def begin_intro(self):
        """Bắt đầu hiệu ứng mở đầu: giọt nước từ mép trên màn hình lan ra thành tai thỏ, rồi nội dung hiện dần (0.2s)."""
        self.intro_state, self.intro_t0 = "running", time.monotonic()
        self._step_intro(self.intro_t0)

    def _step_intro(self, now):
        """Một bước của hiệu ứng mở đầu: đặt kích thước, bán kính tai và độ hiện nội dung theo thời gian đã trôi qua."""
        g = intro_geometry(now - self.intro_t0)
        if g is None:                                        # hiệu ứng đã xong -> về trạng thái thu gọn bình thường
            self.intro_state, self.ear_scale, self.content_alpha = "done", 1.0, 1.0
            self.cur_w, self.cur_h = float(COMPACT_W), float(COMPACT_H)
            self.animating, self._layer = False, None        # giải phóng bề mặt tạm
            return
        self.cur_w, self.cur_h, self.ear_scale, self.content_alpha = g
        self.animating = True                                # giữ 60 FPS trong lúc chạy hiệu ứng

    def trigger_quit(self):
        """Bắt đầu hiệu ứng thu nhỏ giọt nước ngược về mép trên trước khi tắt app."""
        if self.closing:
            return
        # Đóng cửa sổ cài đặt ngay lập tức trước khi chạy animation của Dynamic Notch
        if self.settings_win:
            self.settings_win.close_immediate()
        self.closing = True
        self.outro_t0 = time.monotonic()
        self.outro_start_w = float(self.cur_w)
        self.outro_start_h = float(self.cur_h)
        self.animating = True

    def _step_outro(self, now):
        """Một bước của hiệu ứng đóng: co thân thành giọt nước rồi rút vào mép trên màn hình."""
        g = outro_geometry(now - self.outro_t0, self.outro_start_w, self.outro_start_h)
        if g is None:
            self.cur_w, self.cur_h, self.ear_scale, self.content_alpha = 0.0, 0.0, 0.0, 0.0
            self.quit = True
            return
        self.cur_w, self.cur_h, self.ear_scale, self.content_alpha = g
        self.animating = True

    def _apply_art(self, data):
        """Giải mã ảnh bìa trên luồng chính. data là bytes (cùng object cho tới khi đổi bài) hoặc None."""
        if data is self._art_token:
            return
        self._art_token = data
        self.art = None
        if not data:
            return
        hint = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
        try:
            self.art = pygame.image.load(io.BytesIO(data), hint).convert_alpha()
        except Exception:
            self.art = None

    def position(self):
        """Vị trí bài hát hiện tại (giây), nội suy giữa 2 lần hỏi Windows."""
        if not self.title:
            return 0.0
        pos = self.base_pos + ((time.monotonic() - self.base_t) if self.playing else 0.0)
        return min(pos, self.duration) if self.duration > 0 else pos

    def _fetch_lyrics(self, key):
        times, lines = fetch_synced_lyrics(*key)             # chạy ở luồng nền vì có gọi mạng
        if key == self.track_key:                            # bỏ kết quả cũ nếu đã đổi bài
            self.lyrics = (times, lines)
            self.lyr_state = "ok" if lines else "none"

    # --------------------------------- Cài đặt ---------------------------------
    def _load_settings(self):
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            self.settings.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
        except Exception:
            pass
        # Đồng bộ trạng thái thực tế từ Windows Registry
        try:
            from utils.win32 import is_startup_enabled
            self.settings["auto_startup"] = is_startup_enabled()
        except Exception:
            pass

    def set_setting(self, key, value):
        self.settings[key] = value
        if key == "week_start":
            calendar.setfirstweekday(value)
        elif key == "bg_opacity":
            self.apply_window_opacity()
        elif key == "auto_startup":
            try:
                from utils.win32 import set_startup_enabled
                set_startup_enabled(bool(value))
            except Exception:
                pass
        try:
            SETTINGS_FILE.write_text(json.dumps(self.settings), encoding="utf-8")
        except Exception:
            pass

    def apply_window_opacity(self):
        """Áp dụng độ trong suốt: khi dùng LayeredPresenter, độ trong suốt áp dụng riêng cho hình nền."""
        if not self.presenter:
            try:
                import ctypes
                from config import TITLE
                hwnd = ctypes.windll.user32.FindWindowW(None, TITLE)
                if hwnd:
                    opacity = int(self.settings.get("bg_opacity", 100))
                    alpha = max(30, min(255, int(255 * opacity / 100)))
                    ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0x00FF00FF, alpha, 0x3)
            except Exception:
                pass

    def theme(self):
        """Bảng màu tương phản thích ứng tự động theo màu nền hiện tại của Dynamic Island."""
        bg = tuple(self.settings.get("bg_color", [4, 6, 10]))
        lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
        is_black = (bg[0] < 25 and bg[1] < 25 and bg[2] < 25)

        def blend(c1, c2, f):
            return tuple(round(c1[i] * (1 - f) + c2[i] * f) for i in range(3))

        # Phân loại độ sáng:
        # lum >= 135 được coi là nền sáng (Light Theme) để chữ và nút tự động tối đi, tương phản rõ rệt
        is_light = lum >= 135

        if is_light:
            c_main = (18, 18, 22)                         # Chữ chính & icon chính đen đậm rõ nét
            c_sub = blend(bg, (0, 0, 0), 0.72)            # Chữ phụ tối vừa phải, dễ đọc
            c_dim = blend(bg, (0, 0, 0), 0.50)            # Chữ mờ / divider
            c_panel = blend(bg, (0, 0, 0), 0.12)          # Nền nút / panel
            c_panel_hover = blend(bg, (0, 0, 0), 0.22)    # Hover nút
            c_div = blend(bg, (0, 0, 0), 0.16)
            c_bar = blend(bg, (0, 0, 0), 0.20)
            c_lyric_active = (10, 10, 15)
            c_accent = (0, 102, 204)
        elif is_black:
            c_main = (255, 255, 255)
            c_sub = (185, 185, 192)
            c_dim = (115, 115, 120)
            c_panel = (28, 28, 30)
            c_panel_hover = (50, 50, 54)
            c_div = (42, 42, 46)
            c_bar = (60, 60, 64)
            c_lyric_active = (10, 132, 255)
            c_accent = (10, 132, 255)
        else:
            c_main = (255, 255, 255)
            c_sub = blend(bg, (255, 255, 255), 0.90)
            c_dim = blend(bg, (255, 255, 255), 0.72)
            c_panel = blend(bg, (255, 255, 255), 0.18)
            c_panel_hover = blend(bg, (255, 255, 255), 0.32)
            c_div = blend(bg, (255, 255, 255), 0.25)
            c_bar = blend(bg, (255, 255, 255), 0.30)
            c_lyric_active = (255, 255, 255)
            c_accent = (255, 220, 50) if (bg[2] > 130 and bg[0] < 80) else (100, 215, 255)

        return {
            "main": c_main,
            "sub": c_sub,
            "dim": c_dim,
            "panel": c_panel,
            "panel_hover": c_panel_hover,
            "div": c_div,
            "bar": c_bar,
            "lyric_active": c_lyric_active,
            "accent": c_accent,
            "bg": bg,
            "is_light": is_light
        }

    def open_settings(self, tab=None):
        """Giọt nước tách ra từ đáy island, rơi xuống giữa màn hình rồi phóng to thành cửa sổ Cài đặt."""
        if self.settings_win:
            self.settings_win.open(round(self.cur_h) + TOP_MARGIN, tab=tab)

    # ------------------------------- Ngăn xếp file -------------------------------
    def add_file(self, path):
        # Nếu thả file lịch .ics hoặc zip xuất từ Google Calendar -> tự động nạp lịch
        p_lower = str(path).lower()
        if p_lower.endswith(".ics"):
            if self.gcal.import_ics_file(path):
                self.page = 1                                # Chuyển sang tab Lịch
                self.open_until = time.monotonic() + 5.0
                return
        if p_lower.endswith(".zip") and ("calendar" in p_lower or "export" in p_lower):
            if self.gcal._unpack_zip(path):
                self.page = 1
                self.open_until = time.monotonic() + 5.0
                return

        # Nếu thả file JSON OAuth Client của Google -> tự động cài đặt và kết nối đăng nhập
        if self.gcal.try_install_client(path):
            self.page = 1                                    # Chuyển sang tab Lịch
            self.open_until = time.monotonic() + 5.0
            return

        if path not in self.files:                           # tránh trùng
            self.files.append(path)
            self._save_shelf()
        self.page = 2                                        # chuyển sang tab ngăn xếp
        self.open_until = time.monotonic() + 3.0             # giữ mở 3 giây sau khi thả

    def remove_file(self, idx):
        if 0 <= idx < len(self.files):
            self.files.pop(idx)
            self._save_shelf()

    def tile_press(self, idx):
        """Nhấn chuột trái lên ô file: nhận diện nhấp đôi (mở file) và đánh dấu có thể bắt đầu kéo ra."""
        now = time.monotonic()
        last_idx, last_t = self.last_click
        if idx == last_idx and now - last_t < 0.4:           # nhấp đôi trong 0.4s -> mở file
            try:
                os.startfile(self.files[idx])
            except Exception:
                pass
        self.last_click = (idx, now)
        self.drag = (idx, cursor_pos())                      # nhớ ô và vị trí nhấn để biết khi nào chuột đã kéo đủ xa

    def icon_for(self, path):
        key = icon_cache_key(path)
        if key not in self.icons:
            try:
                self.icons[key] = get_system_icon(path)      # lần đầu mới hỏi Windows, sau đó dùng cache
            except Exception:
                self.icons[key] = None                       # lỗi thì dùng nhãn đuôi file thay thế
        return self.icons[key]

    def wheel(self, dy):
        """Xử lý sự kiện lăn chuột chuyển tiếp cho tab tương ứng."""
        if self.cur_h <= COMPACT_H + 60:
            return
        if 0 <= self.page < len(self.tabs):
            self.tabs[self.page].on_wheel(dy)

    def get_blob_color(self):
        """Tính màu giọt nước tương phản hài hòa theo màu nền với độ chênh lệch vừa phải nhẹ nhàng."""
        bg = tuple(self.settings.get("bg_color", [4, 6, 10]))
        lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
        if lum >= 128:
            # Nền sáng -> giọt nước hơi đậm nhẹ (giảm ~15% độ sáng)
            r = max(0, min(255, round(bg[0] * 0.85)))
            g = max(0, min(255, round(bg[1] * 0.85)))
            b = max(0, min(255, round(bg[2] * 0.85)))
        else:
            # Nền tối -> giọt nước hơi sáng nhẹ (blend ~14% về trắng, nhạt hơn và tự nhiên)
            r = max(0, min(255, round(bg[0] * 0.86 + 255 * 0.14)))
            g = max(0, min(255, round(bg[1] * 0.86 + 255 * 0.14)))
            b = max(0, min(255, round(bg[2] * 0.86 + 255 * 0.14)))
        return (r, g, b, 255)

    def _save_shelf(self):
        try:
            SHELF_FILE.write_text(json.dumps(self.files), encoding="utf-8")
        except Exception:
            pass

    def _load_shelf(self):
        try:
            self.files = [p for p in json.loads(SHELF_FILE.read_text(encoding="utf-8")) if Path(p).exists()]
        except Exception:
            self.files = []

    # --------------------------------- Lịch ---------------------------------
    def _pick_default_day(self):
        """Đổi tháng xong thì chọn hôm nay (nếu nằm trong tháng đó) hoặc ngày 1."""
        self.ev_scroll = 0
        y, m = self.cal_year, self.cal_month
        self.sel = self.today if (self.today[0], self.today[1]) == (y, m) else (y, m, 1)

    def shift_month(self, delta):
        m = self.cal_month + delta
        self.cal_year += (m - 1) // 12                       # sang năm khác nếu vượt 12 hoặc dưới 1
        self.cal_month = (m - 1) % 12 + 1
        self._pick_default_day()

    def go_today(self):
        self.cal_year, self.cal_month = self.today[0], self.today[1]
        self.sel, self.ev_scroll = self.today, 0

    def prev_tab(self):
        """Chuyển sang tab trước đó (quay vòng tròn)."""
        self.page = (self.page - 1) % len(self.tabs)

    def next_tab(self):
        """Chuyển sang tab kế tiếp (quay vòng tròn)."""
        self.page = (self.page + 1) % len(self.tabs)

    # --------------------------------- Chuột & Hits --------------------------
    def click(self, pos, button):
        if self.cur_h < COMPACT_H + 60:
            return                                           # đang thu gọn thì bỏ qua click
        for rect, left_fn, right_fn in reversed(self.hits):  # vùng vẽ sau nằm trên nên xét trước
            if rect.collidepoint(pos):
                fn = left_fn if button == 1 else right_fn if button == 3 else None
                if fn:
                    fn()
                return

    def add_hit(self, rect, left_fn=None, right_fn=None):
        self.hits.append((rect.move(self._hit_ox, self._hit_dy), left_fn, right_fn))

    # --------------------------------- Vẽ giao diện --------------------------
    def draw(self, surf):
        self.hits = []
        target = self._render_surf if self.presenter else surf
        target.fill((0, 0, 0, 0) if self.presenter else KEY)
        if self.intro_state == "pending":
            if self.presenter:
                self.presenter.present(self._render_surf)
            return                                           # chưa tới lúc hiện: giữ toàn bộ cửa sổ trong suốt

        rect = self.island_rect()
        shape = rect.move(EAR, 0)                            # dời sang toạ độ cửa sổ (chừa chỗ cho tai trái)
        r = int(min(shape.height / 2, shape.width / 2, 28))  # bán kính bo 2 góc DƯỚI không vượt quá nửa bề rộng thân
        er = max(0, round(EAR * self.ear_scale))             # bán kính tai hiện tại (lớn dần trong hiệu ứng mở đầu)

        bg_c = tuple(self.settings.get("bg_color", [4, 6, 10]))
        bg_op = int(self.settings.get("bg_opacity", 100))
        bg_alpha = max(20, min(255, int(255 * bg_op / 100)))

        if self.presenter:
            bg_rgba = (*bg_c, bg_alpha)
            # Hai "tai" cong ở góc trên với độ khử răng cưa mượt mà (chỉ vẽ khi er > 0)
            if er > 0:
                ear_key = (er, bg_rgba)
                ear = self._ear_cache.get(ear_key)
                if ear is None:
                    k = 3
                    big_ear = pygame.Surface((er * k, er * k), pygame.SRCALPHA)
                    big_ear.fill(bg_rgba)
                    mask = pygame.Surface((er * k, er * k), pygame.SRCALPHA)
                    mask.fill((255, 255, 255, 255))
                    pygame.draw.circle(mask, (0, 0, 0, 0), (0, er * k), er * k)
                    big_ear.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                    ear = pygame.transform.smoothscale(big_ear, (er, er))
                    self._ear_cache[ear_key] = ear
                target.blit(ear, (shape.left - er, 0))

                ear_r = pygame.transform.flip(ear, True, False)
                target.blit(ear_r, (shape.right, 0))

            # Thân island: phần thẳng vẽ trước, 2 góc dưới bo tròn khử răng cưa siêu mượt
            if r > 0 and shape.height > r and shape.width >= 2 * r:
                pygame.draw.rect(target, bg_rgba, (shape.left, 0, shape.width, shape.height - r))
                pygame.draw.rect(target, bg_rgba, (shape.left + r, shape.height - r, shape.width - 2 * r, r))
                corner_key = (r, bg_rgba)
                corner_bl = self._corner_cache.get(corner_key)
                if corner_bl is None:
                    k = 3
                    big_c = pygame.Surface((r * k, r * k), pygame.SRCALPHA)
                    big_c.fill((0, 0, 0, 0))
                    pygame.draw.circle(big_c, bg_rgba, (r * k, 0), r * k)
                    corner_bl = pygame.transform.smoothscale(big_c, (r, r))
                    self._corner_cache[corner_key] = corner_bl
                target.blit(corner_bl, (shape.left, shape.height - r))
                corner_br = pygame.transform.flip(corner_bl, True, False)
                target.blit(corner_br, (shape.right - r, shape.height - r))
            else:
                pygame.draw.rect(target, bg_rgba, shape)
        else:
            # Hai "tai" cong ở góc trên: hình vuông er x er màu nền, rồi khoét bằng hình tròn trong suốt
            pygame.draw.rect(target, bg_c, (shape.left - er, 0, er, er))
            pygame.draw.circle(target, KEY, (shape.left - er, er), er)
            pygame.draw.rect(target, bg_c, (shape.right, 0, er, er))
            pygame.draw.circle(target, KEY, (shape.right + er, er), er)
            pygame.draw.rect(target, bg_c, shape, border_radius=0,
                             border_bottom_left_radius=r, border_bottom_right_radius=r)

        if self.content_alpha <= 0.0:
            if self.presenter:
                self.presenter.present(self._render_surf)
            return                                           # hiệu ứng mở đầu: hình đang thành hình, chưa hiện nội dung

        body = target.subsurface((EAR, 0, EXPAND_W, EXPAND_H + NAV_EXTRA))  # vùng nội dung
        if self.content_alpha < 1.0:
            if self._layer is None:
                self._layer = pygame.Surface((EXPAND_W, EXPAND_H + NAV_EXTRA), pygame.SRCALPHA)
            layer = self._layer
            layer.fill((0, 0, 0, 0))
            layer.set_clip(rect)
            self.draw_top(layer, rect, False)
            layer.set_clip(None)
            layer.set_alpha(int(255 * self.content_alpha))
            body.blit(layer, (0, 0))
            if self.presenter:
                self.presenter.present(self._render_surf)
            return

        expanded = self.cur_h > COMPACT_H + 60
        body.set_clip(rect)                                  # nội dung không tràn ra ngoài island khi đang animate
        self.draw_top(body, rect, expanded)
        if expanded:
            self.draw_content(body)
            self.draw_nav(body, rect)
        body.set_clip(None)

        # Xoá góc bo nhọn ngoài viền bo tròn r ở đáy để nội dung/gradient không bao giờ bị lem ra ngoài góc
        if r > 0 and shape.height > r and shape.width >= 2 * r:
            k = 3
            corner_clear_key = (r,)
            corner_mask = self._corner_cache.get(corner_clear_key)
            if corner_mask is None:
                big_m = pygame.Surface((r * k, r * k), pygame.SRCALPHA)
                big_m.fill((255, 255, 255, 255))
                pygame.draw.circle(big_m, (0, 0, 0, 0), (r * k, 0), r * k)
                corner_mask = pygame.transform.smoothscale(big_m, (r, r))
                self._corner_cache[corner_clear_key] = corner_mask
            if self.presenter:
                # Trừ alpha của phần ngoài vòng tròn ở 2 góc dưới
                target.blit(corner_mask, (shape.left, shape.height - r), special_flags=pygame.BLEND_RGBA_SUB)
                corner_mask_r = pygame.transform.flip(corner_mask, True, False)
                target.blit(corner_mask_r, (shape.right - r, shape.height - r), special_flags=pygame.BLEND_RGBA_SUB)
            else:
                target.blit(corner_mask, (shape.left, shape.height - r))
                corner_mask_r = pygame.transform.flip(corner_mask, True, False)
                target.blit(corner_mask_r, (shape.right - r, shape.height - r))

        if self.presenter:
            self.presenter.present(self._render_surf)

    def ring_info(self):
        """(tỉ lệ 0..1, màu) cho vòng tròn bên trái: % pin hoặc tiến độ bài nhạc theo ring_source."""
        src = self.settings.get("ring_source", "battery")
        if src == "battery" and self.battery:
            pct, charging = self.battery
            color = GREEN if (charging or pct > 40) else (ORANGE if pct > 20 else CLOSE_RED)
            return pct / 100, color
        if src == "music" and self.duration > 0:
            return min(self.position() / self.duration, 1.0), GREEN
        return 0.0, GREEN

    def draw_top(self, surf, rect, expanded):
        th = self.theme()
        cy = COMPACT_H // 2
        sec_mode = self.settings.get("seconds_mode")
        if sec_mode is None:
            sec_mode = "expand" if self.settings.get("show_seconds", True) else "none"

        show_sec = (sec_mode == "both") or (expanded and sec_mode == "expand") or (not expanded and sec_mode == "compact")
        fmt = "%H:%M:%S" if show_sec else "%H:%M"
        txt = self.f_time.render(datetime.now().strftime(fmt), True, th["main"])     # ảnh chữ giờ
        trect = txt.get_rect(center=(EXPAND_W // 2, cy))                        # căn giữa island
        surf.blit(txt, trect)
        # Bên trái: vòng tròn xanh (pin / tiến độ nhạc)
        frac, color = self.ring_info()
        ring = make_ring(24, frac, color)
        surf.blit(ring, ring.get_rect(center=(rect.left + 28, cy)))
        # --- Bên phải: 5 thanh sóng nhạc với animation chuyển tiếp mượt mà ---
        target_play_t = 1.0 if self.playing else 0.0
        self.play_t += (target_play_t - self.play_t) * 0.18
        if abs(target_play_t - self.play_t) < 0.01:
            self.play_t = target_play_t

        t = time.monotonic()
        for i in range(5):
            target_h = 5.0 + 13.0 * abs(math.sin(t * 5 + i * 1.3)) * self.play_t
            self.wave_heights[i] += (target_h - self.wave_heights[i]) * 0.35
            bar = pygame.Rect(0, 0, 3, round(self.wave_heights[i]))
            bar.center = (rect.right - 42 + i * 6, cy)
            draw_aa_round_rect(surf, th["main"], bar, 1.5)
        if self.notif_count > 0 and self.settings["show_bell"]:   # có thông báo -> hiện cái chuông ngay bên phải giờ
            self.draw_bell(surf, (trect.right + 18, cy))

    def draw_bell(self, surf, center):
        """Vẽ cái chuông (lắc nhẹ khi vừa có thông báo mới) và huy hiệu đỏ báo số lượng."""
        img = self.bell_img
        now = time.monotonic()
        if now < self.shake_until:                           # đang trong thời gian lắc
            left = self.shake_until - now                    # thời gian lắc còn lại (giây)
            angle = 22 * math.sin(now * 28) * min(1.0, left / 0.6)    # góc lắc, nhỏ dần ở 0.6 giây cuối
            img = pygame.transform.rotozoom(img, angle, 1.0)
        surf.blit(img, img.get_rect(center=center))
        bx, by = center[0] + 8, center[1] - 8                # tâm huy hiệu: góc trên bên phải chuông
        n = self.notif_count
        if n <= 1:
            draw_aa_circle(surf, BADGE_RED, (bx, by), 4)     # 1 thông báo -> chấm đỏ nhỏ
        else:
            label = self.f_tiny.render(str(n) if n < 10 else "9+", True, WHITE)   # nhiều thông báo -> hiện số
            box = label.get_rect(center=(bx, by)).inflate(6, 2)
            box.width = max(box.width, box.height)           # ít nhất là hình tròn
            box.center = (bx, by)
            draw_aa_round_rect(surf, BADGE_RED, box, box.height // 2)
            surf.blit(label, label.get_rect(center=box.center))

    def page_size(self, idx):
        """Kích thước thân island tương ứng với tab. Riêng tab Nhạc tự điều chỉnh theo tuỳ chọn bật/tắt lyrics."""
        if idx == 0:
            if not self.settings.get("show_lyrics", True):
                return (MUSIC_COMPACT_W, MUSIC_COMPACT_H)
        if 0 <= idx < len(PAGE_SIZES):
            return PAGE_SIZES[idx]
        return PAGE_SIZES[0]

    def seek_to(self, sec):
        """Tua bài hát đến vị trí sec (giây), cập nhật ngay lập tức UI và gửi lệnh SMTC nền."""
        if self.duration > 0:
            sec = max(0.0, min(float(sec), float(self.duration)))
        else:
            sec = max(0.0, float(sec))
        self.base_pos = sec
        self.base_t = time.monotonic()
        self._last_seek_time = time.monotonic()
        MediaBridge.command(("seek", sec))

    def draw_content(self, body):
        """Vẽ tab đang chọn lên lớp riêng rồi dán lên island, dịch lên CONTENT_DY px (không còn thanh tab ở trên).
        Lớp nền BLACK + colorkey BLACK nên chỉ phần tab vẽ mới đè lên island (không phá góc bo / phần trong suốt)."""
        if not (0 <= self.page < len(self.tabs)):
            return
        # Sử dụng bề rộng hiện tại self.cur_w đang co giãn mượt mà của Island!
        # Điều này đảm bảo khi tab morph từ 480 <-> 680, toàn bộ nội dung luôn căn đúng tâm island hiện tại!
        pw = round(self.cur_w)
        ph = round(EXPAND_H + NAV_EXTRA - CONTENT_DY)
        if self._content is None or self._content.get_size() != (pw, ph):
            self._content = pygame.Surface((pw, ph), pygame.SRCALPHA)
        layer = self._content
        layer.fill((0, 0, 0, 0))
        ox = (EXPAND_W - pw) // 2                            # căn giữa theo thân island đang animate
        real_mouse = self.mouse_local
        self.mouse_local = (real_mouse[0] - ox, real_mouse[1] - CONTENT_DY)   # tab nghĩ rằng nó vẫn nằm ở toạ độ gốc
        self._hit_ox, self._hit_dy = ox, CONTENT_DY          # vùng bấm của tab dời theo
        try:
            self.tabs[self.page].draw(layer)
        finally:
            self.mouse_local, self._hit_ox, self._hit_dy = real_mouse, 0, 0
        body.blit(layer, (ox, CONTENT_DY))

    NAV_ITEMS = (("music", "Nhạc"), ("calendar", "Lịch"), ("shelf", "Ngăn xếp"))

    def nav_icon(self, kind, color, size=21):
        key = (kind, color, size)
        if key not in self.nav_icons:
            self.nav_icons[key] = make_nav_icon(kind, size, color)
        return self.nav_icons[key]

    def draw_nav(self, surf, rect):
        """Thanh điều hướng ở đáy: mặc định là các chấm tròn (bán kính 3px);
        rê chuột vào thì đảo kéo dài xuống và phóng to thành các vòng tròn (bán kính 18px) chứa icon.
        Nút cài đặt (trái) và nút tắt (đỏ, phải) căn chỉnh đối xứng thẳng với điểm kết thúc góc bo."""
        nt = self.nav_t
        cx = rect.centerx
        extra_h = self.nav_extra()
        rest = self.cur_h - extra_h * nt                     # đáy thân tab (chưa kéo dài), bám theo kích thước đang animate
        top = rest - NAV_H                                   # đỉnh dải điều hướng

        # Khi thu nhỏ: cy_collapsed cách đáy 15px (nằm trong đoạn thẳng trước góc bo r=28)
        # Khi phóng to: cy_expanded cách đáy 25px (đủ không gian cho vòng tròn r=18px)
        cy_collapsed = rest - 27
        cy_expanded = self.cur_h - 27
        cy = lerp(cy_collapsed, cy_expanded, nt)
        hit_cy = cy

        spacing = lerp(16, 44, nt)
        radius = lerp(4.0, 18.0, nt)                         # thu nhỏ: 4px, phóng to: 18px theo yêu cầu
        th = self.theme()

        # Cập nhật vị trí giọt nước đang trôi giữa các tab điều hướng
        target_x = cx + (self.page - 1) * spacing
        if self.nav_cur_x is None:
            self.nav_cur_x = self.nav_tail_x = target_x
        else:
            # Đầu giọt nước tiến nhanh tới đích
            self.nav_cur_x += (target_x - self.nav_cur_x) * 0.35
            # Đuôi giọt nước chạy theo trễ hơn tạo độ co giãn chất lỏng
            self.nav_tail_x += (self.nav_cur_x - self.nav_tail_x) * 0.22

        # Vẽ nền các nút điều hướng không active trước
        for i, (kind, label) in enumerate(self.NAV_ITEMS):
            x = cx + (i - 1) * spacing
            active = i == self.page
            hit = pygame.Rect(0, 0, 44, max(NAV_H + extra_h, 44))
            hit.center = (x, hit_cy)
            hovered = hit.collidepoint(self.mouse_local) and nt > 0.3
            dot_c = th["dim"]
            btn_c = th["panel_hover"] if hovered else th["panel"]
            col = tuple(round(lerp(a, b, nt)) for a, b in zip(dot_c, btn_c))
            if not active:
                draw_aa_circle(surf, col, (x, cy), radius)
                if nt > 0.45:
                    icon = self.nav_icon(kind, th["sub"], size=22).copy()
                    icon.set_alpha(int(255 * min(1.0, (nt - 0.45) / 0.55)))
                    surf.blit(icon, icon.get_rect(center=(round(x), round(cy))))
            # Chỉ nhận sự kiện click khi thanh điều hướng đã mở rộng (nt >= 0.6)
            if nt >= 0.6:
                self.add_hit(hit, lambda i=i: setattr(self, "page", i))

        # Vẽ giọt nước chất lỏng (indicator) đang di chuyển/co giãn ở tab active
        active_dot_c = th["main"]
        active_btn_c = th["accent"]
        active_col = tuple(round(lerp(a, b, nt)) for a, b in zip(active_dot_c, active_btn_c))

        if nt < 0.35:
            # Chế độ thu nhỏ (chấm tròn): giọt nước biến thành viên thuốc trôi dẻo quẹo giữa 2 chấm
            pill_w = max(14.0, abs(self.nav_cur_x - self.nav_tail_x) + 14.0)
            pill_cx = (self.nav_cur_x + self.nav_tail_x) / 2
            pill = pygame.Rect(0, 0, round(pill_w), 6)
            pill.center = (round(pill_cx), round(cy))
            draw_aa_round_rect(surf, active_col, pill, 3.0)
        else:
            # Chế độ phóng to (vòng tròn icon): giọt nước chất lỏng co giãn giữa đầu và đuôi
            c1 = (self.nav_cur_x, cy)
            c2 = (self.nav_tail_x, cy)
            draw_capsule(surf, c1, radius, c2, radius, active_col)
            draw_aa_circle(surf, active_col, (round(self.nav_cur_x), round(cy)), radius)
            draw_aa_circle(surf, active_col, (round(self.nav_tail_x), round(cy)), radius)

            # Vẽ icon của tab active đè lên trên giọt nước
            for i, (kind, label) in enumerate(self.NAV_ITEMS):
                if i == self.page and nt > 0.45:
                    x = cx + (i - 1) * spacing
                    icon = self.nav_icon(kind, WHITE, size=22).copy()
                    icon.set_alpha(int(255 * min(1.0, (nt - 0.45) / 0.55)))
                    surf.blit(icon, icon.get_rect(center=(round(x), round(cy))))

        # Hai nút tròn ở hai đầu hàng: Cài đặt (trái) và Tắt (đỏ, phải).
        # Căn đúng vị trí tiếp tuyến kết thúc góc bo (tiếp giáp đường thẳng đứng bên hông):
        # Bán kính bo góc r=28px -> tâm nút cách mép bên đúng 28px
        side_margin = 27
        is_black = (th["bg"][0] < 25 and th["bg"][1] < 25 and th["bg"][2] < 25)
        gear_dot = th["dim"] if not is_black else GEAR_DOT
        gear_bg = th["panel"] if not is_black else GEAR_BG
        gear_hover = th["panel_hover"] if not is_black else GEAR_BG_HOVER
        self._nav_button(surf, (rect.left + side_margin, cy), nt, "gear", gear_dot, gear_bg, gear_hover,
                         self.open_settings, hit_cy)
        self._nav_button(surf, (rect.right - side_margin, cy), nt, "close", CLOSE_RED, CLOSE_RED, CLOSE_RED_HOVER,
                         self.trigger_quit, hit_cy)

    def _nav_button(self, surf, center, nt, kind, dot_c, btn_c, hover_c, fn, hit_cy):
        cx, cy = round(center[0]), round(center[1])
        hit = pygame.Rect(0, 0, 44, max(NAV_H + NAV_EXTRA, 44))
        hit.center = (cx, hit_cy)
        hovered = hit.collidepoint(self.mouse_local) and nt > 0.3
        col = tuple(round(lerp(a, b, nt)) for a, b in zip(dot_c, hover_c if hovered else btn_c))
        draw_aa_circle(surf, col, (cx, cy), lerp(4.0, 18.0, nt))  # thu nhỏ: 4px, phóng to: 18px
        if nt > 0.45:                                        # icon hiện dần khi nút đã đủ lớn
            th = self.theme()
            icon_col = WHITE if kind == "close" else th["main"]
            icon = self.nav_icon(kind, icon_col, size=22).copy()
            icon.set_alpha(int(255 * min(1.0, (nt - 0.45) / 0.55)))
            surf.blit(icon, icon.get_rect(center=(cx, cy)))      # cùng toạ độ nguyên với vòng tròn nên luôn căn giữa
        # Chỉ nhận sự kiện click khi thanh điều hướng đã mở rộng (nt >= 0.6)
        if nt >= 0.6:
            self.add_hit(hit, fn)
