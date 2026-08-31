def beta_variance(alpha: float, beta: float) -> float:
    return (alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1))


def beta_confidence_level(alpha: float, beta: float) -> str:
    """Coarse, explainable confidence tiers — not a black-box score.
    Thresholds are illustrative starting points; tune against your actual
    batch data rather than treating these as fixed constants."""
    total_observations = alpha + beta
    if total_observations < 5:
        return "low"       # fewer than ~5 effective observations for this (context, arm) pair
    elif total_observations < 20:
        return "medium"
    return "high"
