import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class NudgeResult:
    text: str
    method: str  # "llm_generated" | "template_fallback"

TEMPLATE_FALLBACKS = {
    "send_nudge_hinglish": "Namaste! Aapka payment complete nahi hua. Please retry karein: {link}",
    "send_nudge_english": "Hi! Your recent payment didn't go through. Please retry here: {link}",
    "send_card_update_link": "Your card on file needs updating. Update it here: {link}",
}

import google.generativeai as genai
from packages.config.settings import settings

genai.configure(api_key=settings.gemini_api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

class NudgeGenerator:
    def __init__(self, llm_client=None, timeout_seconds: float = 5.0):
        self.llm_client = llm_client
        self.timeout_seconds = timeout_seconds

    def generate(self, decision, language: str) -> NudgeResult:
        prompt = self._build_prompt(decision, language)
        try:
            from services.act.fault_injection import with_fault_injection
            # wrap the call for fault injection testing
            if self.llm_client is not None:
                text = self.llm_client.complete(prompt)
            else:
                injected_complete = with_fault_injection(lambda p, t: model.generate_content(p).text)
                text = injected_complete(prompt, self.timeout_seconds)
            return NudgeResult(text=text, method="llm_generated")
        except Exception as e:  # noqa: BLE001 — deliberately broad: ANY LLM failure must fall back, never propagate
            logger.warning("nudge_generation_failed_falling_back", extra={
                "arm": language, "error": str(e),
            })
            template = TEMPLATE_FALLBACKS.get(language, TEMPLATE_FALLBACKS["send_nudge_english"])
            return NudgeResult(text=template.format(link="[payment_link]"), method="template_fallback")

    def _build_prompt(self, decision, language: str) -> str:
        tone = "warm, casual Hinglish" if language == "send_nudge_hinglish" else "polite, professional English"
        # Safely access episode_id; assumes decision.episode exists or decision.event.episode exists
        episode_id = getattr(getattr(decision, "episode", decision), "episode_id", "unknown")
        
        return (
            f"Write a short (under 40 words) payment reminder message in {tone}. "
            f"The customer's payment for episode {episode_id} failed. "
            f"Do not be pushy. Include a placeholder [payment_link] for the retry link."
        )
