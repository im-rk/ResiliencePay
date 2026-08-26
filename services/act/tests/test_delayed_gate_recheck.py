import pytest
from unittest.mock import MagicMock
from packages.db_models.models.action import Action

# We have to patch load_decision, build_context, evaluate_gate to simulate
# Phase 4 being evaluated at execution time and blocking it.
def test_delayed_action_blocks_if_opted_out_since_scheduling(monkeypatch):
    import apps.worker.src.tasks.execute_delayed_action as task_module
    
    decision = MagicMock()
    decision.decision_id = "test-decision-id"
    decision.chosen_arm = "retry_long_delay"
    
    mock_db = MagicMock()
    monkeypatch.setattr(task_module, "SessionLocal", lambda: mock_db)
    
    # Mock load_decision to return our decision
    monkeypatch.setattr(task_module, "load_decision", lambda did, db: decision)
    
    # Mock build_context
    monkeypatch.setattr(task_module, "build_context", lambda event, arm, now: "fake_context")
    
    # Mock evaluate_gate to simulate an opt-out (Gate fails)
    gate_result = MagicMock(passed=False)
    monkeypatch.setattr(task_module, "evaluate_gate", lambda ctx: gate_result)
    
    # Execute
    task_module.execute_delayed_action_task(decision.decision_id)
    
    # Verify that an Action with status="blocked_at_execution" was saved
    mock_db.add.assert_called_once()
    saved_action = mock_db.add.call_args[0][0]
    
    assert isinstance(saved_action, Action)
    assert saved_action.status == "blocked_at_execution"
    mock_db.commit.assert_called_once()
