from packages.config.settings import settings
import anthropic
from dataclasses import dataclass

@dataclass(frozen=True)
class EpisodeNarrative:
    text: str
    method: str  # "llm_generated" | "template_fallback"


NARRATOR_PROMPT_TEMPLATE = """\
You are summarizing a payment recovery episode for a non-technical reader.
Given these structured facts, write a plain-English summary in 2-3
sentences. Do not invent any fact not present below. Do not use technical
jargon like "bandit," "gate," or "context bucket" — describe what happened
in terms a merchant's finance team would understand.

Facts:
- Original failure cause: {cause_category}
- Amount at risk: Rs. {amount_rupees}
- Number of recovery attempts: {attempt_count}
- Actions taken, in order: {actions_taken}
- Any actions blocked, and why: {blocked_actions}
- Final outcome: {final_outcome}
- Total time to resolution: {time_to_resolution}
"""

TEMPLATE_FALLBACK = (
    "This episode involved {attempt_count} recovery attempt(s) for a "
    "{cause_category} failure. Final outcome: {final_outcome}."
)


class AuditNarrator:
    def __init__(self, timeout_seconds: float = 5.0):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.timeout_seconds = timeout_seconds

    def narrate(self, episode_facts: dict) -> EpisodeNarrative:
        prompt = NARRATOR_PROMPT_TEMPLATE.format(**episode_facts)
        try:
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=150,
                timeout=self.timeout_seconds,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text
            return EpisodeNarrative(text=text, method="llm_generated")
        except Exception:  # guaranteed fallback
            return EpisodeNarrative(
                text=TEMPLATE_FALLBACK.format(**episode_facts), method="template_fallback"
            )
