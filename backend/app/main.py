"""RecoverAI Backend Application Entrypoint.

Phase 1: Foundation, configuration, infrastructure connections, and health endpoints.
Phase 2: Razorpay webhook handler, signature verification, idempotency, and Redis queue.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.health import router as health_router
from app.api.routes.webhook import router as webhook_router
from app.core.config import settings

# Create FastAPI application instance
app = FastAPI(
    title=f"{settings.APP_NAME} Backend",
    description="AI-powered payment recovery agent for Razorpay AI Buildathon.",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure Cross-Origin Resource Sharing (CORS) for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Hackathon-appropriate permissive CORS for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount health routes directly at root level (/health) as requested
app.include_router(health_router)

# Mount webhook routes (/webhooks/razorpay)
app.include_router(webhook_router)

# Mount API V1 prefixed routes
app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(webhook_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["Root"])
def root():
    """Root entrypoint offering API discovery links."""
    return {
        "service": settings.APP_NAME,
        "status": "operational",
        "phase": "Phase 2 - Webhook Handler & Redis Queue",
        "docs": "/docs",
        "health": "/health",
        "webhooks": "/webhooks/razorpay",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
