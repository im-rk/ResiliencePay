# Phase 0 — Foundations & Engineering Standards

**Depends on:** nothing (first phase)
**Unblocks:** every other phase
**Owner:** whoever sets up the repo (typically the most infra-comfortable team member)
**Estimated time:** ~2-3 hours

## Objective
Establish engineering scaffolding before any business logic exists, so every
later phase inherits consistent standards instead of retrofitting them under
time pressure.

## Scope
**In scope:** repo skeleton, config validation, linting/formatting, CI
pipeline, branching/PR policy, docker-compose skeleton with health checks.
**Out of scope:** any actual business logic, DB schema, or API routes —
those belong to Phases 1+.

## Deliverables mapped to monorepo paths

| Path | What goes here |
|---|---|
| `pyproject.toml` (root) | Python workspace definition, shared dev-dependencies (`black`, `ruff`, `mypy`, `pytest`) |
| `package.json` (root) | Dashboard workspace definition |
| `packages/config/settings.py` | `pydantic.BaseSettings` subclass, validates all required env vars at import time |
| `.env.example` | Every env var the system needs, with dummy/placeholder values, committed |
| `.pre-commit-config.yaml` | Hooks: `black`, `ruff`, `mypy` (backend); `eslint`, `prettier` (frontend) |
| `.github/workflows/ci.yml` | `lint → typecheck → test`, required check on PRs |
| `CONTRIBUTING.md` | Branch naming (`feat/…`, `fix/…`), Conventional Commits, PR review requirement |
| `infra/docker-compose.yml` | `api`, `worker`, `postgres`, `redis`, `dashboard` services, each with a `healthcheck` block |
| `infra/docker-compose.override.yml` | Local dev overrides (hot reload volumes, exposed debug ports) |

## Detailed task breakdown

1. **Repo init & directory skeleton**
   - Create every top-level directory from `MONOREPO_STRUCTURE.md` as empty
     dirs with a `.gitkeep` or a stub `__init__.py`, so the structure is
     visible in the first commit before any code lands.
   - Acceptance: `tree -L 3` output matches `MONOREPO_STRUCTURE.md`.

2. **`packages/config/settings.py`**
   ```python
   from pydantic_settings import BaseSettings

   class Settings(BaseSettings):
       database_url: str
       redis_url: str
       razorpay_key_id: str
       razorpay_key_secret: str
       anthropic_api_key: str
       env: str = "development"

       class Config:
           env_file = ".env"

   settings = Settings()  # raises at import time if any required var is missing
   ```
   - Acceptance: running any app entrypoint with a missing required env var
     fails immediately with a clear Pydantic validation error, not a
     downstream `KeyError` three layers deep.

3. **Linting/formatting/type-checking setup**
   - `pyproject.toml`: configure `black` (line length 100), `ruff` (import
     sorting + common bug-pattern lint rules), `mypy` (`strict = true` for
     `services/` and `packages/`, relaxed for `apps/dashboard`'s generated
     types).
   - `.pre-commit-config.yaml` wiring all of the above to run on `git commit`.
   - Acceptance: `pre-commit run --all-files` passes on an empty/skeleton repo.

4. **CI pipeline**
   - `.github/workflows/ci.yml`: matrix job across `apps/api`,
     `apps/worker`, `services/*` running `ruff check`, `mypy`, `pytest
     --cov`; separate job for `apps/dashboard` running `eslint`, `tsc
     --noEmit`, `vitest run`.
   - Required status check on the default branch (branch protection rule).
   - Acceptance: a trivial PR (e.g., a README typo fix) shows all CI jobs
     green and cannot be merged without at least one approval.

5. **`docker-compose.yml` with health checks**
   ```yaml
   services:
     postgres:
       image: postgres:16
       healthcheck:
         test: ["CMD-SHELL", "pg_isready -U postgres"]
         interval: 5s
         timeout: 3s
         retries: 5
     redis:
       image: redis:7
       healthcheck:
         test: ["CMD", "redis-cli", "ping"]
         interval: 5s
     api:
       build: ../apps/api
       depends_on:
         postgres:
           condition: service_healthy
         redis:
           condition: service_healthy
   ```
   - Acceptance: `docker-compose up` on a clean clone brings up all five
     services to a healthy state with zero manual intervention beyond
     `cp .env.example .env`.

6. **`CONTRIBUTING.md`**
   - Document: branch naming, commit convention, PR template (what a PR
     description must include: what changed, how it was tested), review
     requirement (1 approval minimum).

## Design decisions & trade-offs

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Monorepo vs. polyrepo | 3 separate repos | Monorepo | Cross-cutting changes (schema→API→dashboard) land atomically; polyrepo versioning overhead isn't worth it at 10-day, 4-person scale |
| Config validation | `.env` read ad hoc vs. validated `Settings` class | Validated `Settings` class | Fails fast at boot, not deep in a request handler |
| Branching | GitFlow vs. trunk-based | Trunk-based, short-lived branches | GitFlow overhead unjustified at this scale; trunk-based keeps everyone continuously integrated |
| Code review | Skip for speed vs. mandatory | Mandatory 1-reviewer approval | Cheap, high-signal for your submission; genuinely catches bugs in money-handling code |

## Definition of Done
- [ ] `docker-compose up` succeeds from a clean clone with zero manual steps beyond `.env.example` → `.env`.
- [ ] A trivial PR demonstrates full CI green + requires review to merge.
- [ ] `pre-commit run --all-files` passes.
- [ ] Repo skeleton matches `MONOREPO_STRUCTURE.md` exactly.

## Handoff to Phase 1
Phase 1 assumes: a working `pyproject.toml` workspace, a validated
`Settings` class importable from `packages/config`, and a healthy
`postgres` service reachable via `docker-compose`.
