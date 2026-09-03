# Current Status & Next Steps — ResiliencePay

This is the honest, working-state document — not aspirational. Update it
as phases actually complete. Its job is to answer one question at a
glance: **what's real right now, and what's the single next highest-leverage
thing to build.**

## 1. What's actually real and running (verified, not just documented)

### Verification record — 2026-09-02

- Local backend/service tests: **83 passed** when run with the repository's
   application and service test paths.
- Dashboard tests: **7 passed**; production TypeScript/Vite build succeeds.
- API health, metrics, audit fallback, CORS, and the SSE route were exercised
   locally. The dashboard now reconnects after a temporary SSE outage.
- `.env` contains configured `DATABASE_URL`, `REDIS_URL`, `GEMINI_API_KEY`,
   and Razorpay variables. Secrets were not printed.
- Live Supabase and Upstash connectivity are **not verified**: the configured
   endpoints refused connections during the last smoke test. Real database
   writes, Redis-backed bandit updates, and Razorpay calls therefore remain
   release blockers.
- The full default test selection includes data tests that require the live
   database schema; scratch probes are excluded by `testpaths`.

- **Phase 0 (Foundations):** `pyproject.toml` workspace, Pydantic `Settings` class (validated at boot), `docker-compose.yml` with health checks, `.env.example`.
- **Phase 1 (Data Layer):** All 16 tables from `DATABASE_DESIGN.md` implemented as SQLAlchemy models, with Alembic migrations. Live Supabase schema verification is still pending.
- **Phase 2-3 (Synthetic Data & Diagnose):** Generating realistic failed payment events, with rule-based diagnosis and Gemini fallback covered by tests. Live Gemini verification is still pending.
- **Phase 4 (Gate):** Deterministic compliance checks verified against adversarial ML conditions. `GateContext` structurally enforces independence.
- **Phase 5-7 (Decide, Act, Observe):** Contextual bandit, Razorpay wrapper, simulated LLM nudges, webhook handlers, and audit logging are implemented and unit-tested. Live Redis/Razorpay/webhook verification is still pending.
- **Phase 8 (Batch Eval):** `run_batch.py` script running synthetic multi-seed evaluations.
- **Phase 9-10 (API & Dashboard):** Live React frontend visualizing metrics, the learning curve, and the audit trail dynamically.
- **Phase 11 (Resilience/Chaos):** Fault injection and no-gap behavior are covered by tests; a live 15% chaos run remains to be rehearsed.
- **Phase 12 (Submission):** Documentation parity achieved.
- **Advanced Features:** Semantic caching/LLM fallback, payment-instrument context, promise-to-pay extraction, circuit breaking, narrator, and Redis Streams ingestion have implementation and unit coverage. They are not all proven against live external services yet.

## 2. What's fully documented but not yet coded

The remaining release-level work is live infrastructure verification: restore
Supabase and Upstash connectivity, run a real batch, verify Redis state and
audit immutability, exercise Razorpay test-mode webhooks, and rehearse the
dashboard on the presentation machine.

## 3. The critical path — what actually blocks your demo, in order

```
Phase 2 (data)  →  Phase 3 (diagnose)  →  Phase 4 (gate)  →  Phase 5 (bandit)
                                                                     ↓
Phase 10 (dashboard)  ←  Phase 9 (API)  ←  Phase 8 (batch eval)  ←  Phase 7 (observe)  ←  Phase 6 (act)
                                                     ↓
                                          Phase 11 (chaos) — bolts onto 6+10
                                                     ↓
                                          Phase 12 (submission)
```

**The core code exists, but end-to-end confidence is currently limited by
unreachable Supabase and Upstash endpoints.** Restore those connections
before treating the dashboard numbers or live event workflow as release
evidence.

## 4. Recommended sequencing given limited remaining time

If you have a 4-person team and roughly the remaining days before
submission, this is the highest-leverage order — not necessarily matching
phase numbers exactly, because some phases can run in parallel:

**Immediate (today):**
1. Phase 2 — synthetic data generator. Nothing else can be tested without it.
2. Phase 4 — Gate. Build this in parallel with Phase 2; it has no
   dependency on real event data (its unit tests use constructed fixtures).

**Next 1-2 days:**
3. Phase 3 — Diagnose (needs Phase 2's data to test against realistically).
4. Phase 5 — Bandit (needs Phase 4's Gate contract finalized, per
   `PHASE_05_decide_DETAILED.md`'s dependency note).
5. Phase 6 — Act (can start in parallel with Phase 5 once Phase 4 is done).

**Following 1-2 days:**
6. Phase 7 — Observe (needs Phase 5 + 6 done).
7. Phase 8 — Batch Evaluation (needs the full pipeline; this is where your
   headline numbers get produced — budget real time to tune priors/buckets
   if the learning curve doesn't converge cleanly on the first attempt,
   per the tuning notes in `PHASE_05_decide_DETAILED.md` section 3.2).

**Final 2-3 days:**
8. Phase 9 — API (thin layer over everything above).
9. Phase 10 — Dashboard (the demo surface).
10. Phase 11 — Chaos testing (cheap now, given Phase 6's fault-injection
    seam was built early — budget ~1 day).
11. Phase 12 — Rehearsal and submission.

## 5. Risk register — what's most likely to go wrong, and the mitigation already documented

| Risk | Where it's addressed |
|---|---|
| Bandit doesn't visibly converge in a 200-event batch | `PHASE_05_decide_DETAILED.md` §3.2 — reduce context-bucket cardinality first, not batch size |
| Baseline-vs-bandit comparison looks unfair or gets challenged by a judge | `PHASE_08_batch_eval_DETAILED.md` §2.1 — same code, same data, one variable; the fairness test proves this |
| Live demo API call fails on stage | `DEMO_SCRIPT.md`'s fallback plan + `eval/results/` cached runs |
| A judge asks "isn't your taxonomy hardcoded?" | `WINNING_STRATEGY.md` §5 — direct, confident answer already prepared |
| Chaos test looks staged / not real | `PHASE_11_resilience_chaos_DETAILED.md` §2.1 — fault injection raises the *actual* exception type real failures raise, verified by a dedicated indistinguishability test |
| Documentation drifts from actual code as you build under time pressure | `CLAUDE.md`'s instruction to flag discrepancies immediately, and this doc's "what's actually real" section — update it honestly as you go, don't let it go stale |

## 6. How to use this document day to day

Update section 1 ("what's actually real") every time a phase's Definition
of Done is genuinely met — not when code is written, when its tests pass
against real infrastructure. Keep the distinction between "documented" and
"coded and verified" sharp; conflating them is exactly the kind of
documentation/reality drift `CLAUDE.md` warns against, and it's worse to
discover that drift during a judge's question than during your own
rehearsal.
