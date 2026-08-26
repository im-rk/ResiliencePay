AMOUNT_BUCKETS = [(0, 50_000, "low"), (50_000, 200_000, "medium"),
                   (200_000, 1_000_000, "high"), (1_000_000, None, "very_high")]

def bucket_amount(amount_paise: int) -> str:
    for lo, hi, label in AMOUNT_BUCKETS:
        if amount_paise >= lo and (hi is None or amount_paise < hi):
            return label
    raise ValueError(f"amount {amount_paise} did not match any bucket")  # should be unreachable

RETRY_COUNT_CAP_FOR_BUCKETING = 3  # collapse retry_count 3+ into one bucket

def context_bucket_for(event, diagnosis) -> str:
    amount_bucket = bucket_amount(event.amount)
    retry_bucket = min(event.retry_count_so_far, RETRY_COUNT_CAP_FOR_BUCKETING)
    return f"{diagnosis.cause_category}|{amount_bucket}|{event.customer_segment}|{retry_bucket}"
