import eval.run_batch
from eval.run_batch import run_batch
from services.decide.baseline_policy import BaselinePolicy
from services.decide.bandit import ThompsonSamplingBandit
from services.decide.in_memory_store import InMemoryArmStatsStore

def test_baseline_and_bandit_see_identical_event_sequence(monkeypatch):
    """Proves both policies are evaluated on the exact same sequence of synthetic events."""
    captured_batches = []
    original_generate_batch = eval.run_batch.generate_batch

    def capturing_generate_batch(seed: int, n: int, merchant_id: str):
        batch = original_generate_batch(seed=seed, n=n, merchant_id=merchant_id)
        captured_batches.append([dict(e) for e in batch])
        return batch

    monkeypatch.setattr(eval.run_batch, "generate_batch", capturing_generate_batch)

    # Run baseline
    run_batch(
        db_session=None,
        dataset_seed=99,
        n=50,
        policy_name="baseline",
        policy=BaselinePolicy(),
    )
    events_seen_by_baseline = captured_batches[-1]

    # Run bandit
    run_batch(
        db_session=None,
        dataset_seed=99,
        n=50,
        policy_name="bandit",
        policy=ThompsonSamplingBandit(InMemoryArmStatsStore()),
    )
    events_seen_by_bandit = captured_batches[-1]

    assert events_seen_by_baseline == events_seen_by_bandit, (
        "Baseline and bandit runs must process the EXACT same event sequence for a fair comparison"
    )
