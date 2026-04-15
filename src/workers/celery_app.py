from celery import Celery
from celery.schedules import crontab

from src.config import load_settings

settings = load_settings()

celery = Celery(
    "deployments",
    include=[
        "src.workers.build",
        "src.workers.deploy",
        "src.workers.cleanup",
    ],
)

celery.conf.update(
    broker_url=settings.redis.url,
    result_backend=settings.redis.url,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_routes={
        "src.workers.build.run_build": {"queue": "build"},
        "src.workers.deploy.run_deploy": {"queue": "deploy"},
        "src.workers.cleanup.cleanup_stale_jobs": {"queue": "build"},
    },
    beat_schedule={
        "cleanup-stale-jobs": {
            "task": "src.workers.cleanup.cleanup_stale_jobs",
            "schedule": crontab(minute="*/5"),
        },
    },
)
