from collections import Counter
from data.generator import generate_batch, CAUSE_DISTRIBUTION

def test_distribution_conformance():
    """
    Test that generated causes match the target CAUSE_DISTRIBUTION
    within an acceptable tolerance (e.g. 2% absolute difference) for n=10,000.
    """
    seed = 123
    n = 10000
    merchant_id = "test_merchant"
    
    batch = generate_batch(seed, n, merchant_id)
    
    assert len(batch) == n
    
    counts = Counter([draft["cause_category"] for draft in batch])
    
    for cause, target_prob in CAUSE_DISTRIBUTION.items():
        actual_prob = counts.get(cause, 0) / n
        
        # Check that it's within a 2% absolute tolerance window
        assert abs(actual_prob - target_prob) < 0.02, (
            f"Cause '{cause}' deviated too much: "
            f"expected {target_prob}, got {actual_prob}"
        )
