from dataclasses import dataclass

@dataclass(frozen=True)
class BlendedPrior:
    alpha: float
    beta: float
    global_weight: float


def blend_priors(
    global_alpha: float, global_beta: float,
    merchant_alpha: float, merchant_beta: float,
    merchant_observation_count: float,
    full_trust_threshold: float = 30.0,
) -> BlendedPrior:
    """Simple, explainable linear blending for partial pooling."""
    global_weight = max(0.0, 1.0 - (merchant_observation_count / full_trust_threshold))
    merchant_weight = 1.0 - global_weight

    blended_alpha = global_weight * global_alpha + merchant_weight * merchant_alpha
    blended_beta = global_weight * global_beta + merchant_weight * merchant_beta

    return BlendedPrior(alpha=blended_alpha, beta=blended_beta, global_weight=global_weight)
