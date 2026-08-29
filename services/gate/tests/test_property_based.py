from hypothesis import given, strategies as st
from services.gate.rules import check_max_attempts
from packages.db_models.models.episode import Episode

def make_episode(attempt_count=0):
    ep = Episode()
    ep.attempt_count = attempt_count
    return ep

@given(attempt_count=st.integers(min_value=0, max_value=20), max_attempts=st.integers(min_value=1, max_value=5))
def test_never_passes_at_or_above_max_attempts(attempt_count, max_attempts):
    episode = make_episode(attempt_count=attempt_count)
    result = check_max_attempts(episode, max_attempts=max_attempts)
    
    if attempt_count >= max_attempts:
        assert isinstance(result, tuple) and result[0] == "blocked"
    else:
        assert result == "pass"
