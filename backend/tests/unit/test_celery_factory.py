from app.core.config import Settings
from app.workers.factory import create_celery_app


def test_celery_uses_redis_when_no_explicit_urls_are_configured():
    settings = Settings(_env_file=None)
    settings.redis.url = "redis://localhost:6379/3"

    celery_app = create_celery_app(settings)

    assert celery_app.conf.broker_url == "redis://localhost:6379/3"
    assert celery_app.conf.result_backend == "redis://localhost:6379/3"
    assert celery_app.conf.task_default_queue == "flowchart"
    assert celery_app.conf.timezone == "Asia/Shanghai"


def test_celery_allows_dedicated_broker_and_result_backend():
    settings = Settings(_env_file=None)
    settings.celery.broker_url = "redis://broker:6379/4"
    settings.celery.result_backend = "redis://result:6379/5"
    settings.celery.task_default_queue = "flowchart_tasks"

    celery_app = create_celery_app(settings)

    assert celery_app.conf.broker_url == "redis://broker:6379/4"
    assert celery_app.conf.result_backend == "redis://result:6379/5"
    assert celery_app.conf.task_default_queue == "flowchart_tasks"


def test_celery_registers_task_module_and_compensation_schedule():
    settings = Settings(_env_file=None)
    celery_app = create_celery_app(settings)

    assert "app.workers.tasks" in celery_app.conf.include
    schedule = celery_app.conf.beat_schedule["flowchart-compensate-tasks"]
    assert schedule["task"] == "flowchart.tasks.compensate"
    assert schedule["schedule"] == 60.0
    assert celery_app.conf.task_serializer == "json"
