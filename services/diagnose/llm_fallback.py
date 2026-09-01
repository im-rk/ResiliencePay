import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from packages.domain_constants.cause_categories import CauseCategoryEnum
from services.diagnose.schemas import DiagnosisResult
from packages.config.settings import settings

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

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
    retry=retry_if_exception_type((anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.InternalServerError, ValueError))
)
def _call_llm(raw_message: str) -> DiagnosisResult:
    tools = [
        {
            "name": "provide_diagnosis",
            "description": "Provide a diagnosis for the payment failure.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "cause_category": {
                        "type": "string",
                        "enum": [e.value for e in CauseCategoryEnum if e != CauseCategoryEnum.UNKNOWN],
                        "description": "The category of the failure."
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence score from 0.0 to 1.0."
                    },
                    "justification": {
                        "type": "string",
                        "description": "A brief explanation of why this category was chosen."
                    }
                },
                "required": ["cause_category", "confidence", "justification"]
            }
        }
    ]

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=200,
        timeout=5.0, # 5s timeout as requested
        tools=tools,
        tool_choice={"type": "tool", "name": "provide_diagnosis"},
        messages=[
            {
                "role": "user",
                "content": f"Classify this raw payment gateway error message:\n\n{raw_message}"
            }
        ]
    )

    for content in response.content:
        if content.type == "tool_use" and content.name == "provide_diagnosis":
            args = content.input
            try:
                return DiagnosisResult(
                    cause_category=CauseCategoryEnum(args["cause_category"]),
                    confidence=float(args["confidence"]),
                    method="llm_fallback",
                    justification=args["justification"],
                    model_version="claude-3-haiku-20240307"
                )
            except (KeyError, ValueError) as e:
                raise ValueError(f"Malformed LLM output: {e}")
                
    raise ValueError("LLM did not return a valid tool call.")

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
