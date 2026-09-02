import os
import redis
from services.act.razorpay_client import RazorpayClient
from services.act.nudge_generator import NudgeGenerator
from services.act.service import execute_action
from services.act.circuit_breaker import CircuitBreaker, RedisCircuitBreakerStore

def get_action_executor(db):
    """
    Dependency Injection factory for execute_action.
    Constructs the required external clients and returns a callable.
    """
    from packages.config.settings import settings
    
    key_id = settings.razorpay_key_id
    key_secret = settings.razorpay_key_secret
    
    razorpay_client = RazorpayClient(key_id, key_secret)
    
    # Nudge generator LLM
    nudge_generator = NudgeGenerator()
    
    # Audit log service
    from services.audit.audit_log_service import AuditLogService
    
    redis_url = settings.upstash_redis_rest_url
    redis_client = redis.from_url(redis_url) if redis_url.startswith("redis") else redis.Redis()
    
    audit_log_service = AuditLogService(db, redis_client=redis_client)
    
    # Circuit Breaker
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
