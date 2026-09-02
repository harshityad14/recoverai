"""Pydantic schemas for health check responses."""

from typing import Dict, Optional
from pydantic import BaseModel, Field


class ComponentStatus(BaseModel):
    """Status details for attached infrastructure components."""

    database: str = Field(..., description="PostgreSQL connectivity status")
    redis: str = Field(..., description="Redis connectivity status")


class HealthResponse(BaseModel):
    """Standard health check response model."""

    status: str = Field(..., description="Overall service status (healthy/ok)")
    service: str = Field(..., description="Service identifier")
    environment: str = Field(..., description="Current environment (development, staging, production)")
    version: str = Field(..., description="Application release version")
    components: Optional[ComponentStatus] = Field(
        default=None,
        description="Health indicators for connected database and cache infrastructure",
    )
