import ctypes
from ctypes import wintypes
import pygame

KEY = (55, 66, 77)

class Winow:
    def __init__(self, title: str, always_on_top: bool, utility: bool):
        pygame.init()
        
        self.win = pygame.Window(title, (400, 400), borderless=True, fullscreen_desktop=True)
        self.win.always_on_top = always_on_top
        self.win.utility = utility
        self.screen = self.win.get_surface()
        
        user32 = ctypes.windll.user32
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND  # HWND 64-bit, tránh bị cắt thành 32-bit
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowLongW.restype = ctypes.c_long
        user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, ctypes.c_ubyte, wintypes.DWORD]
        
        hwnd = user32.FindWindowW(None, title)  # Tìm HWND theo tiêu đề
        if not hwnd:
            raise RuntimeError("Không tìm thấy cửa sổ")
        
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        LWA_COLORKEY = 0x1
        colorref = KEY[0] | (KEY[1] << 8) | (KEY[2] << 16)  # RGB -> COLORREF (thứ tự BGR)
        
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)  # Đọc extended style hiện tại
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)  # Bật chế độ layered
        user32.SetLayeredWindowAttributes(hwnd, colorref, 0, LWA_COLORKEY)  # Màu KEY thành trong suốt
        
        self.clock = pygame.time.Clock()
        self.running = True
    
    @property
    def always_on_top(self):
        return self.win.always_on_top
    
    @always_on_top.setter
    def always_on_top(self, value: bool):
        self.win.always_on_top = value
    
    @property
    def utility(self):
        return self.win.utility
    
    @always_on_top.setter
    def utility(self, value: bool):
        self.win.utility = value
    
    def run(self):
        while self.running:
            self.win
