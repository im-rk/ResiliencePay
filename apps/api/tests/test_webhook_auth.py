import hmac
import hashlib
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from apps.api.src.main import app
from packages.config.settings import settings

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c

def compute_hmac(body: bytes, secret: str) -> str:
    return hmac.new(
        key=secret.encode(),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()

@pytest.mark.asyncio
async def test_signature_verification_rejects_tampered_payload(client):
    body = b'{"event_id": "evt_1", "payment": {"id": "pay_1"}}'
    wrong_signature = "0" * 64
    response = await client.post("/v1/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": wrong_signature})
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_signature_verification_rejects_missing_signature(client):
    body = b'{"event_id": "evt_1", "payment": {"id": "pay_1"}}'
    response = await client.post("/v1/webhooks/razorpay", content=body)
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_signature_verification_accepts_correctly_signed_payload(client, mocker):
    # Mock acquire_webhook_processing_lock to avoid needing real redis
    mocker.patch("apps.api.src.routers.webhooks.acquire_webhook_processing_lock", return_value=False)
    
    body = b'{"event_id": "evt_1", "payment": {"id": "pay_1"}}'
    correct_signature = compute_hmac(body, settings.razorpay_webhook_secret)
    
    response = await client.post(
        "/v1/webhooks/razorpay", 
        content=body,
        headers={"X-Razorpay-Signature": correct_signature}
    )
    # Should not be 401. Since we mocked the lock to return False, it should return 200 with "already_processed"
    assert response.status_code == 200
    assert response.json()["status"] == "already_processed"
