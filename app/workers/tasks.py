"""Celery tasks.

Activity logging is moved here (off the request/response path) because it
is called from every authenticated action (login, task CRUD, AI generate)
but the client never needs to wait for it to finish, and it benefits from
Celery's retry semantics if the DB write fails transiently.

Tasks run in a plain sync worker process, so they use the sync DB session
(app.database_sync) rather than the FastAPI app's async engine.
"""

import asyncio
import logging

from app.celery_app import celery_app
from app.database_sync import SyncSessionLocal
from app.models.activity_log import ActivityLog

logger = logging.getLogger("app.workers")


@celery_app.task(name="log_activity_task", bind=True, max_retries=3, default_retry_delay=5)
def log_activity_task(self, user_id: int, action: str, detail: str | None = None) -> None:
    db = SyncSessionLocal()
    try:
        db.add(ActivityLog(user_id=user_id, action=action, detail=detail))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("log_activity_task failed, retrying: %s", exc)
        raise self.retry(exc=exc)
    finally:
        db.close()


def _safe_delay(user_id: int, action: str, detail: str | None) -> None:
    try:
        log_activity_task.delay(user_id=user_id, action=action, detail=detail)
    except Exception as exc:
        logger.warning("Could not enqueue activity log (Celery/Redis unavailable?): %s", exc)


async def enqueue_activity_log(user_id: int, action: str, detail: str | None = None) -> None:
    """Fire-and-forget activity logging, called from async routes.

    Activity logging is a non-critical side effect. `.delay()` does a
    synchronous socket call to the Redis broker, which would otherwise block
    the whole event loop if Redis is slow or down — so it runs in a worker
    thread. Celery/kombu's own connection-retry tuning turned out to still
    block for a very long time against an unreachable broker (observed to
    exceed 60s even with broker_connection_retry disabled), so the request
    does not trust that tuning: it waits at most 2 seconds for the enqueue,
    then moves on regardless. The background thread is left to finish (or
    fail) on its own; it swallows its own exceptions and never touches the
    response.
    """
    try:
        await asyncio.wait_for(asyncio.to_thread(_safe_delay, user_id, action, detail), timeout=2)
    except asyncio.TimeoutError:
        logger.warning("Activity log enqueue exceeded 2s timeout; continuing without it.")
