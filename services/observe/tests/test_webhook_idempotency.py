from unittest.mock import MagicMock
from services.observe.webhook_handlers import handle_payment_captured_webhook

def test_duplicate_webhook_delivery_is_idempotent(mocker):
    # Mock DB session
    db_session = MagicMock()
    fake_bandit = MagicMock()
    real_reward_service = MagicMock()
    real_reward_service.compute.return_value = 1.0
    fake_audit_log = MagicMock()
    
    # Mock action query
    mock_action = MagicMock()
    mock_action.action_id = "test-action-123"
    db_session.query().filter().first.side_effect = [
        mock_action, # Action
        MagicMock(), # Decision
        MagicMock()  # Event
    ]
    
    # Mock execute result
    mock_result_proxy = MagicMock()
    mock_result_proxy.rowcount = 1
    db_session.execute.return_value = mock_result_proxy
    
    payload = {"payment": {"id": "pay_abc123", "amount": 149900}}
    
    # First delivery
    handle_payment_captured_webhook(payload, db_session, fake_bandit, real_reward_service, fake_audit_log)
    
    assert fake_bandit.update.call_count == 1
    assert fake_audit_log.write.call_count == 1
    
    # Second delivery (duplicate)
    # Reset mocks for next delivery context
    db_session.query().filter().first.side_effect = [
        mock_action, # Action
        MagicMock(), # Decision
        MagicMock()  # Event
    ]
    mock_result_proxy.rowcount = 0  # Is not new
    
    handle_payment_captured_webhook(payload, db_session, fake_bandit, real_reward_service, fake_audit_log)
    
    # Still 1 because it didn't increase
    assert fake_bandit.update.call_count == 1
    assert fake_audit_log.write.call_count == 1

def test_webhook_for_unknown_razorpay_ref_does_not_crash(caplog):
    db_session = MagicMock()
    db_session.query().filter().first.return_value = None
    
    fake_bandit = MagicMock()
    real_reward_service = MagicMock()
    fake_audit_log = MagicMock()
    
    payload = {"payment": {"id": "pay_does_not_exist", "amount": 100}}
    handle_payment_captured_webhook(payload, db_session, fake_bandit, real_reward_service, fake_audit_log)
    
    assert "webhook_unknown_razorpay_ref" in caplog.text
    fake_bandit.update.assert_not_called()
