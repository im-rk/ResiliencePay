import redis
import os
from packages.config.settings import settings

redis_url = os.environ.get("REDIS_URL") or settings.upstash_redis_rest_url
redis_client = redis.from_url(redis_url) if redis_url.startswith("redis") else redis.Redis()
