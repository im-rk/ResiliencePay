from typing import Literal
from datetime import datetime, timedelta
from packages.db_models.models.customer import OptOut
from sqlalchemy.orm import Session
from packages.db_models.models.episode import Episode

RuleResult = Literal["pass"] | tuple[Literal["blocked"], str]

def check_opt_out(customer_id, db: Session) -> RuleResult:
    if db.query(OptOut).filter(OptOut.customer_id == customer_id).first():
        return ("blocked", "customer_opted_out")
    return "pass"

def check_max_attempts(episode: Episode, max_attempts: int = 3) -> RuleResult:
    if episode.attempt_count >= max_attempts:
        return ("blocked", "max_attempts_exceeded")
    return "pass"

def check_cool_off(episode: Episode, min_gap_hours: int, now: datetime) -> RuleResult:
    if episode.last_action_at and (now - episode.last_action_at) < timedelta(hours=min_gap_hours):
        return ("blocked", "cool_off_active")
    return "pass"

def check_time_window(now: datetime, allowed_hours: tuple[int, int] = (9, 20)) -> RuleResult:
    if not (allowed_hours[0] <= now.hour < allowed_hours[1]):
        return ("blocked", "outside_communication_window")
    return "pass"
