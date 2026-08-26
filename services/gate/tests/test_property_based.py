import pytest
from hypothesis import given, settings, strategies as st
from services.gate.rules import check_max_attempts
from unittest.mock import MagicMock

@settings(max_examples=1000)
@given(
    attempt_count=st.integers(min_value=0, max_value=100),
    max_attempts=st.integers(min_value=1, max_value=10)
)
def test_gate_never_allows_exceeded_attempts(attempt_count, max_attempts):
    """
    Mathematically prove the gate never allows an action when attempt_count >= max_attempts,
    across 1000 fuzzed generative cases.
    """
    episode = MagicMock(attempt_count=attempt_count)
    result = check_max_attempts(episode, max_attempts=max_attempts)
    
    if attempt_count >= max_attempts:
        assert isinstance(result, tuple) and result[0] == "blocked"
    else:
        assert result == "pass"
