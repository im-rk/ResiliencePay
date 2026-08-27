from packages.db_models.models import AuditLog
import structlog

logger = structlog.get_logger(__name__)


class AuditLogService:
    """The ONLY code path permitted to write to the audit_log table.
    Called from: services/observe (Phase 7), the reconciliation task,
    and eval/run_batch.py (Phase 8) — never from apps/api route handlers
    directly, never from services/act."""

    def __init__(self, db_session):
        self.db_session = db_session

    def write(self, event, decision=None, gate_result=None, outcome=None):
        """Write an audit row from ORM objects (live pipeline path)."""
        event_id = getattr(event, "event_id", None) or getattr(event, "id", None)
        episode_id = getattr(event, "episode_id", None)
        cause_category = None
        if hasattr(event, "diagnosis") and event.diagnosis:
            cause_category = event.diagnosis.cause_category
        elif hasattr(event, "diagnoses") and event.diagnoses:
            cause_category = event.diagnoses[-1].cause_category

        self.db_session.add(AuditLog(
            event_id=event_id,
            episode_id=episode_id,
            cause_category=cause_category,
            chosen_arm=decision.chosen_arm if decision else None,
            gate_result="passed" if (gate_result and gate_result.passed) else ("blocked" if gate_result else None),
            simulated=(decision.action.simulated if decision and getattr(decision, "action", None) else None),
            outcome_result=outcome.result if outcome else None,
            reward=getattr(outcome, "reward", None),
        ))
        self.db_session.commit()

    def write_batch(self, event_draft: dict, choice=None, gate_result=None, outcome=None, reward: float | None = None):
        """Write an audit row from dicts/dataclasses (batch evaluation path)."""
        outcome_res = getattr(outcome, "result", None) if outcome else None
        reward_val = reward if reward is not None else getattr(outcome, "reward", None)

        self.db_session.add(AuditLog(
            event_id=event_draft.get("event_id"),
            episode_id=event_draft.get("episode_id"),
            cause_category=event_draft.get("cause_category"),
            chosen_arm=getattr(choice, "arm", None) if choice else None,
            gate_result="passed" if (gate_result and gate_result.passed) else ("blocked" if gate_result else None),
            simulated=True,
            outcome_result=outcome_res,
            reward=reward_val,
        ))

    def write_error(self, decision, code: str, reason: str):
        """Called by services/act on a permanent/exhausted-retry failure."""
        event_id = getattr(decision, "event_id", None)
        episode_id = None
        if hasattr(decision, "event") and decision.event:
            event_id = decision.event.event_id
            episode_id = decision.event.episode_id

        self.db_session.add(AuditLog(
            event_id=event_id,
            episode_id=episode_id,
            chosen_arm=decision.chosen_arm,
            outcome_result="failed",
            error_code=code,
            reward=None,
        ))
        self.db_session.commit()

    def write_note(self, decision, note: str):
        """For non-outcome annotations, e.g. 'nudge_template_fallback_used'."""
        event_id = getattr(decision, "event_id", None)
        episode_id = None
        if hasattr(decision, "event") and decision.event:
            event_id = decision.event.event_id
            episode_id = decision.event.episode_id

        self.db_session.add(AuditLog(
            event_id=event_id,
            episode_id=episode_id,
            chosen_arm=decision.chosen_arm,
            outcome_result="note",
            error_code=note,
            reward=None,
        ))
        self.db_session.commit()
