from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
import re
import os

from apps.api.src.middleware.error_handler import register_error_handlers
from apps.api.src.middleware.request_id import RequestIDMiddleware
from apps.api.src.routers import events, batch, metrics, audit, admin, simulations, webhooks

SECRET_PATTERNS = [re.compile(r"(key_secret|api_key|password|ADMIN_SECRET)=\S+", re.IGNORECASE)]

def redact_secrets_processor(logger, method_name, event_dict):
    for key, value in event_dict.items():
        if isinstance(value, str):
            for pattern in SECRET_PATTERNS:
                value = pattern.sub(r"\1=[REDACTED]", value)
            event_dict[key] = value
    return event_dict

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        redact_secrets_processor,
        structlog.dev.ConsoleRenderer() if os.environ.get("ENVIRONMENT") == "development" else structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger()

app = FastAPI(
    title="ResiliencePay API",
    description="API for the AI Revenue Recovery Agent — Detect, Diagnose, Decide, Act, Observe",
    version="0.1.0",
)

# Register structured domain and exception error handlers
register_error_handlers(app)

# Configure CORS to accept all origins
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.add_middleware(RequestIDMiddleware)

# Include all core routers under /v1
app.include_router(events.router, prefix="/v1", tags=["events"])
app.include_router(batch.router, prefix="/v1", tags=["batch"])
app.include_router(metrics.router, prefix="/v1", tags=["metrics"])
app.include_router(audit.router, prefix="/v1", tags=["audit"])
app.include_router(admin.router, prefix="/v1", tags=["admin"])
app.include_router(simulations.router, prefix="/v1/simulations", tags=["simulations"])
app.include_router(webhooks.router, prefix="/v1", tags=["webhooks"])


@app.get("/healthz")
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "resiliencepay-api"}


@app.get("/")
def root():
    return {
        "message": "Welcome to ResiliencePay API",
        "docs_url": "/docs",
        "version": "0.1.0",
    }
# Reload trigger

