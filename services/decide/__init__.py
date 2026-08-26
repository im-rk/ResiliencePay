from services.decide.bandit import ThompsonSamplingBandit, BanditPolicy, ArmChoice
from services.decide.redis_store import RedisArmStatsStore
from services.decide.context import context_bucket_for
from packages.domain_constants.bandit_priors import DEFAULT_PRIORS
import redis

# We accept a redis client rather than hardcoding connection URL here, 
# to allow tests and eval scripts to inject fake or configured clients.
def get_bandit_policy(redis_client: redis.Redis) -> BanditPolicy:
    """
    Factory function wiring up the Contextual Bandit policy with its 
    Redis store and domain priors.
    """
    store = RedisArmStatsStore(redis_client, default_priors=DEFAULT_PRIORS)
    return ThompsonSamplingBandit(store)

__all__ = ["get_bandit_policy", "context_bucket_for", "BanditPolicy", "ArmChoice"]
