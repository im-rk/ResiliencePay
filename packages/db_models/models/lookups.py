from sqlalchemy import Column, String, Boolean
from packages.db_models.database import Base

class CauseCategory(Base):
    __tablename__ = 'cause_categories'

    cause_category = Column(String, primary_key=True)
    description = Column(String, nullable=False)
    typical_recoverable = Column(Boolean, nullable=False, server_default='true')

class Arm(Base):
    __tablename__ = 'arms'

    arm_name = Column(String, primary_key=True)
    description = Column(String, nullable=False)
    is_real_action = Column(Boolean, nullable=False)
