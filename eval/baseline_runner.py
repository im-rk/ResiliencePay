from eval.run_batch import run_batch
from services.decide.baseline_policy import BaselinePolicy
from packages.db_models.models.batch_run import BatchRun


def run_baseline_batch(db_session, dataset_seed: int = 42, n: int = 200) -> BatchRun:
    """Convenience runner for naive same-day retry baseline."""
    policy = BaselinePolicy()
    return run_batch(
        db_session=db_session,
        dataset_seed=dataset_seed,
        n=n,
        policy_name="baseline",
        policy=policy,
    )
