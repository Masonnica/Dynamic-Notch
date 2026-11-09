"""
Tab Nhạc - pixel-perfect theo ảnh mẫu:
1. ĐÓNG Lyrics (W=480, H=275):
   - Header giờ + vòng tròn pin + sóng nhạc (do draw_top vẽ)
   - Ảnh bìa 68x68 + Tên + Nghệ sĩ
   - Seek bar ngắn căn giữa + nhãn thời gian
   - Dải điều khiển: nút tròn Lyrics bên trái + << ▶ >> ở giữa
   - Nền tối đơn sắc (màu island)

2. MỞ Lyrics (W=680, H=275):
   - Giống bên trái nhưng thêm cột phải: 3 dòng lyrics
   - Nền GRADIENT từ màu chủ đạo ảnh bìa → màu island (nửa dưới island)
   - Seek bar dài suốt toàn chiều ngang
   - Dải điều khiển giống chế độ đóng

3. Gradient chỉ áp ở nửa dưới (từ dưới ảnh bìa → đáy), blend mịn
4. Seek bar mượt, kéo thả chính xác từng pixel
"""
import math
import time
import bisect
import pygame

from config import WHITE, GREY, DIM, ACCENT, PANEL, PANEL_HOVER
from utils.drawing import (draw_text, fit_text, fmt_time, make_nav_icon, lerp,
                           draw_aa_circle, draw_aa_round_rect, dominant_color)
from bridges.media import MediaBridge
from .base import BaseTab


def _rounded(surf, radius):
    """Bo góc ảnh mượt mà có khử răng cưa."""
    w, h = surf.get_size()
    out = surf.convert_alpha()
    k = 2
    big_mask = pygame.Surface((w * k, h * k), pygame.SRCALPHA)
    big_mask.fill((0, 0, 0, 0))
    pygame.draw.rect(big_mask, (255, 255, 255, 255), big_mask.get_rect(), border_radius=radius * k)
    mask = pygame.transform.smoothscale(big_mask, (w, h))
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def _draw_gradient_rect(surf, rect, color_top_rgb, color_bot_rgb, alpha_top=180, alpha_bot=0):
    """Vẽ gradient dọc RGBA từ trên xuống dưới dùng surface SRCALPHA."""
    x, y0, rw, rh = rect.x, rect.y, rect.width, rect.height
    if rh <= 0 or rw <= 0:
        return
    grad_surf = pygame.Surface((rw, rh), pygame.SRCALPHA)
    steps = min(rh, 128)
    for i in range(steps):
        t = i / max(1, steps - 1)
        r = int(color_top_rgb[0] * (1 - t) + color_bot_rgb[0] * t)
        g = int(color_top_rgb[1] * (1 - t) + color_bot_rgb[1] * t)
        b = int(color_top_rgb[2] * (1 - t) + color_bot_rgb[2] * t)
        a = int(alpha_top * (1 - t) + alpha_bot * t)
        band_y = round(i * rh / steps)
        band_h = max(1, round((i + 1) * rh / steps) - band_y)
        grad_surf.fill((r, g, b, a), (0, band_y, rw, band_h))
    surf.blit(grad_surf, (x, y0))


class MusicTab(BaseTab):
    """Tab Nhạc pixel-perfect theo ảnh mẫu tham chiếu với hoạt ảnh Morph mượt mà."""

    def __init__(self, island):
        super().__init__(island)
        self._art_key = None
        self._art_img = None
        self._scroll_pos = 0.0
        self._last_target = -1
        self._dragging_seek = False
        self._drag_pos = 0.0
        self._dom_color = (40, 40, 44)   # màu chủ đạo ảnh bìa hiện tại
        self._dom_art_id = None          # id ảnh bìa đã tính màu
        self._morph_t = 1.0 if island.settings.get("show_lyrics", True) else 0.0

    def lyric_index(self, pos):
        times = self.island.lyrics[0]
        return bisect.bisect_right(times, pos + 0.2) - 1 if times else -1

    def artwork(self, size, radius=16):
        src = self.island.art
        key = (id(src) if src is not None else 0, size, radius)
        if key == self._art_key:
            return self._art_img
        if src is None:
            img = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.rect(img, (36, 130, 245, 255), img.get_rect(), border_radius=radius)
            txt = self.island.f_text.render("Ảnh", True, WHITE)
            img.blit(txt, txt.get_rect(center=img.get_rect().center))
        else:
            img = _rounded(pygame.transform.smoothscale(src, (size, size)), radius)
        self._art_key, self._art_img = key, img
        return img

    def _get_dominant(self):
        """Trả về màu chủ đạo ảnh bìa, cache lại tránh tính lại mỗi frame."""
        src = self.island.art
        art_id = id(src) if src is not None else None
        if art_id != self._dom_art_id:
            self._dom_art_id = art_id
            self._dom_color = dominant_color(src)
        return self._dom_color

    def draw(self, surf):
        island = self.island
        surf_w, surf_h = surf.get_size()
        pos = self._drag_pos if self._dragging_seek else island.position()
        th = island.theme()
        mx, my = island.mouse_local
        show_lyrics = island.settings.get("show_lyrics", True)

        # Cập nhật tiến trình morph (0.0: đóng lyrics, 1.0: mở lyrics)
        target_t = 1.0 if show_lyrics else 0.0
        diff = target_t - self._morph_t
        if abs(diff) > 0.005:
            self._morph_t += diff * 0.22
            island.animating = True
        else:
            self._morph_t = target_t
        t = self._morph_t

        from utils.win32 import mouse_down
        is_lmb = mouse_down(1)

        if self._dragging_seek:
            if not is_lmb:
                self._dragging_seek = False
                island.seek_to(self._drag_pos)
            else:
                island.animating = True

        self._draw_morphed(surf, surf_w, surf_h, pos, th, mx, my, show_lyrics, t)

    def _draw_seek_bar(self, surf, bar, current_pos, duration, th, mx, my):
        """Thanh tiến độ mượt mà, kéo thả chính xác."""
        island = self.island
        hit_box = pygame.Rect(bar.left - 6, bar.top - 12, bar.width + 12, bar.height + 24)
        is_hover = hit_box.collidepoint((mx, my))

        from utils.win32 import mouse_down
        is_lmb = mouse_down(1)

        if self._dragging_seek:
            if duration > 0:
                rel = max(0.0, min(1.0, (mx - bar.left) / max(1, bar.width)))
                self._drag_pos = rel * duration
                current_pos = self._drag_pos
        elif is_hover and is_lmb:
            if duration > 0:
                self._dragging_seek = True
                rel = max(0.0, min(1.0, (mx - bar.left) / max(1, bar.width)))
                self._drag_pos = rel * duration
                current_pos = self._drag_pos
                island.animating = True

        bar_h = 5 if (is_hover or self._dragging_seek) else 3.5
        bar_rect = pygame.Rect(bar.left, bar.centery - int(bar_h) // 2, bar.width, int(bar_h))
        # Đổi màu fill/thanh seek bar thích ứng theo theme
        bar_bg_col = (200, 200, 205) if th["is_light"] else (55, 55, 60)
        draw_aa_round_rect(surf, bar_bg_col, bar_rect, int(bar_h) // 2)

        pct = max(0.0, min(1.0, current_pos / duration)) if duration > 0 else 0.0
        fill_w = int(bar.width * pct)
        if fill_w > 0:
            fill_rect = pygame.Rect(bar_rect.left, bar_rect.top, fill_w, int(bar_h))
            draw_aa_round_rect(surf, th["main"], fill_rect, int(bar_h) // 2)

        if (is_hover or self._dragging_seek) and duration > 0:
            draw_aa_circle(surf, th["main"], (bar.left + fill_w, bar.centery), 5.5)

        left_t = fmt_time(current_pos) if duration > 0 else "--:--"
        draw_text(surf, island.f_tiny, left_t, th["main"], midright=(bar.left - 8, bar.centery))
        rem = max(0.0, duration - current_pos) if duration > 0 else 0.0
        rem_str = f"-{fmt_time(rem)}" if duration > 0 else "--:--"
        draw_text(surf, island.f_tiny, rem_str, th["sub"], midleft=(bar.right + 8, bar.centery))

        def on_click():
            if duration > 0:
                cur_mx, _ = island.mouse_local
                rel = max(0.0, min(1.0, (cur_mx - bar.left) / max(1, bar.width)))
                island.seek_to(rel * duration)
        island.add_hit(hit_box, on_click)

    def _draw_controls(self, surf, center_x, cy, mx, my, show_lyrics, lyr_offset=85):
        """Dải điều khiển: Nút Lyrics tròn bên trái, << ▶/|| >> ở giữa notch."""
        island = self.island
        th = island.theme()

        # Nút Lyrics — OFF: icon viền xám; ON: icon tô đặc th["main"] (2 chấm khoét thủng), không có nền
        # lyr_offset nội suy giữa 85 (compact) và 115 (expanded) tạo hiệu ứng morph trượt mượt mà
        lyr_btn = 30                                         # vùng hit box
        lyr_cx = center_x - lyr_offset
        lyr_rect = pygame.Rect(0, 0, lyr_btn + 10, lyr_btn + 10)
        lyr_rect.center = (round(lyr_cx), cy)
        is_hover_lyr = lyr_rect.collidepoint((mx, my))

        if show_lyrics:
            # Tô đặc, 2 chấm khoét thủng (th["main"] cho nền sáng/tối)
            icon_col = th["main"] if not is_hover_lyr else th["sub"]
            icon = make_nav_icon("lyrics", 22, icon_col, filled=True)
        else:
            # Chỉ viền xám/tối, không nền
            icon_col = th["sub"] if is_hover_lyr else th["dim"]
            icon = make_nav_icon("lyrics", 22, icon_col, filled=False)
        surf.blit(icon, icon.get_rect(center=(round(lyr_cx), cy)))
        island.add_hit(lyr_rect, lambda: island.set_setting("show_lyrics", not show_lyrics))

        # Nút Prev <<
        prev_rect = pygame.Rect(0, 0, 40, 32)
        prev_rect.center = (center_x - 42, cy)
        p_col = th["main"] if prev_rect.collidepoint((mx, my)) else th["sub"]
        pygame.draw.polygon(surf, p_col, [(center_x - 36, cy - 6), (center_x - 36, cy + 6), (center_x - 44, cy)])
        pygame.draw.polygon(surf, p_col, [(center_x - 43, cy - 6), (center_x - 43, cy + 6), (center_x - 51, cy)])
        island.add_hit(prev_rect, lambda: MediaBridge.command("prev"))

        # Nút Play/Pause
        play_rect = pygame.Rect(0, 0, 40, 32)
        play_rect.center = (center_x, cy)
        pl_col = th["main"] if play_rect.collidepoint((mx, my)) else th["sub"]
        if island.playing:
            pygame.draw.rect(surf, pl_col, (center_x - 6, cy - 8, 4, 16))
            pygame.draw.rect(surf, pl_col, (center_x + 2, cy - 8, 4, 16))
        else:
            pygame.draw.polygon(surf, pl_col, [(center_x - 5, cy - 8), (center_x - 5, cy + 8), (center_x + 7, cy)])
        island.add_hit(play_rect, lambda: MediaBridge.command("toggle"))

        # Nút Next >>
        next_rect = pygame.Rect(0, 0, 40, 32)
        next_rect.center = (center_x + 42, cy)
        n_col = th["main"] if next_rect.collidepoint((mx, my)) else th["sub"]
        pygame.draw.polygon(surf, n_col, [(center_x + 36, cy - 6), (center_x + 36, cy + 6), (center_x + 44, cy)])
        pygame.draw.polygon(surf, n_col, [(center_x + 43, cy - 6), (center_x + 43, cy + 6), (center_x + 51, cy)])
        island.add_hit(next_rect, lambda: MediaBridge.command("next"))

    def _draw_morphed(self, surf, w, h, pos, th, mx, my, show_lyrics, t):
        """Vẽ tab Âm thanh theo đúng logic tuần tự:
        - Khi mở lyrics (t tăng 0 -> 1): Mở rộng dynamic, đồng thời cắt bớt chữ phần tên trước; khi mở gần xong mới hiện lyrics.
        - Khi tắt lyrics (t giảm 1 -> 0): Thu gọn dynamic, phần lyrics nào đang trùng với phần thông tin âm thanh thì biến mất ngay; sau cùng mới mở rộng lại phần tên.
        """
        island = self.island
        dom = self._get_dominant()
        bg = tuple(island.settings.get("bg_color", [4, 6, 10]))

        cur_w = w
        div_x = cur_w // 2

        # 1. Gradient nền: chỉ hiện khi có lyrics (alpha tăng/giảm theo t)
        if t > 0.05:
            from config import CONTENT_DY
            bottom_y = round(island.cur_h - CONTENT_DY)
            grad_top_y = 176
            grad_rect = pygame.Rect(0, grad_top_y, cur_w, max(0, bottom_y - grad_top_y))
            _draw_gradient_rect(surf, grad_rect, dom, dom, alpha_top=0, alpha_bot=round(220 * t))

        # 2. Cột trái: Ảnh bìa + Tên + Nghệ sĩ
        art_s = 64
        art = pygame.Rect(36, 92, art_s, art_s)
        surf.blit(self.artwork(art_s, radius=14), art.topleft)

        info_x = art.right + 14
        # LOGIC PHẦN TÊN:
        # - Khi MỞ lyrics: Cắt bớt chữ của phần tên NGAY LẬP TỨC để nhường chỗ cho cột lyrics sắp mở.
        # - Khi TẮT lyrics: Vì lyrics đã ẩn đi ngay, tên bài hát và nghệ sĩ được GIÃN NGAY RA TRÀN QUA PHẦN LYRICS
        #   (tận dụng toàn bộ bề ngang cur_w đang co lại của Dynamic Notch).
        info_w_compact = cur_w - info_x - 32
        info_w_expanded = max(10, div_x - info_x - 18)

        if show_lyrics:
            # Đang mở lyrics: co chữ lại trong phạm vi nửa cột trái
            info_w = info_w_expanded
        else:
            # Đang tắt lyrics: chữ lập tức giãn rộng ra suốt chiều ngang cur_w hiện tại
            info_w = info_w_compact

        title = island.title or "Tên âm thanh"
        artist = island.artist or "Tên tác giả"
        draw_text(surf, island.f_title, fit_text(island.f_title, title, info_w), th["main"], topleft=(info_x, 100))
        draw_text(surf, island.f_small, fit_text(island.f_small, artist, info_w), th["sub"], topleft=(info_x, 128))

        # 3. Đường phân cách đứng & Cột Lyrics bên phải
        # LOGIC PHẦN LYRICS:
        # - Khi MỞ lyrics: Sau khi mở rộng dynamic gần xong (t >= 0.7) thì lyrics mới bắt đầu hiện lên
        # - Khi TẮT lyrics: Ngay khi bắt đầu thu gọn (show_lyrics=False), lyrics mờ và biến mất nhanh trước để không bị trùng
        if show_lyrics and t >= 0.7:
            lyr_alpha_factor = (t - 0.7) / 0.3  # 0.0 -> 1.0 trong đoạn cuối của mở rộng
        elif not show_lyrics and t > 0.8:
            lyr_alpha_factor = (t - 0.8) / 0.2  # biến mất ngay khi vừa bắt đầu thu gọn
        else:
            lyr_alpha_factor = 0.0

        if lyr_alpha_factor > 0.02:
            div_alpha = int(255 * lyr_alpha_factor)
            # Đường phân cách mờ đứng (mở rộng xuống thêm 16px)
            div_surf = pygame.Surface((2, 104), pygame.SRCALPHA)
            div_surf.fill((55, 55, 62, div_alpha))
            surf.blit(div_surf, (div_x, 84))

            # Cột phải: 3 dòng lyrics
            lyric_left = div_x + 16
            lyric_right = cur_w - 24
            lyric_w = max(0, lyric_right - lyric_left)
            times, lines = island.lyrics

            # Giới hạn tuyệt đối lyrics trong phạm vi cột phải từ lyric_left đến lyric_right (không trùng thông tin âm thanh)
            # Mở rộng chiều cao layer thêm 16px (112 -> 128) để hiển thị thoáng hơn
            if lyric_w > 20:
                lyr_layer = pygame.Surface((lyric_w, 128), pygame.SRCALPHA)
                lyr_rel_cx = lyric_w // 2

                if lines:
                    target_idx = self.lyric_index(pos)
                    if target_idx < 0:
                        target_idx = 0

                    if self._last_target == -1 or abs(target_idx - self._scroll_pos) > 3.0:
                        self._scroll_pos = float(target_idx)
                    else:
                        diff_lyr = target_idx - self._scroll_pos
                        self._scroll_pos += diff_lyr * 0.16
                        if abs(diff_lyr) < 0.005:
                            self._scroll_pos = float(target_idx)
                        else:
                            island.animating = True
                    self._last_target = target_idx

                    start_i = max(0, int(self._scroll_pos - 2))
                    end_i = min(len(lines), int(self._scroll_pos + 3))
                    bg_col = bg
                    cy_lyr = 58
                    for i in range(start_i, end_i):
                        dist = abs(i - self._scroll_pos)
                        if dist > 2.0:
                            continue
                        y_i = cy_lyr + (i - self._scroll_pos) * 34
                        font = island.f_lyric if dist < 0.45 else island.f_text
                        if dist <= 0.45:
                            col = (*th["lyric_active"], div_alpha)
                        elif dist <= 1.0:
                            t_d = 1.0 - dist
                            base_c = th["main"] if th["is_light"] else (255, 255, 255)
                            fade_c = th["dim"] if th["is_light"] else (85, 85, 85)
                            col = (round(fade_c[0] + (base_c[0] - fade_c[0]) * t_d),
                                   round(fade_c[1] + (base_c[1] - fade_c[1]) * t_d),
                                   round(fade_c[2] + (base_c[2] - fade_c[2]) * t_d), div_alpha)
                        else:
                            t_fade = max(0.0, 2.0 - dist)
                            fade_c = th["dim"] if th["is_light"] else (85, 85, 85)
                            col = (round(fade_c[0] * t_fade + bg_col[0] * (1 - t_fade)),
                                   round(fade_c[1] * t_fade + bg_col[1] * (1 - t_fade)),
                                   round(fade_c[2] * t_fade + bg_col[2] * (1 - t_fade)), div_alpha)
                        draw_text(lyr_layer, font, fit_text(font, lines[i], lyric_w), col, center=(lyr_rel_cx, round(y_i)))
                elif island.title:
                    # Đang có bài hát phát nhưng không tìm thấy lyrics/phụ đề
                    not_avail = "Lời cho âm thanh này không khả dụng"
                    draw_text(lyr_layer, island.f_small, fit_text(island.f_small, not_avail, lyric_w), (*th["sub"], div_alpha), center=(lyr_rel_cx, 58))
                    self._last_target = -1
                else:
                    # Mockup / chưa phát gì
                    draw_text(lyr_layer, island.f_text, "Dòng 1", (*th["dim"], div_alpha), center=(lyr_rel_cx, 28))
                    draw_text(lyr_layer, island.f_lyric, "Dòng 2", (*th["lyric_active"], div_alpha), center=(lyr_rel_cx, 58))
                    draw_text(lyr_layer, island.f_text, "Dòng 3", (*th["dim"], div_alpha), center=(lyr_rel_cx, 88))
                    self._last_target = -1

                surf.blit(lyr_layer, (lyric_left, 74))

        # 4. Thanh Seek bar: tự động co giãn theo bề rộng cur_w (nhích xuống 16px: 188 -> 204)
        bar_left = 48
        bar_w = cur_w - bar_left * 2
        bar = pygame.Rect(bar_left, 204, bar_w, 4)
        self._draw_seek_bar(surf, bar, pos, island.duration, th, mx, my)

        # 5. Controls: nút lyrics di chuyển mượt mà (nhích xuống 8px: 234 -> 242)
        lyr_off = lerp(85.0, 115.0, t)
        self._draw_controls(surf, cur_w // 2, 242, mx, my, show_lyrics, lyr_offset=lyr_off)
