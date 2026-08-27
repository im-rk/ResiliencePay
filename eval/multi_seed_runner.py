import numpy as np
import structlog
from eval.run_batch import run_batch
from services.decide.bandit import ThompsonSamplingBandit
from services.decide.baseline_policy import BaselinePolicy
from services.decide.in_memory_store import InMemoryArmStatsStore

logger = structlog.get_logger(__name__)


def run_multi_seed_comparison(db_session=None, seeds: list[int] | None = None, n: int = 200) -> dict:
    """Executes a multi-seed comparison between ThompsonSamplingBandit and BaselinePolicy.
    Holds all factors identical (seed, events, gate, outcome generation) except the policy.
    """
    if seeds is None:
        seeds = [42, 123, 999]

    results: dict[str, list[float]] = {"bandit": [], "baseline": []}
    run_records = []

    for seed in seeds:
        # Fresh store per seed to evaluate clean convergence
        store = InMemoryArmStatsStore()
        bandit = ThompsonSamplingBandit(store)
        baseline = BaselinePolicy()

        bandit_run = run_batch(
            db_session=db_session,
            dataset_seed=seed,
            n=n,
            policy_name="bandit",
            policy=bandit,
        )
        baseline_run = run_batch(
            db_session=db_session,
            dataset_seed=seed,
            n=n,
            policy_name="baseline",
            policy=baseline,
        )

        b_rate = float(bandit_run.metrics.recovery_rate)
        base_rate = float(baseline_run.metrics.recovery_rate)

        results["bandit"].append(b_rate)
        results["baseline"].append(base_rate)
        run_records.append({
            "seed": seed,
            "bandit_recovery_rate": b_rate,
            "baseline_recovery_rate": base_rate,
            "lift": round(b_rate - base_rate, 4),
            "bandit_amount_recovered": bandit_run.metrics.amount_recovered,
            "baseline_amount_recovered": baseline_run.metrics.amount_recovered,
        })

    bandit_mean = float(np.mean(results["bandit"]))
    baseline_mean = float(np.mean(results["baseline"]))
    lift_mean = bandit_mean - baseline_mean
    consistent = all(b > base for b, base in zip(results["bandit"], results["baseline"]))

    summary = {
        "seeds": seeds,
        "n_events_per_seed": n,
        "runs": run_records,
        "bandit_mean": round(bandit_mean, 4),
        "bandit_range": (round(min(results["bandit"]), 4), round(max(results["bandit"]), 4)),
        "baseline_mean": round(baseline_mean, 4),
        "baseline_range": (round(min(results["baseline"]), 4), round(max(results["baseline"]), 4)),
        "lift_mean": round(lift_mean, 4),
        "consistent_direction": consistent,
    }

    logger.info(
        "multi_seed_comparison_completed",
        bandit_mean=summary["bandit_mean"],
        baseline_mean=summary["baseline_mean"],
        lift_mean=summary["lift_mean"],
        consistent_direction=consistent,
    )

    return summary
