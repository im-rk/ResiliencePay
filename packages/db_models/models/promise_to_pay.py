import uuid
from sqlalchemy import Column, String, Date, DateTime, Numeric, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from packages.db_models.database import Base

class PromiseToPay(Base):
    __tablename__ = "promises_to_pay"

    ptp_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    episode_id = Column(UUID(as_uuid=True), ForeignKey("episodes.episode_id", ondelete="CASCADE"), nullable=False, index=True)
    promised_date = Column(Date, nullable=False)
    source_message = Column(String, nullable=False)
    extraction_confidence = Column(Numeric(4, 3), nullable=False)
    status = Column(String, nullable=False, server_default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
