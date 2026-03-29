from celery import Celery

from src.config import settings

app = Celery(
    "dating_bot",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "recalculate-ratings-every-10min": {
            "task": "src.worker.tasks.recalculate_ratings",
            "schedule": 600.0,  # every 10 minutes
        },
    },
)

app.autodiscover_tasks(["src.worker"])
