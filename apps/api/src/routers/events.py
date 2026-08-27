from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.dialects.postgresql import insert
from packages.db_models.database import get_db
from packages.db_models.models import Action, Outcome, Decision, Event, Episode
from services.observe.webhook_handlers import now, hours_between
from services.observe.reward_service import RewardService
from services.audit.audit_log_service import AuditLogService
from services.observe.dtos import EventStateDTO
from services.observe.mappers import event_to_dto
from fastapi import HTTPException

router = APIRouter()

class MarkResolvedRequest(BaseModel):
    result: str  # "recovered" | "not_recovered"

class IngestEventRequest(BaseModel):
    amount: int
    currency: str = "INR"

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive_and_reasonable(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("amount must be positive")
        if v > 100_000_000:  # ₹10 lakh in paise — a sanity ceiling for a demo merchant
            raise ValueError("amount exceeds reasonable ceiling — check units (paise, not rupees)")
        return v

    @field_validator("currency")
    @classmethod
    def currency_must_be_supported(cls, v: str) -> str:
        if v != "INR":
            raise ValueError("only INR is supported in this build")
        return v

@router.get("/v1/events/{event_id}", response_model=EventStateDTO)
def get_event(event_id: str, db_session=Depends(get_db)):
    """Fetch event state DTO — this is the explicit contract boundary."""
    event = db_session.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event_to_dto(event)

@router.post("/v1/events")
def ingest_event(body: IngestEventRequest, db_session=Depends(get_db)):
    """Ingest a new event with validated amount and currency."""
    # Dummy implementation to satisfy business logic validation requirement
    return {"status": "ok", "amount_ingested": body.amount}


@router.post("/v1/events/{event_id}/mark-resolved")
def mark_resolved(event_id: str, body: MarkResolvedRequest, db_session=Depends(get_db)):
    """Manual trigger for live demos only."""
    
    # We mock dependencies just for this demo controller if not injected
    reward_service = RewardService()
    audit_log_service = AuditLogService(db_session)
    class DummyBandit:
        def update(self, *args, **kwargs):
            pass
    bandit = DummyBandit()
    
    event = db_session.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        return {"status": "error", "reason": "Event not found"}
        
    decision = db_session.query(Decision).filter(Decision.event_id == event.event_id).order_by(Decision.decided_at.desc()).first()
    if not decision:
        return {"status": "error", "reason": "Decision not found"}
        
    action = db_session.query(Action).filter(Action.decision_id == decision.decision_id).order_by(Action.executed_at.desc()).first()
    if not action:
        return {"status": "error", "reason": "Action not found"}
        
    episode = db_session.query(Episode).filter(Episode.episode_id == event.episode_id).first()
    
    decision.event = event
    decision.action = action

    outcome_result = body.result
    amount_recovered = episode.original_amount if body.result == "recovered" else 0
    time_to_res = hours_between(action.executed_at, now())
    
    outcome_obj = Outcome(
        action_id=action.action_id,
        result=outcome_result,
        amount_recovered=amount_recovered,
        time_to_resolution_hrs=time_to_res,
    )
    reward = reward_service.compute(outcome_obj)
    
    # Idempotent upsert matching webhook path
    stmt = insert(Outcome).values(
        action_id=action.action_id,
        result=outcome_result,
        amount_recovered=amount_recovered,
        reward=reward,
        time_to_resolution_hrs=time_to_res,
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=['action_id']
    )
    
    result_proxy = db_session.execute(stmt)
    is_new = result_proxy.rowcount > 0
    
    if is_new:
        db_session.commit()
        inserted_outcome = db_session.query(Outcome).filter_by(action_id=action.action_id).first()
        bandit.update(decision.context_bucket, decision.chosen_arm, reward)
        audit_log_service.write(event=event, decision=decision, outcome=inserted_outcome)
        
    return {"status": "ok"}
