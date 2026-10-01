from celery import Celery

from app.config import settings

celery_app = Celery(
    "ai_backend",
    broker=settings.resolved_celery_broker_url,
    backend=settings.resolved_celery_result_backend,
)

celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Fail fast instead of retrying with backoff when Redis is unreachable —
    # .delay() is called from request handlers and must not hang them.
    broker_connection_retry_on_startup=False,
    broker_connection_retry=False,
    broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 2},
)

celery_app.autodiscover_tasks(["app.workers"])
