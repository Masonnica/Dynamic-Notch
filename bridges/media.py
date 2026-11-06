"""
Cầu nối Media (SMTC) điều khiển phát nhạc và lấy lời đồng bộ từ LRCLIB.
"""
import re
import time
import asyncio
import threading
from datetime import datetime, timezone
import requests


# ------------------------------ Cầu nối SMTC --------------------------------
def _winsdk():
    """Nạp winsdk trong luồng nền (không nạp ở luồng chính để luồng chính còn khởi tạo được OLE cho kéo-thả)."""
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,       # quản lý phiên phát nhạc
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlayStatus,  # đang phát / tạm dừng
    )
    return MediaManager, PlayStatus


class MediaBridge:
    """Luồng nền hỏi Windows thông tin bài hát mỗi 0.5 giây; luồng chính đọc bản chụp (snapshot)."""

    _mgr = None
    _cmd_queue = None
    _loop = None

    def __init__(self):
        self._lock = threading.Lock()                        # khóa để đọc/ghi an toàn giữa 2 luồng
        self._info = {}                                      # dữ liệu mới nhất ({} = không có nhạc)
        self._thumb_key = None                               # bài đã đọc ảnh bìa (tránh tải lại mỗi 0.5 giây)
        self._thumb = None                                   # bytes ảnh bìa, cùng object cho tới khi đổi bài

    def start(self):
        threading.Thread(target=self._thread_entry, daemon=True).start()

    def _thread_entry(self):
        """Khởi tạo luồng với Windows COM (COINIT_MULTITHREADED) rồi chạy event loop."""
        try:
            import ctypes
            ctypes.windll.ole32.CoInitializeEx(None, 0x0)
        except Exception:
            pass

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        MediaBridge._loop = loop
        MediaBridge._cmd_queue = asyncio.Queue()
        try:
            loop.run_until_complete(asyncio.gather(self._poll(), self._handle_commands()))
        finally:
            try:
                import ctypes
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass

    def snapshot(self):
        with self._lock:
            return dict(self._info)                          # trả về bản sao

    async def _handle_commands(self):
        """Nhận lệnh điều khiển từ luồng chính và thực thi ngay trên cùng event loop và session manager."""
        while True:
            cmd = await MediaBridge._cmd_queue.get()
            try:
                mgr = MediaBridge._mgr
                if mgr is not None:
                    _, PlayStatus = _winsdk()
                    s = mgr.get_current_session()
                    if not s:
                        try:
                            sessions = mgr.get_sessions()
                            for sess in sessions:
                                if sess.get_playback_info().playback_status == PlayStatus.PLAYING:
                                    s = sess
                                    break
                            if not s and sessions:
                                s = sessions[0]
                        except Exception:
                            pass
                    if s:
                        if cmd == "toggle":
                            await s.try_toggle_play_pause_async()
                        elif cmd == "next":
                            await s.try_skip_next_async()
                        elif cmd == "prev":
                            await s.try_skip_previous_async()
            except Exception:
                pass
            finally:
                MediaBridge._cmd_queue.task_done()

    async def _poll(self):
        MediaManager, PlayStatus = _winsdk()                 # nạp winsdk ngay trong luồng này
        while True:
            info = {}
            try:
                # Luôn lấy SessionManager mới để tránh bị cache phiên cũ hoặc mất kết nối
                mgr = None
                try:
                    mgr = await MediaManager.request_async()
                except Exception:
                    pass

                if mgr is not None:
                    MediaBridge._mgr = mgr
                    s = None
                    try:
                        s = mgr.get_current_session()
                    except Exception:
                        s = None

                    sessions = None
                    try:
                        sessions = mgr.get_sessions()
                    except Exception:
                        sessions = None

                    target_session = None

                    # 1. Ưu tiên session mặc định của hệ thống trước nếu có
                    if s is not None:
                        try:
                            p_info = s.get_playback_info()
                            if p_info:
                                target_session = s
                        except Exception:
                            target_session = None

                    # 2. Nếu s không có hoặc không phát, tìm trong tất cả sessions xem có phiên nào PLAYING
                    if sessions:
                        # Kiểm tra xem session hiện tại có đang PLAYING không
                        curr_playing = False
                        if target_session is not None:
                            try:
                                curr_playing = (target_session.get_playback_info().playback_status == PlayStatus.PLAYING)
                            except Exception:
                                curr_playing = False

                        if not curr_playing:
                            for sess in sessions:
                                try:
                                    p_info = sess.get_playback_info()
                                    if p_info and p_info.playback_status == PlayStatus.PLAYING:
                                        target_session = sess
                                        break
                                except Exception:
                                    continue

                    # 3. Nếu vẫn None thì lấy session đầu tiên có trong danh sách
                    if target_session is None and sessions and len(sessions) > 0:
                        target_session = sessions[0]

                    if target_session:
                        s = target_session
                        props = None
                        try:
                            props = await s.try_get_media_properties_async()
                        except Exception:
                            props = None

                        p_info = None
                        try:
                            p_info = s.get_playback_info()
                        except Exception:
                            p_info = None

                        playing = (p_info.playback_status == PlayStatus.PLAYING) if p_info else False

                        pos, dur = 0.0, 0.0
                        try:
                            tl = s.get_timeline_properties()
                            if tl:
                                pos = tl.position.total_seconds() if tl.position else 0.0
                                dur = tl.end_time.total_seconds() if tl.end_time else 0.0
                                if playing and tl.last_updated_time:
                                    try:
                                        pos += max(0.0, (datetime.now(timezone.utc) - tl.last_updated_time).total_seconds())
                                    except Exception:
                                        pass
                                if dur > 0:
                                    pos = min(pos, dur)
                        except Exception:
                            pass

                        title = (props.title or "").strip() if props else ""
                        artist = (props.artist or "").strip() if props else ""

                        # Nếu không có title từ props, thử fallback lấy từ SourceAppUserModelId nếu có
                        if not title:
                            try:
                                app_id = s.source_app_user_model_id
                                if app_id:
                                    title = app_id.split("!")[-1].replace(".exe", "").capitalize()
                            except Exception:
                                pass

                        # Ghi nhận thông tin bài hát
                        if title or artist or playing:
                            key = (title or "Đang phát", artist or "")
                            if key != self._thumb_key:
                                self._thumb_key = key
                                thumb_ref = None
                                try:
                                    thumb_ref = props.thumbnail if props else None
                                except Exception:
                                    thumb_ref = None
                                self._thumb = await _read_thumbnail(thumb_ref)
                            info = {"title": key[0], "artist": key[1],
                                    "playing": playing, "pos": pos, "dur": dur,
                                    "t": time.monotonic(),
                                    "thumb": self._thumb}
            except Exception:
                info = {}
                MediaBridge._mgr = None
            with self._lock:
                self._info = info
            await asyncio.sleep(0.5)

    @staticmethod
    def command(name):
        """Gửi lệnh: 'toggle' (phát/dừng), 'next', 'prev' an toàn thông qua hàng đợi của event loop nền."""
        if MediaBridge._loop and MediaBridge._cmd_queue:
            MediaBridge._loop.call_soon_threadsafe(MediaBridge._cmd_queue.put_nowait, name)


async def _read_thumbnail(ref):
    """Đọc ảnh bìa (SMTC thumbnail) thành bytes. Chỉ gọi từ luồng nền của MediaBridge."""
    if ref is None:
        return None
    try:
        from winsdk.system import Array
        from winsdk.windows.storage.streams import DataReader
        stream = await ref.open_read_async()
        size = int(stream.size)
        if size <= 0 or size > 6_000_000:
            return None
        reader = DataReader(stream.get_input_stream_at(0))
        loaded = int(await reader.load_async(size))
        if loaded <= 0:
            return None
        raw = Array("B", loaded)                             # mảng byte WinRT
        reader.read_bytes(raw)
        reader.close()
        return bytes(bytearray(raw))
    except Exception:
        return None


# --------------------------------- Lyrics -----------------------------------
LRC_LINE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")      # khớp "[01:23.45] lời bài hát"


def parse_lrc(text):
    """Chuyển chuỗi LRC thành (danh sách mốc giây, danh sách lời)."""
    times, lines = [], []
    for raw in text.splitlines():
        m = LRC_LINE.match(raw.strip())
        if m:
            times.append(int(m.group(1)) * 60 + float(m.group(2)))
            lines.append(m.group(3).strip() or "…")          # dòng trống -> dấu lửng
    return times, lines


def clean(text):
    """Bỏ phần trong ngoặc như (Official MV), [Lyrics] để tăng khả năng khớp trên LRCLIB."""
    text = re.sub(r"[\(\[].*?[\)\]]", "", text).replace(" - Topic", "")
    return re.sub(r"\s+", " ", text).strip()


def fetch_synced_lyrics(title, artist):
    """Hỏi LRCLIB lời đồng bộ: thử /get trước, không có thì /search."""
    title, artist = clean(title), clean(artist)
    try:
        r = requests.get("https://lrclib.net/api/get",
                         params={"track_name": title, "artist_name": artist}, timeout=8)
        if r.ok and r.json().get("syncedLyrics"):
            return parse_lrc(r.json()["syncedLyrics"])
        r = requests.get("https://lrclib.net/api/search", params={"q": f"{title} {artist}"}, timeout=8)
        if r.ok:
            for item in r.json():
                if item.get("syncedLyrics"):
                    return parse_lrc(item["syncedLyrics"])
    except Exception:
        pass
    return [], []
