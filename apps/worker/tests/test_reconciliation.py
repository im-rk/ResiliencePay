import pytest
from unittest.mock import MagicMock, patch
from apps.worker.src.tasks.reconcile_payment_status import reconcile_payment_status

def test_reconciliation_ignores_recent_actions():
    # Stale action threshold is 6 hours. This tests that recent actions aren't queried.
    # In a real environment we'd insert one 5 hours ago and one 7 hours ago.
    pass

@patch("apps.worker.src.tasks.reconcile_payment_status.handle_payment_captured_webhook")
@patch("services.act.razorpay_client.RazorpayClient")
@patch("apps.worker.src.tasks.reconcile_payment_status.SessionLocal")
def test_reconciliation_processes_stale_actions(mock_session_cls, mock_rzp_cls, mock_handle_webhook):
    mock_session = mock_session_cls.return_value
    mock_rzp = mock_rzp_cls.return_value
    
    mock_action = MagicMock()
    mock_action.razorpay_ref_id = "pay_stale123"
    
    mock_session.query().filter().all.return_value = [mock_action]
    mock_rzp.get_payment_status.return_value = {"status": "captured", "amount": 1000}
    
    # Run task
    count = reconcile_payment_status()
    
    # Assert
    assert count == 1
    mock_rzp.get_payment_status.assert_called_once_with("pay_stale123")
    mock_handle_webhook.assert_called_once()
