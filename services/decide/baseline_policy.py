from services.decide.bandit import ArmChoice

class BaselinePolicy:
    """No-learning policy — always retries immediately, once. Satisfies the
    same BanditPolicy Protocol so eval/run_batch.py can inject either policy
    with zero branching. Deliberately trivial: it represents 'what merchants
    do today,' not a strawman."""

    def sample_arm(self, context_bucket: str) -> ArmChoice:
        return ArmChoice(
            arm="retry_immediate", 
            sampled_score=1.0,
            alpha_at_decision=1.0, 
            beta_at_decision=1.0
        )

    def update(self, context_bucket: str, arm: str, reward: float) -> None:
        pass  # no learning, by design

    def get_stats(self, context_bucket: str) -> dict[str, tuple[float, float]]:
        return {}
