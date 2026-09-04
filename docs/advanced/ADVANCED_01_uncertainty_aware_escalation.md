# Advanced Feature 1 — Uncertainty-Aware Escalation

**Effort:** ~half a day
**Builds on:** Phase 5 (bandit), Phase 4 (Gate)
**Demo impact:** High — directly visible in the audit trail and easy to explain in 30 seconds

---

## The gap this closes

Right now, the bandit picks the arm with the highest *sampled* score from
Thompson Sampling — a single draw from each arm's Beta distribution. This
is correct for the exploration/exploitation trade-off, but it throws away
information the moment a decision is made: **how confident was the system
in that choice?** A context bucket with `Beta(50, 10)` (lots of evidence,
tight distribution) and one with `Beta(2, 1)` (almost no evidence, wide
distribution) can produce the same sampled score, but they represent
completely different levels of trustworthiness.

Real decision-theoretic systems — and any serious production ML system
making financial decisions — explicitly reason about **uncertainty, not
just expected value.** This is the single most common gap in
hackathon-grade "AI agent" projects, and it's cheap to close given your
existing architecture.

## The addition

Compute the **variance** of each arm's Beta distribution alongside its
mean, and use both together to decide not just *which arm*, but *whether
to trust the automated choice at all* for this specific decision:

```
variance of Beta(alpha, beta) = (alpha * beta) / ((alpha + beta)^2 * (alpha + beta + 1))
```

High variance + high stakes (large `amount`) → escalate to human review
instead of acting automatically, **even if the sampled score looks
favorable** — because a favorable sample drawn from a wide, uncertain
distribution is not the same kind of evidence as a favorable sample drawn
from a narrow, well-established one.

## Implementation

### `services/decide/uncertainty.py`

```python
def beta_variance(alpha: float, beta: float) -> float:
    return (alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1))


def beta_confidence_level(alpha: float, beta: float) -> str:
    """Coarse, explainable confidence tiers — not a black-box score.
    Thresholds are illustrative starting points; tune against your actual
    batch data rather than treating these as fixed constants."""
    total_observations = alpha + beta
    if total_observations < 5:
        return "low"       # fewer than ~5 effective observations for this (context, arm) pair
    elif total_observations < 20:
        return "medium"
    return "high"
```

### Wiring into the decision pipeline — `services/decide/bandit.py` addition

```python
@dataclass(frozen=True)
class ArmChoice:
    arm: str
    sampled_score: float
    alpha_at_decision: float
    beta_at_decision: float
    confidence_level: str  # NEW — "low" | "medium" | "high"
    variance_at_decision: float  # NEW


def sample_arm(self, context_bucket: str) -> ArmChoice:
    best: ArmChoice | None = None
    for arm in ARMS:
        alpha, beta = self.store.get_stats(context_bucket, arm)
        score = float(np.random.beta(alpha, beta))
        if best is None or score > best.sampled_score:
            best = ArmChoice(
                arm=arm, sampled_score=score,
                alpha_at_decision=alpha, beta_at_decision=beta,
                confidence_level=beta_confidence_level(alpha, beta),
                variance_at_decision=beta_variance(alpha, beta),
            )
    return best
```

### A new Gate rule — `services/gate/rules.py` addition

```python
def check_uncertainty_escalation(choice: "ArmChoice", amount: int,
                                   high_stakes_threshold_paise: int = 500_000) -> "RuleResult":
    """Not a compliance rule in the legal sense — a risk-management rule.
    Kept in the Gate layer anyway because it's the same category of
    decision: 'should this automated action actually execute,'
    deterministically evaluated, independent of the bandit's own
    confidence in itself being sufficient justification."""
    if choice.confidence_level == "low" and amount >= high_stakes_threshold_paise:
        return ("blocked", "escalated_low_confidence_high_stakes")
    return "pass"
```

Add this to `RULE_CHAIN` in `PHASE_04_gate_DETAILED.md`'s rule ordering —
after the legal/compliance rules (opt-out, max attempts, cool-off, time
window), since those take absolute priority, but before the action executes.

## Why this is architecturally correct, not just an add-on

This keeps the separation of concerns from `SOLUTION.md` section 3 intact:
the bandit still only produces a recommendation; a deterministic rule
(now informed by, but not controlled by, the bandit's self-reported
uncertainty) still makes the final bounded decision. The bandit is not
"trusted more" because it says it's confident — the Gate independently
checks whether that confidence, combined with the stakes involved, meets a
fixed bar.

## Dashboard addition (Phase 10)

Add a "Confidence" column to `AuditTrailTable`, and a distinct visual
treatment (e.g., a small icon or badge) for `escalated_low_confidence_high_stakes`
rows — this is a genuinely compelling thing to point at live: "here's a
case where the system recognized its own uncertainty and routed to a
human instead of guessing."

## Test to write

```python
def test_low_confidence_high_stakes_escalates_regardless_of_sampled_score():
    choice = ArmChoice(arm="retry_immediate", sampled_score=0.95,  # a HIGH sampled score
                        alpha_at_decision=1.0, beta_at_decision=1.0,  # but almost no evidence
                        confidence_level="low", variance_at_decision=0.08)
    result = check_uncertainty_escalation(choice, amount=1_000_000)
    assert result == ("blocked", "escalated_low_confidence_high_stakes"), (
        "a favorable sampled score from a near-uniform, low-evidence distribution "
        "must not be treated the same as a favorable score from a well-established one"
    )
```

## What to say in the demo

*"The bandit doesn't just report which action it thinks is best — it
reports how confident it is, based on how many real observations back that
belief. For a high-value payment where we've barely seen this situation
before, we escalate to a human instead of trusting a single lucky sample —
that's a deliberate, testable rule, not something we hope the model
figures out on its own."*
