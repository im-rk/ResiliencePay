# Phase 1 — Data Layer

**Depends on:** Phase 0 (config, workspace, CI, docker-compose)
**Unblocks:** Phase 2 (generator needs the schema), Phases 3-9 (everything reads/writes this schema)
**Owner:** DB/backend-strongest team member
**Estimated time:** ~1 day

## Objective
Stand up the full schema from `DATABASE_DESIGN.md` as versioned migrations,
with constraint enforcement and a factory-based test-data strategy that
every later phase can depend on without ambiguity.

## Scope
**In scope:** SQLAlchemy models, Alembic migrations, DB constraints, factory
fixtures, constraint-level tests.
**Out of scope:** any business logic that writes to these tables (Phases 3+).

## Deliverables mapped to monorepo paths

| Path | What goes here |
|---|---|
| `packages/db-models/models/*.py` | One file per entity: `merchant.py`, `customer.py`, `episode.py`, `event.py`, `diagnosis.py`, `decision.py`, `gate_check.py`, `action.py`, `outcome.py`, `bandit_arm_stats.py`, `batch_run.py`, `audit_log.py`, `opt_out.py` |
| `packages/db-models/alembic/versions/` | One migration per logical table group |
| `packages/db-models/factories.py` | `factory_boy` factories for every model |
| `packages/domain-constants/arms.py` | `Arm` enum/constants — single source of truth, referenced by DB seed data and by `services/decide` |
| `packages/domain-constants/cause_categories.py` | `CauseCategory` enum/constants — same pattern |
| `packages/db-models/tests/test_constraints.py` | Constraint edge-case tests |
| `packages/db-models/tests/test_migrations.py` | Up/down/up migration cycle test |

## Detailed task breakdown

1. **Model definitions** — translate every `CREATE TABLE` in
   `DATABASE_DESIGN.md` §2 into a SQLAlchemy 2.0 declarative model,
   including all `CHECK` constraints, foreign keys, and indexes exactly as
   specified there. Do not simplify constraints "to move faster" — they are
   the safety net for Phase 6's money-handling code.

2. **Alembic setup**
   ```bash
   cd packages/db-models
   alembic init alembic
   ```
   Configure `alembic/env.py` to import `Base.metadata` from your models
   package for autogenerate support.

3. **Migrations, one logical group per file:**
   - `0001_core_entities.py` — merchants, customers, opt_outs
   - `0002_episodes_events.py` — episodes, events
   - `0003_pipeline_stages.py` — diagnoses, decisions, gate_checks, actions, outcomes
   - `0004_lookup_tables.py` — cause_categories, arms (+ seed `INSERT`s)
   - `0005_bandit_and_batch.py` — bandit_arm_stats, batch_runs, batch_run_metrics
   - `0006_audit_log.py` — audit_log + **revoke UPDATE/DELETE grants for the app role**

4. **Audit log immutability (do this in the same migration that creates it)**
   ```sql
   CREATE ROLE app_role NOLOGIN;
   GRANT SELECT, INSERT ON audit_log TO app_role;
   REVOKE UPDATE, DELETE ON audit_log FROM app_role;
   ```
   This is the concrete, testable version of "append-only audit trail" —
   don't leave it as a comment/convention.

5. **`factories.py`**
   ```python
   import factory
   from packages.db_models.models import Episode

   class EpisodeFactory(factory.alchemy.SQLAlchemyModelFactory):
       class Meta:
           model = Episode
           sqlalchemy_session_persistence = "commit"

       episode_type = "subscription_charge_failed"
       original_amount = factory.Faker("random_int", min=9900, max=999900)
       currency = "INR"
       status = "open"
   ```
   One factory per model, composable (e.g., `EventFactory` takes an
   `episode` param defaulting to `factory.SubFactory(EpisodeFactory)`).

6. **Constraint edge-case tests** — implement every row of the edge-case
   matrix below as a `pytest.raises(IntegrityError)` test.

## Edge-case matrix (must all be covered by tests)

| Case | Expected DB behavior |
|---|---|
| Insert episode with `original_amount = 0` | Rejected (`chk_episode_amount`) |
| Insert event with `retry_count_so_far = -1` | Rejected (`chk_retry_count`) |
| Insert outcome with negative `amount_recovered` | Rejected (`chk_amount_recovered`) |
| Insert action referencing nonexistent `decision_id` | Rejected (FK violation) |
| Delete a customer with existing episodes | Cascades (`ON DELETE CASCADE`) — assert this is intentional, not accidental |
| `app_role` attempts `UPDATE`/`DELETE` on `audit_log` | Rejected at the DB permission level |

## Design decisions & trade-offs

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Schema evolution | Single SQL dump vs. incremental Alembic migrations | Alembic, one migration per logical group | Visible migration history is itself an engineering-discipline artifact; mirrors real production schema evolution |
| Constraint enforcement | App-layer only vs. DB-layer `CHECK` | Both — DB is source of truth | Defense in depth; a bug in app validation can't write a negative amount to the DB |
| Test data | Hand-written fixtures vs. factory pattern | `factory_boy` | Generates valid-by-construction rows, overridable per test, scales with the schema |
| Enum-like values | Postgres `ENUM` type vs. lookup table | Lookup table (`cause_categories`, `arms`) | Adding a new category is a data migration, not a schema migration + redeploy |

## Test plan
- **Unit:** each row in the edge-case matrix.
- **Integration:** factory-built full chain (merchant→customer→episode→event) inserts cleanly, relationships traversable via ORM.
- **Migration test:** `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` succeeds cleanly.

## Definition of Done
- [ ] All edge-case matrix tests pass.
- [ ] Migration up/down/up cycle is clean.
- [ ] `audit_log` UPDATE/DELETE rejection proven by a test using the actual `app_role`, not just asserted in a comment.
- [ ] Factories exist for every core table.

## Handoff to Phase 2
Phase 2 assumes: all models importable from `packages.db_models.models`,
factories available for constructing valid test rows, and `cause_categories`
/ `arms` lookup tables seeded.
