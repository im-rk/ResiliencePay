import pytest
from services.decide.bandit import ThompsonSamplingBandit, ARMS

class FakeStore:
    def __init__(self):
        self.data = {}
        for arm in ARMS:
            self.data[arm] = [1.0, 1.0] # alpha, beta
            
    def get_stats(self, merchant_id, bucket, arm):
        return self.data[arm][0], self.data[arm][1]
        
    def increment_alpha(self, merchant_id, bucket, arm, amount):
        self.data[arm][0] += amount
        
    def increment_beta(self, merchant_id, bucket, arm, amount):
        self.data[arm][1] += amount

@pytest.fixture
def fake_store():
    return FakeStore()

@pytest.fixture
def bandit_with_fake_store(fake_store):
    return ThompsonSamplingBandit(fake_store)

def test_invalid_reward_rejected(bandit_with_fake_store):
    with pytest.raises(ValueError):
        bandit_with_fake_store.update("test_merchant", "bucket", "arm", reward=1.5)
    with pytest.raises(ValueError):
        bandit_with_fake_store.update("test_merchant", "bucket", "arm", reward=-0.5)  # only -0.1 is a valid negative

def test_gate_blocked_penalty_only_touches_beta(bandit_with_fake_store, fake_store):
    alpha_before, beta_before = fake_store.get_stats("test_merchant", "bucket", "retry_immediate")
    bandit_with_fake_store.update("test_merchant", "bucket", "retry_immediate", reward=-0.1)
    alpha_after, beta_after = fake_store.get_stats("test_merchant", "bucket", "retry_immediate")
    
    assert alpha_after == alpha_before
    # Due to floating point math, we should use pytest.approx or round
    assert round(beta_after, 5) == round(beta_before + 0.1, 5)
