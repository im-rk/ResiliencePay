import uuid
from sqlalchemy import Column, String, Numeric, DateTime, text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from packages.db_models.database import Base

class Decision(Base):
    __tablename__ = 'decisions'

    decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    event_id = Column(UUID(as_uuid=True), ForeignKey('events.event_id', ondelete='CASCADE'), nullable=False, index=True)
    chosen_arm = Column(String, nullable=False, index=True)
    context_bucket = Column(String, nullable=False)
    sampled_score = Column(Numeric(6, 5))
    alpha_at_decision = Column(Numeric(10, 4))
    beta_at_decision = Column(Numeric(10, 4))
    decided_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
