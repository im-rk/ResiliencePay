from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

logger = structlog.get_logger()

app = FastAPI(
    title="ResiliencePay API",
    description="API for the AI Revenue Recovery Agent",
    version="0.1.0",
)

# Configure CORS for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    logger.info("Health check called")
    return {"status": "ok", "service": "resiliencepay-api"}

@app.get("/")
async def root():
    return {"message": "Welcome to ResiliencePay API"}
