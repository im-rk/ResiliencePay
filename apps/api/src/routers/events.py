from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert
from packages.db_models.database import get_db
from packages.db_models.models import Action, Outcome, Decision, Event, Episode
from services.observe.webhook_handlers import now, hours_between
from services.observe.reward_service import RewardService
from services.audit.audit_log_service import AuditLogService

router = APIRouter()

class MarkResolvedRequest(BaseModel):
    result: str  # "recovered" | "not_recovered"

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
