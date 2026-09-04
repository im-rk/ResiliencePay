from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from apps.api.src.dependencies import get_db_session
from eval.run_batch import run_batch
from services.decide.bandit import ThompsonSamplingBandit
from services.decide.baseline_policy import BaselinePolicy
from services.decide.in_memory_store import InMemoryArmStatsStore

router = APIRouter()


class RunBatchRequest(BaseModel):
    n_events: int = Field(default=200, ge=1, le=1000)
    policy: str = Field(default="bandit", pattern="^(bandit|baseline)$")
    random_seed: int = Field(default=42)
    merchant_id: str = "merch_demo01"


@router.post("/pipeline/run-batch")
def trigger_batch_run(body: RunBatchRequest, db_session=Depends(get_db_session)):
    """Triggers an offline evaluation batch run across synthetic events."""
    if body.policy == "baseline":
        policy_obj = BaselinePolicy()
    else:
        try:
            from packages.config.redis_client import redis_client
            redis_client.ping()
            from services.decide.redis_store import RedisArmStatsStore
            from services.decide.bandit import ARMS
            default_priors = {arm: (1.0, 2.0) for arm in ARMS}
            store = RedisArmStatsStore(redis_client, default_priors)
            policy_obj = ThompsonSamplingBandit(store)
        except Exception:
            policy_obj = ThompsonSamplingBandit(InMemoryArmStatsStore())

    run = run_batch(
        db_session=db_session,
        dataset_seed=body.random_seed,
        n=body.n_events,
        policy_name=body.policy,
        policy=policy_obj,
        merchant_id=body.merchant_id,
    )

    return {
        "run_id": str(run.run_id),
        "policy": run.policy,
        "n_events": run.metrics.n_events,
        "recovery_rate": float(run.metrics.recovery_rate),
        "amount_recovered": run.metrics.amount_recovered,
        "amount_at_risk": run.metrics.amount_at_risk,
        "exceptions": run.metrics.exception_count,
        "gate_blocked": run.metrics.gate_blocked_count,
    }
