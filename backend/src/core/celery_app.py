from celery import Celery
from config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

# Initialize Celery app
celery_app = Celery(
    "grievance_tasks",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

# Celery settings
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Prevent database locks by running only 1 concurrent task per worker process if needed,
    # but since celery is horizontal we can use standard defaults.
)

# Auto-discover tasks from the 'workers' package
celery_app.autodiscover_tasks(["workers"])
