from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Root directory of backend and project root
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    # Application settings
    APP_NAME: str = "RecoverAI"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    API_V1_PREFIX: str = "/api/v1"

    # PostgreSQL Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/recoverai_db"

    # Redis Cache & Queue
    REDIS_URL: str = "redis://localhost:6379/0"

    # Razorpay Configurations (Placeholders for future phases)
    RAZORPAY_KEY_ID: Optional[str] = "rzp_test_placeholder_key"
    RAZORPAY_KEY_SECRET: Optional[str] = "placeholder_secret_key"
    RAZORPAY_WEBHOOK_SECRET: Optional[str] = "placeholder_webhook_secret"

    # LLM Settings — model and provider are configurable via environment.
    # Production model will be set when provider/model is confirmed.
    GEMINI_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gemini-2.5-flash"
    LLM_TIMEOUT_SECONDS: float = 10.0
    LLM_TEMPERATURE: float = 0.0

    # Deterministic Safety Guard Settings (Phase 5)
    LLM_MIN_CONFIDENCE: float = 0.70
    MAX_RECOVERY_RETRIES: int = 2

    # Frontend URL
    VITE_API_BASE_URL: str = "http://localhost:8000"

    model_config = SettingsConfigDict(
        env_file=(
            ROOT_DIR / ".env",
            BACKEND_DIR / ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
