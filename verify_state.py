import sys
import os

# Ensure the current directory is in PYTHONPATH so we can import from packages
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from packages.db_models.database import get_db
from packages.db_models.models import AuditLog
from packages.config.redis_client import redis_client

print("--- END TO END VERIFICATION ---")

try:
    db_gen = get_db()
    db = next(db_gen)
    log_count = db.query(AuditLog).count()
    print(f"[SUCCESS] Connected to Supabase. Total AuditLog rows: {log_count}")
except Exception as e:
    print(f"[ERROR] Failed to query Supabase: {e}")

try:
    keys = redis_client.keys("bandit:merch_demo01:*")
    print(f"[SUCCESS] Connected to Upstash Redis. Total Context/Arm distributions learned: {len(keys)}")
    if len(keys) > 0:
        sample_key = keys[0]
        sample_val = redis_client.hgetall(sample_key)
        print(f"          Example: {sample_key.decode()} = {sample_val}")
except Exception as e:
    print(f"[ERROR] Failed to query Upstash Redis: {e}")

print("-------------------------------")
