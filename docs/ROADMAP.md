# 10-Day Roadmap

Assumes a mixed product+ML team. Adjust owners to your actual headcount —
if you're 2-3 people, several rows collapse onto the same person.

## Day 1 — Lock scope, set up accounts, finalize schemas
- [ ] Finalize this doc set (PRD, architecture, data model) as the team's
      shared source of truth — no code until everyone's read `PRD.md`.
- [ ] Create Razorpay test-mode account, get API keys, explore Payments /
      Subscriptions / Payment Links / Webhooks in their dashboard.
- [ ] Repo scaffolding per `ARCHITECTURE.md` structure.
- [ ] Assign owners: Diagnose+Data, Decide (bandit), Act+API integration,
      Dashboard.

## Day 2 — Data generator + rule-based diagnosis
- [ ] Build `data/generator.py` producing 200+ events per `DATA_MODEL.md`.
- [ ] Build the rule-based cause-category lookup table.
- [ ] Stub the LLM fallback call (don't over-invest yet — get the happy
      path working first).

## Day 3 — Gate + Act (real Razorpay integration)
- [ ] Build the stopping-rule engine (`Gate`) with unit tests from
      `TESTING_METRICS.md` §6.
- [ ] Wire real Razorpay test-mode calls for retry/payment-link creation.
- [ ] Build the simulated-nudge module (LLM call, Hinglish/English,
      clearly flagged `simulated: true`).

## Day 4 — Bandit implementation
- [ ] Implement bucketed Thompson Sampling per `ML_DESIGN.md` §2.4.
- [ ] Seed priors from rule-table intuition.
- [ ] Unit test arm-statistics update logic.

## Day 5 — Wire the full pipeline end-to-end
- [ ] Connect Diagnose → Decide → Gate → Act → Observe → Audit for a single
      event, run it manually, verify every audit field populates correctly.
- [ ] Fix integration bugs — budget the whole day for this, it always takes
      longer than expected.

## Day 6 — Batch evaluation
- [ ] Build `eval/run_batch.py` (agent policy) and `eval/baseline.py`
      (naive policy) using the same seed.
- [ ] Run both over the full synthetic dataset.
- [ ] Compute all metrics from `TESTING_METRICS.md` §3–4.
- [ ] Sanity-check: does the exception list look realistic? Does the lift
      number look defensible, not too good to be true?

## Day 7 — Dashboard, part 1
- [ ] Live event feed view.
- [ ] Metrics summary panel (baseline vs agent table).
- [ ] Audit trail table with filters.

## Day 8 — Dashboard, part 2
- [ ] Learning curve chart (recovery rate over batch index).
- [ ] Arm distribution shift chart.
- [ ] Exception list view.
- [ ] Visual styling pass — this is what judges see first, don't neglect it.

## Day 9 — Demo rehearsal + hardening
- [ ] Run through `DEMO_SCRIPT.md` at least 3 times as a team, timed.
- [ ] Deliberately break one live API call to test your fallback plan.
- [ ] Prepare the one-pager (architecture diagram + honest real-vs-simulated
      callout) for submission.
- [ ] Load-test the batch run one more time — cache the results in case of
      live demo API flakiness.

## Day 10 — Final polish + submission
- [ ] Final demo run-through.
- [ ] Submit via the form: https://forms.gle/d9r2gvxp8cmoZhon9
- [ ] Prepare 1-2 backup team members to answer technical questions on the
      bandit design and the Gate/compliance logic specifically — these are
      the questions most likely to come from a technically sharp judge.

## Definition of done for the hackathon submission
- [ ] Full pipeline runs end-to-end on a live-triggered event.
- [ ] Batch evaluation numbers are reproducible from a documented seed.
- [ ] Dashboard shows: live feed, metrics table, learning curve, exception
      list, audit trail.
- [ ] Every simulated action is visibly labeled as simulated.
- [ ] At least one explicit "graceful failure / stopping rule respected"
      case is demonstrable on request.
- [ ] All doc files in this set are up to date with what was actually built
      (a PRD that doesn't match the product is worse than no PRD).
