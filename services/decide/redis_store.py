import redis

class RedisArmStatsStore:
    def __init__(self, client: redis.Redis, default_priors: dict[str, tuple[float, float]]):
        self.client = client
        self.default_priors = default_priors  # {arm: (alpha, beta)}

    def _key(self, context_bucket: str, arm: str) -> str:
        return f"bandit:{context_bucket}:{arm}"

    def _ensure_materialized(self, context_bucket: str, arm: str):
        key = self._key(context_bucket, arm)
        alpha, beta = self.default_priors.get(arm, (1.0, 1.0))
        # hsetnx is atomic: only sets the field if it doesn't already exist.
        # This prevents a race where multiple threads overwrite each other's increments
        # with the base prior.
        self.client.hsetnx(key, "alpha", alpha)
        self.client.hsetnx(key, "beta", beta)

    def get_stats(self, context_bucket: str, arm: str) -> tuple[float, float]:
        self._ensure_materialized(context_bucket, arm)
        key = self._key(context_bucket, arm)
        raw = self.client.hgetall(key)
        return float(raw[b"alpha"]), float(raw[b"beta"])

    def increment_alpha(self, context_bucket: str, arm: str, amount: float) -> None:
        if amount == 0:
            return
        self._ensure_materialized(context_bucket, arm)
        self.client.hincrbyfloat(self._key(context_bucket, arm), "alpha", amount)

    def increment_beta(self, context_bucket: str, arm: str, amount: float) -> None:
        if amount == 0:
            return
        self._ensure_materialized(context_bucket, arm)
        self.client.hincrbyfloat(self._key(context_bucket, arm), "beta", amount)
