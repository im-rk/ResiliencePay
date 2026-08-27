import copy
import uuid
from datetime import datetime, timezone
import numpy as np
import structlog

from data.generator import generate_batch
from packages.db_models.models.batch_run import BatchRun, BatchRunMetrics
from packages.domain_constants.cause_categories import CauseCategoryEnum
from services.audit.audit_log_service import AuditLogService
from services.decide.bandit import BanditPolicy
from services.decide.context import context_bucket_for
from services.diagnose.rules import RULES
from services.diagnose.schemas import DiagnosisResult
from services.gate.schemas import GateResult
from services.observe.reward_service import RewardService
from eval.outcome_simulator import simulate_outcome

logger = structlog.get_logger(__name__)


def diagnose_from_draft(draft: dict) -> DiagnosisResult:
    """Thin adapter converting a synthetic event draft into a DiagnosisResult."""
    error_code = draft.get("gateway_error_code")
    if error_code and error_code in RULES:
        return DiagnosisResult(
            cause_category=RULES[error_code],
            confidence=1.0,
            method="rule_based",
        )
    cause = draft.get("cause_category", "unknown")
    try:
        cause_enum = CauseCategoryEnum(cause)
    except ValueError:
        cause_enum = CauseCategoryEnum.UNKNOWN

    return DiagnosisResult(
        cause_category=cause_enum,
        confidence=0.85,
        method="rule_based",
    )


def context_bucket_for_draft(draft: dict, diagnosis: DiagnosisResult) -> str:
    """Constructs the context bucket string for a draft event."""
    class DraftWrapper:
        def __init__(self, d):
            self.amount = d.get("amount", 100000)
            self.customer_segment = d.get("customer_segment", "new")
            self.retry_count_so_far = d.get("retry_count_so_far", 0)

    return context_bucket_for(DraftWrapper(draft), diagnosis)


def evaluate_gate_for_draft(draft: dict, chosen_arm: str) -> GateResult:
    """Evaluates compliance gate rules for a synthetic event draft."""
    if chosen_arm == "stop":
        return GateResult(passed=True, reason="do_nothing_allowed", rule_name="stop_arm")
    if draft.get("opted_out", False):
        return GateResult(passed=False, reason="customer_opted_out", rule_name="opt_out")
    if draft.get("retry_count_so_far", 0) >= 3:
        return GateResult(passed=False, reason="max_attempts_exceeded", rule_name="max_attempts")
    return GateResult(passed=True)


def run_batch(
    db_session,
    dataset_seed: int,
    n: int,
    policy_name: str,
    policy: BanditPolicy,
    merchant_id: str | None = None,
) -> BatchRun:
    """Runs a controlled batch evaluation over synthetic events."""
    if n < 150:
        logger.warning(
            "batch_size_below_recommended",
            n=n,
            min_recommended=150,
            detail="Statistical power may be low for n < 150",
        )

    run_id = uuid.uuid4()
    dataset_ref = f"seed={dataset_seed},n={n}"
    start_time = datetime.now(timezone.utc)

    run = BatchRun(
        run_id=run_id,
        policy=policy_name,
        dataset_ref=dataset_ref,
        random_seed=dataset_seed,
        started_at=start_time,
    )

    if db_session:
        db_session.add(run)
        db_session.flush()

    reward_service = RewardService()
    audit_log_service = AuditLogService(db_session) if db_session else None
    outcome_rng = np.random.default_rng(dataset_seed + 1)

    raw_drafts = generate_batch(seed=dataset_seed, n=n, merchant_id=merchant_id or "merch_demo01")

    exception_count = 0
    gate_blocked_count = 0
    amount_recovered_total = 0
    amount_at_risk_total = 0
    recovered_count = 0
    resolution_times = []

    for raw in raw_drafts:
        draft = copy.deepcopy(raw)
        draft["event_id"] = uuid.uuid4()
        draft["episode_id"] = uuid.uuid4()

        amount_at_risk_total += draft["amount"]
        diagnosis = diagnose_from_draft(draft)
        context_bucket = context_bucket_for_draft(draft, diagnosis)

        choice = policy.sample_arm(context_bucket)
        gate_result = evaluate_gate_for_draft(draft, choice.arm)

        if gate_result.passed:
            sim_outcome = simulate_outcome(draft, choice.arm, outcome_rng)
            reward = reward_service.compute(sim_outcome)
            policy.update(context_bucket, choice.arm, reward)
            if sim_outcome.result == "recovered":
                recovered_count += 1
                amount_recovered_total += sim_outcome.amount_recovered
                if sim_outcome.time_to_resolution_hrs is not None:
                    resolution_times.append(sim_outcome.time_to_resolution_hrs)
        else:
            gate_blocked_count += 1
            reward = reward_service.REWARD_BLOCKED_BY_POLICY
            policy.update(context_bucket, choice.arm, reward)
            sim_outcome = None

        if sim_outcome is None or sim_outcome.result == "not_recovered":
            exception_count += 1

        if audit_log_service:
            audit_log_service.write_batch(
                event_draft=draft,
                choice=choice,
                gate_result=gate_result,
                outcome=sim_outcome,
                reward=reward,
            )

    recovery_rate = (recovered_count / n) if n > 0 else 0.0
    avg_time = (sum(resolution_times) / len(resolution_times)) if resolution_times else None

    run.finished_at = datetime.now(timezone.utc)

    metrics = BatchRunMetrics(
        run_id=run.run_id,
        n_events=n,
        recovery_rate=round(recovery_rate, 4),
        amount_recovered=amount_recovered_total,
        amount_at_risk=amount_at_risk_total,
        avg_time_to_recovery_hrs=round(avg_time, 2) if avg_time is not None else None,
        exception_count=exception_count,
        gate_blocked_count=gate_blocked_count,
    )

    run.metrics = metrics

    if db_session:
        db_session.add(metrics)
        db_session.commit()

    logger.info(
        "batch_run_completed",
        run_id=str(run.run_id),
        policy=policy_name,
        n_events=n,
        recovery_rate=recovery_rate,
        amount_recovered=amount_recovered_total,
        amount_at_risk=amount_at_risk_total,
        exception_count=exception_count,
        gate_blocked_count=gate_blocked_count,
    )

    return run
