import redis

url = "rediss://default:gQAAAAAAAVhaAAIgcDI3YTg5ZDFjNWY0ZDU0MDAyOWNkNGMzMmZjY2FiYzQyNQ@creative-shepherd-88154.upstash.io:6379"
try:
    r = redis.from_url(url)
    r.ping()
    print("SUCCESS: 6379")
except Exception as e:
    print("FAILED 6379:", e)
