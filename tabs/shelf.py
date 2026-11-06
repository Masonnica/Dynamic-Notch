"""
Tab Ngăn xếp: lưu trữ tạm file, mở nhanh, xóa và hỗ trợ kéo thả ra ngoài.
"""
from pathlib import Path
import pygame

from config import WHITE, GREY, DIM, BLACK, PANEL, PANEL_HOVER, BADGES
from utils.drawing import draw_text, fit_text, draw_aa_round_rect
from .base import BaseTab


class ShelfTab(BaseTab):
    """Tab Ngăn xếp: cất giữ file nhanh, mở và kéo thả ra ngoài."""

    def draw(self, surf):
        island = self.island
        th = island.theme()
        draw_text(surf, island.f_tiny,
                  fit_text(island.f_tiny, "Thả file vào đây • nhấp đôi để mở • kéo ra để lấy • chuột phải để gỡ", 440),
                  th["sub"], midtop=(surf.get_width() // 2, 80))
        if not island.files:                                   # trạng thái trống
            area = pygame.Rect(20, 104, 440, 180)
            draw_aa_round_rect(surf, th["div"], area, 14, width=2)
            draw_text(surf, island.f_text, "Kéo file vào island để cất ở đây", th["main"], center=area.center)
            return
        start = island.scroll * 5                              # 5 ô mỗi hàng, hiện 2 hàng
        for n, idx in enumerate(range(start, min(start + 10, len(island.files)))):
            path = island.files[idx]
            col, row = n % 5, n // 5
            tile = pygame.Rect(20 + col * 90, 104 + row * 94, 80, 86)
            t_col = th["panel_hover"] if tile.collidepoint(island.mouse_local) else th["panel"]
            draw_aa_round_rect(surf, t_col, tile, 10)
            zone = (tile.centerx, tile.y + 34)               # tâm vùng chứa icon
            icon = island.icon_for(path)                     # icon thật của Windows (đã cache)
            if icon:
                surf.blit(icon, icon.get_rect(center=zone))
            else:                                            # không lấy được icon -> nhãn đuôi file
                ext = "DIR" if Path(path).is_dir() else (Path(path).suffix.lstrip(".").upper()[:4] or "FILE")
                badge = pygame.Rect(0, 0, 44, 34)
                badge.center = zone
                draw_aa_round_rect(surf, BADGES[sum(map(ord, ext)) % len(BADGES)], badge, 8)
                draw_text(surf, island.f_small, ext, BLACK, center=badge.center)
            draw_text(surf, island.f_tiny, fit_text(island.f_tiny, Path(path).name, 72), th["main"],
                      midtop=(tile.centerx, tile.y + 62))
            island.add_hit(tile, lambda i=idx: island.tile_press(i), lambda i=idx: island.remove_file(i))

    def on_wheel(self, dy):
        island = self.island
        rows = (len(island.files) + 4) // 5
        island.scroll = max(0, min(island.scroll - dy, max(0, rows - 2)))   # cuộn theo hàng, tối đa rows-2
