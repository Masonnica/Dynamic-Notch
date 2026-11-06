"""
Cấu hình và hằng số cho Dynamic Island.
"""
from pathlib import Path

# --- Cửa sổ & Kích thước ---
TITLE = "DynamicNotch"                      # tiêu đề cửa sổ (dùng để tìm HWND bằng FindWindowW)
COMPACT_W, COMPACT_H = 220, 48               # kích thước thân island khi thu gọn
# Mỗi tab một cỡ thân (chưa tính phần kéo dài của thanh điều hướng). Đảo animate sang cỡ của tab đang chọn.
MUSIC_W, MUSIC_H = 660, 285                  # nhạc: (660x285) chiều ngang rộng rãi cho tên bài & lyrics
CAL_W, CAL_H = 540, 296                      # lịch: tăng thêm 60px chiều ngang cho phần thông tin sự kiện (480 -> 540)
SHELF_W, SHELF_H = 480, 296                  # ngăn xếp
PAGE_SIZES = ((MUSIC_W, MUSIC_H), (CAL_W, CAL_H), (SHELF_W, SHELF_H))
EXPAND_W = max(w for w, _ in PAGE_SIZES)     # vùng nội dung cửa sổ = bề rộng lớn nhất
EXPAND_H = max(h for _, h in PAGE_SIZES)     # vùng nội dung cửa sổ = chiều cao lớn nhất
NAV_H = 32                                   # chiều cao dải điều hướng ở đáy island (lúc chỉ hiện các chấm)
NAV_EXTRA = 22                               # island kéo dài thêm bấy nhiêu px khi rê chuột vào dải điều hướng (chấm -> icon)
CONTENT_DY = -32                             # nội dung các tab dịch lên (âm) vì không còn thanh tab ở phía trên
WIN_H = EXPAND_H + NAV_EXTRA                 # chiều cao cửa sổ: đủ chỗ cho island ở trạng thái kéo dài nhất
EAR = 27                                     # bán kính 2 "tai" cong ở góc trên, nơi island nối vào mép màn hình
WIN_W = EXPAND_W + 2 * EAR                   # cửa sổ rộng hơn thân island để chừa chỗ cho 2 tai
TOP_MARGIN = 0                               # 0 = dính sát mép trên màn hình như tai thỏ thật

# --- File lưu trữ dữ liệu ---
SETTINGS_FILE = Path.home() / ".dynamic_island_settings.json"              # nơi lưu cài đặt
SHELF_FILE = Path.home() / ".dynamic_island_shelf.json"                    # nơi lưu ngăn xếp file
GOOGLE_PREFS_FILE = Path.home() / ".dynamic_island_calendar_prefs.json"   # tuỳ chọn bật/tắt các loại lịch
CALENDARS_DIR = Path.home() / ".dynamic_island_calendars"                  # thư mục lưu trữ file .ics các lịch

# --- Bảng màu ---
KEY = (255, 0, 255)                          # màu magenta làm "màu trong suốt" (colorkey)
BLACK = (4, 6, 10)                           # nền island
PANEL = (28, 28, 30)                         # nền nút/ô
PANEL_HOVER = (50, 50, 54)                   # nền nút khi rê chuột
ACCENT = (10, 132, 255)                      # xanh nhấn (ngày đang chọn, tab đang chọn)
ACCENT_SOFT = (36, 84, 140)                  # xanh dịu hơn: ngày hôm nay khi không được chọn
GREEN = (48, 209, 88)                        # vòng tròn bên trái thanh thu nhỏ
ORANGE = (255, 159, 10)
CLOSE_RED = (255, 69, 58)                    # nền nút tắt
CLOSE_RED_HOVER = (255, 105, 97)
GEAR_DOT = (52, 96, 156)                     # chấm "xanh đen" của nút Cài đặt khi thanh điều hướng thu nhỏ
GEAR_BG = (26, 50, 88)                       # nền xanh đen của nút Cài đặt khi hiện icon
GEAR_BG_HOVER = (40, 72, 122)
WHITE = (255, 255, 255)
GREY = (150, 150, 155)
DIM = (90, 90, 95)
RED = (255, 95, 87)                          # chủ nhật trên lịch
BADGE_RED = (255, 59, 48)                    # màu huy hiệu số thông báo trên chuông
BADGES = [(255, 159, 10), (48, 209, 88), (10, 132, 255), (191, 90, 242), (255, 69, 58), (100, 210, 255)]

# --- Hiệu ứng mở đầu: giọt nước từ mép trên màn hình lan ra thành hình tai thỏ ---
OFFSCREEN_POS = (-32000, -32000)             # cửa sổ được tạo ở đây (ngoài màn hình) cho tới khi nền trong suốt sẵn sàng
INTRO_DROP = 0.30                            # giây: giọt nước hình thành và treo ở mép trên màn hình
INTRO_SPREAD = 0.34                          # giây: giọt nước lan ra thành hình tai thỏ (hơi vọt quá rồi co lại như chất lỏng)
INTRO_FADE = 0.20                            # giây: nội dung (giờ, chuông...) hiện dần sau khi hình đã thành

# --- Lịch tự đồng bộ ---
REFRESH_SECONDS = 60                        # tự tải lại sự kiện của tháng đang xem mỗi 1 phút

# --- Giọt nước đen đi theo chuột khi kéo file (Drag Blob) ---
BLOB_S = 112                                 # cạnh cửa sổ giọt nước (px)
BLOB_SS = 3                                  # vẽ to gấp 3 rồi thu nhỏ để mép mượt (anti-alias)
BLOB_R = 11.0                                # bán kính "đầu" giọt nước (px)
BLOB_OFF = 16                                # lệch xuống-phải so với con trỏ để không che mũi tên chuột
BLOB_MAX = 46.0                              # độ dài tối đa của "đuôi" (px)
BLOB_FADE = 0.16                             # thời gian giọt nước thu nhỏ khi thả (giây)

# --- Vòng tròn bên trái thanh thu nhỏ ---
# "battery": hiện % pin; "music": hiện tiến độ bài nhạc
RING_SOURCE = "battery"

# --- Phiên bản ứng dụng & Cập nhật tự động ---
APP_VERSION = "1.0.4"                        # Phiên bản hiện tại của app
GITHUB_REPO = "Masonnica/Dynamic-Notch"      # Kho GitHub chính thức

# --- Cửa sổ Cài đặt ---
SET_W, SET_H = 700, 460                      # kích thước cửa sổ cài đặt (chiều ngang tăng thêm 60px: 640 -> 700)
SETTINGS_TITLE = "DynamicIslandSettings"     # tiêu đề cửa sổ (dùng để tìm HWND)
DEFAULT_SETTINGS = {
    "ring_source": RING_SOURCE,              # vòng tròn bên trái: "auto" | "battery" | "music"
    "seconds_mode": "expand",                # hiện giây: "both" (cả 2) | "compact" (thu gọn) | "expand" (mở rộng) | "none" (không hiển thị)
    "show_seconds": True,                    # tương thích ngược
    "show_bell": True,                       # hiện chuông khi có thông báo
    "auto_startup": False,                   # khởi động cùng Windows
    "auto_update": True,                     # tự động kiểm tra và tải cập nhật mới từ GitHub
    "week_start": 0,                         # lịch: tuần bắt đầu từ 0 = Thứ Hai, 6 = Chủ Nhật
    "show_event_dots": True,                 # lịch: chấm màu báo có sự kiện dưới mỗi ngày
    "bg_color": [4, 6, 10],                  # màu nền island (RGB)
    "bg_opacity": 100,                       # độ trong suốt nền island (20..100 %)
}
