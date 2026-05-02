import logging

import requests

from src.workers.celery_app import celery
from src.config import load_settings
from src.workers.urls import internal_url

logger = logging.getLogger(__name__)


@celery.task(name="src.workers.cleanup.cleanup_stale_jobs")
def cleanup_stale_jobs():
    settings = load_settings()
    url = internal_url(settings.server.service_url, "/internal/cleanup")
    try:
        resp = requests.post(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        count = data.get("cleaned", 0)
        if count:
            logger.info("Stale job cleanup: marked %d job(s) as failed", count)
        else:
            logger.debug("Stale job cleanup: nothing to clean")
    except Exception as exc:
        logger.error("Stale job cleanup failed: %s", exc)
