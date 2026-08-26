from services.decide.redis_store import RedisArmStatsStore
from packages.db_models.models.bandit_arm_stats import BanditArmStats
from sqlalchemy.dialects.postgresql import insert
import structlog

logger = structlog.get_logger(__name__)

def upsert_bandit_arm_stats(db_session, context_bucket: str, arm_name: str, alpha: float, beta: float):
    stmt = insert(BanditArmStats).values(
        context_bucket=context_bucket,
        arm_name=arm_name,
        alpha=alpha,
        beta=beta
    )
    
    # On conflict (primary key is context_bucket + arm_name), update alpha and beta
    do_update_stmt = stmt.on_conflict_do_update(
        index_elements=['context_bucket', 'arm_name'],
        set_={
            'alpha': stmt.excluded.alpha,
            'beta': stmt.excluded.beta
        }
    )
    
    db_session.execute(do_update_stmt)


def snapshot_bandit_state_to_postgres(store: RedisArmStatsStore, db_session) -> int:
    """Invoked periodically by apps/worker (Celery beat). Scans all
    bandit:* keys in Redis and upserts them into bandit_arm_stats. Returns
    the number of rows written, for logging/observability."""
    count = 0
    for key in store.client.scan_iter(match="bandit:*"):
        parts = key.decode().split(":", 2)
        if len(parts) < 3:
            continue
            
        _, context_bucket, arm = parts
        
        raw = store.client.hgetall(key)
        if not raw:
            continue
            
        alpha, beta = float(raw.get(b"alpha", 1.0)), float(raw.get(b"beta", 1.0))
        
        upsert_bandit_arm_stats(db_session, context_bucket, arm, alpha, beta)
        count += 1
        
    db_session.commit()
    
    logger.info("bandit_snapshot_completed", rows_written=count)
    return count
