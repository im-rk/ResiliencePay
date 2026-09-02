from fastapi import APIRouter, Request, BackgroundTasks
from sse_starlette.sse import EventSourceResponse
from typing import AsyncGenerator
import json
import asyncio
from packages.config.redis_client import redis_client

router = APIRouter()

async def stream_audit_events(request: Request) -> AsyncGenerator[str, None]:
    pubsub = redis_client.pubsub()
    pubsub.subscribe("audit_stream")
    try:
        while True:
            if await request.is_disconnected():
                break
            
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                data = message["data"].decode("utf-8") if isinstance(message["data"], bytes) else message["data"]
                yield {"data": data}
            else:
                await asyncio.sleep(0.5)
    finally:
        pubsub.unsubscribe("audit_stream")

@router.get("/stream")
async def sse_audit_stream(request: Request):
    """
    Server-Sent Events endpoint that streams new audit log entries in real-time.
    Subscribes to the 'audit_stream' Redis channel.
    """
    return EventSourceResponse(stream_audit_events(request))

@router.post("/run")
def run_batch_simulation(background_tasks: BackgroundTasks):
    """
    Trigger a backend-driven simulation of 300 events.
    Spawns a background task that writes to the DB and publishes events to the Redis stream.
    """
    from eval.run_batch import run_batch
    # Run the batch logic as a background task. 
    # run_batch is assumed to be synchronous or async depending on its implementation.
    # We will wrap it in a try-except for safety.
    def execute_simulation():
        import structlog
        log = structlog.get_logger(__name__)
        try:
            log.info("starting_background_simulation")
            # We trigger run_batch which uses the real services.
            run_batch(batch_size=300)
            log.info("finished_background_simulation")
        except Exception as e:
            log.error("background_simulation_failed", error=str(e))

    background_tasks.add_task(execute_simulation)
    return {"status": "started", "message": "Simulation batch triggered on backend"}

@router.post("/chaos")
def inject_chaos():
    """
    Toggles the chaos mode flag in Redis, which the Circuit Breaker observes
    to simulate upstream 5xx errors.
    """
    current_chaos = redis_client.get("circuit_breaker:chaos_mode")
    if current_chaos and current_chaos == b"1":
        redis_client.set("circuit_breaker:chaos_mode", "0")
        return {"status": "chaos_disabled"}
    else:
        redis_client.set("circuit_breaker:chaos_mode", "1")
        return {"status": "chaos_enabled"}

@router.get("/bandit-stats")
def get_bandit_stats(cause_category: str):
    """
    Returns the real-time Thompson Sampling distribution parameters (alpha, beta)
    for a given context bucket.
    """
    from services.decide.bandit import ARMS, get_default_prior_for_context
    
    stats = []
    for arm in ARMS:
        # these keys match redis_store.py
        # run_batch uses "merch_demo01" as default merchant_id
        redis_key = f"bandit:merch_demo01:{cause_category}|high:{arm}"
        
        # fallback to GLOBAL if not found
        global_key = f"bandit:GLOBAL:{cause_category}|high:{arm}"

        raw = redis_client.hgetall(redis_key)
        if not raw:
            raw = redis_client.hgetall(global_key)
        
        default_alpha, default_beta = get_default_prior_for_context(cause_category, arm)
        
        if raw and b"alpha" in raw and b"beta" in raw:
            alpha = float(raw[b"alpha"])
            beta = float(raw[b"beta"])
        else:
            alpha = default_alpha
            beta = default_beta
        
        # Mean of beta distribution is alpha / (alpha + beta)
        prob = alpha / (alpha + beta)
        
        stats.append({
            "name": arm,
            "alpha": alpha,
            "beta": beta,
            "prob": prob
        })
        
    return {"arms": stats}
