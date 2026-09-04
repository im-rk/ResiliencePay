# Phase 6 — Act (Execution Layer) — Full Detailed Spec

**Depends on:** Phase 4 (only ever called with a gate-passed decision), Phase 5 (chosen arm)
**Unblocks:** Phase 7 (Observe watches for outcomes of these actions), Phase 11 (chaos testing hooks directly into this layer)
**Owner:** backend/integration-strongest team member
**Estimated time:** ~1–1.5 days (can run in parallel with Phase 5)

---

## 1. Why this phase exists and why it matters more than it looks

This is the phase where your system stops being a decision engine and
starts being a payments system — the moment abstract "arm chosen" becomes a
real Razorpay API call or a real (simulated) message a customer would see.
That transition point is exactly where production payments engineering
gets serious, and it's where most hackathon teams get sloppy, because it's
tempting to treat "call the API" as the easy, unglamorous part after the
"real" work (the bandit) is done.

It is not the easy part. Three properties have to hold simultaneously, and
each is a genuine payments-engineering concern, not hackathon theater:

1. **Idempotency** — a network blip causing a retry must never create a
   second real-money resource. This is the single most common real-world
   payments bug class, and it's cheap to prevent correctly from the start.
2. **Correct timing modeling** — `retry_long_delay` means "in 2-3 days,"
   and that has to be a real scheduled future event, not a blocking wait or
   a lie in a status field.
3. **An unambiguous simulated/real boundary** — the moment you conflate
   "we sent a real payment retry" with "we generated a plausible-sounding
   message," your entire audit trail's credibility collapses. This has to
   be structurally impossible to get wrong, not just documented as a
   convention.

Additionally, this phase is where Phase 11's chaos testing will later hook
in — so every external call built here should be wrapped behind a thin,
swappable client from day one. Getting that seam right now is what makes
Phase 11 cost one day instead of three.

---

## 2. Conceptual model — read this before touching code

### 2.1 The arm taxonomy, and why each type needs different execution logic

Not all 8 arms are the same *kind* of action, and conflating them into one
code path is the most common mistake in this phase. There are really four
distinct execution patterns hiding behind "8 arms":

| Category | Arms | What actually happens |
|---|---|---|
| **Real, immediate** | `retry_immediate` | A real Razorpay API call, executed synchronously, right now |
| **Real, delayed** | `retry_short_delay`, `retry_long_delay` | A real Razorpay API call, but scheduled for a future point in time — this requires a task queue, not a blocking wait |
| **Simulated, immediate** | `send_card_update_link`, `send_nudge_hinglish`, `send_nudge_english`, `escalate_human` | No real external side effect happens (or a genuinely inert one, like flagging a row) — an LLM-generated message is produced and logged as if sent |
| **No-op** | `stop` | Nothing happens at all, but it must still be logged — "the agent decided to stop" is itself an auditable fact |

Your `execute_action()` routing function exists specifically to dispatch
correctly across these four categories. Get the taxonomy right before
writing the dispatch logic — trying to special-case arms one at a time as
you discover their differences leads to duplicated, drifting logic.

### 2.2 Why idempotency keys, specifically, and not "just don't retry"

You might think: "why not just make sure Celery/retry logic never calls
this function twice?" Because you cannot guarantee that in a distributed
system. A Celery worker can crash after sending the Razorpay request but
before recording success. A network partition can cause your retry logic
to legitimately not know whether the first attempt succeeded. The correct
engineering response to "I don't know if my last request went through" is
never "assume it didn't and try again" — it's "make trying again safe
regardless of whether it went through," which is exactly what an
idempotency key does: Razorpay (like Stripe, and most modern payment APIs)
deduplicates requests bearing the same idempotency key, returning the
original result instead of creating a second resource.

### 2.3 Why the delayed-arm gate re-check matters more than it looks

Here's a subtle but important scenario: at 9am, the bandit chooses
`retry_long_delay` for a failed subscription charge, scheduling a retry for
in 3 days. At 2pm that same day, the customer explicitly texts back "stop
contacting me," which correctly gets recorded as an opt-out. If your
Celery task, when it fires 3 days later, just blindly executes the
originally-scheduled action without re-checking the gate, you will retry a
payment against a customer who explicitly opted out — a real compliance
violation that happened purely because of a stale decision. The gate must
be evaluated fresh, at execution time, not just inherited from scheduling
time. This is a one-line fix in code and a serious bug if missed, which is
exactly the kind of detail that separates a careful engineer from a rushed one.

---

## 3. Detailed component design

### 3.1 `services/act/razorpay_client.py`

```python
import time
import logging
from dataclasses import dataclass
import razorpay

logger = logging.getLogger(__name__)

class RazorpayPermanentError(Exception):
    """Raised when a Razorpay call fails in a way that retrying will not fix
    (e.g., 4xx validation errors). Distinct from transient errors so callers
    know not to retry."""

class RazorpayTransientError(Exception):
    """Raised after retries are exhausted on a transient (5xx/timeout) failure."""


@dataclass(frozen=True)
class PaymentLinkResult:
    id: str
    short_url: str
    status: str


class RazorpayClient:
    """Idempotency-key-aware, retrying wrapper over the Razorpay SDK.
    NOTHING outside this file should import razorpay directly — this is the
    single seam Phase 11's fault injection wraps, and the single place
    retry/timeout policy lives."""

    def __init__(self, key_id: str, key_secret: str, max_retries: int = 3,
                 base_backoff_seconds: float = 0.5):
        self._client = razorpay.Client(auth=(key_id, key_secret))
        self.max_retries = max_retries
        self.base_backoff_seconds = base_backoff_seconds

    def create_retry_payment_link(self, episode, idempotency_key: str) -> PaymentLinkResult:
        payload = {
            "amount": episode.original_amount,
            "currency": episode.currency,
            "description": f"Payment retry for episode {episode.episode_id}",
            "notes": {"idempotency_key": idempotency_key, "episode_id": str(episode.episode_id)},
        }
        return self._call_with_retry(
            lambda: self._client.payment_link.create(payload),
            result_mapper=lambda r: PaymentLinkResult(id=r["id"], short_url=r["short_url"], status=r["status"]),
            idempotency_key=idempotency_key,
        )

    def get_payment_status(self, payment_id: str) -> dict:
        return self._call_with_retry(
            lambda: self._client.payment.fetch(payment_id),
            result_mapper=lambda r: r,
            idempotency_key=f"fetch:{payment_id}",
        )

    def _call_with_retry(self, fn, result_mapper, idempotency_key: str):
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            try:
                raw_result = fn()
                return result_mapper(raw_result)
            except razorpay.errors.BadRequestError as e:
                # 4xx-class — retrying will not help, fail fast and loud
                raise RazorpayPermanentError(str(e)) from e
            except (razorpay.errors.ServerError, ConnectionError, TimeoutError) as e:
                last_exc = e
                backoff = self.base_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "razorpay_transient_error", extra={
                        "idempotency_key": idempotency_key, "attempt": attempt, "backoff_seconds": backoff,
                    })
                time.sleep(backoff)
        raise RazorpayTransientError(
            f"exhausted {self.max_retries} retries for idempotency_key={idempotency_key}"
        ) from last_exc
```

**Note on idempotency at the Razorpay API level:** confirm during Phase 6
implementation exactly which Razorpay endpoints natively support
idempotency keys (check current Razorpay API docs — this may vary by
endpoint and by API version). Where native idempotency isn't supported,
implement an **application-level idempotency guard**: before calling the
API, check whether an `actions` row already exists for this
`idempotency_key`; if so, return the existing result instead of calling the
API again. This is a legitimate and common fallback pattern — document
which mechanism (native or application-level) is actually in effect for
each call.

### 3.2 `services/act/nudge_generator.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class NudgeResult:
    text: str
    method: str  # "llm_generated" | "template_fallback"

TEMPLATE_FALLBACKS = {
    "send_nudge_hinglish": "Namaste! Aapka payment complete nahi hua. Please retry karein: {link}",
    "send_nudge_english": "Hi! Your recent payment didn't go through. Please retry here: {link}",
    "send_card_update_link": "Your card on file needs updating. Update it here: {link}",
}

class NudgeGenerator:
    def __init__(self, llm_client, timeout_seconds: float = 5.0):
        self.llm_client = llm_client
        self.timeout_seconds = timeout_seconds

    def generate(self, decision, language: str) -> NudgeResult:
        prompt = self._build_prompt(decision, language)
        try:
            text = self.llm_client.complete(prompt, timeout=self.timeout_seconds)
            return NudgeResult(text=text, method="llm_generated")
        except Exception as e:  # noqa: BLE001 — deliberately broad: ANY LLM failure must fall back, never propagate
            logger.warning("nudge_generation_failed_falling_back", extra={
                "arm": language, "error": str(e),
            })
            template = TEMPLATE_FALLBACKS.get(language, TEMPLATE_FALLBACKS["send_nudge_english"])
            return NudgeResult(text=template.format(link="[payment_link]"), method="template_fallback")

    def _build_prompt(self, decision, language: str) -> str:
        tone = "warm, casual Hinglish" if language == "send_nudge_hinglish" else "polite, professional English"
        return (
            f"Write a short (under 40 words) payment reminder message in {tone}. "
            f"The customer's payment for episode {decision.episode.episode_id} failed. "
            f"Do not be pushy. Include a placeholder [payment_link] for the retry link."
        )
```

**Important:** the broad `except Exception` here is a deliberate,
documented exception to the general rule of catching specific exceptions —
this function's entire contract is "never raise, always return a
NudgeResult," because a customer-facing message generator failing must
never take down the pipeline. Keep the comment explaining this; a linter or
a future contributor might otherwise "fix" this into a narrower except
clause that reintroduces a failure path this design specifically closes off.

### 3.3 `services/act/fault_injection.py`

```python
import random
from functools import wraps
from packages.config.settings import settings

class SimulatedFault(Exception):
    def __init__(self, fault_type: str):
        self.fault_type = fault_type
        super().__init__(f"simulated fault: {fault_type}")

FAULT_TYPES = ["timeout", "server_error", "malformed_response"]

def with_fault_injection(fn):
    """Decorator applied to external-call boundaries (Razorpay client
    methods, LLM client calls). Off by default — gated by
    settings.fault_injection_enabled, flipped on only for Phase 11's chaos
    suite and the live-demo admin toggle. Built here, in Phase 6, because
    retrofitting this into already-tightly-coupled client code later is
    expensive; adding the seam now, while writing these clients anyway, is
    nearly free."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if getattr(settings, "fault_injection_enabled", False):
            if random.random() < settings.fault_injection_rate:
                fault_type = random.choice(FAULT_TYPES)
                raise SimulatedFault(fault_type)
        return fn(*args, **kwargs)
    return wrapper
```

Apply this decorator directly on `RazorpayClient._call_with_retry`'s inner
`fn` invocation point and on `NudgeGenerator.generate`'s LLM call — not on
the whole class — so fault injection simulates realistic single-call
failures rather than making an entire method disappear.

### 3.4 `services/act/service.py` — full routing logic

```python
from datetime import timedelta

REAL_MONEY_ARMS = {"retry_immediate"}
DELAYED_ARMS = {"retry_short_delay", "retry_long_delay"}
NUDGE_ARMS = {"send_card_update_link", "send_nudge_hinglish", "send_nudge_english"}
NO_OP_ARMS = {"escalate_human", "stop"}  # escalate_human has no automated side effect — it flags for a human

ARM_DELAYS = {
    "retry_short_delay": timedelta(hours=4),
    "retry_long_delay": timedelta(days=3),
}

def execute_action(decision, gate_result, razorpay_client, nudge_generator, audit_log_service) -> "Action":
    assert gate_result.passed, "execute_action must never be called on a blocked decision"
    idempotency_key = f"action:{decision.decision_id}"

    if decision.chosen_arm in REAL_MONEY_ARMS:
        try:
            result = razorpay_client.create_retry_payment_link(decision.episode, idempotency_key)
            action = Action(decision_id=decision.decision_id, arm_name=decision.chosen_arm,
                             simulated=False, razorpay_ref_id=result.id, status="executed")
        except RazorpayPermanentError as e:
            action = Action(decision_id=decision.decision_id, arm_name=decision.chosen_arm,
                             simulated=False, status="failed")
            audit_log_service.write_error(decision, code="RAZORPAY_PERMANENT_ERROR", reason=str(e))
        except RazorpayTransientError as e:
            action = Action(decision_id=decision.decision_id, arm_name=decision.chosen_arm,
                             simulated=False, status="failed")
            audit_log_service.write_error(decision, code="RAZORPAY_RETRIES_EXHAUSTED", reason=str(e))

    elif decision.chosen_arm in DELAYED_ARMS:
        eta = now() + ARM_DELAYS[decision.chosen_arm]
        execute_delayed_action.apply_async(args=[str(decision.decision_id)], eta=eta)
        action = Action(decision_id=decision.decision_id, arm_name=decision.chosen_arm,
                         simulated=False, scheduled_for=eta, status="scheduled")

    elif decision.chosen_arm in NUDGE_ARMS:
        nudge = nudge_generator.generate(decision, language=decision.chosen_arm)
        action = Action(decision_id=decision.decision_id, arm_name=decision.chosen_arm,
                         simulated=True, message_text=nudge.text, status="executed")
        if nudge.method == "template_fallback":
            audit_log_service.write_note(decision, note="nudge_template_fallback_used")

    else:  # NO_OP_ARMS: 'escalate_human', 'stop'
        action = Action(decision_id=decision.decision_id, arm_name=decision.chosen_arm,
                         simulated=True, status="executed")

    db.save(action)
    return action
```

### 3.5 `apps/worker/src/tasks/execute_delayed_action.py`

```python
@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def execute_delayed_action(self, decision_id: str):
    decision = load_decision(decision_id)
    if decision is None:
        logger.error("delayed_action_decision_missing", extra={"decision_id": decision_id})
        return  # nothing to do — do not retry a task for a decision that no longer exists

    # Gate re-check at EXECUTION time, not scheduling time — see section 2.3.
    fresh_context = build_context(decision.event, decision.chosen_arm, now=now())
    gate_result = evaluate_gate(fresh_context)

    if gate_result.passed:
        execute_action(decision, gate_result, razorpay_client, nudge_generator, audit_log_service)
    else:
        action = Action(decision_id=decision.decision_id, arm_name=decision.chosen_arm,
                         simulated=False, status="blocked_at_execution")
        db.save(action)
        audit_log_service.write(event=decision.event, decision=decision, gate_result=gate_result)
```

---

## 4. Full edge-case matrix (expanded)

| # | Case | Expected behavior | How to test |
|---|---|---|---|
| 1 | `execute_action` called with `gate_result.passed=False` | `AssertionError` — structurally unreachable in correct usage | Unit test calling with a manually-constructed failing `GateResult`, assert raises |
| 2 | Razorpay returns a 4xx (permanent) error | Raises `RazorpayPermanentError`, action logged as `status="failed"`, no retry attempted | Unit test with mocked client raising the 4xx-equivalent exception |
| 3 | Razorpay returns a 5xx (transient) error, all retries exhausted | Raises `RazorpayTransientError` after `max_retries` attempts with exponential backoff, action logged `status="failed"` | Unit test with mocked client always raising a transient error, assert call count == max_retries |
| 4 | Same `decision_id` executed twice (idempotency key reused) | Razorpay-native idempotency dedupes, OR application-level guard returns the existing action without a second API call | Idempotency test — see §5.2 |
| 5 | LLM nudge generation raises any exception | `NudgeGenerator.generate` never propagates — falls back to template, `method="template_fallback"` logged | Unit test with a mocked LLM client raising, assert a `NudgeResult` is still returned |
| 6 | LLM nudge generation times out (slow but not erroring) | Timeout enforced client-side (`timeout_seconds`), treated the same as any other failure — falls back | Unit test with a mocked LLM client that sleeps past the timeout |
| 7 | Delayed task fires, but customer opted out since scheduling | Gate re-checked at execution time, blocks, `status="blocked_at_execution"` logged | Integration test — see §5.3 |
| 8 | Delayed task fires, but the referenced `decision_id` no longer exists (data cleanup, bad state) | Logged as an error, task returns without retrying indefinitely | Unit test with a `load_decision` mock returning `None` |
| 9 | `stop` arm executed | Logged as `Action(simulated=True, status="executed")` with no external call — a no-op is still an auditable fact | Unit test asserting no client calls occur, but an `Action` row is still created |
| 10 | Fault injection enabled, Razorpay call fails with a `SimulatedFault` | Propagates through the exact same retry/backoff/failure logic as a real transient error — chaos injection must be indistinguishable from a real failure to the code under test | Covered properly in Phase 11, but write one smoke test here confirming `SimulatedFault` is caught by the same `except` clause as `ServerError` |

---

## 5. Test plan — with actual test code to implement

### 5.1 `services/act/tests/test_routing.py`

```python
import pytest
from unittest.mock import MagicMock
from services.act.service import execute_action

@pytest.fixture
def mocks():
    return {
        "razorpay_client": MagicMock(),
        "nudge_generator": MagicMock(),
        "audit_log_service": MagicMock(),
    }

def make_decision(arm):
    decision = MagicMock()
    decision.chosen_arm = arm
    decision.decision_id = "test-decision-id"
    return decision

def make_passed_gate():
    gate_result = MagicMock()
    gate_result.passed = True
    return gate_result

def test_real_money_arm_calls_razorpay(mocks):
    mocks["razorpay_client"].create_retry_payment_link.return_value = MagicMock(id="pl_123")
    action = execute_action(make_decision("retry_immediate"), make_passed_gate(), **mocks)
    mocks["razorpay_client"].create_retry_payment_link.assert_called_once()
    assert action.simulated is False
    assert action.razorpay_ref_id == "pl_123"

def test_delayed_arm_schedules_celery_task(mocks, monkeypatch):
    apply_async_mock = MagicMock()
    monkeypatch.setattr("services.act.service.execute_delayed_action.apply_async", apply_async_mock)
    action = execute_action(make_decision("retry_long_delay"), make_passed_gate(), **mocks)
    apply_async_mock.assert_called_once()
    _, kwargs = apply_async_mock.call_args
    assert kwargs["eta"] > now()  # scheduled in the future, not executed immediately
    assert action.status == "scheduled"

def test_nudge_arm_calls_llm(mocks):
    mocks["nudge_generator"].generate.return_value = MagicMock(text="hi", method="llm_generated")
    action = execute_action(make_decision("send_nudge_english"), make_passed_gate(), **mocks)
    assert action.simulated is True
    assert action.message_text == "hi"

def test_stop_arm_is_pure_noop(mocks):
    action = execute_action(make_decision("stop"), make_passed_gate(), **mocks)
    mocks["razorpay_client"].assert_not_called()
    mocks["nudge_generator"].assert_not_called()
    assert action.simulated is True
    assert action.status == "executed"

def test_gate_not_passed_raises(mocks):
    failing_gate = MagicMock(passed=False)
    with pytest.raises(AssertionError):
        execute_action(make_decision("retry_immediate"), failing_gate, **mocks)
```

### 5.2 `services/act/tests/test_idempotency.py`

```python
def test_duplicate_execute_action_calls_create_only_once(mocks):
    mocks["razorpay_client"].create_retry_payment_link.return_value = MagicMock(id="pl_123")
    decision = make_decision("retry_immediate")

    execute_action(decision, make_passed_gate(), **mocks)
    execute_action(decision, make_passed_gate(), **mocks)  # simulate a retried Celery task

    # This assertion depends on WHERE idempotency is enforced:
    # - If enforced at the Razorpay API level (native idempotency keys),
    #   this mock-based test can't observe deduplication directly — instead,
    #   assert both calls passed the SAME idempotency_key, and cover the
    #   actual dedup behavior in a Razorpay-test-mode integration test.
    # - If enforced at the application level (checking for an existing
    #   `actions` row by idempotency_key before calling out), assert
    #   create_retry_payment_link was called exactly once here.
    calls = mocks["razorpay_client"].create_retry_payment_link.call_args_list
    idempotency_keys_used = {call.args[1] for call in calls}
    assert len(idempotency_keys_used) == 1, "both calls must use the identical idempotency key"
```

**Write this test to match whichever idempotency mechanism you actually
implement (see §3.1's note)** — don't leave the ambiguity unresolved in
your actual codebase; pick one, document it in a code comment at the top of
`razorpay_client.py`, and make this test assert the real guarantee that
mechanism provides.

### 5.3 `services/act/tests/test_delayed_gate_recheck.py`

```python
def test_delayed_action_blocks_if_opted_out_since_scheduling(db_session, mocks):
    decision = create_test_decision(chosen_arm="retry_long_delay")
    # Simulate scheduling happening, then an opt-out occurring before the task fires
    create_test_opt_out(customer_id=decision.event.episode.customer_id)

    execute_delayed_action(str(decision.decision_id))

    action = get_latest_action_for_decision(decision.decision_id)
    assert action.status == "blocked_at_execution"
    mocks["razorpay_client"].create_retry_payment_link.assert_not_called()
```

### 5.4 `services/act/tests/test_nudge_fallback.py`

```python
def test_llm_failure_falls_back_to_template():
    failing_llm = MagicMock()
    failing_llm.complete.side_effect = TimeoutError("llm too slow")
    generator = NudgeGenerator(llm_client=failing_llm)

    result = generator.generate(make_decision("send_nudge_hinglish"), language="send_nudge_hinglish")

    assert result.method == "template_fallback"
    assert "[payment_link]" in result.text or "{link}" not in result.text  # placeholder substituted
```

---

## 6. Observability — what to log at runtime

Every call to `execute_action` should emit a structured log line
(`structlog`) with: `decision_id`, `chosen_arm`, `simulated`, `status`, and
(if applicable) `razorpay_ref_id` or `nudge_method`. Every Razorpay retry
attempt inside `_call_with_retry` should log the attempt number and backoff
duration — this is what lets you demonstrate, live, exactly how many
retries occurred during Phase 11's chaos beat, rather than asserting it
happened.

---

## 7. Definition of Done (full checklist)

- [ ] `RazorpayClient` wraps every mutating call with idempotency key + retry/backoff, raises typed `RazorpayPermanentError`/`RazorpayTransientError` distinctly.
- [ ] Idempotency mechanism (native or application-level) is explicitly chosen, documented in a code comment, and tested against that specific guarantee.
- [ ] `NudgeGenerator.generate()` never raises under any LLM failure mode — verified by a test that forces an LLM exception and asserts a `NudgeResult` is still returned.
- [ ] `execute_action` routes all 8 arms correctly per the taxonomy in §2.1 — one passing test per arm category.
- [ ] `execute_action` asserts on a non-passed gate result — verified by `test_gate_not_passed_raises`.
- [ ] `execute_delayed_action` re-evaluates the gate at execution time, not scheduling time — verified by `test_delayed_gate_recheck.py`.
- [ ] Fault injection hooks present on both the Razorpay client and the LLM client call boundaries, flag-gated off by default.
- [ ] `stop` and `escalate_human` (no-op arms) still produce an auditable `Action` row.
- [ ] All Razorpay retry attempts and nudge-generation fallbacks are structurally logged (not just asserted in tests).

---

## 8. Prompts for your coding agent

Use these as focused, sequential prompts — one per agent session or
sub-task. `CLAUDE.md`'s repo-wide standards apply automatically; these
assume that context is already loaded (see `docs/AGENT_KICKOFF_PROMPT.md`).

### Prompt 1 — Razorpay client wrapper
```
Implement services/act/razorpay_client.py per docs/phases/PHASE_06_act_DETAILED.md
section 3.1: RazorpayPermanentError, RazorpayTransientError, PaymentLinkResult,
and RazorpayClient with create_retry_payment_link and get_payment_status,
both routed through a shared _call_with_retry helper implementing exponential
backoff on transient errors and immediate raise on permanent (4xx-class)
errors. Before writing this, check the current Razorpay Python SDK docs (or
its installed version's source in this repo's dependencies) for whether
payment_link.create natively supports an idempotency key parameter — if it
does, use it; if it doesn't, implement an application-level idempotency
guard by checking for an existing actions row with the same idempotency_key
before calling out, and document which mechanism you used in a comment at
the top of the file. Write services/act/tests/test_idempotency.py matching
whichever mechanism you implemented, per section 5.2 of the doc.
```

### Prompt 2 — Nudge generator with guaranteed fallback
```
Implement services/act/nudge_generator.py per docs/phases/PHASE_06_act_DETAILED.md
section 3.2: NudgeResult, TEMPLATE_FALLBACKS, and NudgeGenerator.generate().
The critical contract is that generate() must NEVER raise under any LLM
client failure (timeout, exception, malformed response) — it must always
return a NudgeResult, falling back to a template with method="template_fallback"
when the LLM call fails. Keep the broad except-Exception catch here; do not
narrow it, and preserve the comment explaining why it's intentionally broad.
Write services/act/tests/test_nudge_fallback.py per section 5.4 of the doc,
covering both a raised-exception LLM failure and a timeout LLM failure.
```

### Prompt 3 — Fault injection seam
```
Implement services/act/fault_injection.py per docs/phases/PHASE_06_act_DETAILED.md
section 3.3: the with_fault_injection decorator, flag-gated by
settings.fault_injection_enabled and settings.fault_injection_rate (add
these fields to packages/config/settings.py if they don't already exist,
defaulting fault_injection_enabled to False). Apply this decorator at the
correct call boundary inside RazorpayClient._call_with_retry's actual SDK
call, and inside NudgeGenerator.generate's LLM call — not wrapping the
entire method, so injected faults simulate a single failed call rather than
making the whole function disappear. Write one smoke test confirming that
when fault_injection_enabled=True and the injected fault_type is
"server_error", it is caught by RazorpayClient's existing transient-error
retry handling (i.e., a SimulatedFault should be indistinguishable from a
real Razorpay 5xx to the retry logic).
```

### Prompt 4 — Core routing logic
```
Implement services/act/service.py per docs/phases/PHASE_06_act_DETAILED.md
section 3.4: REAL_MONEY_ARMS, DELAYED_ARMS, NUDGE_ARMS, NO_OP_ARMS constants,
ARM_DELAYS, and the full execute_action() function exactly as specified,
including the assertion that gate_result.passed must be True, and the
distinct handling of RazorpayPermanentError vs RazorpayTransientError
(both result in status="failed" but should be logged with different error
codes via audit_log_service.write_error — check services/audit/audit_log_service.py
from Phase 7/9 for the exact method signature before calling it, or stub a
minimal version if Phase 7 hasn't been implemented yet in this session).
Write services/act/tests/test_routing.py exactly per section 5.1 of the
doc, with one test per arm category (real-money, delayed, nudge, no-op) plus
the gate-assertion test.
```

### Prompt 5 — Delayed execution task with gate re-check
```
Implement apps/worker/src/tasks/execute_delayed_action.py per
docs/phases/PHASE_06_act_DETAILED.md section 3.5. The critical requirement,
explained in section 2.3 of the doc, is that the compliance gate MUST be
re-evaluated fresh at execution time using current state (e.g., checking
for opt-outs that may have occurred since scheduling), not reused from
scheduling time. Handle the case where load_decision returns None (the
decision no longer exists) by logging an error and returning without
retrying. Write services/act/tests/test_delayed_gate_recheck.py per section
5.3 of the doc: create a decision with chosen_arm="retry_long_delay", then
create an opt-out for that customer AFTER the decision exists, then call
execute_delayed_action directly and assert it blocks and does not call the
Razorpay client.
```

### Prompt 6 — Full integration + observability + Definition of Done pass
```
Wire razorpay_client.py, nudge_generator.py, fault_injection.py, and
service.py together, ensuring execute_action's dependencies (razorpay_client,
nudge_generator, audit_log_service) are constructed via a single factory or
dependency-injection point that both apps/api and apps/worker can use
consistently — don't let each entrypoint construct its own separately
configured instance. Add structured logging (structlog) per section 6 of
docs/phases/PHASE_06_act_DETAILED.md: every execute_action call logs
decision_id, chosen_arm, simulated, status, and razorpay_ref_id/nudge_method
where applicable; every retry attempt inside _call_with_retry logs the
attempt number and backoff duration. Then work through the full Definition
of Done checklist in section 7 of that doc and report back which items pass,
with actual test output for each — don't summarize, show the real pytest
output for every relevant test file.
```
