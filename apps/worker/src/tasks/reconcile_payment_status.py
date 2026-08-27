import logging
import os
from datetime import timedelta
from celery import shared_task
from packages.db_models.database import SessionLocal
from packages.db_models.models import Action
from services.observe.webhook_handlers import handle_payment_captured_webhook, now

logger = logging.getLogger(__name__)

RECONCILIATION_THRESHOLD = timedelta(hours=6)

@shared_task(name="reconcile_payment_status")
def reconcile_payment_status():
    db_session = SessionLocal()
    
    # In a real app we'd inject these, but for hackathon we instantiate
    from services.act.razorpay_client import RazorpayClient
    from services.observe.reward_service import RewardService
    from services.audit.audit_log_service import AuditLogService
    
    razorpay_client = RazorpayClient(os.getenv("RAZORPAY_KEY_ID", "test"), os.getenv("RAZORPAY_KEY_SECRET", "test"))
    reward_service = RewardService()
    audit_log_service = AuditLogService(db_session)
    
    # We mock the bandit for the purpose of this task structure if it's not fully injected
    class DummyBandit:
        def update(self, *args, **kwargs):
            pass
    bandit = DummyBandit()

    older_than = now() - RECONCILIATION_THRESHOLD
    
    stale_actions = db_session.query(Action).filter(
        Action.status.in_(["scheduled", "executed"]),
        Action.executed_at < older_than,
        Action.simulated == False
    ).all()
    
    reconciled_count = 0
    for action in stale_actions:
        if action.razorpay_ref_id is None:
            continue
        try:
            status = razorpay_client.get_payment_status(action.razorpay_ref_id)
            if status.get("status") == "captured":
                payload = {"payment": {"id": action.razorpay_ref_id, "amount": status.get("amount", 0)}}
                handle_payment_captured_webhook(
                    payload=payload,
                    db_session=db_session,
                    bandit=bandit,
                    reward_service=reward_service,
                    audit_log_service=audit_log_service
                )
                reconciled_count += 1
        except Exception as e:
            logger.error("reconciliation_failed_for_action", extra={"action_id": str(action.action_id), "error": str(e)})
            
    logger.info("reconciliation_run_complete", extra={"reconciled_count": reconciled_count, "checked": len(stale_actions)})
    db_session.close()
    return reconciled_count
