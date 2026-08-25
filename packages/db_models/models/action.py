import uuid
from sqlalchemy import Column, String, Boolean, DateTime, text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from packages.db_models.database import Base

class Action(Base):
    __tablename__ = 'actions'

    action_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    decision_id = Column(UUID(as_uuid=True), ForeignKey('decisions.decision_id', ondelete='CASCADE'), nullable=False, index=True)
    arm_name = Column(String, ForeignKey('arms.arm_name'), nullable=False)
    simulated = Column(Boolean, nullable=False)
    razorpay_ref_id = Column(String)
    message_text = Column(String)
    scheduled_for = Column(DateTime(timezone=True))
    executed_at = Column(DateTime(timezone=True))
    status = Column(String, nullable=False, server_default='scheduled')

    __table_args__ = (
        Index('idx_actions_status_scheduled', 'status', 'scheduled_for'),
    )
