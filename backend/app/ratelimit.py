"""Per-visitor rate limiting.

The Cloudflare tunnel makes this server public, and every AI call spends the
owner's Groq quota, so one visitor must not be able to drain it.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request


class RateLimiter:
    """Sliding-window limit per client key."""

    def __init__(self, limit: int, window_s: float) -> None:
        self.limit = limit
        self.window_s = window_s
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window_s:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        if len(self.hits) > 5000:  # forget idle clients so memory stays bounded
            for k in [k for k, v in self.hits.items() if not v]:
                del self.hits[k]
        return True


def client_key(request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    # Behind cloudflared every request arrives from localhost; the real
    # visitor is in CF-Connecting-IP. Only trust that header from localhost.
    if host in ("127.0.0.1", "::1"):
        return request.headers.get("cf-connecting-ip", host)
    return host
