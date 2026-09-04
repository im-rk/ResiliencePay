# API Specification

## 1. Internal service API

### `POST /events/ingest`
Ingests a new failure event (from synthetic generator or a real Razorpay
webhook receiver).

**Request**
```json
{
  "event_type": "subscription_charge_failed",
  "merchant_id": "merch_demo01",
  "customer_id": "cust_1029",
  "amount": 149900,
  "currency": "INR",
  "gateway_error_code": "BAD_REQUEST_PAYMENT_CARD_INSUFFICIENT_FUNDS",
  "raw_gateway_message": "Insufficient funds in the account.",
  "customer_segment": "returning_high_value",
  "retry_count_so_far": 0
}
```

**Response `202 Accepted`**
```json
{ "event_id": "evt_9f3a2b", "status": "queued_for_diagnosis" }
```

### `GET /events/{event_id}`
Returns full pipeline state for one event: diagnosis, chosen arm, gate
result, action, outcome.

### `POST /pipeline/run-batch`
Triggers a full batch run over a stored synthetic dataset. Used for the
offline evaluation, not per-event production flow.

**Request**
```json
{ "dataset_path": "data/synthetic_events.json", "policy": "bandit" }
```
`policy` can be `bandit` or `baseline` — this is how you generate the
comparison numbers.

**Response**
```json
{
  "run_id": "run_20260824_01",
  "n_events": 200,
  "recovery_rate": 0.47,
  "amount_recovered": 8123400,
  "exceptions": 18
}
```

### `GET /metrics/summary?run_id=...`
Returns the full metrics payload for a completed run (see
`TESTING_METRICS.md` for the exact fields expected).

### `GET /audit-trail?filter=...`
Returns filterable audit log records for the dashboard table.

## 2. Razorpay test-mode endpoints used

| Purpose | Razorpay endpoint | Notes |
|---|---|---|
| Create a payment retry / new payment link | `POST /v1/payment_links` | Use test-mode key; amount in paise |
| Fetch payment status | `GET /v1/payments/{id}` | Poll to observe outcome after a retry |
| Subscription details / mandate status | `GET /v1/subscriptions/{id}` | Used to check `mandate_inactive` cases |
| Webhook receiver | Your own endpoint, registered in Razorpay test-mode dashboard | Listen for `payment.failed`, `subscription.charge.failed` |

**Auth:** test-mode `key_id` / `key_secret` from the Razorpay dashboard,
stored as environment variables, never committed to the repo.

**Important:** every real Razorpay call in the audit trail should be tagged
`simulated: false`; every LLM-generated nudge or message should be tagged
`simulated: true`. This distinction must be visible in the dashboard, not
just in logs — it's your credibility safeguard with judges.

## 3. LLM API usage

Two distinct call types — keep them architecturally separate so each is easy
to test and audit independently:

1. **Diagnosis fallback** — classification call, constrained output, low
   temperature, logged with its justification string.
2. **Nudge generation** — creative call (Hinglish/English message text),
   higher temperature acceptable, always logged verbatim as `simulated: true`
   content in the audit trail.

## 4. Error handling contract

Every API in this system must return a structured error, never a silent
failure:

```json
{ "error": true, "code": "GATE_BLOCKED", "reason": "max_attempts_exceeded", "event_id": "evt_9f3a2b" }
```

This is what lets you show "one failure handled gracefully" live — a
blocked/failed action should be a visible, labeled state in the UI, not a
crash or a silently dropped event.
