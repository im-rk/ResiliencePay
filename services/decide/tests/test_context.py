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

def test_retry_count_capping():
    fake_event = MagicMock()
    fake_event.amount = 50000
    fake_event.customer_segment = "new"
    
    fake_diagnosis = MagicMock()
    fake_diagnosis.cause_category = "insufficient_funds"

    fake_event.retry_count_so_far = 3
    b1 = context_bucket_for(fake_event, fake_diagnosis)
    
    fake_event.retry_count_so_far = 10
    b2 = context_bucket_for(fake_event, fake_diagnosis)
    
    assert b1 == b2, "retry counts beyond the cap must collapse into the same bucket"
