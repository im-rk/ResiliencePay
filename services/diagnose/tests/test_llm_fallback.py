from unittest.mock import patch, MagicMock
import anthropic
from services.diagnose.llm_fallback import classify
from packages.domain_constants.cause_categories import CauseCategoryEnum

@patch("services.diagnose.llm_fallback.client.messages.create")
def test_successful_llm_response(mock_create):
    mock_content = MagicMock()
    mock_content.type = "tool_use"
    mock_content.name = "provide_diagnosis"
    mock_content.input = {
        "cause_category": "insufficient_funds",
        "confidence": 0.95,
        "justification": "Clear NSF indicator"
    }
    
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    mock_create.return_value = mock_response
    
    result = classify("User has no money")
    
    assert result.method == "llm_fallback"
    assert result.cause_category == CauseCategoryEnum.INSUFFICIENT_FUNDS
    assert result.confidence == 0.95
    assert mock_create.call_count == 1

@patch("services.diagnose.llm_fallback.client.messages.create")
def test_timeout_fallback(mock_create):
    # Simulate timeout
    mock_create.side_effect = anthropic.APITimeoutError(request=MagicMock())
    
    result = classify("Some message")
    
    assert result.method == "fallback_failed"
    assert result.cause_category == CauseCategoryEnum.UNKNOWN
    assert result.confidence == 0.0
    # 1 initial + 2 retries = 3 calls
    assert mock_create.call_count == 3

@patch("services.diagnose.llm_fallback.client.messages.create")
def test_malformed_response_fallback(mock_create):
    mock_content = MagicMock()
    mock_content.type = "tool_use"
    mock_content.name = "provide_diagnosis"
    mock_content.input = {
        "cause_category": "fake_category", # Invalid enum
        "confidence": 0.95,
        "justification": "Bad output"
    }
    
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    mock_create.return_value = mock_response
    
    result = classify("Some message")
    
    assert result.method == "fallback_failed"
    assert result.cause_category == CauseCategoryEnum.UNKNOWN
    # 1 initial + 2 retries = 3 calls
    assert mock_create.call_count == 3
