import pytest
from datetime import datetime, timedelta

from services.gate.rules import check_cool_off, check_max_attempts, check_opt_out, check_time_window
from packages.db_models.models.episode import Episode

def make_episode(attempt_count=0, last_action_at=None):
    ep = Episode()
    ep.attempt_count = attempt_count
    ep.last_action_at = last_action_at
    return ep

def test_max_attempts_blocks_at_limit():
    episode = make_episode(attempt_count=3)
    assert check_max_attempts(episode, max_attempts=3) == ("blocked", "max_attempts_exceeded")

def test_max_attempts_passes_below_limit():
    episode = make_episode(attempt_count=2)
    assert check_max_attempts(episode, max_attempts=3) == "pass"

def test_cool_off_blocks_within_window():
    episode = make_episode(last_action_at=datetime.utcnow() - timedelta(hours=2))
    assert check_cool_off(episode, min_cool_off_hours=12, now=datetime.utcnow()) == ("blocked", "cool_off_active")

def test_cool_off_passes_with_no_prior_action():
    episode = make_episode(last_action_at=None)
    assert check_cool_off(episode, min_cool_off_hours=12, now=datetime.utcnow()) == "pass"

@pytest.mark.parametrize("hour,expected", [
    (8, ("blocked", "outside_communication_window")),
    (9, "pass"), 
    (19, "pass"),
    (20, ("blocked", "outside_communication_window"))
])
def test_time_window_boundaries(hour, expected):
    now = datetime(2026, 8, 20, hour, 0)
    assert check_time_window(now, allowed_hour_start=9, allowed_hour_end=20) == expected
