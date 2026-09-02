from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    fault_injection_enabled: bool = False
    fault_injection_rate: float = 0.0

    # Gate Settings
    gate_max_attempts: int = 3
    gate_min_cool_off_hours: int = 24
    gate_allowed_hour_start: int = 9
    gate_allowed_hour_end: int = 20

    # Third Party Credentials
    anthropic_api_key: str = "dummy_key"
    gemini_api_key: str = "dummy_key"
    razorpay_key_id: str = "fake_key"
    razorpay_key_secret: str = "fake_secret"
    razorpay_webhook_secret: str = "fake_webhook_secret"
    upstash_redis_rest_url: str = "redis://localhost:6379"
    upstash_redis_rest_token: str = "dummy_token"

    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }

settings = Settings()
