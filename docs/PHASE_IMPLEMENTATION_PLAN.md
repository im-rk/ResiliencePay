# Phase-by-Phase Engineering Implementation Plan — ResiliencePay

**Purpose of this document:** this is written the way a senior/staff engineer
would structure an internal design + execution doc before a sprint — every
phase has an explicit objective, the trade-offs considered (not just the
choice made), interface contracts, pseudocode, an edge-case matrix, a test
plan, and hard exit criteria. Nothing moves to the next phase until its exit
criteria are met. This discipline *is* the novelty signal for a hackathon —
most teams ship a demo; you're shipping a system with decision records.

**How to use this doc:** pair it with `IMPLEMENTATION_GUIDE.md` (the fast
build-order checklist) and `DATABASE_DESIGN.md` / `ML_DESIGN.md` (the
detailed specs). This document is the "why we built it this way" layer.

---

## Phase 0 — Foundations & Engineering Standards

### Objective
Establish the engineering scaffolding *before* any business logic, so every
subsequent phase inherits consistent standards instead of retrofitting them.

### Decisions & trade-offs
| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Monorepo vs. polyrepo | Split `api`/`worker`/`frontend` into 3 repos | **Monorepo** | 10-day hackathon — cross-cutting changes (schema → API → dashboard) need to land atomically; polyrepo versioning overhead isn't worth it at this scale |
| Config management | Hardcoded values, `.env` only, or a config service | **`.env` + Pydantic `Settings` class** | Type-validated config at startup fails fast on missing/malformed env vars instead of failing deep in a request handler |
| Branching strategy | Trunk-based, GitFlow | **Trunk-based with short-lived feature branches + PR review** | GitFlow's overhead isn't justified for a 4-person, 10-day build; trunk-based keeps everyone's work continuously integrated |
| Code review policy | No review (move fast), mandatory review | **Mandatory 1-reviewer PR approval, even at hackathon speed** | This is a cheap, high-signal thing to point to in your submission ("every PR was reviewed") and genuinely catches bugs in money-handling code |

### Deliverables
- `pydantic.BaseSettings` config class validating all required env vars at boot.
- `.pre-commit-config.yaml`: `black`, `ruff`, `mypy` (backend), `eslint`+`prettier` (frontend).
- GitHub Actions workflow: `lint → typecheck → test` on every PR, required to pass before merge.
- `CONTRIBUTING.md`: branch naming (`feat/…`, `fix/…`), commit message convention (Conventional Commits — free, readable git history).
- `docker-compose.yml` bringing up `api`, `worker`, `postgres`, `redis`, `frontend` with health checks on each service.

### Exit criteria
- [ ] `docker-compose up` succeeds from a clean clone with zero manual steps beyond copying `.env.example` → `.env`.
- [ ] A trivial PR (e.g., README typo fix) demonstrates the full CI pipeline green + requires review to merge.

---

## Phase 1 — Data Layer

### Objective
Stand up the schema in `DATABASE_DESIGN.md` with migrations, constraints,
and a seed/fixture strategy that later phases can rely on without ambiguity.

### Decisions & trade-offs
| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Schema evolution | Single `schema.sql` dump vs. incremental Alembic migrations | **Alembic, one migration per logical table group** | A visible migration history (`alembic/versions/`) is itself an artifact of disciplined engineering — free credibility, and it's how real production systems evolve schemas |
| Constraint enforcement | App-layer validation only vs. DB-layer `CHECK` constraints | **Both — DB is source of truth, app validates early for better error messages** | Defense in depth: a bug in app validation shouldn't be able to write a negative `amount` to the DB, full stop |
| Test data | Hand-written fixtures vs. factory pattern | **Factory pattern (`factory_boy`)** | Generates valid-by-construction test rows with sensible defaults, overridable per test — scales far better than hand-maintained fixture files as the schema grows |

### Interface contract
Every model exposes a `to_audit_dict()` method returning only the fields
relevant to audit logging — this becomes the single source of truth for what
the append-only `audit_log` table captures, so Phase 9 doesn't have to
guess which fields matter.

### Edge-case matrix (constraint-level)
| Case | Expected DB behavior |
|---|---|
| Insert episode with `original_amount = 0` | Rejected by `chk_episode_amount` |
| Insert event with `retry_count_so_far = -1` | Rejected by `chk_retry_count` |
| Insert outcome with `amount_recovered` negative | Rejected by `chk_amount_recovered` |
| Insert action referencing a non-existent `decision_id` | Rejected by FK constraint |
| Delete a customer with existing episodes | Cascades per `ON DELETE CASCADE` — deliberate choice; document this explicitly since cascading deletes are a common production footgun if undocumented |

### Test plan
- **Unit:** one test per `CHECK`/FK constraint in the edge-case matrix above (should fail to insert).
- **Integration:** factory-built full chain (merchant→customer→episode→event) inserts cleanly and is queryable via the ORM relationships.
- **Migration test:** `alembic upgrade head` then `alembic downgrade -1` then `alembic upgrade head` again succeeds cleanly (migrations are reversible) — a real production hygiene check most hackathon teams skip entirely.

### Exit criteria
- [ ] All constraint edge cases in the matrix pass.
- [ ] Migration up/down/up cycle is clean.
- [ ] `factory_boy` factories exist for every core table.

---

## Phase 2 — Synthetic Data Generation Service

### Objective
Produce a reproducible, realistically-noisy synthetic dataset that exercises
the full schema — not a flat JSON file, actual inserted rows.

### Decisions & trade-offs
| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Randomness source | Python `random` vs. `numpy.random.Generator` | **`numpy.random.Generator(seed)`** | Explicit generator object avoids global-state seed pollution across test runs — a subtle bug class in naive `random.seed()` usage |
| Distribution shaping | Uniform random per field vs. joint distributions (cause category correlates with recoverability) | **Joint distributions, hand-specified per `DATA_MODEL.md` §4** | Uncorrelated synthetic data is the single fastest way to make judges distrust your numbers — real failure data has structure |
| Idempotency | Regenerate-and-overwrite vs. content-addressed dataset versioning | **Content-addressed: dataset hash = f(seed, count, distribution params)** stored alongside the batch run | Lets you prove *exactly* which dataset produced which headline number, months later — genuine reproducibility discipline |

### Pseudocode
```python
def generate_batch(seed: int, n: int, merchant_id: UUID) -> list[EventDraft]:
    rng = np.random.default_rng(seed)
    cause_dist = CAUSE_CATEGORY_DISTRIBUTION  # from DATA_MODEL.md §4
    events = []
    for i in range(n):
        cause = rng.choice(list(cause_dist), p=list(cause_dist.values()))
        recoverable_ceiling = RECOVERABLE_CEILING[cause]
        will_recover = rng.random() < recoverable_ceiling  # ground truth for eval only, NOT fed to the agent
        opted_out = rng.random() < 0.05
        events.append(EventDraft(
            cause_category=cause,          # used only to pick a realistic gateway_error_code
            gateway_error_code=sample_error_code(cause, rng),
            amount=sample_amount(rng, merchant_vertical),
            customer_segment=sample_segment(rng),
            occurred_at=sample_timestamp(rng, window_days=14),
            _ground_truth_recoverable=will_recover,  # private field, used only by eval simulation, never exposed to the pipeline under test
            opted_out=opted_out,
        ))
    return events
```
**Critical design point:** `_ground_truth_recoverable` must never be passed
into the Diagnose/Decide pipeline — it exists only so the *evaluation
harness* can simulate an outcome after the agent acts. Leaking it into the
pipeline would make your bandit results meaningless (the model would be
"cheating"). Call this out explicitly in code comments and in your demo if asked.

### Edge-case matrix
| Case | Handling |
|---|---|
| `n = 0` | Returns empty list, no DB writes, no crash |
| Duplicate seed + params run twice | Byte-identical output (reproducibility test) |
| Extreme amount values (₹1, ₹10,00,000) | Included deliberately at low frequency to test downstream formatting/overflow handling |

### Test plan
- **Reproducibility test:** same seed+params twice → identical serialized output (hash comparison).
- **Distribution test:** generate n=10,000, assert observed cause-category frequencies are within a statistical tolerance (e.g., chi-squared test) of the target distribution.
- **Schema-validity test:** every generated event, once inserted, passes all Phase 1 constraints.

### Exit criteria
- [ ] Reproducibility and distribution tests pass.
- [ ] 200+ event batch inserted cleanly into the real schema.

---

## Phase 3 — Diagnose Service

### Objective
Deterministic-first, LLM-fallback classification of failure cause, with
full auditability of *why* a classification was made.

### Decisions & trade-offs
| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Primary classification strategy | LLM-first vs. rules-first | **Rules-first, LLM fallback only on miss** | Rules are free, instant, deterministic, and trivially explainable — exactly what "explainable" in the track's bar demands. LLM-first for a solved lookup problem would be over-engineering that *hurts* your explainability story |
| LLM call resilience | Fire-and-hope vs. retry+timeout+circuit breaker | **Retry (2x, exponential backoff) + 5s timeout + fallback to `unknown` category with `method='fallback_failed'`** | A hung LLM call must never block the pipeline; a classification of `unknown` is an honest, recoverable state — silently crashing is not |
| Prompt strategy | Free-text response vs. constrained/structured output | **Structured output (JSON mode / tool-call schema) with an enum-constrained field** | Removes an entire class of parsing bugs (LLM returning "Insufficient Funds" vs "insufficient_funds" vs a sentence) |

### Interface contract
```python
class DiagnosisResult(BaseModel):
    cause_category: CauseCategory       # enum, validated
    confidence: float                    # 0.0-1.0
    method: Literal["rule_based", "llm_fallback", "fallback_failed"]
    justification: str | None
    model_version: str | None

def diagnose(event: Event) -> DiagnosisResult: ...
```

### Edge-case matrix
| Case | Expected behavior |
|---|---|
| Known gateway error code | Rule-based, confidence=1.0, no LLM call (cost + latency saved) |
| Unmapped code, valid LLM response | LLM fallback, confidence from LLM, justification logged |
| Unmapped code, LLM times out | `cause_category=unknown`, `method=fallback_failed`, confidence=0.0 — pipeline continues, Gate/Decide treat `unknown` conservatively (see Phase 5) |
| Unmapped code, LLM returns invalid enum value | Pydantic validation rejects it → caught, logged, same fallback path as timeout |
| Empty/null `raw_gateway_message` | Rule path checked on `gateway_error_code` alone; LLM only invoked if that's also missing |

### Test plan
- **Unit:** rule table covers 100% of codes present in the synthetic dataset.
- **Unit:** LLM fallback path tested with a mocked client (both valid-response and timeout/malformed-response cases).
- **Contract test:** `DiagnosisResult` schema validation rejects any out-of-enum value — this is your safety net against LLM drift.

### Exit criteria
- [ ] 0% unintended `unknown` classifications on the synthetic dataset.
- [ ] LLM timeout/failure path proven non-blocking via a forced-failure test.

---

## Phase 4 — Gate (Compliance Engine)

### Objective
A deterministic, independently-testable safety layer that the learning
system (Decide) cannot override. Build and harden this *before* the bandit
so the bandit is developed against a known-safe boundary.

### Decisions & trade-offs
| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Where compliance logic lives | Embedded inside the bandit's action space (bandit "learns" not to violate rules) vs. a separate hard-coded layer | **Separate hard-coded layer, always evaluated after Decide, before Act** | A probabilistic system should never be the only thing standing between a decision and a compliance violation — this is the single most important architectural decision in the whole project, and worth stating explicitly in your demo |
| Rule composition | One monolithic `is_allowed()` function | **Chain of independent, individually-testable rule functions, each returning a typed result** | Each rule is independently auditable and unit-testable; a monolith obscures *which* rule fired when something is blocked |
| Fail-safe direction | Default-allow (block only on explicit rule match) vs. default-deny | **Default-deny is NOT used** (would be overly restrictive for a hackathon demo) — **default-allow with an exhaustive, tested rule set**, but every blocked action logs the specific rule name, never a generic "blocked" | Explicit reasoning is required either way; default-allow is the pragmatic choice for a bounded rule set you fully control and test |

### Pseudocode
```python
RuleResult = Literal["pass"] | tuple[Literal["blocked"], str]  # str = rule name

def check_max_attempts(episode, max_attempts=3) -> RuleResult:
    if episode.attempt_count >= max_attempts:
        return ("blocked", "max_attempts_exceeded")
    return "pass"

def check_opt_out(customer_id, db) -> RuleResult:
    if db.query(OptOut).filter_by(customer_id=customer_id).exists():
        return ("blocked", "customer_opted_out")
    return "pass"

def check_cool_off(episode, min_gap_hours, now) -> RuleResult:
    last = episode.last_action_at
    if last and (now - last) < timedelta(hours=min_gap_hours):
        return ("blocked", "cool_off_active")
    return "pass"

def check_time_window(now, allowed_hours=(9, 20)) -> RuleResult:
    if not (allowed_hours[0] <= now.hour < allowed_hours[1]):
        return ("blocked", "outside_communication_window")
    return "pass"

RULES = [check_max_attempts, check_opt_out, check_cool_off, check_time_window]

def evaluate_gate(context) -> GateResult:
    for rule in RULES:
        result = rule(context)
        if result != "pass":
            return GateResult(passed=False, rule_triggered=result[1])
    return GateResult(passed=True, rule_triggered=None)
```

### Edge-case matrix
| Case | Expected result |
|---|---|
| High-confidence bandit arm, but attempt #4 | **Blocked** — bandit confidence is irrelevant, rule is absolute |
| Customer opted out mid-episode (after episode opened, before this attempt) | **Blocked** — opt-out check is always evaluated fresh, not cached at episode start |
| Two rules would both block (e.g., max attempts AND opted out) | First rule in the chain that fails is logged — order rules by severity/regulatory importance, document the order explicitly |
| `stop` arm chosen by bandit | Always passes gate trivially — "do nothing" can never violate a compliance rule |

### Test plan
- **Unit, one per rule, both directions** (rule passes / rule blocks).
- **Adversarial test:** construct a context where the bandit *would* pick a real-money-moving arm, force gate evaluation, confirm block — this is the test to screenshot for your submission writeup.
- **Property-based test (stretch):** using `hypothesis`, generate random contexts and assert the gate never allows an action when `attempt_count >= max_attempts`, across thousands of generated cases — a genuinely FAANG-caliber testing technique that's cheap to add here.

### Exit criteria
- [ ] 100% rule coverage in unit tests.
- [ ] Adversarial test passes.
- [ ] (Stretch) property-based test passes across ≥1000 generated cases.

---

## Phase 5 — Decide (Contextual Bandit)

### Objective
A self-improving, fully auditable policy that operates strictly upstream of
the Gate — see `ML_DESIGN.md` for the algorithm itself; this phase focuses
on engineering the *system* around it.

### Decisions & trade-offs
| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| State storage | Postgres-only, Redis-only, or Redis (hot) + Postgres (durable snapshot) | **Redis hot path + periodic Postgres snapshot** | Every event triggers a read+write of arm statistics — Redis keeps this fast; Postgres snapshot protects against Redis data loss without paying Postgres latency on the hot path |
| Concurrency safety | Assume single-threaded, or handle concurrent updates | **Redis `HINCRBYFLOAT` (atomic)**, avoid read-modify-write races | Even in a demo, multiple events can be processed concurrently by Celery workers — atomic increments avoid lost updates without needing distributed locks |
| Cold-start handling | Uniform prior vs. informed prior | **Informed prior seeded from domain intuition** (see `ML_DESIGN.md` §2.6) | Reduces early-batch regret and gives a legitimate "we encoded domain knowledge, then let data refine it" story |
| Explainability at decision time | Log only the chosen arm | **Log chosen arm + sampled score + α/β snapshot at decision time** | Lets you answer "why did it choose this?" with actual numbers during Q&A, not "it's a black box" |

### Interface contract
```python
class BanditPolicy(Protocol):
    def sample_arm(self, context_bucket: str) -> str: ...
    def update(self, context_bucket: str, arm: str, reward: float) -> None: ...
    def get_stats(self, context_bucket: str) -> dict[str, tuple[float, float]]: ...  # arm -> (alpha, beta)
```
Defining this as a `Protocol` (structural typing) means the baseline policy
(Phase 8) and the bandit policy both satisfy the same interface — your batch
harness calls one abstract `policy.sample_arm(...)`, and swapping
`policy=baseline` vs `policy=bandit` requires zero branching logic elsewhere
in the codebase. This is a real software engineering pattern (strategy
pattern via structural typing), not incidental — call it out explicitly.

### Edge-case matrix
| Case | Expected behavior |
|---|---|
| Brand-new `context_bucket` never seen before | Falls back to a default informed prior, not a crash or a uniform-random guess |
| Redis unavailable | Fails loudly (raises), does NOT silently fall back to random — a broken hot-path store should stop the pipeline, not corrupt bandit learning silently |
| Reward outside [0,1] or negative-penalty range | Rejected by `update()`'s input validation before touching α/β |
| Extremely skewed context bucket (e.g., only 1 historical observation) | Thompson Sampling's Beta distribution naturally has high variance here — this is a feature, not a bug (explore more when uncertain); worth a code comment explaining this is intentional |

### Test plan
- **Unit:** `update()` correctly increments α on reward=1, β on reward=0.
- **Statistical convergence test:** simulate 500 rounds where one arm has a true 80% success rate and another 20%, assert the bandit's empirical arm-selection ratio shifts toward the better arm over time (tolerance-based assertion, not exact).
- **Concurrency test:** fire 50 concurrent `update()` calls for the same `context_bucket`+`arm`, assert final α/β reflects all 50 updates (no lost updates) — this is the test that specifically validates your atomic-increment design decision.

### Exit criteria
- [ ] Convergence test passes.
- [ ] Concurrency test passes with zero lost updates.
- [ ] Redis-unavailable failure mode is a loud, logged error, not silent degradation.

---

## Phase 6 — Act (Execution Layer)

### Objective
Translate an approved (gate-passed) decision into a real Razorpay test-mode
API call or a clearly-labeled simulated action, with proper handling of
delayed/scheduled actions.

### Decisions & trade-offs
| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Delayed action scheduling | `time.sleep()` in a loop, cron polling, or a real task queue | **Celery with ETA-scheduled tasks** | Models the real-world timing problem correctly; `time.sleep()` in a request-handling process is a genuine anti-pattern that a FAANG reviewer would flag immediately |
| Razorpay call resilience | Fire-and-forget vs. retry with idempotency | **Idempotency key per action + retry with exponential backoff** | Prevents double-charging/double-creating payment links if a retry occurs after a network blip — this is a real payments-engineering concern, not hackathon theater |
| Simulated vs. real boundary | Infer from arm type at render time | **Explicit `simulated` boolean set at creation time, persisted, never re-derived** | As documented in `DATABASE_DESIGN.md` — prevents any code path from accidentally mislabeling a simulated action as real |

### Pseudocode
```python
def execute_action(decision: Decision, gate_result: GateResult) -> Action:
    assert gate_result.passed, "execute_action must never be called on a blocked decision"
    idempotency_key = f"action:{decision.decision_id}"  # stable, safe to retry

    if decision.chosen_arm in REAL_MONEY_ARMS:
        result = razorpay_client.create_retry_payment_link(
            episode=decision.episode,
            idempotency_key=idempotency_key,
        )
        return Action(simulated=False, razorpay_ref_id=result.id, status="executed")

    elif decision.chosen_arm in DELAYED_ARMS:
        eta = now() + ARM_DELAYS[decision.chosen_arm]
        execute_action_task.apply_async(args=[decision.decision_id], eta=eta)
        return Action(simulated=False, scheduled_for=eta, status="scheduled")

    elif decision.chosen_arm in NUDGE_ARMS:
        text = llm_client.generate_nudge(decision, language=decision.chosen_arm)
        return Action(simulated=True, message_text=text, status="executed")

    else:  # 'stop'
        return Action(simulated=True, status="executed")  # no-op, but still logged
```

### Edge-case matrix
| Case | Expected behavior |
|---|---|
| `execute_action` called with `gate_result.passed=False` | Assertion error — this should be structurally unreachable, and the assertion is a deliberate defensive check, not just documentation |
| Razorpay API returns a transient 5xx | Retried with backoff, up to a max attempt count, then marked `status='failed'` with reason logged |
| Same `decision_id` executed twice (e.g., a retried Celery task) | Idempotency key prevents Razorpay from creating a duplicate payment link |
| LLM nudge generation fails | Falls back to a pre-written template message, still marked `simulated=true`, logged with `method=template_fallback` |

### Test plan
- **Unit:** each arm type routes to the correct execution path (mocked Razorpay client + mocked LLM client).
- **Idempotency test:** call `execute_action` twice with the same `decision_id`, assert only one real Razorpay resource is created (verified via mock call count).
- **Delayed task test:** assert a `retry_long_delay` arm enqueues a Celery task with an ETA ~2-3 days out, not executed immediately.

### Exit criteria
- [ ] Idempotency test passes.
- [ ] All four arm-type routing paths covered by unit tests.
- [ ] Failure and fallback paths (Razorpay 5xx, LLM failure) both tested.

---

## Phase 7 — Observe & Reward Loop

### Objective
Close the loop: capture outcomes, compute rewards, feed them back to the
bandit, and write the audit trail — this is what makes the system "learn"
rather than just "act."

### Decisions & trade-offs
| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Outcome capture for real actions | Polling `GET /payments/{id}` vs. webhook-driven | **Webhook-driven (with polling as a fallback/reconciliation job)** | Webhooks are the correct architectural pattern for event-driven state changes; polling alone would be both wasteful and laggy. Keep a periodic reconciliation poll as a safety net in case a webhook is missed — a real production pattern (webhook + reconciliation) |
| Reward computation location | Inline in the webhook handler vs. a separate reward-computation service | **Separate `RewardService`** | Keeps reward-shaping logic (see `ML_DESIGN.md` §2.5) independently testable and swappable without touching webhook-handling code |

### Pseudocode
```python
def handle_payment_captured_webhook(payload: dict):
    action = find_action_by_razorpay_ref(payload["payment"]["id"])
    outcome = Outcome(
        action_id=action.id,
        result="recovered",
        amount_recovered=payload["payment"]["amount"],
        time_to_resolution_hrs=hours_between(action.executed_at, now()),
    )
    outcome.reward = reward_service.compute(outcome)
    db.save(outcome)

    decision = action.decision
    bandit.update(decision.context_bucket, decision.chosen_arm, outcome.reward)
    audit_log_service.write(event=decision.event, outcome=outcome)  # single source of truth for audit writes
```

### Edge-case matrix
| Case | Expected behavior |
|---|---|
| Webhook arrives for an action that's already been reconciled by the polling job | Idempotent write — `outcome` upsert keyed on `action_id`, not a duplicate insert |
| Webhook payload references an unknown `razorpay_ref_id` | Logged as an integrity warning, does not crash the handler, alerts for manual review |
| Simulated nudge action — no real webhook will ever arrive | Outcome generated by the eval harness's outcome-simulation logic (Phase 8) in batch mode, or a manual "mark resolved" action in live-demo mode |
| Bandit update called with a `context_bucket` that no longer exists (e.g., cause taxonomy changed) | Falls back to the default prior bucket, logs a warning — doesn't crash the reward loop |

### Test plan
- **Unit:** `RewardService.compute()` returns expected reward for each outcome type (recovered / not_recovered / blocked_by_policy).
- **Integration:** simulated webhook payload → outcome row → bandit state change → audit_log row, all within one test, asserting all four side effects occurred correctly.
- **Idempotency test:** same webhook delivered twice (a real-world guarantee, not an edge case — most webhook providers explicitly warn of at-least-once delivery) → only one outcome row exists.

### Exit criteria
- [ ] Full webhook→outcome→bandit→audit chain integration test passes.
- [ ] Duplicate webhook delivery is provably idempotent.

---

## Phase 8 — Batch Evaluation Harness

### Objective
Produce the headline, reproducible, judge-defensible numbers: bandit policy
vs. naive baseline over an identical dataset.

### Decisions & trade-offs
| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Baseline implementation | A separate, simplified pipeline vs. the real pipeline with `policy=baseline` | **Real pipeline, only `Decide` swapped** (enabled by the `BanditPolicy` Protocol from Phase 5) | A baseline built on a *different* code path invites judges to (rightly) question whether the comparison is fair. Reusing Diagnose/Gate/Act/Observe for both means the ONLY variable is the decision policy — a properly controlled experiment |
| Outcome simulation for batch mode | Deterministic rule vs. ground-truth-probability sampling | **Sample from `_ground_truth_recoverable` probability with added noise per action-quality** (e.g., a well-matched arm for the cause category gets a probability boost over a poorly-matched one) | This is what actually lets the bandit have something to learn — if outcome were independent of arm choice, there'd be nothing for the policy to optimize, and your "learning curve" would be flat by construction |
| Metrics computation | Ad hoc Python aggregation vs. SQL views | **SQL aggregation queries, saved as reusable views** | Independently re-verifiable by anyone with DB access — a materialized, inspectable source of truth beats a Python script judges have to trust blindly |

### Pseudocode (controlled experiment structure)
```python
def run_batch(dataset_seed: int, n: int, policy_name: Literal["bandit", "baseline"]):
    run = BatchRun(policy=policy_name, dataset_ref=f"seed={dataset_seed},n={n}", random_seed=dataset_seed)
    events = generate_batch(seed=dataset_seed, n=n)  # SAME seed for both policy runs
    policy = bandit_policy if policy_name == "bandit" else baseline_policy

    for event in events:
        diagnosis = diagnose(event)
        decision = policy.sample_arm(context_bucket_for(event, diagnosis))
        gate_result = evaluate_gate(context_for(event, decision))
        if gate_result.passed:
            action = execute_action_simulated(decision, gate_result)  # batch mode: simulated execution, not live API calls
            outcome = simulate_outcome(event, decision, action)        # uses _ground_truth_recoverable + arm-match quality
            policy.update(context_bucket_for(event, diagnosis), decision, outcome.reward)
        else:
            outcome = Outcome(result="blocked_by_policy", reward=-0.1)
        audit_log_service.write(event, decision, gate_result, outcome)

    compute_and_persist_metrics(run)
```

### Edge-case matrix
| Case | Expected behavior |
|---|---|
| `n` too small for statistical significance | Document the minimum viable batch size (e.g., n≥150) and note this explicitly in `TESTING_METRICS.md`, don't silently present an underpowered result as conclusive |
| Baseline "policy" needs to satisfy the same `BanditPolicy` Protocol | Implement as a trivial no-learning policy: `sample_arm()` always returns `retry_immediate`; `update()` is a no-op |
| Two runs with different seeds produce very different lift numbers | Run 3+ seeds, report mean ± range — a single-seed result is fragile and a sharp judge will ask about variance |

### Test plan
- **Reproducibility:** same `(seed, n, policy)` twice → identical `batch_run_metrics` row.
- **Fairness-of-comparison test:** assert both baseline and bandit runs process the exact same `events` list (same seed) — a regression test against accidentally comparing on different data.
- **Multi-seed variance check:** run 3 seeds, assert lift is directionally consistent (bandit > baseline) across all three, not just one lucky seed.

### Exit criteria
- [ ] Reproducibility test passes.
- [ ] Multi-seed lift is consistent and positive.
- [ ] SQL metric views independently reproduce the same numbers as the Python harness output (cross-check).

---

## Phase 9 — API & Audit Trail

### Objective
Expose the system via a documented, versioned API; make the audit trail a
first-class, queryable, immutable artifact.

### Decisions & trade-offs
| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Audit write mechanism | DB trigger vs. application-level write-through | **Application-level write-through via a single `AuditLogService`** | Faster to iterate on during a 10-day build than debugging trigger logic; still centralizes all writes through one code path, which is the property that actually matters (not *where* the write happens, but that there's exactly one path) |
| Audit immutability enforcement | Convention only vs. DB permission enforcement | **DB permission enforcement**: application's DB role has no `UPDATE`/`DELETE` grant on `audit_log` | Converts "we promise not to edit the log" into "the database physically will not allow it" — a meaningfully stronger claim in a fintech-adjacent demo |
| API versioning | Unversioned vs. `/v1/` prefix from day one | **`/v1/` prefix from day one** | Costs nothing now, signals forward-thinking API design, and is genuinely how production APIs are built |

### Test plan
- **Permission test:** attempt an `UPDATE`/`DELETE` on `audit_log` using the application's DB role directly (bypassing the app layer entirely) and assert it's rejected by Postgres, not just by application logic.
- **API contract test:** OpenAPI schema (auto-generated by FastAPI) validated against example requests/responses in a snapshot test, so accidental breaking changes to the API surface are caught in CI.

### Exit criteria
- [ ] DB-level immutability of `audit_log` proven by a test that bypasses the app.
- [ ] `/v1/` API fully documented via auto-generated OpenAPI, browsable at `/docs`.

---

## Phase 10 — Dashboard

### Objective
Make the system's behavior legible at a glance — this is the surface judges
actually look at for the first 90 seconds, so treat it with the same rigor
as the backend, not as an afterthought.

### Decisions & trade-offs
| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Data fetching | Polling vs. WebSocket | **Polling (5-10s interval) for hackathon scope**, with the fetching logic abstracted behind a hook so swapping to WebSocket later is a contained change | WebSockets add real complexity (connection lifecycle, reconnection logic) that isn't worth the engineering risk in a 10-day build for a demo dashboard — the honest, sized-right choice |
| State management | Redux vs. React Query + local state | **React Query** for server state, local `useState` for UI-only state | React Query gives you caching, loading/error states, and refetching for free — exactly the concerns a dashboard polling a batch-run API actually has |
| Chart library | D3 (custom) vs. Recharts | **Recharts** | D3 gives more control than you need here; Recharts gets you a correct, clean learning-curve chart in far less time — the sized-right tool, same principle as above |

### Test plan
- **Component tests (Vitest + Testing Library):** metrics panel renders correct before/after numbers given a mocked API response; exception list renders empty-state correctly when there are zero exceptions (don't let this path go untested — it's exactly the kind of thing that breaks live).
- **Visual smoke test:** Storybook or a simple visual snapshot for the learning-curve chart component, so a data-shape regression is caught before demo day, not during it.

### Exit criteria
- [ ] Dashboard fully populated from a real batch run with zero manual data massaging.
- [ ] Loading and error states are handled visibly, not blank screens, for every panel.

---

## Phase 11 — Resilience & Chaos Testing (this is your "heavy novelty" differentiator)

### Objective
Most hackathon teams stop at "it works in the happy path." A FAANG-caliber
team proves it survives failure — this phase is what elevates ResiliencePay
from "a working demo" to "a system I'd trust," and it's cheap to add given
what you've already built with clean interface boundaries.

### What to actually build
1. **Fault injection harness**: a flag-gated wrapper around the Razorpay
   client and the LLM client that can simulate timeouts, 5xx errors, and
   malformed responses on command.
2. **Chaos test suite**: run a batch through the pipeline with fault
   injection enabled at a configurable failure rate (e.g., 15% of Razorpay
   calls fail), assert:
   - No event is silently dropped — every event ends in a terminal, logged state (`recovered`, `not_recovered`, `blocked_by_policy`, or `failed_permanently`).
   - The bandit's state remains internally consistent (no partial/corrupt updates) even under injected concurrency + failure.
   - The audit trail has zero gaps — every decision has a corresponding gate check, and every gate-passed decision has a corresponding action record, even when the downstream Act call failed.
3. **Live-demo fault injection as a deliberate demo beat**: this directly satisfies "show one failure handled gracefully" from the track's bar, but done as a *system property you can trigger on demand* rather than a scripted, faked failure — a materially stronger claim to make to judges.

### Why this specifically wins on novelty
Every team in Track 03 will show a happy-path recovery flow. Almost none
will demonstrate their system surviving and gracefully degrading under
injected real-world failure conditions, live, on command. This is the
single highest-leverage addition you can make in the time it costs (1 day),
because it's built entirely from interfaces you already have (thanks to the
Protocol-based, dependency-injected design from Phases 5 and 6) — this phase
is the payoff for those earlier architectural decisions.

### Exit criteria
- [ ] Chaos suite passes at 15% injected failure rate with zero silently-dropped events.
- [ ] A judge can ask "what happens if Razorpay is down right now" and you can trigger it live and show the graceful degradation, not just describe it.

---

## Phase 12 — Rehearsal, Documentation Parity & Submission

### Objective
Ensure the delivered artifact (repo + demo) matches the documented design
exactly — a PRD that doesn't match the product is worse than no PRD.

### Checklist
- [ ] Every `.md` doc in `/docs` reflects what was actually built, not the original plan where they diverged (update docs as you go, not on Day 10).
- [ ] `docker-compose up` on a clean machine, timed — should be under 5 minutes to a fully running system.
- [ ] Full `DEMO_SCRIPT.md` rehearsed at least 3 times, including the Phase 11 chaos-injection beat.
- [ ] README has: problem statement, architecture diagram, how to run, how to reproduce the headline metrics, and an explicit "what's real vs. simulated" section.
- [ ] Submit via https://forms.gle/d9r2gvxp8cmoZhon9.

### The one sentence to have ready when a judge asks "what's the most interesting engineering decision you made"
*"We separated the learning system from the compliance system architecturally, not just logically — the bandit physically cannot execute a money-moving action without passing through an independently-tested, rule-based gate — and we proved the whole pipeline degrades gracefully under injected failure, live, on demand."*
