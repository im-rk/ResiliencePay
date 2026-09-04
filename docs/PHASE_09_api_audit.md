# Phase 9 — API & Audit Trail

**Depends on:** Phases 1-8 (everything the API exposes)
**Unblocks:** Phase 10 (dashboard consumes this API exclusively)
**Owner:** backend/API owner
**Estimated time:** ~1 day

## Objective
Expose the system via a documented, versioned API; make the audit trail a
first-class, queryable, provably-immutable artifact — not just a log file.

## Scope
**In scope:** all `/v1/` routes, OpenAPI contract generation, DB-level
immutability verification.
**Out of scope:** how the dashboard renders this data (Phase 10).

## Deliverables mapped to monorepo paths

| Path | What goes here |
|---|---|
| `apps/api/src/main.py` | App factory, middleware, router registration |
| `apps/api/src/routers/events.py` | `POST /v1/events/ingest`, `GET /v1/events/{id}` |
| `apps/api/src/routers/batch.py` | `POST /v1/pipeline/run-batch` |
| `apps/api/src/routers/metrics.py` | `GET /v1/metrics/summary`, `GET /v1/metrics/learning-curve` |
| `apps/api/src/routers/audit.py` | `GET /v1/audit-trail` |
| `apps/api/src/middleware/error_handler.py` | Converts domain exceptions → structured API errors |
| `packages/api-contracts/openapi.json` | Auto-generated OpenAPI spec, exported for the dashboard's typed client |
| `apps/api/tests/test_contract_openapi.py` | Snapshot test on the OpenAPI schema |
| `apps/api/tests/test_audit_immutability.py` | DB-level UPDATE/DELETE rejection test using the real `app_role` |

## Detailed task breakdown

1. **Router implementation** — thin controllers that call into `services/*`
   directly; **no business logic lives in `apps/api`** — this is what keeps
   Phase 8's batch harness able to run the same logic without a web server.

2. **Structured error contract**
   ```python
   class DomainError(Exception):
       def __init__(self, code: str, reason: str, **context):
           self.code, self.reason, self.context = code, reason, context

   @app.exception_handler(DomainError)
   def handle_domain_error(request, exc: DomainError):
       return JSONResponse(status_code=422, content={
           "error": True, "code": exc.code, "reason": exc.reason, **exc.context
       })
   ```
   This is what lets you show "one failure handled gracefully" as a visible,
   labeled API response rather than a 500 stack trace on stage.

3. **`GET /v1/audit-trail?episode_id=...&cause=...&arm=...`** — filterable,
   paginated, backed by the indexed `audit_log` table from
   `DATABASE_DESIGN.md`.

4. **`GET /v1/metrics/learning-curve?run_id=...`** — buckets outcomes by
   batch index (e.g., rolling windows of 20 events), computes recovery rate
   per bucket — this is the exact data shape Phase 10's chart needs, so
   design this endpoint's response shape together with whoever builds that
   chart.

5. **OpenAPI export + typed client generation** — FastAPI auto-generates
   `/openapi.json`; export it into `packages/api-contracts/openapi.json` and
   run a TS client generator (e.g., `openapi-typescript`) into
   `packages/api-contracts/generated/`, consumed by `apps/dashboard`. This
   is what guarantees the dashboard never silently drifts out of sync with
   the API contract.

6. **DB-level immutability test** — connect directly using the real
   `app_role` credentials (bypassing the ORM/app layer entirely) and attempt
   an `UPDATE`/`DELETE` on `audit_log`; assert it's rejected by Postgres.

## Edge-case matrix

| Case | Expected behavior |
|---|---|
| `GET /v1/events/{id}` for a nonexistent event | `404` with structured error body, not an unhandled exception |
| `POST /v1/pipeline/run-batch` called with `n=0` | `422` with a clear validation message, not a silent no-op |
| Any handler raises an unexpected (non-`DomainError`) exception | Caught by a top-level handler, returns a generic `500` with a request ID for correlation, never leaks a raw stack trace to the client |

## Design decisions & trade-offs

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Audit write mechanism | DB trigger vs. app-level write-through (Phase 7) | App-level, single `AuditLogService` | Faster to iterate on in 10 days; still centralizes all writes through one path |
| Audit immutability | Convention only vs. DB permission enforcement | DB permission enforcement | Converts "we promise not to edit" into "the database physically will not allow it" |
| API versioning | Unversioned vs. `/v1/` from day one | `/v1/` from day one | Costs nothing, signals forward-thinking API design |

## Test plan
- **Permission test:** direct `UPDATE`/`DELETE` attempt via `app_role`, bypassing the app layer, rejected by Postgres.
- **Contract test:** OpenAPI schema snapshot-tested so accidental breaking changes are caught in CI.
- **Router tests:** happy path + at least one error path per route.

## Definition of Done
- [ ] DB-level immutability of `audit_log` proven by a test bypassing the app.
- [ ] Full `/v1/` API documented via auto-generated OpenAPI, browsable at `/docs`.
- [ ] `packages/api-contracts` exports a typed client the dashboard actually imports (not a hand-maintained duplicate type).

## Handoff to Phase 10
Phase 10 assumes: every data need it has maps to exactly one documented
`/v1/` endpoint, and that it can import types from
`packages/api-contracts/generated` rather than hand-writing its own
response interfaces.
