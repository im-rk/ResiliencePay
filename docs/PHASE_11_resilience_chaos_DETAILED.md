# Phase 11 — Resilience & Chaos Testing — Full Detailed Spec

**Depends on:** Phase 6 (fault-injection hooks stubbed there), Phase 10 (dashboard must reflect this live)
**Unblocks:** Phase 12 (this becomes a rehearsed, on-demand demo beat)
**Owner:** whoever built Phase 6 (deepest context on the Act layer)
**Estimated time:** ~1 day

---

## 1. Why this phase exists and why it matters more than it looks

The Razorpay buildathon's own framing — "what broke at 2 AM, and how you
got out" — is not incidental language. It is a direct statement of what
they are screening for: not a spotless happy-path demo, but evidence that
you understand failure is normal in real systems and have engineered for
it deliberately. Every other Track 03 team will show their agent recovering
a payment successfully. Very few will show their agent's compliance and
audit guarantees surviving an actively-injected Razorpay outage, live, on
command. That gap is your highest-leverage remaining opportunity, and it is
cheap specifically *because* Phases 4-6 were built with clean interface
boundaries — this phase is where that earlier discipline gets cashed in.

There's a subtlety worth being explicit about: chaos testing here is not
about proving your system never fails. It's about proving that **when it
fails, it fails into a well-defined, auditable, non-silent state** — a
`failed` action row still exists, a customer who was mid-retry-sequence is
not double-charged, and nothing vanishes from the audit trail. The demo
value isn't "look, nothing broke" — it's "look, something broke, and here
is exactly what happened and why nothing bad resulted."

---

## 2. Conceptual model — read this before touching code

### 2.1 Why fault injection must be indistinguishable from a real failure to the code under test

If your fault-injection mechanism raises a custom `SimulatedFault`
exception that your retry/error-handling code has to specifically check
for, you haven't tested your resilience — you've tested a special code path
that only exists for testing. The correct design (already established in
`PHASE_06_act_DETAILED.md` §3.3) is for `SimulatedFault` to be caught by
the **exact same** exception handling that catches a real Razorpay 5xx or a
real network timeout. If your retry logic's `except` clause needs to be
widened specifically to catch `SimulatedFault` in addition to
`RazorpayTransientError`/`ConnectionError`/`TimeoutError`, that widening
itself is suspicious — it likely means your test isn't exercising the real
failure path, it's exercising a parallel one that happens to look similar.
Verify this explicitly (see the smoke test in §5.1) rather than assuming it.

### 2.2 Why "zero silently-dropped events" is the single metric that matters most here

A chaos test could report "95% success rate under 15% injected failures"
and still be hiding a catastrophic bug — for example, if the missing 5%
aren't failed-and-logged, they're just *gone*: no action row, no audit
entry, no trace. In a revenue-recovery system, a silently-dropped event is
strictly worse than a correctly-logged failure, because it means money that
could have been recovered is now untracked and unrecoverable *and nobody
knows it happened*. This is why the chaos suite's core assertion is not
"did most things succeed" but **"did every single event reach a terminal,
logged state"** — success, failure, or blocked, but never nothing.

### 2.3 Why the live-trigger admin endpoint needs the protection from `PRODUCTION_ENGINEERING_STANDARDS.md` §3.4, not more, not less

The fault-injection toggle is a genuinely dangerous endpoint if left
unprotected — it can degrade your system's real behavior, including during
someone else's demo slot if you're running a shared environment. But
building full authentication for a hackathon admin toggle is
disproportionate effort for a control that only needs to stop an
accidental or malicious unauthenticated call. A shared-secret header,
explicitly labeled as "the minimal viable control for a demo environment,"
is the correctly-scoped choice — and saying so explicitly, unprompted, if a
judge asks about it, reads as calibrated engineering judgment rather than
an oversight.

---

## 3. Detailed component design

### 3.1 Completing `services/act/fault_injection.py` (stubbed in Phase 6)

```python
import random
from functools import wraps

from packages.config.settings import settings

class SimulatedFault(Exception):
    """Deliberately a plain Exception, not a custom hierarchy — the whole
    point is that this must be catchable by whatever generic exception
    handling already exists for real transient failures (see section 2.1).
    Do NOT give this a distinct base class that retry logic would need to
    special-case."""
    def __init__(self, fault_type: str):
        self.fault_type = fault_type
        super().__init__(f"simulated fault: {fault_type}")


FAULT_TYPES = ["timeout", "server_error", "malformed_response"]

# Map each simulated fault type to the REAL exception type it should
# masquerade as, so it's caught by the exact same except clause a genuine
# failure would hit — not a fault-injection-only branch.
FAULT_TYPE_TO_REAL_EXCEPTION = {
    "timeout": TimeoutError,
    "server_error": ConnectionError,  # stands in for RazorpayTransientError's underlying cause
    "malformed_response": ValueError,
}


def with_fault_injection(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if getattr(settings, "fault_injection_enabled", False):
            if random.random() < settings.fault_injection_rate:
                fault_type = random.choice(FAULT_TYPES)
                real_exception_type = FAULT_TYPE_TO_REAL_EXCEPTION[fault_type]
                raise real_exception_type(f"[SIMULATED FAULT: {fault_type}] injected for chaos testing")
        return fn(*args, **kwargs)
    return wrapper
```

**Design refinement from the Phase 6 stub:** rather than raising a custom
`SimulatedFault` that retry logic must specifically catch, this version
raises the **actual exception type** (`TimeoutError`, `ConnectionError`,
`ValueError`) that a real failure of that kind would raise, with a
recognizable message prefix for logging/debugging purposes only. This is
the concrete fix for the risk described in section 2.1 — verify your
existing `RazorpayClient._call_with_retry`'s `except` clauses already
handle these exact exception types (they should, from Phase 6) without any
modification.

### 3.2 `services/act/tests/test_chaos.py`

```python
import pytest

from eval.run_batch import run_batch
from services.decide.baseline_policy import BaselinePolicy
from packages.config.settings import settings


@pytest.fixture
def fault_injection_enabled(monkeypatch):
    monkeypatch.setattr(settings, "fault_injection_enabled", True)
    monkeypatch.setattr(settings, "fault_injection_rate", 0.15)
    yield
    monkeypatch.setattr(settings, "fault_injection_enabled", False)


def test_pipeline_survives_15pct_fault_rate(db_session, fault_injection_enabled):
    run = run_batch(db_session, dataset_seed=7, n=200, policy_name="baseline", policy=BaselinePolicy())

    all_audit_rows = get_all_audit_rows_for_run(db_session, run.run_id)
    assert len(all_audit_rows) == 200, (
        f"expected exactly one audit row per event (zero silently dropped), got {len(all_audit_rows)}"
    )

    terminal_states = {"recovered", "not_recovered", "blocked_by_policy", "failed", "failed_permanently"}
    for row in all_audit_rows:
        assert row.outcome_result in terminal_states, (
            f"audit row {row.audit_id} has non-terminal outcome_result={row.outcome_result!r} — "
            f"every event must reach a terminal, logged state even under injected failure"
        )

    # Verify audit-trail completeness at the decision/action level too, not
    # just at the top-level audit_log — see section 2.2's "zero gaps" definition.
    decisions_missing_actions = find_gate_passed_decisions_without_action_row(db_session, run.run_id)
    assert len(decisions_missing_actions) == 0, (
        f"found {len(decisions_missing_actions)} gate-passed decisions with no corresponding "
        f"action row — this is exactly the audit-trail gap chaos testing exists to catch"
    )


def test_simulated_fault_indistinguishable_from_real_failure(fault_injection_enabled, mocked_razorpay_sdk):
    """The smoke test described in section 2.1 — proves fault injection is
    caught by the SAME except clause as a genuine failure, not a
    fault-injection-only code path."""
    from services.act.razorpay_client import RazorpayClient, RazorpayTransientError

    client = RazorpayClient(key_id="test", key_secret="test", max_retries=1)
    with pytest.raises(RazorpayTransientError):
        client.create_retry_payment_link(fake_episode(), idempotency_key="test-key")
    # If this raises RazorpayTransientError (the same exception a real 5xx
    # produces after retries are exhausted) rather than a raw
    # SimulatedFault/ConnectionError leaking out, the fault is correctly
    # indistinguishable from a real one to the calling code.
```

### 3.3 Audit-trail completeness helper

```python
# services/audit/query_service.py addition
def find_gate_passed_decisions_without_action_row(db_session, run_id) -> list:
    """The concrete query behind 'zero audit-trail gaps' — every decision
    whose gate_check passed should have exactly one corresponding action
    row, even if that action's status ended up 'failed'. A gate-passed
    decision with NO action row at all is the specific gap this chaos
    testing phase exists to catch and prevent."""
    return db_session.execute(
        select(Decision)
        .join(GateCheck, GateCheck.decision_id == Decision.decision_id)
        .outerjoin(Action, Action.decision_id == Decision.decision_id)
        .where(GateCheck.result == "passed", Action.action_id.is_(None))
    ).scalars().all()
```

### 3.4 Live-trigger admin endpoint

```python
# apps/api/src/routers/admin.py
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from packages.config.settings import settings

router = APIRouter()


def require_admin_secret(x_admin_secret: str = Header(...)):
    """Minimal viable control for a demo environment — see
    PRODUCTION_ENGINEERING_STANDARDS.md section 3.4. Explicitly NOT
    intended as a production auth mechanism; state this plainly if asked,
    rather than overstating what a shared secret header provides."""
    if x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="forbidden")


class FaultInjectionToggleRequest(BaseModel):
    enabled: bool
    rate: float = 0.15


@router.post("/admin/fault-injection", dependencies=[Depends(require_admin_secret)])
def toggle_fault_injection(body: FaultInjectionToggleRequest):
    settings.fault_injection_enabled = body.enabled
    settings.fault_injection_rate = body.rate
    return {"fault_injection_enabled": settings.fault_injection_enabled, "rate": settings.fault_injection_rate}
```

**Mutating `settings` at runtime like this is a deliberate, scoped
exception** to the "config is validated once at boot and immutable"
principle elsewhere in the project — acceptable specifically because this
is a demo-only control surface with no effect on data integrity (the Gate
and audit logic remain fully correct regardless of this flag's value; it
only affects whether synthetic faults are injected upstream of them).
Comment this exception clearly so it doesn't get mistaken for a general
pattern to reuse elsewhere.

---

## 4. Full edge-case matrix (expanded)

| # | Injected fault | Expected system behavior | How to test |
|---|---|---|---|
| 1 | Razorpay call times out | Retried per Phase 6's backoff policy, eventually `RazorpayTransientError`, action row exists with `status="failed"` | `test_pipeline_survives_15pct_fault_rate` |
| 2 | Razorpay returns malformed response | Caught by existing error handling, logged, does not crash the pipeline | Same suite, `malformed_response` fault type |
| 3 | LLM nudge generation fails under injected fault | Falls back to template (Phase 6's guaranteed-fallback contract), still `simulated=true`, pipeline continues | Extend the chaos suite to also enable fault injection on the LLM client boundary |
| 4 | Redis briefly unavailable during a bandit update | Raises loudly per Phase 5's design — verify this is what ACTUALLY happens under chaos, not just documented intent | Chaos variant specifically targeting the Redis client, asserting the pipeline halts for that event rather than silently using a random fallback |
| 5 | Webhook never arrives due to injected network fault | Phase 7's reconciliation polling eventually catches it — verify end-to-end under chaos conditions, not just in isolation | Integration-level chaos test combining Phase 7's reconciliation task with fault injection enabled |
| 6 | A gate-passed decision's downstream action call fails entirely (no partial state) | An `action` row still exists with `status="failed"` — never a decision with zero corresponding action rows | `find_gate_passed_decisions_without_action_row` assertion in `test_pipeline_survives_15pct_fault_rate` |
| 7 | Admin fault-injection endpoint called without the correct secret | `403 Forbidden`, fault injection state unchanged | Unit test posting without the header, asserting both the status code and that `settings.fault_injection_enabled` didn't change |
| 8 | Admin toggle enables fault injection, then a batch run completes, then toggle disables it | State correctly reflects `enabled=False` for any subsequent run — no stuck-on chaos mode after the demo beat | Integration test: toggle on, run batch, toggle off, run batch again, assert the second run shows zero injected-fault-caused failures |

---

## 5. Test plan — with actual test code to implement

### 5.1 Already shown in §3.2: `test_pipeline_survives_15pct_fault_rate` and `test_simulated_fault_indistinguishable_from_real_failure` — implement both exactly as specified there.

### 5.2 `apps/api/tests/test_admin_fault_injection.py`

```python
def test_toggle_without_secret_rejected(client):
    response = client.post("/v1/admin/fault-injection", json={"enabled": True, "rate": 0.3})
    assert response.status_code == 403  # FastAPI's default for a missing required header is 422, not 403 —
    # verify your require_admin_secret dependency actually surfaces 403 as intended, adjust if FastAPI's
    # header-validation short-circuits before your dependency runs; document whichever behavior is correct.

def test_toggle_with_wrong_secret_rejected(client):
    response = client.post("/v1/admin/fault-injection",
                            json={"enabled": True, "rate": 0.3},
                            headers={"X-Admin-Secret": "wrong-secret"})
    assert response.status_code == 403

def test_toggle_with_correct_secret_succeeds(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_secret", "correct-secret")
    response = client.post("/v1/admin/fault-injection",
                            json={"enabled": True, "rate": 0.3},
                            headers={"X-Admin-Secret": "correct-secret"})
    assert response.status_code == 200
    assert response.json()["fault_injection_enabled"] is True
```

### 5.3 `services/act/tests/test_chaos_llm_boundary.py`

```python
def test_nudge_generation_survives_injected_llm_failure(fault_injection_enabled):
    generator = NudgeGenerator(llm_client=real_but_fault_wrapped_llm_client)
    result = generator.generate(make_decision("send_nudge_english"), language="send_nudge_english")
    # Even under injected failure, generate() must never raise — this
    # re-verifies Phase 6's guaranteed-fallback contract specifically under
    # chaos conditions, not just under a directly-mocked single failure.
    assert result.method in ("llm_generated", "template_fallback")
```

### 5.4 `apps/worker/tests/test_reconciliation_under_chaos.py`

```python
def test_reconciliation_eventually_catches_missed_webhook_under_fault_injection(fault_injection_enabled):
    action = create_test_action(razorpay_ref_id="pay_chaos_test", status="executed",
                                 executed_at=now() - timedelta(hours=8))
    # Simulate several reconciliation attempts, since fault injection may
    # cause the FIRST poll attempt to fail — the point is that eventual
    # consistency holds across retries, not that every single attempt succeeds.
    for _ in range(5):
        reconcile_payment_status()
        outcome = get_outcome_for_action(action.id)
        if outcome is not None:
            break
    assert outcome is not None, "reconciliation should eventually succeed across retries even under 15% fault injection"
```

---

## 6. Observability — what to log and show live

Every injected fault should log distinctly from a "real" failure it's
masquerading as, but ONLY at the fault-injection layer itself (e.g.,
`logger.debug("fault_injected", fault_type=..., real_exception_type=...)`)
— never in the business logic that catches it, which must treat it
identically to a genuine failure per section 2.1. This gives you, as the
presenter, a way to privately confirm "yes, that failure I just showed the
judges was really injected by me, not a coincidental real bug" without the
audience needing to see that distinction.

---

## 7. Definition of Done (full checklist)

- [ ] Chaos suite passes at 15% injected failure rate with zero silently-dropped events — verified by asserting exactly one audit row per input event.
- [ ] `find_gate_passed_decisions_without_action_row` returns zero results after a chaos run.
- [ ] `test_simulated_fault_indistinguishable_from_real_failure` passes, proving fault injection is caught by the same exception handling as genuine failures, not a special-cased path.
- [ ] LLM nudge generation survives injected failure without ever raising, verified specifically under fault injection (not just a single direct mock).
- [ ] Reconciliation eventually catches a missed webhook even under injected fault, verified across multiple attempts.
- [ ] Admin fault-injection endpoint rejects requests without the correct secret, and correctly toggles state when given the correct one.
- [ ] The dashboard (Phase 10) visibly and clearly renders a `failed`/`blocked_by_policy` outcome distinctly from a `recovered` one, confirmed by triggering chaos mode against a real running dashboard, not just checking the API response.
- [ ] The live-trigger flow (toggle on → run/observe a failure live → toggle off) has been rehearsed at least twice and is fast enough to be a demo beat, not a 30-second dead-air wait.

---

## 8. Prompts for your coding agent

Use these as focused, sequential prompts. `CLAUDE.md`'s repo-wide standards
apply automatically; these assume that context is already loaded (see
`docs/AGENT_KICKOFF_PROMPT.md`).

### Prompt 1 — Finalize fault injection to raise real exception types
```
Update services/act/fault_injection.py per docs/phases/PHASE_11_resilience_chaos_DETAILED.md
section 3.1: change the fault-injection decorator so it raises the ACTUAL
exception type a real failure would raise (TimeoutError, ConnectionError,
ValueError) rather than a custom SimulatedFault class, using the
FAULT_TYPE_TO_REAL_EXCEPTION mapping shown in the doc. Then write
services/act/tests/test_simulated_fault_indistinguishable_from_real_failure
exactly per section 3.2/5.1 of the doc — this test must prove the injected
fault is caught by RazorpayClient's EXISTING retry/error-handling logic
from Phase 6 without any modification to that logic. If you find yourself
needing to widen an except clause in razorpay_client.py to make this test
pass, stop and tell me — that would indicate the fault injection isn't
actually indistinguishable from a real failure, which defeats the purpose.
```

### Prompt 2 — Chaos test suite with the zero-gaps assertion
```
Implement services/act/tests/test_chaos.py per docs/phases/PHASE_11_resilience_chaos_DETAILED.md
section 3.2: test_pipeline_survives_15pct_fault_rate, running a full 200-event
batch through eval/run_batch.py (from Phase 8) with fault injection enabled
at a 15% rate. The core assertion is NOT a success-rate threshold — it's
that every single input event has exactly one corresponding audit_log row
in a terminal outcome_result state, with zero silently-dropped events.
Implement find_gate_passed_decisions_without_action_row in
services/audit/query_service.py per section 3.3 of the doc, and assert it
returns zero results after the chaos run — this is the concrete
'zero audit-trail gaps' check.
```

### Prompt 3 — LLM boundary and reconciliation chaos tests
```
Implement services/act/tests/test_chaos_llm_boundary.py and
apps/worker/tests/test_reconciliation_under_chaos.py per sections 5.3 and
5.4 of docs/phases/PHASE_11_resilience_chaos_DETAILED.md. For the
reconciliation test, the assertion is about EVENTUAL success across
multiple attempts under fault injection, not that every single attempt
succeeds — retry the reconciliation call a bounded number of times (5, per
the doc) and assert success within that bound, not on the first try.
```

### Prompt 4 — Admin fault-injection toggle endpoint
```
Implement apps/api/src/routers/admin.py per docs/phases/PHASE_11_resilience_chaos_DETAILED.md
section 3.4: the require_admin_secret dependency and the
POST /v1/admin/fault-injection endpoint. Add admin_secret to
packages/config/settings.py as a required field. Write
apps/api/tests/test_admin_fault_injection.py per section 5.2 of the doc,
covering: no secret provided, wrong secret provided, and correct secret
provided. Note the doc's caveat about FastAPI's header validation
potentially returning 422 rather than reaching your 403 logic if the
header is entirely missing vs. present-but-wrong — verify which actually
happens in this codebase and adjust the test/implementation to be
consistent and documented, don't just assume 403 in all cases.
```

### Prompt 5 — Dashboard chaos visibility and full live-trigger rehearsal
```
Confirm (or wire, if missing) that apps/dashboard's AuditTrailTable and
ExceptionList panels (from Phase 10) render a status="failed" or
blocked_by_policy outcome visibly and distinctly from a "recovered" one —
check the actual rendered styling, not just that the data field exists in
the DTO. Then actually run the live-trigger flow end to end: call
POST /v1/admin/fault-injection with enabled=true, trigger a live event
through the pipeline, confirm the dashboard shows the failure clearly, then
call the endpoint again with enabled=false. Time this full sequence and
report back how long it took — if it's much over 30-45 seconds, we need to
simplify the flow before it becomes a demo beat. Finally work through the
Definition of Done checklist in section 7 of
docs/phases/PHASE_11_resilience_chaos_DETAILED.md and report back which
items pass, with actual test output for every relevant test file.
```
