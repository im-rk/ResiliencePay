# Phase 5 — Decide (Contextual Bandit) — Full Detailed Spec

**Depends on:** Phase 3 (diagnosis for context), Phase 4 (the compliance boundary this must respect)
**Unblocks:** Phase 6 (Act consumes the chosen arm), Phase 8 (batch harness swaps this policy for baseline)
**Owner:** ML-strongest team member
**Estimated time:** ~1–1.5 days — this is your novelty core, budget the most careful time here

---

## 1. Why this phase exists and why it matters more than it looks

Every other phase in this project is "solid engineering." This phase is
the one genuine ML artifact in the system, and it's the difference between
"we built a rule table that retries payments" (what most Track 03 teams
will submit) and "we built a system that provably gets better at recovering
revenue the more it runs" (what you're submitting).

The bar you're clearing here is not "does the bandit algorithm run
correctly" — Thompson Sampling is a 30-year-old, extremely well-understood
technique, and getting the math right is not the hard part. The hard part,
and the part that actually earns engineering respect, is everything around
the algorithm:

- Making the decision **explainable** (you can show a judge the exact α/β
  values and sampled score behind any specific choice).
- Making the decision **safe to compute concurrently** (multiple events
  being processed by parallel workers must not corrupt shared state).
- Making the decision **durable** (a Redis restart mid-demo shouldn't erase
  everything the bandit learned).
- Making the decision **auditable after the fact** (every decision this
  phase makes must be reconstructable from the `decisions` table alone).

If you get the algorithm right but skip these four properties, you've built
a Jupyter notebook, not a production decision system. This phase spec is
written to make sure you build the latter.

---

## 2. Conceptual model — read this before touching code

### 2.1 What a "contextual bandit" actually is, in plain terms

Imagine you have 8 possible actions (the "arms") you could take in response
to a failed payment. You don't know in advance which action works best for
which kind of failure — but every time you take an action, you find out
(eventually) whether it worked. A contextual bandit is a policy that:

1. Groups similar situations together (the "context" — e.g., "insufficient
   funds, medium amount, returning customer, first attempt").
2. For each such situation, keeps a running belief about how well each arm
   performs *specifically in that situation*.
3. Chooses actions that balance **exploiting** what it already believes
   works well against **exploring** arms it's less certain about — so it
   doesn't get stuck on an early lucky/unlucky result.

Thompson Sampling implements the explore/exploit balance elegantly: for
each arm, it maintains a Beta probability distribution representing "how
confident am I that this arm succeeds, and how sure am I of that
confidence." It draws one random sample from each arm's distribution and
picks whichever arm's sample came out highest. Early on, when you're
unsure, the distributions are wide and sampling is nearly random
(exploration). As evidence accumulates, the distributions narrow around the
true success rate, and sampling converges to reliably picking the best arm
(exploitation) — automatically, with no manually-tuned schedule.

### 2.2 Why Beta distributions specifically

A Beta(α, β) distribution is the natural way to represent "belief about a
success probability" when your evidence is a sequence of successes and
failures. Starting at Beta(1,1) (uniform — "I have no idea"), every
observed success increments α by 1, every observed failure increments β by
1. After enough observations, Beta(α, β) tightly clusters around
α / (α + β), which is just the observed success rate — but critically, it
also encodes *how many* observations that estimate is based on: Beta(8, 2)
and Beta(80, 20) both center around 80%, but the second is far more
confident, and Thompson Sampling correctly draws tighter, more reliable
samples from it.

### 2.3 What "context bucket" means concretely here

You cannot maintain one global Beta distribution per arm — that would mean
the bandit can't tell the difference between "insufficient funds" and
"expired card," which defeats the purpose. Instead, you maintain a
**separate Beta(α, β) per (context bucket, arm) pair**. The context bucket
is a coarse-grained key like:

```
insufficient_funds|amount_medium|returning_high_value|attempt_1
```

"Coarse-grained" is doing real work in that sentence — see §3.2 below for
exactly why and how to bucket amounts instead of using raw values.

---

## 3. Detailed component design

### 3.1 `services/decide/bandit.py`

```python
from typing import Protocol
import numpy as np

class BanditPolicy(Protocol):
    """Structural interface shared by the real bandit and the baseline
    policy (Phase 8). Any code that depends on 'a policy' should type-hint
    against THIS, never against ThompsonSamplingBandit directly — this is
    what makes swapping policies in eval/run_batch.py a zero-branching
    operation."""

    def sample_arm(self, context_bucket: str) -> "ArmChoice": ...
    def update(self, context_bucket: str, arm: str, reward: float) -> None: ...
    def get_stats(self, context_bucket: str) -> dict[str, tuple[float, float]]: ...


from dataclasses import dataclass

@dataclass(frozen=True)
class ArmChoice:
    """Return type for sample_arm — deliberately richer than a bare string
    so the decision's explainability data travels with it, rather than
    needing a second lookup at write time."""
    arm: str
    sampled_score: float
    alpha_at_decision: float
    beta_at_decision: float


ARMS = [
    "retry_immediate", "retry_short_delay", "retry_long_delay",
    "send_card_update_link", "send_nudge_hinglish", "send_nudge_english",
    "escalate_human", "stop",
]

# Informed priors — see §3.4. Loaded once at import time from a seed table
# (packages/domain-constants/bandit_priors.py), not hardcoded inline, so
# priors can be tuned without touching this file.
from packages.domain_constants.bandit_priors import DEFAULT_PRIORS


class ThompsonSamplingBandit:
    def __init__(self, store: "RedisArmStatsStore"):
        self.store = store

    def sample_arm(self, context_bucket: str) -> ArmChoice:
        best: ArmChoice | None = None
        for arm in ARMS:
            alpha, beta = self.store.get_stats(context_bucket, arm)
            score = float(np.random.beta(alpha, beta))
            if best is None or score > best.sampled_score:
                best = ArmChoice(arm=arm, sampled_score=score,
                                  alpha_at_decision=alpha, beta_at_decision=beta)
        assert best is not None  # ARMS is never empty — defensive, not reachable
        return best

    def update(self, context_bucket: str, arm: str, reward: float) -> None:
        if not (0.0 <= reward <= 1.0 or reward == -0.1):
            raise ValueError(f"reward {reward} outside valid range; validate before calling update()")
        success_increment = max(reward, 0.0)
        failure_increment = 1.0 - success_increment if reward >= 0 else 0.0
        # A -0.1 penalty (gate-blocked-but-attempted case, see ML_DESIGN.md §2.5)
        # is handled as a pure beta-side nudge without a full failure increment,
        # since it represents a POLICY violation risk, not an observed recovery failure.
        if reward == -0.1:
            self.store.increment_beta(context_bucket, arm, 0.1)
            return
        self.store.increment_alpha(context_bucket, arm, success_increment)
        self.store.increment_beta(context_bucket, arm, failure_increment)

    def get_stats(self, context_bucket: str) -> dict[str, tuple[float, float]]:
        return {arm: self.store.get_stats(context_bucket, arm) for arm in ARMS}
```

**Important design note to preserve in code comments:** the `-0.1` reward
case is handled distinctly from a normal 0.0 failure — a gate-blocked
attempt reflects the *policy* proposing something disallowed, which is
useful signal to discourage that arm in that context, but it is not the
same statistical event as "we tried and the customer didn't pay." Conflating
them would corrupt your success-rate estimates. Keep this branch and its
comment intact; a reviewer (or judge) who reads this code should see that
you thought about this distinction deliberately.

### 3.2 `services/decide/context.py`

```python
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
```

**Why bucket instead of using raw values:** with 8 cause categories × 4
amount buckets × 4 segments × 4 retry-count buckets, you already have 512
possible context buckets. A 200-event batch spreads thin across even that —
using raw continuous amounts instead of 4 buckets would explode cardinality
and mean almost every context bucket sees 0 or 1 observations, and the
bandit would never visibly converge within your demo batch size. This is
the single most important tuning knob if your learning curve looks flat in
testing — reduce bucket cardinality further (e.g., merge `customer_segment`
into 2 categories instead of 4) rather than increasing batch size past
what's demo-realistic.

### 3.3 `services/decide/redis_store.py`

```python
import redis

class RedisArmStatsStore:
    def __init__(self, client: redis.Redis, default_priors: dict[str, tuple[float, float]]):
        self.client = client
        self.default_priors = default_priors  # {arm: (alpha, beta)}

    def _key(self, context_bucket: str, arm: str) -> str:
        return f"bandit:{context_bucket}:{arm}"

    def get_stats(self, context_bucket: str, arm: str) -> tuple[float, float]:
        key = self._key(context_bucket, arm)
        raw = self.client.hgetall(key)
        if not raw:
            alpha, beta = self.default_priors.get(arm, (1.0, 1.0))
            # Lazily materialize the prior into Redis on first access so
            # subsequent HINCRBYFLOAT calls have a base to increment from.
            self.client.hset(key, mapping={"alpha": alpha, "beta": beta})
            return alpha, beta
        return float(raw[b"alpha"]), float(raw[b"beta"])

    def increment_alpha(self, context_bucket: str, arm: str, amount: float) -> None:
        if amount == 0:
            return
        self.client.hincrbyfloat(self._key(context_bucket, arm), "alpha", amount)

    def increment_beta(self, context_bucket: str, arm: str, amount: float) -> None:
        if amount == 0:
            return
        self.client.hincrbyfloat(self._key(context_bucket, arm), "beta", amount)
```

**Concurrency note:** `HINCRBYFLOAT` is atomic at the Redis level — this is
what makes the concurrency test in §5 pass without any application-level
locking. Do not "simplify" this into a `GET` then `SET` pattern; that
reintroduces the exact race condition this design avoids.

**Failure mode note:** if `self.client` raises (Redis unreachable), let it
propagate. Do not wrap this in a `try/except` that falls back to a random
arm — per the edge-case matrix, a broken hot-path store must stop the
pipeline loudly, not silently corrupt learning.

### 3.4 Informed priors — `packages/domain-constants/bandit_priors.py`

```python
# Seeded from domain intuition per ML_DESIGN.md §2.6. These are STARTING
# points, not claims about real-world performance — document this clearly
# if asked. Format: {arm: (alpha, beta)}. Higher alpha relative to beta =
# more optimistic prior.
DEFAULT_PRIORS: dict[str, tuple[float, float]] = {
    "retry_immediate":       (2.0, 2.0),   # neutral — situational
    "retry_short_delay":     (2.0, 2.0),
    "retry_long_delay":      (3.0, 2.0),   # slightly favored for funds-timing cases
    "send_card_update_link": (2.0, 2.0),
    "send_nudge_hinglish":   (2.0, 3.0),   # slightly conservative until proven
    "send_nudge_english":    (2.0, 3.0),
    "escalate_human":        (1.0, 4.0),   # expensive — bandit should need real evidence to favor this
    "stop":                  (1.0, 1.0),   # neutral — always safe, no reward upside to learn
}

# Optional: per-cause-category overrides, applied at context_bucket
# construction time rather than baked into RedisArmStatsStore, so the prior
# logic stays testable independent of Redis.
CAUSE_SPECIFIC_OVERRIDES: dict[str, dict[str, tuple[float, float]]] = {
    "otp_failure": {"retry_immediate": (4.0, 1.0)},          # OTP retries recover fast, favor strongly
    "insufficient_funds": {"retry_long_delay": (4.0, 1.5)},  # payday timing intuition
    "hard_decline": {"escalate_human": (1.5, 3.0), "stop": (2.0, 1.0)},  # lean toward stopping
}
```

### 3.5 `services/decide/snapshot.py`

```python
def snapshot_bandit_state_to_postgres(store: RedisArmStatsStore, db_session) -> int:
    """Invoked periodically by apps/worker (Celery beat). Scans all
    bandit:* keys in Redis and upserts them into bandit_arm_stats. Returns
    the number of rows written, for logging/observability."""
    count = 0
    for key in store.client.scan_iter(match="bandit:*"):
        _, context_bucket, arm = key.decode().split(":", 2)
        raw = store.client.hgetall(key)
        alpha, beta = float(raw[b"alpha"]), float(raw[b"beta"])
        upsert_bandit_arm_stats(db_session, context_bucket, arm, alpha, beta)
        count += 1
    db_session.commit()
    return count
```

### 3.6 `services/decide/baseline_policy.py`

```python
class BaselinePolicy:
    """No-learning policy — always retries immediately, once. Satisfies the
    same BanditPolicy Protocol so eval/run_batch.py can inject either policy
    with zero branching. Deliberately trivial: it represents 'what merchants
    do today,' not a strawman."""

    def sample_arm(self, context_bucket: str) -> ArmChoice:
        return ArmChoice(arm="retry_immediate", sampled_score=1.0,
                          alpha_at_decision=1.0, beta_at_decision=1.0)

    def update(self, context_bucket: str, arm: str, reward: float) -> None:
        pass  # no learning, by design

    def get_stats(self, context_bucket: str) -> dict[str, tuple[float, float]]:
        return {}
```

---

## 4. Full edge-case matrix (expanded)

| # | Case | Expected behavior | How to test |
|---|---|---|---|
| 1 | Brand-new `context_bucket`, never seen | Falls back to seeded default/override prior, materializes it in Redis, does not crash | Unit test: fresh Redis, call `get_stats` on an unseen bucket, assert returned values match `DEFAULT_PRIORS` |
| 2 | Redis connection refused | `sample_arm`/`update` raise, pipeline halts loudly | Unit test with a mocked client raising `ConnectionError`; assert it propagates, not swallowed |
| 3 | `update()` called with `reward=1.5` | Raises `ValueError` before touching Redis | Unit test asserting no Redis call occurs (mock call count = 0) |
| 4 | `update()` called with `reward=-0.1` | Only β incremented by 0.1, α untouched | Unit test checking exact α/β delta |
| 5 | Context bucket with 1 historical observation | Wide Beta variance, high-variance sampled scores — intentional | Statistical test: sample 1000 times from Beta(2,2) vs Beta(50,10), assert variance is meaningfully higher for the former |
| 6 | Two arms have identical α/β | Either can be chosen — no deterministic bias | Statistical test: over many samples, both arms chosen roughly equally |
| 7 | `amount_paise` exactly on a bucket boundary (e.g., 50,000) | Falls into the upper bucket per the `>=` comparison in `bucket_amount` | Unit test with boundary values exactly at 0, 50000, 200000, 1000000 |
| 8 | `retry_count_so_far` = 10 (way beyond cap) | Collapsed into the same bucket as retry_count=3 | Unit test asserting `context_bucket_for` output is identical for retry_count=3 and retry_count=10 |
| 9 | Snapshot job runs while Redis is being concurrently updated | Snapshot reflects a consistent-enough point-in-time read (Redis single-threaded command execution guarantees this per-key) — no crash, no partial corrupted row | Integration test: fire updates and a snapshot concurrently, assert snapshot completes without error |
| 10 | `BaselinePolicy.update()` called | No-op, no exception, no state change | Unit test |

---

## 5. Test plan — with actual test code to implement

### 5.1 `services/decide/tests/test_convergence.py`

```python
import numpy as np
from services.decide.bandit import ThompsonSamplingBandit
from services.decide.redis_store import RedisArmStatsStore

def test_bandit_converges_to_better_arm(fake_redis):
    store = RedisArmStatsStore(fake_redis, default_priors={"arm_good": (1,1), "arm_bad": (1,1)})
    bandit = ThompsonSamplingBandit(store)
    bandit_arms_module_patch(["arm_good", "arm_bad"])  # patch ARMS for this test

    rng = np.random.default_rng(42)
    selections = {"arm_good": 0, "arm_bad": 0}

    for _ in range(500):
        choice = bandit.sample_arm("test_bucket")
        selections[choice.arm] += 1
        true_success_rate = 0.8 if choice.arm == "arm_good" else 0.2
        reward = 1.0 if rng.random() < true_success_rate else 0.0
        bandit.update("test_bucket", choice.arm, reward)

    # Assert convergence: by the end, arm_good should dominate selections.
    # Use a tolerance-based assertion, not an exact ratio — this is inherently stochastic.
    assert selections["arm_good"] > selections["arm_bad"] * 2, (
        f"expected arm_good to dominate after 500 rounds, got {selections}"
    )
```

### 5.2 `services/decide/tests/test_concurrency.py`

```python
import concurrent.futures
from services.decide.bandit import ThompsonSamplingBandit
from services.decide.redis_store import RedisArmStatsStore

def test_concurrent_updates_no_lost_writes(real_redis_test_instance):
    store = RedisArmStatsStore(real_redis_test_instance, default_priors={"arm": (1.0, 1.0)})
    bandit = ThompsonSamplingBandit(store)

    def do_update():
        bandit.update("concurrent_bucket", "arm", reward=1.0)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(do_update) for _ in range(50)]
        concurrent.futures.wait(futures)

    alpha, beta = store.get_stats("concurrent_bucket", "arm")
    # Started at alpha=1.0, 50 updates each with reward=1.0 -> alpha should be 1.0 + 50 = 51.0
    assert alpha == 51.0, f"expected 51.0 after 50 concurrent updates, got {alpha}"
    assert beta == 1.0  # unchanged, since every reward was a full success
```

**Use a real Redis test instance for this test, not a fake/mock** — the
entire point is validating `HINCRBYFLOAT`'s real atomicity guarantee; a
Python-level fake dict would trivially "pass" this test while hiding a real
race condition. Spin up a Redis test container in CI for this specific test
if your fake-Redis fixture doesn't support true concurrent access.

### 5.3 `services/decide/tests/test_context.py`

```python
from services.decide.context import bucket_amount, context_bucket_for

def test_bucket_amount_boundaries():
    assert bucket_amount(0) == "low"
    assert bucket_amount(49_999) == "low"
    assert bucket_amount(50_000) == "medium"          # boundary case
    assert bucket_amount(199_999) == "medium"
    assert bucket_amount(200_000) == "high"           # boundary case
    assert bucket_amount(999_999) == "high"
    assert bucket_amount(1_000_000) == "very_high"    # boundary case
    assert bucket_amount(50_000_000) == "very_high"

def test_retry_count_capping(fake_event, fake_diagnosis):
    fake_event.retry_count_so_far = 3
    b1 = context_bucket_for(fake_event, fake_diagnosis)
    fake_event.retry_count_so_far = 10
    b2 = context_bucket_for(fake_event, fake_diagnosis)
    assert b1 == b2, "retry counts beyond the cap must collapse into the same bucket"
```

### 5.4 `services/decide/tests/test_reward_validation.py`

```python
import pytest
from services.decide.bandit import ThompsonSamplingBandit

def test_invalid_reward_rejected(bandit_with_fake_store):
    with pytest.raises(ValueError):
        bandit_with_fake_store.update("bucket", "arm", reward=1.5)
    with pytest.raises(ValueError):
        bandit_with_fake_store.update("bucket", "arm", reward=-0.5)  # only -0.1 is a valid negative

def test_gate_blocked_penalty_only_touches_beta(bandit_with_fake_store, fake_store):
    alpha_before, beta_before = fake_store.get_stats("bucket", "arm")
    bandit_with_fake_store.update("bucket", "arm", reward=-0.1)
    alpha_after, beta_after = fake_store.get_stats("bucket", "arm")
    assert alpha_after == alpha_before
    assert beta_after == beta_before + 0.1
```

---

## 6. Observability — what to log at runtime (not just test)

Every call to `sample_arm` should emit a structured log line (via
`structlog`, per `TECH_STACK.md`) containing: `context_bucket`,
`chosen_arm`, `sampled_score`, and the full `get_stats()` snapshot for that
bucket at decision time. This is cheap to add now and is exactly what
you'll want to screenshot or query live if a judge asks "show me why it
chose that." Don't defer this to Phase 9/10 — wire it here, at the source.

---

## 7. Definition of Done (full checklist)

- [ ] `BanditPolicy` Protocol defined and both `ThompsonSamplingBandit` and `BaselinePolicy` satisfy it (verify with `mypy` structural check, not just visual inspection).
- [ ] `context_bucket_for` produces bounded-cardinality keys (verify by computing total possible distinct buckets given your bucket definitions — should be well under 200, ideally under 100, for a 200-event batch to show convergence).
- [ ] Informed priors loaded from `packages/domain-constants/bandit_priors.py`, not hardcoded inline.
- [ ] `test_convergence.py` passes.
- [ ] `test_concurrency.py` passes **against a real Redis instance**, not a fake.
- [ ] `test_context.py` boundary tests pass.
- [ ] `test_reward_validation.py` passes, including the `-0.1` distinct-handling case.
- [ ] Redis-unavailable failure mode verified to raise loudly (test with a mocked client that raises `ConnectionError`).
- [ ] Structured logging emits `context_bucket`, `chosen_arm`, `sampled_score`, and full stats snapshot on every `sample_arm` call.
- [ ] `snapshot_bandit_state_to_postgres` tested against a populated fake Redis, writes correct rows to `bandit_arm_stats`.

---

## 8. Prompts for your coding agent

Use these as individual, focused prompts — one per agent session or one
per sub-task within a session. Paste `CLAUDE.md`'s standards apply
automatically if it's in the repo root; these prompts assume that context
is already loaded (see `docs/AGENT_KICKOFF_PROMPT.md` for the general
session-opening template).

### Prompt 1 — Scaffold the module and the Protocol
```
Implement services/decide/bandit.py per docs/phases/PHASE_05_decide_DETAILED.md
section 3.1: define the BanditPolicy Protocol, the ArmChoice dataclass, the
ARMS constant list, and the ThompsonSamplingBandit class with sample_arm()
and update() exactly as specified, including the distinct handling of the
-0.1 gate-blocked reward case (do not collapse it into the normal
success/failure increment logic — keep it as a separate branch with the
comment explaining why). Also implement services/decide/baseline_policy.py
with the trivial BaselinePolicy satisfying the same Protocol. Do not wire
Redis yet — accept a `store` object in the constructor and assume it
already implements get_stats/increment_alpha/increment_beta; I'll ask for
that in the next step. Write services/decide/tests/test_reward_validation.py
covering the edge cases in section 4, rows 3 and 4 of this doc's edge-case
matrix, using a simple in-memory fake store for these tests.
```

### Prompt 2 — Redis-backed hot state
```
Implement services/decide/redis_store.py per docs/phases/PHASE_05_decide_DETAILED.md
section 3.3: RedisArmStatsStore with get_stats (lazily materializing the
default prior on first access), increment_alpha, and increment_beta, using
HINCRBYFLOAT for atomic updates — do not implement this as a read-modify-write
pattern under any circumstance, that reintroduces the race condition this
design exists to avoid. If the underlying Redis client raises, let the
exception propagate uncaught; do not add a try/except fallback to a default
value. Write services/decide/tests/test_concurrency.py exactly as specified
in section 5.2 of the doc, using a real Redis test instance (spin one up via
testcontainers or the project's existing Redis test fixture — check
apps/api/tests/conftest.py for an existing pattern before creating a new one).
```

### Prompt 3 — Context bucketing
```
Implement services/decide/context.py per docs/phases/PHASE_05_decide_DETAILED.md
section 3.2: the AMOUNT_BUCKETS table, bucket_amount(), and
context_bucket_for(). Pay careful attention to the boundary semantics
(>= lower bound, < upper bound) and the retry_count capping logic. Write
services/decide/tests/test_context.py covering every boundary case listed
in section 5.3 of the doc, including the retry_count capping test.
```

### Prompt 4 — Informed priors and cause-specific overrides
```
Create packages/domain-constants/bandit_priors.py per section 3.4 of
docs/phases/PHASE_05_decide_DETAILED.md, with DEFAULT_PRIORS and
CAUSE_SPECIFIC_OVERRIDES exactly as specified. Then wire context_bucket_for
or a new helper (your choice, but document which) so that when a bandit
looks up priors for a bucket whose cause_category has an entry in
CAUSE_SPECIFIC_OVERRIDES, the override takes precedence over DEFAULT_PRIORS
for that specific arm, falling back to DEFAULT_PRIORS for any arm not
listed in the override. Write a unit test proving both the override and the
fallback-to-default paths.
```

### Prompt 5 — Convergence proof
```
Implement services/decide/tests/test_convergence.py exactly per section 5.1
of docs/phases/PHASE_05_decide_DETAILED.md: simulate 500 rounds against a
bandit with two arms of true success rates 80% and 20%, and assert the
bandit's selection ratio favors the better arm by the end. Use a fixed
random seed for reproducibility. If the test is flaky across reruns with
different seeds, don't loosen the assertion threshold blindly — first check
whether the priors or bucket cardinality are the actual problem, per the
tuning note in section 3.2 of the doc, and report back what you find before
changing the test.
```

### Prompt 6 — Postgres durability snapshot
```
Implement services/decide/snapshot.py per section 3.5 of
docs/phases/PHASE_05_decide_DETAILED.md: snapshot_bandit_state_to_postgres()
that scans all bandit:* keys in Redis and upserts them into the
bandit_arm_stats table (see packages/db-models/models/bandit_arm_stats.py
from Phase 1 — read that file first to confirm the exact column names and
upsert semantics before writing this). Then wire this as a Celery beat task
in apps/worker/src/tasks/snapshot_bandit_state.py running every 5 minutes.
Write an integration test that seeds fake Redis bandit state, runs the
snapshot function, and asserts the correct rows exist in a test Postgres
database with the correct alpha/beta values.
```

### Prompt 7 — Full integration + explainability logging
```
Wire services/decide/bandit.py, redis_store.py, context.py, and
bandit_priors.py together behind a single factory function
(e.g., get_bandit_policy() in services/decide/__init__.py) that apps/api
and eval/run_batch.py can both import. Add structured logging (structlog)
to sample_arm() per section 6 of docs/phases/PHASE_05_decide_DETAILED.md,
emitting context_bucket, chosen_arm, sampled_score, and the full stats
snapshot for that bucket at decision time. Then run through the full
Definition of Done checklist in section 7 of that doc and report back
which items pass and which don't, with the actual test output — don't just
tell me it's done, show me the checklist filled in.
```
