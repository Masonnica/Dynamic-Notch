"""
Lớp cơ sở (Base class) cho các tab trong Dynamic Island.
"""


class BaseTab:
    """Lớp giao diện cơ bản cho từng tab nội dung của Dynamic Island."""

    def __init__(self, island):
        self.island = island

    def draw(self, surf):
        """Vẽ nội dung tab lên surface."""
        raise NotImplementedError

    def on_wheel(self, dy):
        """Xử lý sự kiện lăn chuột khi tab đang hoạt động."""
        pass
