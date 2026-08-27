import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from apps.api.src.main import app

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_unexpected_exception_never_leaks_stack_trace(client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("something deeply internal broke, with sensitive details: SECRET_TOKEN=abc123_DO_NOT_LEAK")

    monkeypatch.setattr("apps.api.src.routers.events.get_event_full_state", boom)

    response = await client.get("/v1/events/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 500
    body = response.json()
    assert "SECRET_TOKEN" not in response.text, "Sensitive internal details must NEVER leak to client"
    assert body["error"] is True
    assert body["code"] == "INTERNAL_ERROR"
    assert "request_id" in body
