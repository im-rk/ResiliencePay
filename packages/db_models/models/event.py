import uuid
from sqlalchemy import Column, String, Integer, DateTime, text, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from packages.db_models.database import Base

class Event(Base):
    __tablename__ = 'events'

    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    episode_id = Column(UUID(as_uuid=True), ForeignKey('episodes.episode_id', ondelete='CASCADE'), nullable=False, index=True)
    event_type = Column(String, nullable=False)
    gateway_error_code = Column(String)
    raw_gateway_message = Column(String)
    payment_method = Column(String)
    retry_count_so_far = Column(Integer, nullable=False, server_default='0')
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'), index=True)
    raw_payload = Column(JSONB)

    __table_args__ = (
        CheckConstraint('retry_count_so_far >= 0', name='chk_retry_count'),
        Index('idx_events_raw_payload_gin', 'raw_payload', postgresql_using='gin'),
    )
