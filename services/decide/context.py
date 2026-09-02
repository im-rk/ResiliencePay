AMOUNT_BUCKETS = [
    (0, 50_000, "low"),
    (50_000, 200_000, "medium"),
    (200_000, 1_000_000, "high"),
    (1_000_000, None, "very_high"),
]

INSTRUMENT_ARM_AFFINITY_HINT = {
    # Used only to seed informed priors (Phase 5 section 2.6), never to
    # hardcode a mapping the bandit is prevented from overriding —
    # the bandit remains free to learn otherwise from real outcomes.
    "upi_autopay": {"send_nudge_hinglish": (3.0, 1.5), "send_nudge_english": (3.0, 1.5)},
    "card": {"send_card_update_link": (3.0, 1.5), "retry_short_delay": (2.5, 2.0)},
    "netbanking": {"retry_short_delay": (2.5, 2.0)},
}

def bucket_amount(amount_paise: int) -> str:
    for lo, hi, label in AMOUNT_BUCKETS:
        if amount_paise >= lo and (hi is None or amount_paise < hi):
            return label
    return "medium"

RETRY_COUNT_CAP_FOR_BUCKETING = 3  # collapse retry_count 3+ into one bucket

def context_bucket_for(event, diagnosis) -> str:
    amount = getattr(event, "amount", None)
    if amount is None and hasattr(event, "episode") and getattr(event, "episode", None):
        amount = getattr(event.episode, "original_amount", 100_000)
    amount_bucket = bucket_amount(amount if amount is not None else 100_000)
    
    cause = getattr(diagnosis, "cause_category", "unknown")
    cause_val = cause.value if hasattr(cause, "value") else str(cause)

    # Retry bucket
    retry_count = getattr(event, "retry_count_so_far", 0)
    retry_bucket = min(retry_count, RETRY_COUNT_CAP_FOR_BUCKETING)

    # Customer Segment
    customer_segment = getattr(event, "customer_segment", None)
    if not customer_segment and hasattr(event, "episode") and getattr(event, "episode", None):
        if hasattr(event.episode, "customer") and getattr(event.episode.customer, "segment", None):
            customer_segment = event.episode.customer.segment
    customer_segment = customer_segment or "unknown"
    
    # Instrument bucket (coarse)
    instrument_raw = getattr(event, "payment_method", None) or "unknown"
    instrument_lower = instrument_raw.lower()
    if "upi" in instrument_lower:
        instrument = "upi"
    elif "card" in instrument_lower:
        instrument = "card"
    else:
        instrument = "other"
    
    return f"{cause_val}|{amount_bucket}|{customer_segment}|{retry_bucket}|{instrument}"
