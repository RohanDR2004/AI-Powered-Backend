import asyncio
import time
from unittest.mock import patch

import pytest

from app.workers.tasks import enqueue_activity_log


@pytest.mark.asyncio
async def test_enqueue_activity_log_does_not_block_past_timeout():
    """Regression test: a slow/unreachable Celery broker must not hang the
    calling request. enqueue_activity_log should give up after ~2s even if
    the underlying dispatch call never returns."""

    def never_returns(*args, **kwargs):
        # Short enough that the leaked background thread (asyncio.wait_for
        # cancels waiting but can't kill the thread) doesn't stall process
        # exit, long enough to prove the 2s timeout actually triggers.
        time.sleep(5)

    with patch("app.workers.tasks._safe_delay", side_effect=never_returns):
        start = asyncio.get_event_loop().time()
        await enqueue_activity_log(user_id=1, action="test", detail=None)
        elapsed = asyncio.get_event_loop().time() - start

    assert elapsed < 5, f"enqueue_activity_log took {elapsed}s, expected it to time out around 2s"
