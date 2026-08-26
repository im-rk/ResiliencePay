import pytest
from datetime import datetime, timedelta, timezone
from services.gate import rules
from unittest.mock import MagicMock

def test_check_max_attempts():
    episode = MagicMock(attempt_count=3)
    assert rules.check_max_attempts(episode, max_attempts=3) == ("blocked", "max_attempts_exceeded")
    
    episode.attempt_count = 2
    assert rules.check_max_attempts(episode, max_attempts=3) == "pass"

def test_check_opt_out():
    db = MagicMock()
    # Mock return value true for blocking
    db.query().filter().first.return_value = True
    assert rules.check_opt_out("cust_1", db) == ("blocked", "customer_opted_out")
    
    # Mock return value false for passing
    db.query().filter().first.return_value = None
    assert rules.check_opt_out("cust_1", db) == "pass"

def test_check_cool_off():
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    # Last action was 1 hour ago (blocked)
    episode = MagicMock(last_action_at=now - timedelta(hours=1))
    assert rules.check_cool_off(episode, min_gap_hours=24, now=now) == ("blocked", "cool_off_active")
    
    # Last action was 25 hours ago (pass)
    episode = MagicMock(last_action_at=now - timedelta(hours=25))
    assert rules.check_cool_off(episode, min_gap_hours=24, now=now) == "pass"
    
    # No last action (pass)
    episode = MagicMock(last_action_at=None)
    assert rules.check_cool_off(episode, min_gap_hours=24, now=now) == "pass"

def test_check_time_window():
    # 10 AM is allowed (9-20)
    now = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    assert rules.check_time_window(now) == "pass"
    
    # 8 AM is blocked
    now = datetime(2026, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
    assert rules.check_time_window(now) == ("blocked", "outside_communication_window")
    
    # 21 PM is blocked
    now = datetime(2026, 1, 1, 21, 0, 0, tzinfo=timezone.utc)
    assert rules.check_time_window(now) == ("blocked", "outside_communication_window")
