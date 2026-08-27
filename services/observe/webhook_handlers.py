import logging
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert
from packages.db_models.models import Action, Outcome, Decision, Event, Episode

logger = logging.getLogger(__name__)

def now():
    return datetime.now(timezone.utc)

def hours_between(start, end):
    if not start or not end:
        return 0.0
    return (end - start).total_seconds() / 3600.0

def handle_payment_captured_webhook(payload: dict, db_session, bandit, reward_service, audit_log_service):
    razorpay_payment_id = payload["payment"]["id"]
    
    action = db_session.query(Action).filter(Action.razorpay_ref_id == razorpay_payment_id).first()
    
    if action is None:
        logger.warning("webhook_unknown_razorpay_ref", extra={"razorpay_payment_id": razorpay_payment_id})
        return

    decision = db_session.query(Decision).filter(Decision.decision_id == action.decision_id).first()
    event = db_session.query(Event).filter(Event.event_id == decision.event_id).first()
    
    decision.event = event
    decision.action = action
    
    outcome_result = "recovered"
    amount_recovered = payload["payment"]["amount"]
    time_to_res = hours_between(action.executed_at, now())
    
    outcome_obj = Outcome(
        action_id=action.action_id,
        result=outcome_result,
        amount_recovered=amount_recovered,
        time_to_resolution_hrs=time_to_res
    )
    reward = reward_service.compute(outcome_obj)
    
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
    else:
        logger.info("webhook_redelivery_deduped", extra={"action_id": str(action.action_id)})

def handle_subscription_charge_failed_webhook(payload: dict, db_session, bandit, reward_service, audit_log_service):
    """Mirror structure to handle_payment_captured_webhook, for failure-confirmation event."""
    razorpay_payment_id = payload["payment"]["id"]
    
    action = db_session.query(Action).filter(Action.razorpay_ref_id == razorpay_payment_id).first()
    
    if action is None:
        logger.warning("webhook_unknown_razorpay_ref", extra={"razorpay_payment_id": razorpay_payment_id})
        return

    decision = db_session.query(Decision).filter(Decision.decision_id == action.decision_id).first()
    event = db_session.query(Event).filter(Event.event_id == decision.event_id).first()
    
    decision.event = event
    decision.action = action
    
    outcome_result = "failed_permanently"
    amount_recovered = 0
    time_to_res = hours_between(action.executed_at, now())
    
    outcome_obj = Outcome(
        action_id=action.action_id,
        result=outcome_result,
        amount_recovered=amount_recovered,
        time_to_resolution_hrs=time_to_res
    )
    reward = reward_service.compute(outcome_obj)
    
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
    else:
        logger.info("webhook_redelivery_deduped", extra={"action_id": str(action.action_id)})
