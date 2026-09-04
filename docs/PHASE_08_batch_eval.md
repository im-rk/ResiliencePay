# Phase 8 — Batch Evaluation Harness

**Depends on:** Phases 2-7 (the entire pipeline, minus a web server)
**Unblocks:** Phase 10 (dashboard reads these results), your entire demo's headline numbers
**Owner:** whoever owns Phase 2 (data) — natural continuity
**Estimated time:** ~1 day

## Objective
Produce the headline, reproducible, judge-defensible numbers: bandit policy
vs. naive baseline over an identical synthetic dataset, using the exact same
pipeline code for both — only the `Decide` step differs.

## Scope
**In scope:** baseline policy, batch runner, outcome simulation for
batch-mode (no real Razorpay calls), SQL metric views, multi-seed variance check.
**Out of scope:** how metrics are displayed (Phase 10).

## Deliverables mapped to monorepo paths

| Path | What goes here |
|---|---|
| `services/decide/baseline_policy.py` | Trivial no-learning policy, same `BanditPolicy` Protocol (stubbed in Phase 5, finished here) |
| `eval/run_batch.py` | Orchestrates a full batch run for a given policy |
| `eval/baseline_runner.py` | Baseline-specific run entrypoint (thin wrapper over `run_batch.py`) |
| `eval/outcome_simulator.py` | Batch-mode outcome simulation using `_ground_truth_recoverable` + arm-match quality |
| `eval/metrics_queries.sql` | SQL views independently reproducing Python-computed metrics |
| `eval/results/` | Cached batch-run outputs — your live-demo fallback |
| `eval/tests/test_reproducibility.py` | Same params → identical `batch_run_metrics` row |
| `eval/tests/test_fairness.py` | Both policies process the exact same event set |

## Detailed task breakdown

1. **Baseline policy** (satisfies the same `BanditPolicy` Protocol from Phase 5):
   ```python
   class BaselinePolicy:
       def sample_arm(self, context_bucket: str) -> str:
           return "retry_immediate"
       def update(self, context_bucket, arm, reward): pass  # no learning
       def get_stats(self, context_bucket): return {}
   ```

2. **Outcome simulator** — this is what gives the bandit something to
   learn from; if outcome were independent of arm choice, the learning
   curve would be flat by construction:
   ```python
   def simulate_outcome(event_draft, chosen_arm) -> Outcome:
       base_prob = event_draft["_ground_truth_recoverable_prob"]
       match_quality = ARM_MATCH_QUALITY[event_draft["cause_category"]].get(chosen_arm, 0.5)
       final_prob = base_prob * match_quality
       recovered = np.random.random() < final_prob
       return Outcome(result="recovered" if recovered else "not_recovered",
                       amount_recovered=event_draft["amount"] if recovered else 0,
                       reward=1.0 if recovered else 0.0)
   ```
   `ARM_MATCH_QUALITY` is a hand-specified table (e.g., `retry_long_delay`
   has high match quality for `insufficient_funds`, low for `hard_decline`)
   — document this table in `ML_DESIGN.md` as the ground-truth reward
   structure the bandit is expected to discover.

3. **Batch runner**
   ```python
   def run_batch(dataset_seed: int, n: int, policy_name: Literal["bandit", "baseline"]):
       run = BatchRun(policy=policy_name, dataset_ref=f"seed={dataset_seed},n={n}", random_seed=dataset_seed)
       events = generate_batch(seed=dataset_seed, n=n)  # SAME seed for both policies
       policy = bandit_policy if policy_name == "bandit" else BaselinePolicy()

       for event in events:
           diagnosis = diagnose(event)
           context = context_bucket_for(event, diagnosis)
           chosen_arm = policy.sample_arm(context)
           gate_result = evaluate_gate(build_context(event, chosen_arm))
           if gate_result.passed:
               outcome = outcome_simulator.simulate_outcome(event, chosen_arm)
               policy.update(context, chosen_arm, outcome.reward)
           else:
               outcome = Outcome(result="blocked_by_policy", reward=-0.1)
           audit_log_service.write(event, chosen_arm, gate_result, outcome)

       compute_and_persist_metrics(run)
   ```

4. **SQL metric views** — write the recovery-rate, ₹-recovered, and lift
   calculations as SQL views/queries against `outcomes`/`batch_runs`, so
   anyone with DB access can independently re-verify your Python-computed
   numbers. This cross-check is itself a test (see below).

5. **Multi-seed run** — run at least 3 different seeds, store all results,
   report mean and range in your final metrics, not a single lucky number.

## Edge-case matrix

| Case | Expected behavior |
|---|---|
| `n` too small for statistical significance | Document minimum viable batch size (n≥150) in `TESTING_METRICS.md`; don't present an underpowered single run as conclusive |
| Baseline must satisfy the same Protocol | Verified by a `mypy`/structural test — both policies are interchangeable at the call site |
| Two seeds give very different lift | Multi-seed variance check catches this before it reaches your demo slide |

## Design decisions & trade-offs

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Baseline implementation | Separate simplified pipeline vs. same pipeline, policy swapped | Same pipeline, `Decide` swapped via the shared Protocol | A baseline on a *different* code path invites judges to question fairness; this is a properly controlled experiment |
| Outcome simulation | Deterministic rule vs. probability sampling with arm-match quality | Probability sampling, arm-match-quality-weighted | Gives the bandit a genuine signal to learn from — required for a real (not staged) learning curve |
| Metrics computation | Ad hoc Python vs. SQL views | SQL views, independently queryable | Anyone with DB access can re-verify your numbers without trusting your script |

## Test plan
- **Reproducibility:** same `(seed, n, policy)` twice → identical `batch_run_metrics` row.
- **Fairness-of-comparison:** assert baseline and bandit runs process the exact same `events` list.
- **Multi-seed variance:** 3 seeds, assert lift is directionally consistent (bandit > baseline) across all three.
- **Cross-check:** SQL view output matches Python harness output exactly.

## Definition of Done
- [ ] Reproducibility test passes.
- [ ] Multi-seed lift is consistent and positive.
- [ ] SQL views independently reproduce the same numbers as the Python harness.
- [ ] At least one full 200+-event run cached in `eval/results/` as the live-demo fallback.

## Handoff to Phase 10
Phase 10 assumes: a `GET /v1/metrics/summary?run_id=...` API (built in
Phase 9) backed by real `batch_run_metrics` rows produced here, plus
per-event audit rows it can chart as a learning curve.
