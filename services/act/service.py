from datetime import timedelta, datetime, timezone
from packages.db_models.models.action import Action
from packages.db_models.models.pending_action import PendingAction
from services.act.razorpay_client import RazorpayPermanentError, RazorpayTransientError

REAL_MONEY_ARMS = {"retry_immediate"}
DELAYED_ARMS = {"retry_short_delay", "retry_long_delay"}
NUDGE_ARMS = {"send_card_update_link", "send_nudge_hinglish", "send_nudge_english"}
NO_OP_ARMS = {"escalate_human", "stop"}

ARM_DELAYS = {
    "retry_short_delay": timedelta(hours=4),
    "retry_long_delay": timedelta(days=3),
}

def now():
    return datetime.now(timezone.utc)

def derive_bank_segment(decision) -> str:
    # Use payment_method if available (e.g., 'card_HDFC' -> 'HDFC'), otherwise use gateway error code
    event = getattr(decision, "event", None)
    if not event:
        return "default"
        
    payment_method = getattr(event, "payment_method", None)
    if payment_method and "_" in payment_method:
        return payment_method.split("_")[-1]
        
    error_code = getattr(event, "gateway_error_code", None)
    if error_code:
        return error_code
        
    return "default"

def execute_action(decision, gate_result, razorpay_client, nudge_generator, audit_log_service, db, circuit_breaker=None, schedule_delayed_action=None) -> Action:
    assert getattr(gate_result, "passed", False), "execute_action must never be called on a blocked decision"
    
    idempotency_key = f"action:{decision.decision_id}"
    
    existing_action = db.query(Action).filter(Action.decision_id == decision.decision_id).first()
    if existing_action and existing_action.status in ("executed", "failed", "scheduled", "blocked_at_execution"):
        return existing_action

    import structlog
    logger = structlog.get_logger(__name__)
    log_context = {
        "decision_id": str(decision.decision_id),
        "chosen_arm": decision.chosen_arm
    }

    action = None

    if decision.chosen_arm in REAL_MONEY_ARMS:
        segment = derive_bank_segment(decision)
        if circuit_breaker and not circuit_breaker.should_allow_attempt(segment):
            eta = now() + timedelta(minutes=45)
            if schedule_delayed_action:
                schedule_delayed_action(str(decision.decision_id), eta)
                
            action = Action(
                decision_id=decision.decision_id, 
                arm_name=decision.chosen_arm,
                simulated=False, 
                scheduled_for=eta,
                status="deferred_circuit_open",
                executed_at=now()
            )
            audit_log_service.write_note(decision, note=f"circuit_open_for_segment:{segment}")
            logger.info("action_deferred", **log_context, simulated=False, status="deferred_circuit_open", segment=segment, eta=eta.isoformat())
        else:
            try:
                # Step 1 — durable intent record, committed BEFORE the external call.
                pending = PendingAction(
                    decision_id=decision.decision_id,
                    idempotency_key=idempotency_key, 
                    status="attempting"
                )
                db.add(pending)
                db.commit()  # deliberately a separate, immediate commit

                # Assuming decision.episode is available or decision.event.episode
                episode = getattr(decision, "episode", None) or getattr(decision.event, "episode", decision.event)
                
                result = razorpay_client.create_retry_payment_link(episode, idempotency_key)
                
                pending.status = "confirmed"
                pending.razorpay_ref_id = result.id
                pending.resolved_at = now()
                db.commit()

                if circuit_breaker:
                    circuit_breaker.record_result(segment, succeeded=True)
                
                action = Action(
                    decision_id=decision.decision_id, 
                    arm_name=decision.chosen_arm,
                    simulated=False, 
                    razorpay_ref_id=result.id, 
                    status="executed",
                    executed_at=now()
                )
                logger.info("action_executed", **log_context, simulated=False, status="executed", razorpay_ref_id=result.id)
            except RazorpayPermanentError as e:
                pending.status = "failed"
                pending.resolved_at = now()
                db.commit()
                if circuit_breaker:
                    circuit_breaker.record_result(segment, succeeded=False)
                action = Action(
                    decision_id=decision.decision_id, 
                    arm_name=decision.chosen_arm,
                    simulated=False, 
                    status="failed",
                    executed_at=now()
                )
                audit_log_service.write_error(decision, code="RAZORPAY_PERMANENT_ERROR", reason=str(e))
                logger.info("action_failed", **log_context, simulated=False, status="failed", error="RAZORPAY_PERMANENT_ERROR")
            except RazorpayTransientError as e:
                pending.status = "failed"
                pending.resolved_at = now()
                db.commit()
                if circuit_breaker:
                    circuit_breaker.record_result(segment, succeeded=False)
                action = Action(
                    decision_id=decision.decision_id, 
                    arm_name=decision.chosen_arm,
                    simulated=False, 
                    status="failed",
                    executed_at=now()
                )
                audit_log_service.write_error(decision, code="RAZORPAY_RETRIES_EXHAUSTED", reason=str(e))
                logger.info("action_failed", **log_context, simulated=False, status="failed", error="RAZORPAY_RETRIES_EXHAUSTED")

    elif decision.chosen_arm in DELAYED_ARMS:
        eta = now() + ARM_DELAYS[decision.chosen_arm]
        
        if schedule_delayed_action:
            schedule_delayed_action(str(decision.decision_id), eta)
        
        action = Action(
            decision_id=decision.decision_id, 
            arm_name=decision.chosen_arm,
            simulated=False, 
            scheduled_for=eta, 
            status="scheduled"
        )
        logger.info("action_scheduled", **log_context, simulated=False, status="scheduled")

    elif decision.chosen_arm in NUDGE_ARMS:
        nudge = nudge_generator.generate(decision, language=decision.chosen_arm)
        action = Action(
            decision_id=decision.decision_id, 
            arm_name=decision.chosen_arm,
            simulated=True, 
            message_text=nudge.text, 
            status="executed",
            executed_at=now()
        )
        logger.info("action_executed", **log_context, simulated=True, status="executed", nudge_method=nudge.method)
        if nudge.method == "template_fallback":
            # Just write a note; the action itself succeeded from our perspective
            audit_log_service.write_note(decision, note="nudge_template_fallback_used")

    else:  # NO_OP_ARMS: 'escalate_human', 'stop'
        action = Action(
            decision_id=decision.decision_id, 
            arm_name=decision.chosen_arm,
            simulated=True, 
            status="executed",
            executed_at=now()
        )
        logger.info("action_executed", **log_context, simulated=True, status="executed")

    db.add(action)
    db.commit()
    db.refresh(action)
    return action
