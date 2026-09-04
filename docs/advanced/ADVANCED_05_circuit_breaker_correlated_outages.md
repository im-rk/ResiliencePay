# Advanced Feature 5 — Circuit Breaker for Correlated Gateway Outages

**Effort:** ~half a day
**Builds on:** Phase 6 (Act), Phase 11 (chaos testing)
**Demo impact:** High — this is a distinct, more sophisticated failure mode than Phase 11's existing chaos suite, and it's a named, recognizable production pattern

---

## The gap this closes

Phase 11's existing chaos testing injects **independent, per-call random
failures** (e.g., 15% of individual Razorpay calls fail, uncorrelated with
each other). This is a reasonable model of transient network blips, but it
does **not** model a real and distinct failure mode: a **correlated,
bursty outage** — e.g., every card issued by one specific bank failing
with `GATEWAY_TIMEOUT` for a sustained 20-minute window, because that
bank's systems are actually down, not because of random per-request noise.

Without handling this distinctly, a naive retry policy will burn through
its `max_attempts` budget on transactions that were never recoverable
during the outage window — wasting the customer's limited retry attempts
on a doomed cause, then giving up permanently right as the bank's systems
recover. This is a real, well-known production failure mode, and the fix
— a **circuit breaker** — is a standard, named pattern (popularized by
Netflix's Hystrix library) that detects a burst of correlated failures and
temporarily stops attempting an action category, rather than continuing to
fail and consuming retry budget pointlessly.

## The technique

A circuit breaker has three states:

```
CLOSED (normal)  →  [failure rate exceeds threshold]  →  OPEN (stop trying)
                                                              |
                                                    [cool-off period elapses]
                                                              v
                                            HALF_OPEN (try a small probe)
                                          /                              \
                        [probe succeeds]                    [probe fails]
                               |                                    |
                               v                                    v
                            CLOSED                                 OPEN
```

Scoped **per failure-cause-plus-bank-identifier segment** (not globally) —
this is the key design decision: you want to detect "HDFC card gateway is
down" specifically, not "something somewhere failed once," which would
trip the breaker far too eagerly and stop legitimate recovery attempts for
unrelated, healthy segments.

## Implementation

### `services/act/circuit_breaker.py`

```python
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerState:
    state: CircuitState = CircuitState.CLOSED
    recent_failures: int = 0
    recent_attempts: int = 0
    opened_at: datetime | None = None


class CircuitBreaker:
    """One instance per (bank_identifier) segment — e.g., derived from the
    card's issuing bank if available in the gateway response, or from the
    gateway_error_code's pattern if bank-level detail isn't present.
    Stored in Redis, atomically updated, mirroring the durability pattern
    already established for bandit state in Phase 5."""

    def __init__(self, store: "CircuitBreakerStore", failure_rate_threshold: float = 0.7,
                 min_attempts_before_tripping: int = 5, open_duration: timedelta = timedelta(minutes=10)):
        self.store = store
        self.failure_rate_threshold = failure_rate_threshold
        self.min_attempts_before_tripping = min_attempts_before_tripping
        self.open_duration = open_duration

    def should_allow_attempt(self, segment: str) -> bool:
        state = self.store.get_state(segment)
        if state.state == CircuitState.CLOSED:
            return True
        if state.state == CircuitState.OPEN:
            if datetime.utcnow() - state.opened_at >= self.open_duration:
                self.store.transition(segment, CircuitState.HALF_OPEN)
                return True  # allow exactly one probe attempt through
            return False
        if state.state == CircuitState.HALF_OPEN:
            return True  # only reached here for the single probe attempt
        return True

    def record_result(self, segment: str, succeeded: bool) -> None:
        state = self.store.get_state(segment)

        if state.state == CircuitState.HALF_OPEN:
            # The probe attempt's result decides the next state directly.
            self.store.transition(segment, CircuitState.CLOSED if succeeded else CircuitState.OPEN,
                                   reset_counts=True)
            return

        self.store.increment_attempt(segment, succeeded)
        updated = self.store.get_state(segment)
        if updated.recent_attempts >= self.min_attempts_before_tripping:
            failure_rate = updated.recent_failures / updated.recent_attempts
            if failure_rate >= self.failure_rate_threshold:
                self.store.transition(segment, CircuitState.OPEN)
```

### Wiring into `services/act/service.py`

```python
def execute_action(decision, gate_result, razorpay_client, nudge_generator,
                    audit_log_service, circuit_breaker):
    assert gate_result.passed
    segment = derive_bank_segment(decision.episode)  # e.g., from BIN range or issuer field if available

    if decision.chosen_arm in REAL_MONEY_ARMS:
        if not circuit_breaker.should_allow_attempt(segment):
            # Distinct outcome from a normal gate block — this is a
            # systemic-outage defer, not a compliance block, and should be
            # labeled distinctly in the audit trail.
            action = Action(decision_id=decision.decision_id, arm_name=decision.chosen_arm,
                             simulated=False, status="deferred_circuit_open")
            audit_log_service.write_note(decision, note=f"circuit_open_for_segment:{segment}")
            return action

        try:
            result = razorpay_client.create_retry_payment_link(decision.episode, idempotency_key=...)
            circuit_breaker.record_result(segment, succeeded=True)
            ...
        except (RazorpayTransientError, RazorpayPermanentError):
            circuit_breaker.record_result(segment, succeeded=False)
            ...
```

**Critically, a `deferred_circuit_open` outcome must NOT consume the
episode's `attempt_count`** — this is the entire point of the feature:
protecting a customer's limited retry budget from being wasted during a
detected systemic outage, so they still have real attempts left once the
gateway recovers.

## The chaos test that proves this works

```python
def test_circuit_breaker_prevents_wasted_attempts_during_correlated_outage(db_session):
    """Simulates the exact scenario from the feedback: a burst of
    correlated failures for one segment, sustained over multiple attempts."""
    breaker = CircuitBreaker(RedisCircuitBreakerStore(fake_redis), min_attempts_before_tripping=5)
    segment = "HDFC"

    # First 5 attempts all fail — simulating a real outage, not random noise
    for _ in range(5):
        assert breaker.should_allow_attempt(segment) is True
        breaker.record_result(segment, succeeded=False)

    # Circuit should now be OPEN — further attempts deferred, not wasted
    assert breaker.should_allow_attempt(segment) is False

    # After the cool-off period, exactly one probe attempt is allowed through
    advance_fake_clock(minutes=11)
    assert breaker.should_allow_attempt(segment) is True

    # If the probe succeeds, the circuit closes and normal attempts resume
    breaker.record_result(segment, succeeded=True)
    assert breaker.should_allow_attempt(segment) is True


def test_unrelated_segment_unaffected_by_another_segments_outage():
    """The scoping-per-segment decision, verified — HDFC failing must not
    affect ICICI's circuit state."""
    breaker = CircuitBreaker(RedisCircuitBreakerStore(fake_redis), min_attempts_before_tripping=5)
    for _ in range(5):
        breaker.record_result("HDFC", succeeded=False)
    assert breaker.should_allow_attempt("HDFC") is False
    assert breaker.should_allow_attempt("ICICI") is True
```

## Dashboard addition

A small, distinct visual state in `AuditTrailTable` for
`deferred_circuit_open` rows — different from both `recovered` and normal
`failed`/`blocked_by_policy` — and a live indicator if any segment's
circuit is currently open, so a judge can see this triggered explicitly
in the chaos-testing demo beat (Phase 11) as a *second*, distinct failure
scenario alongside the existing per-call fault injection.

## What to say in the demo

*"We distinguish between two different failure modes a real payments
system has to handle differently: random, independent transient errors —
which we handle with retries and backoff — and correlated, systemic
outages, like one bank's gateway going down entirely. For the second case,
a circuit breaker detects the burst of correlated failures and defers
further attempts for that specific segment, without burning through the
customer's limited retry budget on transactions that have no chance of
succeeding until the outage clears. This is the same pattern popularized
by Netflix's Hystrix library, applied to payments recovery specifically."*
