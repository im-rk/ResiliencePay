import json
import math
from services.diagnose.semantic_cache import find_cached_classification, store_classification_for_future_cache_hits
from services.diagnose.schemas import DiagnosisResult
from packages.domain_constants.cause_categories import CauseCategoryEnum

def fake_embed_fn(text: str):
    if text == "Insufficient balance in account":
        return [1.0, 0.0] + [0.0]*766
    elif text == "Insufficient funds available":
        return [0.99, 0.14] + [0.0]*766  # ~0.99 cosine similarity
    elif text == "Card reported stolen by issuer":
        return [0.0, 1.0] + [0.0]*766  # 0.0 cosine similarity
    return [0.0]*768

class MockDBSession:
    def __init__(self):
        self.embeddings = []
        
    def add(self, obj):
        self.embeddings.append(obj)
        
    def commit(self):
        pass
        
    def execute(self, query, params):
        class Result:
            def __init__(self, data):
                self.data = data
            def fetchone(self):
                return self.data
                
        query_emb_str = params["query_embedding"]
        query_emb = json.loads(query_emb_str)
        
        best_match = None
        best_sim = -1.0
        
        def cosine_sim(v1, v2):
            dot = sum(a*b for a, b in zip(v1, v2))
            mag1 = math.sqrt(sum(a*a for a in v1))
            mag2 = math.sqrt(sum(b*b for b in v2))
            if mag1 * mag2 == 0: return 0
            return dot / (mag1 * mag2)
            
        for e in self.embeddings:
            sim = cosine_sim(e.embedding, query_emb)
            if sim > best_sim:
                best_sim = sim
                best_match = e
                
        if best_match:
            class Row:
                cause_category = best_match.cause_category
                confidence = best_match.confidence
                similarity = best_sim
            return Result(Row())
        
        return Result(None)

def test_semantic_cache_hit_skips_llm_call():
    db_session = MockDBSession()
    
    store_classification_for_future_cache_hits(
        db_session, "Insufficient balance in account",
        DiagnosisResult(cause_category=CauseCategoryEnum.INSUFFICIENT_FUNDS, confidence=0.92, method="llm_fallback", justification=""),
        fake_embed_fn,
    )
    
    result = find_cached_classification(db_session, "Insufficient funds available", fake_embed_fn)
    
    assert result is not None
    assert result.cause_category == CauseCategoryEnum.INSUFFICIENT_FUNDS
    assert result.method == "semantic_cache_hit"

def test_dissimilar_message_does_not_hit_cache():
    db_session = MockDBSession()
    
    store_classification_for_future_cache_hits(
        db_session, "Insufficient balance in account",
        DiagnosisResult(cause_category=CauseCategoryEnum.INSUFFICIENT_FUNDS, confidence=0.92, method="llm_fallback", justification=""),
        fake_embed_fn,
    )
    
    result = find_cached_classification(db_session, "Card reported stolen by issuer", fake_embed_fn)
    
    assert result is None
