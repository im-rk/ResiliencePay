import pytest
from unittest.mock import MagicMock
from services.act.service import execute_action
from packages.db_models.models.action import Action
import uuid

@pytest.fixture
def mocks():
    return {
        "razorpay_client": MagicMock(),
        "nudge_generator": MagicMock(),
        "audit_log_service": MagicMock(),
        "db": MagicMock(),
    }

def make_decision(arm):
    decision = MagicMock()
    decision.chosen_arm = arm
    decision.decision_id = uuid.uuid4()
    return decision

def make_passed_gate():
    gate_result = MagicMock()
    gate_result.passed = True
    return gate_result

def test_duplicate_execute_action_calls_create_only_once(mocks):
    """
    Tests application-level idempotency: if an Action with the decision_id 
    already exists in the DB, we return it and DO NOT call Razorpay again.
    """
    mocks["razorpay_client"].create_retry_payment_link.return_value = MagicMock(id="pl_123", short_url="http://x", status="created")
    decision = make_decision("retry_immediate")

    # First call: DB returns None for existing action
    mocks["db"].query.return_value.filter.return_value.first.return_value = None
    
    action1 = execute_action(decision, make_passed_gate(), **mocks)
    
    # Assert client was called once
    mocks["razorpay_client"].create_retry_payment_link.assert_called_once()
    
    # Second call (simulating Celery retry on a crash after save):
    # DB now returns the existing Action row.
    existing_action = Action(decision_id=decision.decision_id, arm_name="retry_immediate", simulated=False, razorpay_ref_id="pl_123", status="executed")
    mocks["db"].query.return_value.filter.return_value.first.return_value = existing_action
    
    action2 = execute_action(decision, make_passed_gate(), **mocks)
    
    # Assert client was NOT called a second time
    assert mocks["razorpay_client"].create_retry_payment_link.call_count == 1
    
    # Assert the identical action is returned
    assert action1.razorpay_ref_id == "pl_123"
    assert action2.razorpay_ref_id == "pl_123"
