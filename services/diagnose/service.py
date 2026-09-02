from packages.db_models.models.event import Event
from services.diagnose.schemas import DiagnosisResult
from services.diagnose.rules import RULES
from services.diagnose import llm_fallback
from services.diagnose.semantic_cache import find_cached_classification, store_classification_for_future_cache_hits
from services.diagnose.embedder import embed_text
from sqlalchemy.orm import Session

def diagnose(event: Event, db_session: Session) -> DiagnosisResult:
    """
    Orchestrates the diagnosis process:
    1. Fast rule-based lookup on gateway_error_code.
    2. Slower LLM fallback on raw_gateway_message if rules miss.
    """
    if event.gateway_error_code:
        if category := RULES.get(event.gateway_error_code):
            return DiagnosisResult(
                cause_category=category, 
                confidence=1.0, 
                method="rule_based"
            )
            
    raw_message = getattr(event, "raw_gateway_message", None)
    if not raw_message and event.raw_payload:
        raw_message = event.raw_payload.get("raw_gateway_message", "")
        
    raw_message = raw_message or ""

    if raw_message:
        if cached := find_cached_classification(db_session, raw_message, embed_text):
            return cached

    result = llm_fallback.classify(raw_message)
    
    if result.method == "llm_fallback" and raw_message: 
        store_classification_for_future_cache_hits(db_session, raw_message, result, embed_text)
        
    return result
