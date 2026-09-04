# Advanced Feature 6 — Webhook Signature Verification & Distributed-Lock Idempotency

**Effort:** ~half a day
**Builds on:** Phase 7 (Observe/webhook handlers)
**Demo impact:** High for a fintech-literate judge specifically — this is the single most concrete "this person has actually secured a payments webhook before" signal available

---

## The gap this closes

Two related gaps in the current webhook handler:

1. **No signature verification.** Any HTTP POST reaching
   `/webhooks/razorpay` is currently trusted and processed. In reality,
   anyone who discovers the URL could inject a fake `payment.captured`
   event and have your system record recovered revenue that never
   happened — a real, exploitable gap, not a theoretical one.
2. **Idempotency is reactive, not preventive.** The current design (DB
   unique constraint + `is_new` check after upsert) correctly prevents a
   *second* database row, but both concurrent requests still race into
   processing before either is blocked — wasteful, and in rarer timing
   windows, a source of subtle bugs. A lock acquired *before* processing
   begins is the stronger pattern.

## 1. HMAC signature verification

Razorpay signs every webhook payload with your account's webhook secret
using HMAC-SHA256, delivered in the `X-Razorpay-Signature` header. Verify
this **before** parsing the payload at all — an unverified payload should
never even reach your business logic.

### `apps/api/src/middleware/webhook_auth.py`

```python
import hashlib
import hmac

from fastapi import HTTPException, Request

from packages.config.settings import settings


async def verify_razorpay_signature(request: Request) -> bytes:
    """FastAPI dependency — use as Depends(verify_razorpay_signature) on
    the webhook route. Returns the raw body bytes so the route handler
    parses JSON from the SAME bytes that were verified, never from a
    separately re-read body (which could theoretically differ)."""
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="missing signature header")

    expected = hmac.new(
        key=settings.razorpay_webhook_secret.encode(),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # constant-time comparison — a naive == comparison leaks timing
    # information an attacker could exploit to guess the signature byte by byte
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="invalid signature")

    return raw_body
```

### Wiring into the route

```python
@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    raw_body: bytes = Depends(verify_razorpay_signature),
    db_session=Depends(get_db_session),
):
    payload = json.loads(raw_body)
    # only now, after verification, does the payload reach business logic
    ...
```

Add `razorpay_webhook_secret` to `packages/config/settings.py` as a
required field, sourced from Razorpay's dashboard for your test-mode
account — never hardcoded, never logged.

## 2. Distributed-lock idempotency via Redis, keyed on the event ID

Razorpay includes a unique `event_id` on every webhook delivery — this is
the correct idempotency key (not the payment ID alone, which could
legitimately appear across multiple distinct events for the same payment
over its lifecycle).

### `services/observe/webhook_lock.py`

```python
import redis

LOCK_TTL_SECONDS = 300  # long enough to cover realistic processing time, short enough not to permanently wedge a genuinely-failed attempt


def acquire_webhook_processing_lock(redis_client: redis.Redis, razorpay_event_id: str) -> bool:
    """Returns True if this call acquired the lock (i.e., this is the
    first time this event_id has been seen); False if another request
    already holds or has completed processing for this exact event.
    SET ... NX is atomic at the Redis level — no race window between
    'check if seen' and 'mark as seen', unlike a naive GET-then-SET."""
    key = f"webhook_lock:razorpay:{razorpay_event_id}"
    return bool(redis_client.set(key, "processing", nx=True, ex=LOCK_TTL_SECONDS))
```

### Wiring into the webhook handler

```python
async def razorpay_webhook(raw_body: bytes = Depends(verify_razorpay_signature), ...):
    payload = json.loads(raw_body)
    event_id = payload["event_id"] if "event_id" in payload else payload["payment"]["id"]  # fallback for older payload shapes

    if not acquire_webhook_processing_lock(redis_client, event_id):
        # Not an error — this is the expected, correct outcome for a
        # legitimate Razorpay redelivery. Return 200 so Razorpay does not
        # keep retrying an event we've already accepted.
        logger.info("webhook_duplicate_event_id_deduped", extra={"event_id": event_id})
        return {"status": "already_processed"}

    handle_payment_captured_webhook(payload, db_session, bandit, reward_service, audit_log_service)
    return {"status": "processed"}
```

**This sits alongside, not instead of, the existing DB-level idempotency
from Phase 7** — the Redis lock is a fast, cheap first line of defense
that prevents redundant processing from even starting; the DB unique
constraint remains the durable, authoritative guarantee if the lock were
ever somehow bypassed (e.g., Redis unavailability). Defense in depth, not
a replacement.

## Test to write

```python
def test_signature_verification_rejects_tampered_payload(test_client):
    body = b'{"event_id": "evt_1", "payment": {"id": "pay_1"}}'
    wrong_signature = "0" * 64
    response = test_client.post("/webhooks/razorpay", content=body,
                                  headers={"X-Razorpay-Signature": wrong_signature})
    assert response.status_code == 401

def test_signature_verification_accepts_correctly_signed_payload(test_client):
    body = b'{"event_id": "evt_1", "payment": {"id": "pay_1"}}'
    correct_signature = compute_hmac(body, settings.razorpay_webhook_secret)
    response = test_client.post("/webhooks/razorpay", content=body,
                                  headers={"X-Razorpay-Signature": correct_signature})
    assert response.status_code != 401

def test_distributed_lock_prevents_concurrent_duplicate_processing(redis_client):
    first = acquire_webhook_processing_lock(redis_client, "evt_123")
    second = acquire_webhook_processing_lock(redis_client, "evt_123")
    assert first is True
    assert second is False, "a second delivery of the same event_id must not acquire the lock"
```

## What to say in the demo

*"Every webhook is HMAC-verified before we even parse the payload — an
unsigned or tampered request never reaches our business logic, it's
rejected with a 401 at the edge. And idempotency is enforced twice:
a Redis lock acquired atomically before processing starts, as the fast
path, backed by a database unique constraint as the durable guarantee —
so a Razorpay redelivery, which their docs explicitly say to expect, can
never cause us to double-process a recovered payment."*
