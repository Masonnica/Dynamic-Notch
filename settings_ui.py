"""
Cửa sổ Cài đặt: hiện ra bằng hiệu ứng giọt nước tách từ đáy Dynamic Island, rơi xuống giữa màn hình
rồi phóng to thành cửa sổ. Dùng chung kiểu cửa sổ trong suốt (colorkey) và đọc chuột trực tiếp từ Windows
như island, nên không cướp focus và không cần xử lý sự kiện chuột của pygame.

Cửa sổ pygame thật là một "sân khấu" trong suốt rộng bằng cửa sổ cài đặt (+ lề) và cao từ mép trên màn hình
tới hết cửa sổ cài đặt: giọt nước rơi trên sân khấu này, phần không vẽ là màu KEY nên trong suốt và chuột xuyên qua.
"""
import time
import pygame

from config import (
    KEY, BLACK, PANEL, PANEL_HOVER, ACCENT, WHITE, GREY, DIM, RED, CLOSE_RED, CLOSE_RED_HOVER, GEAR_BG,
    OFFSCREEN_POS, TOP_MARGIN, SET_W, SET_H, SETTINGS_TITLE, APP_VERSION, GITHUB_REPO
)
from utils.win32 import setup_native_window, keep_on_top, move_window, dwm_flush, cursor_pos, mouse_down, get_clipboard_text, LayeredPresenter
from utils.drawing import (
    draw_text, draw_capsule, make_nav_icon, lerp, ease_out_cubic, ease_out_back, fit_text,
    draw_aa_circle, draw_aa_round_rect, draw_fluid_pill
)

# Thời lượng từng pha (giây): tách giọt -> rơi -> phóng to thành cửa sổ -> nội dung hiện dần
T_NECK, T_FALL, T_GROW, T_FADE = 0.20, 0.30, 0.34, 0.16
T_TOTAL = T_NECK + T_FALL + T_GROW + T_FADE
DROP_R = 11                                  # bán kính giọt nước khi rơi
WIN_RADIUS = 27                              # bo góc cửa sổ cài đặt
MARGIN = 48                                  # lề trong suốt quanh cửa sổ (chừa chỗ cho hiệu ứng vọt quá)

T_SHRINK = 0.22                              # đóng: nội dung ẩn + cửa sổ co lại thành giọt
T_RISE = 0.42                                # đóng: giọt bay lên, đè qua island rồi ra khỏi mép trên màn hình
# Thứ tự tabs: Chung, Cá nhân hóa (đưa lên), Lịch (đưa xuống), Thông tin (neo dưới cùng)
TOP_TABS = ("Chung", "Cá nhân hóa", "Lịch")
BOTTOM_TAB = "Thông tin"
TABS = ("Chung", "Cá nhân hóa", "Lịch", "Thông tin")

RING_CHOICES = (("battery", "Pin"), ("music", "Nhạc"))
PRESET_COLORS = (
    ("Đen", (4, 6, 10)),
    ("Đỏ", (235, 55, 65)),
    ("Xanh dương", (30, 130, 250)),
    ("Xanh lá", (48, 195, 85)),
    ("Hồng", (240, 70, 155)),
    ("Cam", (255, 135, 35)),
    ("Tím", (165, 80, 235)),
)

PALETTE_COLORS = (
    (4, 6, 10),       # Đen Dynamic
    (28, 36, 48),     # Xám chì
    (15, 23, 42),     # Lam đêm
    (15, 76, 129),    # Lam cổ điển
    (0, 128, 128),    # Xanh mòng két Teal
    (16, 149, 93),    # Xanh lục bảo Emerald
    (34, 112, 62),    # Xanh lá thông Forest
    (217, 119, 6),    # Vàng hổ phách Amber
    (234, 88, 12),    # Cam hoàng hôn
    (225, 29, 72),    # Đỏ mâm xôi
    (190, 18, 60),    # Đỏ Ruby
    (147, 51, 234),   # Tím Violet
    (79, 70, 229),    # Xanh chàm Indigo
    (78, 52, 46),     # Nâu Mocha
)


SECONDS_CHOICES = (
    ("both", "Cả 2 chế độ"),
    ("compact", "Chế độ thu gọn"),
    ("expand", "Chế độ mở rộng"),
    ("none", "Không hiển thị"),
)


class SettingsWindow:
    def __init__(self, island, scr_w, scr_h):
        self.island = island
        self.ov_w = SET_W + 2 * MARGIN
        self.cy = scr_h // 2 + 50                            # tâm cửa sổ dịch xuống thêm một chút (+50px)
        self.ov_h = min(scr_h, self.cy + SET_H // 2 + MARGIN)
        self.x, self.y = (scr_w - self.ov_w) // 2, TOP_MARGIN
        # Tạo ngoài màn hình, tô trong suốt rồi mới được dời vào khi mở (giống cửa sổ island)
        self.window = pygame.Window(SETTINGS_TITLE, (self.ov_w, self.ov_h), position=OFFSCREEN_POS, borderless=True)
        self.hwnd = setup_native_window(SETTINGS_TITLE, use_colorkey=False)
        self.presenter = LayeredPresenter(self.hwnd, self.ov_w, self.ov_h) if self.hwnd else None
        self._render_surf = pygame.Surface((self.ov_w, self.ov_h), pygame.SRCALPHA)
        if self.presenter:
            self._render_surf.fill((0, 0, 0, 0))
            self.presenter.present(self._render_surf)
        else:
            self.window.get_surface().fill(KEY)
            self.window.flip()
        font_family = "segoeui,segoeuiemoji,segoeuisymbol"
        # Dùng font chuẩn, hỗ trợ tiếng Việt và kerning chính xác
        self.f_title = pygame.font.SysFont(font_family, 24, bold=True)
        self.f_text = pygame.font.SysFont(font_family, 17, bold=True)
        self.f_small = pygame.font.SysFont(font_family, 14, bold=True)
        # Font chữ phụ rõ nét (size 14 regular không bị dính chữ như synthetic bold)
        self.f_sub = pygame.font.SysFont(font_family, 14, bold=False)
        self.f_btn = pygame.font.SysFont(font_family, 13, bold=True)
        self.f_tiny = pygame.font.SysFont(font_family, 12, bold=True)
        self.tab = 0                                         # tab đang chọn: 0 Chung, 1 Lịch
        self.tab_cur_y = None                                # vị trí Y đầu giọt nước của tab sidebar
        self.tab_tail_y = None                               # vị trí Y đuôi giọt nước của tab sidebar
        self._seg_cur_x = {}                                 # vị trí X đầu giọt nước cho segmented control
        self._seg_tail_x = {}                                # vị trí X đuôi giọt nước cho segmented control
        self.ct = 0.0                                        # thời gian đã trôi qua của hiệu ứng đóng
        self.state = "closed"                                # closed | opening | open | closing
        self.visible = False
        self.t = 0.0                                         # tiến độ hiệu ứng 0..T_TOTAL
        self._last = time.monotonic()
        self.start_y = 0                                     # đáy island (toạ độ cửa sổ) lúc bấm
        self.prev_l = False
        self.hits = []
        self.mouse = (-999, -999)
        self.input_url = ""        # nội dung đang gõ trong ô nhập link iCal
        self.input_active = False  # True: đang hiện ô nhập link iCal
        self.input_anim = 0.0      # tiến độ hiệu ứng mở hộp nhập link iCal (0.0 -> 1.0)
        self.color_modal_active = False # True: đang mở popup chọn màu tùy chỉnh
        self.color_modal_anim = 0.0     # tiến độ hiệu ứng mở popup chọn màu (0.0 -> 1.0)
        self.color_picker_rgb = [4, 6, 10]
        self._dragging_slider = None
        self._last_click_t = 0.0
        self.modal_dialog_active = False # True: đang mở hộp thoại của hệ điều hành
        self.dropdown_active = False # True: menu sổ xuống của Hiện giây đang mở
        self._bksp_down = False    # Trạng thái đang giữ phím Backspace
        self._bksp_timer = 0.0     # Mốc thời gian lần xóa kế tiếp khi đè phím

    # ------------------------------ Trạng thái ------------------------------
    @property
    def active(self):
        return self.state != "closed"

    @property
    def animating(self):
        return self.state in ("opening", "closing") or (0.001 < self.input_anim < 0.999) or (0.001 < self.color_modal_anim < 0.999)

    def win_rect(self):
        r = pygame.Rect(0, 0, SET_W, SET_H)
        r.center = (self.ov_w // 2, self.cy)
        return r

    def covers(self, sx, sy):
        """Điểm (toạ độ màn hình) có nằm trên cửa sổ cài đặt đã hiện đầy đủ không (để island bỏ qua chuột ở đó)."""
        if self.state != "open":
            return False
        return self.win_rect().move(self.x, self.y).collidepoint(sx, sy)

    def open(self, island_bottom, tab=None):
        if tab is not None:
            self._switch_tab(tab)
        if self.state in ("opening", "open"):
            return
        self.start_y = island_bottom
        self.state = "opening"
        self.prev_l = True                                   # nút chuột còn đang giữ từ cú bấm mở -> không tính là click mới
        self._last = time.monotonic()

    def close(self):
        if self.state in ("opening", "open"):
            self.state, self.ct = "closing", 0.0
            self.t = min(self.t, T_TOTAL)
            self.color_modal_active = False
            self.color_modal_anim = 0.0
            self._dragging_slider = None

    def close_immediate(self):
        """Đóng ngay lập tức và ẩn cửa sổ không chờ animation (dùng khi tắt app)."""
        self.state = "closed"
        self.t = self.ct = 0.0
        self.input_active = False
        self.input_anim = 0.0
        self.color_modal_active = False
        self.color_modal_anim = 0.0
        self._dragging_slider = None
        self.dropdown_active = False
        self._hide()

    # ------------------------------ Cập nhật ------------------------------
    def update(self):
        if self.state == "closed":
            return
        now = time.monotonic()
        dt = min(now - self._last, 0.05)
        self._last = now
        if self.state == "opening":
            self.t += dt
            if self.t >= T_TOTAL:
                self.t, self.state = T_TOTAL, "open"
        elif self.state == "closing":
            self.ct += dt
            if self.ct >= T_SHRINK + T_RISE:
                self.t, self.state = 0.0, "closed"
                self._hide()
                return
        if self.animating:
            self.start_y = round(self.island.cur_h) + TOP_MARGIN   # giọt luôn bám đúng đáy island hiện tại (kể cả lúc nó đang thu lại)
        cx, cy = cursor_pos()
        self.mouse = (cx - self.x, cy - self.y)
        left = mouse_down(1)
        if not left:
            self._dragging_slider = None
        elif self.color_modal_active and self._dragging_slider is not None:
            wr = self.win_rect()
            box_left = (SET_W - 540) // 2
            slider_start_x = 158
            track_x = slider_start_x + 24
            track_w = (540 - slider_start_x - 24) - 68
            mouse_in_layer_x = self.mouse[0] - wr.left
            rel_x = max(0.0, min(float(track_w), float(mouse_in_layer_x - (box_left + track_x))))
            self.color_picker_rgb[self._dragging_slider] = int(round((rel_x / track_w) * 255.0))

        if left and not self.prev_l and self.state == "open":
            if now - self._last_click_t >= 0.2:
                self._last_click_t = now
                for rect, fn in reversed(self.hits):
                    if rect.collidepoint(self.mouse):
                        fn()
                        break
        self.prev_l = left

        # Animation mượt mà khi mở / đóng hộp thoại nhập link iCal
        target_anim = 1.0 if self.input_active else 0.0
        if abs(self.input_anim - target_anim) > 0.001:
            self.input_anim += (target_anim - self.input_anim) * min(1.0, dt * 14.0)
            if not self.input_active and self.input_anim < 0.02:
                self.input_anim = 0.0
                self.input_url = ""

        # Animation mượt mà khi mở / đóng popup chọn màu tùy chỉnh
        target_color_anim = 1.0 if self.color_modal_active else 0.0
        if abs(self.color_modal_anim - target_color_anim) > 0.001:
            self.color_modal_anim += (target_color_anim - self.color_modal_anim) * min(1.0, dt * 14.0)
            if not self.color_modal_active and self.color_modal_anim < 0.02:
                self.color_modal_anim = 0.0
                self._dragging_slider = None

        # Xử lý xóa liên tục khi đè giữ phím Backspace
        if self.input_active and self._bksp_down:
            if now >= self._bksp_timer and self.input_url:
                self.input_url = self.input_url[:-1]
                self._bksp_timer = now + 0.035  # Lặp lại nhanh (~28 ký tự/giây) giống chuẩn hệ điều hành

    def _hide(self):
        if self.presenter:
            self._render_surf.fill((0, 0, 0, 0))
            self.presenter.present(self._render_surf)
        else:
            surf = self.window.get_surface()
            surf.fill(KEY)
            self.window.flip()
        dwm_flush()
        if self.hwnd:
            move_window(self.hwnd, *OFFSCREEN_POS)
        else:
            self.window.position = OFFSCREEN_POS
        self.visible = False

    # ------------------------------ Vẽ ------------------------------
    def draw(self):
        if self.state == "closed":
            return
        surf = self._render_surf if self.presenter else self.window.get_surface()
        surf.fill((0, 0, 0, 0) if self.presenter else KEY)
        self.hits = []
        if self.state == "closing":
            self.draw_closing(surf, self.ct)
        else:
            self.draw_anim(surf, self.t)
        if self.presenter:
            self.presenter.present(self._render_surf)
        else:
            self.window.flip()
        if not self.visible:                                 # khung đầu đã sẵn sàng -> đưa cửa sổ vào màn hình
            dwm_flush()
            if self.hwnd:
                move_window(self.hwnd, self.x, self.y)
            else:
                self.window.position = (self.x, self.y)
            self.visible = True

    def draw_closing(self, surf, ct):
        """Đóng: nội dung ẩn dần, cửa sổ co thành giọt, rồi giọt bay thẳng lên, đè lên Dynamic Island và ra khỏi mép trên."""
        cx = self.ov_w // 2
        bg_c = tuple(self.island.settings.get("bg_color", [4, 6, 10]))
        if ct < T_SHRINK:                                    # chạy ngược pha 'nội dung hiện' + 'phóng to'
            u = ct / T_SHRINK
            self.draw_anim(surf, T_TOTAL - u * (T_GROW + T_FADE))
            return
        u = (ct - T_SHRINK) / T_RISE
        y = lerp(self.cy, -4 * DROP_R, u * u)                # nhanh dần lên trên
        tail = lerp(0, 30, min(1.0, u * 2.0))                # đuôi kéo dài phía dưới theo tốc độ
        draw_capsule(surf, (cx, y), DROP_R, (cx, y + tail), 4, bg_c)

    def draw_anim(self, surf, t):
        cx = self.ov_w // 2
        by = self.start_y                                    # đáy island
        bg_c = tuple(self.island.settings.get("bg_color", [4, 6, 10]))
        if t < T_NECK:                                       # pha 1: giọt phình ra ở đáy island, cổ giọt mảnh dần rồi đứt
            u = ease_out_cubic(t / T_NECK)
            draw_capsule(surf, (cx, by - 8), lerp(16, 3, u), (cx, by + lerp(1, 26, u)), lerp(4, DROP_R, u), bg_c)
            return
        t2 = t - T_NECK
        if t2 < T_FALL:                                      # pha 2: giọt rơi xuống tâm cửa sổ (nhanh dần), đuôi kéo dài theo tốc độ
            u = t2 / T_FALL
            y = lerp(by + 26, self.cy, u * u)
            tail = lerp(0, 24, min(1.0, u * 1.6)) * (1 - u ** 4)
            draw_capsule(surf, (cx, y), DROP_R, (cx, y - tail), lerp(3, 5, min(1.0, u * 2)), bg_c)
            return
        t3 = t2 - T_FALL
        if t3 < T_GROW:                                      # pha 3: giọt phóng to thành hình cửa sổ (vọt quá một chút rồi co lại)
            u = ease_out_back(t3 / T_GROW, 0.9)
            w, h = lerp(2 * DROP_R, SET_W, u), lerp(2 * DROP_R, SET_H, u)
            rad = int(max(1, min(lerp(DROP_R, WIN_RADIUS, min(u, 1.0)), min(w, h) / 2)))
            r = pygame.Rect(0, 0, round(w), round(h))
            r.center = (cx, self.cy)
            draw_aa_round_rect(surf, bg_c, r, rad)
            return
        a = min(1.0, (t3 - T_GROW) / T_FADE)                 # pha 4: nội dung hiện dần
        self.draw_window(surf, a * a * (3 - 2 * a))

    # ------------------------------ Nội dung cửa sổ ------------------------------
    def draw_window(self, surf, alpha):
        wr = self.win_rect()
        bg_c = tuple(self.island.settings.get("bg_color", [4, 6, 10]))
        draw_aa_round_rect(surf, bg_c, wr, WIN_RADIUS)
        if alpha <= 0:
            return
        layer = surf.subsurface(wr).copy()                   # nội dung vẽ lên bản sao rồi trộn lại -> hiện/ẩn dần mà không phá góc bo
        self._content(layer, wr.topleft, self.island)
        layer.set_alpha(int(255 * alpha))
        surf.blit(layer, wr.topleft)

    def _hit(self, rect, origin, fn):
        self.hits.append((rect.move(origin), fn))

    def _seg(self, s, origin, mouse, x, y, choices, current, on_pick, seg_w, h=32):
        """Nhóm nút chọn 1 trong nhiều (segmented control) có hiệu ứng giọt nước chuyển động mượt mà."""
        th = self.island.theme()
        total_w = seg_w * len(choices)
        draw_aa_round_rect(s, th["panel"], (x, y, total_w, h), h // 2)

        # Tìm chỉ số mục đang chọn
        cur_idx = 0
        for i, (key, _) in enumerate(choices):
            if key == current:
                cur_idx = i
                break

        seg_id = f"{x}_{y}"
        target_x = x + cur_idx * seg_w
        if seg_id not in self._seg_cur_x:
            self._seg_cur_x[seg_id] = self._seg_tail_x[seg_id] = float(target_x)
        else:
            self._seg_cur_x[seg_id] += (target_x - self._seg_cur_x[seg_id]) * 0.35
            self._seg_tail_x[seg_id] += (self._seg_cur_x[seg_id] - self._seg_tail_x[seg_id]) * 0.22

        # Vẽ giọt nước chất lỏng màu accent trôi giữa các nút chọn
        pad_in = 2
        pill_h = h - pad_in * 2
        pill_w = seg_w - pad_in * 2
        p1 = (self._seg_cur_x[seg_id] + pad_in, y + pad_in, pill_w, pill_h)
        p2 = (self._seg_tail_x[seg_id] + pad_in, y + pad_in, pill_w, pill_h)
        draw_fluid_pill(s, p1, p2, th["accent"], border_radius=(pill_h) // 2)

        for i, (key, label) in enumerate(choices):
            r = pygame.Rect(x + i * seg_w, y, seg_w, h)
            on = current == key
            if not on and r.collidepoint(mouse):
                draw_aa_round_rect(s, th["panel_hover"], r.inflate(-4, -4), (h - 4) // 2)
            draw_text(s, self.f_btn, label, WHITE if on else th["sub"], center=(r.centerx, r.centery - 1))
            self._hit(r, origin, lambda k=key: on_pick(k))

    def _switch(self, s, origin, mouse, right, y, on, on_toggle):
        th = self.island.theme()
        sw = pygame.Rect(right - 52, y, 52, 28)
        off_col = th["panel_hover"] if not th["is_light"] else (180, 180, 190)
        draw_aa_round_rect(s, th["accent"] if on else off_col, sw, 14)
        draw_aa_circle(s, WHITE, (sw.right - 14 if on else sw.left + 14, sw.centery), 11)
        self._hit(sw.inflate(8, 8), origin, on_toggle)

    def _row(self, s, y, title, sub, pad, max_w=None):
        th = self.island.theme()
        draw_text(s, self.f_text, title, th["main"], topleft=(pad, y))
        sub_txt = fit_text(self.f_sub, sub, max_w) if max_w else sub
        draw_text(s, self.f_sub, sub_txt, th["sub"], topleft=(pad, y + 29))

    def handle_click_event(self, button, pos=None):
        """Xử lý sự kiện click chuột trực tiếp từ event queue."""
        if self.state != "open" or button != 1:
            return
        now = time.monotonic()
        if now - self._last_click_t < 0.2:
            return
        self._last_click_t = now
        self.prev_l = True
        cx, cy = cursor_pos()
        click_mouse = (cx - self.x, cy - self.y)
        for rect, fn in reversed(self.hits):
            if rect.collidepoint(click_mouse):
                fn()
                break

    def handle_event(self, e):
        """Xử lý phím khi ô nhập link iCal hoặc popup chọn màu đang mở."""
        if self.color_modal_active and e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self._cancel_color_picker()
            return
        if not self.input_active or self.state != "open":
            return
        if e.type == pygame.KEYDOWN:
            # Hỗ trợ Ctrl + V dán link từ clipboard
            if (e.key == pygame.K_v and (pygame.key.get_mods() & pygame.KMOD_CTRL)) or \
               (e.key == pygame.K_INSERT and (pygame.key.get_mods() & pygame.KMOD_SHIFT)):
                clip = get_clipboard_text().strip()
                if clip:
                    self.input_url += clip
                return
            if e.key == pygame.K_BACKSPACE:
                self.input_url = self.input_url[:-1]
                self._bksp_down = True
                self._bksp_timer = time.monotonic() + 0.35  # Chờ 350ms trước khi bắt đầu xóa liên tục
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._submit_ical_url()
            elif e.key == pygame.K_ESCAPE:
                self.input_active = False
                self.input_url = ""
                self._bksp_down = False
                try:
                    pygame.key.stop_text_input()
                except Exception:
                    pass
        elif e.type == pygame.KEYUP:
            if e.key == pygame.K_BACKSPACE:
                self._bksp_down = False
        elif e.type == pygame.TEXTINPUT:
            # Bỏ qua nếu đang bấm tổ hợp phím tắt Ctrl
            if not (pygame.key.get_mods() & pygame.KMOD_CTRL):
                self.input_url += e.text

    def _submit_ical_url(self):
        url = self.input_url.strip()
        self.input_active = False
        pygame.key.stop_text_input()
        if url:
            import threading
            threading.Thread(target=lambda: self.island.gcal.import_ical_url(url), daemon=True).start()

    def _open_color_picker(self):
        """Mở popup chọn màu tùy chỉnh với hiệu ứng animation mượt mà."""
        cur = list(self.island.settings.get("bg_color", [4, 6, 10]))
        self.color_picker_rgb = [int(cur[0]), int(cur[1]), int(cur[2])]
        self.color_modal_active = True
        self._dragging_slider = None

    def _cancel_color_picker(self):
        """Đóng popup chọn màu tùy chỉnh không lưu."""
        self.color_modal_active = False
        self._dragging_slider = None

    def _apply_color_picker(self):
        """Lưu màu nền tùy chỉnh và đóng popup."""
        self.island.set_setting("bg_color", [int(c) for c in self.color_picker_rgb])
        self.color_modal_active = False
        self._dragging_slider = None

    def _set_palette_color(self, c):
        """Chọn nhanh màu từ bảng gợi ý trong popup."""
        self.color_picker_rgb = [int(c[0]), int(c[1]), int(c[2])]

    def _switch_tab(self, i):
        """Chuyển tab; nếu ô nhập iCal hoặc popup chọn màu đang mở thì đóng lại trước."""
        if self.input_active:
            self.input_active = False
            self.input_anim = 0.0
            self.input_url = ""
            pygame.key.stop_text_input()
        if self.color_modal_active:
            self.color_modal_active = False
            self.color_modal_anim = 0.0
            self._dragging_slider = None
        self.dropdown_active = False
        self.tab = i

    def _content(self, s, origin, island):
        mouse = (self.mouse[0] - origin[0], self.mouse[1] - origin[1])   # chuột trong toạ độ cửa sổ cài đặt
        pad_l, pad_r = 28, SET_W - 32
        sidebar_w = 170
        content_left = pad_l + sidebar_w + 24
        right = pad_r
        st = island.settings
        th = island.theme()

        # Tiêu đề + nút đóng
        gear = make_nav_icon("gear", 26, th["main"])
        s.blit(gear, gear.get_rect(center=(pad_l + 14, 42)))
        draw_text(s, self.f_title, "Cài đặt", th["main"], midleft=(pad_l + 38, 42))
        qr = pygame.Rect(0, 0, 28, 28)
        qr.center = (right - 14, 42)
        draw_aa_circle(s, CLOSE_RED_HOVER if qr.collidepoint(mouse) else CLOSE_RED, qr.center, 14)
        x_icon = make_nav_icon("close", 20, WHITE)
        s.blit(x_icon, x_icon.get_rect(center=qr.center))
        self._hit(qr.inflate(8, 8), origin, self.close)

        # Thanh tab dọc (sidebar) bên trái: 3 tab đầu ở trên, tab "Thông tin" neo ở đáy
        tab_y = 86
        info_idx = 3
        info_r = pygame.Rect(pad_l, SET_H - pad_l - 38, sidebar_w, 38)
        
        # Danh sách vị trí các tab
        tab_rects = []
        for i in range(len(TOP_TABS)):
            tab_rects.append(pygame.Rect(pad_l, tab_y + i * 46, sidebar_w, 38))
        tab_rects.append(info_r)

        target_r = tab_rects[min(self.tab, len(tab_rects) - 1)]
        target_y = float(target_r.y)

        # Cập nhật vị trí giọt nước chất lỏng trôi giữa các tab sidebar
        if self.tab_cur_y is None:
            self.tab_cur_y = self.tab_tail_y = target_y
        else:
            self.tab_cur_y += (target_y - self.tab_cur_y) * 0.32
            self.tab_tail_y += (self.tab_cur_y - self.tab_tail_y) * 0.20

        # Vẽ nền xám mặc định cho tất cả các tab trước
        for i, name in enumerate(TOP_TABS):
            r = tab_rects[i]
            bg = th["panel_hover"] if r.collidepoint(mouse) else th["panel"]
            draw_aa_round_rect(s, bg, r, 12)
            self._hit(r, origin, lambda i=i: self._switch_tab(i))

        info_bg = th["panel_hover"] if info_r.collidepoint(mouse) else th["panel"]
        draw_aa_round_rect(s, info_bg, info_r, 12)
        self._hit(info_r, origin, lambda: self._switch_tab(info_idx))

        # Vẽ giọt nước chất lỏng màu xanh accent trôi dẻo quẹo giữa tab cũ và tab mới
        p1 = (pad_l, self.tab_cur_y, sidebar_w, 38)
        p2 = (pad_l, self.tab_tail_y, sidebar_w, 38)
        draw_fluid_pill(s, p1, p2, th["accent"], border_radius=12)

        # Vẽ chữ của các tab đè lên trên giọt nước
        for i, name in enumerate(TOP_TABS):
            r = tab_rects[i]
            on = i == self.tab
            draw_text(s, self.f_text, name, WHITE if on else th["sub"], midleft=(r.left + 16, r.centery - 1))

        info_on = self.tab == info_idx
        draw_text(s, self.f_text, BOTTOM_TAB, WHITE if info_on else th["sub"], midleft=(info_r.left + 16, info_r.centery - 1))

        # Đường phân cách dọc giữa Sidebar và vùng Nội dung
        div_x = pad_l + sidebar_w + 12
        pygame.draw.line(s, th["div"], (div_x, 86), (div_x, SET_H - pad_l), 1)

        # Vùng nội dung tab bên phải
        pad = content_left
        y0, step = 92, 86
        if self.tab == 0:                                    # ---- Chung ----
            self._row(s, y0, "Vòng tròn bên trái", "Hiển thị % pin hoặc tiến độ bài nhạc", pad)
            cur_src = st.get("ring_source", "battery")
            if cur_src not in ("battery", "music"):
                cur_src = "battery"
            self._seg(s, origin, mouse, right - 64 * 2, y0 + 2, RING_CHOICES, cur_src,
                      lambda k: island.set_setting("ring_source", k), 64, h=28)

            dd_w, dd_h = 152, 28
            self._row(s, y0 + step, "Hiện giây", "Chọn hiển thị giây cho đồng hồ Dynamic Notch", pad)
            sec_mode = st.get("seconds_mode")
            if sec_mode is None:
                sec_mode = "expand" if st.get("show_seconds", True) else "none"

            mode_labels = dict(SECONDS_CHOICES)
            cur_label = mode_labels.get(sec_mode, "Chế độ mở rộng")

            # Dropdown menu nhỏ gọn hơn, không bị lấn sang dòng chữ mô tả
            dd_rect = pygame.Rect(right - dd_w, y0 + step + 2, dd_w, dd_h)
            dd_hover = dd_rect.collidepoint(mouse)
            dd_bg = th["panel_hover"] if (dd_hover or self.dropdown_active) else th["panel"]
            draw_aa_round_rect(s, dd_bg, dd_rect, 6)
            draw_aa_round_rect(s, th["div"], dd_rect, 6, width=1)

            # Vạch màu xanh điểm nhấn nhỏ bên trái khi đang chọn
            draw_aa_round_rect(s, th["accent"], (dd_rect.left + 4, dd_rect.top + 5, 2.5, dd_h - 10), 1.5)
            draw_text(s, self.f_small, cur_label, th["main"], midleft=(dd_rect.left + 12, dd_rect.centery - 1))

            # Mũi tên nhỏ chỉ xuống
            arr_y = dd_rect.centery - 2 if not self.dropdown_active else dd_rect.centery + 2
            pygame.draw.lines(s, th["sub"], False, [
                (dd_rect.right - 16, arr_y - 2),
                (dd_rect.right - 12, arr_y + 2),
                (dd_rect.right - 8, arr_y - 2)
            ], 2)

            def _toggle_dd():
                self.dropdown_active = not self.dropdown_active
            self._hit(dd_rect, origin, _toggle_dd)

            self._row(s, y0 + 2 * step, "Hiện chuông thông báo", "Chuông nằm cạnh giờ khi có thông báo mới", pad)
            on = bool(st["show_bell"])
            self._switch(s, origin, mouse, right, y0 + 2 * step + 2, on, lambda v=on: island.set_setting("show_bell", not v))

            self._row(s, y0 + 3 * step, "Khởi động cùng Windows", "Tự động chạy Dynamic Notch khi mở máy", pad)
            on = bool(st.get("auto_startup", False))
            self._switch(s, origin, mouse, right, y0 + 3 * step + 2, on, lambda v=on: island.set_setting("auto_startup", not v))
        elif self.tab == 1:                                  # ---- Cá nhân hóa (được đưa lên) ----
            cur_color = tuple(st.get("bg_color", [4, 6, 10]))
            cur_op = int(st.get("bg_opacity", 100))

            # 1. Màu nền
            self._row(s, 86, "Màu nền", "Chọn màu sắc chủ đạo cho Dynamic Island và Cài đặt", pad)

            # Nút Tùy chọn màu căn thẳng mép phải `right` (thẳng hàng nút tắt)
            custom_btn_w = 110
            custom_btn = pygame.Rect(right - custom_btn_w, 141, custom_btn_w, 32)
            is_custom = all(list(c) != list(cur_color) for _, c in PRESET_COLORS)
            btn_bg = th["panel_hover"] if custom_btn.collidepoint(mouse) else th["panel"]
            draw_aa_round_rect(s, btn_bg, custom_btn, 16)
            border_col = th["accent"] if is_custom else th["div"]
            draw_aa_round_rect(s, border_col, custom_btn, 16, width=2 if is_custom else 1)
            if is_custom:
                draw_aa_circle(s, cur_color, (custom_btn.left + 16, custom_btn.centery), 7)
                draw_text(s, self.f_small, "Tùy chọn", th["main"], midleft=(custom_btn.left + 28, custom_btn.centery - 1))
            else:
                draw_text(s, self.f_small, "+ Tùy chọn", th["main"], center=(custom_btn.centerx, custom_btn.centery - 1))
            self._hit(custom_btn, origin, self._open_color_picker)

            # Các nút màu mặc định (tươi sáng)
            cx = pad + 16
            for name, c in PRESET_COLORS:
                cr = pygame.Rect(cx - 15, 142, 30, 30)
                is_selected = list(c) == list(cur_color)
                draw_aa_circle(s, c, (cx, 157), 14)
                draw_aa_circle(s, th["div"], (cx, 157), 14, width=1)
                if is_selected:
                    draw_aa_circle(s, th["main"], (cx, 157), 17, width=2)
                    draw_aa_circle(s, WHITE, (cx, 157), 4)
                elif cr.collidepoint(mouse):
                    draw_aa_circle(s, th["main"], (cx, 157), 16, width=1)
                self._hit(cr, origin, lambda col=c: island.set_setting("bg_color", list(col)))
                cx += 38

            # Đường phân cách
            pygame.draw.line(s, th["div"], (pad, 198), (right, 198), 1)

            # 2. Độ trong suốt của nền
            self._row(s, 214, "Độ trong suốt nền", f"Mức độ trong suốt hiện tại: {cur_op}% (nội dung sắc nét 100%)", pad)

            # Nhóm nút chọn nhanh độ trong suốt (100%, 85%, 70%, 50%) căn thẳng mép phải `right` và nhích lên ngang với dòng chữ chính
            op_choices = ((100, "100%"), (85, "85%"), (70, "70%"), (50, "50%"))
            seg_w = 54
            seg_x = right - seg_w * 4
            self._seg(s, origin, mouse, seg_x, 212, op_choices, cur_op,
                      lambda v: island.set_setting("bg_opacity", v), seg_w, h=28)

            # Thanh trượt liên tục (Slider) từ 20% đến 100%
            slider_w = right - pad
            slider_y = 276
            slider_rect = pygame.Rect(pad - 12, slider_y - 12, slider_w + 24, 30)
            draw_aa_round_rect(s, th["div"], (pad, slider_y, slider_w, 6), 3)
            prog = max(0.0, min(1.0, (cur_op - 20) / 80))
            fill_w = int(slider_w * prog)
            draw_aa_round_rect(s, th["accent"], (pad, slider_y, fill_w, 6), 3)
            thumb_x = pad + fill_w
            draw_aa_circle(s, WHITE, (thumb_x, slider_y + 3), 9)

            draw_text(s, self.f_tiny, "20% (Trong suốt)", th["sub"], topleft=(pad, slider_y + 12))
            draw_text(s, self.f_tiny, "100% (Đục hoàn toàn)", th["sub"], topright=(right, slider_y + 12))

            # Cho phép kéo / bấm thanh trượt trực tiếp (bao gồm cả điểm 100% ở mép phải)
            if mouse_down(1) and slider_rect.collidepoint(mouse):
                rel_x = max(0.0, min(float(slider_w), float(mouse[0] - pad)))
                new_op = int(round(20 + (rel_x / slider_w) * 80))
                new_op = max(20, min(100, new_op))
                if new_op != cur_op:
                    island.set_setting("bg_opacity", new_op)
            self._hit(slider_rect, origin, lambda: None)

            # 3. Khối xem trước tai thỏ (Live Preview)
            preview_r = pygame.Rect(0, 0, 200, 36)
            preview_r.center = (pad + (right - pad) // 2, 362)
            draw_aa_round_rect(s, cur_color, preview_r, 18)
            draw_aa_round_rect(s, th["div"], preview_r, 18, width=1)
            draw_aa_circle(s, (48, 209, 88), (preview_r.left + 20, preview_r.centery), 6, width=2)
            draw_text(s, self.f_small, "22:47", th["main"], center=preview_r.center)
            for si, sh in enumerate((6, 12, 8, 14, 7)):
                sbar = pygame.Rect(0, 0, 2, sh)
                sbar.center = (preview_r.right - 28 + si * 4, preview_r.centery)
                draw_aa_round_rect(s, th["main"], sbar, 1)
            draw_text(s, self.f_tiny, "Xem trước màu sắc tai thỏ", th["sub"], center=(preview_r.centerx, 392))

        elif self.tab == 2:                                  # ---- Lịch (được đưa xuống) ----
            # Cài đặt hiển thị cơ bản (giãn dòng thoáng đãng)
            seg1_w = 96
            self._row(s, 88, "Tuần bắt đầu từ", "Thứ tự các cột khi xem lịch theo tuần", pad)
            self._seg(s, origin, mouse, right - seg1_w * 2, 90, ((0, "Thứ Hai"), (6, "Chủ Nhật")), st["week_start"],
                      lambda k: island.set_setting("week_start", k), seg1_w)

            seg2_w = 126
            self._row(s, 162, "Kiểu xem lịch", "Xem 7 ngày theo tuần hoặc lấy hôm nay làm tâm", pad)
            # Đưa nút lên trên 5px (164 -> 159) để căn ngang với dòng tiêu đề, không đè lên dòng chữ phụ bên dưới
            self._seg(s, origin, mouse, right - seg2_w * 2, 159,
                      (("week", "Theo tuần"), ("7days_center", "Hôm nay ở giữa")),
                      st.get("cal_view_mode", "week"),
                      lambda k: island.set_setting("cal_view_mode", k), seg2_w)

            self._row(s, 236, "Chấm báo sự kiện", "Chấm màu dưới mỗi ngày có sự kiện", pad)
            on = bool(st.get("show_event_dots", True))
            self._switch(s, origin, mouse, right, 238, on, lambda v=on: island.set_setting("show_event_dots", not v))

            # Đường phân cách phần Quản lý Lịch
            pygame.draw.line(s, th["div"], (pad, 292), (right, 292), 1)

            # ---- Header Quản lý Lịch Google Calendar ----
            y_cal = 306
            draw_text(s, self.f_text, "Lịch Google Calendar", th["main"], midleft=(pad, y_cal + 13))

            gcal = island.gcal
            cals = gcal.get_calendars() if gcal.state != "disconnected" else []

            # Nút thêm Link iCal ở góc phải header
            add_btn = pygame.Rect(right - 105, y_cal, 105, 26)
            add_hover = add_btn.collidepoint(mouse)
            draw_aa_round_rect(s, (30, 145, 255) if add_hover else th["accent"], add_btn, 13)
            draw_text(s, self.f_small, "+ Link iCal", WHITE, center=(add_btn.centerx, add_btn.centery - 1))
            def _open_input():
                self.input_active = True
                pygame.key.start_text_input()
            self._hit(add_btn, origin, _open_input)

            # ---- Danh sách các Lịch đã thêm ----
            y_list = 348
            if not cals:
                empty_box = pygame.Rect(pad, y_list, right - pad, 72)
                draw_aa_round_rect(s, th["panel"], empty_box, 10)
                draw_aa_round_rect(s, th["div"], empty_box, 10, width=1)
                draw_text(s, self.f_small, "Chưa có lịch nào được kết nối", th["sub"],
                          center=(empty_box.centerx, empty_box.y + 24))
                draw_text(s, self.f_tiny, "Nhấn \"+ Link iCal\" để đồng bộ lịch từ Google Calendar", th["dim"],
                          center=(empty_box.centerx, empty_box.y + 46))
            else:
                for i, cal in enumerate(cals[:3]):
                    ry = y_list + i * 34
                    row = pygame.Rect(pad, ry, right - pad, 30)
                    row_hover = row.collidepoint(mouse)
                    draw_aa_round_rect(s, th["panel_hover"] if row_hover else th["panel"], row, 8)

                    draw_aa_circle(s, cal["color"], (row.x + 14, row.centery), 5)

                    is_url = cal["id"] in gcal.ical_urls
                    tag_txt = "Link" if is_url else "File"
                    tag_bg = (20, 48, 80) if is_url else th["panel_hover"]
                    tag_col = (110, 180, 255) if is_url else th["sub"]
                    tag_r = pygame.Rect(row.x + 26, row.centery - 9, 36, 18)
                    draw_aa_round_rect(s, tag_bg, tag_r, 4)
                    draw_text(s, self.f_tiny, tag_txt, tag_col, center=tag_r.center)

                    draw_text(s, self.f_small, fit_text(self.f_small, cal["name"], 280), th["main"],
                              midleft=(row.x + 70, row.centery))

                    del_r = pygame.Rect(row.right - 54, row.centery - 11, 46, 22)
                    del_hover = del_r.collidepoint(mouse)
                    del_bg = (70, 22, 24) if del_hover else (45, 18, 20)
                    draw_aa_round_rect(s, del_bg, del_r, 11)
                    draw_text(s, self.f_tiny, "Xóa", CLOSE_RED_HOVER if del_hover else CLOSE_RED, center=del_r.center)
                    self._hit(del_r, origin, lambda cid=cal["id"]: island.gcal.remove_calendar(cid))

                if len(cals) > 3:
                    draw_text(s, self.f_tiny, f"... và còn {len(cals) - 3} lịch khác", th["dim"],
                              topleft=(pad + 4, y_list + 3 * 34 + 4))

            # ---- Trạng thái kết nối & Nút Xóa tất cả ----
            y_stat = 456
            st_conn = gcal.state
            st_color = (48, 209, 88) if st_conn == "connected" else ((255, 159, 10) if st_conn == "connecting" else th["dim"])
            st_txt = f"Đã kết nối • {len(cals)} lịch" if st_conn == "connected" else ("Đang kết nối..." if st_conn == "connecting" else "Chưa kết nối")
            draw_aa_circle(s, st_color, (pad + 6, y_stat), 4)
            draw_text(s, self.f_tiny, st_txt, th["sub"], midleft=(pad + 18, y_stat))

            if cals:
                logout_r = pygame.Rect(0, 0, 84, 22)
                logout_r.midright = (right, y_stat)
                lb_hover = logout_r.collidepoint(mouse)
                lb_bg = (60, 20, 22) if lb_hover else (38, 16, 18)
                draw_aa_round_rect(s, lb_bg, logout_r, 11)
                draw_text(s, self.f_tiny, "Xóa tất cả", CLOSE_RED_HOVER if lb_hover else CLOSE_RED, center=logout_r.center)
                self._hit(logout_r, origin, island.gcal.disconnect)

        elif self.tab == 3:                                  # ---- Thông tin & Cập nhật ----
            upd = island.updater
            y_info = 88

            # 1. Hộp hiển thị phiên bản hiện tại & thông tin app
            info_box = pygame.Rect(pad, y_info, right - pad, 106)
            draw_aa_round_rect(s, th["panel"], info_box, 14)
            draw_aa_round_rect(s, th["div"], info_box, 14, width=1)

            # Icon hoặc Logo nhỏ
            logo_r = pygame.Rect(info_box.x + 18, info_box.centery - 24, 48, 48)
            draw_aa_round_rect(s, th["accent"], logo_r, 14)
            draw_text(s, self.f_title, "DN", WHITE, center=logo_r.center)

            draw_text(s, self.f_title, "Dynamic Notch cho Windows", th["main"], topleft=(logo_r.right + 18, info_box.y + 18))
            draw_text(s, self.f_small, f"Phiên bản hiện tại: V{APP_VERSION}", th["sub"], topleft=(logo_r.right + 18, info_box.y + 48))
            draw_text(s, self.f_tiny, f"GitHub: {GITHUB_REPO}", th["dim"], topleft=(logo_r.right + 18, info_box.y + 72))

            # 2. Tùy chọn Tự động cập nhật (giãn dòng thoáng)
            y_opt = y_info + 134
            self._row(s, y_opt, "Cập nhật tự động", "Tự động kiểm tra bản phát hành mới khi mở ứng dụng", pad)
            on = bool(st.get("auto_update", True))
            self._switch(s, origin, mouse, right, y_opt + 4, on, lambda v=on: island.set_setting("auto_update", not v))

            # Đường kẻ phân cách
            pygame.draw.line(s, th["div"], (pad, y_opt + 72), (right, y_opt + 72), 1)

            # 3. Trạng thái cập nhật và Nút kiểm tra
            y_check = y_opt + 92
            draw_text(s, self.f_text, "Trạng thái cập nhật", th["main"], topleft=(pad, y_check))

            status_msg = upd.message or "Phiên bản mới nhất đã được cài đặt"
            msg_color = th["sub"]
            if upd.status == "update_available":
                msg_color = (48, 209, 88)  # Xanh lá
            elif upd.status == "error":
                msg_color = RED
            elif upd.status in ("checking", "downloading"):
                msg_color = th["accent"]
            elif upd.status == "up_to_date":
                msg_color = th["dim"]

            draw_text(s, self.f_small, status_msg, msg_color, topleft=(pad, y_check + 33))

            # Nút Kiểm tra cập nhật / Tải bản cập nhật
            btn_w = 170
            chk_btn = pygame.Rect(right - btn_w, y_check + 10, btn_w, 34)
            chk_hover = chk_btn.collidepoint(mouse)

            if upd.status == "update_available":
                # Chỉ hiện nút Tải & Cài đặt khi có phiên bản mới hơn trên GitHub
                draw_aa_round_rect(s, (48, 209, 88) if chk_hover else (38, 180, 75), chk_btn, 17)
                draw_text(s, self.f_small, f"Tải & Cài đặt V{upd.latest_version}", WHITE, center=(chk_btn.centerx, chk_btn.centery - 1))
                self._hit(chk_btn, origin, upd.download_and_install)
            elif upd.status == "up_to_date":
                # Phiên bản trên máy đã là mới nhất hoặc lớn hơn: nút bị vô hiệu hóa
                draw_aa_round_rect(s, th["panel"], chk_btn, 17)
                draw_aa_round_rect(s, th["div"], chk_btn, 17, width=1)
                draw_text(s, self.f_small, "Đã cập nhật", th["dim"], center=(chk_btn.centerx, chk_btn.centery - 1))
                # Không gắn self._hit để vô hiệu hóa click
            elif upd.status == "downloading":
                draw_aa_round_rect(s, th["panel"], chk_btn, 17)
                draw_text(s, self.f_small, f"Đang tải {upd.download_progress}%", th["accent"], center=(chk_btn.centerx, chk_btn.centery - 1))
            elif upd.status == "checking":
                draw_aa_round_rect(s, th["panel"], chk_btn, 17)
                draw_text(s, self.f_small, "Đang kiểm tra...", th["sub"], center=(chk_btn.centerx, chk_btn.centery - 1))
            else:
                # Trạng thái ban đầu (idle) hoặc lỗi: cho phép bấm kiểm tra
                draw_aa_round_rect(s, (30, 145, 255) if chk_hover else th["accent"], chk_btn, 17)
                draw_text(s, self.f_small, "Kiểm tra cập nhật", WHITE, center=(chk_btn.centerx, chk_btn.centery - 1))
                self._hit(chk_btn, origin, lambda: upd.check_for_updates(auto_download=False))

        # ---- Dropdown menu sổ xuống của Hiện giây (vẽ đè lên trên các thành phần khác) ----
        if self.tab == 0 and self.dropdown_active:
            sec_mode = st.get("seconds_mode")
            if sec_mode is None:
                sec_mode = "expand" if st.get("show_seconds", True) else "none"

            dd_w = 152
            item_h = 30
            menu_x = right - dd_w
            menu_y = y0 + step + 32
            menu_h = item_h * len(SECONDS_CHOICES)
            menu_rect = pygame.Rect(menu_x, menu_y, dd_w, menu_h)

            # Đổ bóng nhẹ và nền menu
            draw_aa_round_rect(s, (24, 24, 28) if not th["is_light"] else (245, 245, 250), menu_rect, 6)
            draw_aa_round_rect(s, th["div"], menu_rect, 6, width=1)

            for idx, (m_key, m_title) in enumerate(SECONDS_CHOICES):
                it_r = pygame.Rect(menu_x + 2, menu_y + 2 + idx * item_h, dd_w - 4, item_h - 4)
                it_hover = it_r.collidepoint(mouse)
                it_on = m_key == sec_mode

                if it_on:
                    draw_aa_round_rect(s, th["panel_hover"], it_r, 4)
                    # Vạch màu xanh bên trái mục đang chọn giống Windows 11 (ảnh 2)
                    draw_aa_round_rect(s, th["accent"], (it_r.left + 3, it_r.top + 5, 3, it_r.height - 10), 1.5)
                elif it_hover:
                    draw_aa_round_rect(s, th["panel"], it_r, 4)

                draw_text(s, self.f_small, m_title, WHITE if it_on else th["main"], midleft=(it_r.left + 14, it_r.centery - 1))

                def _pick_mode(val=m_key):
                    island.set_setting("seconds_mode", val)
                    self.dropdown_active = False

                self._hit(it_r, origin, _pick_mode)

        draw_text(s, self.f_tiny, "Thay đổi được lưu tự động", th["dim"], midbottom=(SET_W // 2, SET_H - 12))

        # ---- Popup Modal: Thêm Lịch Google (iCal) ----
        if self.input_active or self.input_anim > 0.005:
            anim = self.input_anim
            overlay_alpha = int(190 * anim)
            overlay = pygame.Surface((SET_W, SET_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, overlay_alpha))
            s.blit(overlay, (0, 0))

            if self.input_active:
                def _cancel_inp():
                    self.input_active = False
                    pygame.key.stop_text_input()
                self._hit(pygame.Rect(0, 0, SET_W, SET_H), origin, _cancel_inp)

            scale = 0.92 + 0.08 * anim
            base_w = min(590, SET_W - 80)
            base_h = 175
            box_w = int(base_w * scale)
            box_h = int(base_h * scale)
            box = pygame.Rect(0, 0, box_w, box_h)
            box.center = (SET_W // 2, SET_H // 2)

            modal_surf = pygame.Surface((box.width, box.height), pygame.SRCALPHA)
            modal_rect = pygame.Rect(0, 0, box.width, box.height)
            draw_aa_round_rect(modal_surf, (24, 24, 28), modal_rect, 16)
            draw_aa_round_rect(modal_surf, (60, 60, 68), modal_rect, 16, width=1)

            draw_text(modal_surf, self.f_text, "Thêm Lịch Google (iCal)", WHITE, topleft=(24, 18))
            draw_text(modal_surf, self.f_tiny, "Google Calendar > Cài đặt lịch > Tích hợp lịch > Địa chỉ bí mật ở định dạng iCal", GREY,
                      topleft=(24, 44))

            inp = pygame.Rect(24, 70, modal_rect.width - 48 - 72, 32)
            draw_aa_round_rect(modal_surf, (36, 36, 42), inp, 8)
            draw_aa_round_rect(modal_surf, ACCENT, inp, 8, width=1)

            paste_r = pygame.Rect(inp.right + 8, 70, 64, 32)
            paste_hover = paste_r.move(box.topleft).collidepoint(mouse) if self.input_active else False
            draw_aa_round_rect(modal_surf, PANEL_HOVER if paste_hover else PANEL, paste_r, 8)
            draw_aa_round_rect(modal_surf, (60, 60, 68), paste_r, 8, width=1)
            draw_text(modal_surf, self.f_small, "Dán", WHITE, center=paste_r.center)
            if self.input_active:
                def _do_paste():
                    clip = get_clipboard_text().strip()
                    if clip:
                        self.input_url += clip
                self._hit(paste_r.move(box.topleft), origin, _do_paste)

            if self.input_url:
                display_url = self.input_url[-48:] if len(self.input_url) > 48 else self.input_url
                t_surf = self.f_small.render(display_url, True, WHITE)
                t_rect = t_surf.get_rect(midleft=(inp.x + 10, inp.centery - 1))
                modal_surf.blit(t_surf, t_rect)
                if int(time.monotonic() * 2) % 2 == 0:
                    cur_x = min(inp.right - 8, t_rect.right + 2)
                    pygame.draw.line(modal_surf, WHITE, (cur_x, inp.centery - 7), (cur_x, inp.centery + 7), 2)
            else:
                draw_text(modal_surf, self.f_small, "Dán link hoặc bấm nút Dán bên cạnh...", DIM, midleft=(inp.x + 10, inp.centery - 1))

            cancel_r = pygame.Rect(modal_rect.right - 170, modal_rect.bottom - 42, 72, 28)
            c_hover = cancel_r.move(box.topleft).collidepoint(mouse) if self.input_active else False
            draw_aa_round_rect(modal_surf, PANEL_HOVER if c_hover else PANEL, cancel_r, 14)
            draw_text(modal_surf, self.f_small, "Hủy", GREY, center=cancel_r.center)
            if self.input_active:
                def _cancel():
                    self.input_active = False
                    pygame.key.stop_text_input()
                self._hit(cancel_r.move(box.topleft), origin, _cancel)

            ok_r = pygame.Rect(modal_rect.right - 88, modal_rect.bottom - 42, 68, 28)
            ok_hover = ok_r.move(box.topleft).collidepoint(mouse) if self.input_active else False
            draw_aa_round_rect(modal_surf, (30, 145, 255) if ok_hover else ACCENT, ok_r, 14)
            draw_text(modal_surf, self.f_small, "Thêm", WHITE, center=ok_r.center)
            if self.input_active:
                self._hit(ok_r.move(box.topleft), origin, self._submit_ical_url)

            if anim < 0.999:
                modal_surf.set_alpha(int(255 * anim))
            s.blit(modal_surf, box.topleft)

        # ---- Popup Modal: Chọn màu tùy chỉnh ----
        if self.color_modal_anim > 0.005 or self.color_modal_active:
            anim = self.color_modal_anim
            overlay_alpha = int(190 * anim)
            overlay = pygame.Surface((SET_W, SET_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, overlay_alpha))
            s.blit(overlay, (0, 0))

            scale = 0.92 + 0.08 * anim
            base_w = min(540, SET_W - 60)
            base_h = 320
            box_w = int(base_w * scale)
            box_h = int(base_h * scale)
            box = pygame.Rect(0, 0, box_w, box_h)
            box.center = (SET_W // 2, SET_H // 2)

            if self.color_modal_active:
                # 1. Bắt click ngoài box -> hủy/đóng modal
                def _on_backdrop_click():
                    if not box.collidepoint(mouse):
                        self._cancel_color_picker()
                self._hit(pygame.Rect(0, 0, SET_W, SET_H), origin, _on_backdrop_click)
                # 2. Bắt click trong box -> chặn rơi xuống backdrop hoặc các nút bên dưới
                self._hit(box, origin, lambda: None)

            modal_surf = pygame.Surface((box.width, box.height), pygame.SRCALPHA)
            modal_rect = pygame.Rect(0, 0, box.width, box.height)
            draw_aa_round_rect(modal_surf, (24, 24, 28), modal_rect, 16)
            draw_aa_round_rect(modal_surf, (60, 60, 68), modal_rect, 16, width=1)

            draw_text(modal_surf, self.f_text, "Chọn màu nền tùy chỉnh", WHITE, topleft=(24, 18))
            draw_text(modal_surf, self.f_tiny, "Kéo các thanh trượt RGB hoặc chọn nhanh từ bảng màu gợi ý", GREY,
                      topleft=(24, 44))

            # Nút X ở góc trên bên phải
            close_btn = pygame.Rect(modal_rect.right - 36, 16, 22, 22)
            c_hover = close_btn.move(box.topleft).collidepoint(mouse) if self.color_modal_active else False
            x_icon = make_nav_icon("close", 16, WHITE if c_hover else GREY)
            modal_surf.blit(x_icon, x_icon.get_rect(center=close_btn.center))
            if self.color_modal_active:
                self._hit(close_btn.move(box.topleft), origin, self._cancel_color_picker)

            cur_rgb = (int(self.color_picker_rgb[0]), int(self.color_picker_rgb[1]), int(self.color_picker_rgb[2]))

            # Khối xem trước màu sắc (Live Preview) bên trái
            preview_r = pygame.Rect(24, 76, 110, 68)
            draw_aa_round_rect(modal_surf, cur_rgb, preview_r, 12)
            draw_aa_round_rect(modal_surf, (80, 80, 90), preview_r, 12, width=1)
            hex_txt = f"#{cur_rgb[0]:02X}{cur_rgb[1]:02X}{cur_rgb[2]:02X}"
            draw_text(modal_surf, self.f_small, hex_txt, WHITE, center=(preview_r.centerx, preview_r.bottom + 15))
            rgb_txt = f"RGB({cur_rgb[0]}, {cur_rgb[1]}, {cur_rgb[2]})"
            draw_text(modal_surf, self.f_tiny, rgb_txt, (150, 150, 155), center=(preview_r.centerx, preview_r.bottom + 32))

            # 3 Thanh trượt R, G, B bên phải
            slider_start_x = 158
            slider_w = modal_rect.width - slider_start_x - 24
            channels = (
                (0, "R", (255, 69, 58), 74),
                (1, "G", (48, 209, 88), 112),
                (2, "B", (10, 132, 255), 150),
            )
            track_w = slider_w - 68
            for ch_idx, ch_name, ch_col, ch_y in channels:
                draw_text(modal_surf, self.f_small, ch_name, ch_col, midleft=(slider_start_x, ch_y + 8))
                track_x = slider_start_x + 24
                track_y = ch_y + 5
                track_h = 6
                track_rect = pygame.Rect(track_x, track_y, track_w, track_h)
                ch_val = self.color_picker_rgb[ch_idx]
                prog = max(0.0, min(1.0, ch_val / 255.0))
                fill_w = int(track_w * prog)
                draw_aa_round_rect(modal_surf, (45, 45, 52), track_rect, 3)
                draw_aa_round_rect(modal_surf, ch_col, (track_x, track_y, fill_w, track_h), 3)
                thumb_x = track_x + fill_w
                draw_aa_circle(modal_surf, WHITE, (thumb_x, track_y + 3), 8)
                draw_text(modal_surf, self.f_small, str(ch_val), WHITE, midleft=(track_x + track_w + 14, track_y + 3))

                slider_hit = pygame.Rect(track_x - 12, track_y - 12, track_w + 24, 30)
                win_slider_hit = slider_hit.move(box.topleft)
                if self.color_modal_active:
                    def _on_slider_click(ci=ch_idx, tx=track_x, tw=track_w):
                        self._dragging_slider = ci
                        rel = max(0.0, min(float(tw), float(mouse[0] - (box.left + tx))))
                        self.color_picker_rgb[ci] = int(round((rel / tw) * 255.0))
                    self._hit(win_slider_hit, origin, _on_slider_click)

                    is_down = mouse_down(1)
                    if is_down and (self._dragging_slider == ch_idx or (self._dragging_slider is None and win_slider_hit.collidepoint(mouse))):
                        self._dragging_slider = ch_idx
                        rel_x = max(0.0, min(float(track_w), float(mouse[0] - (box.left + track_x))))
                        self.color_picker_rgb[ch_idx] = int(round((rel_x / track_w) * 255.0))

            # Bảng màu gợi ý 14 màu
            draw_text(modal_surf, self.f_tiny, "Gợi ý màu sắc:", (160, 160, 165), topleft=(24, 194))
            pal_y = 222
            n_pal = len(PALETTE_COLORS)
            pal_step = (modal_rect.width - 48) / n_pal
            for p_i, p_col in enumerate(PALETTE_COLORS):
                p_cx = int(24 + pal_step * (p_i + 0.5))
                is_cur = list(p_col) == list(cur_rgb)
                draw_aa_circle(modal_surf, p_col, (p_cx, pal_y), 11)
                draw_aa_circle(modal_surf, (70, 70, 78), (p_cx, pal_y), 11, width=1)
                if is_cur:
                    draw_aa_circle(modal_surf, WHITE, (p_cx, pal_y), 13, width=2)
                if self.color_modal_active:
                    p_hit = pygame.Rect(p_cx - 13, pal_y - 13, 26, 26).move(box.topleft)
                    self._hit(p_hit, origin, lambda c=p_col: self._set_palette_color(c))

            # Nút Hủy và Áp dụng
            cancel_r = pygame.Rect(modal_rect.right - 180, modal_rect.bottom - 44, 76, 28)
            can_hover = cancel_r.move(box.topleft).collidepoint(mouse) if self.color_modal_active else False
            draw_aa_round_rect(modal_surf, PANEL_HOVER if can_hover else PANEL, cancel_r, 14)
            draw_text(modal_surf, self.f_small, "Hủy", GREY, center=cancel_r.center)
            if self.color_modal_active:
                self._hit(cancel_r.move(box.topleft), origin, self._cancel_color_picker)

            ok_r = pygame.Rect(modal_rect.right - 92, modal_rect.bottom - 44, 76, 28)
            ok_hover = ok_r.move(box.topleft).collidepoint(mouse) if self.color_modal_active else False
            draw_aa_round_rect(modal_surf, (30, 145, 255) if ok_hover else ACCENT, ok_r, 14)
            draw_text(modal_surf, self.f_small, "Áp dụng", WHITE, center=ok_r.center)
            if self.color_modal_active:
                self._hit(ok_r.move(box.topleft), origin, self._apply_color_picker)

            if anim < 0.999:
                modal_surf.set_alpha(int(255 * anim))
            s.blit(modal_surf, box.topleft)
