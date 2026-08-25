import uuid
from sqlalchemy import Column, String, DateTime, text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from packages.db_models.database import Base

class GateCheck(Base):
    __tablename__ = 'gate_checks'

    gate_check_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    decision_id = Column(UUID(as_uuid=True), ForeignKey('decisions.decision_id', ondelete='CASCADE'), nullable=False, index=True)
    result = Column(String, nullable=False, index=True)
    rule_triggered = Column(String)
    checked_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
