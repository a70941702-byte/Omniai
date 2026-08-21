from __future__ import annotations

import logging
import threading
import time
from collections import deque

log = logging.getLogger("omniai")
_lock = threading.Lock()
counters: dict[str, int] = {}
route_counters: dict[str, int] = {}
latencies = deque(maxlen=2000)


def record(name: str, value: int = 1):
    with _lock:
        counters[name] = counters.get(name, 0) + value


def record_route(method: str, path: str, status: int):
    key = f"{method.upper()} {path} {status}"
    with _lock:
        route_counters[key] = route_counters.get(key, 0) + 1


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[idx]


def snapshot():
    with _lock:
        values = list(latencies)
        return {
            "counters": dict(counters),
            "routes": dict(route_counters),
            "latency_count": len(values),
            "latency_avg_s": sum(values) / len(values) if values else 0.0,
            "latency_p50_s": _percentile(values, 0.50),
            "latency_p95_s": _percentile(values, 0.95),
            "latency_max_s": max(values) if values else 0.0,
        }


class MetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        t = time.monotonic()
        method = scope.get("method", "GET")
        path = scope.get("path", "")
        record("http_requests_total")
        status_holder = {"code": 500}

        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = int(message["status"])
                record(f"http_status_{message['status']}")
                record_route(method, path, int(message["status"]))
            await send(message)

        try:
            return await self.app(scope, receive, wrapped_send)
        finally:
            elapsed = time.monotonic() - t
            with _lock:
                latencies.append(elapsed)
            log.info(
                "request",
                extra={
                    "path": path,
                    "method": method,
                    "status": status_holder["code"],
                    "latency_s": elapsed,
                },
            )
