from datetime import timedelta, datetime, timezone
from packages.db_models.models.action import Action
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

def execute_action(decision, gate_result, razorpay_client, nudge_generator, audit_log_service, db) -> Action:
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
        try:
            # Assuming decision.episode is available or decision.event.episode
            episode = getattr(decision, "episode", None) or getattr(decision.event, "episode", decision.event)
            
            result = razorpay_client.create_retry_payment_link(episode, idempotency_key)
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
        
        # We must import this dynamically to avoid circular imports during tests,
        # or we assume it's available via an import.
        from apps.worker.src.tasks.execute_delayed_action import execute_delayed_action_task
        execute_delayed_action_task.apply_async(args=[str(decision.decision_id)], eta=eta)
        
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
