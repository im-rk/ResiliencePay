# Tech Stack — ResiliencePay

## 1. Guiding principles for stack choices

1. **Boring where it doesn't matter, sharp where it does.** The bandit,
   diagnosis, and gate logic is where you show engineering judgment — the
   web framework and DB choice should be reliable and fast to build with,
   not novel for novelty's sake.
2. **Every choice must be defensible in 30 seconds if a judge asks "why
   this?"** — each row below includes that answer.
3. **Type safety end-to-end** where cheap to get — money-handling code is
   exactly where a `string` vs `int` bug becomes an embarrassing live-demo
   failure.

## 2. Stack overview

| Layer | Choice | Why (30-second answer) |
|---|---|---|
| Backend language/framework | **Python 3.12 + FastAPI** | Native async, automatic OpenAPI docs (free API contract artifact for judges), first-class numpy/pandas for the bandit math, mature Razorpay SDK |
| Decision engine (bandit) | **Python, numpy/scipy** | Thompson Sampling is a few lines of Beta-distribution sampling — no need for a heavy ML framework, which itself is a judgment signal ("we used the right-sized tool") |
| LLM integration | **Anthropic API (Claude)**, called via a thin internal `llm_client` wrapper | Wrapper lets you swap models/providers without touching business logic — a real production pattern, not a hardcoded SDK call scattered everywhere |
| Database | **PostgreSQL 16** | ACID transactions matter here — you're modeling money-adjacent state transitions; JSONB columns give you schema flexibility for gateway payloads without going full NoSQL |
| ORM / migrations | **SQLAlchemy 2.0 + Alembic** | Versioned schema migrations are a concrete "we thought about this like a real system" artifact — `alembic/versions/` in your repo is free credibility |
| Cache / bandit hot-state | **Redis** | Bandit arm statistics (α, β per bucket) are read/written on every event — keep this in-memory-fast, persist to Postgres periodically as a durability backstop |
| Task queue | **Celery + Redis broker** (or FastAPI `BackgroundTasks` if time-constrained) | Retry scheduling (`retry_short_delay`, `retry_long_delay`) is inherently a delayed-job problem — a real queue models this correctly instead of a `time.sleep()` hack |
| Payments | **Razorpay Python SDK**, test-mode keys | Required by the track |
| Frontend | **React 18 + TypeScript + Vite** | Type safety on the dashboard too; Vite for fast local iteration during the 10 days |
| Charts | **Recharts** | Clean, fast to wire for the learning-curve and arm-distribution visuals |
| Styling | **Tailwind CSS** | Fast, consistent, no design-system bikeshedding under time pressure |
| Auth (if needed for multi-user demo) | **JWT via FastAPI security utils** | Minimal, standard, don't over-engineer this — it's not the point of the demo |
| Testing | **pytest** (backend), **Vitest** (frontend) | Standard, and having a visible `tests/` folder with passing CI is a strong signal on its own |
| CI | **GitHub Actions** — lint + test on every push | Costs almost nothing to set up, and "green checkmarks in the repo" is a cheap, high-signal credibility boost for recruiters browsing your GitHub |
| Containerization | **Docker + docker-compose** (api, worker, postgres, redis, frontend) | `docker-compose up` as your entire local setup story is exactly what a production-minded reviewer wants to see |
| Deployment (optional, if you want a live URL) | **Railway or Render** for backend+DB, **Vercel** for frontend | Fastest path to a real public URL to put in your submission, not required but a strong bonus |
| Observability | **Structured logging (structlog) → stdout**, optionally piped to a simple log viewer in the dashboard | The audit trail *is* your primary observability artifact; keep infra logging separate and simple |
| Secrets management | **.env + python-dotenv locally**, never committed; `.env.example` checked in | Standard hygiene — checked-in secrets is an instant credibility loss if a judge looks at your repo |

## 3. Why this specific combination signals "production-minded," not just "hackathon-fast"

- **Postgres + Alembic migrations** over "just a JSON file" shows you modeled
  the domain with real entities, relationships, and constraints — see
  `DATABASE_DESIGN.md`.
- **Redis-backed bandit state** shows you thought about the difference
  between hot, frequently-updated state and durable system-of-record data —
  a genuine architectural distinction, not just "use a database for
  everything."
- **A task queue for delayed retries** models the real-world timing problem
  correctly instead of faking it with a loop and a sleep call.
- **Docker Compose** means anyone (a judge, a recruiter, a future teammate)
  can run the entire system with one command — this alone differentiates
  you from most hackathon repos that only run on the author's laptop.

## 4. What to deliberately NOT build (protect your 10 days)

- No Kubernetes, no microservices split beyond api/worker — a monolith with
  clean internal module boundaries (`diagnose/`, `decide/`, `gate/`, `act/`,
  `observe/`, `audit/`) gets you 90% of the "production architecture" signal
  for 10% of the operational complexity.
- No custom auth/identity system beyond a minimal JWT stub — not the point
  of this build.
- No Kafka/event-streaming infrastructure — Celery+Redis is more than
  sufficient at hackathon scale and is much faster to stand up correctly.
