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
        chaos_active = False
        try:
            from packages.config.redis_client import redis_client
            chaos_val = redis_client.get("circuit_breaker:chaos_mode")
            if chaos_val and (chaos_val == b"1" or chaos_val == "1"):
                chaos_active = True
        except Exception:
            pass

        if chaos_active or getattr(settings, "fault_injection_enabled", False):
            rate = 0.60 if chaos_active else getattr(settings, "fault_injection_rate", 0.0)
            if random.random() < rate:
                fault_type = random.choice(FAULT_TYPES)
                raise SimulatedFault(fault_type)
        return fn(*args, **kwargs)
    return wrapper
