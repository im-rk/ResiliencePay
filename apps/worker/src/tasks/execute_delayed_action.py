import logging
from celery import shared_task
from packages.db_models.database import SessionLocal
from packages.db_models.models.action import Action
# In a real app we'd have a proper dependency injection mechanism here.
# For the hackathon, we can wire up simple instances.

logger = logging.getLogger(__name__)

# Fake placeholders for the required imports from other phases:
def load_decision(decision_id, db):
    # Try to load it from the DB in a real app, here we assume it exists in some mock context or Phase 7 DB
    pass

def build_context(event, chosen_arm, now):
    pass

def evaluate_gate(fresh_context):
    pass

@shared_task(name="execute_delayed_action", bind=True, max_retries=3, default_retry_delay=60)
def execute_delayed_action_task(self, decision_id: str):
    db = SessionLocal()
    try:
        decision = load_decision(decision_id, db)
        if decision is None:
            logger.error("delayed_action_decision_missing", extra={"decision_id": decision_id})
            return  # nothing to do — do not retry a task for a decision that no longer exists

        # Gate re-check at EXECUTION time, not scheduling time
        from services.act.service import now
        fresh_context = build_context(decision.event, decision.chosen_arm, now=now())
        gate_result = evaluate_gate(fresh_context)

        if gate_result.passed:
            # We would normally import and inject real clients here
            # execute_action(decision, gate_result, razorpay_client, nudge_generator, audit_log_service, db)
            pass
        else:
            action = Action(
                decision_id=decision.decision_id, 
                arm_name=decision.chosen_arm,
                simulated=False, 
                status="blocked_at_execution",
                executed_at=now()
            )
            db.add(action)
            db.commit()
            
            # audit_log_service.write(event=decision.event, decision=decision, gate_result=gate_result)
    finally:
        db.close()
