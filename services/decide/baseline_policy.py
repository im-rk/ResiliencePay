from services.decide.bandit import ArmChoice, BanditPolicy

class BaselinePolicy:
    """Represents 'what merchants do today': always retry immediately,
    once, no personalization, no learning. Satisfies the identical
    BanditPolicy Protocol as ThompsonSamplingBandit — this is what lets
    eval/run_batch.py inject either with zero branching at the call site."""

    def sample_arm(self, context_bucket: str) -> ArmChoice:
        return ArmChoice(
            arm="retry_immediate",
            sampled_score=1.0,
            alpha_at_decision=1.0,
            beta_at_decision=1.0
        )

    def update(self, context_bucket: str, arm: str, reward: float) -> None:
        pass  # no learning, by design — this IS the baseline's defining property

    def get_stats(self, context_bucket: str) -> dict[str, tuple[float, float]]:
        return {}
