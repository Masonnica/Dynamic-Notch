"""
Dynamic Island cho Windows - bản pygame-ce (pygame.Window), hình dạng "tai thỏ" (notch)
Điểm khởi chạy ứng dụng (Entry point).
"""
import os
import sys
import time
import ctypes
import pygame

from config import TITLE, WIN_W, WIN_H, TOP_MARGIN, KEY, OFFSCREEN_POS
from utils.win32 import setup_native_window, keep_on_top, move_window, dwm_flush, poll_mouse, register_mouse_click, cursor_pos
from island import Island
from settings_ui import SettingsWindow


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)       # tránh Windows phóng to mờ cửa sổ khi scale 125-150%
    except Exception:
        pass
    os.environ.setdefault("SDL_MOUSE_FOCUS_CLICKTHROUGH", "1")   # nhấp lần đầu lên cửa sổ chưa active vẫn được tính là click
    os.environ.setdefault("SDL_WINDOW_NO_ACTIVATION_WHEN_SHOWN", "1")   # hiện cửa sổ mà không cướp focus của app đang dùng
    pygame.init()                                            # khởi tạo pygame (bao gồm display và font)
    scr_w = pygame.display.get_desktop_sizes()[0][0]         # chiều rộng màn hình chính
    win_x, win_y = (scr_w - WIN_W) // 2, TOP_MARGIN          # vị trí CUỐI CÙNG: căn giữa, dính mép trên

    # 1) Tạo cửa sổ ở NGOÀI màn hình (borderless ngay lúc tạo để không bị đổi khung sau khi đã hiện ra)
    window = pygame.Window(TITLE, (WIN_W, WIN_H), position=OFFSCREEN_POS, borderless=True)
    try:
        window.always_on_top = True                          # luôn nằm trên cùng
    except Exception:
        pass                                                 # nếu bản pygame-ce không có thì setup_native_window sẽ lo

    # 2) Biến thành cửa sổ trong suốt và tô sẵn toàn bộ bằng màu trong suốt
    surface = window.get_surface()                           # tạo surface của Window trước: convert_alpha() (icon file) cần có nó
    surface.fill(KEY)
    hwnd = setup_native_window(TITLE, use_colorkey=False)    # layered alpha (hỗ trợ nền trong suốt mà chữ vẫn 100% rõ) + ẩn taskbar + topmost
    window.flip()                                            # khung hình đầu tiên: toàn màu trong suốt

    # 3) Khởi tạo nặng (font, lịch, luồng nền...) trong lúc cửa sổ còn nằm ngoài màn hình
    island = Island(win_x, win_y, intro=True, hwnd=hwnd)     # intro=True: island ẩn, chờ begin_intro()
    island.draw(window.get_surface())                        # khung "rỗng": toàn bộ là màu trong suốt
    window.flip()
    dwm_flush()                                              # chờ Windows ghép xong khung trong suốt này

    # 4) Nền trong suốt đã sẵn sàng -> đưa cửa sổ vào màn hình rồi chạy hiệu ứng giọt nước
    if hwnd:
        move_window(hwnd, win_x, win_y)
    else:
        window.position = (win_x, win_y)
    island.begin_intro()

    # Cửa sổ Cài đặt: tạo sẵn (nằm ngoài màn hình, trong suốt), chỉ hiện khi bấm nút bánh răng
    scr_h = pygame.display.get_desktop_sizes()[0][1]
    settings = SettingsWindow(island, scr_w, scr_h)
    island.settings_win = settings

    next_top = 0.0                                           # mốc thời gian lần giữ topmost kế tiếp
    clock = pygame.time.Clock()

    while not island.quit:                                   # vòng lặp chính
        for e in pygame.event.get():
            if e.type == pygame.WINDOWCLOSE and getattr(e, "window", None) is settings.window:
                settings.close()                             # đóng cửa sổ Cài đặt (vd. Alt+F4) không được tắt cả island
            elif e.type in (pygame.QUIT, pygame.WINDOWCLOSE):
                island.trigger_quit()
            elif e.type == pygame.MOUSEBUTTONDOWN:
                register_mouse_click(e.button, getattr(e, "pos", None), getattr(e, "window", None))
                # Phân phối trực tiếp sự kiện click cho Settings hoặc Island
                ev_win = getattr(e, "window", None)
                if ev_win is settings.window or (settings.visible and settings.covers(*cursor_pos())):
                    settings.handle_click_event(e.button, getattr(e, "pos", None))
                else:
                    island.handle_click_event(e.button, getattr(e, "pos", None))
            elif e.type == pygame.MOUSEWHEEL:
                island.wheel(e.y)
            elif e.type == pygame.DROPFILE:                  # file được thả vào cửa sổ
                island.add_file(e.file)
            elif e.type in (pygame.KEYDOWN, pygame.KEYUP, pygame.TEXTINPUT):
                settings.handle_event(e)

        if time.monotonic() >= next_top:                     # mỗi 0.5 giây tự giành lại vị trí trên cùng
            # Nếu đang mở hộp thoại chọn file của hệ thống thì không cưỡng chế z-order tránh che mất dialog
            if not getattr(settings, "modal_dialog_active", False):
                keep_on_top(hwnd)
                if settings.visible or settings.state == "closing":
                    keep_on_top(settings.hwnd)               # cửa sổ Cài đặt / giọt nước luôn nằm trên island (không bị island giành lại)
            next_top = time.monotonic() + 0.5

        poll_mouse()                                         # đọc trạng thái chuột 1 lần duy nhất/frame, cache lại để island và settings dùng chung (tránh miss click nhanh của remote desktop)
        island.update()                                      # cập nhật trạng thái, hover, kéo file, animation
        island.draw(window.get_surface())                    # vẽ lên surface của Window
        window.flip()                                        # đẩy surface lên màn hình
        settings.update()
        settings.draw()                                      # chỉ vẽ khi cửa sổ Cài đặt đang mở / đang chạy hiệu ứng
        wave_animating = abs(getattr(island, "play_t", 0.0) - (1.0 if island.playing else 0.0)) > 0.005
        clock.tick(60 if (island.animating or settings.animating or island.playing or wave_animating or island.hover or time.monotonic() < island.shake_until) else 30)   # nghỉ bớt khi không có gì chuyển động

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
