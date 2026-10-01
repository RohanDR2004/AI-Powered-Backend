"""Async, Redis-backed fixed-window rate limiting.

slowapi (the common FastAPI rate-limiting library) checks its Redis-backed
storage synchronously inside the request, even for async routes (confirmed
by reading slowapi/extension.py: `self._check_request_limit(...)` is called
directly, not awaited or offloaded) — exactly the kind of blocking call that
froze the whole event loop for Celery in this project. Rather than rely on
that, this is a small dependency that uses the app's own async Redis client,
bounded by a timeout, and fails open (allows the request) if Redis is slow
or unreachable — rate limiting is a non-critical defense, and it must not
take down login/register/AI generate when Redis is down.
"""

import asyncio
import logging

from fastapi import HTTPException, Request, status

from app.redis_client import redis_client

logger = logging.getLogger("app.rate_limit")

_PERIOD_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


def _parse_limit(limit: str) -> tuple[int, int]:
    """Parse "5/minute" -> (5, 60)."""
    count_str, _, period = limit.partition("/")
    return int(count_str), _PERIOD_SECONDS[period.strip().lower()]


class RateLimiter:
    def __init__(self, limit: str):
        self.max_requests, self.window_seconds = _parse_limit(limit)

    async def __call__(self, request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{request.url.path}:{client_ip}"

        try:
            current = await asyncio.wait_for(self._increment(key), timeout=0.5)
        except Exception as exc:
            logger.warning("Rate limiter unavailable (%s); allowing request through.", exc)
            return

        if current > self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit exceeded: {self.max_requests} requests per "
                    f"{self.window_seconds}s. Try again later."
                ),
                headers={"Retry-After": str(self.window_seconds)},
            )

    async def _increment(self, key: str) -> int:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, self.window_seconds)
        return count
