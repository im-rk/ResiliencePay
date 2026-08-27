from eval.multi_seed_runner import run_multi_seed_comparison

def test_bandit_beats_baseline_consistently_across_seeds():
    """Bandit policy must achieve positive lift and beat naive baseline across seeds."""
    result = run_multi_seed_comparison(db_session=None, seeds=[10, 42, 99], n=200)

    assert result["consistent_direction"] is True, (
        f"Bandit did not consistently beat baseline across seeds: {result}"
    )
    assert result["lift_mean"] > 0, f"Expected positive lift mean, got {result['lift_mean']}"
    assert result["bandit_mean"] > result["baseline_mean"]
