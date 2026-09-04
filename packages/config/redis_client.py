import redis
import os
from packages.config.settings import settings

redis_url = os.environ.get("REDIS_URL") or settings.upstash_redis_rest_url
if redis_url and redis_url.startswith("rediss://"):
    redis_client = redis.from_url(redis_url, ssl_cert_reqs="none", socket_connect_timeout=0.5, socket_timeout=1.0)
elif redis_url and redis_url.startswith("redis"):
    redis_client = redis.from_url(redis_url, socket_connect_timeout=0.5, socket_timeout=1.0)
else:
    redis_client = redis.Redis(socket_connect_timeout=0.5, socket_timeout=1.0)
