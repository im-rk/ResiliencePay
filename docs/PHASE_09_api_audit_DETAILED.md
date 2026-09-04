# Phase 9 — API & Audit Trail — Full Detailed Spec

**Depends on:** Phases 1-8 (everything the API exposes)
**Unblocks:** Phase 10 (dashboard consumes this API exclusively)
**Owner:** backend/API owner
**Estimated time:** ~1 day

---

## 1. Why this phase exists and why it matters more than it looks

Up to this point, the entire pipeline is a set of importable Python
modules — powerful, tested, but invisible to anything outside a Python
process. This phase is the seam where "a system that works" becomes "a
system a judge, a dashboard, or a curious teammate can actually interact
with." It carries two responsibilities that are easy to under-scope:

1. **A genuinely thin API layer.** The temptation here is to let business
   logic creep into route handlers because "it's just a few lines, it's
   convenient." Resist this completely. If `apps/api` contains anything
   beyond request parsing, calling into `services/*`, and response
   formatting, you've broken the property that let Phase 8's batch harness
   run the whole pipeline without a web server — and that property is not
   a nice-to-have, it's what makes your "controlled experiment" claim
   credible (see `PHASE_08_batch_eval_DETAILED.md` section 2.1).
2. **Proving audit immutability, not asserting it.** "The audit log is
   append-only" is a claim. A test that connects as the actual application
   database role and watches Postgres itself reject an `UPDATE` is
   evidence. The difference between these two is the difference between
   "we designed it to be safe" and "we can show you it's safe" — and only
   one of those survives a skeptical judge's follow-up question.

This phase is also where your **OpenAPI contract becomes the single source
of truth** shared between backend and frontend. Get this wired correctly
and Phase 10's dashboard literally cannot drift out of sync with your API,
because it imports generated types rather than hand-written ones.

---

## 2. Conceptual model — read this before touching code

### 2.1 Why "thin controllers" is a testable property, not just a style preference

"Keep business logic out of route handlers" sounds like generic advice
every codebase claims to follow and few actually do. Here's how to make it
concrete and checkable: **a route handler function should be expressible in
under ~15 lines: parse input → call exactly one `services/*` function →
translate the result into a response.** If a route handler needs an `if`
statement deciding *what to do* (as opposed to *how to format the
response*), that's business logic that belongs in `services/*`. This isn't
pedantry — it's the difference between an API you can test with mocks in
milliseconds and one where testing requires spinning up the whole HTTP
stack.

### 2.2 Why structured errors are part of your "graceful failure" story

The buildathon's own stated bar (recall the "what broke at 2 AM, and how
you got out" framing) rewards visible, legible failure handling. A raw
Python stack trace returned as a `500` response is the *opposite* of that —
it signals "this broke and nobody thought about what happens next." A
structured error response (`{"error": true, "code": "GATE_BLOCKED",
"reason": "max_attempts_exceeded"}`) is the same underlying failure,
communicated as a designed outcome rather than an accident. This is cheap
to build and disproportionately valuable in how your system reads to a
judge poking at it live.

### 2.3 Why the OpenAPI export is not optional busywork

FastAPI generates an OpenAPI schema for free from your route type hints —
you don't have to write it by hand. Exporting that schema into
`packages/api-contracts/` and generating a TypeScript client from it means
the dashboard's data-fetching code is **generated, not hand-written** — if
you change an API response shape, the dashboard's TypeScript types update
automatically (or loudly fail to compile if the dashboard code wasn't
updated to match), rather than silently drifting into a runtime bug that
only shows up live, during your demo, in front of judges.

### 2.4 Why proving `audit_log` immutability requires bypassing your own application

If you only test immutability by calling your own `AuditLogService` and
confirming it never issues an `UPDATE`, you've tested that your
*application code* behaves — not that the *database* would prevent
misbehavior if it tried. The real test connects using the actual
`resiliencepay_app` role's credentials directly (bypassing SQLAlchemy, your
service layer, everything) and attempts a raw `UPDATE`/`DELETE` SQL
statement. If Postgres rejects it, you've proven the guarantee holds even
if a future bug, a compromised dependency, or a rushed 2 AM hotfix tried to
violate it. This is precisely the test built and run in the Phase 1
migration work — reuse that proof here rather than re-deriving it, and
reference it directly.

---

## 3. Detailed component design

### 3.1 `apps/api/src/main.py` — app factory and wiring

```python
from fastapi import FastAPI

from apps.api.src.middleware.error_handler import register_error_handlers
from apps.api.src.routers import audit, batch, events, metrics

app = FastAPI(title="ResiliencePay API", version="0.1.0")

register_error_handlers(app)

app.include_router(events.router, prefix="/v1", tags=["events"])
app.include_router(batch.router, prefix="/v1", tags=["batch"])
app.include_router(metrics.router, prefix="/v1", tags=["metrics"])
app.include_router(audit.router, prefix="/v1", tags=["audit"])


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
```

### 3.2 `apps/api/src/middleware/error_handler.py`

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Base class for all business-logic errors raised by services/*.
    Route handlers never construct HTTPException directly for domain
    failures — they let a DomainError propagate and this handler converts
    it, keeping the error-shaping logic in exactly one place."""

    def __init__(self, code: str, reason: str, status_code: int = 422, **context):
        self.code = code
        self.reason = reason
        self.status_code = status_code
        self.context = context
        super().__init__(f"{code}: {reason}")


class NotFoundError(DomainError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(code="NOT_FOUND", reason=f"{resource} not found",
                          status_code=404, resource=resource, resource_id=resource_id)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": True, "code": exc.code, "reason": exc.reason, **exc.context},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        # Never leak a raw stack trace to the client. Log the full
        # exception server-side (structlog, with a request ID for
        # correlation), return a generic, safe body.
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception("unhandled_exception", extra={"request_id": request_id})
        return JSONResponse(
            status_code=500,
            content={"error": True, "code": "INTERNAL_ERROR",
                      "reason": "An unexpected error occurred.", "request_id": request_id},
        )
```

### 3.3 `apps/api/src/routers/events.py` — thin controller example

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.src.dependencies import get_db_session
from apps.api.src.middleware.error_handler import NotFoundError
from services.observe.query_service import get_event_full_state  # a services/* read helper, not inline ORM queries in the router

router = APIRouter()


class IngestEventRequest(BaseModel):
    event_type: str
    merchant_id: str
    customer_id: str
    amount: int
    currency: str = "INR"
    gateway_error_code: str | None = None
    raw_gateway_message: str | None = None
    customer_segment: str
    retry_count_so_far: int = 0


@router.post("/events/ingest", status_code=202)
def ingest_event(body: IngestEventRequest, db_session=Depends(get_db_session)):
    from services.diagnose.service import ingest_and_queue_event  # single call — all logic lives in services/*
    event = ingest_and_queue_event(db_session, body.model_dump())
    return {"event_id": str(event.event_id), "status": "queued_for_diagnosis"}


@router.get("/events/{event_id}")
def get_event(event_id: str, db_session=Depends(get_db_session)):
    state = get_event_full_state(db_session, event_id)
    if state is None:
        raise NotFoundError(resource="event", resource_id=event_id)
    return state
```

**Notice this router file contains zero decision-making** — no `if
cause_category == ...`, no gate logic, no bandit calls. It parses,
delegates, formats. If you find yourself wanting to add a conditional here
that isn't purely about HTTP status codes or response shaping, that logic
belongs in `services/diagnose/service.py` or wherever the relevant domain
module lives.

### 3.4 `apps/api/src/routers/metrics.py` — the learning-curve endpoint

```python
from fastapi import APIRouter, Depends

from apps.api.src.dependencies import get_db_session
from services.observe.query_service import get_learning_curve_data, get_batch_summary

router = APIRouter()


@router.get("/metrics/summary")
def metrics_summary(run_id: str, db_session=Depends(get_db_session)):
    return get_batch_summary(db_session, run_id)


@router.get("/metrics/learning-curve")
def learning_curve(run_id: str, bucket_size: int = 20, db_session=Depends(get_db_session)):
    """bucket_size groups outcomes into rolling windows for the recovery-
    rate-over-batch-index chart — see PHASE_10 dashboard's LearningCurveChart,
    which consumes this exact shape. Coordinate this response schema with
    whoever builds that chart component before finalizing it."""
    return get_learning_curve_data(db_session, run_id, bucket_size)
```

### 3.5 `apps/api/src/routers/audit.py`

```python
from fastapi import APIRouter, Depends, Query

from apps.api.src.dependencies import get_db_session
from services.audit.query_service import query_audit_trail

router = APIRouter()


@router.get("/audit-trail")
def audit_trail(
    episode_id: str | None = None,
    cause_category: str | None = None,
    chosen_arm: str | None = None,
    outcome_result: str | None = None,
    page: int = 1,
    page_size: int = Query(default=50, le=200),
    db_session=Depends(get_db_session),
):
    return query_audit_trail(
        db_session, episode_id=episode_id, cause_category=cause_category,
        chosen_arm=chosen_arm, outcome_result=outcome_result, page=page, page_size=page_size,
    )
```

### 3.6 OpenAPI export + typed client generation

```bash
# Run as part of CI or a Makefile target — regenerates the contract
# whenever route signatures change, catching drift immediately.
python -c "
import json
from apps.api.src.main import app
with open('packages/api-contracts/openapi.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2)
"
npx openapi-typescript packages/api-contracts/openapi.json \
    -o packages/api-contracts/generated/schema.ts
```
Wire this as a pre-commit hook or a CI step that fails if the checked-in
`openapi.json` doesn't match a freshly generated one — this is what
prevents the contract from silently going stale.

---

## 4. Full edge-case matrix (expanded)

| # | Case | Expected behavior | How to test |
|---|---|---|---|
| 1 | `GET /v1/events/{id}` for a nonexistent event | `404` with structured body `{"error": true, "code": "NOT_FOUND", ...}`, not an unhandled exception | Unit test with a random UUID, assert status code and body shape |
| 2 | `POST /v1/pipeline/run-batch` with `n=0` | `422` with a clear validation message (Pydantic's built-in validation, or a `DomainError` if business-rule validation) | Unit test |
| 3 | A route handler's underlying `services/*` call raises an unexpected (non-`DomainError`) exception | Caught by the top-level handler, returns generic `500` with a `request_id`, full details logged server-side only | Unit test with a route wired to a mock that raises `RuntimeError`, assert the response never contains the exception message or a stack trace |
| 4 | `GET /v1/audit-trail` with an invalid `page_size` (e.g., 500, above the `le=200` limit) | `422`, FastAPI's built-in Pydantic validation | Unit test |
| 5 | Direct `UPDATE`/`DELETE` on `audit_log` using the real `resiliencepay_app` role, bypassing the app entirely | Rejected by Postgres with `permission denied for table audit_log` | Test in §5.4 — reuses the proof already established during Phase 1's migration work |
| 6 | OpenAPI schema drifts from a route's actual type hints (e.g., someone changes a response model without regenerating) | CI catches this via a schema-diff check, not discovered later by a broken dashboard build | Contract snapshot test in §5.3 |

---

## 5. Test plan — with actual test code to implement

### 5.1 `apps/api/tests/test_events_router.py`

```python
from fastapi.testclient import TestClient
from apps.api.src.main import app

client = TestClient(app)


def test_get_nonexistent_event_returns_structured_404():
    response = client.get("/v1/events/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] is True
    assert body["code"] == "NOT_FOUND"


def test_ingest_event_validates_input():
    response = client.post("/v1/events/ingest", json={"event_type": "payment_failed"})  # missing required fields
    assert response.status_code == 422
```

### 5.2 `apps/api/tests/test_unhandled_exception_handling.py`

```python
def test_unexpected_exception_never_leaks_stack_trace(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("something deeply internal broke, with sensitive details: SECRET_TOKEN=abc123")

    monkeypatch.setattr("services.observe.query_service.get_event_full_state", boom)

    response = client.get("/v1/events/some-id")
    assert response.status_code == 500
    body = response.json()
    assert "SECRET_TOKEN" not in response.text  # the sensitive detail must never reach the client
    assert body["code"] == "INTERNAL_ERROR"
    assert "request_id" in body
```

### 5.3 `apps/api/tests/test_contract_openapi.py`

```python
import json
from apps.api.src.main import app


def test_openapi_schema_matches_checked_in_contract():
    current_schema = app.openapi()
    with open("packages/api-contracts/openapi.json") as f:
        checked_in_schema = json.load(f)
    assert current_schema == checked_in_schema, (
        "OpenAPI schema has drifted from packages/api-contracts/openapi.json — "
        "regenerate it (see section 3.6 of the phase doc) and commit the update, "
        "or the dashboard's generated types will silently go stale."
    )
```

### 5.4 `apps/api/tests/test_audit_immutability.py`

```python
import psycopg2
import pytest

from packages.config.settings import settings


def test_app_role_cannot_update_or_delete_audit_log():
    """This connects as the REAL resiliencepay_app-inheriting role,
    bypassing SQLAlchemy and the application entirely — see
    PHASE_09_api_audit_DETAILED.md section 2.4 for why this specific test
    design is required, not optional. This mirrors the exact manual
    verification already performed during Phase 1's migration work
    (see packages/db-models/alembic/versions/0006_audit_log.py)."""
    conn = psycopg2.connect(
        host="localhost", dbname="resiliencepay",
        user="app_test_login", password="test",  # test-only login role inheriting resiliencepay_app
    )
    conn.autocommit = True
    cur = conn.cursor()

    # INSERT and SELECT must succeed
    cur.execute(
        "INSERT INTO audit_log (event_id, episode_id, outcome_result) VALUES (gen_random_uuid(), gen_random_uuid(), 'recovered')"
    )
    cur.execute("SELECT COUNT(*) FROM audit_log")
    assert cur.fetchone()[0] >= 1

    # UPDATE must be rejected
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("UPDATE audit_log SET outcome_result = 'tampered'")

    conn.rollback()

    # DELETE must be rejected
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute("DELETE FROM audit_log")

    conn.close()
```

---

## 6. Observability

Every request should carry a `request_id` (generated at the top of the
middleware stack if not already present in an incoming header), logged on
every structured log line for that request's lifecycle and included in
every error response. This is what turns "something failed during the
demo" into "here's the exact request_id, here's the exact log line" if you
ever need to explain a live hiccup to a judge with precision instead of a
shrug.

---

## 7. Definition of Done (full checklist)

- [ ] Every route handler is under ~15 lines and contains no business-logic branching — verified by code review against the standard in section 2.1, not just by line count.
- [ ] `DomainError` and its subclasses are the only way route handlers signal business-logic failures; no raw `HTTPException` for domain errors.
- [ ] Unhandled exceptions never leak a stack trace or sensitive details to the client — verified by `test_unexpected_exception_never_leaks_stack_trace`.
- [ ] OpenAPI schema is exported to `packages/api-contracts/openapi.json` and a drift-detection test is wired into CI.
- [ ] TypeScript client generated into `packages/api-contracts/generated/` from the OpenAPI schema.
- [ ] `audit_log` immutability proven by a test connecting as the real `resiliencepay_app`-inheriting role, bypassing the application entirely.
- [ ] `/docs` (FastAPI's auto-generated interactive API docs) is reachable and reflects every implemented route.

---

## 8. Prompts for your coding agent

Use these as focused, sequential prompts. `CLAUDE.md`'s repo-wide standards
apply automatically; these assume that context is already loaded (see
`docs/AGENT_KICKOFF_PROMPT.md`).

### Prompt 1 — App factory and structured error handling
```
Implement apps/api/src/main.py and apps/api/src/middleware/error_handler.py
per docs/phases/PHASE_09_api_audit_DETAILED.md sections 3.1 and 3.2:
DomainError, NotFoundError, and register_error_handlers with both a
DomainError handler and a catch-all Exception handler that never leaks a
stack trace or exception message text to the client — log full details
server-side via structlog with a request_id, return only a generic safe
body. Write apps/api/tests/test_unhandled_exception_handling.py per
section 5.2 of the doc, using monkeypatch to force an underlying services/*
call to raise a RuntimeError with a deliberately sensitive-looking message,
and assert that message text never appears anywhere in the HTTP response.
```

### Prompt 2 — Thin routers
```
Implement apps/api/src/routers/events.py, batch.py, metrics.py, and
audit.py per docs/phases/PHASE_09_api_audit_DETAILED.md sections 3.3-3.5.
Every handler must satisfy the 'under ~15 lines, no business-logic
branching' standard from section 2.1 of the doc — if implementing a route
requires a conditional beyond HTTP status/response shaping, stop and
implement that logic as a new function in the relevant services/* module
instead (e.g., services/observe/query_service.py for read-side helpers),
then call it from the thin router. Check the actual function signatures
already implemented in services/diagnose, services/gate, services/observe,
and services/audit from earlier phases before writing these routers —
do not invent new service-layer function names without checking what
already exists. Write apps/api/tests/test_events_router.py per section 5.1.
```

### Prompt 3 — OpenAPI export and typed client
```
Set up the OpenAPI export and TypeScript client generation pipeline per
docs/phases/PHASE_09_api_audit_DETAILED.md section 3.6: a script or
Makefile target that dumps apps/api/src/main.py's app.openapi() to
packages/api-contracts/openapi.json, and runs openapi-typescript to
generate packages/api-contracts/generated/schema.ts. Add this as a
pre-commit hook or CI step. Write apps/api/tests/test_contract_openapi.py
per section 5.3, asserting the checked-in openapi.json matches what the
running app currently generates — this test should FAIL if someone changes
a route without regenerating the contract, which is the entire point.
```

### Prompt 4 — Audit immutability proof (bypassing the application)
```
Write apps/api/tests/test_audit_immutability.py per
docs/phases/PHASE_09_api_audit_DETAILED.md section 5.4, connecting directly
via psycopg2 as a test login role that inherits resiliencepay_app (create
this test role via a test fixture or a documented one-time setup step —
check whether packages/db-models/alembic/versions/0006_audit_log.py already
established this pattern during Phase 1, and reuse the exact same
verification approach rather than inventing a new one). This test must
prove, independent of any application code, that INSERT/SELECT succeed and
UPDATE/DELETE are rejected by Postgres itself for this role.
```

### Prompt 5 — Full integration pass and Definition of Done
```
Wire main.py, all four routers, the error handlers, and the OpenAPI export
together, boot the app with uvicorn, and hit /healthz and /docs to confirm
it actually runs (not just imports cleanly) — show me the real curl output
for both, don't just tell me it works. Then work through the full
Definition of Done checklist in section 7 of
docs/phases/PHASE_09_api_audit_DETAILED.md and report back which items
pass, with actual test output for every relevant test file, including the
audit immutability test's real output showing the InsufficientPrivilege
errors being correctly raised and caught.
```
