AMOUNT_BUCKETS = [
    (0, 50_000, "low"),
    (50_000, 200_000, "medium"),
    (200_000, 1_000_000, "high"),
    (1_000_000, None, "very_high"),
]

def bucket_amount(amount_paise: int) -> str:
    for lo, hi, label in AMOUNT_BUCKETS:
        if amount_paise >= lo and (hi is None or amount_paise < hi):
            return label
    return "medium"

RETRY_COUNT_CAP_FOR_BUCKETING = 3  # collapse retry_count 3+ into one bucket

def context_bucket_for(event, diagnosis) -> str:
    amount = getattr(event, "amount", None)
    if amount is None and hasattr(event, "episode") and event.episode:
        amount = event.episode.original_amount
    amount_bucket = bucket_amount(amount if amount is not None else 100_000)
    
    cause = getattr(diagnosis, "cause_category", "unknown")
    cause_val = cause.value if hasattr(cause, "value") else str(cause)
    
    return f"{cause_val}|{amount_bucket}"
