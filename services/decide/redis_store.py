import redis
from services.decide.hierarchical_priors import blend_priors

class RedisArmStatsStore:
    def __init__(self, client: redis.Redis, default_priors: dict[str, tuple[float, float]]):
        self.client = client
        self.default_priors = default_priors  # {arm: (alpha, beta)}

    def _merchant_key(self, merchant_id: str, context_bucket: str, arm: str) -> str:
        return f"bandit:{merchant_id}:{context_bucket}:{arm}"
        
    def _global_key(self, context_bucket: str, arm: str) -> str:
        return f"bandit:GLOBAL:{context_bucket}:{arm}"

    def _ensure_materialized(self, key: str, arm: str):
        alpha, beta = self.default_priors.get(arm, (1.0, 1.0))
        # hsetnx is atomic: only sets the field if it doesn't already exist.
        # This prevents a race where multiple threads overwrite each other's increments
        # with the base prior.
        self.client.hsetnx(key, "alpha", alpha)
        self.client.hsetnx(key, "beta", beta)

    def get_stats(self, merchant_id: str, context_bucket: str, arm: str) -> tuple[float, float]:
        merchant_key = self._merchant_key(merchant_id, context_bucket, arm)
        global_key = self._global_key(context_bucket, arm)

        merchant_raw = self.client.hgetall(merchant_key)
        global_raw = self.client.hgetall(global_key)
        
        global_alpha, global_beta = (
            (float(global_raw[b"alpha"]), float(global_raw[b"beta"])) if global_raw
            else self.default_priors.get(arm, (1.0, 1.0))
        )

        if not merchant_raw:
            return global_alpha, global_beta

        merchant_alpha, merchant_beta = float(merchant_raw[b"alpha"]), float(merchant_raw[b"beta"])
        merchant_observations = merchant_alpha + merchant_beta - 2.0
        blended = blend_priors(global_alpha, global_beta, merchant_alpha, merchant_beta, max(merchant_observations, 0.0))
        return blended.alpha, blended.beta

    def increment_alpha(self, merchant_id: str, context_bucket: str, arm: str, amount: float) -> None:
        if amount == 0:
            return
        m_key = self._merchant_key(merchant_id, context_bucket, arm)
        g_key = self._global_key(context_bucket, arm)
        self._ensure_materialized(m_key, arm)
        self._ensure_materialized(g_key, arm)
        self.client.hincrbyfloat(m_key, "alpha", amount)
        self.client.hincrbyfloat(g_key, "alpha", amount)

    def increment_beta(self, merchant_id: str, context_bucket: str, arm: str, amount: float) -> None:
        if amount == 0:
            return
        m_key = self._merchant_key(merchant_id, context_bucket, arm)
        g_key = self._global_key(context_bucket, arm)
        self._ensure_materialized(m_key, arm)
        self._ensure_materialized(g_key, arm)
        self.client.hincrbyfloat(m_key, "beta", amount)
        self.client.hincrbyfloat(g_key, "beta", amount)
