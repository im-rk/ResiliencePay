from typing import Protocol, Optional
import numpy as np
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)

class BanditPolicy(Protocol):
    """Structural interface shared by the real bandit and the baseline policy."""
    def sample_arm(self, context_bucket: str) -> "ArmChoice": ...
    def update(self, context_bucket: str, arm: str, reward: float) -> None: ...
    def get_stats(self, context_bucket: str) -> dict[str, tuple[float, float]]: ...

@dataclass(frozen=True)
class ArmChoice:
    arm: str
    sampled_score: float
    alpha_at_decision: float
    beta_at_decision: float

ARMS = [
    "retry_immediate", "retry_short_delay", "retry_long_delay",
    "send_card_update_link", "send_nudge_hinglish", "send_nudge_english",
    "escalate_human", "stop",
]

# Informed priors per (cause_category, arm) as specified in ML_DESIGN.md §2.6
INFORMED_PRIORS: dict[str, dict[str, tuple[float, float]]] = {
    "insufficient_funds": {
        "retry_long_delay": (3.5, 1.0),
        "retry_short_delay": (2.0, 2.0),
        "retry_immediate": (1.0, 3.5),
        "send_nudge_english": (2.0, 2.0),
        "send_nudge_hinglish": (2.0, 2.0),
        "stop": (1.0, 3.0),
    },
    "expired_card": {
        "send_card_update_link": (4.0, 1.0),
        "retry_immediate": (1.0, 5.0),
        "send_nudge_english": (2.0, 2.0),
        "send_nudge_hinglish": (2.0, 2.0),
        "stop": (1.0, 3.0),
    },
    "otp_failure": {
        "retry_immediate": (4.0, 1.0),
        "retry_short_delay": (2.5, 1.5),
        "retry_long_delay": (1.0, 3.5),
        "stop": (1.0, 3.0),
    },
    "bank_timeout": {
        "retry_short_delay": (4.0, 1.0),
        "retry_immediate": (2.0, 2.0),
        "retry_long_delay": (2.0, 2.0),
        "stop": (1.0, 3.0),
    },
    "mandate_inactive": {
        "escalate_human": (3.5, 1.0),
        "send_nudge_english": (2.5, 1.5),
        "send_nudge_hinglish": (2.5, 1.5),
        "retry_immediate": (1.0, 4.0),
        "stop": (1.0, 3.0),
    },
    "hard_decline": {
        "stop": (3.5, 1.0),
        "escalate_human": (2.0, 2.0),
        "retry_immediate": (1.0, 5.0),
    },
    "customer_cancelled": {
        "stop": (4.0, 1.0),
        "retry_immediate": (1.0, 5.0),
    },
}


def get_default_prior_for_context(context_bucket: str, arm: str) -> tuple[float, float]:
    cause = context_bucket.split("|")[0] if "|" in context_bucket else context_bucket
    if cause in INFORMED_PRIORS and arm in INFORMED_PRIORS[cause]:
        return INFORMED_PRIORS[cause][arm]
    return (1.0, 2.0)


class ThompsonSamplingBandit:
    def __init__(self, store):
        self.store = store

    def sample_arm(self, context_bucket: str) -> ArmChoice:
        best: Optional[ArmChoice] = None
        stats_snapshot = {}

        for arm in ARMS:
            alpha, beta = self.store.get_stats(context_bucket, arm)
            stats_snapshot[arm] = (alpha, beta)
            score = float(np.random.beta(alpha, beta))
            if best is None or score > best.sampled_score:
                best = ArmChoice(
                    arm=arm,
                    sampled_score=score,
                    alpha_at_decision=alpha,
                    beta_at_decision=beta,
                )

        assert best is not None

        logger.info(
            "bandit_sampled_arm",
            context_bucket=context_bucket,
            chosen_arm=best.arm,
            sampled_score=best.sampled_score,
            stats_snapshot=stats_snapshot,
        )

        return best

    def update(self, context_bucket: str, arm: str, reward: float) -> None:
        if not (0.0 <= reward <= 1.0 or reward == -0.1):
            raise ValueError(f"reward {reward} outside valid range; validate before calling update()")

        success_increment = max(reward, 0.0)
        failure_increment = 1.0 - success_increment if reward >= 0 else 0.0

        if reward == -0.1:
            self.store.increment_beta(context_bucket, arm, 0.1)
            return

        self.store.increment_alpha(context_bucket, arm, success_increment)
        self.store.increment_beta(context_bucket, arm, failure_increment)

    def get_stats(self, context_bucket: str) -> dict[str, tuple[float, float]]:
        return {arm: self.store.get_stats(context_bucket, arm) for arm in ARMS}
