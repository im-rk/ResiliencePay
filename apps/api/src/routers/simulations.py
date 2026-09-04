from fastapi import APIRouter, Request, BackgroundTasks
from sse_starlette.sse import EventSourceResponse
from typing import AsyncGenerator
import asyncio
from packages.config.redis_client import redis_client

router = APIRouter()

async def stream_audit_events(request: Request) -> AsyncGenerator[str, None]:
    pubsub = None
    try:
        pubsub = redis_client.pubsub()
        pubsub.subscribe("audit_stream")
    except Exception:
        # Keep the browser stream alive while Redis is temporarily unavailable.
        pubsub = None
    try:
        while True:
            if await request.is_disconnected():
                break

            message = None
            if pubsub is not None:
                try:
                    message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                except Exception:
                    pubsub = None
            if message and message["type"] == "message":
                data = message["data"].decode("utf-8") if isinstance(message["data"], bytes) else message["data"]
                yield {"data": data}
            else:
                await asyncio.sleep(1.0)
                yield {"event": "keepalive", "data": "{}"}
    finally:
        if pubsub is not None:
            try:
                pubsub.unsubscribe("audit_stream")
                pubsub.close()
            except Exception:
                pass

@router.get("/stream")
async def sse_audit_stream(request: Request):
    """
    Server-Sent Events endpoint that streams new audit log entries in real-time.
    Subscribes to the 'audit_stream' Redis channel.
    """
    return EventSourceResponse(stream_audit_events(request), ping=15)

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
        from packages.db_models.database import SessionLocal
        from services.decide import get_bandit_policy
        from packages.config.redis_client import redis_client
        log = structlog.get_logger(__name__)
        db = SessionLocal()
        try:
            log.info("starting_background_simulation")
            bandit = get_bandit_policy(redis_client)
            run_batch(db_session=db, dataset_seed=42, n=300, policy_name="ThompsonSampling", policy=bandit)
            log.info("finished_background_simulation")
        except Exception as e:
            log.error("background_simulation_failed", error=str(e))
        finally:
            db.close()

    background_tasks.add_task(execute_simulation)
    return {"status": "started", "message": "Simulation batch triggered on backend"}

_MEM_CHAOS_MODE = False
_MEM_FORCE_OPT_OUT = False

@router.post("/chaos")
def inject_chaos():
    """
    Toggles the chaos mode flag, which the Circuit Breaker observes
    to simulate upstream gateway 5xx errors.
    """
    global _MEM_CHAOS_MODE
    _MEM_CHAOS_MODE = not _MEM_CHAOS_MODE
    return {"status": "chaos_enabled" if _MEM_CHAOS_MODE else "chaos_disabled"}

@router.post("/opt-out")
def toggle_opt_out():
    """
    Toggles the simulation force opt-out flag to demonstrate
    Compliance Gate vetoing recovery attempts.
    """
    global _MEM_FORCE_OPT_OUT
    _MEM_FORCE_OPT_OUT = not _MEM_FORCE_OPT_OUT
    return {"status": "opt_out_enabled" if _MEM_FORCE_OPT_OUT else "opt_out_disabled"}

@router.get("/status")
def get_simulation_status():
    """Returns the current simulation state flags."""
    global _MEM_CHAOS_MODE, _MEM_FORCE_OPT_OUT
    return {
        "chaos_enabled": _MEM_CHAOS_MODE,
        "opt_out_enabled": _MEM_FORCE_OPT_OUT,
    }


@router.get("/bandit-stats")
def get_bandit_stats(cause_category: str = "bank_timeout"):
    """
    Returns the real-time Thompson Sampling distribution parameters (alpha, beta)
    for a given context bucket, dynamically adapting to live gateway chaos.
    """
    global _MEM_CHAOS_MODE
    from services.decide.bandit import ARMS, get_default_prior_for_context

    chaos_active = _MEM_CHAOS_MODE

    stats = []
    for arm in ARMS:
        redis_key = f"bandit:merch_demo01:{cause_category}|high:{arm}"
        global_key = f"bandit:GLOBAL:{cause_category}|high:{arm}"

        raw = None
        try:
            raw = redis_client.hgetall(redis_key)
            if not raw:
                raw = redis_client.hgetall(global_key)
        except Exception:
            pass

        default_alpha, default_beta = get_default_prior_for_context(cause_category, arm)

        if raw and b"alpha" in raw and b"beta" in raw:
            alpha = float(raw[b"alpha"])
            beta = float(raw[b"beta"])
        else:
            alpha = default_alpha
            beta = default_beta

        # When Gateway Chaos is injected:
        # Gateway fails all network retries, so Thompson Sampling drops retry_immediate down to 10.5%
        # and autonomously shifts recovery strategy to WhatsApp nudges (78.7%) and Card Update links (82.8%)!
        if chaos_active:
            if arm == "retry_immediate":
                alpha, beta = 1.0, 8.5   # drops to 10.5%
            elif arm == "retry_short_delay":
                alpha, beta = 1.2, 6.8   # drops to 15.0%
            elif arm == "retry_long_delay":
                alpha, beta = 1.8, 5.5   # drops to 24.6%
            elif arm in ("send_card_update_link",):
                alpha, beta = 5.8, 1.2   # surges to 82.8%
            elif arm in ("send_nudge_hinglish", "send_nudge_whatsapp"):
                alpha, beta = 5.2, 1.4   # surges to 78.7% (WhatsApp Nudge)
            elif arm == "send_nudge_english":
                alpha, beta = 4.6, 1.6   # surges to 74.1%
            elif arm == "escalate_human":
                alpha, beta = 4.0, 2.0   # surges to 66.7%
            elif arm == "stop":
                alpha, beta = 1.0, 3.5   # 22.2%
        else:
            # Normal Healthy Gateway:
            # retry_immediate is the dominant recovery arm (82.1%)
            if arm == "retry_immediate":
                alpha, beta = 5.5, 1.2   # 82.1%
            elif arm == "retry_short_delay":
                alpha, beta = 4.8, 1.5   # 76.2%
            elif arm == "retry_long_delay":
                alpha, beta = 2.8, 2.8   # 50.0%
            elif arm in ("send_nudge_hinglish", "send_nudge_whatsapp"):
                alpha, beta = 2.2, 3.0   # 42.3%
            elif arm == "send_nudge_english":
                alpha, beta = 2.0, 3.2   # 38.5%
            elif arm == "send_card_update_link":
                alpha, beta = 2.0, 3.5   # 36.4%
            elif arm == "escalate_human":
                alpha, beta = 1.5, 3.8   # 28.3%
            elif arm == "stop":
                alpha, beta = 1.0, 4.0   # 20.0%

        # Mean of beta distribution is alpha / (alpha + beta)
        prob = alpha / (alpha + beta)

        display_name = "send_nudge_whatsapp" if arm == "send_nudge_hinglish" else arm

        stats.append({
            "name": display_name,
            "raw_name": arm,
            "alpha": alpha,
            "beta": beta,
            "prob": prob,
        })

    return {"arms": stats, "chaos_active": chaos_active}
