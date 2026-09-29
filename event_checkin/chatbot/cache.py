"""Cache in-memory có TTL. `Cache` là interface tối thiểu (get/set) để sau này
thay bằng Redis chỉ cần viết thêm 1 class con."""

import threading
import time
from abc import ABC, abstractmethod


class Cache(ABC):
    @abstractmethod
    def get(self, key):
        ...

    @abstractmethod
    def set(self, key, value):
        ...


class InMemoryTTLCache(Cache):
    def __init__(self, ttl_seconds=60, max_items=500):
        self._ttl = ttl_seconds
        self._max = max_items
        self._data = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at < time.monotonic():
                del self._data[key]
                return None
            return value

    def set(self, key, value):
        with self._lock:
            if len(self._data) >= self._max:
                now = time.monotonic()
                self._data = {k: v for k, v in self._data.items() if v[0] >= now}
                if len(self._data) >= self._max:
                    self._data.pop(next(iter(self._data)))
            self._data[key] = (time.monotonic() + self._ttl, value)
