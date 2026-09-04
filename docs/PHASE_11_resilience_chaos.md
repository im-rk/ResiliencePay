# Phase 11 — Resilience & Chaos Testing (your novelty differentiator)

**Depends on:** Phase 6 (fault-injection hooks already stubbed there), Phase 10 (dashboard must reflect this live)
**Unblocks:** Phase 12 (this becomes a scripted, on-demand demo beat)
**Owner:** whoever built Phase 6 (has the deepest context on the Act layer)
**Estimated time:** ~1 day

## Objective
Prove the system survives and degrades gracefully under real-world failure
conditions — live, on command — not just in a scripted happy path. This is
the single highest-leverage addition given what you've already built: it's
cheap because Phases 5 and 6 used Protocol-based, dependency-injected
interfaces specifically to make this possible.

## Why this phase wins on novelty
Every team in Track 03 will show a happy-path recovery flow. Almost none
will demonstrate their system surviving and gracefully degrading under
injected real-world failure, live, on demand. This is your payoff for the
architectural discipline in Phases 4-6.

## Scope
**In scope:** fault-injection wiring (already stubbed in Phase 6), chaos
test suite, dashboard visibility into fault-injected states, a rehearsed
live-trigger demo path.
**Out of scope:** any new business logic — this phase tests what already exists.

## Deliverables mapped to monorepo paths

| Path | What goes here |
|---|---|
| `services/act/fault_injection.py` | Completed here (stub existed from Phase 6) — configurable failure rate, failure type |
| `services/act/tests/test_chaos.py` | Chaos suite: batch run with injected failures |
| `apps/api/src/routers/admin.py` | (Optional) `POST /v1/admin/fault-injection` toggle, for live-demo triggering |
| `.github/workflows/chaos-nightly.yml` | (Optional) scheduled chaos suite run |

## Detailed task breakdown

1. **Finish the fault-injection wrapper**
   ```python
   FAULT_INJECTION_ENABLED = settings.fault_injection_enabled  # env-flag gated, off by default

   def with_fault_injection(fn):
       @wraps(fn)
       def wrapper(*args, **kwargs):
           if FAULT_INJECTION_ENABLED and random.random() < settings.fault_injection_rate:
               fault_type = random.choice(["timeout", "5xx", "malformed_response"])
               raise SimulatedFault(fault_type)
           return fn(*args, **kwargs)
       return wrapper
   ```
   Apply this decorator to `razorpay_client`'s mutating calls and to the
   LLM client calls — the exact places Phase 6 already isolated behind thin
   wrappers, which is precisely why this is cheap now.

2. **Chaos test suite**
   ```python
   def test_pipeline_survives_15pct_fault_rate():
       settings.fault_injection_enabled = True
       settings.fault_injection_rate = 0.15
       events = generate_batch(seed=42, n=200)
       results = run_batch_with_injected_faults(events)

       # No event silently dropped — every event ends in a terminal, logged state
       for r in results:
           assert r.final_status in {"recovered", "not_recovered", "blocked_by_policy", "failed_permanently"}

       # Audit trail has zero gaps
       for r in results:
           assert audit_log_has_complete_chain(r.event_id)

       # Bandit state remains internally consistent (no partial/corrupt updates)
       assert bandit_state_is_consistent()
   ```

3. **Audit-trail completeness check** — every decision that passed the gate
   must have a corresponding `actions` row, even if the downstream Razorpay
   call failed (status=`failed`, not a missing row) — this is what "zero
   gaps" means concretely, and it's the thing to specifically verify, since
   it's the failure mode most likely to silently break under chaos testing.

4. **Dashboard visibility** — ensure a `failed`/`blocked_by_policy` outcome
   renders clearly and distinctly in `AuditTrailTable` and
   `ExceptionList` (Phase 10) — the chaos beat is only demo-worthy if the
   audience can *see* the graceful handling, not just read your test output.

5. **(Optional) Live-trigger admin endpoint** — a
   `POST /v1/admin/fault-injection {enabled: true, rate: 0.3}` toggle you
   can hit live during the demo, so a judge's "what if Razorpay is down
   right now" question gets answered by actually turning on chaos mode in
   front of them, not a slide.

## Edge-case matrix (what the chaos suite specifically verifies)

| Injected fault | Expected system behavior |
|---|---|
| Razorpay call times out | Retried per Phase 6's backoff policy, eventually marked `failed`, action row still exists with `status="failed"` |
| Razorpay returns malformed response | Caught, logged as an integrity warning, does not crash the pipeline |
| LLM nudge generation fails | Falls back to template message (Phase 6), still `simulated=true`, pipeline continues |
| Redis briefly unavailable during a bandit update | Raises loudly (per Phase 5's design) rather than corrupting state — verify this is what actually happens under chaos, not just what's documented |
| Webhook never arrives due to injected network fault | Reconciliation polling (Phase 7) eventually catches it — verify end-to-end, not just that each piece works in isolation |

## Design decisions & trade-offs

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| Fault injection location | Ad hoc `if random.random() < X: raise` scattered in code vs. centralized decorator | Centralized decorator applied at the client boundary | Keeps chaos logic in one place, easy to enable/disable, doesn't pollute business logic with test-only branches |
| When to build this | Bolted on at the very end vs. hooks stubbed early (Phase 6), completed here | Hooks stubbed in Phase 6, completed in Phase 11 | Retrofitting fault injection into tightly-coupled code is expensive; stubbing the seam early made this phase cheap |

## Test plan
- **Chaos suite:** 15% injected failure rate across a 200-event batch, assert zero silently-dropped events, zero audit-trail gaps, consistent bandit state.
- **Live-trigger rehearsal:** actually run the live-trigger flow at least twice before demo day, timed, to make sure it's fast enough to be a demo beat and not a 30-second dead-air wait.

## Definition of Done
- [ ] Chaos suite passes at 15% injected failure rate with zero silently-dropped events.
- [ ] Audit-trail completeness verified under chaos (no gaps).
- [ ] A judge can ask "what happens if Razorpay is down right now" and you can trigger it live and show graceful degradation, not just describe it.

## Handoff to Phase 12
Phase 12 assumes: the chaos-injection beat is rehearsed and timed as part
of `DEMO_SCRIPT.md`, and that the dashboard visibly and clearly shows the
failure being handled, not just the test suite passing silently in CI.
