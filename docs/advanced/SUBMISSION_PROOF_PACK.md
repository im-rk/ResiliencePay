# Submission Proof Pack — Making Your Evidence Trivial to Verify

**Effort:** ~half a day
**Builds on:** Phase 8 (batch evaluation)
**Demo impact:** Extremely high — this is arguably the single best-value addition available to you right now, because it doesn't add a new capability, it makes your *existing* evidence impossible for a judge to miss or doubt

---

## The gap this closes

You already produce a real recovery-rate lift number from a real
controlled experiment. But right now, seeing that number requires
navigating your dashboard, or worse, trusting a claim in your README. A
judge evaluating dozens of submissions under time pressure rewards
projects that make verification effortless — this is about **presentation
of proof**, not new engineering, and it's disproportionately cheap given
what you already have running.

## Part 1 — A clean, structured `summary_report.json`

### `eval/generate_summary_report.py`

```python
import json
from datetime import datetime, timezone

def generate_summary_report(db_session, bandit_run_id: str, baseline_run_id: str, output_path: str = "summary_report.json"):
    bandit = get_batch_run_metrics(db_session, bandit_run_id)
    baseline = get_batch_run_metrics(db_session, baseline_run_id)

    gate_violations = count_gate_violations_that_were_not_blocked(db_session, bandit_run_id)
    # This should always be zero by construction — see PHASE_04_gate_DETAILED.md.
    # Computing and reporting it explicitly, rather than just asserting it in
    # a test, is itself a credibility move: you're showing your work, not
    # just claiming compliance.

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {"n_events": bandit.n_events, "seed": bandit.run.random_seed},
        "total_value_at_risk_paise": bandit.amount_at_risk,
        "baseline": {
            "recovered_paise": baseline.amount_recovered,
            "recovery_rate": round(baseline.recovery_rate, 4),
        },
        "resiliencepay_agent": {
            "recovered_paise": bandit.amount_recovered,
            "recovery_rate": round(bandit.recovery_rate, 4),
        },
        "lift": {
            "absolute_recovery_rate_points": round(bandit.recovery_rate - baseline.recovery_rate, 4),
            "net_additional_paise_recovered": bandit.amount_recovered - baseline.amount_recovered,
        },
        "compliance": {
            "gate_checks_performed": count_total_gate_checks(db_session, bandit_run_id),
            "gate_blocks_enforced": bandit.gate_blocked_count,
            "compliance_violations": gate_violations,  # must be 0 — reported explicitly, not just assumed
        },
        "honesty": {
            "exception_count": bandit.exception_count,
            "exception_rate": round(bandit.exception_count / bandit.n_events, 4),
        },
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print_terminal_summary(report)  # human-readable table, see Part 2
    return report
```

**Note the `compliance_violations` field is computed, not hardcoded to
zero** — it queries whether any gate-passed decision ever resulted in an
action that violated a rule (which should be structurally impossible per
`PHASE_04_gate_DETAILED.md`, but reporting the actual computed count,
not an assumed constant, is what makes this evidence rather than a claim).

## Part 2 — A clean terminal table on every run

```python
def print_terminal_summary(report: dict) -> None:
    def rupees(paise: int) -> str:
        return f"Rs. {paise / 100:,.2f}"

    print("=" * 60)
    print("  RESILIENCEPAY — BATCH EVALUATION SUMMARY")
    print("=" * 60)
    print(f"  Total Value at Risk:        {rupees(report['total_value_at_risk_paise'])}")
    print(f"  Naive Baseline Recovered:   {rupees(report['baseline']['recovered_paise'])} "
          f"({report['baseline']['recovery_rate']*100:.1f}%)")
    print(f"  ResiliencePay Recovered:    {rupees(report['resiliencepay_agent']['recovered_paise'])} "
          f"({report['resiliencepay_agent']['recovery_rate']*100:.1f}%)")
    print(f"  Absolute Lift:              +{report['lift']['absolute_recovery_rate_points']*100:.1f} pts "
          f"({rupees(report['lift']['net_additional_paise_recovered'])} net gained)")
    print(f"  Compliance Violations:      {report['compliance']['compliance_violations']} "
          f"({'100% adherence' if report['compliance']['compliance_violations'] == 0 else 'REVIEW NEEDED'})")
    print(f"  Honest Exception Rate:      {report['honesty']['exception_rate']*100:.1f}% "
          f"({report['honesty']['exception_count']} genuinely unrecoverable cases)")
    print("=" * 60)
```

**Deliberately report the exception rate as a positive, not a hidden
weakness** — per `TESTING_METRICS.md`, a non-zero rate here is evidence of
honest measurement, and presenting it confidently in your own summary
table pre-empts a judge feeling like they "caught" you hiding it.

## Part 3 — Single-command reproduction

### `run_demo.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Starting infrastructure..."
docker-compose -f infra/docker-compose.yml up -d --build postgres redis

echo "Waiting for services to be healthy..."
docker-compose -f infra/docker-compose.yml up -d --wait api worker

echo "Running database migrations..."
docker-compose -f infra/docker-compose.yml exec api alembic upgrade head

echo "Running batch evaluation (bandit vs. baseline, 3 seeds)..."
docker-compose -f infra/docker-compose.yml exec api python -m eval.multi_seed_runner

echo "Generating summary report..."
docker-compose -f infra/docker-compose.yml exec api python -m eval.generate_summary_report

echo "Starting dashboard..."
docker-compose -f infra/docker-compose.yml up -d dashboard

echo ""
echo "Done. Dashboard: http://localhost:5173"
echo "Summary report: ./summary_report.json"
```

Make it executable (`chmod +x run_demo.sh`) and reference it as the first
line of your README's "How to run this" section — literally: `./run_demo.sh`
and nothing else.

## Test to write

```python
def test_summary_report_has_zero_compliance_violations_by_construction(db_session):
    """This is the test that makes the proof pack's central compliance
    claim verifiable, not just asserted in a JSON file."""
    run = run_batch(db_session, dataset_seed=1, n=200, policy_name="bandit", policy=fresh_bandit())
    report = generate_summary_report(db_session, run.run_id, baseline_run_id=...)
    assert report["compliance"]["compliance_violations"] == 0
```

## What to say in the demo

*"Rather than ask you to trust a claim, running `./run_demo.sh` reproduces
our entire result from scratch — migrations, batch evaluation across
multiple seeds, and this exact summary report, in one command. Every
number here, including our zero compliance violations, is computed from
the run you just watched happen, not something we're asserting."*
