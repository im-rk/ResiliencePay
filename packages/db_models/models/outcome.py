import uuid
from sqlalchemy import Column, String, BigInteger, Numeric, DateTime, text, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from packages.db_models.database import Base

class Outcome(Base):
    __tablename__ = 'outcomes'

    outcome_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    action_id = Column(UUID(as_uuid=True), ForeignKey('actions.action_id', ondelete='CASCADE'), nullable=False, index=True)
    result = Column(String, nullable=False, index=True)
    amount_recovered = Column(BigInteger, nullable=False, server_default='0')
    reward = Column(Numeric(4, 3), nullable=False)
    time_to_resolution_hrs = Column(Numeric(8, 2))
    observed_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))

    __table_args__ = (
        CheckConstraint('amount_recovered >= 0', name='chk_amount_recovered'),
        UniqueConstraint('action_id', name='uq_outcome_action'),
    )
