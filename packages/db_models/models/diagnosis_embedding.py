import uuid
from sqlalchemy import Column, String, DateTime, text, func, Numeric
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from packages.db_models.database import Base

class DiagnosisEmbedding(Base):
    __tablename__ = "diagnosis_embeddings"

    embedding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    raw_message = Column(String, nullable=False)
    embedding = Column(Vector(768), nullable=False)
    cause_category = Column(String, nullable=False)
    confidence = Column(Numeric(4, 3), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
