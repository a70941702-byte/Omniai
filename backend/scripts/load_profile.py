from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx


async def post_chat_with_retry(client: httpx.AsyncClient, base_url: str, token: str, idx: int) -> float:
    last_error: Exception | None = None
    for attempt in range(3):
        t0 = time.perf_counter()
        try:
            r = await client.post(
                f"{base_url}/api/v1/chat",
                headers={"Authorization": f"Bearer {token}"},
                json={"text": f"compute {idx} + {idx}"},
                timeout=30.0,
            )
            if r.status_code >= 500:
                raise httpx.HTTPStatusError("server error", request=r.request, response=r)
            r.raise_for_status()
            return time.perf_counter() - t0
        except (httpx.HTTPError, httpx.TransportError) as exc:
            last_error = exc
            if attempt == 2:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


async def worker(client: httpx.AsyncClient, base_url: str, token: str, idx: int, rounds: int) -> list[float]:
    latencies = []
    for i in range(rounds):
        latencies.append(await post_chat_with_retry(client, base_url, token, idx + i))
    return latencies


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--owner-token", default="test-owner-token")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--rounds", type=int, default=10)
    args = ap.parse_args()

    async with httpx.AsyncClient() as client:
        ready = await client.get(f"{args.base_url}/readyz", timeout=10.0)
        ready.raise_for_status()
        login = await client.post(
            f"{args.base_url}/api/v1/auth/login",
            json={"token": args.owner_token, "device_id": "load-profile"},
            timeout=10.0,
        )
        login.raise_for_status()
        token = login.json()["token"]

        warmup = await client.post(
            f"{args.base_url}/api/v1/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": "compute 1 + 1"},
            timeout=30.0,
        )
        warmup.raise_for_status()

        tasks = [worker(client, args.base_url, token, n * 1000, args.rounds) for n in range(args.concurrency)]
        batches = await asyncio.gather(*tasks)
        values = sorted(v for batch in batches for v in batch)

        metrics = await client.get(
            f"{args.base_url}/api/v1/metrics/prometheus",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        metrics.raise_for_status()
        assert "omniai_http_latency_p95_seconds" in metrics.text

    p95_idx = min(len(values) - 1, max(0, round((len(values) - 1) * 0.95)))
    print({
        "requests": len(values),
        "avg_s": round(statistics.mean(values), 4),
        "p95_s": round(values[p95_idx], 4),
        "max_s": round(max(values), 4),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
