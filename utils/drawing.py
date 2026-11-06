"""
Các hàm tiện ích vẽ hình, render chữ và định dạng giao diện.
"""
import math
import pygame
from config import ACCENT, COMPACT_W, COMPACT_H, INTRO_DROP, INTRO_SPREAD, INTRO_FADE


def parse_hex_color(value, default=ACCENT):
    """'#9fe1e7' -> (159, 225, 231); sai định dạng thì dùng màu mặc định."""
    try:
        v = value.lstrip("#")
        return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))
    except Exception:
        return default


def wrap_text(font, text, width):
    """Ngắt chữ thành nhiều dòng sao cho mỗi dòng không rộng quá width px (ngắt theo từ)."""
    lines, cur = [], ""
    for word in text.split():
        test = (cur + " " + word).strip()
        if font.size(test)[0] <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


_EMOJI_FONT_CACHE = {}


def _get_emoji_font(size):
    """Lấy hoặc tạo font Segoe UI Emoji cho cỡ chữ chỉ định."""
    f = _EMOJI_FONT_CACHE.get(size)
    if f is None:
        try:
            # Đường dẫn font emoji chuẩn của Windows
            f = pygame.font.Font("C:/WINDOWS/Fonts/seguiemj.ttf", size)
        except Exception:
            try:
                f = pygame.font.SysFont("segoeuiemoji", size)
            except Exception:
                f = None
        _EMOJI_FONT_CACHE[size] = f
    return f


def is_emoji_char(char):
    """Kiểm tra một ký tự có phải là emoji/symbol đặc biệt không."""
    cp = ord(char)
    # Loại trừ các dấu chấm câu và ký tự tiếng Việt / Latin thông thường
    if cp < 0x203C or cp in (0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026, 0x2013, 0x2014):
        return False
    return (
        0x203C <= cp <= 0x32FF or
        0x1F000 <= cp <= 0x1FFFF or
        0xFE00 <= cp <= 0xFE0F
    )


def text_has_emoji(text):
    return any(is_emoji_char(c) for c in text)


def render_rich_text(font, text, color):
    """Render chuỗi văn bản hỗn hợp (chữ tiếng Việt + emoji/symbols màu).
    Tự động tách các đoạn emoji để render bằng font Segoe UI Emoji màu sắc thật,
    và các đoạn chữ tiếng Việt bằng font chính (Segoe UI Bold) để không bị lỗi ô vuông.
    """
    if not text or not text_has_emoji(text):
        return font.render(text, True, color)

    font_size = font.get_height()
    # Khớp kích thước font emoji tương đương với font chính
    f_emj = _get_emoji_font(max(10, font_size - 4))
    if f_emj is None:
        return font.render(text, True, color)

    runs = []
    cur_txt = []
    cur_is_emj = None
    for c in text:
        emj = is_emoji_char(c)
        if cur_is_emj is None or emj == cur_is_emj:
            cur_txt.append(c)
            cur_is_emj = emj
        else:
            runs.append((''.join(cur_txt), cur_is_emj))
            cur_txt = [c]
            cur_is_emj = emj
    if cur_txt:
        runs.append((''.join(cur_txt), cur_is_emj))

    surfs = []
    total_w = 0
    max_h = font.get_height()
    for chunk, emj in runs:
        f = f_emj if emj else font
        s = f.render(chunk, True, color)
        surfs.append(s)
        total_w += s.get_width()
        max_h = max(max_h, s.get_height())

    res = pygame.Surface((total_w, max_h), pygame.SRCALPHA)
    x = 0
    for s in surfs:
        y = (max_h - s.get_height()) // 2
        res.blit(s, (x, y))
        x += s.get_width()
    return res


def fit_text(font, text, max_w):
    """Cắt chữ và thêm … nếu dài hơn max_w pixel (tính cả độ rộng của emoji)."""
    def _measure(txt):
        if not text_has_emoji(txt):
            return font.size(txt)[0]
        # Ước lượng độ rộng chính xác
        f_emj = _get_emoji_font(max(10, font.get_height() - 4))
        w = 0
        for c in txt:
            if is_emoji_char(c) and f_emj:
                w += f_emj.size(c)[0]
            else:
                w += font.size(c)[0]
        return w

    if _measure(text) <= max_w:
        return text
    while text and _measure(text + "…") > max_w:
        text = text[:-1]
    return text + "…"


def draw_text(surf, font, text, color, **anchor):
    """Render chữ rồi đặt theo neo, ví dụ center=(x, y) hoặc midtop=(x, y)."""
    img = render_rich_text(font, text, color)
    surf.blit(img, img.get_rect(**anchor))


_aa_circle_cache = {}
def draw_aa_circle(surf, color, center, radius, width=0):
    """Vẽ hình tròn khử răng cưa mượt mà (anti-aliasing) bằng siêu lấy mẫu có cache."""
    r = int(round(radius))
    if r <= 0:
        return
    k = 3
    col = tuple(color)
    key = (r, col, width)
    img = _aa_circle_cache.get(key)
    if img is None:
        if len(_aa_circle_cache) > 250:
            _aa_circle_cache.clear()
        dia = 2 * r
        big_s = (dia + 2) * k
        big = pygame.Surface((big_s, big_s), pygame.SRCALPHA)
        big.fill((0, 0, 0, 0))
        bc = big_s / 2
        pygame.draw.circle(big, col, (bc, bc), r * k, width=width * k)
        img = pygame.transform.smoothscale(big, (dia + 2, dia + 2))
        _aa_circle_cache[key] = img
    cx, cy = round(center[0]), round(center[1])
    surf.blit(img, (cx - r - 1, cy - r - 1))


_aa_rect_cache = {}
def draw_aa_round_rect(surf, color, rect, radius, width=0):
    """Vẽ hình chữ nhật bo góc khử răng cưa mượt mà (anti-aliasing) bằng siêu lấy mẫu."""
    r = pygame.Rect(rect)
    if r.width <= 0 or r.height <= 0:
        return
    rad = int(max(0, min(radius, r.width // 2, r.height // 2)))
    if rad == 0:
        pygame.draw.rect(surf, color, r, width=width)
        return
    col = tuple(color)
    key = (r.width, r.height, col, rad, width)
    img = _aa_rect_cache.get(key)
    if img is None:
        if len(_aa_rect_cache) > 250:
            _aa_rect_cache.clear()
        # Đối với hình rỗng có viền (width > 0): dùng k=3 và bù nhẹ bề dày nét cong (+1px trên canvas phóng to)
        # để các đoạn bo góc tròn không bị mờ nhạt hoặc đứt nét so với các cạnh thẳng.
        if width > 0:
            k = 3
            draw_w = width * k + 1
            big = pygame.Surface((r.width * k, r.height * k), pygame.SRCALPHA)
            big.fill((0, 0, 0, 0))
            pygame.draw.rect(big, col, big.get_rect(), width=draw_w, border_radius=rad * k)
            img = pygame.transform.smoothscale(big, (r.width, r.height))
        else:
            k = 2
            big = pygame.Surface((r.width * k, r.height * k), pygame.SRCALPHA)
            big.fill((0, 0, 0, 0))
            pygame.draw.rect(big, col, big.get_rect(), width=0, border_radius=rad * k)
            img = pygame.transform.smoothscale(big, (r.width, r.height))
        _aa_rect_cache[key] = img
    surf.blit(img, r.topleft)


def fmt_time(sec):
    """Đổi số giây sang chuỗi 'mm:ss'."""
    sec = int(max(sec, 0))
    return f"{sec // 60}:{sec % 60:02d}"


def lerp(a, b, u):
    """Nội suy tuyến tính từ a tới b theo u (0..1)."""
    return a + (b - a) * u


def ease_out_cubic(u):
    """Nhanh lúc đầu, chậm dần về cuối (0..1 -> 0..1)."""
    u = min(max(u, 0.0), 1.0)
    return 1 - (1 - u) ** 3


def ease_out_back(u, s=1.2):
    """Vọt quá đích một chút rồi co lại (giống chất lỏng sóng sánh); s càng lớn càng vọt xa."""
    u = min(max(u, 0.0), 1.0)
    return 1 + (s + 1) * (u - 1) ** 3 + s * (u - 1) ** 2


def intro_geometry(t):
    """Hình dạng island ở giây thứ t của hiệu ứng mở đầu (giọt nước từ mép trên lan ra thành tai thỏ).
    Trả về (rộng, cao, tỉ_lệ_bán_kính_tai, độ_hiện_nội_dung 0..1), hoặc None khi hiệu ứng đã kết thúc."""
    t = max(t, 0.0)
    if t >= INTRO_DROP + INTRO_SPREAD + INTRO_FADE:
        return None
    if t < INTRO_DROP:                                       # pha 1: giọt nước hình thành, treo ở mép trên (cao hơn rộng)
        u = ease_out_cubic(t / INTRO_DROP)
        return lerp(2, 18, u), lerp(2, 34, u), lerp(0.15, 0.40, u), 0.0
    t2 = t - INTRO_DROP
    if t2 < INTRO_SPREAD:                                    # pha 2: giọt nước lan ra hai bên thành hình tai thỏ
        u = t2 / INTRO_SPREAD
        return (lerp(18, COMPACT_W, ease_out_back(u)),       # bề ngang vọt quá một chút rồi co lại
                lerp(34, COMPACT_H, ease_out_cubic(u)),
                lerp(0.40, 1.0, ease_out_cubic(u)),          # hai tai cong dần ra, nối liền với mép màn hình
                0.0)
    u = (t2 - INTRO_SPREAD) / INTRO_FADE                     # pha 3: hình đã thành, nội dung hiện dần
    return COMPACT_W, COMPACT_H, 1.0, u * u * (3 - 2 * u)    # smoothstep cho độ hiện mượt hai đầu


def make_bell(size=22):
    """Vẽ biểu tượng cái chuông màu trắng (vẽ to gấp 4 rồi thu nhỏ để mép mượt)."""
    k = 4                                                    # hệ số siêu lấy mẫu
    big = pygame.Surface((size * k, size * k), pygame.SRCALPHA)
    s = size * k / 80                                        # tỉ lệ so với bản vẽ gốc 80x80

    def P(x, y):                                             # đổi toạ độ bản vẽ gốc sang toạ độ thật
        return (x * s, y * s)

    white = (255, 255, 255, 255)
    pygame.draw.circle(big, white, P(40, 32), 18 * s)        # vòm chuông
    pygame.draw.polygon(big, white, [P(22, 34), P(58, 34), P(62, 56), P(68, 62), P(12, 62), P(18, 56)])   # thân loe ra
    pygame.draw.rect(big, white, pygame.Rect(*P(10, 60), 60 * s, 6 * s), border_radius=int(3 * s))        # viền dưới
    pygame.draw.circle(big, white, P(40, 12), 4 * s)         # núm phía trên
    pygame.draw.circle(big, white, P(40, 70), 7 * s)         # quả lắc
    return pygame.transform.smoothscale(big, (size, size))


_ring_cache = {}


def make_ring(size, frac, color, width=3.5):
    """Vòng tròn tiến độ (bắt đầu từ đỉnh, chạy theo chiều kim đồng hồ), phần chưa đầy là vạch tối cùng tông.
    Vẽ gấp 4 lần rồi thu nhỏ cho mép mượt; có cache theo (phần trăm, màu)."""
    pct = int(round(max(0.0, min(1.0, frac)) * 100))
    key = (size, pct, color, width)
    if key in _ring_cache:
        return _ring_cache[key]
    k = 4
    big = pygame.Surface((size * k, size * k), pygame.SRCALPHA)
    c = size * k / 2
    ro, ri = c - 1 * k, c - 1 * k - width * k           # bán kính ngoài / trong
    track = tuple(int(v * 0.32) for v in color)
    pygame.draw.circle(big, track, (c, c), ro)
    pygame.draw.circle(big, (0, 0, 0, 0), (c, c), ri)
    if pct > 0:
        a0, sweep = -math.pi / 2, 2 * math.pi * pct / 100
        n = max(8, int(pct * 1.2))
        outer = [(c + ro * math.cos(a0 + sweep * i / n), c + ro * math.sin(a0 + sweep * i / n)) for i in range(n + 1)]
        inner = [(c + ri * math.cos(a0 + sweep * i / n), c + ri * math.sin(a0 + sweep * i / n)) for i in range(n, -1, -1)]
        pygame.draw.polygon(big, color, outer + inner)
        mid, cap = (ro + ri) / 2, (ro - ri) / 2             # hai đầu bo tròn
        for a in (a0, a0 + sweep):
            pygame.draw.circle(big, color, (c + mid * math.cos(a), c + mid * math.sin(a)), cap)
    img = pygame.transform.smoothscale(big, (size, size))
    _ring_cache[key] = img
    return img


def make_nav_icon(kind, size=18, color=(255, 255, 255)):
    """Icon điều hướng: 'music' (nốt nhạc), 'calendar' (lịch), 'shelf' (khay file). Vẽ gấp 4 lần rồi thu nhỏ."""
    k = 4
    big = pygame.Surface((size * k, size * k), pygame.SRCALPHA)
    s = size * k / 24                                        # bản vẽ gốc 24x24

    def P(x, y):
        return (x * s, y * s)

    if kind == "music":
        pygame.draw.ellipse(big, color, pygame.Rect(*P(4, 15), 9 * s, 7 * s))
        pygame.draw.ellipse(big, color, pygame.Rect(*P(13, 12), 9 * s, 7 * s))
        pygame.draw.rect(big, color, pygame.Rect(*P(11, 3), 2.2 * s, 15 * s))
        pygame.draw.rect(big, color, pygame.Rect(*P(20, 1), 2.2 * s, 14 * s))
        pygame.draw.polygon(big, color, [P(11, 3), P(22.2, 1), P(22.2, 5.5), P(11, 7.5)])
    elif kind == "calendar":
        # Khung viền ngoài của lịch: bo tròn mềm mại
        pygame.draw.rect(big, color, pygame.Rect(*P(2.5, 4.5), 19 * s, 17 * s), width=max(1, int(1.8 * s)), border_radius=int(3.2 * s))
        # Dải thanh ngang trên đỉnh lịch (được tô đầy)
        pygame.draw.rect(big, color, pygame.Rect(*P(2.5, 4.5), 19 * s, 4.5 * s), border_top_left_radius=int(3.2 * s), border_top_right_radius=int(3.2 * s))
        # 2 móc treo lịch có đầu bo tròn nhô lên trên
        for x in (6.5, 15.5):
            pygame.draw.rect(big, color, pygame.Rect(*P(x, 1.8), 2 * s, 4 * s), border_radius=int(s))
        
        # Bố cục 4 cột chấm tròn to rõ nét, nhích lên để cách đều mép đáy và mép trên:
        r_dot = 1.3 * s
        # Hàng 1 (y = 11.2): 2 chấm lệch về bên phải (cột 3, 4)
        for cx in (13.8, 17.5):
            pygame.draw.circle(big, color, P(cx, 11.2), r_dot)
        # Hàng 2 (y = 14.5): 4 chấm đầy đủ ở tất cả các cột
        for cx in (6.5, 10.2, 13.8, 17.5):
            pygame.draw.circle(big, color, P(cx, 14.5), r_dot)
        # Hàng 3 (y = 17.8): 1 chấm ở cột đầu tiên (cách đáy khung lịch thoải mái)
        pygame.draw.circle(big, color, P(6.5, 17.8), r_dot)
    elif kind == "close":                                    # dấu X căn giữa tuyệt đối trong ô size x size
        w = int(2.6 * s)
        pygame.draw.line(big, color, P(7, 7), P(17, 17), w)
        pygame.draw.line(big, color, P(17, 7), P(7, 17), w)
        for p_ in ((7, 7), (17, 17), (17, 7), (7, 17)):      # bo tròn đầu nét
            pygame.draw.circle(big, color, P(*p_), w / 2)
    elif kind == "gear":                                     # bánh răng 8 răng
        cx = cy = 12
        for n in range(8):
            ang = n * math.pi / 4
            ca, sa = math.cos(ang), math.sin(ang)
            pts = []
            for ra, off in ((7, -1.9), (11.3, -1.4), (11.3, 1.4), (7, 1.9)):   # hình thang một răng
                pts.append(P(cx + ra * ca - off * sa, cy + ra * sa + off * ca))
            pygame.draw.polygon(big, color, pts)
        pygame.draw.circle(big, color, P(cx, cy), 8.2 * s)
        pygame.draw.circle(big, (0, 0, 0, 0), P(cx, cy), 3.6 * s)   # lỗ ở giữa (trong suốt)
    else:                                                    # shelf: khay có mũi tên xuống
        pygame.draw.polygon(big, color, [P(12, 15), P(7, 9.5), P(10.6, 9.5), P(10.6, 2.5), P(13.4, 2.5), P(13.4, 9.5), P(17, 9.5)])
        pygame.draw.lines(big, color, False, [P(3.5, 13), P(3.5, 20.5), P(20.5, 20.5), P(20.5, 13)], int(2.4 * s))
    return pygame.transform.smoothscale(big, (size, size))


def draw_capsule(surf, c1, r1, c2, r2, color):
    """Vẽ hình giọt nước: 2 vòng tròn nối bằng 2 tiếp tuyến ngoài (vòng lớn ở đầu, vòng nhỏ ở đuôi)."""
    (x1, y1), (x2, y2) = c1, c2
    pygame.draw.circle(surf, color, (x1, y1), r1)            # vòng ở đầu (chỗ con trỏ)
    pygame.draw.circle(surf, color, (x2, y2), r2)            # vòng ở đuôi (chạy theo trễ)
    dx, dy = x2 - x1, y2 - y1
    d = math.hypot(dx, dy)                                   # khoảng cách giữa 2 tâm
    if d <= abs(r1 - r2) + 0.5:
        return                                               # vòng này nằm trọn trong vòng kia -> không cần nối
    base = math.atan2(dy, dx)                                # hướng từ đầu sang đuôi
    a = math.acos((r1 - r2) / d)                             # góc lệch của pháp tuyến tiếp tuyến ngoài
    pts = [(x1 + r1 * math.cos(base + s * a), y1 + r1 * math.sin(base + s * a)) for s in (1, -1)]    # 2 điểm tiếp xúc ở đầu
    pts += [(x2 + r2 * math.cos(base + s * a), y2 + r2 * math.sin(base + s * a)) for s in (-1, 1)]   # 2 điểm tiếp xúc ở đuôi
    pygame.draw.polygon(surf, color, pts)                    # lấp phần thân giữa 2 vòng
