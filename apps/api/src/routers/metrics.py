from fastapi import APIRouter, Depends, Query
from apps.api.src.dependencies import get_db_session
from apps.api.src.middleware.error_handler import NotFoundError
from services.observe.query_service import get_batch_summary, get_learning_curve_data

router = APIRouter()


@router.get("/metrics/summary")
def metrics_summary(run_id: str = "sample", db_session=Depends(get_db_session)):
    """Returns headline metrics for a batch run."""
    summary = get_batch_summary(db_session, run_id)
    if summary is None:
        raise NotFoundError(resource="batch_run", resource_id=run_id)
    return summary


@router.get("/metrics/learning-curve")
def learning_curve(
    run_id: str = "sample",
    bucket_size: int = Query(default=20, ge=5, le=100),
    db_session=Depends(get_db_session),
):
    """Returns rolling recovery rate data over batch progress for the learning curve chart."""
    return get_learning_curve_data(db_session, run_id, bucket_size)
