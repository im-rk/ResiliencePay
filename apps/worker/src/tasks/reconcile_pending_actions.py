from datetime import timedelta, datetime, timezone
import structlog
from celery import shared_task
from sqlalchemy.orm import Session
from packages.db_models.database import SessionLocal
from packages.db_models.models.pending_action import PendingAction
from packages.db_models.models.dead_lettered_action import DeadLetteredAction
from packages.db_models.models.action import Action
from packages.db_models.models.decision import Decision
from services.act.razorpay_client import RazorpayClient
from packages.config.settings import settings
from services.audit.audit_log_service import AuditLogService

logger = structlog.get_logger(__name__)
STUCK_THRESHOLD = timedelta(minutes=10)

def now():
    return datetime.now(timezone.utc)

def create_action_from_reconciled_pending(db: Session, pending: PendingAction, decision: Decision | None):
    action = Action(
        decision_id=pending.decision_id,
        arm_name=decision.chosen_arm if decision else "retry_immediate",
        simulated=False,
        razorpay_ref_id=pending.razorpay_ref_id,
        status="executed",
        executed_at=now()
    )
    db.add(action)

def send_to_dead_letter_queue(db: Session, pending: PendingAction):
    db.add(DeadLetteredAction(
        pending_action_id=pending.pending_action_id,
        reason="razorpay_call_unresolvable_after_reconciliation_attempt",
        requires_manual_review=True,
    ))

@shared_task(name="reconcile_pending_actions")
def reconcile_pending_actions():
    db = SessionLocal()
    try:
        razorpay_client = RazorpayClient(settings.razorpay_key_id, settings.razorpay_key_secret)
        audit_log_service = AuditLogService(db)
        
        stuck_actions = db.query(PendingAction).filter(
            PendingAction.status == "attempting",
            PendingAction.created_at < now() - STUCK_THRESHOLD
        ).all()

        for pending in stuck_actions:
            try:
                found_payment = razorpay_client.find_payment_link_by_idempotency_key(pending.idempotency_key)
                decision = db.query(Decision).filter(Decision.decision_id == pending.decision_id).first()

                if found_payment is not None:
                    pending.status = "reconciled"
                    pending.razorpay_ref_id = found_payment.id
                    pending.resolved_at = now()
                    create_action_from_reconciled_pending(db, pending, decision)
                    if decision:
                        audit_log_service.write_note(decision, note="reconciled_after_dual_write_gap")
                else:
                    pending.status = "dead_lettered"
                    pending.resolved_at = now()
                    send_to_dead_letter_queue(db, pending)
                    if decision:
                        audit_log_service.write_note(decision, note="dead_lettered_after_dual_write_gap")
                
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error("reconciliation_failed_for_pending_action", pending_action_id=str(pending.pending_action_id), error=str(e))
                
    finally:
        db.close()
