import copy
import uuid
from datetime import datetime, timezone
import numpy as np
import structlog

from data.generator import generate_batch
from packages.db_models.models.batch_run import BatchRun, BatchRunMetrics
from packages.db_models.models import (
    Merchant, Customer, Episode, Event, Diagnosis, Decision, GateCheck,
    Action, Outcome, Arm, CauseCategory,
)
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


def evaluate_gate_for_draft(draft: dict, chosen_arm: str, force_opt_out: bool = False) -> GateResult:
    """Evaluates compliance gate rules for a synthetic event draft."""
    if chosen_arm == "stop":
        return GateResult(passed=True, reason="do_nothing_allowed", rule_name="stop_arm")
    
    is_opted_out = draft.get("opted_out", False) or force_opt_out

    if is_opted_out:
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
        merchant_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"resiliencepay:merchant:{merchant_id or 'merch_demo01'}")
        merchant = db_session.query(Merchant).filter_by(merchant_id=merchant_uuid).first()
        if merchant is None:
            merchant = Merchant(
                merchant_id=merchant_uuid,
                name=merchant_id or "merch_demo01",
                razorpay_key_id="test",
                vertical="general",
                created_at=start_time,
            )
            db_session.add(merchant)
        for cause_name in CauseCategoryEnum:
            if not db_session.query(CauseCategory).filter_by(cause_category=cause_name.value).first():
                db_session.add(CauseCategory(
                    cause_category=cause_name.value,
                    description=cause_name.value.replace("_", " "),
                    typical_recoverable=True,
                ))
        for arm_name in policy.get_stats("seed", "seed"):
            if not db_session.query(Arm).filter_by(arm_name=arm_name).first():
                db_session.add(Arm(arm_name=arm_name, description=arm_name.replace("_", " "), is_real_action=arm_name.startswith("retry")))
        db_session.flush()

    reward_service = RewardService()
    from packages.config.redis_client import redis_client
    audit_log_service = AuditLogService(db_session, None) if db_session else None
    outcome_rng = np.random.default_rng(dataset_seed + 1)

    raw_drafts = generate_batch(seed=dataset_seed, n=n, merchant_id=merchant_id or "merch_demo01")

    force_opt_out = False
    chaos_active = False
    try:
        opt_flag = redis_client.get("simulation:force_opt_out")
        if opt_flag and opt_flag in (b"1", "1"):
            force_opt_out = True
        chaos_val = redis_client.get("circuit_breaker:chaos_mode")
        if chaos_val and chaos_val in (b"1", "1"):
            chaos_active = True
    except Exception:
        pass

    exception_count = 0
    gate_blocked_count = 0
    amount_recovered_total = 0
    amount_at_risk_total = 0
    recovered_count = 0
    resolution_times = []

    batch_customers = []
    batch_episodes = []
    batch_events = []
    batch_decisions = []
    batch_diagnoses = []
    batch_gate_checks = []
    batch_actions = []
    batch_outcomes = []

    for raw in raw_drafts:
        draft = copy.deepcopy(raw)
        draft["event_id"] = uuid.uuid4()
        draft["episode_id"] = uuid.uuid4()

        amount_at_risk_total += draft["amount"]
        diagnosis = diagnose_from_draft(draft)
        context_bucket = context_bucket_for_draft(draft, diagnosis)

        choice = policy.sample_arm(merchant_id or "merch_demo01", context_bucket)
        gate_result = evaluate_gate_for_draft(draft, choice.arm, force_opt_out=force_opt_out)

        if db_session:
            customer_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"resiliencepay:customer:{draft['event_id']}")
            customer = Customer(
                customer_id=customer_uuid,
                merchant_id=merchant_uuid,
                external_ref=str(customer_uuid),
                segment=draft.get("customer_segment", "new"),
                locale="en-IN",
                created_at=draft["occurred_at"],
            )

            episode = Episode(
                episode_id=draft["episode_id"],
                merchant_id=merchant_uuid,
                customer_id=customer_uuid,
                episode_type=draft["event_type"],
                original_amount=draft["amount"],
                currency="INR",
                opened_at=draft["occurred_at"],
            )

            event = Event(
                event_id=draft["event_id"],
                episode_id=episode.episode_id,
                event_type=draft["event_type"],
                gateway_error_code=draft.get("gateway_error_code"),
                retry_count_so_far=draft.get("retry_count_so_far", 0),
                occurred_at=draft["occurred_at"],
                raw_payload={
                    **draft,
                    "event_id": str(draft["event_id"]),
                    "episode_id": str(draft["episode_id"]),
                    "occurred_at": draft["occurred_at"].isoformat(),
                },
            )

            decision = Decision(
                decision_id=uuid.uuid4(),
                event_id=event.event_id,
                chosen_arm=choice.arm,
                context_bucket=context_bucket,
                sampled_score=choice.sampled_score,
                alpha_at_decision=choice.alpha_at_decision,
                beta_at_decision=choice.beta_at_decision,
                decided_at=draft["occurred_at"],
            )
            
            action_id = uuid.uuid4()
            action = Action(
                action_id=action_id,
                decision_id=decision.decision_id,
                arm_name=choice.arm,
                simulated=True,
                status="executed" if gate_result.passed else "blocked",
                executed_at=draft["occurred_at"],
            )

            batch_customers.append(customer)
            batch_episodes.append(episode)
            batch_events.append(event)
            batch_decisions.append(decision)
            batch_diagnoses.append(Diagnosis(
                event_id=event.event_id,
                cause_category=diagnosis.cause_category.value,
                confidence=diagnosis.confidence,
                method=diagnosis.method,
                created_at=draft["occurred_at"],
            ))
            batch_gate_checks.append(GateCheck(
                decision_id=decision.decision_id,
                result="passed" if gate_result.passed else "blocked",
                rule_triggered=gate_result.rule_name,
                checked_at=draft["occurred_at"],
            ))
            batch_actions.append(action)

        if gate_result.passed:
            sim_outcome = simulate_outcome(draft, choice.arm, outcome_rng, chaos_active=chaos_active)
            reward = reward_service.compute(sim_outcome)
            policy.update(merchant_id or "merch_demo01", context_bucket, choice.arm, reward)
            if sim_outcome.result == "recovered":
                recovered_count += 1
                amount_recovered_total += sim_outcome.amount_recovered
                if sim_outcome.time_to_resolution_hrs is not None:
                    resolution_times.append(sim_outcome.time_to_resolution_hrs)
        else:
            gate_blocked_count += 1
            reward = reward_service.REWARD_BLOCKED_BY_POLICY
            policy.update(merchant_id or "merch_demo01", context_bucket, choice.arm, reward)
            sim_outcome = None

        if db_session:
            action.status = "executed" if gate_result.passed else "blocked"
            if sim_outcome is not None:
                batch_outcomes.append(Outcome(
                    action_id=action_id,
                    result=sim_outcome.result,
                    amount_recovered=sim_outcome.amount_recovered,
                    reward=reward,
                    time_to_resolution_hrs=sim_outcome.time_to_resolution_hrs,
                    observed_at=draft["occurred_at"],
                ))

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

    if db_session:
        db_session.add_all(batch_customers)
        db_session.add_all(batch_episodes)
        db_session.add_all(batch_events)
        db_session.flush()

        db_session.add_all(batch_decisions)
        db_session.flush()

        db_session.add_all(batch_diagnoses)
        db_session.add_all(batch_gate_checks)
        db_session.add_all(batch_actions)
        db_session.flush()

        if batch_outcomes:
            db_session.add_all(batch_outcomes)
            db_session.flush()

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

if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
    from packages.db_models.database import get_db
    from services.decide.bandit import ThompsonSamplingBandit
    from services.decide.redis_store import RedisArmStatsStore
    from packages.config.redis_client import redis_client

    db_gen = get_db()
    db = next(db_gen)
    
    from services.decide.bandit import ARMS
    default_priors = {arm: (1.0, 2.0) for arm in ARMS}
    store = RedisArmStatsStore(redis_client, default_priors)
    bandit = ThompsonSamplingBandit(store)
    
    print("Starting batch simulation...")
    run_batch(db, 42, 300, "ThompsonSampling", bandit)
    print("Batch simulation completed.")
