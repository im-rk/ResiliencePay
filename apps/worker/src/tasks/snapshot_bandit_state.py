from celery import shared_task
from packages.db_models.database import SessionLocal
from services.decide.redis_store import RedisArmStatsStore
from services.decide.snapshot import snapshot_bandit_state_to_postgres
import redis
import os

# We would ideally get this from a central config/settings object
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

@shared_task(name="snapshot_bandit_state")
def task_snapshot_bandit_state():
    """
    Celery beat periodic task to snapshot bandit state from Redis to Postgres.
    """
    db = SessionLocal()
    client = redis.Redis.from_url(REDIS_URL)
    
    try:
        store = RedisArmStatsStore(client, default_priors={})
        rows_written = snapshot_bandit_state_to_postgres(store, db)
        return {"status": "success", "rows_written": rows_written}
    finally:
        db.close()
        client.close()
