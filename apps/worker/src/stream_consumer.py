import json
import redis
import structlog
from packages.config.redis_client import redis_client
from packages.db_models.database import SessionLocal
from services.observe.webhook_handlers import (
    handle_payment_captured_webhook,
    handle_subscription_charge_failed_webhook,
)
from services.decide import get_bandit_policy
from services.observe.reward_service import RewardService
from services.audit.audit_log_service import AuditLogService

logger = structlog.get_logger(__name__)

def consume_webhook_events_durable(redis_client, run_once=False):
    GROUP, CONSUMER = "webhook_processors", "worker-1"
    try:
        redis_client.xgroup_create("webhook_stream", GROUP, mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise
            
    bandit = get_bandit_policy(redis_client)
    reward_service = RewardService()
    
    logger.info("started_webhook_stream_consumer")
    while True:
        try:
            messages = redis_client.xreadgroup(GROUP, CONSUMER, {"webhook_stream": ">"}, count=1, block=5000 if not run_once else 1)
            if not messages:
                if run_once:
                    break
                continue
                
            for stream, entries in messages:
                for entry_id, fields in entries:
                    db_session = SessionLocal()
                    audit_log_service = AuditLogService(db_session)
                    
                    try:
                        payload_bytes = fields.get(b"payload") or fields.get("payload")
                        payload = json.loads(payload_bytes)
                        handler = (
                            handle_subscription_charge_failed_webhook
                            if payload.get("event") == "subscription.charge.failed"
                            else handle_payment_captured_webhook
                        )
                        handler(
                            payload, 
                            db_session, 
                            bandit, 
                            reward_service, 
                            audit_log_service
                        )
                        redis_client.xack("webhook_stream", GROUP, entry_id)  # only ack on success
                        logger.info("webhook_processed_and_acked", entry_id=entry_id)
                    except Exception:
                        db_session.rollback()
                        logger.exception("webhook_processing_failed_will_retry", extra={"entry_id": entry_id})
                        # Left unacked — will be redelivered
                    finally:
                        db_session.close()
            if run_once:
                break
        except KeyboardInterrupt:
            logger.info("stopped_webhook_stream_consumer")
            break
        except redis.exceptions.ConnectionError:
            logger.warning("redis_connection_dropped_reconnecting")
            if run_once:
                break
            continue
        except Exception as e:
            logger.error("webhook_consumer_loop_error", error=str(e))
            if run_once:
                break

if __name__ == "__main__":
    consume_webhook_events_durable(redis_client)
