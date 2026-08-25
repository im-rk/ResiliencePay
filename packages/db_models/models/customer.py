import uuid
from sqlalchemy import Column, String, DateTime, text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from packages.db_models.database import Base

class Customer(Base):
    __tablename__ = 'customers'

    customer_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    merchant_id = Column(UUID(as_uuid=True), ForeignKey('merchants.merchant_id', ondelete='CASCADE'), nullable=False, index=True)
    external_ref = Column(String)
    segment = Column(String, nullable=False)
    locale = Column(String, nullable=False, server_default='en-IN')
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))

    __table_args__ = (
        UniqueConstraint('merchant_id', 'external_ref'),
    )

class OptOut(Base):
    __tablename__ = 'opt_outs'

    opt_out_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    customer_id = Column(UUID(as_uuid=True), ForeignKey('customers.customer_id', ondelete='CASCADE'), nullable=False, index=True)
    scope = Column(String, nullable=False, server_default='all_recovery_comms')
    reason = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
