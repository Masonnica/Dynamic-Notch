"""
Cầu nối đọc số lượng thông báo hệ thống từ Action Center của Windows.
"""
import asyncio
import threading


class NotifBridge:
    """Luồng nền đếm số thông báo đang nằm trong Action Center của Windows (UserNotificationListener).
    Cần bật quyền: Settings > Privacy & security > Notifications (cho phép ứng dụng truy cập thông báo)."""

    def __init__(self):
        self._lock = threading.Lock()                        # khóa để đọc/ghi an toàn giữa 2 luồng
        self._count = 0                                      # số thông báo hiện có
        self.status = "pending"                              # pending | allowed | denied | error

    def start(self):
        threading.Thread(target=lambda: asyncio.run(self._poll()), daemon=True).start()

    def count(self):
        with self._lock:
            return self._count

    async def _poll(self):
        try:                                                 # nạp winsdk ngay trong luồng này
            from winsdk.windows.ui.notifications.management import (
                UserNotificationListener, UserNotificationListenerAccessStatus)
            from winsdk.windows.ui.notifications import NotificationKinds
            listener = UserNotificationListener.current      # bộ lắng nghe thông báo của hệ thống
        except Exception as ex:
            self.status = "error"
            print(f"[Dynamic Island] Không dùng được API thông báo: {ex}")
            return
        warned = False                                       # chỉ in cảnh báo thiếu quyền một lần
        while True:
            n = 0
            try:
                status = listener.get_access_status()        # đã được cấp quyền đọc thông báo chưa?
                if status == UserNotificationListenerAccessStatus.UNSPECIFIED:
                    status = await listener.request_access_async()   # chưa hỏi lần nào -> xin quyền
                if status == UserNotificationListenerAccessStatus.ALLOWED:
                    self.status = "allowed"
                    n = len(await listener.get_notifications_async(NotificationKinds.TOAST))   # đếm toast đang chờ
                else:
                    self.status = "denied"
                    if not warned:
                        warned = True
                        print("[Dynamic Island] Chưa được phép đọc thông báo. Hãy bật: Settings > Privacy & security > "
                              "Notifications > cho phép ứng dụng truy cập thông báo.")
            except Exception:
                self.status = "error"
            with self._lock:
                self._count = n
            await asyncio.sleep(2 if self.status == "allowed" else 8)   # hỏi lại: 2 giây/lần (hoặc 8 giây nếu chưa có quyền)
