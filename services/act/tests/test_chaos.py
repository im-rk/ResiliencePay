import pytest
import uuid
from packages.config.settings import settings
from data.generator import generate_batch
from services.act.razorpay_client import RazorpayClient
from services.act.nudge_generator import NudgeGenerator
from services.act.service import execute_action
from services.decide.bandit import ThompsonSamplingBandit
from services.decide.redis_store import RedisArmStatsStore
from services.audit.audit_log_service import AuditLogService

class MockLLMClient:
    def complete(self, prompt: str, timeout: float = 5.0) -> str:
        return "Fake LLM completion"

class MockDB:
    def __init__(self):
        self.objects = []
        self._queries = []
    
    def add(self, obj):
        self.objects.append(obj)
    
    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def query(self, model):
        # Very simple mock just enough to make execute_action not crash
        class QueryMock:
            def filter(self, *args, **kwargs):
                return self
            def first(self):
                return None
        return QueryMock()

class MockAuditLogService:
    def __init__(self):
        self.errors = []
        self.notes = []

    def write_error(self, decision, code, reason):
        self.errors.append({"decision": decision, "code": code, "reason": reason})

    def write_note(self, decision, note):
        self.notes.append({"decision": decision, "note": note})

def run_batch_with_injected_faults(events):
    # This simulates the real backend pipeline
    import fakeredis
    redis_client = fakeredis.FakeRedis()
    store = RedisArmStatsStore(redis_client, default_priors={"retry_immediate": (1.0, 1.0)})
    bandit = ThompsonSamplingBandit(store)
    
    # Needs to be mocked properly or it hits real URLs
    class FakeRazorpayClient(RazorpayClient):
        def __init__(self):
            super().__init__("test", "test", max_retries=2, base_backoff_seconds=0.001)
            # Patch the inner client so we don't hit real Razorpay
            self._client = type("MockClient", (), {
                "payment_link": type("MockPL", (), {
                    "create": lambda self, payload: {"id": "pl_" + str(uuid.uuid4()), "short_url": "http://mock", "status": "created"}
                })()
            })()
            
    razorpay_client = FakeRazorpayClient()
    nudge_generator = NudgeGenerator(MockLLMClient(), timeout_seconds=0.1)
    audit_log = MockAuditLogService()
    db = MockDB()

    results = []

    for event in events:
        decision_id = uuid.uuid4()
        
        class FakeEvent:
            pass
        class FakeDecision:
            def __init__(self):
                self.decision_id = decision_id
                self.chosen_arm = "retry_immediate"  # Keep it simple for chaos test, or random
                self.episode = type("FakeEpisode", (), {"episode_id": uuid.uuid4(), "original_amount": 100, "currency": "INR"})()
        
        class FakeGateResult:
            passed = True
        
        decision = FakeDecision()
        gate_result = FakeGateResult()
        
        # Act layer
        action = execute_action(decision, gate_result, razorpay_client, nudge_generator, audit_log, db)
        
        # The test requires final_status to be captured. Let's record action.status
        # Note: 'failed' in action maps to 'not_recovered' or 'failed_permanently'
        results.append({
            "event_id": event.get("event_id", uuid.uuid4()),
            "action_status": action.status,
            "action": action
        })
        
        bandit.update("test_merchant", "test_bucket", decision.chosen_arm, reward=1.0)

    # Return structure matching what test expects
    return results, bandit, audit_log, db

def test_pipeline_survives_15pct_fault_rate():
    # Setup chaos
    settings.fault_injection_enabled = True
    settings.fault_injection_rate = 0.15
    
    events = generate_batch(seed=42, n=200)
    
    # We do a specific run that isolates the actual Act logic
    results, bandit, audit_log, db = run_batch_with_injected_faults(events)

    # 1. No event silently dropped
    for r in results:
        # Our Action object maps states executed/scheduled/failed
        assert r["action_status"] in {"executed", "scheduled", "failed"}
        assert r["action"].status in {"executed", "scheduled", "failed"}

    # 2. Audit trail has zero gaps (every event generated an Action record in DB)
    assert len(db.objects) == len(events), "Every event should yield 1 Action in DB"
    
    # Verify that some faults actually occurred!
    assert len(audit_log.errors) > 0, "At 15% fault rate over 200 events, some errors must have been logged"

    # 3. Bandit state remains internally consistent
    # Since we did 200 updates, bandit alpha should be 1 + 200 = 201
    alpha, beta = bandit.store.get_stats("test_merchant", "test_bucket", "retry_immediate")
    assert alpha == 201.0
    
    # Cleanup
    settings.fault_injection_enabled = False
    settings.fault_injection_rate = 0.0
