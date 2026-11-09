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
                        elif isinstance(cmd, (tuple, list)) and len(cmd) >= 2 and cmd[0] == "seek":
                            ticks = int(max(0.0, float(cmd[1])) * 10_000_000)
                            await s.try_change_playback_position_async(ticks)
            except Exception:
                pass
            finally:
                MediaBridge._cmd_queue.task_done()

    async def _poll(self):
        MediaManager, PlayStatus = _winsdk()                 # nạp winsdk ngay trong luồng này
        mgr = None
        last_mgr_refresh = 0.0
        cached_title = ""
        cached_artist = ""
        cached_app_id = ""

        # Biến theo dõi để định kỳ kích hoạt GC dọn dẹp các wrapper C++/COM
        poll_count = 0

        while True:
            info = {}
            now = time.monotonic()
            poll_count += 1
            if poll_count % 120 == 0:  # Mỗi 60 giây (120 vòng * 0.5s) quét gom rác
                import gc
                gc.collect()

            try:
                # 1. Quản lý vòng đời của SessionManager:
                # Tái sử dụng manager thay vì gọi request_async() mỗi 0.5 giây (ngăn rò rỉ COM wrapper/native handles).
                # Chỉ làm mới định kỳ sau mỗi 300 giây hoặc khi mất kết nối / gặp lỗi.
                if mgr is None or (now - last_mgr_refresh > 300.0):
                    try:
                        mgr = await MediaManager.request_async()
                        MediaBridge._mgr = mgr
                        last_mgr_refresh = now
                    except Exception:
                        mgr = None
                        MediaBridge._mgr = None

                if mgr is not None:
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

                        # 2. Tối ưu hóa việc gọi try_get_media_properties_async():
                        # Lấy app_id kiểm tra trước; chỉ gọi try_get_media_properties_async khi cần
                        app_id = ""
                        try:
                            app_id = s.source_app_user_model_id or ""
                        except Exception:
                            app_id = ""

                        # Lấy metadata bài hát
                        props = None
                        try:
                            props = await s.try_get_media_properties_async()
                        except Exception:
                            props = None

                        title = (props.title or "").strip() if props else ""
                        artist = (props.artist or "").strip() if props else ""

                        # Fallback tên ứng dụng nếu không có title
                        if not title and app_id:
                            title = app_id.split("!")[-1].replace(".exe", "").capitalize()

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
                        # Giải phóng biến cục bộ để COM wrapper không bị giữ lại
                        del props
                        del p_info
                        del s
                        del target_session
                    if sessions:
                        del sessions
            except Exception:
                info = {}
                mgr = None
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
    """Đọc ảnh bìa (SMTC thumbnail) thành bytes và giải phóng toàn bộ stream/reader WinRT."""
    if ref is None:
        return None
    stream = None
    reader = None
    try:
        from winsdk.system import Array
        from winsdk.windows.storage.streams import DataReader
        stream = await ref.open_read_async()
        if not stream:
            return None
        size = int(stream.size)
        if size <= 0 or size > 6_000_000:
            return None
        input_stream = stream.get_input_stream_at(0)
        reader = DataReader(input_stream)
        loaded = int(await reader.load_async(size))
        if loaded <= 0:
            return None
        raw = Array("B", loaded)                             # mảng byte WinRT
        reader.read_bytes(raw)
        result = bytes(bytearray(raw))
        return result
    except Exception:
        return None
    finally:
        if reader is not None:
            try:
                reader.close()
            except Exception:
                pass
            del reader
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
            del stream


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


def fetch_youtube_manual_subtitles(title, artist=""):
    """Tìm phụ đề thủ công do tác giả tải lên (không lấy phụ đề tự động) trên YouTube."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        ytt = YouTubeTranscriptApi()
        search_query = f"{title} {artist}".strip()
        if not search_query:
            return [], []

        r = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": search_query},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=6
        )
        if not r.ok:
            return [], []

        # Trích xuất video IDs từ kết quả tìm kiếm
        vids = re.findall(r"/watch\?v=([a-zA-Z0-9_-]{11})", r.text)
        seen = set()
        unique_vids = []
        for v in vids:
            if v not in seen:
                seen.add(v)
                unique_vids.append(v)

        for vid in unique_vids[:3]:
            try:
                transcript_list = ytt.list(vid)
                for t in transcript_list:
                    # Chỉ lấy phụ đề thủ công do tác giả tạo, không lấy phụ đề tự động (is_generated == False)
                    if not t.is_generated:
                        snippets = t.fetch()
                        times = []
                        lines = []
                        for s in snippets:
                            t_sec = float(s.start)
                            # Thay dòng xuống dòng bằng khoảng trắng
                            text_line = (s.text or "").replace("\n", " ").strip()
                            if text_line:
                                times.append(t_sec)
                                lines.append(text_line)
                        if lines:
                            return times, lines
            except Exception:
                continue
    except Exception:
        pass
    return [], []


def fetch_synced_lyrics(title, artist):
    """Lấy lời đồng bộ: thử LRCLIB trước; nếu không có (như video/nhạc YouTube), thử phụ đề thủ công YouTube."""
    raw_title, raw_artist = title, artist
    c_title, c_artist = clean(title), clean(artist)
    
    # 1. Thử lấy từ LRCLIB
    try:
        r = requests.get("https://lrclib.net/api/get",
                         params={"track_name": c_title, "artist_name": c_artist}, timeout=8)
        if r.ok and r.json().get("syncedLyrics"):
            return parse_lrc(r.json()["syncedLyrics"])
        r = requests.get("https://lrclib.net/api/search", params={"q": f"{c_title} {c_artist}"}, timeout=8)
        if r.ok:
            for item in r.json():
                if item.get("syncedLyrics"):
                    return parse_lrc(item["syncedLyrics"])
    except Exception:
        pass

    # 2. Nếu LRCLIB không có (thường xảy ra với video YouTube), tìm phụ đề do tác giả làm trên YouTube
    yt_times, yt_lines = fetch_youtube_manual_subtitles(raw_title, raw_artist)
    if yt_lines:
        return yt_times, yt_lines

    return [], []
