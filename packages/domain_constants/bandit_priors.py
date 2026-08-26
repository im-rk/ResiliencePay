# Seeded from domain intuition per ML_DESIGN.md §2.6. These are STARTING
# points, not claims about real-world performance — document this clearly
# if asked. Format: {arm: (alpha, beta)}. Higher alpha relative to beta =
# more optimistic prior.
DEFAULT_PRIORS: dict[str, tuple[float, float]] = {
    "retry_immediate":       (2.0, 2.0),   # neutral — situational
    "retry_short_delay":     (2.0, 2.0),
    "retry_long_delay":      (3.0, 2.0),   # slightly favored for funds-timing cases
    "send_card_update_link": (2.0, 2.0),
    "send_nudge_hinglish":   (2.0, 3.0),   # slightly conservative until proven
    "send_nudge_english":    (2.0, 3.0),
    "escalate_human":        (1.0, 4.0),   # expensive — bandit should need real evidence to favor this
    "stop":                  (1.0, 1.0),   # neutral — always safe, no reward upside to learn
}

# Optional: per-cause-category overrides, applied at context_bucket
# construction time rather than baked into RedisArmStatsStore, so the prior
# logic stays testable independent of Redis.
CAUSE_SPECIFIC_OVERRIDES: dict[str, dict[str, tuple[float, float]]] = {
    "otp_failure": {"retry_immediate": (4.0, 1.0)},          # OTP retries recover fast, favor strongly
    "insufficient_funds": {"retry_long_delay": (4.0, 1.5)},  # payday timing intuition
    "hard_decline": {"escalate_human": (1.5, 3.0), "stop": (2.0, 1.0)},  # lean toward stopping
}

def get_prior_for(cause_category: str, arm: str) -> tuple[float, float]:
    """Helper to merge CAUSE_SPECIFIC_OVERRIDES with DEFAULT_PRIORS"""
    overrides = CAUSE_SPECIFIC_OVERRIDES.get(cause_category, {})
    return overrides.get(arm, DEFAULT_PRIORS.get(arm, (1.0, 1.0)))
