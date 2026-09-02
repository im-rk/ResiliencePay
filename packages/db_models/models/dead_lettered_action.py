import uuid
from sqlalchemy import Column, String, Boolean, DateTime, text, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from packages.db_models.database import Base

class DeadLetteredAction(Base):
    __tablename__ = "dead_lettered_actions"

    dead_letter_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    pending_action_id = Column(UUID(as_uuid=True), ForeignKey('pending_actions.pending_action_id', ondelete='CASCADE'), nullable=False)
    reason = Column(String, nullable=False)
    requires_manual_review = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
