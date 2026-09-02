import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from packages.domain_constants.cause_categories import CauseCategoryEnum
from services.diagnose.schemas import DiagnosisResult
from pydantic import BaseModel, ValidationError, Field
from packages.config.settings import settings
import json

class LLMOutputSchema(BaseModel):
    cause_category: CauseCategoryEnum
    confidence: float = Field(ge=0.0, le=1.0)
    justification: str

genai.configure(api_key=settings.gemini_api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

def get_fallback_result() -> DiagnosisResult:
    return DiagnosisResult(
        cause_category=CauseCategoryEnum.UNKNOWN,
        method="fallback_failed",
        confidence=0.0,
        justification="LLM fallback failed or timed out."
    )

@retry(
    stop=stop_after_attempt(3), # 1 initial + 2 retries
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((Exception,))
)
def _call_llm(raw_message: str) -> DiagnosisResult:
    prompt = f"Classify this raw payment gateway error message:\n\n{raw_message}"
    
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=LLMOutputSchema,
        )
    )
    
    try:
        # Strict Pydantic Validation on LLM Diagnostics
        parsed = LLMOutputSchema.model_validate_json(response.text)
        return DiagnosisResult(
            cause_category=parsed.cause_category,
            confidence=parsed.confidence,
            method="llm_fallback",
            justification=parsed.justification,
            model_version="gemini-1.5-flash"
        )
    except ValidationError as e:
        raise ValueError(f"Malformed LLM output: {e}")

def classify(raw_message: str) -> DiagnosisResult:
    """
    Classifies a raw gateway message using an LLM.
    Guaranteed to never raise an exception (returns a fallback DiagnosisResult instead).
    """
    if not raw_message:
        return get_fallback_result()
        
    try:
        return _call_llm(raw_message)
    except Exception:
        # Catch *any* exception after all retries are exhausted to guarantee it never raises
        return get_fallback_result()
