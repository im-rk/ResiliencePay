# Advanced Feature 11 — Asynchronous Webhook Ingestion

**Effort:** ~1 day
**Builds on:** Phase 7 (Observe), Phase 9 (API)
**Priority note:** Real and legitimate, but read the "honest scope check" section before committing time to this — it's the most substantial of the remaining additions relative to its demo-visible payoff

---

## The gap this closes

Right now, your webhook handler processes the full detect-diagnose-decide
loop **synchronously**, within the HTTP request/response cycle. This means
the handler's response time is bounded by the slowest thing it does —
which, if the Diagnose step's LLM fallback is invoked, could be several
seconds. Razorpay (like most webhook providers) expects a fast
acknowledgment and may consider a slow-responding endpoint unhealthy or
retry aggressively. The correct production pattern is to **acknowledge
receipt instantly, then process asynchronously.**

## The pattern

```
Razorpay POST → [verify signature] → [acquire idempotency lock] →
    publish to a queue → return 200 OK immediately (milliseconds)
                              |
                              v
              Background worker consumes from the queue,
              runs the full detect-diagnose-decide-act loop
```

## Implementation

### `apps/api/src/routers/webhooks.py` — the now-instant ingress

```python
@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    raw_body: bytes = Depends(verify_razorpay_signature),  # from ADVANCED_06
    redis_client=Depends(get_redis_client),
):
    payload = json.loads(raw_body)
    event_id = payload.get("event_id") or payload["payment"]["id"]

    if not acquire_webhook_processing_lock(redis_client, event_id):  # from ADVANCED_06 — still applied HERE, at ingress
        return {"status": "already_processed"}

    # Enqueue for async processing — this is the only new step.
    redis_client.publish("webhook_events", json.dumps(payload))
    # Alternative if you want durability beyond pub/sub's fire-and-forget
    # semantics: use a Redis Stream (XADD) instead of pub/sub, so a
    # consumer that's briefly down doesn't silently miss an event —
    # see "Honest scope check" below for why this distinction matters.

    return {"status": "accepted"}  # returned within milliseconds
```

### `apps/worker/src/tasks/process_webhook_event.py` — the consumer

```python
def consume_webhook_events(redis_client):
    pubsub = redis_client.pubsub()
    pubsub.subscribe("webhook_events")
    for message in pubsub.listen():
        if message["type"] != "message":
            continue
        payload = json.loads(message["data"])
        try:
            handle_payment_captured_webhook(payload, db_session, bandit, reward_service, audit_log_service)
        except Exception:
            logger.exception("webhook_processing_failed", extra={"payload": payload})
            # See "Honest scope check" — plain pub/sub has no built-in
            # redelivery for a failed consumer; a Stream-based approach
            # (XADD/XREADGROUP) would let you retry or dead-letter this.
```

## Honest scope check — read this before building

**Plain Redis Pub/Sub is fire-and-forget.** If your worker process is down
or crashes mid-message, that event is silently lost — no redelivery, no
persistence. For a real production system, you would use **Redis Streams**
(`XADD`/`XREADGROUP` with consumer groups) instead, which durably persist
messages and support acknowledgment/redelivery semantics much closer to a
real message queue (Kafka, SQS). This is a meaningfully more correct
choice, and if you build this feature, **build it with Streams, not bare
Pub/Sub** — the code above uses Pub/Sub for illustration brevity only;
implementing it with Pub/Sub in your real submission would be a regression
relative to the synchronous version's actual reliability, not an
improvement, since your synchronous handler at least fails loudly (returns
an error Razorpay will retry) rather than silently dropping a message.

Given this, the corrected recommendation: **either build this properly
with Redis Streams (~1 day, as scoped), or skip it entirely and keep the
synchronous handler.** Do not ship the naive Pub/Sub version — it would be
a net reliability regression dressed up as a sophistication signal, and a
judge who understands the Pub/Sub-vs-Streams distinction would notice
immediately.

### Corrected consumer using Streams

```python
def consume_webhook_events_durable(redis_client):
    GROUP, CONSUMER = "webhook_processors", "worker-1"
    try:
        redis_client.xgroup_create("webhook_stream", GROUP, mkstream=True)
    except redis.ResponseError:
        pass  # group already exists

    while True:
        messages = redis_client.xreadgroup(GROUP, CONSUMER, {"webhook_stream": ">"}, count=1, block=5000)
        for stream, entries in messages:
            for entry_id, fields in entries:
                try:
                    payload = json.loads(fields[b"payload"])
                    handle_payment_captured_webhook(payload, db_session, bandit, reward_service, audit_log_service)
                    redis_client.xack("webhook_stream", GROUP, entry_id)  # only ack on success
                except Exception:
                    logger.exception("webhook_processing_failed_will_retry", extra={"entry_id": entry_id})
                    # Left unacked — will be redelivered to this or another
                    # consumer via XCLAIM/XAUTOCLAIM after a visibility timeout.
```

## Test to write

```python
def test_ingress_returns_fast_and_does_not_block_on_processing(test_client, monkeypatch):
    def slow_processing(*args, **kwargs):
        time.sleep(3)  # simulates a slow LLM call
    monkeypatch.setattr("...", slow_processing)  # patched at the CONSUMER, not the ingress

    start = time.monotonic()
    response = test_client.post("/webhooks/razorpay", content=valid_signed_payload(), headers=valid_signature_header())
    elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert elapsed < 0.5, "ingress must return quickly regardless of downstream processing time"

def test_failed_processing_is_redelivered_not_lost(redis_client):
    """Proves the Streams-based consumer's core durability property —
    this test would FAIL against the naive Pub/Sub version, which is
    exactly why Pub/Sub alone is the wrong choice here."""
    publish_test_event(redis_client, "evt_1")
    consume_with_forced_failure(redis_client, fail_once=True)
    remaining = redis_client.xpending("webhook_stream", "webhook_processors")
    assert remaining["pending"] >= 1, "a failed message must remain pending for redelivery, not be silently dropped"
```

## What to say in the demo

*"Our webhook ingress acknowledges Razorpay within milliseconds regardless
of downstream processing time — we don't want a slow LLM classification
call to risk a webhook timeout or retry storm. We used Redis Streams
rather than plain Pub/Sub specifically because Streams give us durable,
acknowledged delivery — if our worker crashes mid-processing, the message
is redelivered, not silently lost, which matters a great deal when the
message represents a real payment recovery outcome."*
