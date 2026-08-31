import pytest
from eval.off_policy_evaluation import evaluate_off_policy

class DummyBandit:
    def __init__(self, stats):
        self.stats = stats
        
    def get_stats(self, context_bucket):
        # Fallback to neutral priors for arms not in stats
        arms = [
            "retry_immediate", "retry_short_delay", "retry_long_delay",
            "send_card_update_link", "send_nudge_hinglish", "send_nudge_english",
            "escalate_human", "stop"
        ]
        res = {a: (1.0, 1.0) for a in arms}
        res.update(self.stats)
        return res

def test_ope_returns_low_ess_when_policies_diverge_heavily():
    """A logging policy that never chooses the arms the new policy wants
    should produce a low effective sample size."""
    historical_log = [{"context_bucket": "otp_failure|low|new|0", "chosen_arm": "retry_immediate", "reward": 1.0}] * 50
    
    bandit_favoring_different_arm = DummyBandit({
        "send_nudge_english": (100.0, 1.0),
        "retry_immediate": (1.0, 100.0) # very low chance of choosing retry_immediate
    })
    
    result = evaluate_off_policy(historical_log, bandit_favoring_different_arm)
    assert result.effective_sample_size < 10  # meaningfully lower than the 50 raw records
