import pytest
from datetime import datetime, timezone
import uuid
from packages.db_models.models.episode import Episode
from packages.db_models.models.merchant import Merchant
from packages.db_models.models.customer import Customer
from packages.db_models.models.gate_check import GateCheck
from services.gate.service import evaluate_gate
from unittest.mock import MagicMock

def test_adversarial_high_confidence_block():
    """
    Test that even if a bandit is 99% confident in a real-money action,
    if max_attempts is exceeded, the gate absolute-blocks it.
    """
    # Mock the DB session instead of connecting to a live Postgres instance
    db_session = MagicMock()
    
    merchant = Merchant(merchant_id=uuid.uuid4(), name="Adv Merchant", razorpay_key_id="rzp_adv", vertical="saas")
    customer = Customer(customer_id=uuid.uuid4(), merchant_id=merchant.merchant_id, segment="new")

    # Construct context where bandit chooses real-money arm with high confidence,
    # but attempt_count is 4 (which exceeds max 3).
    episode = Episode(
        episode_id=uuid.uuid4(),
        merchant_id=merchant.merchant_id,
        customer_id=customer.customer_id,
        original_amount=5000,
        opened_at=datetime.now(timezone.utc)
    )
    episode.attempt_count = 4 # Exceeded max
    episode.last_action_at = datetime.now(timezone.utc)

    # Bandit context (faked for the adversarial test)
    bandit_confidence = 0.99
    arm_name = "email_with_discount" # real-money-moving arm

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc) # valid time window
    
    # Mock opt-out query to return None (so it passes opt_out check and hits max_attempts check)
    db_session.query.return_value.filter.return_value.first.return_value = None
    
    # Evaluate gate
    decision_id = uuid.uuid4()
    result = evaluate_gate(db_session, decision_id, episode, customer.customer_id, arm_name, now)
    
    # ASSERT THE BANDIT DOES NOT OVERRIDE THE GATE
    assert result.passed is False
    assert result.rule_name == "max_attempts"
    
    # Verify db.add() was called with a GateCheck that blocked the action
    db_session.add.assert_called_once()
    db_session.commit.assert_called_once()
    
    added_obj = db_session.add.call_args[0][0]
    assert isinstance(added_obj, GateCheck)
    assert added_obj.decision_id == decision_id
    assert added_obj.result == "blocked"
    assert added_obj.rule_triggered == "max_attempts"
