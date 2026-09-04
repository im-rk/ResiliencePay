# Implementation Guide — Step by Step

This translates `ARCHITECTURE.md`, `DATABASE_DESIGN.md`, `ML_DESIGN.md`, and
`TECH_STACK.md` into an exact build order. Follow it top to bottom — each
step assumes the previous ones exist and work.

---

## Phase 0 — Environment setup (Day 1, ~2 hrs)

1. `git init resiliencepay && cd resiliencepay`
2. Create the repo skeleton exactly as in `README.md` §"Suggested repo structure."
3. `docker-compose.yml` with services: `api` (FastAPI), `worker` (Celery),
   `postgres`, `redis`, `frontend`.
4. `.env.example` with placeholders: `DATABASE_URL`, `REDIS_URL`,
   `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `ANTHROPIC_API_KEY`.
5. `docker-compose up` should bring up empty Postgres + Redis successfully
   before you write any business logic. Confirm this works first.

## Phase 1 — Database (Day 1-2)

1. Set up SQLAlchemy models mirroring every table in `DATABASE_DESIGN.md`
   §2, one file per logical group: `models/merchant.py`,
   `models/episode.py`, `models/decision.py`, `models/outcome.py`, etc.
2. Initialize Alembic: `alembic init alembic`.
3. Generate and run the first migration containing all tables + seed data
   for `cause_categories` and `arms` (as `INSERT` statements in a data
   migration, not hardcoded in application code).
4. Write one smoke test: insert a merchant, a customer, an episode, an
   event — confirm foreign keys and constraints behave as designed
   (e.g., `chk_episode_amount` rejects a zero/negative amount).

**Checkpoint:** `pytest tests/test_db_smoke.py` passes against a real
Postgres instance in Docker.

## Phase 2 — Synthetic data generator (Day 2)

1. `data/generator.py`: implement per `DATA_MODEL.md` — takes a seed and a
   count, returns a list of event dicts matching the `FailedPaymentEvent`
   schema, following the cause-category distribution table.
2. Write it to insert directly into `merchants → customers → episodes →
   events` (not a flat JSON dump) so the generator exercises your real
   schema from day one, catching FK/constraint issues early.
3. Include the 5% `customer_opted_out` cohort and a handful of
   `customer_cancelled` (unrecoverable) cases explicitly.

**Checkpoint:** running the generator twice with the same seed produces
byte-identical output (reproducibility).

## Phase 3 — Diagnose (Day 2-3)

1. `src/diagnose/rules.py`: the static `gateway_error_code → cause_category`
   dictionary from `DATA_MODEL.md` §3.
2. `src/diagnose/llm_fallback.py`: thin wrapper around the Anthropic API
   with the constrained classification prompt from `ML_DESIGN.md` §1.
3. `src/diagnose/service.py`: orchestrates — try rules first, fall back to
   LLM, write a row to `diagnoses`.
4. Unit tests: every code in your synthetic dataset's cause distribution
   resolves via the rule path (fallback path exercised only by a
   deliberately-unmapped test code).

**Checkpoint:** for 100 synthetic events, 0% land in `unknown` unless
deliberately constructed to.

## Phase 4 — Gate (compliance engine) (Day 3)

Build this **before** the bandit, even though it logically sits after
Decide in the pipeline — you want the hard rules locked and tested first so
the bandit is developed against a known-safe boundary, not the other way
around.

1. `src/gate/rules.py`: pure functions, each takes context + proposed arm,
   returns `pass` or `(blocked, rule_name)`.
   - `check_max_attempts(episode, max_attempts=3)`
   - `check_cool_off(last_action_time, min_gap_hours)`
   - `check_opt_out(customer_id)`
   - `check_time_window(now, allowed_hours=(9,20))`
2. `src/gate/service.py`: runs all checks in sequence, writes a
   `gate_checks` row regardless of outcome.
3. Unit tests directly from `TESTING_METRICS.md` §6 (max-attempts always
   blocks, opt-out always blocks, regardless of what's passed in as the
   proposed arm).

**Checkpoint:** gate unit tests pass with 100% coverage of the four rules
above, including adversarial inputs (e.g., attempt #4 with a "high
confidence" bandit score should still block).

## Phase 5 — Bandit (Decide) (Day 4)

1. `src/decide/bandit.py`: implement bucketed Thompson Sampling exactly per
   `ML_DESIGN.md` §2.4 — `sample_arm(context_bucket) -> arm_name`,
   `update(context_bucket, arm_name, reward)`.
2. Back the live α/β state with Redis (`HINCRBYFLOAT` for updates), with a
   scheduled job (Celery beat, or a simple cron in `worker/`) that snapshots
   state into `bandit_arm_stats` every N minutes for durability.
3. Seed initial priors per `ML_DESIGN.md` §2.6 (favorable priors for
   intuitive cause→arm pairings) via a data migration or a seed script.
4. `src/decide/service.py`: builds the context bucket string from an
   event's diagnosis + episode + customer fields, calls `sample_arm`, writes
   a `decisions` row with the sampled score and α/β at decision time (for
   auditability).

**Checkpoint:** unit test that repeatedly rewarding one arm for a fixed
context bucket increases its selection probability over 500 simulated
trials (a statistical, not exact, assertion — use a tolerance).

## Phase 6 — Act (Day 3-4, parallel with Gate/Bandit)

1. `src/act/razorpay_client.py`: thin wrapper over the Razorpay Python SDK,
   test-mode keys only, functions: `create_retry_payment_link(episode)`,
   `get_payment_status(payment_id)`.
2. `src/act/nudge.py`: LLM call to generate nudge text (Hinglish/English),
   always tags the resulting `actions` row `simulated=true`.
3. `src/act/service.py`: given a `decision_id` that passed the gate, resolve
   `arm_name` → real API call or simulated message, write an `actions` row.
4. For delayed arms (`retry_short_delay`, `retry_long_delay`), enqueue a
   Celery task scheduled for the appropriate future time rather than
   blocking.

**Checkpoint:** triggering one synthetic `insufficient_funds` event through
the full Diagnose→Decide→Gate→Act chain produces one row in each of
`diagnoses`, `decisions`, `gate_checks`, `actions`.

## Phase 7 — Observe + reward loop (Day 5)

1. `src/observe/service.py`: for real Razorpay actions, poll
   `get_payment_status` (or better, handle the `payment.captured` webhook);
   for simulated nudges, use the outcome-probability logic from your
   synthetic dataset design to generate a plausible outcome in batch-eval
   mode, or a manual "mark resolved" trigger in live-demo mode.
2. Writes `outcomes` row, computes `reward`, calls
   `bandit.update(context_bucket, arm_name, reward)`.
3. Writes the corresponding `audit_log` row (see Phase 9).

**Checkpoint:** running one event through the full loop results in the
bandit's α/β for that `(context_bucket, arm)` changing measurably.

## Phase 8 — Batch evaluation harness (Day 6)

1. `eval/baseline.py`: implements the naive policy — always
   `retry_immediate`, once, no bandit, no personalization — reusing the same
   Gate and Act/Observe machinery so the comparison is fair (only Decide
   differs).
2. `eval/run_batch.py`: loads a synthetic dataset, runs it through either
   policy end-to-end, writes a `batch_runs` + `batch_run_metrics` row.
3. Compute all metrics from `TESTING_METRICS.md` §3-4 as a SQL aggregation
   query over `episodes`/`outcomes`/`gate_checks`, not ad hoc Python
   counting — this makes your numbers independently re-verifiable by anyone
   with DB access.

**Checkpoint:** two `batch_runs` rows exist (bandit, baseline) over the
identical dataset+seed, with a visibly different `recovery_rate`.

## Phase 9 — Audit log + API (Day 5-7)

1. Either a Postgres trigger on `outcomes` INSERT that writes a joined
   denormalized row into `audit_log`, or an application-level write-through
   in `observe/service.py` — pick the trigger approach if you want to show
   off DB-level rigor, the app-level approach if you want faster iteration.
2. Implement the endpoints from `API_SPEC.md` §1 in FastAPI, with automatic
   OpenAPI docs enabled (`/docs`) — free, zero-effort API documentation
   artifact.

**Checkpoint:** `GET /audit-trail?episode_id=...` returns the complete,
correctly-ordered history for a single episode.

## Phase 10 — Dashboard (Day 7-8)

1. Live event feed: poll `GET /events?since=...` or use a WebSocket if time
   allows (polling is fine, don't over-engineer).
2. Metrics panel: `GET /metrics/summary?run_id=...` rendered as the
   before/after table from `TESTING_METRICS.md` §7.
3. Learning curve + arm distribution: Recharts line/area charts fed by a
   `GET /metrics/learning-curve?run_id=...` endpoint (bucket outcomes by
   batch index, compute rolling recovery rate).
4. Exception list + audit trail table, both filterable.

**Checkpoint:** a fresh `docker-compose up` + a batch run produces a fully
populated dashboard with no manual data seeding beyond running Phase 2's
generator and Phase 8's batch script.

## Phase 11 — Rehearsal & hardening (Day 9)

1. Run `DEMO_SCRIPT.md` live, end to end, at least 3 times.
2. Deliberately kill the Razorpay API connection mid-demo once, confirm
   your fallback messaging/UI state (from `API_SPEC.md` §4's error contract)
   degrades gracefully rather than crashing the UI.
3. Cache one full batch run's output as a static JSON fallback in case of
   live infra flakiness on demo day.

## Phase 12 — Submission (Day 10)

1. Final README pass — make sure `docker-compose up` truly is the entire
   setup story, tested on a clean machine/VM if possible.
2. Submit via https://forms.gle/d9r2gvxp8cmoZhon9 with the repo link, a
   short writeup (pull directly from `PRD.md` §1-2 and `TESTING_METRICS.md`
   §7's results table), and a demo video/link if required.

---

## Suggested team split (if 4 people)

| Person | Owns |
|---|---|
| A | Phases 1-2 (DB + data generator), Phase 8 (eval harness) |
| B | Phases 3-4 (Diagnose + Gate) |
| C | Phases 5-6 (Bandit + Act/Razorpay integration) |
| D | Phases 9-10 (API + Dashboard) |

Phase 7 (Observe) and Phase 11 (rehearsal) are whole-team checkpoints —
don't let one person own the integration glue alone, it's where most
hackathon time is silently lost.
