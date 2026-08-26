import pytest
import concurrent.futures
from services.decide.bandit import ThompsonSamplingBandit
from services.decide.redis_store import RedisArmStatsStore
from testcontainers.redis import RedisContainer
import redis

@pytest.fixture(scope="module")
def real_redis_test_instance():
    with RedisContainer("redis:alpine") as redis_server:
        client = redis_server.get_client()
        yield client

def test_concurrent_updates_no_lost_writes(real_redis_test_instance):
    store = RedisArmStatsStore(real_redis_test_instance, default_priors={"arm": (1.0, 1.0)})
    bandit = ThompsonSamplingBandit(store)

    def do_update():
        bandit.update("concurrent_bucket", "arm", reward=1.0)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(do_update) for _ in range(50)]
        concurrent.futures.wait(futures)

    alpha, beta = store.get_stats("concurrent_bucket", "arm")
    # Started at alpha=1.0, 50 updates each with reward=1.0 -> alpha should be 1.0 + 50 = 51.0
    assert alpha == 51.0, f"expected 51.0 after 50 concurrent updates, got {alpha}"
    assert beta == 1.0  # unchanged, since every reward was a full success
