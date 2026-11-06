"""
Tab Nhạc: thông tin bài hát (ảnh bìa, tên, tác giả, điều khiển) bên trái, lyrics bên phải.
"""
import bisect
import pygame

from config import WHITE, GREY, DIM, ACCENT, PANEL, PANEL_HOVER
from utils.drawing import draw_text, fit_text, fmt_time, make_nav_icon, draw_aa_circle, draw_aa_round_rect
from bridges.media import MediaBridge
from .base import BaseTab


def _rounded(surf, radius):
    """Bo góc ảnh mượt mà có khử răng cưa (anti-aliasing)."""
    w, h = surf.get_size()
    out = surf.convert_alpha()
    k = 2
    big_mask = pygame.Surface((w * k, h * k), pygame.SRCALPHA)
    big_mask.fill((0, 0, 0, 0))
    pygame.draw.rect(big_mask, (255, 255, 255, 255), big_mask.get_rect(), border_radius=radius * k)
    mask = pygame.transform.smoothscale(big_mask, (w, h))
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


class MusicTab(BaseTab):
    """Tab Nhạc: ảnh bìa và điều khiển ở cột trái, lời bài hát đồng bộ ở cột phải."""

    def __init__(self, island):
        super().__init__(island)
        self._art_key = None
        self._art_img = None
        self._scroll_pos = 0.0
        self._last_target = -1

    def lyric_index(self, pos):
        """Tìm vị trí dòng lyrics tương ứng với mốc thời gian pos."""
        times = self.island.lyrics[0]
        return bisect.bisect_right(times, pos + 0.2) - 1 if times else -1

    def artwork(self, size, radius=14):
        """Ảnh bìa đã thu nhỏ và bo góc. Không có ảnh thì vẽ ô nền kèm nốt nhạc."""
        src = self.island.art
        key = (id(src) if src is not None else 0, size, radius)
        if key == self._art_key:
            return self._art_img
        if src is None:
            img = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.rect(img, (44, 44, 48, 255), img.get_rect(), border_radius=radius)
            note = make_nav_icon("music", size // 2, GREY)
            img.blit(note, note.get_rect(center=img.get_rect().center))
        else:
            img = _rounded(pygame.transform.smoothscale(src, (size, size)), radius)
        self._art_key, self._art_img = key, img
        return img

    def draw(self, surf):
        island = self.island
        w = surf.get_width()
        pos = island.position()
        th = island.theme()

        div_x = w // 2
        left_cx = div_x // 2

        # Cột trái: ảnh bìa ở trên cùng (phóng to rõ nét), tên bài hát và nghệ sĩ ở dưới
        art_s = 84
        art = pygame.Rect(0, 0, art_s, art_s)
        art.center = (left_cx, 112)

        cover = self.artwork(art_s, radius=16)
        surf.blit(cover, art.topleft)
        draw_aa_round_rect(surf, th["div"], art, 16, width=1)

        title = island.title or "Không có nhạc đang phát"
        text_w = div_x - 50
        title_y = art.bottom + 14
        artist_y = title_y + 17
        draw_text(surf, island.f_title, fit_text(island.f_title, title, text_w), th["main"],
                  center=(left_cx, title_y))
        draw_text(surf, island.f_small, fit_text(island.f_small, island.artist, text_w), th["sub"],
                  center=(left_cx, artist_y))

        # Thanh tiến độ nằm dưới khối tên bài hát
        bar_y = artist_y + 16
        bar_w = min(220, div_x - 90)
        bar = pygame.Rect(left_cx - bar_w // 2, bar_y, bar_w, 4)
        draw_aa_round_rect(surf, th["bar"], bar, 2)
        if island.duration > 0:
            fill = bar.copy()
            fill.width = int(bar.width * min(pos / island.duration, 1))
            if fill.width > 0:
                draw_aa_round_rect(surf, th["main"], fill, 2)
        draw_text(surf, island.f_tiny, fmt_time(pos), th["sub"], midright=(bar.left - 6, bar.centery))
        draw_text(surf, island.f_tiny, fmt_time(island.duration), th["sub"], midleft=(bar.right + 6, bar.centery))

        # Nút điều khiển nằm dưới thanh tiến độ
        cy = bar.bottom + 21
        for dx, kind, cmd in ((-50, "prev", "prev"), (0, "play", "toggle"), (50, "next", "next")):
            x = left_cx + dx
            br = pygame.Rect(x - 16, cy - 16, 32, 32)
            btn_col = th["panel_hover"] if br.collidepoint(island.mouse_local) else th["panel"]
            draw_aa_circle(surf, btn_col, (x, cy), 16)
            if kind == "prev":
                pygame.draw.rect(surf, th["main"], (x - 7, cy - 6, 2, 12))
                pygame.draw.polygon(surf, th["main"], [(x + 7, cy - 6), (x + 7, cy + 6), (x - 3, cy)])
            elif kind == "next":
                pygame.draw.rect(surf, th["main"], (x + 5, cy - 6, 2, 12))
                pygame.draw.polygon(surf, th["main"], [(x - 7, cy - 6), (x - 7, cy + 6), (x + 3, cy)])
            elif island.playing:
                pygame.draw.rect(surf, th["main"], (x - 6, cy - 7, 4, 14))
                pygame.draw.rect(surf, th["main"], (x + 2, cy - 7, 4, 14))
            else:
                pygame.draw.polygon(surf, th["main"], [(x - 5, cy - 7), (x - 5, cy + 7), (x + 8, cy)])
            island.add_hit(br, lambda c=cmd: MediaBridge.command(c))

        # Đường phân cách giữa 2 cột (ngay chính giữa tab)
        pygame.draw.line(surf, th["div"], (div_x, 90), (div_x, 246), 1)

        # Cột phải: ba dòng lyrics, căn giữa nửa bên phải kèm hiệu ứng trượt mượt mà
        lyric_left = div_x + 20
        lyric_right = w - 20
        lyric_cx = (lyric_left + lyric_right) // 2
        lyric_w = lyric_right - lyric_left
        times, lines = island.lyrics
        if lines:
            target_idx = self.lyric_index(pos)
            if target_idx < 0:
                target_idx = 0

            # Nhảy tức thì khi đổi bài / tua xa, trượt mượt mà khi qua câu tiếp theo
            if self._last_target == -1 or abs(target_idx - self._scroll_pos) > 3.0:
                self._scroll_pos = float(target_idx)
            else:
                diff = target_idx - self._scroll_pos
                self._scroll_pos += diff * 0.16
                if abs(diff) < 0.005:
                    self._scroll_pos = float(target_idx)
                else:
                    island.animating = True   # Giữ 60 FPS trong lúc đang trượt chữ
            self._last_target = target_idx

            # Giới hạn vùng hiển thị lyrics (clip) để các câu trượt vào/ra không tràn viền
            old_clip = surf.get_clip()
            surf.set_clip(pygame.Rect(lyric_left - 10, 84, lyric_w + 20, 166))
            try:
                start_i = max(0, int(self._scroll_pos - 2))
                end_i = min(len(lines), int(self._scroll_pos + 3))
                bg_col = th["bg"]
                for i in range(start_i, end_i):
                    dist = abs(i - self._scroll_pos)
                    if dist > 2.0:
                        continue
                    y_i = 168 + (i - self._scroll_pos) * 38
                    font = island.f_lyric if dist < 0.45 else island.f_text
                    if dist <= 1.0:
                        t = 1.0 - dist
                        col = tuple(round(th["dim"][c] + (th["lyric_active"][c] - th["dim"][c]) * t) for c in range(3))
                    else:
                        t_fade = max(0.0, 2.0 - dist)
                        col = tuple(round(th["dim"][c] * t_fade + bg_col[c] * (1 - t_fade)) for c in range(3))
                    draw_text(surf, font, fit_text(font, lines[i], lyric_w), col, center=(lyric_cx, round(y_i)))
            finally:
                surf.set_clip(old_clip)
        else:
            self._scroll_pos = 0.0
            self._last_target = -1
            cur_t = {"loading": "Đang tìm lyrics…", "none": "(không tìm thấy lyrics)"}.get(island.lyr_state, "…")
            draw_text(surf, island.f_lyric, fit_text(island.f_lyric, cur_t, lyric_w), th["lyric_active"], center=(lyric_cx, 168))
