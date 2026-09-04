# Phase 5 — Decide (Contextual Bandit)

**Depends on:** Phase 3 (diagnosis for context), Phase 4 (the boundary this must respect)
**Unblocks:** Phase 6 (Act consumes chosen arm), Phase 8 (batch harness swaps this policy for baseline)
**Owner:** ML-strongest team member
**Estimated time:** ~1-1.5 days — this is your novelty core, budget the most careful time here

## Objective
A self-improving, fully auditable decision policy that operates strictly
upstream of the Gate. This phase is the single biggest differentiator
against other Track 03 submissions — most teams hardcode this step.

## Scope
**In scope:** bandit algorithm, Redis-backed hot state, Postgres durability
snapshot, the `BanditPolicy` Protocol (shared with the baseline policy in
Phase 8).
**Out of scope:** execution of the chosen arm (Phase 6).

## Deliverables mapped to monorepo paths

| Path | What goes here |
|---|---|
| `services/decide/bandit.py` | `BanditPolicy` Protocol + `ThompsonSamplingBandit` implementation |
| `services/decide/baseline_policy.py` | Trivial no-learning policy satisfying the same Protocol (used in Phase 8, stubbed here) |
| `services/decide/context.py` | `context_bucket_for(event, diagnosis)` construction logic |
| `services/decide/redis_store.py` | Hot-path α/β state, atomic increments |
| `services/decide/snapshot.py` | Periodic Redis → `bandit_arm_stats` durability write (invoked by `apps/worker`) |
| `services/decide/tests/test_convergence.py` | Statistical convergence test |
| `services/decide/tests/test_concurrency.py` | Atomic-update / no-lost-updates test |

## Detailed task breakdown

1. **`BanditPolicy` Protocol** (structural typing — this is what lets Phase
   8 swap policies with zero branching elsewhere):
   ```python
   class BanditPolicy(Protocol):
       def sample_arm(self, context_bucket: str) -> str: ...
       def update(self, context_bucket: str, arm: str, reward: float) -> None: ...
       def get_stats(self, context_bucket: str) -> dict[str, tuple[float, float]]: ...
   ```

2. **Context bucket construction** — combine `cause_category`,
   `amount_bucket`, `customer_segment`, `retry_count_so_far` into a stable
   string key, e.g. `f"{cause}|{amount_bucket}|{segment}|{retry_count}"`.
   Keep bucket cardinality bounded (bucket amounts into ~4-5 ranges, not raw
   values) so each bucket accumulates enough observations to learn from
   within a 200-event batch.

3. **Thompson Sampling implementation**
   ```python
   def sample_arm(self, context_bucket: str) -> str:
       best_arm, best_score = None, -1
       for arm in ARMS:
           alpha, beta = self.store.get_stats(context_bucket, arm)
           score = np.random.beta(alpha, beta)
           if score > best_score:
               best_arm, best_score = arm, score
       return best_arm

   def update(self, context_bucket: str, arm: str, reward: float) -> None:
       assert 0.0 <= reward <= 1.0 or reward == -0.1  # validate before touching state
       self.store.increment_alpha(context_bucket, arm, reward)
       self.store.increment_beta(context_bucket, arm, 1 - max(reward, 0))
   ```

4. **Redis atomic updates** — use `HINCRBYFLOAT` for α/β increments, never
   read-modify-write in application code (race condition under concurrent
   Celery workers).

5. **Informed priors** — seed initial α/β per `(context_bucket, arm)` from
   domain intuition (e.g., `otp_failure` + `retry_immediate` gets a
   favorable prior) via a one-time seed script, not a uniform prior.

6. **Explainability logging** — every `sample_arm()` call should return
   (or the caller should separately fetch) the sampled score and the α/β
   snapshot at decision time, written to the `decisions` table — this is
   what lets you answer "why did it choose this?" with real numbers in Q&A.

## Edge-case matrix

| Case | Expected behavior |
|---|---|
| Brand-new `context_bucket` never seen before | Falls back to the seeded default prior, not a crash or uniform-random guess |
| Redis unavailable | Raises loudly — does NOT silently fall back to random; a broken hot-path store should stop the pipeline, not corrupt learning silently |
| Reward outside valid range | Rejected by `update()`'s input validation before touching α/β |
| Context bucket with only 1 historical observation | High Beta-distribution variance is intentional (explore when uncertain) — document this in a code comment so it isn't "fixed" as a bug later |

## Design decisions & trade-offs

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| State storage | Postgres-only, Redis-only, Redis+Postgres | Redis hot path + periodic Postgres snapshot | Every event reads+writes arm stats — Redis keeps this fast; Postgres snapshot protects against data loss |
| Concurrency safety | Assume single-threaded vs. handle concurrency | Atomic `HINCRBYFLOAT`, no read-modify-write | Concurrent Celery workers process events in parallel even in a demo |
| Cold-start | Uniform prior vs. informed prior | Informed prior from domain intuition | Reduces early-batch regret; "we encoded domain knowledge, then let data refine it" |
| Explainability | Log only chosen arm | Log chosen arm + sampled score + α/β snapshot | Lets you answer "why" with real numbers during Q&A |

## Test plan
- **Unit:** `update()` correctly increments α on reward=1, β on reward=0.
- **Statistical convergence:** simulate 500 rounds, one arm true 80% success vs. another 20%, assert empirical selection ratio shifts toward the better arm (tolerance-based).
- **Concurrency:** fire 50 concurrent `update()` calls for the same bucket+arm, assert final α/β reflects all 50 (no lost updates).

## Definition of Done
- [ ] Convergence test passes.
- [ ] Concurrency test passes with zero lost updates.
- [ ] Redis-unavailable failure mode is a loud, logged error, not silent degradation.
- [ ] `BanditPolicy` Protocol satisfied and importable by both `apps/api` and `eval/`.

## Handoff to Phase 6 & 8
Phase 6 assumes: a `chosen_arm` string it can route to the correct
execution path. Phase 8 assumes: both `ThompsonSamplingBandit` and
`BaselinePolicy` satisfy the identical `BanditPolicy` Protocol, so the
batch harness's `policy.sample_arm(...)` call is agnostic to which is injected.
