# Database Design — ResiliencePay

**Engine:** PostgreSQL 16. All money stored as integer paise (never float).
All timestamps stored as `timestamptz` (UTC), converted at the display layer.

## 1. Entity-relationship overview

```
merchants ──< customers ──< episodes ──< events ──< audit_log
                                │             │
                                │             └──< actions ──< outcomes
                                │
                                └──< opt_outs

bandit_arm_stats (independent, keyed by context_bucket + arm)
batch_runs ──< batch_run_metrics
```

**Design rationale:** the domain has a natural hierarchy —
`merchant → customer → episode → event → action → outcome`. An **episode**
groups the sequence of retry attempts for one underlying failure (e.g., one
failed subscription charge might spawn 3 events/actions before it resolves).
This hierarchy is what makes multi-attempt recovery queryable and
auditable, instead of flattening everything into one wide table.

## 2. Core tables

### `merchants`
```sql
CREATE TABLE merchants (
    merchant_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    razorpay_key_id TEXT NOT NULL,       -- test-mode key reference, not the secret
    vertical        TEXT NOT NULL,       -- 'saas_subscription' | 'd2c' | 'b2b_receivables'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `customers`
```sql
CREATE TABLE customers (
    customer_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id     UUID NOT NULL REFERENCES merchants(merchant_id) ON DELETE CASCADE,
    external_ref    TEXT,                 -- Razorpay customer id, if real
    segment         TEXT NOT NULL,        -- 'new' | 'returning_low_value' | 'returning_high_value' | 'churn_risk'
    locale          TEXT NOT NULL DEFAULT 'en-IN',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (merchant_id, external_ref)
);
CREATE INDEX idx_customers_merchant ON customers(merchant_id);
```

### `opt_outs`
Separate table (not a boolean flag on `customers`) so opt-outs are
timestamped, auditable, and reversible-with-history rather than a silent
mutable flag.
```sql
CREATE TABLE opt_outs (
    opt_out_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     UUID NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    scope           TEXT NOT NULL DEFAULT 'all_recovery_comms', -- allows future granularity, e.g. 'sms_only'
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_opt_outs_customer ON opt_outs(customer_id);
```

### `episodes`
One episode = one underlying revenue-at-risk incident, which may span
multiple retry attempts before resolving.
```sql
CREATE TABLE episodes (
    episode_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merchant_id      UUID NOT NULL REFERENCES merchants(merchant_id),
    customer_id      UUID NOT NULL REFERENCES customers(customer_id),
    episode_type     TEXT NOT NULL,        -- 'subscription_charge_failed' | 'payment_failed' | 'checkout_abandoned' | 'receivable_overdue'
    original_amount  BIGINT NOT NULL,      -- paise
    currency         CHAR(3) NOT NULL DEFAULT 'INR',
    status           TEXT NOT NULL DEFAULT 'open', -- 'open' | 'recovered' | 'unrecoverable' | 'blocked'
    opened_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at        TIMESTAMPTZ,
    CONSTRAINT chk_episode_amount CHECK (original_amount > 0)
);
CREATE INDEX idx_episodes_merchant_status ON episodes(merchant_id, status);
CREATE INDEX idx_episodes_customer ON episodes(customer_id);
```

### `events`
A raw incoming signal (a failure notification) — one episode can have
multiple events if the same underlying issue triggers repeatedly.
```sql
CREATE TABLE events (
    event_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id         UUID NOT NULL REFERENCES episodes(episode_id) ON DELETE CASCADE,
    event_type         TEXT NOT NULL,
    gateway_error_code TEXT,
    raw_gateway_message TEXT,
    payment_method     TEXT,               -- 'card' | 'upi' | 'netbanking' | 'emandate'
    retry_count_so_far INT NOT NULL DEFAULT 0,
    occurred_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_payload        JSONB,               -- full original webhook/synthetic payload, for forensic replay
    CONSTRAINT chk_retry_count CHECK (retry_count_so_far >= 0)
);
CREATE INDEX idx_events_episode ON events(episode_id);
CREATE INDEX idx_events_occurred_at ON events(occurred_at);
-- GIN index if you ever need to query inside raw_payload
CREATE INDEX idx_events_raw_payload_gin ON events USING GIN (raw_payload);
```

### `diagnoses`
Output of the Diagnose step — kept as its own table (not columns on
`events`) so you can re-diagnose or audit classifier version history.
```sql
CREATE TABLE diagnoses (
    diagnosis_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    cause_category  TEXT NOT NULL,       -- enum-like, see cause_categories table below
    confidence      NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    method          TEXT NOT NULL,       -- 'rule_based' | 'llm_fallback'
    justification   TEXT,                -- LLM explanation, null for rule-based
    model_version   TEXT,                -- e.g. 'claude-sonnet-4-6', null for rule-based
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_diagnoses_event ON diagnoses(event_id);
CREATE INDEX idx_diagnoses_cause ON diagnoses(cause_category);
```

### `cause_categories` (lookup table, not a hardcoded enum)
Using a lookup table instead of a Postgres `ENUM` type means adding a new
cause category is a data migration, not a schema migration — a real
production consideration.
```sql
CREATE TABLE cause_categories (
    cause_category   TEXT PRIMARY KEY,
    description      TEXT NOT NULL,
    typical_recoverable BOOLEAN NOT NULL DEFAULT true
);
INSERT INTO cause_categories VALUES
    ('insufficient_funds', 'Card/account lacked funds at charge time', true),
    ('expired_card', 'Card expired', true),
    ('otp_failure', 'OTP timeout or incorrect entry', true),
    ('bank_timeout', 'Issuer/gateway timeout', true),
    ('mandate_inactive', 'Subscription mandate not active/paused', true),
    ('hard_decline', 'Issuer hard decline (e.g. do-not-honor, blocked card)', false),
    ('customer_cancelled', 'Customer explicitly cancelled', false),
    ('unknown', 'Unclassified', true);
```

### `decisions`
Output of the Decide (bandit) step.
```sql
CREATE TABLE decisions (
    decision_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id          UUID NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    chosen_arm        TEXT NOT NULL,        -- see arms table
    context_bucket    TEXT NOT NULL,        -- serialized context key used for bandit lookup
    sampled_score      NUMERIC(6,5),         -- the θ sampled from Beta dist, for auditability
    alpha_at_decision  NUMERIC(10,4),
    beta_at_decision   NUMERIC(10,4),
    decided_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_decisions_event ON decisions(event_id);
CREATE INDEX idx_decisions_arm ON decisions(chosen_arm);
```

### `arms` (lookup table)
```sql
CREATE TABLE arms (
    arm_name        TEXT PRIMARY KEY,
    description     TEXT NOT NULL,
    is_real_action  BOOLEAN NOT NULL   -- false => simulated (nudge messages)
);
INSERT INTO arms VALUES
    ('retry_immediate', 'Retry charge within minutes', true),
    ('retry_short_delay', 'Retry in 2-6 hours', true),
    ('retry_long_delay', 'Retry in 2-3 days', true),
    ('send_card_update_link', 'Nudge with card-update link', false),
    ('send_nudge_hinglish', 'Hinglish reminder message', false),
    ('send_nudge_english', 'English reminder message', false),
    ('escalate_human', 'Flag for manual follow-up', false),
    ('stop', 'No further action', true);
```

### `gate_checks`
Records every pass/block decision from the compliance layer — this table is
what proves "bounded and gated" with real data, not just a claim.
```sql
CREATE TABLE gate_checks (
    gate_check_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id     UUID NOT NULL REFERENCES decisions(decision_id) ON DELETE CASCADE,
    result          TEXT NOT NULL,        -- 'passed' | 'blocked'
    rule_triggered  TEXT,                 -- e.g. 'max_attempts_exceeded', 'customer_opted_out', 'outside_time_window'
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_gate_checks_decision ON gate_checks(decision_id);
CREATE INDEX idx_gate_checks_result ON gate_checks(result);
```

### `actions`
An action only exists if the gate passed. `simulated` is a first-class,
always-visible column (never buried in JSON) precisely so it can't be
accidentally hidden from the audit UI.
```sql
CREATE TABLE actions (
    action_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id     UUID NOT NULL REFERENCES decisions(decision_id) ON DELETE CASCADE,
    arm_name        TEXT NOT NULL REFERENCES arms(arm_name),
    simulated       BOOLEAN NOT NULL,
    razorpay_ref_id TEXT,                 -- payment_link id / payment id, null if simulated
    message_text    TEXT,                 -- for nudge arms, the actual generated text
    scheduled_for   TIMESTAMPTZ,          -- for delayed retries
    executed_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'scheduled' -- 'scheduled' | 'executed' | 'failed'
);
CREATE INDEX idx_actions_decision ON actions(decision_id);
CREATE INDEX idx_actions_status_scheduled ON actions(status, scheduled_for);
```

### `outcomes`
The Observe step's output, and the source of the bandit's reward signal.
```sql
CREATE TABLE outcomes (
    outcome_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_id             UUID NOT NULL REFERENCES actions(action_id) ON DELETE CASCADE,
    result                TEXT NOT NULL,     -- 'recovered' | 'not_recovered' | 'pending' | 'blocked_by_policy'
    amount_recovered      BIGINT NOT NULL DEFAULT 0,
    reward                NUMERIC(4,3) NOT NULL,
    time_to_resolution_hrs NUMERIC(8,2),
    observed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_amount_recovered CHECK (amount_recovered >= 0)
);
CREATE INDEX idx_outcomes_action ON outcomes(action_id);
CREATE INDEX idx_outcomes_result ON outcomes(result);
```

### `bandit_arm_stats`
Durable snapshot of bandit state (hot path lives in Redis; this table is
the periodic persisted backstop — see `TECH_STACK.md`).
```sql
CREATE TABLE bandit_arm_stats (
    context_bucket  TEXT NOT NULL,
    arm_name        TEXT NOT NULL REFERENCES arms(arm_name),
    alpha           NUMERIC(12,4) NOT NULL DEFAULT 1.0,
    beta            NUMERIC(12,4) NOT NULL DEFAULT 1.0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (context_bucket, arm_name)
);
```

### `batch_runs` and `batch_run_metrics`
For the offline evaluation runs that produce your headline demo numbers.
```sql
CREATE TABLE batch_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy          TEXT NOT NULL,     -- 'bandit' | 'baseline'
    dataset_ref     TEXT NOT NULL,     -- path or hash of the synthetic dataset used
    random_seed     INT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ
);

CREATE TABLE batch_run_metrics (
    run_id                  UUID PRIMARY KEY REFERENCES batch_runs(run_id) ON DELETE CASCADE,
    n_events                INT NOT NULL,
    recovery_rate           NUMERIC(5,4) NOT NULL,
    amount_recovered        BIGINT NOT NULL,
    amount_at_risk          BIGINT NOT NULL,
    avg_time_to_recovery_hrs NUMERIC(8,2),
    exception_count         INT NOT NULL,
    gate_blocked_count      INT NOT NULL
);
```

### `audit_log`
The single append-only table the dashboard's audit trail view reads from —
denormalized on write for fast querying, sourced from the normalized tables
above via a database trigger or an application-level write-through.
```sql
CREATE TABLE audit_log (
    audit_id        BIGSERIAL PRIMARY KEY,
    event_id        UUID NOT NULL,
    episode_id      UUID NOT NULL,
    cause_category  TEXT,
    chosen_arm      TEXT,
    gate_result     TEXT,
    simulated       BOOLEAN,
    outcome_result  TEXT,
    reward          NUMERIC(4,3),
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_log_episode ON audit_log(episode_id);
CREATE INDEX idx_audit_log_recorded_at ON audit_log(recorded_at);
```
**Note:** `audit_log` is intentionally append-only — no `UPDATE` or `DELETE`
grants for the application role, enforced at the database permission level.
This is a real compliance pattern (immutable audit trail), not just a naming
convention, and it's a strong thing to mention if a judge asks about
trustworthiness.

## 3. Key design decisions worth explaining to judges

1. **Episode vs. Event separation.** Without this, you can't answer "how
   many total attempts did it take to recover this customer's payment,"
   which is exactly the kind of question a merchant would ask.
2. **Lookup tables (`cause_categories`, `arms`) instead of enums.** Adding a
   new recovery channel later is a data insert, not a migration + code
   redeploy — a genuine production flexibility consideration.
3. **`gate_checks` as its own table, not a boolean on `decisions`.** This
   makes "show me every time the compliance layer blocked an action, and
   why" a single indexed query — directly serving the track's "bounded and
   gated" requirement with real evidence.
4. **`simulated` as a non-nullable boolean on `actions`, not inferred from
   arm type.** Makes it structurally impossible for the dashboard to
   accidentally present a simulated action as real — a safeguard against
   your own team's mistakes under demo pressure, not just judges' scrutiny.
5. **Money as `BIGINT` paise everywhere, never `FLOAT`/`NUMERIC` for
   currency arithmetic in application code.** Floating-point money bugs are
   an instant credibility loss with any technically literate judge.
6. **Append-only audit_log with DB-level permission enforcement.** Shows
   you understand the difference between "we log things" and "we have an
   audit trail that can't be tampered with," which matters a great deal in
   fintech.

## 4. Indexing strategy summary

| Table | Index | Serves |
|---|---|---|
| `episodes` | `(merchant_id, status)` | Dashboard "open episodes" queries |
| `events` | `(occurred_at)` | Time-windowed batch/live-feed queries |
| `diagnoses` | `(cause_category)` | Cause-distribution charts |
| `decisions` | `(chosen_arm)` | Arm-distribution-over-time charts |
| `gate_checks` | `(result)` | Gate-blocked-rate metric |
| `actions` | `(status, scheduled_for)` | Worker polling for due delayed retries |
| `audit_log` | `(episode_id)`, `(recorded_at)` | Audit trail table filters + pagination |

## 5. Migration workflow

```bash
alembic revision --autogenerate -m "add gate_checks table"
alembic upgrade head
```
Every schema change ships as a versioned, reviewable migration file in
`alembic/versions/` — check this folder into git so its history is visible
proof of iterative, disciplined schema evolution, not a single dump.
