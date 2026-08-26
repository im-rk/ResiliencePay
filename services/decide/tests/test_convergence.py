import numpy as np
import pytest
from services.decide.bandit import ThompsonSamplingBandit
from services.decide.redis_store import RedisArmStatsStore
import fakeredis

@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis()

def test_bandit_converges_to_better_arm(fake_redis, monkeypatch):
    store = RedisArmStatsStore(fake_redis, default_priors={"arm_good": (1,1), "arm_bad": (1,1)})
    bandit = ThompsonSamplingBandit(store)
    
    import services.decide.bandit
    monkeypatch.setattr(services.decide.bandit, "ARMS", ["arm_good", "arm_bad"])

    rng = np.random.default_rng(42)
    selections = {"arm_good": 0, "arm_bad": 0}

    for _ in range(500):
        choice = bandit.sample_arm("test_bucket")
        selections[choice.arm] += 1
        true_success_rate = 0.8 if choice.arm == "arm_good" else 0.2
        reward = 1.0 if rng.random() < true_success_rate else 0.0
        bandit.update("test_bucket", choice.arm, reward)

    # Assert convergence: by the end, arm_good should dominate selections.
    # Use a tolerance-based assertion, not an exact ratio — this is inherently stochastic.
    assert selections["arm_good"] > selections["arm_bad"] * 2, (
        f"expected arm_good to dominate after 500 rounds, got {selections}"
    )
