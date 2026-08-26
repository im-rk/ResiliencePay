from datetime import datetime
import uuid
from sqlalchemy.orm import Session
from packages.db_models.models.episode import Episode
from packages.db_models.models.gate_check import GateCheck
from services.gate.schemas import GateResult
from services.gate import rules

def evaluate_gate(db: Session, decision_id: uuid.UUID, episode: Episode, customer_id: uuid.UUID, arm_name: str, now: datetime) -> GateResult:
    if arm_name == "stop":
        # Always passes trivially
        result = GateResult(passed=True, reason="do_nothing_allowed", rule_name="stop_arm")
    else:
        # Evaluate in order of severity
        rule_evaluations = [
            ("opt_out", rules.check_opt_out(customer_id, db)),
            ("max_attempts", rules.check_max_attempts(episode, max_attempts=3)),
            ("cool_off", rules.check_cool_off(episode, min_gap_hours=24, now=now)),
            ("time_window", rules.check_time_window(now, allowed_hours=(9, 20))),
        ]

        passed = True
        block_reason = None
        block_rule = None

        for rule_name, rule_res in rule_evaluations:
            if isinstance(rule_res, tuple) and rule_res[0] == "blocked":
                passed = False
                block_reason = rule_res[1]
                block_rule = rule_name
                break

        if passed:
            result = GateResult(passed=True)
        else:
            result = GateResult(passed=False, reason=block_reason, rule_name=block_rule)
    
    # Every gate evaluation must write exactly one gate_checks row
    gate_check = GateCheck(
        decision_id=decision_id,
        result="pass" if result.passed else "blocked",
        rule_triggered=result.rule_name,
        checked_at=now
    )
    db.add(gate_check)
    db.commit()

    return result
