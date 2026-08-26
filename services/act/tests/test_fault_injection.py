import pytest
from unittest.mock import MagicMock
from services.act.fault_injection import SimulatedFault
from services.act.razorpay_client import RazorpayClient, RazorpayTransientError
from packages.config.settings import settings

def test_simulated_fault_treated_as_transient(monkeypatch):
    monkeypatch.setattr(settings, "fault_injection_enabled", True)
    monkeypatch.setattr(settings, "fault_injection_rate", 1.0)  # Always inject
    
    # We must patch the random.choice to always return server_error
    import random
    monkeypatch.setattr(random, "choice", lambda opts: "server_error")

    client = RazorpayClient(key_id="test", key_secret="test", max_retries=2, base_backoff_seconds=0.01)
    
    # Mock fn that would normally succeed
    fn = MagicMock(return_value={"id": "pl_123", "short_url": "", "status": ""})
    
    with pytest.raises(RazorpayTransientError) as exc_info:
        client._call_with_retry(
            fn=fn,
            result_mapper=lambda r: r,
            idempotency_key="test_key"
        )
        
    assert "exhausted 2 retries" in str(exc_info.value)
    
    # Assert that fn was never actually called because the fault was injected BEFORE the real call
    fn.assert_not_called()
