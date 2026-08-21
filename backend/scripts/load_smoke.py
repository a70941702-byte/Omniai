from __future__ import annotations

import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx


def one_request(client: httpx.Client, base_url: str, token: str, i: int) -> float:
    t0 = time.perf_counter()
    r = client.post(
        f"{base_url}/api/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": f"compute {i} + {i}"},
        timeout=30.0,
    )
    r.raise_for_status()
    body = r.json()
    expected = str(i + i)
    if expected not in body.get("answer", ""):
        raise RuntimeError(f"unexpected answer for {i}: {body}")
    return time.perf_counter() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--owner-token", default="test-owner-token")
    ap.add_argument("--requests", type=int, default=12)
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()

    latencies = []
    with httpx.Client() as client:
        ready = client.get(f"{args.base_url}/readyz", timeout=10.0)
        ready.raise_for_status()
        if not ready.json().get("ok"):
            raise RuntimeError(f"backend not ready: {ready.text}")

        login = client.post(
            f"{args.base_url}/api/v1/auth/login",
            json={"token": args.owner_token, "device_id": "load-smoke"},
            timeout=10.0,
        )
        login.raise_for_status()
        session_token = login.json()["token"]

        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            futures = [ex.submit(one_request, client, args.base_url, session_token, i) for i in range(1, args.requests + 1)]
            for fut in as_completed(futures):
                latencies.append(fut.result())

        metrics = client.get(
            f"{args.base_url}/api/v1/metrics/prometheus",
            headers={"Authorization": f"Bearer {session_token}"},
            timeout=10.0,
        )
        metrics.raise_for_status()
        if "omniai_http_requests_total" not in metrics.text:
            raise RuntimeError("prometheus metrics missing expected counter")

    latencies.sort()
    p95_idx = min(len(latencies) - 1, max(0, round((len(latencies) - 1) * 0.95)))
    print(
        {
            "requests": len(latencies),
            "avg_s": round(statistics.mean(latencies), 4),
            "p95_s": round(latencies[p95_idx], 4),
            "max_s": round(max(latencies), 4),
        }
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print({"ok": False, "error": str(e)}, file=sys.stderr)
        raise
