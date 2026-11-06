"""
Các hàm gọi API Windows (Win32, Shell, OLE Drag & Drop, Icon trích xuất).
"""
import os
import math
import time
import ctypes
import threading
from ctypes import wintypes
from pathlib import Path
import pygame

from .drawing import draw_capsule
from config import (
    BLOB_S, BLOB_SS, BLOB_R, BLOB_OFF, BLOB_MAX, BLOB_FADE
)

# ------------------------ Khai báo các thư viện Win32 ------------------------
user32 = ctypes.windll.user32                # cửa sổ, chuột, vẽ icon
gdi32 = ctypes.windll.gdi32                  # bitmap, device context
shell32 = ctypes.windll.shell32              # icon hệ thống, PIDL, data object của shell
ole32 = ctypes.windll.ole32                  # OLE drag-drop

VOID = ctypes.c_void_p                       # viết tắt cho con trỏ/handle 64-bit
user32.GetDC.argtypes, user32.GetDC.restype = [wintypes.HWND], VOID
user32.ReleaseDC.argtypes = [wintypes.HWND, VOID]
user32.DrawIconEx.argtypes = [VOID, ctypes.c_int, ctypes.c_int, VOID, ctypes.c_int, ctypes.c_int,
                              wintypes.UINT, VOID, wintypes.UINT]
user32.DestroyIcon.argtypes = [VOID]
gdi32.CreateCompatibleDC.argtypes, gdi32.CreateCompatibleDC.restype = [VOID], VOID
gdi32.CreateDIBSection.argtypes = [VOID, VOID, wintypes.UINT, ctypes.POINTER(VOID), VOID, wintypes.DWORD]
gdi32.CreateDIBSection.restype = VOID
gdi32.SelectObject.argtypes, gdi32.SelectObject.restype = [VOID, VOID], VOID
gdi32.DeleteObject.argtypes = [VOID]
gdi32.DeleteDC.argtypes = [VOID]


# ------------------------------ Hàm Win32 phụ --------------------------------
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD), ('biWidth', wintypes.LONG), ('biHeight', wintypes.LONG),
        ('biPlanes', wintypes.WORD), ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', wintypes.LONG), ('biYPelsPerMeter', wintypes.LONG),
        ('biClrUsed', wintypes.DWORD), ('biClrImportant', wintypes.DWORD),
    ]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', wintypes.DWORD * 3)]

class BLENDFUNCTION(ctypes.Structure):
    """Tham số trộn alpha cho UpdateLayeredWindow."""
    _fields_ = [
        ('BlendOp', ctypes.c_ubyte),
        ('BlendFlags', ctypes.c_ubyte),
        ('SourceConstantAlpha', ctypes.c_ubyte),
        ('AlphaFormat', ctypes.c_ubyte)
    ]

user32.UpdateLayeredWindow.argtypes = [
    VOID, VOID, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE),
    VOID, ctypes.POINTER(wintypes.POINT), wintypes.COLORREF,
    ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD
]


class LayeredPresenter:
    """Quản lý hiển thị bề mặt 32-bit ARGB lên cửa sổ layered bằng Win32 UpdateLayeredWindow.
    Cho phép nền bán trong suốt nhưng toàn bộ nội dung (chữ, icon, nút) giữ nguyên 100% độ sắc nét."""
    def __init__(self, hwnd, width, height):
        self.hwnd = hwnd
        self.width = width
        self.height = height

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height   # top-down DIB
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0

        self.hdc_screen = user32.GetDC(0)
        self.hdc_mem = gdi32.CreateCompatibleDC(self.hdc_screen)
        self.ppvBits = ctypes.c_void_p()
        self.hbmp = gdi32.CreateDIBSection(self.hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(self.ppvBits), 0, 0)
        gdi32.SelectObject(self.hdc_mem, self.hbmp)

        self.pt_src = wintypes.POINT(0, 0)
        self.size = wintypes.SIZE(width, height)
        self.blend = BLENDFUNCTION(0, 0, 255, 1)   # AC_SRC_ALPHA = 1

    def present(self, surf):
        """Chuyển đổi Surface SRCALPHA sang BGRA premultiplied và đẩy thẳng lên DWM qua UpdateLayeredWindow."""
        try:
            # pygame-ce hỗ trợ tobytes("raw", ...) hoặc xuất trực tiếp buffer
            # Nếu có numpy hoạt động chuẩn
            import numpy as np
            raw = pygame.image.tobytes(surf, "BGRA")
            arr = np.frombuffer(raw, dtype=np.uint8).reshape((self.height, self.width, 4)).copy()
            a = arr[:, :, 3].astype(np.float32) / 255.0
            arr[:, :, 0] = (arr[:, :, 0] * a).astype(np.uint8)
            arr[:, :, 1] = (arr[:, :, 1] * a).astype(np.uint8)
            arr[:, :, 2] = (arr[:, :, 2] * a).astype(np.uint8)
            ctypes.memmove(self.ppvBits, arr.ctypes.data, self.width * self.height * 4)
        except Exception:
            # Fallback thuần C-types / bytearray cực nhanh, KHÔNG phụ thuộc vào numpy
            # Tránh 100% lỗi thiếu submodule numpy trên các máy khác
            raw = bytearray(pygame.image.tobytes(surf, "BGRA"))
            # Premultiply alpha qua ctypes uint32 hoặc mảng byte
            n_pixels = self.width * self.height
            for i in range(0, n_pixels * 4, 4):
                a = raw[i + 3]
                if a == 0:
                    raw[i] = raw[i + 1] = raw[i + 2] = 0
                elif a < 255:
                    raw[i] = (raw[i] * a) // 255
                    raw[i + 1] = (raw[i + 1] * a) // 255
                    raw[i + 2] = (raw[i + 2] * a) // 255
            c_buf = (ctypes.c_char * len(raw)).from_buffer(raw)
            ctypes.memmove(self.ppvBits, c_buf, len(raw))

        user32.UpdateLayeredWindow(
            self.hwnd, self.hdc_screen, None, ctypes.byref(self.size),
            self.hdc_mem, ctypes.byref(self.pt_src), 0, ctypes.byref(self.blend), 2
        )

    def close(self):
        try:
            if self.hdc_screen:
                user32.ReleaseDC(0, self.hdc_screen)
            if self.hdc_mem:
                gdi32.DeleteDC(self.hdc_mem)
            if self.hbmp:
                gdi32.DeleteObject(self.hbmp)
        except Exception:
            pass


def setup_native_window(title, use_colorkey=True):
    """Biến cửa sổ pygame thành cửa sổ trong suốt (colorkey hoặc layered alpha), luôn nằm trên, không hiện trên taskbar."""
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]            # khai báo kiểu tham số để 64-bit an toàn
    user32.FindWindowW.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, ctypes.c_ubyte, wintypes.DWORD]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    hwnd = user32.FindWindowW(None, title)                   # tìm HWND theo tiêu đề cửa sổ
    if not hwnd:
        return None                                          # không tìm thấy thì bỏ qua (vẫn chạy được, chỉ không trong suốt)
    GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TOOLWINDOW = -20, 0x00080000, 0x00000080
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)         # đọc extended style hiện tại
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TOOLWINDOW)  # bật layered + ẩn khỏi taskbar
    if use_colorkey:
        user32.SetLayeredWindowAttributes(hwnd, 0x00FF00FF, 0, 0x1)   # pixel màu KEY (magenta) -> trong suốt + chuột xuyên qua
    # HWND_TOPMOST = -1 ; cờ: NOSIZE | NOMOVE | NOACTIVATE | FRAMECHANGED
    user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0020)
    return hwnd                                              # trả về HWND để vòng lặp chính giữ topmost định kỳ


def keep_on_top(hwnd):
    """Giành lại vị trí trên cùng: Windows có thể hạ cửa sổ xuống khi taskbar hoặc app khác (cũng topmost) chen lên."""
    if hwnd:
        # HWND_TOPMOST = -1 ; cờ: NOSIZE | NOMOVE | NOACTIVATE | SHOWWINDOW (không cướp focus của app đang dùng)
        user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0040)


def move_window(hwnd, x, y):
    """Dời cửa sổ tới (x, y) trên màn hình, giữ nguyên kích thước và trạng thái luôn-trên-cùng, không cướp focus."""
    if hwnd:
        # HWND_TOPMOST = -1 ; cờ: NOSIZE (0x1) | NOACTIVATE (0x10) | SHOWWINDOW (0x40)
        user32.SetWindowPos(hwnd, wintypes.HWND(-1), x, y, 0, 0, 0x0001 | 0x0010 | 0x0040)


def dwm_flush():
    """Chờ Desktop Window Manager ghép xong khung hình hiện tại (để khung trong suốt đầu tiên chắc chắn đã lên
    trước khi dời cửa sổ vào màn hình)."""
    try:
        ctypes.windll.dwmapi.DwmFlush()
    except Exception:
        pass                                                 # không có DWM (rất hiếm) thì bỏ qua


def cursor_pos():
    """Vị trí chuột trên toàn màn hình (không phụ thuộc cửa sổ có đang focus hay không)."""
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def mouse_down(button):
    """Nút chuột có đang được giữ ở bất kỳ đâu không. button: 1 = trái, 3 = phải (theo nghĩa logic, có tính cả đổi tay)."""
    swapped = bool(user32.GetSystemMetrics(23))              # SM_SWAPBUTTON: người dùng đã đổi nút trái/phải?
    vk = 0x01 if (button == 1) != swapped else 0x02          # VK_LBUTTON = 1, VK_RBUTTON = 2
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)        # bit cao = đang được nhấn


def key_down(vk_code):
    """Kiểm tra một phím ảo bất kỳ có đang được nhấn trên toàn hệ điều hành hay không (0x8000 = đang nhấn)."""
    return bool(user32.GetAsyncKeyState(vk_code) & 0x8000)


# ------------------------- Icon file của hệ thống ---------------------------
class SHFILEINFOW(ctypes.Structure):
    """Cấu trúc kết quả của SHGetFileInfoW (chỉ dùng trường hIcon)."""
    _fields_ = [("hIcon", VOID), ("iIcon", ctypes.c_int), ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", wintypes.WCHAR * 260), ("szTypeName", wintypes.WCHAR * 80)]


class BITMAPINFOHEADER(ctypes.Structure):
    """Tiêu đề bitmap dùng để tạo DIB 32-bit."""
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


shell32.SHGetFileInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(SHFILEINFOW),
                                   wintypes.UINT, wintypes.UINT]
shell32.SHGetFileInfoW.restype = ctypes.c_size_t
PER_FILE_ICON_EXT = {".exe", ".lnk", ".ico", ".url", ".msi", ".scr", ".cur"}   # đuôi mà mỗi file có icon riêng


def icon_cache_key(path):
    """Các file cùng đuôi thường chung icon nên cache theo đuôi; file exe/lnk/... cache theo từng file."""
    p = Path(path)
    if p.is_dir():
        return "<dir>"
    ext = p.suffix.lower()
    return path if (not ext or ext in PER_FILE_ICON_EXT) else ext


def _draw_icon(hicon, size, bg_byte):
    """Vẽ HICON lên bitmap 32-bit có nền đặc (đen=0x00 hoặc trắng=0xFF) rồi trả về bytes BGRA."""
    hdc_screen = user32.GetDC(None)                          # DC của màn hình để tạo DC tương thích
    hdc = gdi32.CreateCompatibleDC(hdc_screen)               # DC bộ nhớ để vẽ
    bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), size, -size, 1, 32, 0, 0, 0, 0, 0, 0)   # -size = ảnh từ trên xuống
    bits = VOID()                                            # con trỏ tới vùng pixel do Windows cấp
    hbmp = gdi32.CreateDIBSection(hdc_screen, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    old = gdi32.SelectObject(hdc, hbmp)                      # gắn bitmap vào DC
    try:
        ctypes.memset(bits.value, bg_byte, size * size * 4)  # tô nền đen hoặc trắng
        user32.DrawIconEx(hdc, 0, 0, hicon, size, size, 0, None, 0x0003)   # DI_NORMAL: vẽ icon (có alpha) lên nền
        return ctypes.string_at(bits.value, size * size * 4)               # sao chép pixel ra bytes
    finally:
        gdi32.SelectObject(hdc, old)                         # dọn dẹp tài nguyên GDI
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc)
        user32.ReleaseDC(None, hdc_screen)


def get_system_icon(path):
    """Lấy icon thật của Windows cho file/thư mục thành pygame.Surface có alpha (None nếu lỗi)."""
    info = SHFILEINFOW()
    # 0x100 = SHGFI_ICON (kèm SHGFI_LARGEICON mặc định): hỏi shell icon đúng với file này
    if not shell32.SHGetFileInfoW(path, 0, ctypes.byref(info), ctypes.sizeof(info), 0x100) or not info.hIcon:
        return None
    size = max(32, min(48, user32.GetSystemMetrics(11)))     # SM_CXICON: kích thước icon lớn của hệ thống
    try:
        black = _draw_icon(info.hIcon, size, 0x00)           # icon vẽ trên nền đen
        white = _draw_icon(info.hIcon, size, 0xFF)           # icon vẽ trên nền trắng
    finally:
        user32.DestroyIcon(info.hIcon)                       # giải phóng HICON
    # Hai ảnh khác nhau ở phần trong suốt => suy ra alpha: alpha = 255 - (trắng - đen)
    out = bytearray(size * size * 4)                         # kết quả RGBA, mặc định trong suốt hoàn toàn
    for i in range(0, size * size * 4, 4):
        bb, bg_, br = black[i], black[i + 1], black[i + 2]   # kênh B, G, R trên nền đen
        wb, wg, wr = white[i], white[i + 1], white[i + 2]    # kênh B, G, R trên nền trắng
        a = 255 - ((wr - br) + (wg - bg_) + (wb - bb)) // 3  # độ đục của pixel
        if a <= 0:
            continue                                         # pixel trong suốt
        a = min(a, 255)
        out[i] = min(255, br * 255 // a)                     # R (bỏ premultiply vì nền đen làm tối màu)
        out[i + 1] = min(255, bg_ * 255 // a)                # G
        out[i + 2] = min(255, bb * 255 // a)                 # B
        out[i + 3] = a                                       # A
    raw = bytes(out)
    return pygame.image.frombuffer(raw, (size, size), "RGBA").convert_alpha()


# ------------------- Giọt nước đen đi theo chuột khi kéo file ------------------
class MSG(ctypes.Structure):
    """Thông điệp cửa sổ (để luồng giọt nước bơm message cho cửa sổ của nó)."""
    _fields_ = [("hwnd", VOID), ("message", wintypes.UINT), ("wParam", VOID), ("lParam", VOID),
                ("time", wintypes.DWORD), ("pt", wintypes.POINT)]


user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, VOID, VOID, VOID, VOID]
user32.CreateWindowExW.restype = VOID
user32.ShowWindow.argtypes = [VOID, ctypes.c_int]
user32.DestroyWindow.argtypes = [VOID]
user32.PeekMessageW.argtypes = [ctypes.POINTER(MSG), VOID, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]


def render_blob_frame(big, tx, ty, px, py, grow):
    """Vẽ 1 khung hình giọt nước. (tx,ty) = đầu bám theo chuột, (px,py) = đuôi chạy trễ, grow = 0..1 (co giãn).
    Trả về (bytes BGRA, x, y góc trên-trái của cửa sổ giọt nước trên màn hình)."""
    d = math.hypot(tx - px, ty - py)
    stretch = min(d / BLOB_MAX, 1.0)                         # 0 = đứng yên, 1 = kéo căng tối đa
    r1 = max(1.0, BLOB_R * grow * (1 - 0.12 * stretch))      # đầu hơi nhỏ lại khi bị kéo căng
    r2 = max(1.0, max(3.0, BLOB_R * (1 - 0.55 * stretch)) * grow)   # đuôi mảnh dần như chất lỏng bị kéo
    wx, wy = int((tx + px) / 2 - BLOB_S / 2), int((ty + py) / 2 - BLOB_S / 2)   # cửa sổ nằm giữa đầu và đuôi
    big.fill((0, 0, 0, 0))                                   # xoá khung hình cũ (trong suốt hoàn toàn)
    draw_capsule(big, ((tx - wx) * BLOB_SS, (ty - wy) * BLOB_SS), r1 * BLOB_SS,
                 ((px - wx) * BLOB_SS, (py - wy) * BLOB_SS), r2 * BLOB_SS, (0, 0, 0, 255))
    small = pygame.transform.smoothscale(big, (BLOB_S, BLOB_S))      # thu nhỏ => mép mượt
    # Màu đen nên không cần nhân trước alpha (premultiplied) như UpdateLayeredWindow yêu cầu
    return pygame.image.tobytes(small, "BGRA"), wx, wy


class DragBlob:
    """Cửa sổ giọt nước đen: đầu bám con trỏ, đuôi chạy theo trễ như chất lỏng bị kéo."""

    def __init__(self, origin):
        self.origin = origin                                 # chỗ nhấn chuột lúc bắt đầu kéo (giọt nước "tách ra" từ đây)
        self.stop_flag = threading.Event()                   # bật lên khi thả chuột
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_flag.set()                                 # luồng tự thu nhỏ giọt nước rồi huỷ cửa sổ, không chặn luồng chính

    def _run(self):
        S = BLOB_S
        hdc_screen = hdc_mem = hbmp = old = hwnd = None
        try:
            hdc_screen = user32.GetDC(None)                  # DC màn hình
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)   # DC bộ nhớ chứa ảnh giọt nước
            bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), S, -S, 1, 32, 0, 0, 0, 0, 0, 0)   # DIB 32-bit từ trên xuống
            bits = VOID()                                    # con trỏ tới vùng pixel
            hbmp = gdi32.CreateDIBSection(hdc_screen, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
            old = gdi32.SelectObject(hdc_mem, hbmp)
            # LAYERED | TRANSPARENT (chuột xuyên qua) | TOPMOST | TOOLWINDOW | NOACTIVATE ; WS_POPUP = 0x80000000
            ex = 0x00080000 | 0x00000020 | 0x00000008 | 0x00000080 | 0x08000000
            hwnd = user32.CreateWindowExW(ex, "Static", None, 0x80000000, 0, 0, S, S, None, None, None, None)
            if not hwnd:
                return
            user32.ShowWindow(hwnd, 4)                       # SW_SHOWNOACTIVATE: hiện mà không cướp focus

            px, py = self.origin[0] + BLOB_OFF, self.origin[1] + BLOB_OFF   # đuôi bắt đầu từ chỗ nhấn
            tx, ty = px, py                                  # đầu = vị trí con trỏ (cập nhật mỗi khung)
            big = pygame.Surface((S * BLOB_SS, S * BLOB_SS), pygame.SRCALPHA)   # bề mặt vẽ to (siêu lấy mẫu)
            pt, src, size = wintypes.POINT(), wintypes.POINT(0, 0), wintypes.SIZE(S, S)
            blend = BLENDFUNCTION(0, 0, 255, 1)              # AC_SRC_OVER + AC_SRC_ALPHA: dùng alpha từng pixel
            msg = MSG()
            t0 = last = time.monotonic()
            closing_at = None                                # thời điểm bắt đầu thu nhỏ (khi thả chuột)
            while True:
                now = time.monotonic()
                dt = min(now - last, 0.05)                   # thời gian từ khung trước (chặn tối đa 50ms)
                last = now
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):   # bơm message (PM_REMOVE = 1)
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                if closing_at is None and self.stop_flag.is_set():
                    closing_at = now                         # đã thả chuột -> bắt đầu thu nhỏ
                if closing_at is None:
                    cx, cy = cursor_pos()                    # vị trí con trỏ trên toàn màn hình
                    tx, ty = cx + BLOB_OFF, cy + BLOB_OFF
                elif now - closing_at > BLOB_FADE:
                    break                                    # thu nhỏ xong -> thoát vòng lặp
                k = 1 - math.exp(-dt * 16)                   # độ "trễ" của đuôi (số càng nhỏ càng trễ)
                px += (tx - px) * k
                py += (ty - py) * k
                d = math.hypot(tx - px, ty - py)
                if d > BLOB_MAX:                             # đuôi không được tụt xa hơn độ dài tối đa
                    px, py = tx - (tx - px) * BLOB_MAX / d, ty - (ty - py) * BLOB_MAX / d
                grow = min(1.0, (now - t0) / 0.12)           # phồng lên trong 0.12s đầu như giọt nước vừa tách ra
                if closing_at is not None:
                    grow *= max(0.0, 1 - (now - closing_at) / BLOB_FADE)   # thu nhỏ dần khi thả
                data, wx, wy = render_blob_frame(big, tx, ty, px, py, grow)
                ctypes.memmove(bits.value, data, S * S * 4)  # chép pixel vào bitmap của cửa sổ
                pt.x, pt.y = wx, wy
                user32.UpdateLayeredWindow(hwnd, hdc_screen, ctypes.byref(pt), ctypes.byref(size),
                                           hdc_mem, ctypes.byref(src), 0, ctypes.byref(blend), 2)   # 2 = ULW_ALPHA
                time.sleep(0.008)                            # ~120 khung hình/giây
        except Exception:
            pass                                             # lỗi vẽ giọt nước không được làm hỏng việc kéo file
        finally:
            if hwnd:
                user32.DestroyWindow(hwnd)                   # phải huỷ cửa sổ ngay trong luồng đã tạo ra nó
            if hdc_mem and old:
                gdi32.SelectObject(hdc_mem, old)
            if hbmp:
                gdi32.DeleteObject(hbmp)
            if hdc_mem:
                gdi32.DeleteDC(hdc_mem)
            if hdc_screen:
                user32.ReleaseDC(None, hdc_screen)


# -------------------- Kéo file ra ngoài bằng OLE DoDragDrop -------------------
IID_IUNKNOWN = bytes.fromhex("0000000000000000c000000000000046")      # GUID của IUnknown
IID_IDROPSOURCE = bytes.fromhex("2101000000000000c000000000000046")   # GUID của IDropSource
IID_IDATAOBJECT = bytes.fromhex("0e01000000000000c000000000000046")   # GUID của IDataObject

ole32.OleInitialize.argtypes, ole32.OleInitialize.restype = [VOID], ctypes.c_long
ole32.DoDragDrop.argtypes = [VOID, VOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
ole32.DoDragDrop.restype = ctypes.c_long
ole32.CoTaskMemFree.argtypes = [VOID]
shell32.SHParseDisplayName.argtypes = [wintypes.LPCWSTR, VOID, ctypes.POINTER(VOID), wintypes.ULONG,
                                       ctypes.POINTER(wintypes.ULONG)]
shell32.SHParseDisplayName.restype = ctypes.c_long
shell32.ILFindLastID.argtypes, shell32.ILFindLastID.restype = [VOID], VOID
shell32.SHCreateDataObject.argtypes = [VOID, wintypes.UINT, ctypes.POINTER(VOID), VOID, VOID, ctypes.POINTER(VOID)]
shell32.SHCreateDataObject.restype = ctypes.c_long

# IDropSource là đối tượng COM tối giản mà Windows hỏi: "tiếp tục kéo hay thả?" - ta tự dựng bảng hàm ảo bằng ctypes
QI_T = ctypes.WINFUNCTYPE(ctypes.c_long, VOID, VOID, ctypes.POINTER(VOID))      # QueryInterface
REF_T = ctypes.WINFUNCTYPE(ctypes.c_ulong, VOID)                                # AddRef / Release
QCD_T = ctypes.WINFUNCTYPE(ctypes.c_long, VOID, wintypes.BOOL, wintypes.DWORD)  # QueryContinueDrag
GF_T = ctypes.WINFUNCTYPE(ctypes.c_long, VOID, wintypes.DWORD)                  # GiveFeedback


def _qi(this, riid, ppv):
    if ctypes.string_at(riid, 16) in (IID_IUNKNOWN, IID_IDROPSOURCE):   # chỉ hỗ trợ 2 giao diện này
        ppv[0] = this
        return 0                                             # S_OK
    ppv[0] = None
    return -2147467262                                       # E_NOINTERFACE


def _addref(this):
    return 1                                                 # đối tượng tĩnh, không bao giờ bị huỷ


def _release(this):
    return 1


def _query_continue_drag(this, esc_pressed, key_state):
    if esc_pressed:
        return 0x00040101                                    # DRAGDROP_S_CANCEL: nhấn Esc thì huỷ
    if not (key_state & 0x1):                                # MK_LBUTTON: thả chuột trái thì thả file
        return 0x00040100                                    # DRAGDROP_S_DROP
    return 0                                                 # S_OK: tiếp tục kéo


def _give_feedback(this, effect):
    return 0x00040102                                        # DRAGDROP_S_USEDEFAULTCURSORS: dùng con trỏ mặc định


_DS_FUNCS = (QI_T(_qi), REF_T(_addref), REF_T(_release), QCD_T(_query_continue_drag), GF_T(_give_feedback))  # giữ tham chiếu để không bị thu gom
_DS_VTBL = (VOID * 5)(*[ctypes.cast(f, VOID).value for f in _DS_FUNCS])     # bảng hàm ảo
class _DropSource(ctypes.Structure):
    _fields_ = [("vtbl", VOID)]                              # đối tượng COM = con trỏ tới bảng hàm ảo
_DROP_SOURCE = _DropSource(ctypes.addressof(_DS_VTBL))


def _com_release(obj):
    """Gọi IUnknown::Release (phần tử thứ 3 của bảng hàm ảo) để trả đối tượng COM."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(VOID))[0]
    fn = ctypes.cast(vtbl, ctypes.POINTER(VOID))[2]
    ctypes.WINFUNCTYPE(ctypes.c_ulong, VOID)(fn)(obj)


def _do_drag(path, origin):
    """Bắt đầu kéo-thả file ra ngoài. Trả về False nếu luồng này không khởi tạo được OLE."""
    hr = ole32.OleInitialize(None)                           # DoDragDrop yêu cầu OLE (STA) đã khởi tạo
    if hr not in (0, 1):                                     # 0 = S_OK, 1 = S_FALSE (đã khởi tạo rồi)
        return False
    try:
        path = os.path.abspath(path)
        parent, child = VOID(), VOID()                       # PIDL của thư mục cha và của file
        if shell32.SHParseDisplayName(os.path.dirname(path), None, ctypes.byref(parent), 0, None) != 0:
            return True
        if shell32.SHParseDisplayName(path, None, ctypes.byref(child), 0, None) != 0:
            ole32.CoTaskMemFree(parent)
            return True
        try:
            last = shell32.ILFindLastID(child)               # phần PIDL con (tương đối so với thư mục cha)
            items = (VOID * 1)(last)
            data_obj = VOID()
            iid = (ctypes.c_ubyte * 16).from_buffer_copy(IID_IDATAOBJECT)
            # Nhờ shell tạo IDataObject chứa file: chính là thứ Explorer dùng khi bạn kéo file
            if shell32.SHCreateDataObject(parent, 1, items, None, ctypes.byref(iid), ctypes.byref(data_obj)) == 0 \
                    and data_obj.value:
                effect = wintypes.DWORD(0)
                blob = DragBlob(origin)                      # giọt nước đen đi theo chuột trong lúc kéo
                blob.start()
                try:
                    # 1 = COPY, 4 = LINK. Không cho MOVE để file gốc không bao giờ bị di chuyển/mất
                    ole32.DoDragDrop(data_obj, ctypes.byref(_DROP_SOURCE), 1 | 4, ctypes.byref(effect))
                finally:
                    blob.stop()                              # thả chuột (hoặc huỷ) -> giọt nước thu nhỏ rồi biến mất
                _com_release(data_obj)
        finally:
            ole32.CoTaskMemFree(child)                       # giải phóng 2 PIDL
            ole32.CoTaskMemFree(parent)
        return True
    finally:
        ole32.OleUninitialize()                              # cân bằng với OleInitialize


def start_file_drag(path, origin):
    """Kéo file ra ngoài. Hàm chặn tới khi thả chuột; nếu luồng chính không dùng được OLE thì thử luồng riêng."""
    if not _do_drag(path, origin):
        threading.Thread(target=_do_drag, args=(path, origin), daemon=True).start()


class _SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]


def battery_status():
    """(phần trăm pin 0..100, đang sạc?) hoặc None nếu máy không có pin / không đọc được."""
    try:
        st = _SYSTEM_POWER_STATUS()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):
            return None
        if st.BatteryFlag & 128 or st.BatteryLifePercent > 100:   # 128 = không có pin, 255 = không rõ
            return None
        return st.BatteryLifePercent, st.ACLineStatus == 1
    except Exception:
        return None


def get_clipboard_text():
    """Lấy nội dung văn bản từ clipboard của Windows."""
    try:
        if not user32.OpenClipboard(0):
            return ""
        try:
            CF_UNICODETEXT = 13
            h_glb = user32.GetClipboardData(CF_UNICODETEXT)
            if not h_glb:
                return ""
            kernel32 = ctypes.windll.kernel32
            kernel32.GlobalLock.restype = ctypes.c_void_p
            ptr = kernel32.GlobalLock(h_glb)
            if not ptr:
                return ""
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(h_glb)
        finally:
            user32.CloseClipboard()
    except Exception:
        return ""


# -------------------------- Khởi động cùng Windows --------------------------
def is_startup_enabled(app_name="DynamicNotch"):
    """Kiểm tra xem ứng dụng đã được đăng ký khởi động cùng Windows chưa."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ
        )
        try:
            val, _ = winreg.QueryValueEx(key, app_name)
            return bool(val)
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def set_startup_enabled(enabled, app_name="DynamicNotch"):
    """Bật/tắt tính năng khởi động cùng Windows thông qua Registry Run key."""
    try:
        import sys
        import winreg
        from pathlib import Path

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE
        )
        try:
            if enabled:
                # Nếu chạy từ file .exe được build
                if getattr(sys, "frozen", False):
                    cmd = f'"{sys.executable}"'
                else:
                    # Nếu chạy script Python (.py)
                    # Dùng pythonw.exe nếu có để không bị hiện console đen khi khởi động
                    py_exe = sys.executable
                    pyw_exe = Path(py_exe).parent / "pythonw.exe"
                    runner = str(pyw_exe) if pyw_exe.exists() else py_exe

                    main_file = Path(__file__).resolve().parent.parent / "main.py"
                    cmd = f'"{runner}" "{main_file}"'

                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            return True
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False
