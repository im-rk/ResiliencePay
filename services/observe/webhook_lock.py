import redis

LOCK_TTL_SECONDS = 300  # long enough to cover realistic processing time, short enough not to permanently wedge a genuinely-failed attempt


def acquire_webhook_processing_lock(redis_client: redis.Redis, razorpay_event_id: str) -> bool:
    """Returns True if this call acquired the lock (i.e., this is the
    first time this event_id has been seen); False if another request
    already holds or has completed processing for this exact event.
    SET ... NX is atomic at the Redis level — no race window between
    'check if seen' and 'mark as seen', unlike a naive GET-then-SET."""
    key = f"webhook_lock:razorpay:{razorpay_event_id}"
    # Redis REST client returns a value (e.g. "OK" or True) if SET NX succeeds, None/False if it doesn't.
    # In upstash redis python client, set(nx=True) returns True if set, None if not set.
    return bool(redis_client.set(key, "processing", nx=True, ex=LOCK_TTL_SECONDS))
