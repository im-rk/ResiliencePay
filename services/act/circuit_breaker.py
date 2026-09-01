from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Protocol


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


class CircuitBreakerStore(Protocol):
    def get_state(self, segment: str) -> CircuitBreakerState:
        ...

    def transition(self, segment: str, state: CircuitState, reset_counts: bool = False) -> None:
        ...

    def increment_attempt(self, segment: str, succeeded: bool) -> None:
        ...


class RedisCircuitBreakerStore(CircuitBreakerStore):
    def __init__(self, client):
        self.client = client

    def _key(self, segment: str) -> str:
        return f"circuit_breaker:{segment}"

    def get_state(self, segment: str) -> CircuitBreakerState:
        key = self._key(segment)
        raw = self.client.hgetall(key)
        if not raw:
            return CircuitBreakerState()
        
        state_str = raw.get(b"state", b"closed").decode("utf-8")
        try:
            state = CircuitState(state_str)
        except ValueError:
            state = CircuitState.CLOSED
            
        recent_failures = int(raw.get(b"recent_failures", b"0"))
        recent_attempts = int(raw.get(b"recent_attempts", b"0"))
        
        opened_at_str = raw.get(b"opened_at")
        opened_at = None
        if opened_at_str:
            try:
                # Store as isoformat
                opened_at = datetime.fromisoformat(opened_at_str.decode("utf-8"))
            except ValueError:
                pass
                
        return CircuitBreakerState(
            state=state,
            recent_failures=recent_failures,
            recent_attempts=recent_attempts,
            opened_at=opened_at
        )

    def transition(self, segment: str, state: CircuitState, reset_counts: bool = False) -> None:
        key = self._key(segment)
        updates = {"state": state.value}
        if state == CircuitState.OPEN:
            updates["opened_at"] = datetime.now(timezone.utc).isoformat()
        if reset_counts:
            updates["recent_failures"] = 0
            updates["recent_attempts"] = 0
            self.client.hdel(key, "opened_at")
            
        self.client.hset(key, mapping=updates)

    def increment_attempt(self, segment: str, succeeded: bool) -> None:
        key = self._key(segment)
        self.client.hincrby(key, "recent_attempts", 1)
        if not succeeded:
            self.client.hincrby(key, "recent_failures", 1)


class CircuitBreaker:
    """One instance per (bank_identifier) segment — e.g., derived from the
    card's issuing bank if available in the gateway response, or from the
    gateway_error_code's pattern if bank-level detail isn't present.
    Stored in Redis, atomically updated, mirroring the durability pattern
    already established for bandit state in Phase 5."""

    def __init__(self, store: CircuitBreakerStore, failure_rate_threshold: float = 0.7,
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
            if state.opened_at and datetime.now(timezone.utc) - state.opened_at >= self.open_duration:
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
