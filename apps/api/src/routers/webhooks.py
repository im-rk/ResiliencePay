import json
import structlog
from fastapi import APIRouter, Depends

from apps.api.src.dependencies import get_db_session
from apps.api.src.middleware.webhook_auth import verify_razorpay_signature
from services.observe.webhook_lock import acquire_webhook_processing_lock
from packages.config.redis_client import redis_client

logger = structlog.get_logger()
router = APIRouter()


@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    raw_body: bytes = Depends(verify_razorpay_signature),
    db_session=Depends(get_db_session),
):
    payload = json.loads(raw_body)
    
    # Razorpay payload structure usually has event_id or payment id
    event_id = payload.get("event_id")
    if not event_id and "payload" in payload and "payment" in payload["payload"]:
        event_id = payload["payload"]["payment"]["entity"]["id"]
    elif not event_id and "payment" in payload:
        event_id = payload["payment"]["id"]
    
    if not event_id:
        # Fallback to an empty string or UUID if we absolutely can't find one,
        # but realistically Razorpay sends `event_id` or `x-razorpay-event-id`.
        # For safety:
        event_id = "unknown_event_id"

    if not acquire_webhook_processing_lock(redis_client, event_id):
        # Not an error — this is the expected, correct outcome for a
        # legitimate Razorpay redelivery. Return 200 so Razorpay does not
        # keep retrying an event we've already accepted.
        logger.info("webhook_duplicate_event_id_deduped", extra={"event_id": event_id})
        return {"status": "already_processed"}

    # Enqueue for async processing durably using Redis Streams
    redis_client.xadd("webhook_stream", {"payload": json.dumps(payload)})

    return {"status": "accepted"}
