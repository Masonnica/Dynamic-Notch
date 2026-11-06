"""
Tab Lịch: hiển thị lưới ngày trong tháng, sự kiện/nhắc hẹn từ Google Calendar,
và bảng điều khiển bật/tắt từng loại lịch như trên Google Calendar.
"""
import calendar
import threading
import webbrowser
from datetime import date
import pygame

from config import (
    EXPAND_W, WHITE, GREY, DIM, RED, ACCENT, ACCENT_SOFT, PANEL, PANEL_HOVER, BLACK
)
from utils.drawing import draw_text, fit_text, draw_aa_circle, draw_aa_round_rect
from .base import BaseTab

VN_WEEKDAY_NAMES = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]


def format_day_title(d, today):
    """Định dạng tiêu đề ngày, ví dụ 'Hôm nay, 05/11' hoặc 'Thứ Năm, 05/11'."""
    if d == today:
        return f"Hôm nay, {d[2]:02d}/{d[1]:02d}"
    try:
        dt = date(d[0], d[1], d[2])
        return f"{VN_WEEKDAY_NAMES[dt.weekday()]}, {d[2]:02d}/{d[1]:02d}"
    except Exception:
        return f"{d[2]:02d}/{d[1]:02d}/{d[0]}"


class CalendarTab(BaseTab):
    """Tab Lịch: xem tháng, ngày hiện tại, sự kiện Google Calendar và bộ lọc loại sự kiện."""

    def __init__(self, island):
        super().__init__(island)
        self.show_filter = False             # True: hiện danh sách bật/tắt các loại lịch
        self.cal_filter_scroll = 0           # Cuộn danh sách loại lịch

    def prompt_ical_url(self):
        """Mở hộp thoại để người dùng dán link iCal (Secret address in iCal format)."""
        def _run():
            try:
                import tkinter as tk
                from tkinter import simpledialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                url = simpledialog.askstring(
                    "Đồng bộ Google Calendar",
                    "Dán địa chỉ bí mật iCal (Secret address) từ Google Calendar:\n"
                    "(Google Calendar > Cài đặt lịch > Tích hợp lịch > Địa chỉ bí mật ở định dạng iCal)",
                    parent=root
                )
                root.destroy()
                if url:
                    self.island.gcal.import_ical_url(url.strip())
            except Exception as ex:
                print("[Dynamic Island] Lỗi nhập link iCal:", ex)
        threading.Thread(target=_run, daemon=True).start()

    def pick_ics_file(self):
        """Mở hộp thoại để người dùng chọn file .ics lịch trên máy."""
        def _run():
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                p = filedialog.askopenfilename(
                    title="Chọn file lịch .ics hoặc zip xuất từ Google Calendar",
                    filetypes=[("Lịch iCal / Zip", "*.ics;*.zip"), ("All Files", "*.*")]
                )
                root.destroy()
                if p:
                    if p.lower().endswith(".zip"):
                        self.island.gcal._unpack_zip(p)
                    else:
                        self.island.gcal.import_ics_file(p)
            except Exception as ex:
                print("[Dynamic Island] Lỗi khi mở hộp thoại chọn file:", ex)
        threading.Thread(target=_run, daemon=True).start()

    def select_day(self, day):
        """Chọn ngày trên lưới lịch."""
        self.island.sel = (self.island.cal_year, self.island.cal_month, day)
        self.island.ev_scroll = 0

    def draw(self, surf):
        island = self.island
        th = island.theme()

        # 1. Vẽ phần lưới lịch bên trái
        self._draw_month_grid(surf)

        # 2. Đường phân cách dọc
        pygame.draw.line(surf, th["div"], (228, 80), (228, 288), 1)

        # 3. Vẽ phần bên phải (Sự kiện hoặc Bộ lọc lịch)
        if self.show_filter:
            self._draw_filter_panel(surf)
        else:
            self._draw_events_panel(surf)

    # ----------------------------- Phần Lưới Lịch (Bên Trái) -----------------------------
    def _draw_month_grid(self, surf):
        island = self.island
        th = island.theme()

        # Tiêu đề tháng / năm
        title_rect = pygame.Rect(55, 80, 118, 24)
        draw_text(surf, island.f_title, f"Tháng {island.cal_month} / {island.cal_year}", th["main"], center=title_rect.center)
        island.add_hit(title_rect, island.go_today)

        # Nút chuyển tháng trước (<) / tháng sau (>)
        for x, d in ((20, -1), (206, 1)):
            r = pygame.Rect(x - 12, 80, 24, 24)
            c = th["main"] if r.collidepoint(island.mouse_local) else th["sub"]
            if d < 0:
                pygame.draw.polygon(surf, c, [(x + 3, 86), (x + 3, 98), (x - 5, 92)])
            else:
                pygame.draw.polygon(surf, c, [(x - 3, 86), (x - 3, 98), (x + 5, 92)])
            island.add_hit(r, lambda d=d: island.shift_month(d))

        # Tiêu đề các thứ trong tuần (T2 .. CN)
        x_start = 14
        col_w = 29
        start = island.settings["week_start"]                # 0 = tuần bắt đầu Thứ Hai, 6 = Chủ Nhật
        names = ("T2", "T3", "T4", "T5", "T6", "T7", "CN")
        for c in range(7):
            name = names[(start + c) % 7]
            draw_text(surf, island.f_tiny, name, RED if name == "CN" else th["sub"],
                      center=(x_start + c * col_w + col_w // 2, 114))

        # Lưới các ngày trong tháng
        for r, week in enumerate(calendar.monthcalendar(island.cal_year, island.cal_month)):
            for c, day in enumerate(week):
                if day == 0:
                    continue
                cell_rect = pygame.Rect(x_start + c * col_w, 126 + r * 22, col_w, 21)
                center = (cell_rect.centerx, cell_rect.centery)

                is_today = (island.cal_year, island.cal_month, day) == island.today
                is_sel = (island.cal_year, island.cal_month, day) == island.sel

                # Ngày đang chọn: nền xanh dương đậm. Ngày hôm nay (khi không được chọn): nền xanh dịu hơn
                circle_center = (center[0], center[1] + 1.5)
                if is_sel:
                    draw_aa_circle(surf, ACCENT, circle_center, 11)
                elif is_today:
                    draw_aa_circle(surf, ACCENT_SOFT, circle_center, 11)

                # Màu chữ (chủ nhật màu đỏ, trừ khi nằm trên nền xanh)
                text_color = RED if ((start + c) % 7 == 6 and not (is_today or is_sel)) else (WHITE if (is_sel or is_today) else th["main"])
                draw_text(surf, island.f_small, str(day), text_color, center=center)

                # Chấm hiển thị sự kiện bên dưới ngày
                d_obj = date(island.cal_year, island.cal_month, day)
                colors = island.gcal.get_event_colors_on(d_obj) if island.settings["show_event_dots"] else []
                if colors:
                    n_dots = len(colors)
                    dot_y = center[1] + 9.5
                    if n_dots == 1:
                        draw_aa_circle(surf, colors[0], (center[0], dot_y), 2)
                    elif n_dots == 2:
                        draw_aa_circle(surf, colors[0], (center[0] - 3, dot_y), 2)
                        draw_aa_circle(surf, colors[1], (center[0] + 3, dot_y), 2)
                    else:
                        draw_aa_circle(surf, colors[0], (center[0] - 5, dot_y), 2)
                        draw_aa_circle(surf, colors[1], (center[0], dot_y), 2)
                        draw_aa_circle(surf, colors[2], (center[0] + 5, dot_y), 2)

                island.add_hit(cell_rect, lambda d=day: self.select_day(d))

        # Thanh trạng thái dưới cùng bên trái
        today_btn = pygame.Rect(14, 266, 64, 22)
        today_bg = th["panel_hover"] if today_btn.collidepoint(island.mouse_local) else th["panel"]
        draw_aa_round_rect(surf, today_bg, today_btn, 11)
        draw_text(surf, island.f_tiny, "Hôm nay", th["main"], center=today_btn.center)
        island.add_hit(today_btn, island.go_today)

        # Chấm trạng thái kết nối Google
        st = island.gcal.state
        st_color = (48, 209, 88) if st == "connected" else ((255, 159, 10) if st == "connecting" else th["dim"])
        draw_aa_circle(surf, st_color, (90, 277), 3)
        draw_text(surf, island.f_tiny, "Google Calendar", th["main"] if st == "connected" else th["sub"], midleft=(98, 277))

    # ----------------------------- Danh sách Sự Kiện (Bên Phải) -----------------------------
    def _draw_events_panel(self, surf):
        island = self.island
        th = island.theme()
        state = island.gcal.state
        w = surf.get_width()
        right_w = w - 248  # Chiều ngang phần bên phải (mặc định 292px khi CAL_W=540)

        # Header: Tên ngày đã chọn & nút "Lọc"
        date_str = format_day_title(island.sel, island.today)
        draw_text(surf, island.f_title, fit_text(island.f_title, date_str, right_w - 70), th["main"], midleft=(238, 92))

        filter_btn = pygame.Rect(w - 62, 80, 52, 24)
        filter_bg = th["panel_hover"] if filter_btn.collidepoint(island.mouse_local) else th["panel"]
        draw_aa_round_rect(surf, filter_bg, filter_btn, 12)

        # Hiển thị số lượng lịch đang bật
        cals = island.gcal.get_calendars()
        enabled_cals = island.gcal.get_enabled_calendar_ids()
        btn_txt = f"Lọc {len(enabled_cals)}" if len(enabled_cals) < len(cals) else "Lọc"
        draw_text(surf, island.f_tiny, btn_txt, th["accent"] if len(enabled_cals) < len(cals) else th["sub"], center=filter_btn.center)
        island.add_hit(filter_btn, lambda: setattr(self, "show_filter", True))

        # 1. Trạng thái Đang kết nối
        if state == "connecting":
            box = pygame.Rect(238, 110, right_w, 170)
            draw_aa_round_rect(surf, th["panel"], box, 10)
            msg_txt = island.gcal.message or "Đang kết nối..."
            draw_text(surf, island.f_small, fit_text(island.f_small, msg_txt, right_w - 20), th["accent"], center=(box.centerx, box.centery - 16))
            draw_text(surf, island.f_tiny, "Vui lòng chờ trong giây lát...", th["sub"], center=(box.centerx, box.centery + 14))
            return

        # 2. Trạng thái Chưa kết nối -> 3 lựa chọn cực kỳ thuận tiện
        if state == "disconnected":
            box = pygame.Rect(238, 108, right_w, 172)
            draw_aa_round_rect(surf, th["panel"], box, 10)

            draw_text(surf, island.f_small, "Đồng bộ Google Calendar", th["main"], center=(box.centerx, box.y + 20))

            # Nút 1 (Khuyên dùng): Dán link iCal trực tiếp (siêu nhanh, không cần tài khoản dev)
            btn_w = min(220, right_w - 30)
            ical_btn = pygame.Rect(box.centerx - btn_w // 2, box.y + 44, btn_w, 28)
            i_bg = (20, 145, 255) if ical_btn.collidepoint(island.mouse_local) else ACCENT
            draw_aa_round_rect(surf, i_bg, ical_btn, 14)
            draw_text(surf, island.f_tiny, "Dán link iCal (Khuyên dùng)", WHITE, center=ical_btn.center)
            island.add_hit(ical_btn, self.prompt_ical_url)

            # Nút 2: Mở Google Calendar trong trình duyệt để lấy link iCal
            gcal_btn = pygame.Rect(box.centerx - btn_w // 2, box.y + 78, btn_w, 26)
            g_bg = th["panel_hover"] if gcal_btn.collidepoint(island.mouse_local) else th["panel"]
            draw_aa_round_rect(surf, g_bg, gcal_btn, 13)
            draw_text(surf, island.f_tiny, "Mở Google Calendar", th["sub"], center=gcal_btn.center)
            island.add_hit(gcal_btn, lambda: webbrowser.open(
                "https://calendar.google.com/calendar/r/settings"
            ))

            # Nút 3: Chọn file .ics
            file_btn = pygame.Rect(box.centerx - btn_w // 2, box.y + 110, btn_w, 24)
            f_bg = th["panel_hover"] if file_btn.collidepoint(island.mouse_local) else th["panel"]
            draw_aa_round_rect(surf, f_bg, file_btn, 12)
            draw_text(surf, island.f_tiny, "Chọn file .ics / .zip", th["sub"], center=file_btn.center)
            island.add_hit(file_btn, self.pick_ics_file)

            if island.gcal.message:
                draw_text(surf, island.f_tiny, fit_text(island.f_tiny, island.gcal.message, right_w - 20), RED,
                          center=(box.centerx, box.y + 148))
            else:
                draw_text(surf, island.f_tiny, "Hoặc kéo thả file .ics vào đảo", th["sub"], center=(box.centerx, box.y + 148))
            return

        # 3. Đã kết nối: Hiển thị sự kiện trong ngày đã chọn
        events = island.gcal.events_on(date(*island.sel), enabled_only=True)
        if not events:
            draw_text(surf, island.f_text, "Không có sự kiện", th["main"], center=(238 + right_w // 2, 180))
            draw_text(surf, island.f_tiny, "Ngày thảnh thơi hoặc sự kiện đang ẩn", th["sub"], center=(238 + right_w // 2, 202))
            return

        # Hiển thị tối đa 4 sự kiện trên 1 màn hình
        max_ev_scroll = max(0, len(events) - 4)
        island.ev_scroll = max(0, min(island.ev_scroll, max_ev_scroll))
        visible_events = events[island.ev_scroll : island.ev_scroll + 4]

        for i, ev in enumerate(visible_events):
            card = pygame.Rect(238, 112 + i * 42, right_w, 38)
            card_bg = th["panel_hover"] if card.collidepoint(island.mouse_local) else th["panel"]
            draw_aa_round_rect(surf, card_bg, card, 8)

            # Vạch màu bên trái theo màu của lịch
            bar = pygame.Rect(card.x + 3, card.y + 4, 3, 30)
            draw_aa_round_rect(surf, ev["color"], bar, 1.5)

            # Nhãn giờ
            draw_text(surf, island.f_tiny, ev["time_label"], ev["color"], topleft=(card.x + 10, card.y + 4))

            # Nhãn tên lịch ở góc phải
            draw_text(surf, island.f_tiny, fit_text(island.f_tiny, ev["cal_name"], 110), th["sub"],
                      topright=(card.right - 8, card.y + 4))

            # Tiêu đề sự kiện (hỗ trợ emoji/biểu tượng chuẩn Unicode)
            title_w = right_w - 24
            draw_text(surf, island.f_text, fit_text(island.f_text, ev["title"], title_w), th["main"],
                      topleft=(card.x + 10, card.y + 18))

        # Thanh cuộn nhỏ bên phải nếu có nhiều hơn 4 sự kiện
        if len(events) > 4:
            sb_h = max(20, int(160 * 4 / len(events)))
            sb_y = 112 + int((160 - sb_h) * island.ev_scroll / max_ev_scroll)
            draw_aa_round_rect(surf, th["bar"], (w - 7, sb_y, 3, sb_h), 1.5)

    # ----------------------------- Bộ Lọc & Quản Lý Lịch (Bên Phải) -----------------------------
    def _draw_filter_panel(self, surf):
        island = self.island
        th = island.theme()
        cals = island.gcal.get_calendars()
        enabled_ids = island.gcal.get_enabled_calendar_ids()
        w = surf.get_width()
        right_w = w - 248

        # Header: Tiêu đề & nút Xong
        draw_text(surf, island.f_title, "Quản lý lịch", th["main"], midleft=(238, 92))

        done_btn = pygame.Rect(w - 58, 80, 48, 24)
        draw_aa_round_rect(surf, ACCENT, done_btn, 12)
        draw_text(surf, island.f_tiny, "Xong", WHITE, center=done_btn.center)
        island.add_hit(done_btn, lambda: setattr(self, "show_filter", False))

        # Thanh thao tác nhanh: Bật tất cả / Tắt tất cả & số lượng
        all_btn = pygame.Rect(238, 110, 60, 20)
        ab_bg = th["panel_hover"] if all_btn.collidepoint(island.mouse_local) else th["panel"]
        draw_aa_round_rect(surf, ab_bg, all_btn, 10)
        draw_text(surf, island.f_tiny, "Bật tất cả", th["main"], center=all_btn.center)
        island.add_hit(all_btn, lambda: island.gcal.set_all_calendars(True))

        none_btn = pygame.Rect(304, 110, 60, 20)
        nb_bg = th["panel_hover"] if none_btn.collidepoint(island.mouse_local) else th["panel"]
        draw_aa_round_rect(surf, nb_bg, none_btn, 10)
        draw_text(surf, island.f_tiny, "Tắt tất cả", th["main"], center=none_btn.center)
        island.add_hit(none_btn, lambda: island.gcal.set_all_calendars(False))

        draw_text(surf, island.f_tiny, f"{len(enabled_ids)}/{len(cals)} bật", th["sub"], midright=(w - 12, 120))

        # Danh sách lịch (tối đa 4 dòng visible, có cuộn)
        max_scroll = max(0, len(cals) - 4)
        self.cal_filter_scroll = max(0, min(self.cal_filter_scroll, max_scroll))
        visible_cals = cals[self.cal_filter_scroll : self.cal_filter_scroll + 4]

        for i, cal in enumerate(visible_cals):
            cid = cal["id"]
            is_on = cid in enabled_ids
            row = pygame.Rect(238, 136 + i * 32, right_w, 30)
            row_bg = th["panel_hover"] if row.collidepoint(island.mouse_local) else th["panel"]
            draw_aa_round_rect(surf, row_bg, row, 6)

            # Chấm tròn toggle bật/tắt (phong cách Google Calendar)
            dot_center = (row.x + 16, row.centery)
            if is_on:
                draw_aa_circle(surf, cal["color"], dot_center, 7)
                draw_aa_circle(surf, WHITE, dot_center, 3)
            else:
                draw_aa_circle(surf, th["dim"], dot_center, 7, width=2)

            # Nhãn nguồn: Link hoặc File
            is_url_cal = cid in island.gcal.ical_urls
            tag_txt = "Link" if is_url_cal else "File"
            tag_bg = (20, 48, 80) if is_url_cal else th["panel_hover"]
            tag_col = (110, 180, 255) if is_url_cal else th["sub"]
            tag_r = pygame.Rect(row.x + 28, row.centery - 8, 30, 16)
            draw_aa_round_rect(surf, tag_bg, tag_r, 3)
            draw_text(surf, island.f_tiny, tag_txt, tag_col, center=tag_r.center)

            # Tên lịch (rút ngắn để nhường chỗ cho nút xóa)
            name_color = th["main"] if is_on else th["sub"]
            draw_text(surf, island.f_small, fit_text(island.f_small, cal["name"], right_w - 110), name_color,
                      midleft=(row.x + 64, row.centery))

            # Nút ✕ Xóa lịch này
            del_btn = pygame.Rect(row.right - 26, row.y + 7, 22, 16)
            del_bg = (80, 20, 20) if del_btn.collidepoint(island.mouse_local) else (50, 30, 30)
            draw_aa_round_rect(surf, del_bg, del_btn, 4)
            draw_text(surf, island.f_tiny, "✕", RED, center=del_btn.center)
            island.add_hit(del_btn, lambda cid=cid: island.gcal.remove_calendar(cid))

            # Vùng click toggle (loại trừ nút xóa)
            toggle_zone = pygame.Rect(row.x, row.y, row.width - 30, row.height)
            island.add_hit(toggle_zone, lambda cid=cid: island.gcal.toggle_calendar(cid))

        # Thanh cuộn nếu có nhiều hơn 4 lịch
        if len(cals) > 4:
            sb_h = max(16, int(128 * 4 / len(cals)))
            sb_y = 136 + int((128 - sb_h) * self.cal_filter_scroll / max_scroll)
            draw_aa_round_rect(surf, th["bar"], (w - 7, sb_y, 3, sb_h), 1.5)

        # Đường kẻ phân cách
        pygame.draw.line(surf, th["div"], (238, 263), (w - 10, 263), 1)

        # Nút "Thêm lịch" (mở cửa sổ Cài đặt và chuyển thẳng vào tab Lịch)
        # Nhích lên Y=267 (cách đáy thông thoáng hơn, không bị dính sát các chấm điều hướng)
        add_cal_btn = pygame.Rect(238, 267, right_w, 22)
        ac_bg = th["panel_hover"] if add_cal_btn.collidepoint(island.mouse_local) else th["panel"]
        draw_aa_round_rect(surf, ac_bg, add_cal_btn, 11)
        draw_text(surf, island.f_tiny, "+ Thêm lịch", th["main"], center=(add_cal_btn.centerx, add_cal_btn.centery - 1))
        island.add_hit(add_cal_btn, lambda: island.open_settings(tab=2))

    # ----------------------------- Sự Kiện Cuộn Chuột -----------------------------
    def on_wheel(self, dy):
        """Xử lý cuộn chuột: bên trái đổi tháng, bên phải cuộn sự kiện hoặc bộ lọc."""
        island = self.island
        mx, my = island.mouse_local

        if mx < 228:
            # Cuộn chuột bên trái lưới tháng: chuyển tháng trước/sau
            island.shift_month(-1 if dy > 0 else 1)
        else:
            # Cuộn chuột bên phải: cuộn sự kiện hoặc cuộn danh sách lịch
            if self.show_filter:
                cals = island.gcal.get_calendars()
                max_scroll = max(0, len(cals) - 4)
                self.cal_filter_scroll = max(0, min(self.cal_filter_scroll - dy, max_scroll))
            else:
                events = island.gcal.events_on(date(*island.sel), enabled_only=True)
                max_scroll = max(0, len(events) - 4)
                island.ev_scroll = max(0, min(island.ev_scroll - dy, max_scroll))
