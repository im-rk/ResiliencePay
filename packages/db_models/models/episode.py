import uuid
from sqlalchemy import Column, String, Integer, BigInteger, DateTime, text, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from packages.db_models.database import Base

class Episode(Base):
    __tablename__ = 'episodes'

    episode_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    merchant_id = Column(UUID(as_uuid=True), ForeignKey('merchants.merchant_id'), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey('customers.customer_id'), nullable=False, index=True)
    episode_type = Column(String, nullable=False)
    original_amount = Column(BigInteger, nullable=False)
    currency = Column(String(3), nullable=False, server_default='INR')
    status = Column(String, nullable=False, server_default='open')
    opened_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    closed_at = Column(DateTime(timezone=True))
    attempt_count = Column(Integer, nullable=False, server_default='0')
    last_action_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint('original_amount > 0', name='chk_episode_amount'),
        Index('idx_episodes_merchant_status', 'merchant_id', 'status'),
    )

