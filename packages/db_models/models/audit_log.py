from sqlalchemy import Column, String, Boolean, Numeric, DateTime, text, Index, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from packages.db_models.database import Base

class AuditLog(Base):
    __tablename__ = 'audit_log'

    audit_id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(UUID(as_uuid=True), nullable=False)
    episode_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    cause_category = Column(String)
    chosen_arm = Column(String)
    gate_result = Column(String)
    simulated = Column(Boolean)
    outcome_result = Column(String)
    error_code = Column(String)
    reward = Column(Numeric(4, 3))
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'), index=True)
