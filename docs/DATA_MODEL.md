# Data Model — Synthetic Event Dataset

## 1. Why synthetic data

Razorpay does not provide a production dataset for this hackathon — the
tracks explicitly reference "synthetic data" (Track 04) and "batch"
(Track 03). You are expected to generate realistic data yourselves, ideally
shaped to match real Razorpay API/webhook payload structures so the pipeline
generalizes to real data later.

## 2. Core event schema — `FailedPaymentEvent`

```json
{
  "event_id": "evt_9f3a2b",
  "merchant_id": "merch_demo01",
  "customer_id": "cust_1029",
  "episode_id": "epi_5521",          // groups retries of the same underlying failure
  "event_type": "subscription_charge_failed",  // or "payment_failed", "checkout_abandoned"
  "timestamp": "2026-08-20T09:14:00+05:30",
  "amount": 149900,                    // in paise, Razorpay convention
  "currency": "INR",
  "payment_method": "card",           // card | upi | netbanking | emandate
  "gateway_error_code": "BAD_REQUEST_PAYMENT_CARD_INSUFFICIENT_FUNDS",
  "raw_gateway_message": "Insufficient funds in the account.",
  "customer_segment": "returning_high_value",  // new | returning_low_value | returning_high_value | churn_risk
  "retry_count_so_far": 0,
  "mandate_status": "active",         // for subscription events
  "customer_locale": "hi-IN",
  "customer_opted_out": false
}
```

## 3. Cause category taxonomy (for the Diagnose step)

| Cause category | Example gateway codes | Typically recoverable? |
|---|---|---|
| `insufficient_funds` | INSUFFICIENT_FUNDS | Yes, with delay (payday timing) |
| `expired_card` | CARD_EXPIRED | Yes, needs card-update link |
| `otp_failure` | OTP_TIMED_OUT, OTP_INCORRECT | Yes, near-immediate retry |
| `bank_timeout` | GATEWAY_TIMEOUT, ISSUER_UNAVAILABLE | Yes, short-delay retry |
| `mandate_inactive` | MANDATE_NOT_ACTIVE, MANDATE_PAUSED | Needs re-authorization, not a blind retry |
| `hard_decline` | DO_NOT_HONOR, CARD_BLOCKED | Low recoverability — route to alternate method nudge, not retry |
| `customer_cancelled` | USER_CANCELLED | Not recoverable via retry — respect and stop |
| `unknown` | anything unmapped | Route to LLM classifier |

Deliberately include a **realistic mix**, including some genuinely
unrecoverable cases (`customer_cancelled`, repeated `hard_decline`) — a
dataset where everything is recoverable will look fabricated to judges.

## 4. Suggested distribution for a 200-event batch

| Cause category | % of batch | Recoverable ceiling (ballpark, for your own sanity check) |
|---|---|---|
| insufficient_funds | 30% | ~70% |
| expired_card | 15% | ~55% |
| otp_failure | 15% | ~85% |
| bank_timeout | 15% | ~75% |
| mandate_inactive | 10% | ~40% |
| hard_decline | 10% | ~15% |
| customer_cancelled | 5% | ~0% |

These numbers are illustrative starting points, not claims to present as-is
— tune them, add noise, and be ready to explain your reasoning if asked.

## 5. Outcome / label schema — `RecoveryOutcome`

Generated *after* an action is taken (either by your simulation logic during
batch eval, or by the actual pipeline during a live run):

```json
{
  "event_id": "evt_9f3a2b",
  "action_taken": "retry_in_3_days",
  "simulated": false,
  "outcome": "recovered",            // recovered | not_recovered | pending | blocked_by_policy
  "amount_recovered": 149900,
  "time_to_resolution_hours": 71.5,
  "reward": 1
}
```

## 6. Data generation guidelines

1. Use a proper random seed and document it — reproducibility matters if a
   judge asks "can you run this again."
2. Correlate outcome probability with cause category (see table above) but
   add noise — don't make outcomes deterministic given the cause.
3. Include a `customer_opted_out` flag on ~5% of customers to exercise and
   demonstrate the stopping-rule engine explicitly.
4. Timestamp events across a realistic time range (e.g., a 14-day window)
   so the "learning curve over time" chart has something to show.
5. Keep amounts realistic for the assumed merchant vertical (e.g., a SaaS
   subscription merchant: ₹499–₹4999 range; a D2C merchant: wider range).

## 7. Mapping to real Razorpay fields

When you do trigger real test-mode payments, capture the actual response
shape from Razorpay's `payment.failed` / `subscription.charge.failed`
webhook events and reconcile your synthetic schema field names to match
theirs exactly. This one detail — schema parity with the real API — is a
strong, cheap signal to judges that this isn't just a toy simulation.
