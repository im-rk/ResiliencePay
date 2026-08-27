from uuid import UUID
from packages.db_models.models import AuditLog


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
    query = db_session.query(AuditLog)

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

    total = query.count()
    offset = max(0, (page - 1) * page_size)
    items = query.order_by(AuditLog.recorded_at.desc()).offset(offset).limit(page_size).all()

    return {
        "items": [
            {
                "audit_id": item.audit_id,
                "event_id": str(item.event_id) if item.event_id else None,
                "episode_id": str(item.episode_id) if item.episode_id else None,
                "cause_category": item.cause_category,
                "chosen_arm": item.chosen_arm,
                "gate_result": item.gate_result,
                "simulated": item.simulated,
                "outcome_result": item.outcome_result,
                "reward": float(item.reward) if item.reward is not None else None,
                "recorded_at": item.recorded_at.isoformat() if item.recorded_at else None,
            }
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
