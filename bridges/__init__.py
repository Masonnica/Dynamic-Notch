"""
Package chứa các cầu nối hệ thống (Media SMTC, Thông báo hệ thống, Google Calendar).
"""
from .media import MediaBridge, fetch_synced_lyrics
from .notif import NotifBridge
from .calendar import GoogleCalendar
from .updater import UpdaterBridge

__all__ = ["MediaBridge", "fetch_synced_lyrics", "NotifBridge", "GoogleCalendar", "UpdaterBridge"]
