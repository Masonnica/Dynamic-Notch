"""
Tab Lịch: hiển thị lịch 7 ngày to rõ (theo tuần hoặc 7 ngày lấy hôm nay làm tâm),
sự kiện/nhắc hẹn từ Google Calendar và nút thêm lịch liên kết.
"""
from datetime import date, datetime, timedelta
import pygame

from config import (
    EXPAND_W, WHITE, GREY, DIM, RED, ACCENT, ACCENT_SOFT, PANEL, PANEL_HOVER, BLACK
)
from utils.drawing import draw_text, fit_text, draw_aa_circle, draw_aa_round_rect
from .base import BaseTab

VN_WEEKDAY_NAMES = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
VN_SHORT_DAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


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
    """Tab Lịch: xem 7 ngày to rõ (tuần hoặc tâm hôm nay) và danh sách sự kiện Google Calendar."""

    def __init__(self, island):
        super().__init__(island)
        self.week_offset = 0                 # Số tuần/đợt 7 ngày dịch chuyển so với hôm nay

    def select_date(self, d_obj):
        """Chọn ngày cụ thể."""
        self.island.cal_year = d_obj.year
        self.island.cal_month = d_obj.month
        self.island.sel = (d_obj.year, d_obj.month, d_obj.day)
        self.island.ev_scroll = 0

    def shift_days(self, delta):
        """Dịch chuyển 7 ngày trước hoặc sau."""
        self.week_offset += delta
        days = self.get_display_days()
        # Tìm ngày trong dãy mới tương ứng với vị trí đang chọn hoặc giữ cùng thứ
        try:
            cur_d = date(*self.island.sel)
            target_dow = cur_d.weekday()
            match = next((d for d in days if d.weekday() == target_dow), days[0])
            self.select_date(match)
        except Exception:
            if days:
                self.select_date(days[0])
            pass

    def go_today(self):
        """Quay về ngày hôm nay."""
        self.week_offset = 0
        self.island.go_today()

    def get_display_days(self):
        """Lấy danh sách 7 ngày cần hiển thị dựa theo tùy chọn cal_view_mode."""
        island = self.island
        mode = island.settings.get("cal_view_mode", "week")
        today_d = date(*island.today)

        if mode == "7days_center":
            # 7 ngày liên tiếp với ngày hôm nay (hoặc tâm dịch chuyển) ở chính giữa (vị trí 4 / index 3)
            center_d = today_d + timedelta(days=self.week_offset * 7)
            return [center_d + timedelta(days=i) for i in range(-3, 4)]
        else:
            # "week": Theo tuần chuẩn từ T2 -> CN (hoặc tuần bắt đầu từ CN)
            week_start_cfg = island.settings.get("week_start", 0)  # 0: Thứ 2, 6: CN
            base_d = today_d + timedelta(days=self.week_offset * 7)
            diff = (base_d.weekday() - week_start_cfg) % 7
            first_d = base_d - timedelta(days=diff)
            return [first_d + timedelta(days=i) for i in range(7)]

    def draw(self, surf):
        island = self.island
        th = island.theme()

        # 1. Vẽ phần lưới lịch 7 ngày to rõ bên trái (x: 0 .. 340)
        self._draw_week_grid(surf)

        # 2. Đường phân cách dọc
        pygame.draw.line(surf, th["div"], (340, 80), (340, 245), 1)

        # 3. Vẽ phần bên phải (Danh sách sự kiện)
        self._draw_events_panel(surf)

    # ----------------------------- Phần Lưới Lịch 7 Ngày (Bên Trái) -----------------------------
    def _draw_week_grid(self, surf):
        island = self.island
        th = island.theme()

        # Tiêu đề tháng / năm của ngày đang chọn
        title_rect = pygame.Rect(64, 80, 150, 26)
        draw_text(surf, island.f_title, f"Tháng {island.cal_month} / {island.cal_year}", th["main"], center=title_rect.center)
        island.add_hit(title_rect, self.go_today)

        # Nút chuyển 7 ngày trước (<) / 7 ngày sau (>)
        for x, d in ((24, -1), (308, 1)):
            r = pygame.Rect(x - 12, 80, 24, 24)
            c = th["main"] if r.collidepoint(island.mouse_local) else th["sub"]
            if d < 0:
                pygame.draw.polygon(surf, c, [(x + 3, 86), (x + 3, 98), (x - 5, 92)])
            else:
                pygame.draw.polygon(surf, c, [(x - 3, 86), (x - 3, 98), (x + 5, 92)])
            island.add_hit(r, lambda d=d: self.shift_days(d))

        # Nút "Hôm nay" nhỏ gọn bo tròn ngay trên thanh header
        today_btn = pygame.Rect(222, 80, 68, 24)
        today_bg = th["panel_hover"] if today_btn.collidepoint(island.mouse_local) else th["panel"]
        draw_aa_round_rect(surf, today_bg, today_btn, 12)
        draw_text(surf, island.f_tiny, "Hôm nay", th["main"], center=today_btn.center)
        island.add_hit(today_btn, self.go_today)

        # Danh sách 7 ngày hiển thị (mở rộng chiều ngang, col_w=44 cho ô ngày to rõ)
        days = self.get_display_days()
        x_start = 16
        col_w = 44

        # Hàng thứ & Hàng ngày (được đẩy lên 12px sát dòng thứ hơn)
        for c, day_date in enumerate(days):
            dow = day_date.weekday()
            day_name = VN_SHORT_DAYS[dow]
            col_cx = x_start + c * col_w + col_w // 2

            # 1. Tên thứ (T2..CN)
            name_color = RED if dow == 6 else (th["main"] if dow == 5 else th["sub"])
            draw_text(surf, island.f_small, day_name, name_color, center=(col_cx, 126))

            # 2. Ô ngày (dời lên 12px: 168 -> 156, vòng tròn bán kính 16px)
            center = (col_cx, 156)
            is_today = (day_date.year, day_date.month, day_date.day) == island.today
            is_sel = (day_date.year, day_date.month, day_date.day) == island.sel

            if is_sel:
                draw_aa_circle(surf, ACCENT, center, 16)
            elif is_today:
                draw_aa_circle(surf, ACCENT_SOFT, center, 16)

            text_color = RED if (dow == 6 and not (is_today or is_sel)) else (WHITE if (is_sel or is_today) else th["main"])
            draw_text(surf, island.f_text, str(day_date.day), text_color, center=center)

            # Chấm hiển thị sự kiện bên dưới ngày
            colors = island.gcal.get_event_colors_on(day_date) if island.settings.get("show_event_dots", True) else []
            if colors:
                n_dots = len(colors)
                dot_y = center[1] + 12
                if n_dots == 1:
                    draw_aa_circle(surf, colors[0], (center[0], dot_y), 2.0)
                elif n_dots == 2:
                    draw_aa_circle(surf, colors[0], (center[0] - 4, dot_y), 2.0)
                    draw_aa_circle(surf, colors[1], (center[0] + 4, dot_y), 2.0)
                else:
                    draw_aa_circle(surf, colors[0], (center[0] - 6, dot_y), 2.0)
                    draw_aa_circle(surf, colors[1], (center[0], dot_y), 2.0)
                    draw_aa_circle(surf, colors[2], (center[0] + 6, dot_y), 2.0)

            # Hit rect cho ô ngày
            cell_hit = pygame.Rect(x_start + c * col_w, 112, col_w, 62)
            island.add_hit(cell_hit, lambda d=day_date: self.select_date(d))

        # 3. Phần Timeline bên dưới hàng ngày (theo ảnh thiết kế)
        self._draw_mini_timeline(surf)

    # ----------------------------- Phần Mini Timeline (Dưới Hàng Ngày) -----------------------------
    def _draw_mini_timeline(self, surf):
        island = self.island
        th = island.theme()

        # Vùng timeline: x từ 18 đến 328 (w = 310), y từ 180 đến 262 (h = 82)
        clip_rect = pygame.Rect(18, 180, 310, 82)
        tl_x = clip_rect.x
        tl_w = clip_rect.width
        axis_x = 72            # Trục dọc xám
        line_y = 216           # Đường ngang đỏ mốc "Bây giờ" (dời xuống thêm 20px: 196 -> 216)

        # Cắt clip để các mốc thời gian và khối sự kiện cuộn mượt mà bên trong vùng timeline
        orig_clip = surf.get_clip()
        surf.set_clip(clip_rect)

        now_dt = datetime.now()
        cur_hm = now_dt.strftime("%H:%M")
        # Thời gian hiện tại tính theo phút và giây
        now_total_min = now_dt.hour * 60 + now_dt.minute + now_dt.second / 60.0

        # Thông số độ cao của 1 khoảng thời gian (10 phút)
        slot_interval = 10.0   # 10 phút
        slot_height = 50.0     # 80px cho mỗi khoảng 10 phút
        px_per_min = slot_height / slot_interval  # 8.0 px/phút

        # Tọa độ Y của một mốc phút t:
        # Thời gian chạy dần lên theo thời gian => tương lai nằm ở dưới (y > line_y), khi thời gian trôi thì mọi thứ bị đẩy lên trên
        def time_to_y(t_min):
            return line_y + (t_min - now_total_min) * px_per_min

        # 1. Trục dọc thời gian
        pygame.draw.line(surf, th["div"], (axis_x, clip_rect.top), (axis_x, clip_rect.bottom), 2)

        # 2. Các mốc 10 phút trên trục thời gian
        min_slot = int((now_total_min - 20) // 10) * 10
        max_slot = int((now_total_min + 20) // 10) * 10

        for slot_min in range(min_slot, max_slot + 10, 10):
            if slot_min < 0 or slot_min >= 1440:
                continue
            sy = time_to_y(slot_min)
            if clip_rect.top - 20 <= sy <= clip_rect.bottom + 20:
                # Vạch khấc nhỏ trên trục dọc
                pygame.draw.line(surf, th["div"], (axis_x - 3, int(sy)), (axis_x + 3, int(sy)), 1)
                # Giờ hiển thị ở đầu mỗi khoảng (vd: 12:00, 12:10, ...)
                sh = slot_min // 60
                sm = slot_min % 60
                slot_txt = f"{sh:02d}:{sm:02d}"
                draw_text(surf, island.f_tiny, slot_txt, th["sub"], midright=(axis_x - 7, int(sy)))

        # 3. Các khung sự kiện hôm nay di chuyển theo cột thời gian
        # Chỉ hiển thị timeline của ngày hôm nay, khi chuyển ngày cũng không thay đổi
        today_events = island.gcal.events_on(date(*island.today), enabled_only=True)

        card_total_x = axis_x + 8
        card_total_w = (tl_x + tl_w) - card_total_x

        # Gom và tính toán thời gian bắt đầu - kết thúc cho từng sự kiện
        valid_evs = []
        for ev in today_events:
            start_min = ev.get("start_min")
            if start_min is None:
                if ev.get("key") and ":" in ev.get("key"):
                    try:
                        kh, km = map(int, ev["key"].split(":"))
                        start_min = kh * 60 + km
                    except Exception:
                        start_min = None
            if start_min is None:
                continue

            duration_min = max(5, ev.get("duration_min", 60))
            end_min = start_min + duration_min
            # Độ cao của khung sự kiện: height = (thời gian diễn ra sự kiện tính bằng phút / 10) * độ cao của 1 khoảng thời gian
            ev_h = max(24, int((duration_min / 10.0) * slot_height))
            ev_top_y = int(time_to_y(start_min))

            # Chỉ xử lý các sự kiện nằm trong / chạm vào vùng nhìn thấy (clip_rect)
            if ev_top_y + ev_h >= clip_rect.top - 10 and ev_top_y <= clip_rect.bottom + 10:
                valid_evs.append({
                    "ev": ev,
                    "start_min": start_min,
                    "end_min": end_min,
                    "top_y": ev_top_y,
                    "h": ev_h,
                })

        # Sắp xếp sự kiện: bắt đầu trước xếp trước, sự kiện dài hơn ưu tiên trước
        valid_evs.sort(key=lambda item: (item["start_min"], -(item["end_min"] - item["start_min"])))

        # Phân chia cụm (clusters) các sự kiện chồng chéo nhau và gán cột hiển thị (column layout)
        clusters = []
        for item in valid_evs:
            if not clusters:
                clusters.append([item])
            else:
                last_cluster = clusters[-1]
                # Thời điểm kết thúc muộn nhất trong cụm hiện tại
                cluster_end = max(x["end_min"] for x in last_cluster)
                if item["start_min"] < cluster_end:
                    # Giao nhau về thời gian -> thuộc cùng một cụm chồng lấn
                    last_cluster.append(item)
                else:
                    # Không giao nhau -> cụm mới
                    clusters.append([item])

        # Duyệt từng cụm để chia cột (chia đều chiều ngang hoặc xếp tầng thông minh)
        for cluster in clusters:
            cols = []  # danh sách thời điểm kết thúc (end_min) của từng cột
            for item in cluster:
                placed = False
                for c_idx, c_end in enumerate(cols):
                    if item["start_min"] >= c_end:
                        cols[c_idx] = item["end_min"]
                        item["col_idx"] = c_idx
                        placed = True
                        break
                if not placed:
                    item["col_idx"] = len(cols)
                    cols.append(item["end_min"])

            total_cols = len(cols)
            # Tính toán tọa độ x và chiều rộng cho từng sự kiện trong cụm
            col_gap = 4
            single_w = max(45, (card_total_w - (total_cols - 1) * col_gap) // total_cols)

            for item in cluster:
                ev = item["ev"]
                c_idx = item["col_idx"]
                cur_x = card_total_x + c_idx * (single_w + col_gap)
                # Cột cuối cùng co giãn phủ hết mép phải để tránh lẻ pixel
                cur_w = single_w if c_idx < total_cols - 1 else ((card_total_x + card_total_w) - cur_x)

                ev_card = pygame.Rect(cur_x, item["top_y"], cur_w, item["h"])
                ev_color = ev.get("color", (76, 175, 80))

                # Vẽ khung sự kiện bo góc
                draw_aa_round_rect(surf, ev_color, ev_card, 6 if total_cols > 1 else 8)

                # Khi có nhiều cột chồng lên nhau, viền mỏng giúp phân tách trực quan
                if total_cols > 1:
                    border_col = (255, 255, 255, 120) if th["is_light"] else (0, 0, 0, 100)
                    draw_aa_round_rect(surf, border_col, ev_card, 6, width=1)

                # Chọn font hiển thị tùy theo chiều rộng cột
                title_font = island.f_small if total_cols > 1 else island.f_title
                draw_text(surf, title_font, fit_text(title_font, ev.get("title", "Sự kiện"), cur_w - 12),
                          WHITE, topleft=(ev_card.x + 6, ev_card.y + 5))

                # Tên tài khoản / lịch hoặc nhãn thời gian
                cal_info = ev.get("cal_name", "") or ev.get("time_label", "")
                if item["h"] >= 38 and cur_w >= 60:
                    draw_text(surf, island.f_tiny, fit_text(island.f_tiny, cal_info, cur_w - 12),
                              (255, 255, 255, 220), topleft=(ev_card.x + 6, ev_card.y + 24))

                # Gạch chân trang trí (chỉ vẽ khi khung đủ rộng và đủ cao)
                if item["h"] >= 52 and cur_w >= 100:
                    line_w = min(100, cur_w - 20)
                    pygame.draw.line(surf, (255, 255, 255, 200),
                                     (ev_card.x + 6, ev_card.y + 44),
                                     (ev_card.x + 6 + line_w, ev_card.y + 44), 2)

        # 4. Vạch ngang màu đỏ và huy hiệu "Bây giờ" tại vị trí hiện tại line_y
        line_red = (255, 69, 58)
        pygame.draw.line(surf, line_red, (tl_x, line_y), (tl_x + tl_w, line_y), 2)

        # Huy hiệu bo tròn "Bây giờ" bên phải đường đỏ
        badge_text = "Bây giờ"
        badge_surf = island.f_tiny.render(badge_text, True, WHITE)
        bw = badge_surf.get_width() + 18
        bh = 20
        badge_rect = pygame.Rect(tl_x + tl_w - bw, line_y - bh // 2, bw, bh)
        draw_aa_round_rect(surf, line_red, badge_rect, bh // 2)
        draw_text(surf, island.f_tiny, badge_text, WHITE, center=badge_rect.center)

        # Khôi phục clip surface
        surf.set_clip(orig_clip)

    # ----------------------------- Danh sách Sự Kiện (Bên Phải) -----------------------------
    def _draw_events_panel(self, surf):
        island = self.island
        th = island.theme()
        state = island.gcal.state
        w = surf.get_width()
        right_x = 358
        right_w = w - right_x - 18            # Chiều ngang phần bên phải (~304px khi CAL_W=680)

        # Header: Tên ngày đã chọn (Bỏ nút Lọc)
        date_str = format_day_title(island.sel, island.today)
        draw_text(surf, island.f_title, fit_text(island.f_title, date_str, right_w), th["main"], midleft=(right_x, 92))

        # 1. Trạng thái Đang kết nối
        if state == "connecting":
            box = pygame.Rect(right_x, 114, right_w, 128)
            draw_aa_round_rect(surf, th["panel"], box, 10)
            msg_txt = island.gcal.message or "Đang kết nối Google Calendar..."
            draw_text(surf, island.f_small, fit_text(island.f_small, msg_txt, right_w - 20), th["accent"], center=(box.centerx, box.centery - 12))
            draw_text(surf, island.f_tiny, "Vui lòng chờ trong giây lát...", th["sub"], center=(box.centerx, box.centery + 14))
            return

        # 2. Trạng thái Chưa kết nối / Không có tài khoản liên kết -> Nút Thêm lịch như bên phần lọc
        cals = island.gcal.get_calendars() if state != "disconnected" else []
        if state == "disconnected" or not cals:
            box = pygame.Rect(right_x, 114, right_w, 128)
            draw_aa_round_rect(surf, th["panel"], box, 10)
            draw_aa_round_rect(surf, th["div"], box, 10, width=1)

            draw_text(surf, island.f_small, "Chưa liên kết Google Calendar", th["main"], center=(box.centerx, box.y + 36))
            draw_text(surf, island.f_tiny, "Liên kết lịch để đồng bộ và xem các sự kiện", th["sub"], center=(box.centerx, box.y + 60))

            # Nút "+ Thêm lịch" dạng viên thuốc (như nút bên phần lọc)
            add_btn = pygame.Rect(box.centerx - 65, box.y + 80, 130, 28)
            ac_bg = th["panel_hover"] if add_btn.collidepoint(island.mouse_local) else th["div"]
            draw_aa_round_rect(surf, ac_bg, add_btn, 14)
            draw_text(surf, island.f_tiny, "+ Thêm lịch", th["main"], center=(add_btn.centerx, add_btn.centery - 1))
            island.add_hit(add_btn, lambda: island.open_settings(tab=2))
            return

        # 3. Đã kết nối: Hiển thị sự kiện trong ngày đã chọn
        events = island.gcal.events_on(date(*island.sel), enabled_only=True)
        if not events:
            draw_text(surf, island.f_text, "Không có sự kiện", th["main"], center=(right_x + right_w // 2, 160))
            draw_text(surf, island.f_tiny, "Ngày thảnh thơi hoặc sự kiện đang ẩn", th["sub"], center=(right_x + right_w // 2, 185))
            return

        # Hiển thị tối đa 3 sự kiện trên 1 màn hình để vừa vặn chiều cao 275px
        max_ev_scroll = max(0, len(events) - 3)
        island.ev_scroll = max(0, min(island.ev_scroll, max_ev_scroll))
        visible_events = events[island.ev_scroll : island.ev_scroll + 3]

        for i, ev in enumerate(visible_events):
            card = pygame.Rect(right_x, 112 + i * 44, right_w, 38)
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

            # Tiêu đề sự kiện
            title_w = right_w - 24
            draw_text(surf, island.f_text, fit_text(island.f_text, ev["title"], title_w), th["main"],
                      topleft=(card.x + 10, card.y + 18))

        # Thanh cuộn nhỏ bên phải nếu có nhiều hơn 3 sự kiện
        if len(events) > 3:
            sb_h = max(20, int(122 * 3 / len(events)))
            sb_y = 112 + int((122 - sb_h) * island.ev_scroll / max_ev_scroll)
            draw_aa_round_rect(surf, th["bar"], (w - 7, sb_y, 3, sb_h), 1.5)

    # ----------------------------- Sự Kiện Cuộn Chuột -----------------------------
    def on_wheel(self, dy):
        """Xử lý cuộn chuột: bên trái đổi 7 ngày, bên phải cuộn sự kiện."""
        island = self.island
        mx, my = island.mouse_local

        if mx < 340:
            # Cuộn chuột bên trái lưới 7 ngày: chuyển 7 ngày trước/sau
            self.shift_days(-1 if dy > 0 else 1)
        else:
            # Cuộn chuột bên phải: cuộn sự kiện
            events = island.gcal.events_on(date(*island.sel), enabled_only=True)
            max_scroll = max(0, len(events) - 3)
            island.ev_scroll = max(0, min(island.ev_scroll - dy, max_scroll))
