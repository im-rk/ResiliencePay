import os
from redis import Redis

print("Testing Redis (no query param)...")
try:
    r = Redis.from_url("rediss://default:gQAAAAAAAVhaAAIgcDI3YTg5ZDFjNWY0ZDU0MDAyOWNkNGMzMmZjY2FiYzQyNQ@creative-shepherd-88154.upstash.io:6379")
    r.ping()
    print("Redis connected!")
except Exception as e:
    print("Redis error:", e)
