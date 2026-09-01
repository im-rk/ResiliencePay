import os
import redis
from services.act.razorpay_client import RazorpayClient
from services.act.nudge_generator import NudgeGenerator
from services.act.service import execute_action
from services.act.circuit_breaker import CircuitBreaker, RedisCircuitBreakerStore

class FakeLLMClient:
    def complete(self, prompt: str, timeout: float):
        # A simple fake for the hackathon / untest environment
        return f"Payment failed! Please pay here: [payment_link]"

def get_action_executor(db):
    """
    Dependency Injection factory for execute_action.
    Constructs the required external clients and returns a callable.
    """
    # In a real app, these keys come from Secrets Manager / Hashicorp Vault
    from packages.config.settings import settings
    
    key_id = settings.razorpay_key_id
    key_secret = settings.razorpay_key_secret
    
    razorpay_client = RazorpayClient(key_id, key_secret)
    
    # Nudge generator LLM
    nudge_generator = NudgeGenerator(llm_client=FakeLLMClient())
    
    # Audit log service (Assume implemented in Phase 7, mock for now)
    class DummyAudit:
        def write_error(self, *args, **kwargs): pass
        def write_note(self, *args, **kwargs): pass
        def write(self, *args, **kwargs): pass
    audit_log_service = DummyAudit()
    
    # Circuit Breaker
    redis_url = settings.upstash_redis_rest_url
    redis_client = redis.from_url(redis_url) if redis_url.startswith("redis") else redis.Redis()
    circuit_breaker = CircuitBreaker(RedisCircuitBreakerStore(redis_client))
    
    def executor(decision, gate_result, schedule_delayed_action=None):
        return execute_action(
            decision, 
            gate_result, 
            razorpay_client, 
            nudge_generator, 
            audit_log_service, 
            db,
            circuit_breaker=circuit_breaker,
            schedule_delayed_action=schedule_delayed_action
        )
        
    return executor
