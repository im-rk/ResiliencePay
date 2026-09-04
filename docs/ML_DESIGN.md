# ML Design — Diagnosis & Decision Engine

## 1. Diagnose: failure-cause classification

**Primary path — rule-based lookup.** A static dictionary mapping known
gateway error codes to cause categories (see `DATA_MODEL.md` §3). This
should resolve 80%+ of events instantly, deterministically, and with zero
inference cost — and it's trivially explainable, which matters for the
"explainable" requirement.

**Fallback path — LLM classification.** For unmapped/free-text error
messages, call an LLM with a constrained prompt:

```
Given this payment gateway error message, classify it into exactly one of:
[insufficient_funds, expired_card, otp_failure, bank_timeout,
 mandate_inactive, hard_decline, customer_cancelled, unknown]
Return only the category and a one-sentence justification.
Message: "{raw_gateway_message}"
```

Log the LLM's justification in the audit trail — this becomes a nice
explainability artifact in the dashboard ("why did the agent think this was
recoverable?").

## 2. Decide: contextual bandit

### 2.1 Why a bandit, not a fixed rule table or a plain LLM call

A fixed rule table can't improve — it encodes today's guess as gospel
forever. A raw LLM call for the decision step is unauditable and
non-reproducible (same input can yield different output) and is hard to
justify as "learning from real outcomes." A **contextual bandit** is the
right tool because:
- It starts from a reasonable prior (can be seeded with your rule-table
  intuition) and provably improves as it observes real outcomes.
- It's fully auditable — you can always report "arm X was chosen because
  its expected reward given this context was highest," with actual numbers.
- It's a well-established, standard technique (not a research risk) — the
  novelty is in *applying* it here, not in inventing new theory.

### 2.2 Arms (the actions the bandit chooses between)

| Arm | Description |
|---|---|
| `retry_immediate` | Retry the charge within minutes |
| `retry_short_delay` | Retry in ~2–6 hours |
| `retry_long_delay` | Retry in ~2–3 days (e.g., for insufficient funds, aligned to likely payday) |
| `send_card_update_link` | Simulated nudge with a link to update payment method |
| `send_nudge_hinglish` | Simulated Hinglish reminder message |
| `send_nudge_english` | Simulated English reminder message |
| `escalate_human` | Flag for manual follow-up (used sparingly, high-value/high-risk cases) |
| `stop` | No further action (used when confidence of recovery is very low) |

### 2.3 Context features (the "contextual" part)

`[cause_category (one-hot), amount_bucket, customer_segment (one-hot),
retry_count_so_far, hour_of_day_bucket, day_of_week, prior_channel_success_rate_for_customer]`

### 2.4 Algorithm — Thompson Sampling (recommended)

For each arm, maintain a Beta(α, β) distribution over its success
probability, conditioned on context via a simple linear contextual
extension (or, if time is short, maintain separate Beta distributions per
`(cause_category, arm)` bucket — a simpler, still-legitimate contextual
bandit formulation that's easy to implement and easy to explain to judges).

```
For each incoming event with context c:
  For each arm a:
    sample θ_a ~ Beta(α[c_bucket, a], β[c_bucket, a])
  choose arm* = argmax_a θ_a
  execute arm* (after passing the Gate)
  observe reward r ∈ {0, 1}
  update: α[c_bucket, arm*] += r ; β[c_bucket, arm*] += (1 - r)
```

This is deliberately simple — a bucketed Thompson Sampling bandit — because
it is (a) fast to implement correctly, (b) easy to visualize (arm success
rates over time), and (c) easy to explain live to judges without hand-waving.
A LinUCB (linear contextual bandit) is a valid stretch upgrade if time
allows, but bucketed Thompson Sampling is the safer 10-day choice.

### 2.5 Reward function

```
reward = 1.0   if payment recovered within the attempt's resolution window
reward = 0.0   if not recovered / customer declined
reward = -0.1  if the action was blocked by the Gate for a preventable reason
                (small penalty to discourage the bandit from favoring
                 arms that frequently violate policy, even though Gate
                 already blocks them — this keeps the incentive aligned)
```

Optional shaping: partial credit for faster recovery
(`reward = 1.0 * decay(time_to_resolution)`) if you want the learning curve
to also reflect speed, not just success/failure. Keep this optional — it
adds complexity that isn't necessary to hit the track's bar.

### 2.6 Seeding the prior

Initialize `α, β` using your rule-table intuition (e.g., `otp_failure` +
`retry_immediate` gets a favorable prior) rather than a uniform prior. This
is both good ML practice (informative priors reduce early-batch
regret) and a good demo point ("we didn't start from zero — we encoded
domain knowledge, then let it learn from real outcomes").

## 3. What "the bandit learned something" looks like in the demo

Plot **cumulative recovery rate vs. batch index** for:
1. The bandit policy (should trend upward and stabilize above baseline).
2. The naive baseline (flat, same-day-retry-only line).

Also plot **arm selection distribution over time** (e.g., a stacked area
chart) — showing the bandit shifting away from a poor-performing arm for a
given cause category as it learns is one of the most convincing visuals you
can show.

## 4. Evaluation notes (see `TESTING_METRICS.md` for full detail)

Run the same synthetic batch through both the bandit policy and the naive
baseline using the same random seed for outcome generation, so the
comparison is apples-to-apples. Report both absolute recovery rate and lift.
