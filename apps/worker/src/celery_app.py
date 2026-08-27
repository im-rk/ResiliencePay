import os
from celery import Celery
from celery.schedules import crontab

redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

app = Celery("resiliencepay_worker", broker=redis_url, backend=redis_url)

app.autodiscover_tasks(['apps.worker.src.tasks'])

app.conf.beat_schedule = {
    'reconcile-payment-status-every-hour': {
        'task': 'reconcile_payment_status',
        'schedule': crontab(minute=0),
    },
}
