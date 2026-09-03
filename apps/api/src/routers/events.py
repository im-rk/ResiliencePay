from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from apps.api.src.dependencies import get_db_session
from apps.api.src.middleware.error_handler import NotFoundError
from services.observe.dtos import EventStateDTO
from services.observe.query_service import get_event_full_state
from services.observe.webhook_handlers import now, hours_between
from services.observe.reward_service import RewardService
from services.audit.audit_log_service import AuditLogService
from packages.db_models.models import Event, Decision, Action, Episode, Outcome
from packages.db_models.models import Merchant, Customer
from sqlalchemy.dialects.postgresql import insert
import uuid
from datetime import datetime, timezone

router = APIRouter()


class IngestEventRequest(BaseModel):
    event_type: str = "subscription_charge_failed"
    merchant_id: str
    customer_id: str
    amount: int
    currency: str = "INR"
    gateway_error_code: str | None = None
    raw_gateway_message: str | None = None
    customer_segment: str = "new"
    retry_count_so_far: int = 0

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive_and_reasonable(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("amount must be positive")
        if v > 100_000_000:
            raise ValueError("amount exceeds reasonable ceiling — check units (paise, not rupees)")
        return v

    @field_validator("currency")
    @classmethod
    def currency_must_be_supported(cls, v: str) -> str:
        if v != "INR":
            raise ValueError("only INR is supported in this build")
        return v


class MarkResolvedRequest(BaseModel):
    result: str  # "recovered" | "not_recovered"


@router.post("/events/ingest", status_code=202)
def ingest_event(body: IngestEventRequest, db_session=Depends(get_db_session)):
    """Ingests a new failure event and queues for diagnosis."""
    timestamp = datetime.now(timezone.utc)
    merchant_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"resiliencepay:merchant:{body.merchant_id}")
    customer_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"resiliencepay:customer:{body.merchant_id}:{body.customer_id}")

    merchant = db_session.query(Merchant).filter_by(merchant_id=merchant_uuid).first()
    if merchant is None:
        merchant = Merchant(
            merchant_id=merchant_uuid,
            name=body.merchant_id,
            razorpay_key_id="test",
            vertical="general",
            created_at=timestamp,
        )
        db_session.add(merchant)

    customer = db_session.query(Customer).filter_by(customer_id=customer_uuid).first()
    if customer is None:
        customer = Customer(
            customer_id=customer_uuid,
            merchant_id=merchant_uuid,
            external_ref=body.customer_id,
            segment=body.customer_segment,
            locale="en-IN",
            created_at=timestamp,
        )
        db_session.add(customer)

    episode = Episode(
        merchant_id=merchant_uuid,
        customer_id=customer_uuid,
        episode_type=body.event_type,
        original_amount=body.amount,
        currency=body.currency,
        opened_at=timestamp,
    )
    db_session.add(episode)
    db_session.flush()
    event = Event(
        episode_id=episode.episode_id,
        event_type=body.event_type,
        gateway_error_code=body.gateway_error_code,
        raw_gateway_message=body.raw_gateway_message,
        retry_count_so_far=body.retry_count_so_far,
        raw_payload=body.model_dump(),
        occurred_at=timestamp,
    )
    db_session.add(event)
    db_session.commit()

    return {
        "event_id": str(event.event_id),
        "status": "queued_for_diagnosis",
        "amount": body.amount,
    }


@router.get("/events/{event_id}", response_model=EventStateDTO)
def get_event(event_id: str, db_session=Depends(get_db_session)):
    """Returns the full pipeline state for one event using DTO mapper."""
    state = get_event_full_state(db_session, event_id)
    if state is None:
        raise NotFoundError(resource="event", resource_id=event_id)
    return state


@router.post("/events/{event_id}/mark-resolved")
def mark_resolved(event_id: str, body: MarkResolvedRequest, db_session=Depends(get_db_session)):
    """Manual trigger for live demos only."""
    reward_service = RewardService()
    audit_log_service = AuditLogService(db_session)

    event = db_session.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise NotFoundError(resource="event", resource_id=event_id)

    decision = db_session.query(Decision).filter(Decision.event_id == event.event_id).order_by(Decision.decided_at.desc()).first()
    if not decision:
        raise NotFoundError(resource="decision", resource_id=event_id)

    action = db_session.query(Action).filter(Action.decision_id == decision.decision_id).order_by(Action.executed_at.desc()).first()
    if not action:
        raise NotFoundError(resource="action", resource_id=str(decision.decision_id))

    episode = db_session.query(Episode).filter(Episode.episode_id == event.episode_id).first()

    outcome_result = body.result
    amount_recovered = episode.original_amount if body.result == "recovered" else 0
    time_to_res = hours_between(action.executed_at, now())

    outcome_obj = Outcome(
        action_id=action.action_id,
        result=outcome_result,
        amount_recovered=amount_recovered,
        time_to_resolution_hrs=time_to_res,
    )
    reward = reward_service.compute(outcome_obj)

    stmt = insert(Outcome).values(
        action_id=action.action_id,
        result=outcome_result,
        amount_recovered=amount_recovered,
        reward=reward,
        time_to_resolution_hrs=time_to_res,
    ).on_conflict_do_nothing(index_elements=['action_id'])

    result_proxy = db_session.execute(stmt)
    if result_proxy.rowcount > 0:
        db_session.commit()
        inserted = db_session.query(Outcome).filter_by(action_id=action.action_id).first()
        audit_log_service.write(event=event, decision=decision, outcome=inserted)

    return {"status": "ok"}
