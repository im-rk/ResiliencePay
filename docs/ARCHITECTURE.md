# Architecture

## 1. High-level pipeline

```
                    ┌─────────────────────────────────────────────────────┐
                    │                 EVENT SOURCE                        │
                    │  Synthetic generator  +  Razorpay test-mode webhooks│
                    └───────────────────────┬─────────────────────────────┘
                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  DIAGNOSE                                           │
                    │  Rule-based mapping of gateway error code → cause   │
                    │  + LLM fallback for ambiguous/free-text reasons     │
                    └───────────────────────┬─────────────────────────────┘
                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  DECIDE  (the novelty core)                         │
                    │  Contextual bandit (Thompson Sampling)              │
                    │  context → arm (intervention + timing)              │
                    └───────────────────────┬─────────────────────────────┘
                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  GATE  (stopping-rule / compliance engine)          │
                    │  max attempts, cool-off, opt-out/decline = terminal │
                    └───────────────────────┬─────────────────────────────┘
                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  ACT                                                │
                    │  Real: Razorpay test-mode retry / payment link      │
                    │  Simulated (labeled): nudge message via LLM         │
                    └───────────────────────┬─────────────────────────────┘
                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  OBSERVE                                            │
                    │  Outcome captured → reward computed → fed to bandit │
                    └───────────────────────┬─────────────────────────────┘
                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  AUDIT TRAIL (append-only log)                      │
                    │  event → diagnosis → decision → gate result →       │
                    │  action → outcome, all timestamped                  │
                    └───────────────────────┬─────────────────────────────┘
                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  DASHBOARD                                          │
                    │  live feed · metrics · learning curve · exceptions  │
                    └─────────────────────────────────────────────────────┘
```

## 2. Component breakdown

### 2.1 Event Source
- **Synthetic generator**: produces failed-payment / failed-mandate /
  abandoned-checkout events with realistic field distributions (see
  `DATA_MODEL.md`).
- **Razorpay test-mode**: where feasible, real test-mode payment failures are
  triggered via the Razorpay API/dashboard to prove genuine integration, not
  just simulation.

### 2.2 Diagnose
- Deterministic rule table: gateway error code → cause category. This is the
  first line — fast, free, and auditable.
- LLM fallback: only invoked when the error text/code doesn't match a known
  rule, to classify ambiguous cases and produce a human-readable explanation.
- Output: `{cause_category, confidence, raw_reason}`.

### 2.3 Decide
- Contextual bandit (see `ML_DESIGN.md` for full spec).
- Input context vector: cause category, amount bucket, customer segment,
  retry count so far, hour of day, day of week, past nudge channel success
  for this customer.
- Output: chosen arm = `{intervention_type, delay_before_action}`.
- Policy state (arm statistics) persisted so it visibly improves across the
  batch run — this is what the learning-curve chart is built from.

### 2.4 Gate (stopping-rule engine)
- Independent of the bandit — this is a **hard rule layer**, not learned,
  because compliance/safety logic should not be probabilistic.
- Rules (examples):
  - Max 3 automated retry attempts per failure episode.
  - Minimum cool-off of N hours between attempts.
  - Explicit customer decline or opt-out → permanent stop for that customer/episode.
  - No nudge sent outside a reasonable local-time window.
- If the gate blocks an action, that's logged as a distinct outcome
  (`blocked_by_policy`), not silently dropped.

### 2.5 Act
- **Real actions** (Razorpay test-mode): re-attempt a payment, generate a
  fresh payment link for an expired/failed method.
- **Simulated actions** (clearly labeled `simulated: true` in the audit
  trail and UI): SMS/WhatsApp-style nudge text, generated by an LLM,
  optionally in Hinglish, with a "promise to pay" capture prompt for B2B
  cases.

### 2.6 Observe
- Captures the outcome of an action (recovered / not recovered / pending /
  customer declined).
- Converts outcome into a reward signal fed back into the bandit
  (`reward = 1` if recovered within the attempt's time window, else `0`,
  with an optional partial-credit shaping — see `ML_DESIGN.md`).

### 2.7 Audit Trail
- Append-only structured log (JSON records or a simple relational table).
- Every record: `event_id, timestamp, cause_category, confidence, chosen_arm,
  gate_result, action_taken, simulated_flag, outcome, reward`.
- This is the artifact that answers "explainable, bounded, gated" directly —
  make it filterable/searchable in the dashboard, not just a raw log dump.

### 2.8 Dashboard
- Live/animated event feed (detect → diagnose → decide → act → outcome).
- Metrics panel: recovery rate, ₹ recovered, lift vs. baseline.
- Bandit learning curve (recovery rate over time / over batch index).
- Exception list: events the agent could not resolve, with reasons.
- Audit trail table with filters (by cause, by arm, by outcome).

## 3. Suggested tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python (FastAPI) or Node (Express) | Fast to build, good Razorpay SDK support in both |
| Bandit / diagnosis logic | Python | Cleaner numerical libraries (numpy) for Thompson Sampling |
| LLM calls | Anthropic API (Claude) | For diagnosis fallback + nudge message generation |
| Data store | SQLite or a JSON file store | No need for a heavy DB at hackathon scale |
| Frontend | React + a charting library (Recharts) | Fast to build a convincing live dashboard |
| Payments | Razorpay test-mode SDK | Required by the track |

## 4. Data flow guarantee

No step is allowed to mutate state outside its own boundary — Decide never
calls Act directly; it must pass through Gate. This separation is itself a
demo talking point: "the learning component cannot override the compliance
layer," which is precisely what "bounded and gated" is asking for.
