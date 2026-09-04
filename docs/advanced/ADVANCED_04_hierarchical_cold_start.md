# Advanced Feature 4 — Hierarchical Priors for Cold-Start Merchants

**Effort:** ~1 day
**Builds on:** Phase 5 (bandit)
**Demo impact:** High for judges with ML background; requires clear explanation to land with others — build this last, and only if the core is solid

---

## The gap this closes, and why it's a real, named problem

Your bandit is excellent at improving *within* one merchant's data over
time. But it has an honest weakness worth naming before a judge finds it
for you: **a brand-new merchant, on day one, has zero history for every
context bucket**, and starts from the same generic informed prior as every
other merchant, regardless of how different their business actually is (a
SaaS subscription business and a D2C one-time-purchase business plausibly
have very different recovery dynamics). This is the classic **cold-start
problem**, and hand-waving "the bandit will learn eventually" is not a
satisfying answer for a merchant losing revenue during that entire warm-up
period.

## The real technique: partial pooling / hierarchical Bayesian priors

Instead of treating each merchant's bandit state as fully independent
(no shared learning across merchants) or fully pooled (one global policy,
ignoring merchant differences), a **hierarchical model** does something in
between: it lets a new merchant's priors be informed by a global,
cross-merchant estimate for the same context bucket, weighted by how much
merchant-specific evidence exists. As a specific merchant accumulates their
own data, their policy gradually "trusts itself" more and relies less on
the global pool — this is called partial pooling, and it's the standard
solution to cold-start problems in real hierarchical Bayesian systems
(this exact pattern is used in real ad-tech and recommendation systems for
new advertisers/users with no history).

## Implementation

### Conceptual model

```
Global level:    Beta(alpha_global[cause, arm], beta_global[cause, arm])
                       — pooled across ALL merchants for this context

Merchant level:  Beta(alpha_merchant[merchant, cause, arm], beta_merchant[...])
                       — this specific merchant's own evidence

Effective prior for a NEW merchant = the global distribution
Effective prior as a merchant accumulates data = a weighted blend that
    shifts toward their own merchant-level evidence as it grows
```

### `services/decide/hierarchical_priors.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class BlendedPrior:
    alpha: float
    beta: float
    global_weight: float  # for transparency/logging — how much of this prior came from the global pool


def blend_priors(
    global_alpha: float, global_beta: float,
    merchant_alpha: float, merchant_beta: float,
    merchant_observation_count: float,
    full_trust_threshold: float = 30.0,
) -> BlendedPrior:
    """Simple, explainable linear blending — not a full hierarchical
    Bayesian model (which would require a proper multi-level MCMC or
    variational fit), but a principled, correctly-motivated approximation
    that's honest about being one. State this explicitly if asked — the
    FULL hierarchical model is a legitimate stretch goal beyond this,
    not what's claimed here."""
    global_weight = max(0.0, 1.0 - (merchant_observation_count / full_trust_threshold))
    merchant_weight = 1.0 - global_weight

    blended_alpha = global_weight * global_alpha + merchant_weight * merchant_alpha
    blended_beta = global_weight * global_beta + merchant_weight * merchant_beta

    return BlendedPrior(alpha=blended_alpha, beta=blended_beta, global_weight=global_weight)
```

### Wiring into `RedisArmStatsStore.get_stats`

```python
def get_stats(self, merchant_id: str, context_bucket: str, arm: str) -> tuple[float, float]:
    merchant_key = f"bandit:{merchant_id}:{context_bucket}:{arm}"
    global_key = f"bandit:GLOBAL:{context_bucket}:{arm}"

    merchant_raw = self.client.hgetall(merchant_key)
    global_raw = self.client.hgetall(global_key)
    global_alpha, global_beta = (
        (float(global_raw[b"alpha"]), float(global_raw[b"beta"])) if global_raw
        else self.default_priors.get(arm, (1.0, 1.0))
    )

    if not merchant_raw:
        # Brand-new merchant for this context — use the global pool fully.
        return global_alpha, global_beta

    merchant_alpha, merchant_beta = float(merchant_raw[b"alpha"]), float(merchant_raw[b"beta"])
    merchant_observations = merchant_alpha + merchant_beta - 2.0  # subtract the initial prior's pseudo-count
    blended = blend_priors(global_alpha, global_beta, merchant_alpha, merchant_beta,
                            max(merchant_observations, 0.0))
    return blended.alpha, blended.beta
```

**Update the global pool on every `update()` call too**, in parallel with
the merchant-specific update — every merchant's real outcomes contribute
to the shared, cross-merchant knowledge that helps the *next* new merchant
who signs up.

## Why this is a real, defensible addition and not over-engineering

This directly answers a question a good judge should ask ("what about a
brand-new merchant with no data?") with a named, standard technique rather
than an unconvincing "it'll figure itself out." It's also honest about its
own limits — explicitly calling the linear blend an approximation of a
full hierarchical Bayesian model, not overclaiming statistical rigor you
haven't actually implemented.

## Test to write

```python
def test_new_merchant_relies_fully_on_global_pool():
    blended = blend_priors(global_alpha=8.0, global_beta=2.0,
                            merchant_alpha=1.0, merchant_beta=1.0,  # untouched prior, zero real observations
                            merchant_observation_count=0.0)
    assert blended.global_weight == 1.0
    assert (blended.alpha, blended.beta) == (8.0, 2.0)

def test_established_merchant_relies_mostly_on_own_data():
    blended = blend_priors(global_alpha=8.0, global_beta=2.0,
                            merchant_alpha=40.0, merchant_beta=5.0,  # lots of merchant-specific evidence
                            merchant_observation_count=43.0, full_trust_threshold=30.0)
    assert blended.global_weight < 0.1
```

## What to say in the demo

*"A brand-new merchant with zero history shouldn't start from a blank
slate or from one arbitrary generic guess — we pool evidence across all
merchants for the same failure type, so a new merchant benefits from what
we've already learned globally, and as they accumulate their own data, the
policy smoothly shifts to trust their specific patterns more. This is the
same partial-pooling idea used in real hierarchical Bayesian
recommendation systems for cold-starting new users or advertisers — we're
upfront that our blending function is a simplified, explainable
approximation of the full model, not a claim to have implemented full
hierarchical inference."*
