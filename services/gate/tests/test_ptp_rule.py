import pytest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch
from services.gate.rules import check_active_promise_to_pay

@pytest.fixture
def mock_db_session():
    return MagicMock()

@pytest.fixture
def mock_episode():
    ep = MagicMock()
    ep.episode_id = "test-episode-id"
    return ep

@patch("services.gate.persistence.get_active_promise")
def test_check_active_promise_to_pay_blocks(mock_get_active_promise, mock_episode, mock_db_session):
    ptp = MagicMock()
    ptp.promised_date = date.today() + timedelta(days=5)
    mock_get_active_promise.return_value = ptp
    
    result = check_active_promise_to_pay(mock_episode, mock_db_session, datetime.utcnow())
    assert result == ("blocked", "active_promise_to_pay")

@patch("services.gate.persistence.get_active_promise")
def test_check_active_promise_to_pay_passes_if_expired(mock_get_active_promise, mock_episode, mock_db_session):
    ptp = MagicMock()
    ptp.promised_date = date.today() - timedelta(days=2) # Grace period is 1 day, so this is past grace period
    mock_get_active_promise.return_value = ptp
    
    result = check_active_promise_to_pay(mock_episode, mock_db_session, datetime.utcnow())
    assert result == "pass"

@patch("services.gate.persistence.get_active_promise")
def test_check_active_promise_to_pay_passes_if_none(mock_get_active_promise, mock_episode, mock_db_session):
    mock_get_active_promise.return_value = None
    
    result = check_active_promise_to_pay(mock_episode, mock_db_session, datetime.utcnow())
    assert result == "pass"
