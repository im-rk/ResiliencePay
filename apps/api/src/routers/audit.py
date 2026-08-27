from fastapi import APIRouter, Depends, Query
from apps.api.src.dependencies import get_db_session
from services.audit.query_service import query_audit_trail

router = APIRouter()


@router.get("/audit-trail")
def audit_trail(
    episode_id: str | None = None,
    cause_category: str | None = None,
    chosen_arm: str | None = None,
    outcome_result: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db_session=Depends(get_db_session),
):
    """Returns filterable, paginated audit trail records for the dashboard."""
    return query_audit_trail(
        db_session,
        episode_id=episode_id,
        cause_category=cause_category,
        chosen_arm=chosen_arm,
        outcome_result=outcome_result,
        page=page,
        page_size=page_size,
    )
