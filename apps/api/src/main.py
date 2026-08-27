from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
import re
import os
from apps.api.src.middleware.request_id import RequestIDMiddleware
from apps.api.src.routers import events, admin

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
        structlog.dev.ConsoleRenderer() if os.environ.get("ENVIRONMENT") == "development" else structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()

app = FastAPI(
    title="ResiliencePay API",
    description="API for the AI Revenue Recovery Agent",
    version="0.1.0",
)

# Configure CORS for dashboard
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.add_middleware(RequestIDMiddleware)

app.include_router(events.router)
app.include_router(admin.router)


@app.get("/health")
async def health_check():
    logger.info("Health check called")
    return {"status": "ok", "service": "resiliencepay-api"}

@app.get("/")
async def root():
    return {"message": "Welcome to ResiliencePay API"}
