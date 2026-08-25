import pytest
from data.generator import generate_batch

def test_reproducibility():
    """Same seed should yield byte-identical output."""
    seed = 42
    n = 100
    merchant_id = "test_merchant"
    
    batch_1 = generate_batch(seed, n, merchant_id)
    batch_2 = generate_batch(seed, n, merchant_id)
    
    assert batch_1 == batch_2, "Outputs for the same seed differ!"

def test_different_seeds():
    """Different seeds should yield different outputs."""
    merchant_id = "test_merchant"
    batch_1 = generate_batch(42, 100, merchant_id)
    batch_2 = generate_batch(43, 100, merchant_id)
    
    assert batch_1 != batch_2, "Outputs for different seeds were identical!"
