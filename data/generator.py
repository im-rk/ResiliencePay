import numpy as np
from datetime import datetime, timedelta, timezone
from packages.domain_constants.cause_categories import CauseCategoryEnum
from data.error_code_samples import sample_error_code

CAUSE_DISTRIBUTION = {
    CauseCategoryEnum.INSUFFICIENT_FUNDS.value: 0.30,
    CauseCategoryEnum.EXPIRED_CARD.value: 0.15,
    CauseCategoryEnum.OTP_FAILURE.value: 0.15,
    CauseCategoryEnum.BANK_TIMEOUT.value: 0.15,
    CauseCategoryEnum.MANDATE_INACTIVE.value: 0.10,
    CauseCategoryEnum.HARD_DECLINE.value: 0.10,
    CauseCategoryEnum.CUSTOMER_CANCELLED.value: 0.05,
}

RECOVERABLE_CEILING = {
    CauseCategoryEnum.INSUFFICIENT_FUNDS.value: 0.75,
    CauseCategoryEnum.EXPIRED_CARD.value: 0.65,
    CauseCategoryEnum.OTP_FAILURE.value: 0.85,
    CauseCategoryEnum.BANK_TIMEOUT.value: 0.80,
    CauseCategoryEnum.MANDATE_INACTIVE.value: 0.50,
    CauseCategoryEnum.HARD_DECLINE.value: 0.20,
    CauseCategoryEnum.CUSTOMER_CANCELLED.value: 0.05,
}

def sample_segment(rng: np.random.Generator) -> str:
    segments = ['new', 'returning_low_value', 'returning_high_value', 'churn_risk']
    return str(rng.choice(segments))

def sample_timestamp(rng: np.random.Generator, window_days: int = 14) -> datetime:
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    seconds_offset = rng.integers(0, window_days * 24 * 60 * 60)
    return base_time - timedelta(seconds=int(seconds_offset))

def generate_batch(seed: int, n: int, merchant_id: str = "merch_demo01") -> list[dict]:
    """Generates a batch of synthetic events for evaluation or simulation."""
    if n <= 0:
        return []

    rng = np.random.default_rng(seed)
    drafts = []
    causes = list(CAUSE_DISTRIBUTION.keys())
    probs = list(CAUSE_DISTRIBUTION.values())

    for _ in range(n):
        cause = str(rng.choice(causes, p=probs))

        if rng.random() < 0.01:
            amount = int(rng.choice([100, 100000000]))
        else:
            amount = int(rng.integers(9_900, 999_900))

        base_prob = float(RECOVERABLE_CEILING[cause] * rng.uniform(0.75, 1.0))

        drafts.append({
            "cause_category": cause,
            "event_type": str(rng.choice(["subscription_charge_failed", "payment_failed", "checkout_abandoned"])),
            "gateway_error_code": sample_error_code(cause, rng),
            "amount": amount,
            "customer_segment": sample_segment(rng),
            "retry_count_so_far": int(rng.choice([0, 0, 1, 1, 2])),
            "occurred_at": sample_timestamp(rng, window_days=14),
            "opted_out": bool(rng.random() < 0.04),
            "_ground_truth_recoverable_prob": base_prob,
        })
    return drafts
