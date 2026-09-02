import pytest
import pytest_asyncio
import time
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch
from apps.api.src.main import app

from apps.api.src.middleware.webhook_auth import verify_razorpay_signature

@pytest_asyncio.fixture
async def client():
    def override_verify():
        return b'{"payment": {"id": "pay_123"}}'
    
    app.dependency_overrides[verify_razorpay_signature] = override_verify
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

@pytest.mark.asyncio
@patch("apps.api.src.routers.webhooks.redis_client")
@patch("apps.api.src.routers.webhooks.acquire_webhook_processing_lock")
async def test_ingress_returns_fast_and_does_not_block_on_processing(
    mock_lock, mock_redis, client
):
    mock_lock.return_value = True
    
    def slow_xadd(*args, **kwargs):
        pass
    mock_redis.xadd.side_effect = slow_xadd

    start = time.monotonic()
    response = await client.post(
        "/v1/webhooks/razorpay", 
        content=b'{"payment": {"id": "pay_123"}}', 
        headers={"x-razorpay-signature": "valid"}
    )
    elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert elapsed < 0.5, "ingress must return quickly regardless of downstream processing time"
    mock_redis.xadd.assert_called_once()
