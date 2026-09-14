"""RecoverAI Backend Application Entrypoint.

Phase 1: Foundation, configuration, infrastructure connections, and health endpoints.
Phase 2: Razorpay webhook handler, signature verification, idempotency, and Redis queue.
"""

import logging
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.health import router as health_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.webhook import router as webhook_router
from app.core.config import settings

logger = logging.getLogger(__name__)

# Worker process management for single-instance deployment
_worker_thread: Optional[threading.Thread] = None
_worker_stop_event: Optional[threading.Event] = None
_worker_lock = threading.Lock()


def start_background_worker() -> None:
    """Start the WebhookWorker in a managed background thread if not already running."""
    global _worker_thread, _worker_stop_event
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            logger.info("Background WebhookWorker thread is already running.")
            return

        from app.workers.webhook_worker import create_worker_for_deployment

        _worker_stop_event = threading.Event()
        worker = create_worker_for_deployment()

        def _run():
            logger.info("RecoverAI background WebhookWorker thread started.")
            try:
                worker.run(stop_event=_worker_stop_event)
            except Exception as exc:
                logger.error("Error in background WebhookWorker thread: %s", exc)

        _worker_thread = threading.Thread(
            target=_run,
            name="RecoverAI-WebhookWorker",
            daemon=True,
        )
        _worker_thread.start()
        logger.info("RecoverAI background WebhookWorker thread successfully launched.")


def stop_background_worker() -> None:
    """Signal background WebhookWorker to terminate and await cleanup."""
    global _worker_thread, _worker_stop_event
    with _worker_lock:
        if _worker_stop_event is not None:
            logger.info("Signaling background WebhookWorker thread to stop...")
            _worker_stop_event.set()
        if _worker_thread is not None:
            _worker_thread.join(timeout=3.0)
            _worker_thread = None
            _worker_stop_event = None
            logger.info("Background WebhookWorker thread terminated cleanly.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for startup initialization and graceful shutdown."""
    # 1. Initialize database tables if needed for deployment
    try:
        from app.core.database import init_db
        init_db()
    except Exception as exc:
        logger.warning("Database table initialization on startup encountered an issue: %s", exc)

    # 2. Start background worker if enabled in configuration
    if settings.WORKER_ENABLED:
        start_background_worker()

    yield

    # 3. Graceful shutdown
    if settings.WORKER_ENABLED:
        stop_background_worker()


# Create FastAPI application instance
app = FastAPI(
    title=f"{settings.APP_NAME} Backend",
    description="AI-powered payment recovery agent for Razorpay AI Buildathon.",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure Cross-Origin Resource Sharing (CORS) for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount health routes directly at root level (/health) as requested
app.include_router(health_router)

# Mount webhook routes (/webhooks/razorpay)
app.include_router(webhook_router)

# Mount metrics routes (/metrics/recovery)
app.include_router(metrics_router)

# Mount API V1 prefixed routes
app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(webhook_router, prefix=settings.API_V1_PREFIX)
app.include_router(metrics_router, prefix=settings.API_V1_PREFIX)


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
