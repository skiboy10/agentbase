"""
Per-API-key request rate limiting (#10).

In-process sliding window keyed by APIKey.id. Suitable for single-process
deployments (the default Docker Compose layout). Multi-replica deployments
would need a shared store (Redis) — out of scope for this issue.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Optional


class PerKeyRateLimiter:
    """Sliding-window limiter: at most ``rpm`` hits per key_id per 60 seconds."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key_id: str, rpm: Optional[int]) -> tuple[bool, int]:
        """
        Record a hit and return ``(allowed, retry_after_seconds)``.

        When ``rpm`` is None or <= 0 the key is unlimited (always allowed).
        """
        if rpm is None or rpm <= 0:
            return True, 0

        now = time.monotonic()
        window = 60.0
        with self._lock:
            q = self._hits[key_id]
            cutoff = now - window
            while q and q[0] <= cutoff:
                q.popleft()

            if len(q) >= rpm:
                retry_after = max(1, int(window - (now - q[0])) + 1)
                return False, retry_after

            q.append(now)
            return True, 0

    def reset(self) -> None:
        """Clear all buckets (tests)."""
        with self._lock:
            self._hits.clear()


# Process-wide singleton used by REST middleware and MCP auth wrapper.
api_key_rate_limiter = PerKeyRateLimiter()


def rate_limit_response(retry_after: int):
    """Build a FastAPI/Starlette JSON 429 response."""
    from starlette.responses import JSONResponse

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded for this API key",
            "retry_after": retry_after,
        },
        headers={"Retry-After": str(retry_after)},
    )
