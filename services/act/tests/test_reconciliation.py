import pytest
import uuid
from datetime import timedelta
from unittest.mock import MagicMock
from packages.db_models.models.pending_action import PendingAction
from packages.db_models.models.dead_lettered_action import DeadLetteredAction
from packages.db_models.models.action import Action
from packages.db_models.models.decision import Decision
from apps.worker.src.tasks.reconcile_pending_actions import reconcile_pending_actions, now

class MockDB:
    def __init__(self):
        self.objects = []
    
    def query(self, model):
        class QueryMock:
            def __init__(self, db_obj):
                self.db_obj = db_obj
            def filter(self, *args, **kwargs):
                return self
            def first(self):
                for obj in self.db_obj.objects:
                    if isinstance(obj, model):
                        return obj
                return None
            def all(self):
                return [obj for obj in self.db_obj.objects if isinstance(obj, model)]
        return QueryMock(self)

    def add(self, obj):
        self.objects.append(obj)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

def test_reconciliation_recovers_a_genuine_dual_write_gap(mocker):
    # Mock SessionLocal to return MockDB
    mock_db = MockDB()
    mocker.patch("apps.worker.src.tasks.reconcile_pending_actions.SessionLocal", return_value=mock_db)
    
    # Mock RazorpayClient
    mock_rp_client = MagicMock()
    # Simulate finding a payment link
    mock_payment_link = MagicMock()
    mock_payment_link.id = "pl_123"
    mock_rp_client.find_payment_link_by_idempotency_key.return_value = mock_payment_link
    mocker.patch("apps.worker.src.tasks.reconcile_pending_actions.RazorpayClient", return_value=mock_rp_client)
    
    pending = PendingAction(
        pending_action_id=uuid.uuid4(),
        decision_id=uuid.uuid4(),
        idempotency_key="idemp_1",
        status="attempting",
        created_at=now() - timedelta(minutes=15)
    )
    decision = Decision(decision_id=pending.decision_id, chosen_arm="retry_immediate")
    mock_db.add(pending)
    mock_db.add(decision)
    
    reconcile_pending_actions()
    
    assert pending.status == "reconciled"
    assert pending.razorpay_ref_id == "pl_123"
    
    # Check if Action was backfilled
    actions = [obj for obj in mock_db.objects if isinstance(obj, Action)]
    assert len(actions) == 1
    assert actions[0].status == "executed"
    assert actions[0].razorpay_ref_id == "pl_123"

def test_reconciliation_dead_letters_a_genuinely_failed_attempt(mocker):
    mock_db = MockDB()
    mocker.patch("apps.worker.src.tasks.reconcile_pending_actions.SessionLocal", return_value=mock_db)
    
    mock_rp_client = MagicMock()
    # Simulate Razorpay having no record
    mock_rp_client.find_payment_link_by_idempotency_key.return_value = None
    mocker.patch("apps.worker.src.tasks.reconcile_pending_actions.RazorpayClient", return_value=mock_rp_client)
    
    pending = PendingAction(
        pending_action_id=uuid.uuid4(),
        decision_id=uuid.uuid4(),
        idempotency_key="idemp_2",
        status="attempting",
        created_at=now() - timedelta(minutes=15)
    )
    mock_db.add(pending)
    
    reconcile_pending_actions()
    
    assert pending.status == "dead_lettered"
    
    # Check if DeadLetteredAction was created
    dlqs = [obj for obj in mock_db.objects if isinstance(obj, DeadLetteredAction)]
    assert len(dlqs) == 1
    assert dlqs[0].pending_action_id == pending.pending_action_id
