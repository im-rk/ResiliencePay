"""Mappers — the ONLY place ORM models are translated into DTOs. Keeping
this centralized means a reviewer can audit 'what do we expose externally'
by reading one file, not by tracing every router."""
from packages.db_models.models import Event
from .dtos import EventStateDTO

def event_to_dto(event: Event) -> EventStateDTO:
    diagnosis = event.diagnoses[-1] if event.diagnoses else None
    decision = event.decisions[-1] if event.decisions else None
    action = decision.actions[-1] if decision and decision.actions else None
    outcome = action.outcomes[-1] if action and action.outcomes else None

    return EventStateDTO(
        event_id=str(event.event_id),
        episode_id=str(event.episode_id),
        cause_category=diagnosis.cause_category if diagnosis else None,
        diagnosis_confidence=float(diagnosis.confidence) if diagnosis else None,
        chosen_arm=decision.chosen_arm if decision else None,
        gate_passed=(decision.gate_checks[-1].result == "passed") if decision and decision.gate_checks else None,
        simulated=action.simulated if action else None,
        outcome_result=outcome.result if outcome else None,
        amount_recovered=outcome.amount_recovered if outcome else None,
        occurred_at=event.occurred_at,
    )
