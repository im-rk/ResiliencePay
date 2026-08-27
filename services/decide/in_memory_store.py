from services.decide.bandit import get_default_prior_for_context

class InMemoryArmStatsStore:
    """In-memory arm stats store with exact same interface as RedisArmStatsStore.
    Allows running batch evaluations, unit tests, and local simulations without
    requiring a running Redis server or network roundtrips."""

    def __init__(self, default_priors: dict[str, tuple[float, float]] | None = None):
        self.default_priors = default_priors or {}
        self.stats: dict[str, dict[str, float]] = {}

    def _key(self, context_bucket: str, arm: str) -> str:
        return f"bandit:{context_bucket}:{arm}"

    def _ensure_materialized(self, context_bucket: str, arm: str):
        key = self._key(context_bucket, arm)
        if key not in self.stats:
            alpha, beta = self.default_priors.get(arm, get_default_prior_for_context(context_bucket, arm))
            self.stats[key] = {"alpha": float(alpha), "beta": float(beta)}

    def get_stats(self, context_bucket: str, arm: str) -> tuple[float, float]:
        self._ensure_materialized(context_bucket, arm)
        s = self.stats[self._key(context_bucket, arm)]
        return s["alpha"], s["beta"]

    def increment_alpha(self, context_bucket: str, arm: str, amount: float) -> None:
        if amount == 0:
            return
        self._ensure_materialized(context_bucket, arm)
        self.stats[self._key(context_bucket, arm)]["alpha"] += amount

    def increment_beta(self, context_bucket: str, arm: str, amount: float) -> None:
        if amount == 0:
            return
        self._ensure_materialized(context_bucket, arm)
        self.stats[self._key(context_bucket, arm)]["beta"] += amount
