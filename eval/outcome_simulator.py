from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class SimulatedOutcome:
    result: str  # "recovered" | "not_recovered"
    amount_recovered: int  # paise
    time_to_resolution_hrs: float | None

# Hand-specified ground-truth reward structure — this table is what the
# bandit is expected to discover empirically.
ARM_MATCH_QUALITY: dict[str, dict[str, float]] = {
    "insufficient_funds": {
        "retry_immediate": 0.25, "retry_short_delay": 0.50, "retry_long_delay": 0.95,
        "send_nudge_english": 0.40, "send_nudge_hinglish": 0.45, "stop": 0.0
    },
    "expired_card": {
        "retry_immediate": 0.05, "send_card_update_link": 0.95,
        "send_nudge_english": 0.30, "send_nudge_hinglish": 0.30, "stop": 0.0
    },
    "otp_failure": {
        "retry_immediate": 0.95, "retry_short_delay": 0.60, "retry_long_delay": 0.20,
        "stop": 0.0
    },
    "bank_timeout": {
        "retry_immediate": 0.45, "retry_short_delay": 0.90, "retry_long_delay": 0.45,
        "stop": 0.0
    },
    "mandate_inactive": {
        "retry_immediate": 0.05, "send_nudge_english": 0.55, "send_nudge_hinglish": 0.60,
        "escalate_human": 0.75, "stop": 0.0
    },
    "hard_decline": {
        "retry_immediate": 0.02, "send_card_update_link": 0.20,
        "escalate_human": 0.30, "stop": 0.0
    },
    "customer_cancelled": {
        "retry_immediate": 0.0, "send_nudge_english": 0.02, "stop": 0.0
    },
}
DEFAULT_MATCH_QUALITY = 0.20


def simulate_outcome(event_draft: dict, chosen_arm: str, rng: np.random.Generator, chaos_active: bool | None = None) -> SimulatedOutcome:
    """Simulates the outcome of executing chosen_arm on event_draft.
    The 'stop' arm represents deliberate non-action and NEVER recovers money."""
    base_prob = event_draft.get("_ground_truth_recoverable_prob", 0.5)
    cause = event_draft.get("cause_category", "unknown")
    match_quality = ARM_MATCH_QUALITY.get(cause, {}).get(chosen_arm, DEFAULT_MATCH_QUALITY)

    if chaos_active is None:
        try:
            from packages.config.redis_client import redis_client
            val = redis_client.get("circuit_breaker:chaos_mode")
            chaos_active = bool(val and val in (b"1", "1"))
        except Exception:
            chaos_active = False

    if chosen_arm == "stop" or match_quality <= 0.0:
        recovered = False
    elif chaos_active and chosen_arm.startswith("retry"):
        # Gateway blackout! Upstream 5xx/timeouts cause naive retries to fail
        recovered = False
    else:
        final_prob = min(base_prob * match_quality * 1.15, 1.0)
        recovered = bool(rng.random() < final_prob)

    return SimulatedOutcome(
        result="recovered" if recovered else "not_recovered",
        amount_recovered=event_draft["amount"] if recovered else 0,
        time_to_resolution_hrs=float(rng.uniform(1.0, 72.0)) if recovered else None,
    )
