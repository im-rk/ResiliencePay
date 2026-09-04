# Advanced Feature 2 — LLM-Generated Audit Narrator

**Effort:** ~half a day
**Builds on:** Phase 9 (audit query API), Phase 10 (dashboard)
**Demo impact:** Very high — this is the single cheapest, most visually compelling addition on this list

---

## The gap this closes

Your audit trail (`AuditTrailTable`) is technically complete and honest,
but it's a table of codes and IDs — exactly the kind of thing that's
convincing to an engineer reading it carefully and completely
unmemorable to a judge glancing at it for ten seconds during a live demo.
The information is all there; the *legibility* isn't.

## The addition

For any single episode, generate a short, plain-English narrative summary
of its full recovery journey by feeding its structured audit trail (not
raw text — structured facts) to an LLM with a tightly constrained prompt.
This is explicitly **not** a new decision-making component — it never
influences the pipeline, it only explains what already happened, after the
fact, for human consumption.

## Implementation

### `services/audit/narrator.py`

```python
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
    def __init__(self, llm_client, timeout_seconds: float = 5.0):
        self.llm_client = llm_client
        self.timeout_seconds = timeout_seconds

    def narrate(self, episode_facts: dict) -> EpisodeNarrative:
        prompt = NARRATOR_PROMPT_TEMPLATE.format(**episode_facts)
        try:
            text = self.llm_client.complete(prompt, timeout=self.timeout_seconds)
            return EpisodeNarrative(text=text, method="llm_generated")
        except Exception:  # same guaranteed-fallback contract as Phase 6's NudgeGenerator
            return EpisodeNarrative(
                text=TEMPLATE_FALLBACK.format(**episode_facts), method="template_fallback"
            )
```

**Reuses the exact guaranteed-fallback pattern from
`PHASE_06_act_DETAILED.md`'s `NudgeGenerator`** — this is not a new design,
it's applying an already-established, already-tested pattern to a new
piece of content. Point this out explicitly if asked "did you just copy
this pattern" — yes, deliberately, because reusing a proven pattern is
correct engineering, not a lack of originality.

### API endpoint — `apps/api/src/routers/audit.py` addition

```python
@router.get("/audit-trail/{episode_id}/narrative")
def episode_narrative(episode_id: str, db_session=Depends(get_db_session)):
    facts = build_episode_facts(db_session, episode_id)  # services/audit/query_service.py helper
    narrative = narrator.narrate(facts)
    return {"episode_id": episode_id, "narrative": narrative.text, "method": narrative.method}
```

### Dashboard addition

In `AuditTrailTable`, add an expandable row that fetches and displays this
narrative on click — "Explain this episode" — rather than showing it for
every row by default (that would be slow and noisy; make it an
on-demand, single-click reveal).

## Why this doesn't compromise anything already built

This is read-only and side-effect-free — it consumes the already-written
audit trail and never writes anything back, never influences a decision,
and never touches the bandit or Gate. It's the lowest-risk addition on
this entire list precisely because it sits fully downstream of everything
else.

## Test to write

```python
def test_narrator_never_raises_and_falls_back_on_llm_failure():
    failing_llm = MagicMock()
    failing_llm.complete.side_effect = TimeoutError("llm slow")
    narrator = AuditNarrator(llm_client=failing_llm)
    result = narrator.narrate(sample_episode_facts())
    assert result.method == "template_fallback"
    assert result.text  # non-empty, always something to show

def test_narrator_never_invents_facts_not_provided():
    """Not fully automatable, but worth a manual spot-check during
    rehearsal: read 5 generated narratives against their source facts and
    confirm no invented numbers or claims appear. Note this as a manual
    QA step in DEMO_SCRIPT.md, not just an automated test."""
```

## What to say in the demo

*"Every number in this system is queryable and auditable on its own — but
for a merchant's ops team who doesn't want to read a database table, we
generate a plain-English summary of what happened and why, built entirely
from the same structured facts already in the audit trail. It never makes
a decision — it only explains one that's already been made and logged."*
