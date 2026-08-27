from packages.db_models.models import AuditLog

class AuditLogService:
    """The ONLY code path permitted to write to the audit_log table.
    Called from: services/observe (this phase), the reconciliation task,
    and eval/run_batch.py (Phase 8) — never from apps/api route handlers
    directly, never from services/act."""

    def __init__(self, db_session):
        self.db_session = db_session

    def write(self, event, decision=None, gate_result=None, outcome=None):
        self.db_session.add(AuditLog(
            event_id=event.id,
            episode_id=event.episode_id,
            cause_category=event.diagnosis.cause_category if getattr(event, "diagnosis", None) else None,
            chosen_arm=decision.chosen_arm if decision else None,
            gate_result=gate_result.passed if gate_result else None,
            simulated=(decision.action.simulated if decision and getattr(decision, "action", None) else None),
            outcome_result=outcome.result if outcome else None,
            reward=outcome.reward if outcome else None,
        ))
        self.db_session.commit()

    def write_error(self, decision, code: str, reason: str):
        """Called by services/act on a permanent/exhausted-retry failure."""
        self.db_session.add(AuditLog(
            event_id=decision.event.id,
            episode_id=decision.event.episode_id,
            chosen_arm=decision.chosen_arm,
            outcome_result="failed",
            error_code=code,
            reward=None,
        ))
        self.db_session.commit()

    def write_note(self, decision, note: str):
        """For non-outcome annotations, e.g. 'nudge_template_fallback_used'."""
        self.db_session.add(AuditLog(
            event_id=decision.event.id,
            episode_id=decision.event.episode_id,
            chosen_arm=decision.chosen_arm,
            outcome_result="note",
            error_code=note, # Reusing error_code for note to maintain shape, as we didn't add a 'note' column
            reward=None,
        ))
        self.db_session.commit()
