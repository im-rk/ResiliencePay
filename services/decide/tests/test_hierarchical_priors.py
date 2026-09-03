from services.decide.hierarchical_priors import blend_priors

def test_new_merchant_relies_fully_on_global_pool():
    blended = blend_priors(
        global_alpha=8.0, global_beta=2.0,
        merchant_alpha=1.0, merchant_beta=1.0,  
        merchant_observation_count=0.0
    )
    assert blended.global_weight == 1.0
    assert (blended.alpha, blended.beta) == (8.0, 2.0)

def test_established_merchant_relies_mostly_on_own_data():
    blended = blend_priors(
        global_alpha=8.0, global_beta=2.0,
        merchant_alpha=40.0, merchant_beta=5.0,
        merchant_observation_count=43.0, 
        full_trust_threshold=30.0
    )
    assert blended.global_weight < 0.1
    # Very close to merchant values
    assert abs(blended.alpha - 40.0) < 0.1
