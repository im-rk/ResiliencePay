"""DTOs — the ONLY shapes that ever leave services/* toward apps/api.
Never return a raw SQLAlchemy model instance from a service function that
a router will serialize directly."""
from datetime import datetime
from pydantic import BaseModel

class EventStateDTO(BaseModel):
    event_id: str
    episode_id: str
    cause_category: str | None
    diagnosis_confidence: float | None
    chosen_arm: str | None
    gate_passed: bool | None
    simulated: bool | None
    outcome_result: str | None
    amount_recovered: int | None  # paise
    occurred_at: datetime

    model_config = {"from_attributes": False}  # deliberately False — force explicit mapping, never implicit ORM passthrough
