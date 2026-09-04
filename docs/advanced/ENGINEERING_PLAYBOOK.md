# ENGINEERING_PLAYBOOK.md — ResiliencePay

This is the single, authoritative coding standard for this repo. It
supersedes and absorbs everything in your existing `CLAUDE.md` — keep that
file, but treat this as the fuller reference it points to. Any coding
agent or human contributor should be able to write correct, idiomatic,
production-shaped code for this project from this document alone, without
guessing at conventions.

---

## 1. The operating identity

You are writing code as a senior/staff engineer at a top-tier engineering
organization would, on a real production system that happens to be under
a 10-day deadline — not as someone writing a hackathon demo. Concretely,
this means: you default to correctness and explicitness over speed when
the two conflict, you make trade-offs visible instead of silent, and you
treat every shortcut as a decision to be stated, not a default to fall
into unnoticed.

---

## 2. Code organization rules (non-negotiable)

### 2.1 Layer boundaries

```
apps/*        → thin entrypoints (HTTP routes, Celery tasks). Parse input,
                call exactly one services/* function, format the response.
                NEVER contains business logic, decision branching, or
                direct SQLAlchemy queries.
services/*    → all business logic. Framework-agnostic — no FastAPI, no
                Celery imports here. Must be callable from apps/api,
                apps/worker, AND eval/run_batch.py with identical behavior.
packages/*    → shared code with zero project-specific business logic:
                DB models, config, domain constants (arms, cause categories).
eval/*        → offline batch evaluation, imports from services/* only.
```

**Enforce this in CI**, not just by convention — use an import-linter
contract (`.importlinter`) that fails the build if `services/*` ever
imports from `apps/*`. A rule that isn't enforced by tooling will erode
under deadline pressure; assume it will and build the enforcement now.

### 2.2 The DTO/Mapper boundary

Every value that crosses from `services/*` into an `apps/api` response
must pass through an explicit mapper function into a Pydantic DTO — never
serialize an ORM model directly.

```python
# WRONG — leaks internal schema, couples API shape to DB shape
@router.get("/events/{id}")
def get_event(id: str):
    return db.query(Event).get(id)  # returns raw ORM object

# RIGHT
@router.get("/events/{id}")
def get_event(id: str, db_session=Depends(get_db_session)):
    event = get_event_or_404(db_session, id)
    return event_to_dto(event)  # explicit mapper, explicit DTO
```

DTOs use `model_config = {"from_attributes": False}` deliberately, forcing
every field to be explicitly assigned in the mapper — this makes it
structurally impossible for an internal-only field to leak into a public
response by accident.

### 2.3 File and function size discipline

- A route handler over ~15 lines, or containing an `if` that isn't purely
  about HTTP status/response shaping, has business logic that belongs in
  `services/*`. Move it.
- A `services/*` function over ~40 lines is a signal to extract a helper —
  not a hard rule, but a prompt to check whether you're doing two things
  in one function.

---

## 3. Naming and typing conventions

- **Python:** `snake_case` for functions/variables, `PascalCase` for
  classes, `UPPER_SNAKE_CASE` for module-level constants (`ARMS`,
  `REWARD_RECOVERED`). Type-hint every function signature, including
  return types — `mypy --strict` runs on `services/*` and `packages/*` in CI.
- **TypeScript:** `camelCase` for functions/variables, `PascalCase` for
  components and types. No `any` — if a type is genuinely unknown, use
  `unknown` and narrow it explicitly.
- **Money:** always `int` (paise), a variable named `amount` or
  `amount_paise` never holds a float or a rupee value. If a rupee value is
  ever needed for display, convert at the formatting boundary only
  (`lib/format.ts`'s `formatPaise`), never in business logic.
- **IDs:** UUIDs everywhere except `audit_log.audit_id` (bigserial, since
  it's an append-only sequential ledger where insertion order matters).
- **Booleans:** name them as a predicate (`is_real_action`, `simulated`,
  `gate_passed`) — never a bare noun that could be mistaken for a status enum.

---

## 4. Error handling standard

Every function that can fail must fail in one of exactly three
documented ways — never a fourth, undocumented way:

1. **Return an explicit result type** signaling failure without raising
   (e.g., `GateResult(passed=False, rule_triggered=...)`), when failure is
   an expected, common outcome the caller must handle every time.
2. **Raise a specific, typed exception** (`RazorpayPermanentError`,
   `NotFoundError`), when failure is exceptional and callers should
   explicitly opt in to handling it via `try`/`except`.
3. **Guarantee it never raises**, with a documented fallback (e.g.,
   `NudgeGenerator.generate()` always returns a `NudgeResult`, falling back
   to a template on any LLM failure) — used specifically when a downstream
   failure must never propagate and break an unrelated part of the pipeline.

Pick the right one deliberately per function and document which you chose
in the docstring. Never let a bare `except Exception: pass` exist anywhere
in the codebase — if you need to catch broadly (as in the nudge generator
case), catch broadly *and* log *and* return a defined fallback value; never
catch and silently discard.

**At the API boundary**, every error becomes a structured JSON response
(`{"error": true, "code": "...", "reason": "...", "request_id": "..."}`),
never a raw stack trace. Register this centrally in
`apps/api/src/middleware/error_handler.py`, not per-route.

---

## 5. Testing standard

### 5.1 The pyramid, with real ratios, not just a diagram

- **Unit tests (majority):** pure functions, mocked external dependencies.
  Every `services/gate` and `services/decide` function needs a happy-path
  test plus at least one edge case from that phase's documented edge-case
  matrix.
- **Integration tests (moderate):** real Postgres/Redis test instances —
  used specifically when the property under test is about real
  infrastructure behavior (concurrency, DB constraints, permission
  enforcement), not just logic. A fully-mocked test cannot prove a real
  concurrency guarantee — don't let one stand in for this.
- **End-to-end tests (few):** one full docker-compose stack, one real
  event through the whole pipeline. Expensive to run; keep this small and
  deliberate.

### 5.2 Non-negotiable test requirements

- Every external-call wrapper (`RazorpayClient`, `NudgeGenerator`,
  `llm_fallback`) needs a test for both success and failure/timeout paths.
- Every function whose failure mode is "never raises, always falls back"
  needs a test that forces the underlying failure and asserts the fallback
  actually returns, not just that no exception escapes.
- Every idempotency guarantee ("safe to call twice") needs a test that
  actually calls it twice and asserts on the *count* of side effects, not
  just the final state.
- CI enforces a coverage floor (`pytest --cov --cov-fail-under=75`) on
  `services/*` specifically.

### 5.3 Write tests before or alongside the code for money- and
compliance-adjacent logic — `services/gate`, `services/decide`,
`services/act`'s Razorpay calls, and anything touching `amount` fields.
This isn't dogma; it's specifically because these are the areas where a
plausible-looking implementation can be subtly wrong in a way that only a
test written from the requirement (not from the implementation) will catch.

---

## 6. Security standard

- **Secrets** never committed, never logged — wire a log-redaction
  processor (`structlog` processor matching `key_secret|api_key|password`
  patterns) so this is enforced automatically, not by discipline alone.
- **Least-privilege database roles** — the application's runtime DB role
  has no `DROP`/`TRUNCATE`/`ALTER` on any table, and no `DELETE` on
  financial tables (`episodes`, `events`, `outcomes`, `decisions`,
  `actions`) or `audit_log`. Financial records are closed or superseded,
  never deleted.
- **Input validation beyond type-checking** — Pydantic validates shape;
  add explicit `field_validator`s for business-meaningful constraints
  (positive amounts, supported currencies, reasonable ceilings).
- **Every admin/dangerous endpoint** (e.g., the fault-injection toggle)
  requires at minimum a shared-secret header check — state explicitly that
  this is a demo-scoped control, not production auth, if asked.
- **CORS configured with an explicit origin list**, never a wildcard.

---

## 7. Idempotency and concurrency standard

- Any function that creates an external resource (a Razorpay payment
  link, a message send) takes an idempotency key and is safe to call
  twice with identical results.
- Any shared, concurrently-updated state (bandit α/β counters) uses atomic
  operations at the storage layer (`HINCRBYFLOAT`), never
  read-then-write-back in application code.
- Any webhook handler assumes **at-least-once delivery** as a certainty,
  not an edge case — idempotent upsert, and side effects (bandit updates,
  audit writes) gated on "was this actually a new record," never fired
  unconditionally after every upsert call.

---

## 8. Observability standard

- Every request carries a `request_id` (from an incoming header or
  generated fresh), bound to the structured logging context for that
  request's full lifecycle, propagated into any Celery task it enqueues,
  and returned in the response headers and any error body.
- Every decision-making function logs its own explainability data at the
  point of decision (the bandit's α/β snapshot and sampled score; the
  Gate's specific rule triggered) — not reconstructed after the fact from
  incomplete records.
- Structured logs (JSON via `structlog`), never bare `print()`.

---

## 9. Dependency and configuration standard

- All configuration is a validated `pydantic.BaseSettings` subclass,
  failing fast at process boot on any missing/malformed required variable
  — never a bare `os.environ.get()` scattered through business logic.
- New dependencies are added to `pyproject.toml`'s `[project.dependencies]`
  or `[project.optional-dependencies.dev]` explicitly — never installed
  ad hoc and left undeclared.
- No dependency is added for a problem you could solve correctly in
  under ~20 lines with the standard library, unless the dependency is
  something the ecosystem clearly expects (e.g., use `alembic` for
  migrations, don't hand-roll one).

---

## 10. Git and review standard

- Conventional Commits (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`),
  one logical change per commit.
- Trunk-based development, short-lived feature branches, mandatory
  1-reviewer PR approval even under deadline pressure — this is cheap
  insurance against exactly the kind of bug that's easy to introduce
  quickly and expensive to find later in money-handling code.
- PR description states: what changed, which phase/doc it implements
  (link the specific `docs/phases/PHASE_XX_*.md` file), and how it was
  tested (which test files, and whether against real infrastructure or mocks).
- CI (`lint → typecheck → test`) is a required, blocking check on the
  default branch — not advisory.

---

## 11. Documentation-parity standard

If implementing a phase reveals that its doc was wrong, ambiguous, or
incomplete, **fix the doc in the same PR as the code change** — never let
documentation and code silently diverge. A doc that no longer matches the
code is worse than no doc, because it actively misleads the next person
(including a future you) who trusts it. This applies with equal force to
`CURRENT_STATUS_AND_NEXT_STEPS.md`'s "what's actually real" section —
update it the moment a phase's Definition of Done is genuinely met, not
before, and not much after.

---

## 12. The checklist to run before calling any task done

- [ ] Does this respect the layer boundaries in section 2.1?
- [ ] Does every API-facing value pass through an explicit DTO/mapper?
- [ ] Is every money value an `int` paise, never a `float`?
- [ ] Does every external call have explicit timeout/retry/failure handling?
- [ ] Is every money-affecting action idempotent?
- [ ] Are there tests for the happy path AND at least one documented edge case?
- [ ] Do webhook/external-input handlers assume at-least-once delivery / untrusted input?
- [ ] Are secrets absent from every log line, config file, and commit?
- [ ] Does this match the exact file paths in the relevant `docs/phases/PHASE_XX_*.md`?
- [ ] If a doc turned out to be wrong while implementing this, was it corrected in this same PR?

If any box is unchecked, the task is not done — flag what's missing
explicitly rather than reporting completion.
