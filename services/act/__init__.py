import os
from services.act.razorpay_client import RazorpayClient
from services.act.nudge_generator import NudgeGenerator
from services.act.service import execute_action

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
    key_id = os.environ.get("RAZORPAY_KEY_ID", "fake_key")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "fake_secret")
    
    razorpay_client = RazorpayClient(key_id, key_secret)
    
    # Nudge generator LLM
    nudge_generator = NudgeGenerator(llm_client=FakeLLMClient())
    
    # Audit log service (Assume implemented in Phase 7, mock for now)
    class DummyAudit:
        def write_error(self, *args, **kwargs): pass
        def write_note(self, *args, **kwargs): pass
        def write(self, *args, **kwargs): pass
    audit_log_service = DummyAudit()
    
    def executor(decision, gate_result):
        return execute_action(
            decision, 
            gate_result, 
            razorpay_client, 
            nudge_generator, 
            audit_log_service, 
            db
        )
        
    return executor
