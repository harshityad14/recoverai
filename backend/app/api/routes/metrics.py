"""Recovery metrics API route endpoint.

Provides internal analytics endpoint for retrieving recovery KPIs:
- revenue_at_risk
- recovered_revenue
- recovery_rate
- total_failed_transactions
- total_recovered_transactions
- payment_links_created
- stopped_transactions
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.metrics import RecoveryMetrics
from app.services.metrics_service import RecoveryMetricsService

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get(
    "/recovery",
    response_model=RecoveryMetrics,
    summary="Recovery Metrics",
    description="Returns real-time, deterministic payment recovery metrics calculated from database state.",
)
def get_recovery_metrics(db: Session = Depends(get_db)) -> RecoveryMetrics:
    """Compute and return recovery metrics."""
    service = RecoveryMetricsService(db)
    return service.calculate_metrics()
