from celery import Celery

from app.core.config import Settings


def create_celery_app(settings: Settings) -> Celery:
    """Build the shared Celery app without opening a Redis connection."""
    redis_url = settings.redis.url
    app = Celery(
        "flowchart_toolbox",
        broker=settings.celery.broker_url or redis_url,
        backend=settings.celery.result_backend or redis_url,
        include=["app.workers.tasks"],
    )
    app.conf.update(
        accept_content=["json"],
        beat_schedule={
            "flowchart-compensate-tasks": {
                "task": "flowchart.tasks.compensate",
                "schedule": 60.0,
            },
            "flowchart-cleanup-export-files": {
                "task": "flowchart.files.cleanup",
                "schedule": 300.0,
            },
        },
        broker_connection_retry_on_startup=True,
        enable_utc=False,
        result_serializer="json",
        task_serializer="json",
        task_acks_late=True,
        task_default_queue=settings.celery.task_default_queue,
        task_ignore_result=True,
        task_track_started=True,
        timezone="Asia/Shanghai",
        worker_prefetch_multiplier=1,
    )
    return app
