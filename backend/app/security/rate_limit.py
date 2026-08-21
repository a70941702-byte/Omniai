from __future__ import annotations

import threading
import time
from collections import deque


class FixedWindowRateLimiter:
    def __init__(self, limit: int, window_s: int):
        self.limit = limit
        self.window_s = window_s
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def _prune(self, key: str, now: float) -> deque[float]:
        dq = self._hits.setdefault(key, deque())
        cutoff = now - self.window_s
        while dq and dq[0] <= cutoff:
            dq.popleft()
        return dq

    def allowed(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            dq = self._prune(key, now)
            return len(dq) < self.limit

    def record(self, key: str) -> int:
        now = time.time()
        with self._lock:
            dq = self._prune(key, now)
            dq.append(now)
            return len(dq)

    def clear(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


login_rate_limiter = FixedWindowRateLimiter(limit=5, window_s=300)
