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
    draw_aa_circle, draw_aa_round_rect
)

# Thời lượng từng pha (giây): tách giọt -> rơi -> phóng to thành cửa sổ -> nội dung hiện dần
T_NECK, T_FALL, T_GROW, T_FADE = 0.20, 0.30, 0.34, 0.16
T_TOTAL = T_NECK + T_FALL + T_GROW + T_FADE
DROP_R = 11                                  # bán kính giọt nước khi rơi
WIN_RADIUS = 26                              # bo góc cửa sổ cài đặt
MARGIN = 48                                  # lề trong suốt quanh cửa sổ (chừa chỗ cho hiệu ứng vọt quá)

T_SHRINK = 0.22                              # đóng: nội dung ẩn + cửa sổ co lại thành giọt
T_RISE = 0.42                                # đóng: giọt bay lên, đè qua island rồi ra khỏi mép trên màn hình
# Thứ tự tabs: Chung, Cá nhân hóa (đưa lên), Lịch (đưa xuống), Thông tin (neo dưới cùng)
TOP_TABS = ("Chung", "Cá nhân hóa", "Lịch")
BOTTOM_TAB = "Thông tin"
TABS = ("Chung", "Cá nhân hóa", "Lịch", "Thông tin")

RING_CHOICES = (("auto", "Tự động"), ("battery", "Pin"), ("music", "Nhạc"))
PRESET_COLORS = (
    ("Đen", (4, 6, 10)),
    ("Đỏ", (235, 55, 65)),
    ("Xanh dương", (30, 130, 250)),
    ("Xanh lá", (48, 195, 85)),
    ("Hồng", (240, 70, 155)),
    ("Cam", (255, 135, 35)),
    ("Tím", (165, 80, 235)),
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
        self.f_title = pygame.font.SysFont(font_family, 24, bold=True)
        self.f_text = pygame.font.SysFont(font_family, 17, bold=True)
        self.f_small = pygame.font.SysFont(font_family, 14, bold=True)
        self.f_tiny = pygame.font.SysFont(font_family, 12, bold=True)
        self.tab = 0                                         # tab đang chọn: 0 Chung, 1 Lịch
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

    # ------------------------------ Trạng thái ------------------------------
    @property
    def active(self):
        return self.state != "closed"

    @property
    def animating(self):
        return self.state in ("opening", "closing")

    def win_rect(self):
        r = pygame.Rect(0, 0, SET_W, SET_H)
        r.center = (self.ov_w // 2, self.cy)
        return r

    def covers(self, sx, sy):
        """Điểm (toạ độ màn hình) có nằm trên cửa sổ cài đặt đã hiện đầy đủ không (để island bỏ qua chuột ở đó)."""
        if self.state != "open":
            return False
        return self.win_rect().move(self.x, self.y).collidepoint(sx, sy)

    def open(self, island_bottom):
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
        if left and not self.prev_l and self.state == "open":
            for rect, fn in reversed(self.hits):
                if rect.collidepoint(self.mouse):
                    fn()
                    break
        self.prev_l = left

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
        """Nhóm nút chọn 1 trong nhiều (segmented control) với góc trên-trái (x, y)."""
        th = self.island.theme()
        draw_aa_round_rect(s, th["panel"], (x, y, seg_w * len(choices), h), h // 2)
        for i, (key, label) in enumerate(choices):
            r = pygame.Rect(x + i * seg_w, y, seg_w, h)
            on = current == key
            if on:
                draw_aa_round_rect(s, th["accent"], r.inflate(-4, -4), (h - 4) // 2)
            elif r.collidepoint(mouse):
                draw_aa_round_rect(s, th["panel_hover"], r.inflate(-4, -4), (h - 4) // 2)
            draw_text(s, self.f_small, label, WHITE if on else th["sub"], center=r.center)
            self._hit(r, origin, lambda k=key: on_pick(k))

    def _switch(self, s, origin, mouse, right, y, on, on_toggle):
        th = self.island.theme()
        sw = pygame.Rect(right - 52, y, 52, 28)
        off_col = th["panel_hover"] if not th["is_light"] else (180, 180, 190)
        draw_aa_round_rect(s, th["accent"] if on else off_col, sw, 14)
        draw_aa_circle(s, WHITE, (sw.right - 14 if on else sw.left + 14, sw.centery), 11)
        self._hit(sw.inflate(8, 8), origin, on_toggle)

    def _row(self, s, y, title, sub, pad):
        th = self.island.theme()
        draw_text(s, self.f_text, title, th["main"], topleft=(pad, y))
        draw_text(s, self.f_small, sub, th["sub"], topleft=(pad, y + 25))

    def handle_event(self, e):
        """Xử lý phím khi ô nhập link iCal đang mở."""
        if not self.input_active or self.state != "open":
            return
        if e.type == pygame.KEYDOWN:
            # Hỗ trợ Ctrl + V dán link từ clipboard
            if e.key == pygame.K_v and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                clip = get_clipboard_text().strip()
                if clip:
                    self.input_url += clip
                return
            if e.key == pygame.K_BACKSPACE:
                self.input_url = self.input_url[:-1]
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._submit_ical_url()
            elif e.key == pygame.K_ESCAPE:
                self.input_active = False
                self.input_url = ""
                pygame.key.stop_text_input()
        elif e.type == pygame.TEXTINPUT:
            if not (pygame.key.get_mods() & pygame.KMOD_CTRL):
                self.input_url += e.text

    def _submit_ical_url(self):
        url = self.input_url.strip()
        self.input_active = False
        self.input_url = ""
        pygame.key.stop_text_input()
        if url:
            import threading
            threading.Thread(target=lambda: self.island.gcal.import_ical_url(url), daemon=True).start()

    def _pick_ics_file(self):
        import threading
        def _run():
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                p = filedialog.askopenfilename(
                    title="Chọn file lịch .ics hoặc zip",
                    filetypes=[("Lịch iCal / Zip", "*.ics;*.zip"), ("All Files", "*.*")]
                )
                root.destroy()
                if p:
                    if p.lower().endswith(".zip"):
                        self.island.gcal._unpack_zip(p)
                    else:
                        self.island.gcal.import_ics_file(p)
            except Exception as ex:
                print("[Dynamic Island] Lỗi chọn file:", ex)
        threading.Thread(target=_run, daemon=True).start()

    def _pick_custom_color(self):
        """Mở hộp thoại chọn màu tùy chỉnh từ hệ điều hành."""
        import threading
        def _run():
            try:
                import tkinter as tk
                from tkinter import colorchooser
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                cur = tuple(self.island.settings.get("bg_color", [4, 6, 10]))
                initial = f"#{cur[0]:02x}{cur[1]:02x}{cur[2]:02x}"
                color = colorchooser.askcolor(color=initial, title="Chọn màu nền cho Dynamic Island", parent=root)
                root.destroy()
                if color and color[0]:
                    rgb = [int(x) for x in color[0]]
                    self.island.set_setting("bg_color", rgb)
            except Exception as ex:
                print("[Dynamic Island] Lỗi chọn màu:", ex)
        threading.Thread(target=_run, daemon=True).start()

    def _switch_tab(self, i):
        """Chuyển tab; nếu ô nhập iCal đang mở thì đóng lại trước."""
        if self.input_active:
            self.input_active = False
            self.input_url = ""
            pygame.key.stop_text_input()
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
        for i, name in enumerate(TOP_TABS):
            r = pygame.Rect(pad_l, tab_y + i * 46, sidebar_w, 38)
            on = i == self.tab
            bg = th["accent"] if on else (th["panel_hover"] if r.collidepoint(mouse) else th["panel"])
            draw_aa_round_rect(s, bg, r, 12)
            draw_text(s, self.f_text, name, WHITE if on else th["sub"], midleft=(r.left + 16, r.centery))
            self._hit(r, origin, lambda i=i: self._switch_tab(i))

        # Tab "Thông tin" neo ở dưới đáy của sidebar:
        # Khoảng cách tới cạnh đáy (SET_H - info_r.bottom) bằng chính xác khoảng cách tới cạnh trái (pad_l = 28px)
        info_idx = 3
        info_r = pygame.Rect(pad_l, SET_H - pad_l - 38, sidebar_w, 38)
        info_on = self.tab == info_idx
        info_bg = th["accent"] if info_on else (th["panel_hover"] if info_r.collidepoint(mouse) else th["panel"])
        draw_aa_round_rect(s, info_bg, info_r, 12)
        draw_text(s, self.f_text, BOTTOM_TAB, WHITE if info_on else th["sub"], midleft=(info_r.left + 16, info_r.centery))
        self._hit(info_r, origin, lambda: self._switch_tab(info_idx))

        # Đường phân cách dọc giữa Sidebar và vùng Nội dung
        div_x = pad_l + sidebar_w + 12
        pygame.draw.line(s, th["div"], (div_x, 86), (div_x, SET_H - pad_l), 1)

        # Vùng nội dung tab bên phải
        pad = content_left
        y0, step = 92, 70
        if self.tab == 0:                                    # ---- Chung ----
            self._row(s, y0, "Vòng tròn bên trái", "Hiển thị % pin hoặc tiến độ bài nhạc", pad)
            self._seg(s, origin, mouse, right - 76 * 3, y0 + 2, RING_CHOICES, st["ring_source"],
                      lambda k: island.set_setting("ring_source", k), 76)

            self._row(s, y0 + step, "Hiện giây khi mở rộng", "Giờ dạng HH:MM:SS khi island mở ra", pad)
            on = bool(st["show_seconds"])
            self._switch(s, origin, mouse, right, y0 + step + 4, on, lambda v=on: island.set_setting("show_seconds", not v))

            self._row(s, y0 + 2 * step, "Hiện chuông thông báo", "Chuông nằm cạnh giờ khi có thông báo mới", pad)
            on = bool(st["show_bell"])
            self._switch(s, origin, mouse, right, y0 + 2 * step + 4, on, lambda v=on: island.set_setting("show_bell", not v))

            self._row(s, y0 + 3 * step, "Khởi động cùng Windows", "Tự động chạy Dynamic Notch khi mở máy", pad)
            on = bool(st.get("auto_startup", False))
            self._switch(s, origin, mouse, right, y0 + 3 * step + 4, on, lambda v=on: island.set_setting("auto_startup", not v))
        elif self.tab == 1:                                  # ---- Cá nhân hóa (được đưa lên) ----
            cur_color = tuple(st.get("bg_color", [4, 6, 10]))
            cur_op = int(st.get("bg_opacity", 100))

            # 1. Màu nền
            self._row(s, 86, "Màu nền", "Chọn màu sắc chủ đạo cho Dynamic Island và Cài đặt", pad)

            # Các nút màu mặc định (tươi sáng)
            cx = pad + 16
            for name, c in PRESET_COLORS:
                cr = pygame.Rect(cx - 15, 138, 30, 30)
                is_selected = list(c) == list(cur_color)
                draw_aa_circle(s, c, (cx, 153), 14)
                draw_aa_circle(s, th["div"], (cx, 153), 14, width=1)
                if is_selected:
                    draw_aa_circle(s, th["main"], (cx, 153), 17, width=2)
                    draw_aa_circle(s, WHITE, (cx, 153), 4)
                elif cr.collidepoint(mouse):
                    draw_aa_circle(s, th["main"], (cx, 153), 16, width=1)
                self._hit(cr, origin, lambda col=c: island.set_setting("bg_color", list(col)))
                cx += 38

            # Nút Tùy chọn màu
            custom_btn = pygame.Rect(cx + 6, 136, 126, 34)
            is_custom = all(list(c) != list(cur_color) for _, c in PRESET_COLORS)
            btn_bg = th["panel_hover"] if custom_btn.collidepoint(mouse) else th["panel"]
            draw_aa_round_rect(s, btn_bg, custom_btn, 17)
            border_col = th["accent"] if is_custom else th["div"]
            draw_aa_round_rect(s, border_col, custom_btn, 17, width=2 if is_custom else 1)
            if is_custom:
                draw_aa_circle(s, cur_color, (custom_btn.left + 18, custom_btn.centery), 7)
                draw_text(s, self.f_small, "Tùy chọn", th["main"], midleft=(custom_btn.left + 30, custom_btn.centery))
            else:
                draw_text(s, self.f_small, "+ Tùy chọn", th["main"], center=custom_btn.center)
            self._hit(custom_btn, origin, self._pick_custom_color)

            # Đường phân cách
            pygame.draw.line(s, th["div"], (pad, 186), (right, 186), 1)

            # 2. Độ trong suốt của nền
            self._row(s, 198, "Độ trong suốt nền", f"Mức độ trong suốt hiện tại: {cur_op}% (nội dung sắc nét 100%)", pad)

            # Nhóm nút chọn nhanh độ trong suốt (100%, 85%, 70%, 50%)
            op_choices = ((100, "100%"), (85, "85%"), (70, "70%"), (50, "50%"))
            seg_w = 54
            seg_x = right - seg_w * 4
            draw_aa_round_rect(s, th["panel"], (seg_x, 200, seg_w * 4, 28), 14)
            for i, (val, lbl) in enumerate(op_choices):
                sr = pygame.Rect(seg_x + i * seg_w, 200, seg_w, 28)
                on = val == cur_op
                if on:
                    draw_aa_round_rect(s, th["accent"], sr.inflate(-4, -4), 12)
                elif sr.collidepoint(mouse):
                    draw_aa_round_rect(s, th["panel_hover"], sr.inflate(-4, -4), 12)
                draw_text(s, self.f_small, lbl, WHITE if on else th["sub"], center=sr.center)
                self._hit(sr, origin, lambda v=val: island.set_setting("bg_opacity", v))

            # Thanh trượt liên tục (Slider) từ 20% đến 100%
            slider_w = right - pad
            slider_y = 254
            slider_rect = pygame.Rect(pad, slider_y - 8, slider_w, 24)
            draw_aa_round_rect(s, th["div"], (pad, slider_y, slider_w, 6), 3)
            prog = max(0.0, min(1.0, (cur_op - 20) / 80))
            fill_w = int(slider_w * prog)
            draw_aa_round_rect(s, th["accent"], (pad, slider_y, fill_w, 6), 3)
            thumb_x = pad + fill_w
            draw_aa_circle(s, WHITE, (thumb_x, slider_y + 3), 9)

            draw_text(s, self.f_tiny, "20% (Trong suốt)", th["sub"], topleft=(pad, slider_y + 12))
            draw_text(s, self.f_tiny, "100% (Đục hoàn toàn)", th["sub"], topright=(right, slider_y + 12))

            # Cho phép kéo / bấm thanh trượt trực tiếp
            if mouse_down(1) and slider_rect.collidepoint(mouse):
                rel_x = max(0, min(slider_w, mouse[0] - pad))
                new_op = int(20 + (rel_x / slider_w) * 80)
                if new_op != cur_op:
                    island.set_setting("bg_opacity", new_op)
            self._hit(slider_rect, origin, lambda: None)

            # 3. Khối xem trước tai thỏ (Live Preview)
            preview_r = pygame.Rect(0, 0, 200, 36)
            preview_r.center = (pad + (right - pad) // 2, 332)
            draw_aa_round_rect(s, cur_color, preview_r, 18)
            draw_aa_round_rect(s, th["div"], preview_r, 18, width=1)
            draw_aa_circle(s, (48, 209, 88), (preview_r.left + 20, preview_r.centery), 6, width=2)
            draw_text(s, self.f_small, "22:47", th["main"], center=preview_r.center)
            for si, sh in enumerate((6, 12, 8, 14, 7)):
                sbar = pygame.Rect(0, 0, 2, sh)
                sbar.center = (preview_r.right - 28 + si * 4, preview_r.centery)
                draw_aa_round_rect(s, th["main"], sbar, 1)
            draw_text(s, self.f_tiny, "Xem trước màu sắc tai thỏ", th["sub"], center=(preview_r.centerx, 360))

        elif self.tab == 2:                                  # ---- Lịch (được đưa xuống) ----
            # Cài đặt hiển thị cơ bản
            self._row(s, 86, "Tuần bắt đầu từ", "Thứ tự các cột trong lưới tháng", pad)
            self._seg(s, origin, mouse, right - 96 * 2, 88, ((0, "Thứ Hai"), (6, "Chủ Nhật")), st["week_start"],
                      lambda k: island.set_setting("week_start", k), 96)

            self._row(s, 146, "Chấm báo sự kiện", "Chấm màu dưới mỗi ngày có sự kiện", pad)
            on = bool(st["show_event_dots"])
            self._switch(s, origin, mouse, right, 150, on, lambda v=on: island.set_setting("show_event_dots", not v))

            # Đường phân cách phần Quản lý Lịch
            pygame.draw.line(s, th["div"], (pad, 196), (right, 196), 1)

            # ---- Header Quản lý Lịch Google Calendar ----
            y_cal = 208
            draw_text(s, self.f_text, "Lịch Google Calendar", th["main"], midleft=(pad, y_cal + 13))

            gcal = island.gcal
            cals = gcal.get_calendars() if gcal.state != "disconnected" else []

            # 2 nút chức năng ở góc phải header
            add_btn = pygame.Rect(right - 216, y_cal, 110, 26)
            add_hover = add_btn.collidepoint(mouse)
            draw_aa_round_rect(s, (30, 145, 255) if add_hover else th["accent"], add_btn, 13)
            draw_text(s, self.f_small, "+ Link iCal", WHITE, center=add_btn.center)
            def _open_input():
                self.input_active = True
                pygame.key.start_text_input()
            self._hit(add_btn, origin, _open_input)

            file_btn = pygame.Rect(right - 98, y_cal, 98, 26)
            file_hover = file_btn.collidepoint(mouse)
            draw_aa_round_rect(s, th["panel_hover"] if file_hover else th["panel"], file_btn, 13)
            draw_aa_round_rect(s, th["div"], file_btn, 13, width=1)
            draw_text(s, self.f_small, "+ File .ics", th["main"], center=file_btn.center)
            self._hit(file_btn, origin, self._pick_ics_file)

            # ---- Danh sách các Lịch đã thêm ----
            y_list = 246
            if not cals:
                empty_box = pygame.Rect(pad, y_list, right - pad, 80)
                draw_aa_round_rect(s, th["panel"], empty_box, 10)
                draw_aa_round_rect(s, th["div"], empty_box, 10, width=1)
                draw_text(s, self.f_small, "Chưa có lịch nào được kết nối", th["sub"],
                          center=(empty_box.centerx, empty_box.y + 28))
                draw_text(s, self.f_tiny, "Nhấn \"+ Link iCal\" để dán link bí mật hoặc \"+ File .ics\" để nhập file", th["dim"],
                          center=(empty_box.centerx, empty_box.y + 52))
            else:
                for i, cal in enumerate(cals[:3]):
                    ry = y_list + i * 36
                    row = pygame.Rect(pad, ry, right - pad, 32)
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
                              topleft=(pad + 4, y_list + 3 * 36 + 4))

            # ---- Trạng thái kết nối & Nút Xóa tất cả ----
            y_stat = 378
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

            if self.input_active:
                overlay = pygame.Surface((SET_W, SET_H), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 190))
                s.blit(overlay, (0, 0))

                box = pygame.Rect(0, 0, min(590, SET_W - 80), 175)
                box.center = (SET_W // 2, SET_H // 2)
                draw_aa_round_rect(s, (24, 24, 28), box, 16)
                draw_aa_round_rect(s, (60, 60, 68), box, 16, width=1)

                draw_text(s, self.f_text, "Thêm Lịch Google (iCal)", WHITE, topleft=(box.x + 24, box.y + 18))
                draw_text(s, self.f_tiny, "Google Calendar > Cài đặt lịch > Tích hợp lịch > Địa chỉ bí mật ở định dạng iCal", GREY,
                          topleft=(box.x + 24, box.y + 44))

                inp = pygame.Rect(box.x + 24, box.y + 70, box.width - 48 - 72, 32)
                draw_aa_round_rect(s, (36, 36, 42), inp, 8)
                draw_aa_round_rect(s, ACCENT, inp, 8, width=1)

                paste_r = pygame.Rect(inp.right + 8, box.y + 70, 64, 32)
                paste_hover = paste_r.collidepoint(mouse)
                draw_aa_round_rect(s, PANEL_HOVER if paste_hover else PANEL, paste_r, 8)
                draw_aa_round_rect(s, (60, 60, 68), paste_r, 8, width=1)
                draw_text(s, self.f_small, "Dán", WHITE, center=paste_r.center)
                def _do_paste():
                    clip = get_clipboard_text().strip()
                    if clip:
                        self.input_url += clip
                self._hit(paste_r, origin, _do_paste)

                if self.input_url:
                    display_url = self.input_url[-48:] if len(self.input_url) > 48 else self.input_url
                    draw_text(s, self.f_small, display_url + "▍", WHITE, midleft=(inp.x + 10, inp.centery))
                else:
                    draw_text(s, self.f_small, "Dán link hoặc bấm nút Dán bên cạnh...", DIM, midleft=(inp.x + 10, inp.centery))

                cancel_r = pygame.Rect(box.right - 170, box.bottom - 42, 72, 28)
                c_hover = cancel_r.collidepoint(mouse)
                draw_aa_round_rect(s, PANEL_HOVER if c_hover else PANEL, cancel_r, 14)
                draw_text(s, self.f_small, "Hủy", GREY, center=cancel_r.center)
                def _cancel():
                    self.input_active = False
                    self.input_url = ""
                    pygame.key.stop_text_input()
                self._hit(cancel_r, origin, _cancel)

                ok_r = pygame.Rect(box.right - 88, box.bottom - 42, 68, 28)
                ok_hover = ok_r.collidepoint(mouse)
                draw_aa_round_rect(s, (30, 145, 255) if ok_hover else ACCENT, ok_r, 14)
                draw_text(s, self.f_small, "Thêm", WHITE, center=ok_r.center)
                self._hit(ok_r, origin, self._submit_ical_url)

        elif self.tab == 3:                                  # ---- Thông tin & Cập nhật ----
            upd = island.updater
            y_info = 86

            # 1. Hộp hiển thị phiên bản hiện tại & thông tin app
            info_box = pygame.Rect(pad, y_info, right - pad, 100)
            draw_aa_round_rect(s, th["panel"], info_box, 14)
            draw_aa_round_rect(s, th["div"], info_box, 14, width=1)

            # Icon hoặc Logo nhỏ
            logo_r = pygame.Rect(info_box.x + 18, info_box.centery - 24, 48, 48)
            draw_aa_round_rect(s, th["accent"], logo_r, 14)
            draw_text(s, self.f_title, "DN", WHITE, center=logo_r.center)

            draw_text(s, self.f_title, "Dynamic Notch cho Windows", th["main"], topleft=(logo_r.right + 18, info_box.y + 18))
            draw_text(s, self.f_small, f"Phiên bản hiện tại: V{APP_VERSION}", th["sub"], topleft=(logo_r.right + 18, info_box.y + 46))
            draw_text(s, self.f_tiny, f"GitHub: {GITHUB_REPO}", th["dim"], topleft=(logo_r.right + 18, info_box.y + 68))

            # 2. Tùy chọn Tự động cập nhật
            y_opt = y_info + 120
            self._row(s, y_opt, "Cập nhật tự động", "Tự động kiểm tra bản phát hành mới khi mở ứng dụng", pad)
            on = bool(st.get("auto_update", True))
            self._switch(s, origin, mouse, right, y_opt + 4, on, lambda v=on: island.set_setting("auto_update", not v))

            # Đường kẻ phân cách
            pygame.draw.line(s, th["div"], (pad, y_opt + 60), (right, y_opt + 60), 1)

            # 3. Trạng thái cập nhật và Nút kiểm tra
            y_check = y_opt + 76
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

            draw_text(s, self.f_small, status_msg, msg_color, topleft=(pad, y_check + 26))

            # Nút Kiểm tra cập nhật / Tải bản cập nhật
            btn_w = 170
            chk_btn = pygame.Rect(right - btn_w, y_check + 10, btn_w, 34)
            chk_hover = chk_btn.collidepoint(mouse)

            if upd.status == "update_available":
                # Chỉ hiện nút Tải & Cài đặt khi có phiên bản mới hơn trên GitHub
                draw_aa_round_rect(s, (48, 209, 88) if chk_hover else (38, 180, 75), chk_btn, 17)
                draw_text(s, self.f_small, f"Tải & Cài đặt V{upd.latest_version}", WHITE, center=chk_btn.center)
                self._hit(chk_btn, origin, upd.download_and_install)
            elif upd.status == "up_to_date":
                # Phiên bản trên máy đã là mới nhất hoặc lớn hơn: nút bị vô hiệu hóa
                draw_aa_round_rect(s, th["panel"], chk_btn, 17)
                draw_aa_round_rect(s, th["div"], chk_btn, 17, width=1)
                draw_text(s, self.f_small, "Đã cập nhật", th["dim"], center=chk_btn.center)
                # Không gắn self._hit để vô hiệu hóa click
            elif upd.status == "downloading":
                draw_aa_round_rect(s, th["panel"], chk_btn, 17)
                draw_text(s, self.f_small, f"Đang tải {upd.download_progress}%", th["accent"], center=chk_btn.center)
            elif upd.status == "checking":
                draw_aa_round_rect(s, th["panel"], chk_btn, 17)
                draw_text(s, self.f_small, "Đang kiểm tra...", th["sub"], center=chk_btn.center)
            else:
                # Trạng thái ban đầu (idle) hoặc lỗi: cho phép bấm kiểm tra
                draw_aa_round_rect(s, (30, 145, 255) if chk_hover else th["accent"], chk_btn, 17)
                draw_text(s, self.f_small, "Kiểm tra cập nhật", WHITE, center=chk_btn.center)
                self._hit(chk_btn, origin, lambda: upd.check_for_updates(auto_download=False))

        draw_text(s, self.f_tiny, "Thay đổi được lưu tự động", th["dim"], midbottom=(SET_W // 2, SET_H - 12))
