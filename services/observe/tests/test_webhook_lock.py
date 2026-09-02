import pytest
import fakeredis
from services.observe.webhook_lock import acquire_webhook_processing_lock

@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis()

def test_distributed_lock_prevents_concurrent_duplicate_processing(redis_client):
    event_id = "evt_123"
    
    # First attempt should acquire the lock successfully
    first = acquire_webhook_processing_lock(redis_client, event_id)
    assert first is True, "First call must acquire the lock"
    
    # Second attempt with same event_id should fail to acquire lock
    second = acquire_webhook_processing_lock(redis_client, event_id)
    assert second is False, "A second delivery of the same event_id must not acquire the lock"

def test_distributed_lock_allows_different_events(redis_client):
    first = acquire_webhook_processing_lock(redis_client, "evt_abc")
    second = acquire_webhook_processing_lock(redis_client, "evt_def")
    
    assert first is True
    assert second is True
