from sqlalchemy import Column, String, Numeric, DateTime, text, ForeignKey, PrimaryKeyConstraint
from packages.db_models.database import Base

class BanditArmStats(Base):
    __tablename__ = 'bandit_arm_stats'

    context_bucket = Column(String, nullable=False)
    arm_name = Column(String, ForeignKey('arms.arm_name'), nullable=False)
    alpha = Column(Numeric(12, 4), nullable=False, server_default='1.0')
    beta = Column(Numeric(12, 4), nullable=False, server_default='1.0')
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text('now()'))

    __table_args__ = (
        PrimaryKeyConstraint('context_bucket', 'arm_name'),
    )
