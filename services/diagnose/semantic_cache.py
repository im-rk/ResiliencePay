from sqlalchemy import text
from packages.db_models.models.diagnosis_embedding import DiagnosisEmbedding
from services.diagnose.schemas import DiagnosisResult
from packages.domain_constants.cause_categories import CauseCategoryEnum

SIMILARITY_THRESHOLD = 0.95

def find_cached_classification(db_session, raw_message: str, embed_fn):
    query_embedding = embed_fn(raw_message)
    
    result = db_session.execute(
        text("""
            SELECT cause_category, confidence, 1 - (embedding <=> :query_embedding) AS similarity
            FROM diagnosis_embeddings
            ORDER BY embedding <=> :query_embedding
            LIMIT 1
        """),
        {"query_embedding": str(query_embedding)},
    ).fetchone()

    if result is None or result.similarity < SIMILARITY_THRESHOLD:
        return None

    return DiagnosisResult(
        cause_category=CauseCategoryEnum(result.cause_category), 
        confidence=float(result.confidence),
        method="semantic_cache_hit",
        justification=f"similarity={result.similarity:.4f} to a prior classification",
    )

def store_classification_for_future_cache_hits(db_session, raw_message: str, result: DiagnosisResult, embed_fn):
    db_session.add(DiagnosisEmbedding(
        raw_message=raw_message, 
        embedding=embed_fn(raw_message),
        cause_category=result.cause_category.value, 
        confidence=result.confidence,
    ))
    db_session.commit()
