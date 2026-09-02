import uuid
from sqlalchemy import Column, String, DateTime, text, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from packages.db_models.database import Base

class PendingAction(Base):
    """Durable record of intent, written BEFORE the external Razorpay
    call — this is what makes the dual-write window detectable and
    recoverable rather than silently lost. See ADVANCED_07 for the full
    rationale."""
    __tablename__ = "pending_actions"

    pending_action_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    decision_id = Column(UUID(as_uuid=True), ForeignKey('decisions.decision_id', ondelete='CASCADE'), nullable=False)
    idempotency_key = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="attempting")
    # 'attempting' | 'confirmed' | 'failed' | 'reconciled' | 'dead_lettered'
    razorpay_ref_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
