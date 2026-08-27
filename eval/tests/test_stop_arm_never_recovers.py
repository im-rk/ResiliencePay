import numpy as np
from eval.outcome_simulator import simulate_outcome

def test_stop_arm_produces_zero_recovery_probability():
    """Even with a near-certain base probability (0.99), 'stop' must NEVER recover money."""
    rng = np.random.default_rng(42)
    draft = {
        "cause_category": "insufficient_funds",
        "_ground_truth_recoverable_prob": 0.99,
        "amount": 100000,
    }
    for _ in range(150):
        outcome = simulate_outcome(draft, "stop", rng)
        assert outcome.result == "not_recovered", "stop arm should never recover"
        assert outcome.amount_recovered == 0
        assert outcome.time_to_resolution_hrs is None
