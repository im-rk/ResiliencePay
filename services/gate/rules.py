from typing import Literal
from datetime import datetime, timedelta

RuleResult = Literal["pass"] | tuple[Literal["blocked"], str]

def check_opt_out(customer_id, db_session) -> RuleResult:
    """Checked FIRST, always — see section 2.2. A customer's explicit
    opt-out is the single most legally significant signal in this system."""
    from packages.db_models.models import OptOut
    exists = db_session.query(OptOut).filter_by(customer_id=customer_id).first() is not None
    return ("blocked", "customer_opted_out") if exists else "pass"

def check_max_attempts(episode, max_attempts: int) -> RuleResult:
    if episode.attempt_count >= max_attempts:
        return ("blocked", "max_attempts_exceeded")
    return "pass"

def check_cool_off(episode, min_cool_off_hours: int, now: datetime) -> RuleResult:
    if episode.last_action_at and (now - episode.last_action_at) < timedelta(hours=min_cool_off_hours):
        return ("blocked", "cool_off_active")
    return "pass"

def check_time_window(now: datetime, allowed_hour_start: int, allowed_hour_end: int) -> RuleResult:
    if not (allowed_hour_start <= now.hour < allowed_hour_end):
        return ("blocked", "outside_communication_window")
    return "pass"

def check_uncertainty_escalation(choice, amount: int, high_stakes_threshold_paise: int = 500_000) -> RuleResult:
    """Not a compliance rule in the legal sense — a risk-management rule."""
    if getattr(choice, 'confidence_level', 'high') == "low" and amount >= high_stakes_threshold_paise:
        return ("blocked", "escalated_low_confidence_high_stakes")
    return "pass"

# Explicit, documented order — opt-out is checked first regardless of
# performance considerations, because it's the highest-priority signal.
# See section 2.2 for the rationale.
RULE_CHAIN = [check_opt_out, check_max_attempts, check_cool_off, check_time_window, check_uncertainty_escalation]
