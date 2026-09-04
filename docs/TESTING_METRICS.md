# Testing & Metrics Plan

## 1. Principle

Every number shown in the demo must come from an actual batch run you can
reproduce, not a hand-picked example. This document defines exactly how that
run is structured so there's no ambiguity when you sit down to build the
eval script.

## 2. The comparison you must produce

Run the **same synthetic batch** (same seed, same events) through two
policies:

1. **Baseline** — naive same-day retry, once, no personalization, no
   channel variation. This represents "what merchants typically do today."
2. **Agent** — full pipeline (Diagnose → Bandit Decide → Gate → Act →
   Observe).

Report both. The delta between them is your headline number.

## 3. Core metrics (compute for both baseline and agent)

| Metric | Formula | Notes |
|---|---|---|
| Recovery rate | recovered_events / total_events | Primary headline metric |
| ₹ recovered | Σ amount for recovered events | Absolute business-impact number |
| % of at-risk revenue recovered | ₹ recovered / Σ amount for all failed events | Frames the number as impact, not just count |
| Avg. time-to-recovery | mean(time_to_resolution_hours) over recovered events | Report median too if distribution is skewed |
| Lift | agent_recovery_rate − baseline_recovery_rate | The single number to put on your title slide |

## 4. Agent-only metrics

| Metric | Formula | Notes |
|---|---|---|
| Exception rate | unresolved_events / total_events | Report honestly — must be > 0% to be credible |
| Gate-blocked rate | blocked_actions / total_attempted_actions | Shows the compliance layer is actually doing something |
| Bandit convergence | recovery rate in first third of batch vs. last third | Should show visible improvement |
| Arm distribution shift | % selection per arm, early batch vs. late batch | Visual proof of learning |

## 5. Required qualitative artifacts

1. **The exception list** — a table of events the agent could not resolve,
   with the cause category and why (e.g., "hard_decline, 3 attempts
   exhausted, customer non-responsive"). This is a credibility asset, not a
   weakness — present it as evidence of honest measurement.
2. **One "graceful failure" walkthrough** — pick a single event where the
   customer explicitly declines/opts out, and show the audit trail proving
   the agent respected the stopping rule and did not keep contacting them.
3. **One end-to-end live walkthrough** — a single event run live (not from
   the pre-computed batch) from ingestion through to outcome, to prove the
   pipeline works interactively, not just in a canned batch script.

## 6. Test coverage checklist (engineering correctness, separate from ML metrics)

- [ ] Diagnosis: every gateway error code in the dataset maps to exactly one
      cause category (no `unknown` leakage for known codes).
- [ ] Gate: unit test that an event at `retry_count_so_far = max_attempts`
      is always blocked, regardless of bandit output.
- [ ] Gate: unit test that `customer_opted_out = true` always results in
      `stop`, regardless of bandit output.
- [ ] Bandit: unit test that arm statistics update correctly after a
      reward is observed.
- [ ] Audit trail: every event that enters the pipeline has exactly one
      corresponding audit record with all required fields populated.
- [ ] API: `POST /pipeline/run-batch` is idempotent given the same
      `dataset_path` + seed (reproducibility check).

## 7. Reporting format for the final numbers

Present metrics as a simple before/after table, e.g.:

| | Baseline | Agent | Lift |
|---|---|---|---|
| Recovery rate | 22% | 47% | +25 pts |
| ₹ recovered | ₹18.4L | ₹34.1L | +₹15.7L |
| Avg. time-to-recovery | 4.2 days | 2.6 days | −1.6 days |

(Numbers above are illustrative placeholders — replace with your actual
batch results, and be ready to explain the run parameters if asked.)
