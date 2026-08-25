import uuid
from sqlalchemy import Column, String, Integer, BigInteger, Numeric, DateTime, text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from packages.db_models.database import Base

class BatchRun(Base):
    __tablename__ = 'batch_runs'

    run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    policy = Column(String, nullable=False)
    dataset_ref = Column(String, nullable=False)
    random_seed = Column(Integer, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))
    finished_at = Column(DateTime(timezone=True))


class BatchRunMetrics(Base):
    __tablename__ = 'batch_run_metrics'

    run_id = Column(UUID(as_uuid=True), ForeignKey('batch_runs.run_id', ondelete='CASCADE'), primary_key=True)
    n_events = Column(Integer, nullable=False)
    recovery_rate = Column(Numeric(5, 4), nullable=False)
    amount_recovered = Column(BigInteger, nullable=False)
    amount_at_risk = Column(BigInteger, nullable=False)
    avg_time_to_recovery_hrs = Column(Numeric(8, 2))
    exception_count = Column(Integer, nullable=False)
    gate_blocked_count = Column(Integer, nullable=False)
