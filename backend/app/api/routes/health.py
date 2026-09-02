"""Health check route endpoints."""

from fastapi import APIRouter
from app.core.config import settings
from app.core.database import check_db_connection
from app.core.redis import check_redis_connection
from app.schemas.health import HealthResponse, ComponentStatus

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Returns service availability, runtime environment, and infrastructure status.",
)
def get_health() -> HealthResponse:
    """Return health and status information for RecoverAI backend."""
    _, db_msg = check_db_connection()
    _, redis_msg = check_redis_connection()

    return HealthResponse(
        status="healthy",
        service=settings.APP_NAME,
        environment=settings.ENVIRONMENT,
        version="0.1.0",
        components=ComponentStatus(
            database=db_msg,
            redis=redis_msg,
        ),
    )
