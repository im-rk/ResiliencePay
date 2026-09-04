# Phase 3 — Diagnose Service

**Depends on:** Phase 1 (schema), Phase 2 (data to classify)
**Unblocks:** Phase 5 (Decide needs a diagnosis to build context), Phase 9 (audit trail needs diagnosis justification)
**Owner:** ML-leaning team member
**Estimated time:** ~1 day

## Objective
Classify failure cause deterministically where possible, with an LLM
fallback for ambiguous cases — fast, free, and auditable by default; smart
only where it needs to be.

## Scope
**In scope:** rule table, LLM fallback client, orchestration service, full
test coverage of both paths including failure modes.
**Out of scope:** what happens with the diagnosis after it's produced (Phase 5+).

## Deliverables mapped to monorepo paths

| Path | What goes here |
|---|---|
| `services/diagnose/rules.py` | `gateway_error_code → cause_category` static dict |
| `services/diagnose/llm_fallback.py` | Anthropic API wrapper, structured/constrained output, timeout + retry |
| `services/diagnose/service.py` | Orchestration: rules first, LLM fallback on miss |
| `services/diagnose/schemas.py` | `DiagnosisResult` Pydantic model, `CauseCategory` import from `packages.domain_constants` |
| `services/diagnose/tests/test_rules.py` | Full rule-table coverage |
| `services/diagnose/tests/test_llm_fallback.py` | Mocked LLM client — success, timeout, malformed response |

## Detailed task breakdown

1. **Rule table** — every `gateway_error_code` present in
   `data/error_code_samples.py` (Phase 2) must resolve here. Build the two
   files together, or your Phase 2 dataset will trip Phase 3's `unknown`
   fallback unintentionally.

2. **`DiagnosisResult` contract**
   ```python
   class DiagnosisResult(BaseModel):
       cause_category: CauseCategory
       confidence: float
       method: Literal["rule_based", "llm_fallback", "fallback_failed"]
       justification: str | None = None
       model_version: str | None = None
   ```

3. **LLM fallback wrapper** — structured/tool-call output (enum-constrained
   field), 5s timeout, 2x retry with exponential backoff, falls back to
   `cause_category="unknown", method="fallback_failed", confidence=0.0` on
   any failure — **never raises out of this function**; downstream code
   must be able to rely on always getting a `DiagnosisResult`, never an
   exception.

4. **Orchestration service**
   ```python
   def diagnose(event: Event) -> DiagnosisResult:
       if category := RULES.get(event.gateway_error_code):
           return DiagnosisResult(cause_category=category, confidence=1.0, method="rule_based")
       return llm_fallback.classify(event.raw_gateway_message)
   ```

## Edge-case matrix

| Case | Expected behavior |
|---|---|
| Known gateway error code | Rule-based, confidence=1.0, zero LLM calls (cost + latency saved) |
| Unmapped code, valid LLM response | LLM fallback, confidence from response, justification logged |
| Unmapped code, LLM timeout | `unknown` / `fallback_failed`, confidence=0.0, pipeline continues |
| Unmapped code, LLM returns invalid enum value | Pydantic validation rejects → same fallback path as timeout |
| Empty/null `raw_gateway_message` | Rule path tried on `gateway_error_code` alone; LLM invoked only if that's also missing |

## Design decisions & trade-offs

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Primary strategy | LLM-first vs. rules-first | Rules-first, LLM fallback only | Rules are free, instant, deterministic, trivially explainable — exactly what "explainable" demands |
| LLM resilience | Fire-and-hope vs. retry+timeout+fallback | Retry + timeout + graceful fallback to `unknown` | A hung LLM call must never block the pipeline |
| Output format | Free text vs. structured/constrained | Structured (enum-constrained) | Eliminates a whole bug class from inconsistent free-text parsing |

## Test plan
- **Unit:** rule table covers 100% of codes in the Phase 2 dataset.
- **Unit (mocked LLM):** valid response, timeout, and malformed-response paths.
- **Contract test:** `DiagnosisResult` schema rejects any out-of-enum `cause_category`.

## Definition of Done
- [ ] 0% unintended `unknown` classifications on the Phase 2 synthetic dataset.
- [ ] LLM timeout/failure path proven non-blocking via a forced-failure test.
- [ ] `diagnose()` never raises — always returns a `DiagnosisResult`.

## Handoff to Phase 5
Phase 5 assumes: a `DiagnosisResult` object it can fold into the bandit's
`context_bucket` construction (specifically `cause_category`).
