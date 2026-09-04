# Phase 8 — Batch Evaluation Harness — Full Detailed Spec

**Depends on:** Phases 2-7 (the entire pipeline, minus a web server)
**Unblocks:** Phase 10 (dashboard reads these results), your entire demo's headline numbers
**Owner:** whoever owns Phase 2 (data) — natural continuity
**Estimated time:** ~1 day

---

## 1. Why this phase exists and why it matters more than it looks

Every phase before this produces a system that *can* recover revenue.
Nothing before this phase produces a **number** — and a number, backed by a
controlled comparison, is what turns "we built a thing" into "we built a
thing that measurably works." This is also the phase most likely to be
scrutinized adversarially by a judge, because it's the phase making the
strongest claim: "our agent recovers more revenue than what merchants do
today." That claim is only as strong as the experiment behind it.

There is exactly one property that makes or breaks this phase's
credibility: **the baseline and the bandit must be compared on identical
data, processed by identical code, with only the decision policy
different.** If you build a separate, simpler pipeline for the baseline
"just to save time," you've built a strawman comparison, and any
technically literate judge who asks "did both policies see the same
events?" will immediately expose it. Phase 5's `BanditPolicy` Protocol
exists specifically to make this proper controlled experiment possible —
this phase is where that architectural investment pays off.

The second property that matters just as much: **your outcome simulation
must give the bandit something real to learn from.** If recovery
probability doesn't actually depend on which arm was chosen, there is
nothing for Thompson Sampling to discover, your learning curve will be
flat by mathematical necessity, and no amount of tuning batch size or
priors will fix that — because the problem isn't the bandit, it's that the
simulated world has no structure for it to find.

---

## 2. Conceptual model — read this before touching code

### 2.1 Why this is a *controlled experiment*, not just "run the code twice"

A controlled experiment holds everything constant except the one variable
you're studying. Here, the independent variable is **which decision policy
chooses the arm**. Everything else — the sequence of synthetic events, the
diagnosis logic, the gate rules, the outcome-generation mechanics — must be
byte-for-byte identical between the "bandit" run and the "baseline" run.
Concretely, this means:

- Both runs consume `generate_batch(seed=X, n=200)` with the **same seed**
  — not two different datasets that happen to have similar statistical
  properties, the literal same sequence of events in the same order.
- Both runs call the same `diagnose()`, the same `evaluate_gate()`, the
  same `RewardService.compute()`, and the same `AuditLogService.write()`
  from Phases 3, 4, 7 — reused verbatim, not reimplemented.
- The only thing that differs is which object implements the
  `BanditPolicy` Protocol: `ThompsonSamplingBandit` vs. `BaselinePolicy`.

If you can point to your code and show a judge "here is the exact one line
that differs between these two runs," you have an unimpeachable comparison.
If you can't point to that line, you don't have an experiment, you have two
stories.

### 2.2 Why the outcome simulator needs "arm-match quality," not just base recoverability

Phase 2's synthetic generator assigns each event a
`_ground_truth_recoverable` probability based purely on its cause category
— that's "how likely is this to ever be recovered, regardless of what we
do." But if that were the *only* factor determining the simulated outcome,
every arm would have the same expected success rate for a given event, and
the bandit would have nothing to differentiate arms by — it would converge
to nothing in particular, because nothing in the simulated world actually
depends on the arm chosen.

The fix is a second factor: **arm-match quality** — how well-suited a
specific arm is to a specific cause category. `retry_long_delay` is
plausibly a better match for `insufficient_funds` (wait for payday) than
`retry_immediate` is; `escalate_human` is a poor match for anything
low-value. The simulated outcome probability is the product of base
recoverability and arm-match quality. This product is what gives the
bandit a real optimization landscape to discover — and, importantly, this
table is *itself* a design artifact worth showing a judge, because it's the
explicit statement of "here is what a good decision looks like," which the
bandit is expected to rediscover empirically without being told directly.

### 2.3 Why multi-seed reporting matters, and single-seed reporting is a trap

Thompson Sampling is a stochastic algorithm — sampling from Beta
distributions means two runs with different random seeds will not produce
identical results, even with identical inputs. If you run once, get a
great lift number, and put that single number on your title slide, you are
one unlucky rerun away from a judge asking "can you run it again right now"
and getting a materially different (possibly less flattering) result live.
Running 3+ seeds and reporting the range (or mean ± spread) is not just
statistical hygiene — it's insurance against the single most likely way
your headline number could embarrass you live.

---

## 3. Detailed component design

### 3.1 `services/decide/baseline_policy.py` (finalized here, stubbed in Phase 5)

```python
from services.decide.bandit import ArmChoice

class BaselinePolicy:
    """Represents 'what merchants do today': always retry immediately,
    once, no personalization, no learning. Satisfies the identical
    BanditPolicy Protocol as ThompsonSamplingBandit — this is what lets
    eval/run_batch.py inject either with zero branching at the call site."""

    def sample_arm(self, context_bucket: str) -> ArmChoice:
        return ArmChoice(arm="retry_immediate", sampled_score=1.0,
                          alpha_at_decision=1.0, beta_at_decision=1.0)

    def update(self, context_bucket: str, arm: str, reward: float) -> None:
        pass  # no learning, by design — this IS the baseline's defining property

    def get_stats(self, context_bucket: str) -> dict[str, tuple[float, float]]:
        return {}
```

### 3.2 `eval/outcome_simulator.py`

```python
import numpy as np

# Hand-specified ground-truth reward structure — this table is what the
# bandit is expected to discover empirically. Document it in ML_DESIGN.md
# as the "answer key" the bandit shouldn't be given directly, only allowed
# to infer from observed rewards.
ARM_MATCH_QUALITY: dict[str, dict[str, float]] = {
    "insufficient_funds":   {"retry_immediate": 0.3, "retry_short_delay": 0.5, "retry_long_delay": 0.9,
                              "send_nudge_english": 0.4, "send_nudge_hinglish": 0.4, "stop": 0.0},
    "expired_card":         {"retry_immediate": 0.1, "send_card_update_link": 0.9,
                              "send_nudge_english": 0.3, "send_nudge_hinglish": 0.3, "stop": 0.0},
    "otp_failure":          {"retry_immediate": 0.9, "retry_short_delay": 0.6, "retry_long_delay": 0.3,
                              "stop": 0.0},
    "bank_timeout":         {"retry_immediate": 0.5, "retry_short_delay": 0.85, "retry_long_delay": 0.5,
                              "stop": 0.0},
    "mandate_inactive":     {"retry_immediate": 0.1, "send_nudge_english": 0.5, "send_nudge_hinglish": 0.5,
                              "escalate_human": 0.6, "stop": 0.0},
    "hard_decline":         {"retry_immediate": 0.05, "send_card_update_link": 0.3,
                              "escalate_human": 0.4, "stop": 0.7},
    "customer_cancelled":   {"retry_immediate": 0.0, "send_nudge_english": 0.05, "stop": 0.9},
}
DEFAULT_MATCH_QUALITY = 0.3  # for any (cause, arm) pair not explicitly listed above


def simulate_outcome(event_draft: dict, chosen_arm: str, rng: np.random.Generator) -> "SimulatedOutcome":
    base_prob = event_draft["_ground_truth_recoverable_prob"]
    cause = event_draft["cause_category"]
    match_quality = ARM_MATCH_QUALITY.get(cause, {}).get(chosen_arm, DEFAULT_MATCH_QUALITY)
    final_prob = min(base_prob * (0.5 + match_quality), 1.0)  # match_quality modulates, never fully zeroes out base_prob

    if chosen_arm == "stop":
        # 'stop' never recovers money by construction — it's a deliberate
        # no-action arm, not a low-probability action.
        recovered = False
    else:
        recovered = bool(rng.random() < final_prob)

    return SimulatedOutcome(
        result="recovered" if recovered else "not_recovered",
        amount_recovered=event_draft["amount"] if recovered else 0,
        time_to_resolution_hrs=float(rng.uniform(1, 72)) if recovered else None,
    )
```

**Why `stop` is hard-coded to never recover, rather than given a low
probability:** `stop` represents "the agent deliberately took no action."
Modeling it as "a very unlikely-to-succeed action" would be conceptually
wrong — it's not an action that sometimes works, it's the absence of
action. Keep this distinction in the code, not just in your head; a future
teammate who "simplifies" this into a uniform low-probability arm would be
quietly changing what `stop` means.

### 3.3 `eval/run_batch.py`

```python
import numpy as np

from data.generator import generate_batch
from services.diagnose.service import diagnose
from services.decide.context import context_bucket_for
from services.gate.service import evaluate_gate
from services.observe.reward_service import RewardService
from services.audit.audit_log_service import AuditLogService
from eval.outcome_simulator import simulate_outcome
from packages.db_models.models import BatchRun, BatchRunMetrics


def run_batch(db_session, dataset_seed: int, n: int, policy_name: str, policy) -> "BatchRun":
    """policy is injected by the caller — either a ThompsonSamplingBandit
    or a BaselinePolicy, both satisfying BanditPolicy. This function has
    NO branching on policy_name beyond labeling the run — the actual
    behavioral difference lives entirely inside the injected policy object.
    This is the concrete implementation of the controlled-experiment
    principle from section 2.1."""
    dataset_ref = f"seed={dataset_seed},n={n}"
    run = BatchRun(policy=policy_name, dataset_ref=dataset_ref, random_seed=dataset_seed)
    db_session.add(run)
    db_session.flush()

    reward_service = RewardService()
    audit_log_service = AuditLogService(db_session)
    outcome_rng = np.random.default_rng(dataset_seed + 1)  # separate stream from generation, same reproducibility guarantee

    event_drafts = generate_batch(seed=dataset_seed, n=n, merchant_id=None)

    exception_count = 0
    gate_blocked_count = 0
    amount_recovered_total = 0
    amount_at_risk_total = 0
    recovered_count = 0
    resolution_times = []

    for draft in event_drafts:
        amount_at_risk_total += draft["amount"]
        diagnosis = diagnose_from_draft(draft)  # thin adapter constructing a DiagnosisResult from the draft's cause_category — see Prompt 2 below
        context_bucket = context_bucket_for_draft(draft, diagnosis)

        choice = policy.sample_arm(context_bucket)
        gate_result = evaluate_gate(build_gate_context_from_draft(draft, choice.arm))

        if gate_result.passed:
            sim_outcome = simulate_outcome(draft, choice.arm, outcome_rng)
            reward = reward_service.compute(sim_outcome)
            policy.update(context_bucket, choice.arm, reward)
            if sim_outcome.result == "recovered":
                recovered_count += 1
                amount_recovered_total += sim_outcome.amount_recovered
                resolution_times.append(sim_outcome.time_to_resolution_hrs)
        else:
            gate_blocked_count += 1
            reward = reward_service.REWARD_BLOCKED_BY_POLICY
            policy.update(context_bucket, choice.arm, reward)
            sim_outcome = None

        if sim_outcome is None or sim_outcome.result == "not_recovered":
            exception_count += 1  # tracked distinctly from "blocked" — see edge-case matrix row 3

        audit_log_service.write(event=draft, decision=choice, gate_result=gate_result, outcome=sim_outcome)

    metrics = BatchRunMetrics(
        run_id=run.run_id,
        n_events=n,
        recovery_rate=recovered_count / n,
        amount_recovered=amount_recovered_total,
        amount_at_risk=amount_at_risk_total,
        avg_time_to_recovery_hrs=(sum(resolution_times) / len(resolution_times)) if resolution_times else None,
        exception_count=exception_count,
        gate_blocked_count=gate_blocked_count,
    )
    db_session.add(metrics)
    db_session.commit()
    return run
```

**Note the exception-counting distinction in the code above** (edge-case
matrix row 3 below): a gate-blocked event and a not-recovered-but-attempted
event are both "the agent didn't get the money back," but they represent
different failure modes and should be reportable separately, not conflated
into one undifferentiated "failure" bucket — a judge asking "how many of
your failures were compliance-blocked vs. genuinely unrecoverable" deserves
a real answer, not a shrug.

### 3.4 `eval/metrics_queries.sql`

```sql
-- Independently re-verifies the Python harness's computed metrics.
-- Run this against any batch_run's run_id to cross-check
-- batch_run_metrics without trusting the Python aggregation code alone.

-- Recovery rate cross-check
SELECT
    d.decided_at,
    COUNT(*) FILTER (WHERE o.result = 'recovered')::float / COUNT(*) AS recovery_rate
FROM decisions d
JOIN actions a ON a.decision_id = d.decision_id
LEFT JOIN outcomes o ON o.action_id = a.action_id
WHERE d.decision_id IN (
    -- filter to the specific batch run's decisions via audit_log's episode_id join,
    -- or add a run_id column to decisions if batch/live decisions need to be
    -- distinguishable at the DB level — flag this to the team if not already present
    SELECT DISTINCT decision_id FROM decisions WHERE decided_at >= :run_started_at AND decided_at <= :run_finished_at
);

-- Lift computation (run this once per policy, compare manually or via a view)
SELECT
    br.policy,
    brm.recovery_rate,
    brm.amount_recovered,
    brm.amount_at_risk,
    ROUND(brm.amount_recovered::numeric / NULLIF(brm.amount_at_risk, 0) * 100, 2) AS pct_at_risk_recovered
FROM batch_runs br
JOIN batch_run_metrics brm ON brm.run_id = br.run_id
WHERE br.dataset_ref = :dataset_ref  -- same dataset_ref means same seed+n, a fair comparison
ORDER BY br.policy;
```

**Flag to the team while implementing this:** the query above assumes you
can identify which `decisions` belong to a specific batch run. If
`decisions` doesn't currently carry a `run_id` (batch mode) or a
distinguishing marker from live-mode decisions, add one — this is exactly
the kind of schema gap worth surfacing explicitly (per `CLAUDE.md`) rather
than working around with a fragile timestamp-range filter as a permanent
solution.

### 3.5 Multi-seed runner

```python
# eval/multi_seed_runner.py
def run_multi_seed_comparison(db_session, seeds: list[int], n: int) -> dict:
    results = {"bandit": [], "baseline": []}
    for seed in seeds:
        bandit_run = run_batch(db_session, dataset_seed=seed, n=n, policy_name="bandit",
                                policy=ThompsonSamplingBandit(RedisArmStatsStore(...)))
        baseline_run = run_batch(db_session, dataset_seed=seed, n=n, policy_name="baseline",
                                  policy=BaselinePolicy())
        results["bandit"].append(bandit_run.metrics.recovery_rate)
        results["baseline"].append(baseline_run.metrics.recovery_rate)

    return {
        "bandit_mean": np.mean(results["bandit"]), "bandit_range": (min(results["bandit"]), max(results["bandit"])),
        "baseline_mean": np.mean(results["baseline"]), "baseline_range": (min(results["baseline"]), max(results["baseline"])),
        "lift_mean": np.mean(results["bandit"]) - np.mean(results["baseline"]),
        "consistent_direction": all(b > base for b, base in zip(results["bandit"], results["baseline"])),
    }
```

---

## 4. Full edge-case matrix (expanded)

| # | Case | Expected behavior | How to test |
|---|---|---|---|
| 1 | `n` too small for statistical significance | Document minimum viable batch size (n≥150) in `TESTING_METRICS.md`; a run below this should still execute but the harness should log a warning | Unit test: `n=10`, assert a warning is logged, run still completes |
| 2 | Baseline and bandit given different seeds by mistake | Would silently invalidate the comparison — guard against this explicitly, don't rely on callers remembering | Fairness test in §5.2, asserting identical event sequences |
| 3 | Gate-blocked event vs. genuinely-attempted-but-failed event | Tracked as distinct counters (`gate_blocked_count` vs. contributing to `exception_count` only when actually attempted and failed) | Unit test constructing one of each, asserting both counters increment correctly and independently |
| 4 | `stop` arm chosen | Never contributes to `amount_recovered`, regardless of `base_prob` | Unit test: force `chosen_arm="stop"`, assert `simulate_outcome` always returns `not_recovered` |
| 5 | Two seeds produce meaningfully different lift | Multi-seed runner catches this via `consistent_direction`; if `False`, this must be investigated before presenting any single-seed number | Statistical test: run ≥3 seeds, assert `consistent_direction` is `True` for your final tuned priors/buckets (if not, this is real signal to retune, not a test to loosen) |
| 6 | `BaselinePolicy` and `ThompsonSamplingBandit` diverge in the `BanditPolicy` Protocol's method signatures | Would break the "zero-branching swap" property this whole phase depends on | `mypy` structural check + a runtime `isinstance`-free duck-typing test asserting both can be passed to `run_batch` without modification |

---

## 5. Test plan — with actual test code to implement

### 5.1 `eval/tests/test_reproducibility.py`

```python
def test_same_params_produce_identical_metrics(db_session):
    run1 = run_batch(db_session, dataset_seed=42, n=200, policy_name="baseline", policy=BaselinePolicy())
    run2 = run_batch(db_session, dataset_seed=42, n=200, policy_name="baseline", policy=BaselinePolicy())
    assert run1.metrics.recovery_rate == run2.metrics.recovery_rate
    assert run1.metrics.amount_recovered == run2.metrics.amount_recovered
```
**Note:** this test is only meaningful for `BaselinePolicy`, since it has
no randomness beyond the shared `outcome_rng` seed. For
`ThompsonSamplingBandit`, reproducibility means "identical Redis state at
the start of the run" — reset the test Redis instance between runs, or this
test will (correctly) fail due to persisted bandit state from a prior run.

### 5.2 `eval/tests/test_fairness.py`

```python
def test_baseline_and_bandit_see_identical_event_sequence(db_session, capture_generated_events):
    run_batch(db_session, dataset_seed=99, n=50, policy_name="baseline", policy=BaselinePolicy())
    events_seen_by_baseline = capture_generated_events.calls[-1]

    run_batch(db_session, dataset_seed=99, n=50, policy_name="bandit", policy=fresh_bandit())
    events_seen_by_bandit = capture_generated_events.calls[-1]

    assert events_seen_by_baseline == events_seen_by_bandit, (
        "baseline and bandit runs must process the EXACT same event sequence "
        "for the comparison to be scientifically valid"
    )
```

### 5.3 `eval/tests/test_multi_seed_variance.py`

```python
def test_bandit_beats_baseline_consistently_across_seeds(db_session):
    result = run_multi_seed_comparison(db_session, seeds=[1, 2, 3], n=200)
    assert result["consistent_direction"] is True, (
        f"bandit did not consistently beat baseline across seeds: {result}"
    )
    assert result["lift_mean"] > 0
```
**If this test fails, do not loosen it** — per section 2.3's warning, a
failure here means your bucket cardinality, priors, or arm-match-quality
table need retuning, not that the test's bar was set too high.

### 5.4 `eval/tests/test_stop_arm_never_recovers.py`

```python
def test_stop_arm_produces_zero_recovery_probability():
    rng = np.random.default_rng(1)
    draft = {"cause_category": "insufficient_funds", "_ground_truth_recoverable_prob": 0.95, "amount": 100000}
    for _ in range(100):  # even with a near-certain base probability, 'stop' must never recover
        outcome = simulate_outcome(draft, "stop", rng)
        assert outcome.result == "not_recovered"
        assert outcome.amount_recovered == 0
```

---

## 6. Observability

Every `run_batch` invocation should log a structured summary at
completion: `run_id`, `policy`, `dataset_ref`, `recovery_rate`,
`amount_recovered`, `exception_count`, `gate_blocked_count`, and total wall
time. This is what lets you sanity-check a run's plausibility immediately
after it finishes, without querying the DB — useful during iterative tuning
of priors/buckets in the days before your demo.

---

## 7. Definition of Done (full checklist)

- [ ] `BaselinePolicy` satisfies the identical `BanditPolicy` Protocol as `ThompsonSamplingBandit` — verified structurally, not just visually.
- [ ] `run_batch` contains zero branching on `policy_name` beyond labeling — the only behavioral difference is the injected `policy` object.
- [ ] Reproducibility test passes for `BaselinePolicy`.
- [ ] Fairness test passes: identical event sequence proven for both policies at a given seed.
- [ ] Multi-seed variance test passes with `consistent_direction=True` and positive `lift_mean`.
- [ ] `stop` arm never contributes to `amount_recovered`, verified by a dedicated test, not just code review.
- [ ] Gate-blocked and genuinely-failed outcomes are tracked as distinct counters.
- [ ] SQL cross-check queries independently reproduce the Python-computed `recovery_rate`.
- [ ] At least one full 200+-event multi-seed run cached in `eval/results/` as the live-demo fallback.

---

## 8. Prompts for your coding agent

Use these as focused, sequential prompts. `CLAUDE.md`'s repo-wide standards
apply automatically; these assume that context is already loaded (see
`docs/AGENT_KICKOFF_PROMPT.md`).

### Prompt 1 — Baseline policy
```
Finish services/decide/baseline_policy.py per docs/phases/PHASE_08_batch_eval_DETAILED.md
section 3.1: BaselinePolicy satisfying the exact same BanditPolicy Protocol
defined in services/decide/bandit.py from Phase 5. Then write a test (can
live in services/decide/tests/ or eval/tests/, your choice, but document
which) using mypy or a runtime structural check to prove BaselinePolicy and
ThompsonSamplingBandit are interchangeable at any call site expecting a
BanditPolicy — do not just eyeball the method signatures.
```

### Prompt 2 — Outcome simulator with arm-match quality
```
Implement eval/outcome_simulator.py per docs/phases/PHASE_08_batch_eval_DETAILED.md
section 3.2: the ARM_MATCH_QUALITY table exactly as specified, DEFAULT_MATCH_QUALITY,
and simulate_outcome(). Pay close attention to the 'stop' arm special case —
it must NEVER produce a recovered outcome regardless of base probability,
by explicit branching, not by giving it a low-but-nonzero match quality
value. Write eval/tests/test_stop_arm_never_recovers.py per section 5.4 of
the doc, running at least 100 trials with a high base probability to prove
this holds even under favorable conditions.
```

### Prompt 3 — Batch runner (the controlled experiment)
```
Implement eval/run_batch.py per docs/phases/PHASE_08_batch_eval_DETAILED.md
section 3.3. The single most important property to preserve: run_batch()
must contain NO branching logic based on policy_name beyond labeling the
BatchRun row — all behavioral difference between baseline and bandit runs
must come entirely from the injected `policy` object satisfying the
BanditPolicy Protocol. You will need small adapter functions
(diagnose_from_draft, context_bucket_for_draft, build_gate_context_from_draft)
to bridge Phase 2's raw event drafts into the shapes Phase 3/4/5's real
services expect — check services/diagnose/service.py, services/decide/context.py,
and services/gate/service.py's actual signatures from earlier phases before
writing these adapters, don't guess at their interfaces. Track gate-blocked
and genuinely-failed outcomes as separate counters, per edge-case matrix
row 3 in the doc — do not conflate them into one 'failure' count.
```

### Prompt 4 — Reproducibility and fairness tests
```
Write eval/tests/test_reproducibility.py and eval/tests/test_fairness.py
exactly per sections 5.1 and 5.2 of docs/phases/PHASE_08_batch_eval_DETAILED.md.
For the fairness test, you'll need to instrument or wrap data/generator.py's
generate_batch() to capture the exact sequence of events it returns across
two separate run_batch() calls at the same seed, then assert the sequences
are identical — implement this capture mechanism (e.g., a test double or a
call-recording wrapper) without modifying generate_batch()'s actual
production behavior.
```

### Prompt 5 — Multi-seed comparison and SQL cross-check
```
Implement eval/multi_seed_runner.py per section 3.5 of
docs/phases/PHASE_08_batch_eval_DETAILED.md, running at least 3 seeds and
reporting mean, range, and consistent_direction. Write
eval/tests/test_multi_seed_variance.py per section 5.3 — if this test
fails when you run it, do NOT loosen the assertion; instead report back to
me what the actual lift numbers were per seed so we can decide whether to
retune ARM_MATCH_QUALITY, the context bucket cardinality from Phase 5, or
the informed priors, per the tuning guidance in PHASE_05_decide_DETAILED.md
section 3.2. Then write eval/metrics_queries.sql per section 3.4 of this
doc — before finalizing it, check whether packages/db-models/models/decision.py
has any field that distinguishes batch-run decisions from live-mode
decisions; if not, tell me explicitly that a schema addition (e.g., a
nullable run_id column on decisions) is needed rather than writing a
fragile timestamp-range-based query as a permanent solution.
```

### Prompt 6 — Full run + cached fallback + Definition of Done pass
```
Run a full multi-seed batch evaluation (at least 3 seeds, n=200 each) using
your actual implementation, save the results as JSON files in eval/results/
per docs/MONOREPO_STRUCTURE.md, and confirm this cached output is what
DEMO_SCRIPT.md's batch-results-reveal beat will show if live computation
isn't used during the actual demo. Then work through the full Definition
of Done checklist in section 7 of docs/phases/PHASE_08_batch_eval_DETAILED.md
and report back which items pass, including the actual multi-seed lift
numbers you obtained — show me the real output, including if
consistent_direction came out False on your first attempt and what you did
about it.
```
