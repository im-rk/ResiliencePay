# Monorepo Folder Structure — ResiliencePay

## Do you need a frontend? (short version)

Yes — one thin dashboard screen, not a full product. The track's bar
("show the audit trail and one failure handled gracefully") is inherently
visual; judges need to *see* the learning curve and metrics table, not read
raw JSON. Scope it to ~5 panels (live feed, metrics, learning curve, audit
trail, exceptions), skip auth/settings/onboarding entirely. Budget ~1.5-2
of your 10 days for it, not more.

## Design principles behind this layout

1. **Domain-oriented, not layer-oriented, inside the core service.** You
   will NOT find a top-level `controllers/`, `models/`, `views/` split.
   Instead, each pipeline stage (`diagnose/`, `decide/`, `gate/`, `act/`,
   `observe/`) is a self-contained module with its own models, service
   logic, and tests — this mirrors how large engineering orgs structure
   domain-driven monorepos (bounded contexts), and it's what let Phase 11's
   chaos testing bolt on cleanly without touching unrelated code.
2. **`packages/` holds anything imported by 2+ apps** — shared types, the
   OpenAPI-generated client, shared constants (arm names, cause categories).
   Nothing in `apps/` should ever import another app's internals directly;
   cross-app sharing only happens through `packages/`.
3. **Infra-as-code lives in the repo**, not in someone's terminal history —
   `infra/` holds Docker, migrations, and (optionally) deployment configs,
   version-controlled like everything else.
4. **Tests live next to the code they test**, not in a single mirrored
   `tests/` tree far from the source — faster to navigate, and it's the
   convention most modern monorepos (Google, Meta-style) actually use.
5. **One root-level dependency lockfile philosophy per language** — Python
   services share a `pyproject.toml`-based workspace (via `uv` or `poetry`
   workspaces); the frontend has its own `package.json`. No dependency
   drift between backend services.

## Full tree

```
resiliencepay/
├── apps/
│   ├── api/                          # FastAPI HTTP service — the ONLY public entrypoint
│   │   ├── src/
│   │   │   ├── main.py               # app factory, middleware, router registration
│   │   │   ├── routers/
│   │   │   │   ├── events.py         # POST /v1/events/ingest, GET /v1/events/{id}
│   │   │   │   ├── batch.py          # POST /v1/pipeline/run-batch
│   │   │   │   ├── metrics.py        # GET /v1/metrics/summary, /v1/metrics/learning-curve
│   │   │   │   └── audit.py          # GET /v1/audit-trail
│   │   │   ├── dependencies.py       # DB session, auth (if any), settings injection
│   │   │   └── middleware/
│   │   │       ├── error_handler.py  # converts domain exceptions -> structured API errors
│   │   │       └── request_logging.py
│   │   ├── tests/
│   │   │   ├── test_events_router.py
│   │   │   └── test_contract_openapi.py   # snapshot test on the OpenAPI schema
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── worker/                       # Celery worker — delayed retries, scheduled reconciliation
│   │   ├── src/
│   │   │   ├── celery_app.py
│   │   │   ├── tasks/
│   │   │   │   ├── execute_delayed_action.py
│   │   │   │   ├── reconcile_payment_status.py   # polling safety-net for missed webhooks
│   │   │   │   └── snapshot_bandit_state.py      # Redis -> Postgres periodic durability write
│   │   │   └── beat_schedule.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   └── dashboard/                    # React + TypeScript + Vite — the one demo screen
│       ├── src/
│       │   ├── main.tsx
│       │   ├── App.tsx
│       │   ├── panels/
│       │   │   ├── LiveEventFeed.tsx
│       │   │   ├── MetricsSummary.tsx
│       │   │   ├── LearningCurveChart.tsx
│       │   │   ├── ArmDistributionChart.tsx
│       │   │   ├── AuditTrailTable.tsx
│       │   │   └── ExceptionList.tsx
│       │   ├── hooks/
│       │   │   ├── useMetrics.ts             # React Query wrapper
│       │   │   ├── useAuditTrail.ts
│       │   │   └── usePolling.ts             # shared polling abstraction, swappable for WS later
│       │   ├── api/
│       │   │   └── client.ts                 # generated from packages/api-contracts OpenAPI spec
│       │   └── lib/
│       │       └── format.ts                 # paise -> ₹ formatting, date formatting
│       ├── tests/                            # Vitest + Testing Library component tests
│       ├── Dockerfile
│       └── package.json
│
├── services/                         # domain logic, imported by apps/api and apps/worker — NOT web-facing itself
│   ├── diagnose/
│   │   ├── rules.py                  # gateway_error_code -> cause_category lookup
│   │   ├── llm_fallback.py
│   │   ├── service.py                # orchestration: rules -> LLM fallback -> DiagnosisResult
│   │   ├── schemas.py                # DiagnosisResult, CauseCategory enum
│   │   └── tests/
│   │
│   ├── decide/
│   │   ├── bandit.py                 # BanditPolicy Protocol + Thompson Sampling implementation
│   │   ├── baseline_policy.py        # naive policy, same Protocol
│   │   ├── context.py                # context_bucket construction logic
│   │   ├── redis_store.py            # hot-path α/β state
│   │   └── tests/
│   │       ├── test_convergence.py
│   │       └── test_concurrency.py
│   │
│   ├── gate/
│   │   ├── rules.py                  # check_max_attempts, check_opt_out, check_cool_off, check_time_window
│   │   ├── service.py                # evaluate_gate orchestration
│   │   └── tests/
│   │       ├── test_rules.py
│   │       └── test_adversarial.py   # the "high-confidence bandit but still blocked" test
│   │
│   ├── act/
│   │   ├── razorpay_client.py        # idempotency-key-aware wrapper over Razorpay SDK
│   │   ├── nudge_generator.py        # LLM-based Hinglish/English message generation
│   │   ├── fault_injection.py        # Phase 11: chaos testing hooks, flag-gated
│   │   ├── service.py
│   │   └── tests/
│   │       ├── test_idempotency.py
│   │       └── test_chaos.py         # fault-injection-enabled test suite
│   │
│   ├── observe/
│   │   ├── webhook_handlers.py       # payment.captured, subscription.charge.failed, etc.
│   │   ├── reward_service.py         # outcome -> reward computation
│   │   └── tests/
│   │
│   └── audit/
│       ├── audit_log_service.py      # SINGLE write path into audit_log table
│       └── tests/
│
├── packages/                         # shared across apps/ and services/ — no business logic here
│   ├── db-models/                    # SQLAlchemy models + Alembic migrations, per DATABASE_DESIGN.md
│   │   ├── models/
│   │   │   ├── merchant.py
│   │   │   ├── customer.py
│   │   │   ├── episode.py
│   │   │   ├── event.py
│   │   │   ├── diagnosis.py
│   │   │   ├── decision.py
│   │   │   ├── gate_check.py
│   │   │   ├── action.py
│   │   │   ├── outcome.py
│   │   │   ├── bandit_arm_stats.py
│   │   │   ├── batch_run.py
│   │   │   └── audit_log.py
│   │   ├── alembic/
│   │   │   ├── versions/
│   │   │   └── env.py
│   │   └── factories.py              # factory_boy test-data factories
│   │
│   ├── domain-constants/             # arm names, cause categories — single source of truth
│   │   ├── arms.py
│   │   └── cause_categories.py
│   │
│   ├── api-contracts/                # OpenAPI spec (generated from apps/api) + generated TS client
│   │   ├── openapi.json
│   │   └── generated/                # auto-generated TS types consumed by apps/dashboard
│   │
│   └── config/
│       └── settings.py               # pydantic BaseSettings, imported by api + worker
│
├── data/
│   ├── generator.py                  # synthetic dataset generator, per DATA_MODEL.md
│   ├── error_code_samples.py         # realistic Razorpay-style error code pools per cause category
│   └── fixtures/                     # small hand-crafted datasets for demo/testing (not the full batch)
│
├── eval/
│   ├── run_batch.py                  # orchestrates a full batch run for a given policy
│   ├── baseline_runner.py
│   ├── metrics_queries.sql           # the SQL views/queries that independently verify Python-computed metrics
│   └── results/                      # cached batch-run outputs, used as the live-demo fallback
│
├── infra/
│   ├── docker-compose.yml            # api, worker, postgres, redis, dashboard, all wired together
│   ├── docker-compose.override.yml   # local dev overrides (hot reload, exposed debug ports)
│   └── deploy/                       # optional: Railway/Render/Vercel configs, if you deploy a live demo URL
│
├── docs/                             # everything already built: PRD, ARCHITECTURE, DATABASE_DESIGN, etc.
│   ├── README.md
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   ├── ML_DESIGN.md
│   ├── API_SPEC.md
│   ├── DATABASE_DESIGN.md
│   ├── TECH_STACK.md
│   ├── TESTING_METRICS.md
│   ├── DEMO_SCRIPT.md
│   ├── ROADMAP.md
│   ├── IMPLEMENTATION_GUIDE.md
│   └── PHASE_IMPLEMENTATION_PLAN.md
│
├── .github/
│   └── workflows/
│       ├── ci.yml                    # lint -> typecheck -> test, required on every PR
│       └── chaos-nightly.yml         # optional: runs the Phase 11 chaos suite on a schedule
│
├── .pre-commit-config.yaml
├── .env.example
├── CONTRIBUTING.md
├── pyproject.toml                    # workspace root — Python backend services share this
├── package.json                      # workspace root for the dashboard (or a full pnpm/turbo workspace if you want apps/dashboard + packages/api-contracts wired together)
└── README.md                         # top-level: what this is, how to run it, links into docs/
```

## Why `services/` is separate from `apps/` (the decision worth explaining to a judge)

`apps/` contains things that run as standalone processes with their own
entrypoint (`api`, `worker`, `dashboard`). `services/` contains pure domain
logic with **no knowledge of HTTP, Celery, or React** — `diagnose/`,
`decide/`, `gate/`, `act/`, `observe/`, `audit/` are plain importable Python
modules. This is what makes Phase 8's batch harness possible without
spinning up a web server, and what made Phase 11's chaos testing cheap to
bolt on: the fault-injection hooks live inside `services/act/`, completely
decoupled from whether the call originated from an API request or a batch
script. If asked "why is your business logic not inside your FastAPI app,"
this is the answer: **the domain logic has to be runnable outside the web
server, because the batch evaluation harness is a first-class consumer of
it, not an afterthought.**

## Why `packages/db-models` is its own package, not inside `apps/api`

Both `apps/api` and `apps/worker` need the SQLAlchemy models and Alembic
migrations. Putting them inside `apps/api` would force `apps/worker` to
depend on the entire API app just to get a `Merchant` model — a classic
monorepo anti-pattern. Extracting it to `packages/db-models` means each
`app` only depends on exactly the packages it needs, which is the actual
point of a monorepo done well (shared code without unnecessary coupling).

## What NOT to over-build here

- No `apps/mobile` — not needed, don't scaffold it just to look bigger.
- No Nx/Turborepo build-graph tooling unless your team already knows it
  well — a plain `pyproject.toml` workspace + a single `package.json` for
  the dashboard is enough at this scale; adding a monorepo build tool you
  don't already know is a 10-day-budget risk, not a signal of maturity.
- No `packages/ui-components` design system — one dashboard, ~5 panels,
  doesn't need a component library layer yet.
