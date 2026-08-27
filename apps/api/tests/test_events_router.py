import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from apps.api.src.main import app

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_get_nonexistent_event_returns_structured_404(client):
    response = await client.get("/v1/events/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] is True
    assert body["code"] == "NOT_FOUND"
    assert "event not found" in body["reason"].lower()


@pytest.mark.asyncio
async def test_ingest_event_validates_input(client):
    response = await client.post("/v1/events/ingest", json={"event_type": "payment_failed"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ingest_event_rejects_negative_amount(client):
    response = await client.post("/v1/events/ingest", json={
        "event_type": "payment_failed",
        "merchant_id": "merch_123",
        "customer_id": "cust_123",
        "amount": -500,
        "currency": "INR",
        "customer_segment": "new",
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ingest_event_success(client):
    response = await client.post("/v1/events/ingest", json={
        "event_type": "payment_failed",
        "merchant_id": "merch_123",
        "customer_id": "cust_123",
        "amount": 150000,
        "currency": "INR",
        "customer_segment": "new",
    })
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued_for_diagnosis"
    assert body["amount"] == 150000
