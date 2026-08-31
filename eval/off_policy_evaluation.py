import numpy as np
from dataclasses import dataclass


@dataclass(frozen=True)
class OPEResult:
    estimated_value: float
    effective_sample_size: float  # low ESS = low-confidence estimate, report this honestly
    n_records: int


def baseline_policy_probability(context_bucket: str, arm: str) -> float:
    """BaselinePolicy always chooses retry_immediate deterministically."""
    return 1.0 if arm == "retry_immediate" else 0.0


def new_policy_probability(bandit, context_bucket: str, arm: str, n_samples: int = 200) -> float:
    """Estimate probability via Monte Carlo sampling from Beta distributions."""
    stats = bandit.get_stats(context_bucket)
    wins = 0
    for _ in range(n_samples):
        sampled = {a: np.random.beta(alpha, beta) for a, (alpha, beta) in stats.items()}
        if max(sampled, key=sampled.get) == arm:
            wins += 1
    return wins / n_samples


def evaluate_off_policy(historical_log: list[dict], bandit) -> OPEResult:
    """historical_log: list of {context_bucket, chosen_arm, reward} from a PAST baseline run."""
    weights = []
    weighted_rewards = []
    
    for record in historical_log:
        p_new = new_policy_probability(bandit, record["context_bucket"], record["chosen_arm"])
        p_old = baseline_policy_probability(record["context_bucket"], record["chosen_arm"])
        
        if p_old == 0:
            continue  # Avoid divide-by-zero
            
        weight = p_new / p_old
        weights.append(weight)
        weighted_rewards.append(weight * record["reward"])

    estimated_value = float(np.mean(weighted_rewards)) if weighted_rewards else 0.0
    ess = (sum(weights) ** 2) / sum(w ** 2 for w in weights) if weights and sum(weights) > 0 else 0.0

    return OPEResult(estimated_value=estimated_value, effective_sample_size=ess, n_records=len(historical_log))
