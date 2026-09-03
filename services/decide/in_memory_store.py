
class InMemoryArmStatsStore:
    """In-memory arm stats store with exact same interface as RedisArmStatsStore.
    Allows running batch evaluations, unit tests, and local simulations without
    requiring a running Redis server or network roundtrips."""

    def __init__(self, default_priors: dict[str, tuple[float, float]] | None = None):
        self.default_priors = default_priors or {}
        self.alphas: dict[str, float] = {}
        self.betas: dict[str, float] = {}

    def _merchant_key(self, merchant_id: str, context_bucket: str, arm: str) -> str:
        return f"{merchant_id}:{context_bucket}:{arm}"

    def _ensure_materialized(self, merchant_id: str, context_bucket: str, arm: str):
        key = self._merchant_key(merchant_id, context_bucket, arm)
        if key not in self.alphas:
            alpha, beta = self.default_priors.get(arm, (1.0, 1.0))
            self.alphas[key] = alpha
            self.betas[key] = beta

    def get_stats(self, merchant_id: str, context_bucket: str, arm: str) -> tuple[float, float]:
        self._ensure_materialized(merchant_id, context_bucket, arm)
        key = self._merchant_key(merchant_id, context_bucket, arm)
        return self.alphas[key], self.betas[key]

    def increment_alpha(self, merchant_id: str, context_bucket: str, arm: str, amount: float) -> None:
        self._ensure_materialized(merchant_id, context_bucket, arm)
        self.alphas[self._merchant_key(merchant_id, context_bucket, arm)] += amount

    def increment_beta(self, merchant_id: str, context_bucket: str, arm: str, amount: float) -> None:
        self._ensure_materialized(merchant_id, context_bucket, arm)
        self.betas[self._merchant_key(merchant_id, context_bucket, arm)] += amount
