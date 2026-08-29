from dataclasses import dataclass
from datetime import datetime

from packages.config.settings import settings
from .rules import check_cool_off, check_max_attempts, check_opt_out, check_time_window
from .persistence import record_gate_check

@dataclass(frozen=True)
class GateContext:
    decision_id: str
    customer_id: str
    episode: "Episode"

@dataclass(frozen=True)
class GateResult:
    passed: bool
    rule_triggered: str | None = None

def evaluate_gate(context: "GateContext", db_session, now: datetime | None = None) -> GateResult:
    """Pure with respect to prior gate evaluations — always re-derives its
    answer from current state. See section 2.3. Never accepts the bandit's
    sampled_score or confidence as input — see section 2.1; there is no
    parameter here for the bandit to influence."""
    now = now or datetime.utcnow()

    result = check_opt_out(context.customer_id, db_session)
    if result != "pass":
        res = GateResult(passed=False, rule_triggered=result[1])
        record_gate_check(db_session, context.decision_id, res)
        return res

    result = check_max_attempts(context.episode, settings.gate_max_attempts)
    if result != "pass":
        res = GateResult(passed=False, rule_triggered=result[1])
        record_gate_check(db_session, context.decision_id, res)
        return res

    result = check_cool_off(context.episode, settings.gate_min_cool_off_hours, now)
    if result != "pass":
        res = GateResult(passed=False, rule_triggered=result[1])
        record_gate_check(db_session, context.decision_id, res)
        return res

    result = check_time_window(now, settings.gate_allowed_hour_start, settings.gate_allowed_hour_end)
    if result != "pass":
        res = GateResult(passed=False, rule_triggered=result[1])
        record_gate_check(db_session, context.decision_id, res)
        return res

    res = GateResult(passed=True, rule_triggered=None)
    record_gate_check(db_session, context.decision_id, res)
    return res
