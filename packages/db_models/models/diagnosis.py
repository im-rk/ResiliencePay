import uuid
from sqlalchemy import Column, String, Numeric, DateTime, text, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from packages.db_models.database import Base

class Diagnosis(Base):
    __tablename__ = 'diagnoses'

    diagnosis_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    event_id = Column(UUID(as_uuid=True), ForeignKey('events.event_id', ondelete='CASCADE'), nullable=False, index=True)
    cause_category = Column(String, nullable=False, index=True)
    confidence = Column(Numeric(4, 3), nullable=False)
    method = Column(String, nullable=False)
    justification = Column(String)
    model_version = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))

    __table_args__ = (
        CheckConstraint('confidence >= 0 AND confidence <= 1', name='chk_confidence'),
    )
