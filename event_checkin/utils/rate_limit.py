"""Giới hạn tần suất theo IP (đếm trong bộ nhớ), dùng chung cho route chứng chỉ công khai và form đăng ký.

IP lấy bằng event_checkin.audit.client_ip() (IP thật sau ProxyFix) -- nơi gọi tự truyền vào."""
import threading
import time
from collections import deque


class PerIpRateLimiter:
    """Cửa sổ trượt 60 giây cho mỗi IP. Đếm trong bộ nhớ tiến trình: app chạy 1 tiến trình waitress nhiều luồng nên
    đủ dùng; khởi động lại app thì bộ đếm về 0."""

    WINDOW_SECONDS = 60

    def __init__(self):
        self._hits = {}
        self._lock = threading.Lock()
        self._last_sweep = 0.0

    def allow(self, key, limit):
        now = time.monotonic()
        cutoff = now - self.WINDOW_SECONDS
        with self._lock:
            if now - self._last_sweep > self.WINDOW_SECONDS:          # dọn IP không còn hoạt động (không phình bộ nhớ)
                for stale in [k for k, q in self._hits.items() if not q or q[-1] < cutoff]:
                    del self._hits[stale]
                self._last_sweep = now
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def reset(self):
        with self._lock:
            self._hits.clear()
