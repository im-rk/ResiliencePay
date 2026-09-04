from uuid import UUID
from packages.db_models.models import AuditLog, Episode
from packages.db_models.models.action import Action

def build_episode_facts(db_session, episode_id: str | UUID) -> dict:
    if isinstance(episode_id, str):
        episode_id = UUID(episode_id)
    
    ep = db_session.query(Episode).filter_by(episode_id=episode_id).first()
    if not ep:
        raise ValueError("Episode not found")
        
    logs = db_session.query(AuditLog).filter_by(episode_id=episode_id).order_by(AuditLog.recorded_at.asc()).all()
    actions = db_session.query(Action).filter_by(episode_id=episode_id).order_by(Action.created_at.asc()).all()
    
    actions_taken = [f"{a.action_type} (status: {a.status})" for a in actions]
    blocked_actions = [f"{l.chosen_arm} blocked due to {l.gate_result}" for l in logs if l.gate_result != "pass"]
    
    time_to_res = "ongoing"
    if ep.closed_at:
        delta = ep.closed_at - ep.opened_at
        time_to_res = f"{delta.total_seconds() / 3600:.1f} hours"

    return {
        "cause_category": ep.episode_type,
        "amount_rupees": ep.original_amount / 100.0,
        "attempt_count": ep.attempt_count,
        "actions_taken": ", ".join(actions_taken) if actions_taken else "None",
        "blocked_actions": ", ".join(blocked_actions) if blocked_actions else "None",
        "final_outcome": ep.status,
        "time_to_resolution": time_to_res,
    }


def query_audit_trail(
    db_session,
    episode_id: str | None = None,
    cause_category: str | None = None,
    chosen_arm: str | None = None,
    outcome_result: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Queries audit log table with filtering and pagination."""
    query = db_session.query(AuditLog, Episode.original_amount).outerjoin(
        Episode, AuditLog.episode_id == Episode.episode_id
    )

    if episode_id:
        try:
            query = query.filter(AuditLog.episode_id == UUID(episode_id))
        except ValueError:
            pass
    if cause_category:
        query = query.filter(AuditLog.cause_category == cause_category)
    if chosen_arm:
        query = query.filter(AuditLog.chosen_arm == chosen_arm)
    if outcome_result:
        query = query.filter(AuditLog.outcome_result == outcome_result)

    try:
        total = query.count()
        offset = max(0, (page - 1) * page_size)
        items_and_amounts = query.order_by(AuditLog.recorded_at.desc()).offset(offset).limit(page_size).all()
    except Exception:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    res_items = [
        {
            "audit_id": item.audit_id,
            "event_id": str(item.event_id) if item.event_id else None,
            "episode_id": str(item.episode_id) if item.episode_id else None,
            "cause_category": item.cause_category,
            "chosen_arm": item.chosen_arm,
            "gate_result": item.gate_result,
            "rule_name": item.error_code if item.gate_result == "blocked" else None,
            "simulated": item.simulated,
            "outcome_result": item.outcome_result,
            "reward": float(item.reward) if item.reward is not None else None,
            "recorded_at": item.recorded_at.isoformat() if item.recorded_at else None,
            "amount_paise": original_amount,
        }
        for (item, original_amount) in items_and_amounts
    ]

    return {
        "items": res_items,
        "entries": res_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
