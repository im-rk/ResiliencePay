import pytest
from unittest.mock import MagicMock
from services.audit.narrator import AuditNarrator, EpisodeNarrative

def sample_episode_facts():
    return {
        "cause_category": "insufficient_funds",
        "amount_rupees": 150.0,
        "attempt_count": 2,
        "actions_taken": "retry_immediate (status: completed), send_nudge_english (status: completed)",
        "blocked_actions": "None",
        "final_outcome": "closed",
        "time_to_resolution": "2.5 hours"
    }

def test_narrator_never_raises_and_falls_back_on_llm_failure(monkeypatch):
    narrator = AuditNarrator()
    
    def mock_create(*args, **kwargs):
        raise TimeoutError("llm slow")
        
    # Mock anthropic client
    narrator.client.messages.create = mock_create
    
    result = narrator.narrate(sample_episode_facts())
    assert result.method == "template_fallback"
    assert result.text  # non-empty
    assert "insufficient_funds" in result.text
