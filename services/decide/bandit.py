from typing import Protocol, Optional
import numpy as np
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)

class BanditPolicy(Protocol):
    """Structural interface shared by the real bandit and the baseline
    policy (Phase 8). Any code that depends on 'a policy' should type-hint
    against THIS, never against ThompsonSamplingBandit directly — this is
    what makes swapping policies in eval/run_batch.py a zero-branching
    operation."""

    def sample_arm(self, context_bucket: str) -> "ArmChoice": ...
    def update(self, context_bucket: str, arm: str, reward: float) -> None: ...
    def get_stats(self, context_bucket: str) -> dict[str, tuple[float, float]]: ...

@dataclass(frozen=True)
class ArmChoice:
    """Return type for sample_arm — deliberately richer than a bare string
    so the decision's explainability data travels with it, rather than
    needing a second lookup at write time."""
    arm: str
    sampled_score: float
    alpha_at_decision: float
    beta_at_decision: float

ARMS = [
    "retry_immediate", "retry_short_delay", "retry_long_delay",
    "send_card_update_link", "send_nudge_hinglish", "send_nudge_english",
    "escalate_human", "stop",
]

class ThompsonSamplingBandit:
    def __init__(self, store):
        # We accept a store object rather than tightly coupling to Redis.
        self.store = store

    def sample_arm(self, context_bucket: str) -> ArmChoice:
        best: Optional[ArmChoice] = None
        
        # Explainability snapshot for structlog
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
                    beta_at_decision=beta
                )
                
        assert best is not None  # ARMS is never empty — defensive, not reachable
        
        # Structured Logging for explainability (Prompt 7 / Section 6)
        logger.info(
            "bandit_sampled_arm",
            context_bucket=context_bucket,
            chosen_arm=best.arm,
            sampled_score=best.sampled_score,
            stats_snapshot=stats_snapshot
        )
        
        return best

    def update(self, context_bucket: str, arm: str, reward: float) -> None:
        if not (0.0 <= reward <= 1.0 or reward == -0.1):
            raise ValueError(f"reward {reward} outside valid range; validate before calling update()")
        
        success_increment = max(reward, 0.0)
        failure_increment = 1.0 - success_increment if reward >= 0 else 0.0
        
        # A -0.1 penalty (gate-blocked-but-attempted case, see ML_DESIGN.md §2.5)
        # is handled as a pure beta-side nudge without a full failure increment,
        # since it represents a POLICY violation risk, not an observed recovery failure.
        if reward == -0.1:
            self.store.increment_beta(context_bucket, arm, 0.1)
            return
            
        self.store.increment_alpha(context_bucket, arm, success_increment)
        self.store.increment_beta(context_bucket, arm, failure_increment)

    def get_stats(self, context_bucket: str) -> dict[str, tuple[float, float]]:
        return {arm: self.store.get_stats(context_bucket, arm) for arm in ARMS}
