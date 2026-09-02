import google.generativeai as genai
from datetime import date
from pydantic import ValidationError
from packages.config.settings import settings
from services.observe.schemas import PTPExtractionSchema, PTPExtractionResult
import structlog

logger = structlog.get_logger(__name__)

genai.configure(api_key=settings.gemini_api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

PTP_EXTRACTION_PROMPT = """\
A customer replied to a payment reminder. Determine if they committed to a
specific payment date. If yes, extract that date in YYYY-MM-DD format,
relative to today's date: {today}. If no clear commitment or date was
made, return null.

Customer reply: "{customer_reply}"

Respond ONLY with valid JSON matching this schema:
{{"promised_date": "YYYY-MM-DD" or null, "confidence": 0.0-1.0}}
"""

def extract_promise_to_pay(customer_reply: str) -> PTPExtractionResult | None:
    if not customer_reply:
        return None
        
    prompt = PTP_EXTRACTION_PROMPT.format(
        today=date.today().isoformat(), 
        customer_reply=customer_reply
    )
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=PTPExtractionSchema,
            )
        )
        parsed = PTPExtractionSchema.model_validate_json(response.text)
        
        if parsed.promised_date is None or parsed.confidence < 0.7:
            return None
            
        return PTPExtractionResult(
            promised_date=parsed.promised_date, 
            confidence=parsed.confidence
        )
    except Exception as e:
        logger.error("ptp_extraction_failed", error=str(e))
        return None
