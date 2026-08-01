"""
Celery application factory.

Queues:
  default       — general async work
  payroll       — payroll computation (CPU-heavy, rate-limited)
  documents     — PDF generation (RA bills, payroll slips)
  ocr           — PaddleOCR inference (GPU/CPU — separate concurrency pool)
  notifications — SMS / email / push (I/O-bound, high volume)

Beat schedule lives here for lightweight periodic tasks.
Business-critical schedules (payroll runs) are triggered explicitly by the
service layer, not by Beat, to ensure idempotency.
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "construction_platform",
    broker=settings.celery_broker_url.get_secret_value(),
    backend=settings.celery_result_backend.get_secret_value(),
    include=[
        "app.tasks.cleanup",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,          # re-queue on worker crash
    worker_prefetch_multiplier=1, # fair dispatch — don't starve slow tasks
    task_routes={
        "app.tasks.payroll.*": {"queue": "payroll"},
        "app.tasks.documents.*": {"queue": "documents"},
        "app.tasks.ocr.*": {"queue": "ocr"},
        "app.tasks.notifications.*": {"queue": "notifications"},
    },
    beat_schedule={
        # Prune expired refresh tokens nightly at 2 AM IST
        "prune-expired-refresh-tokens": {
            "task": "app.tasks.cleanup.prune_expired_refresh_tokens",
            "schedule": crontab(hour=2, minute=0),
        },
    },
)
