from packages.db_models.models.event import Event
from services.diagnose.schemas import DiagnosisResult
from services.diagnose.rules import RULES
from services.diagnose import llm_fallback

def diagnose(event: Event) -> DiagnosisResult:
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
            
    # Attempt to extract raw message; fallback to empty string if missing
    raw_message = getattr(event, "raw_gateway_message", None)
    if not raw_message and event.raw_payload:
        raw_message = event.raw_payload.get("raw_gateway_message", "")
        
    return llm_fallback.classify(raw_message or "")
