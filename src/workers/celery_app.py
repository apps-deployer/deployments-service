from celery import Celery

from src.config import load_settings

settings = load_settings()

celery = Celery("deployments")

celery.conf.update(
    broker_url=settings.redis.url,
    result_backend=settings.redis.url,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_routes={
        "src.workers.build.run_build": {"queue": "build"},
        "src.workers.deploy.run_deploy": {"queue": "deploy"},
    },
)
