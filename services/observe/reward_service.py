class RewardService:
    """The single source of truth for outcome -> reward mapping. Both the
    live webhook handler (this phase) and the batch evaluation harness
    (Phase 8) MUST call this exact class — never reimplement this logic
    elsewhere, even for 'just a quick eval script.'"""

    REWARD_RECOVERED = 1.0
    REWARD_NOT_RECOVERED = 0.0
    REWARD_BLOCKED_BY_POLICY = -0.1

    def compute(self, outcome) -> float:
        if outcome.result == "recovered":
            return self.REWARD_RECOVERED
        if outcome.result == "blocked_by_policy":
            return self.REWARD_BLOCKED_BY_POLICY
        if outcome.result in ("not_recovered", "pending", "failed_permanently"):
            return self.REWARD_NOT_RECOVERED
        raise ValueError(f"unrecognized outcome.result: {outcome.result!r} — "
                          f"update RewardService.compute() to handle new outcome states explicitly, "
                          f"do not let unrecognized states silently default to 0.0")
