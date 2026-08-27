import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from apps.api.src.main import app

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_healthz_endpoint(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "resiliencepay-api"}


@pytest.mark.asyncio
async def test_trigger_batch_run_endpoint(client):
    response = await client.post("/v1/pipeline/run-batch", json={
        "n_events": 50,
        "policy": "bandit",
        "random_seed": 42,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["policy"] == "bandit"
    assert body["n_events"] == 50
    assert "recovery_rate" in body
    assert "amount_recovered" in body


@pytest.mark.asyncio
async def test_metrics_summary_endpoint(client):
    response = await client.get("/v1/metrics/summary?run_id=sample")
    assert response.status_code == 200
    body = response.json()
    assert "recovery_rate" in body or "n_events" in body


@pytest.mark.asyncio
async def test_learning_curve_endpoint(client):
    response = await client.get("/v1/metrics/learning-curve?run_id=sample&bucket_size=20")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0
    assert "cumulative_recovery_rate" in body[0]
