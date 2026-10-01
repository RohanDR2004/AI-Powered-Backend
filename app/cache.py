"""Thin async caching helper over the app's Redis client.

Every operation is bounded by a short timeout and swallows its own
exceptions: a cache read failure falls back to the database (treated as a
miss), and a cache write/invalidation failure is logged and ignored. Same
reasoning as app/rate_limit.py and app/workers/tasks.py — caching is a
non-critical optimization and must never make GET /tasks, task CRUD, etc.
less reliable than they'd be with no cache at all.
"""

import asyncio
import json
import logging
from typing import Any

from app.redis_client import redis_client

logger = logging.getLogger("app.cache")

_TIMEOUT_SECONDS = 0.5


async def get_cached(key: str) -> Any | None:
    try:
        raw = await asyncio.wait_for(redis_client.get(key), timeout=_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.warning("Cache read failed for %s (%s); falling back to the database.", key, exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


async def set_cached(key: str, value: Any, ttl_seconds: int) -> None:
    try:
        await asyncio.wait_for(
            redis_client.set(key, json.dumps(value), ex=ttl_seconds), timeout=_TIMEOUT_SECONDS
        )
    except Exception as exc:
        logger.warning("Cache write failed for %s (%s); continuing without it.", key, exc)


async def invalidate(*keys: str) -> None:
    if not keys:
        return
    try:
        await asyncio.wait_for(redis_client.delete(*keys), timeout=_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.warning("Cache invalidation failed for %s (%s).", keys, exc)


async def invalidate_pattern(pattern: str) -> None:
    async def _do() -> None:
        keys = [key async for key in redis_client.scan_iter(match=pattern)]
        if keys:
            await redis_client.delete(*keys)

    try:
        await asyncio.wait_for(_do(), timeout=_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.warning("Cache invalidation failed for pattern %s (%s).", pattern, exc)
