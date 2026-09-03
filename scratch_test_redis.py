import redis
import os

token = "gQAAAAAAAVhaAAIgcDI3YTg5ZDFjNWY0ZDU0MDAyOWNkNGMzMmZjY2FiYzQyNQ"
host = "creative-shepherd-88154.upstash.io"
url = f"rediss://default:{token}@{host}:6379"

print(url)
r = redis.from_url(url, ssl_cert_reqs="none")
r.ping()
print("Ping successful!")
