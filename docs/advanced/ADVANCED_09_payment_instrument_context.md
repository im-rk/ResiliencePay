# Advanced Feature 9 — Payment-Instrument Context in the Bandit

**Effort:** ~2-3 hours — the cheapest addition on this entire list
**Builds on:** Phase 5 (bandit context bucketing)
**Demo impact:** Moderate, but very cheap — worth doing for the domain-depth signal alone

---

## The gap this closes

Your context bucket currently combines `cause_category`, `amount_bucket`,
`customer_segment`, and `retry_count`. It has no dimension for **which
payment instrument failed** — but a UPI Autopay mandate failure and a
credit card decline are genuinely different situations requiring
different recovery logic, even when the raw cause category
(`insufficient_funds`, say) is nominally the same. A UPI mandate failure
often needs the customer to simply re-authorize in their banking app; a
card decline might need a card-update link entirely. Your data model
already has `payment_method` on the `events` table (from Phase 1) — it's
just not currently used as a bandit feature.

## The addition

### `services/decide/context.py` update

```python
INSTRUMENT_ARM_AFFINITY_HINT = {
    # Used only to seed informed priors (Phase 5 section 2.6), never to
    # hardcode a mapping the bandit is prevented from overriding —
    # the bandit remains free to learn otherwise from real outcomes.
    "upi_autopay": {"send_nudge_hinglish": (3.0, 1.5), "send_nudge_english": (3.0, 1.5)},
    "card": {"send_card_update_link": (3.0, 1.5), "retry_short_delay": (2.5, 2.0)},
    "netbanking": {"retry_short_delay": (2.5, 2.0)},
}


def context_bucket_for(event, diagnosis) -> str:
    amount_bucket = bucket_amount(event.amount)
    retry_bucket = min(event.retry_count_so_far, RETRY_COUNT_CAP_FOR_BUCKETING)
    instrument = event.payment_method or "unknown"
    return f"{diagnosis.cause_category}|{amount_bucket}|{event.customer_segment}|{retry_bucket}|{instrument}"
```

**Deliberately kept as a prior-seeding hint, not a hardcoded rule** — this
preserves the exact architectural principle from `SOLUTION.md` section 3:
the *taxonomy* (which instruments exist) is fixed, but *which action fits
which instrument* remains something the bandit discovers from real
outcomes, just starting from a sensible, domain-informed prior rather than
a blank one.

## The cardinality trade-off, stated honestly

Adding a fifth dimension to the context bucket increases the total number
of distinct buckets — revisit `PHASE_05_decide_DETAILED.md` section 3.2's
warning about bucket cardinality diluting your 200-event batch's ability
to show visible convergence. **Mitigation:** collapse `payment_method`
into 3 coarse categories (`upi`, `card`, `other`) rather than every raw
value, keeping cardinality bounded. If your learning curve flattens after
adding this dimension, this collapse is the first thing to check, per the
same tuning guidance already established for `amount_bucket` and `customer_segment`.

## Test to write

```python
def test_context_bucket_includes_instrument_dimension():
    event = make_event(payment_method="upi_autopay")
    bucket = context_bucket_for(event, make_diagnosis("insufficient_funds"))
    assert "upi" in bucket.lower() or "upi_autopay" in bucket

def test_different_instruments_produce_different_buckets_for_same_cause():
    upi_event = make_event(payment_method="upi_autopay")
    card_event = make_event(payment_method="card")
    diagnosis = make_diagnosis("insufficient_funds")
    assert context_bucket_for(upi_event, diagnosis) != context_bucket_for(card_event, diagnosis)
```

## What to say in the demo

*"The same failure cause means different things depending on the payment
instrument — a UPI mandate failure and a card decline aren't the same
problem even when both say 'insufficient funds.' We added instrument type
as a context dimension, seeded with a domain-informed prior, but the
bandit remains free to learn a different mapping from real outcomes if
that's what the data shows."*
