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
