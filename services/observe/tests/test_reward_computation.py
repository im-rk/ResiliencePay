import pytest
from services.observe.reward_service import RewardService

class MockOutcome:
    def __init__(self, result):
        self.result = result

def make_fake_outcome(result):
    return MockOutcome(result=result)

@pytest.mark.parametrize("result,expected_reward", [
    ("recovered", 1.0),
    ("not_recovered", 0.0),
    ("pending", 0.0),
    ("failed_permanently", 0.0),
    ("blocked_by_policy", -0.1),
])
def test_reward_mapping(result, expected_reward):
    service = RewardService()
    outcome = make_fake_outcome(result=result)
    assert service.compute(outcome) == expected_reward

def test_unrecognized_result_raises():
    service = RewardService()
    outcome = make_fake_outcome(result="some_new_unhandled_state")
    with pytest.raises(ValueError, match="unrecognized outcome.result"):
        service.compute(outcome)
