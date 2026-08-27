from eval.run_batch import run_batch
from services.decide.baseline_policy import BaselinePolicy

def test_same_params_produce_identical_metrics():
    """BaselinePolicy with same seed must yield byte-for-byte identical metrics."""
    run1 = run_batch(
        db_session=None,
        dataset_seed=42,
        n=200,
        policy_name="baseline",
        policy=BaselinePolicy(),
    )
    run2 = run_batch(
        db_session=None,
        dataset_seed=42,
        n=200,
        policy_name="baseline",
        policy=BaselinePolicy(),
    )

    assert run1.metrics.recovery_rate == run2.metrics.recovery_rate
    assert run1.metrics.amount_recovered == run2.metrics.amount_recovered
    assert run1.metrics.amount_at_risk == run2.metrics.amount_at_risk
    assert run1.metrics.exception_count == run2.metrics.exception_count
    assert run1.metrics.gate_blocked_count == run2.metrics.gate_blocked_count
