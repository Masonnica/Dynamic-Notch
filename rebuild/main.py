import ctypes
from ctypes import wintypes
import pygame

class App:
    def __init__(self):
        pygame.init()
        KEY = (255, 0, 128)
        TITLE = "Dynamic Notch"  # Tiêu đề phải độc nhất để tìm đúng cửa sổ
        self.win = pygame.Window(TITLE, (400, 400), borderless=True, fullscreen_desktop=True)
        self.win.always_on_top = True
        screen = self.win.get_surface()
        
        user32 = ctypes.windll.user32
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND  # HWND 64-bit, tránh bị cắt thành 32-bit
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowLongW.restype = ctypes.c_long
        user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, ctypes.c_ubyte, wintypes.DWORD]
        
        hwnd = user32.FindWindowW(None, TITLE)  # Tìm HWND theo tiêu đề
        if not hwnd:
            raise RuntimeError("Không tìm thấy cửa sổ")
        
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        LWA_COLORKEY = 0x1
        colorref = KEY[0] | (KEY[1] << 8) | (KEY[2] << 16)  # RGB -> COLORREF (thứ tự BGR)
        
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)  # Đọc extended style hiện tại
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)  # Bật chế độ layered
        user32.SetLayeredWindowAttributes(hwnd, colorref, 0, LWA_COLORKEY)  # Màu KEY thành trong suốt
        
        clock = pygame.time.Clock()
        dragging = True
        offset = (0, 0)
        running = True
        
        while running:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    running = False
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    mx, my = pygame.mouse.get_pos(desktop=True)
                    wx, wy = self.win.position
                    offset = (mx - wx, my - wy)
                    dragging = True
                elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                    dragging = False

            if dragging:
                mx, my = pygame.mouse.get_pos(desktop=True)
                self.win.position = (mx - offset[0], my - offset[1])

            screen.fill(KEY)
            pygame.draw.circle(screen, (255, 200, 0), (200, 200), 80)
            self.win.flip()
            clock.tick(60)

        pygame.quit()

App()
