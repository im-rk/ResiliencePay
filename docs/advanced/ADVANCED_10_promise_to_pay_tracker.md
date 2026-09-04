# Advanced Feature 10 — Promise-to-Pay (PTP) Tracker

**Effort:** ~1 day
**Builds on:** Phase 4 (Gate), Phase 6 (Act), Phase 7 (Observe)
**Priority note:** This is explicitly named in Track 03's own example
directions ("Promise-to-pay tracker") — treat this as higher priority than
a generic "nice to have," since it directly demonstrates you built toward
the brief's own suggested feature set, not just the minimum bar

---

## The gap this closes

For B2B receivables (overdue invoices), blind retry logic doesn't apply —
a business customer who says "we'll clear this by Friday" shouldn't be
hit with automated nudges or retries in the meantime; doing so would be
both counterproductive and a bad look for the merchant. Real dunning
systems handle this with a distinct state: **Promise-to-Pay (PTP)** — a
customer commitment with a specific date, during which automated recovery
is deliberately paused, and which is checked and escalated if the promised
date passes without payment.

## The state machine addition

```
ACTIVE_RECOVERY  →  [customer commits to a date via nudge reply]  →  PROMISE_TO_PAY
                                                                            |
                                                        [payment received before promised_date]
                                                                            |
                                                                            v
                                                                        RESOLVED
                                                                            |
                                              [promised_date + grace period passes, still unpaid]
                                                                            |
                                                                            v
                                                                   ACTIVE_RECOVERY (resumed)
```

## Implementation

### Schema addition

```python
class PromiseToPay(Base):
    __tablename__ = "promises_to_pay"

    ptp_id: Mapped[uuid.UUID] = uuid_pk()
    episode_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("episodes.episode_id"), nullable=False)
    promised_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_message: Mapped[str] = mapped_column(String, nullable=False)  # the raw customer reply text, for audit
    extraction_confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")  # 'active' | 'kept' | 'broken'
    created_at: Mapped[datetime] = created_at_col()
```

### Date extraction — constrained, not free-text parsing

```python
# services/observe/ptp_extraction.py
PTP_EXTRACTION_PROMPT = """\
A customer replied to a payment reminder. Determine if they committed to a
specific payment date. If yes, extract that date in YYYY-MM-DD format,
relative to today's date: {today}. If no clear commitment or date was
made, return null.

Customer reply: "{customer_reply}"

Respond ONLY with valid JSON: {{"promised_date": "YYYY-MM-DD" or null, "confidence": 0.0-1.0}}
"""

def extract_promise_to_pay(customer_reply: str, llm_client) -> "PTPExtractionResult | None":
    response = llm_client.complete_structured(
        PTP_EXTRACTION_PROMPT.format(today=date.today().isoformat(), customer_reply=customer_reply),
        schema=PTPExtractionSchema,  # Pydantic model with promised_date: date | None, confidence: float
    )
    if response.promised_date is None or response.confidence < 0.7:
        return None  # ambiguous replies fall back to normal recovery flow, not a guessed date
    return PTPExtractionResult(promised_date=response.promised_date, confidence=response.confidence)
```

**Never act on a low-confidence extraction** — an ambiguous reply
("maybe soon") must not freeze recovery on a fabricated date; the
threshold (0.7) is a deliberate conservative choice, same reasoning as
the semantic-cache threshold in `ADVANCED_08`.

### Gate rule addition

```python
def check_active_promise_to_pay(episode, db_session, now: date) -> "RuleResult":
    """Added to RULE_CHAIN — see PHASE_04_gate_DETAILED.md's rule ordering.
    Placed after opt-out (still the highest priority) but before
    operational rules like max_attempts, since an active promise is a
    customer commitment that should suppress automated action regardless
    of retry count."""
    ptp = get_active_promise(db_session, episode.episode_id)
    if ptp and now <= (ptp.promised_date + GRACE_PERIOD):
        return ("blocked", "active_promise_to_pay")
    return "pass"
```

### Reconciliation — checking broken promises

```python
# apps/worker/src/tasks/check_promise_to_pay_status.py
@celery_app.task
def check_promise_to_pay_deadlines():
    overdue = find_promises_past_grace_period(status="active")
    for ptp in overdue:
        episode = get_episode(ptp.episode_id)
        if episode.status == "recovered":
            ptp.status = "kept"
        else:
            ptp.status = "broken"
            # Episode returns to normal recovery flow — the Gate rule
            # above will no longer block it, since the promise's grace
            # period has passed.
            audit_log_service.write_note(episode, note=f"ptp_broken:{ptp.promised_date}")
        db_session.commit()
```

## Edge cases worth testing explicitly

| Case | Expected behavior |
|---|---|
| Low-confidence date extraction | Discarded, falls back to normal recovery flow |
| Customer makes a promise, then pays early | `PromiseToPay.status='kept'`, episode resolves normally |
| Promise date passes, still unpaid | Status flips to `'broken'`, Gate rule no longer applies, recovery resumes |
| Customer makes a second promise before the first resolves | Only one `active` PTP per episode — reject or supersede the prior one explicitly, don't silently allow two simultaneous freezes |

## What to say in the demo

*"For B2B invoices, blind automated nudges are the wrong tool once a
customer has made a real commitment. When a reply contains a clear date —
extracted with a conservative confidence threshold, never guessed — the
Gate freezes all automated action until that date plus a grace period. If
the promise is broken, recovery resumes automatically. This is the
Promise-to-Pay direction named directly in the track brief, not something
we added speculatively."*
