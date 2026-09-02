from apps.worker.src.celery_app import app as celery_app
from packages.db_models.database import SessionLocal
from packages.db_models.models import PromiseToPay, Episode, AuditLog
from datetime import date, timedelta
import structlog

logger = structlog.get_logger(__name__)

@celery_app.task(name='check_promise_to_pay_deadlines')
def check_promise_to_pay_deadlines():
    db_session = SessionLocal()
    
    try:
        now_date = date.today()
        # Find promises past their grace period (grace period is 1 day, so if promised_date + 1 < now_date)
        overdue = db_session.query(PromiseToPay).filter(
            PromiseToPay.status == "active",
            PromiseToPay.promised_date < (now_date - timedelta(days=1))
        ).all()
        
        for ptp in overdue:
            episode = db_session.query(Episode).filter_by(episode_id=ptp.episode_id).first()
            if not episode:
                continue
                
            if episode.status == "recovered":
                ptp.status = "kept"
                logger.info("ptp_kept", ptp_id=str(ptp.ptp_id))
            else:
                ptp.status = "broken"
                db_session.add(AuditLog(
                    episode_id=episode.episode_id,
                    outcome_result="note",
                    error_code=f"ptp_broken:{ptp.promised_date}"
                ))
                logger.info("ptp_broken", ptp_id=str(ptp.ptp_id), episode_id=str(episode.episode_id))
                
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        logger.error("check_promise_to_pay_failed", error=str(e))
    finally:
        db_session.close()
