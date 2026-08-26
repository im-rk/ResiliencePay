import pytest
from unittest.mock import MagicMock
from services.act.service import execute_action, now

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
    decision.decision_id = "test-decision-id"
    # Ensure episode has an episode_id for logging
    decision.episode.episode_id = "test-episode-id"
    decision.event.episode.episode_id = "test-episode-id"
    return decision

def make_passed_gate():
    gate_result = MagicMock()
    gate_result.passed = True
    return gate_result

def test_real_money_arm_calls_razorpay(mocks):
    mocks["db"].query.return_value.filter.return_value.first.return_value = None
    mocks["razorpay_client"].create_retry_payment_link.return_value = MagicMock(id="pl_123")
    
    action = execute_action(make_decision("retry_immediate"), make_passed_gate(), **mocks)
    
    mocks["razorpay_client"].create_retry_payment_link.assert_called_once()
    assert action.simulated is False
    assert action.razorpay_ref_id == "pl_123"
    mocks["db"].add.assert_called_once()

def test_delayed_arm_schedules_celery_task(mocks, monkeypatch):
    mocks["db"].query.return_value.filter.return_value.first.return_value = None
    apply_async_mock = MagicMock()
    # We must patch the Celery task we import in service.py
    monkeypatch.setattr("apps.worker.src.tasks.execute_delayed_action.execute_delayed_action_task.apply_async", apply_async_mock)
    
    action = execute_action(make_decision("retry_long_delay"), make_passed_gate(), **mocks)
    
    apply_async_mock.assert_called_once()
    _, kwargs = apply_async_mock.call_args
    assert kwargs["eta"] > now()  # scheduled in the future
    assert action.status == "scheduled"
    mocks["db"].add.assert_called_once()

def test_nudge_arm_calls_llm(mocks):
    mocks["db"].query.return_value.filter.return_value.first.return_value = None
    mocks["nudge_generator"].generate.return_value = MagicMock(text="hi", method="llm_generated")
    
    action = execute_action(make_decision("send_nudge_english"), make_passed_gate(), **mocks)
    
    assert action.simulated is True
    assert action.message_text == "hi"
    mocks["db"].add.assert_called_once()

def test_stop_arm_is_pure_noop(mocks):
    mocks["db"].query.return_value.filter.return_value.first.return_value = None
    action = execute_action(make_decision("stop"), make_passed_gate(), **mocks)
    
    mocks["razorpay_client"].create_retry_payment_link.assert_not_called()
    mocks["nudge_generator"].generate.assert_not_called()
    assert action.simulated is True
    assert action.status == "executed"
    mocks["db"].add.assert_called_once()

def test_gate_not_passed_raises(mocks):
    failing_gate = MagicMock(passed=False)
    with pytest.raises(AssertionError):
        execute_action(make_decision("retry_immediate"), failing_gate, **mocks)
