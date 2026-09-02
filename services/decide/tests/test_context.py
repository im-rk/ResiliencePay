from services.decide.context import bucket_amount, context_bucket_for
from unittest.mock import MagicMock

def test_bucket_amount_boundaries():
    assert bucket_amount(0) == "low"
    assert bucket_amount(49_999) == "low"
    assert bucket_amount(50_000) == "medium"          # boundary case
    assert bucket_amount(199_999) == "medium"
    assert bucket_amount(200_000) == "high"           # boundary case
    assert bucket_amount(999_999) == "high"
    assert bucket_amount(1_000_000) == "very_high"    # boundary case
    assert bucket_amount(50_000_000) == "very_high"

def make_event(**kwargs):
    event = MagicMock()
    event.amount = kwargs.get("amount", 50000)
    event.customer_segment = kwargs.get("customer_segment", "new")
    event.retry_count_so_far = kwargs.get("retry_count_so_far", 0)
    event.payment_method = kwargs.get("payment_method", "unknown")
    event.episode = None
    return event

def make_diagnosis(cause="insufficient_funds"):
    diag = MagicMock()
    diag.cause_category = cause
    return diag

def test_retry_count_capping():
    fake_event = make_event(retry_count_so_far=3)
    fake_diagnosis = make_diagnosis("insufficient_funds")

    b1 = context_bucket_for(fake_event, fake_diagnosis)
    
    fake_event.retry_count_so_far = 10
    b2 = context_bucket_for(fake_event, fake_diagnosis)
    
    assert b1 == b2, "retry counts beyond the cap must collapse into the same bucket"

def test_context_bucket_includes_instrument_dimension():
    event = make_event(payment_method="upi_autopay")
    bucket = context_bucket_for(event, make_diagnosis("insufficient_funds"))
    assert "upi" in bucket.lower() or "upi_autopay" in bucket

def test_different_instruments_produce_different_buckets_for_same_cause():
    upi_event = make_event(payment_method="upi_autopay")
    card_event = make_event(payment_method="card")
    diagnosis = make_diagnosis("insufficient_funds")
    assert context_bucket_for(upi_event, diagnosis) != context_bucket_for(card_event, diagnosis)
