from unittest.mock import MagicMock, patch
from apps.worker.src.stream_consumer import consume_webhook_events_durable

@patch("apps.worker.src.stream_consumer.handle_payment_captured_webhook")
@patch("apps.worker.src.stream_consumer.SessionLocal")
def test_failed_processing_is_redelivered_not_lost(mock_session, mock_handle):
    # Setup mock redis stream
    mock_redis = MagicMock()
    
    # First message fails
    mock_handle.side_effect = Exception("Simulated Failure")
    
    # Mock xreadgroup to return 1 message
    mock_redis.xreadgroup.return_value = [
        ("webhook_stream", [("12345-0", {b"payload": b'{"payment": {"id": "pay_123"}}'})])
    ]
    
    consume_webhook_events_durable(mock_redis, run_once=True)
    
    # xack should NOT have been called because it failed
    mock_redis.xack.assert_not_called()
    
    # Second time, it succeeds
    mock_handle.side_effect = None
    consume_webhook_events_durable(mock_redis, run_once=True)
    
    # xack should have been called this time
    mock_redis.xack.assert_called_with("webhook_stream", "webhook_processors", "12345-0")
