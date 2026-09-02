import pytest
from unittest.mock import patch, MagicMock
from datetime import date
from services.observe.ptp_extraction import extract_promise_to_pay

@patch("services.observe.ptp_extraction.model.generate_content")
def test_extract_promise_to_pay_success(mock_generate):
    mock_response = MagicMock()
    mock_response.text = '{"promised_date": "2026-09-10", "confidence": 0.95}'
    mock_generate.return_value = mock_response
    
    result = extract_promise_to_pay("I will pay on Sep 10th.")
    
    assert result is not None
    assert result.promised_date == date(2026, 9, 10)
    assert result.confidence == 0.95

@patch("services.observe.ptp_extraction.model.generate_content")
def test_extract_promise_to_pay_low_confidence(mock_generate):
    mock_response = MagicMock()
    mock_response.text = '{"promised_date": "2026-09-10", "confidence": 0.5}'
    mock_generate.return_value = mock_response
    
    result = extract_promise_to_pay("Maybe sometime next week.")
    
    assert result is None

@patch("services.observe.ptp_extraction.model.generate_content")
def test_extract_promise_to_pay_no_date(mock_generate):
    mock_response = MagicMock()
    mock_response.text = '{"promised_date": null, "confidence": 0.9}'
    mock_generate.return_value = mock_response
    
    result = extract_promise_to_pay("I am not sure when I can pay.")
    
    assert result is None
