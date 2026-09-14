import logging
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import settings

logger = logging.getLogger(__name__)

# Normalize connection URL (e.g. postgres:// to postgresql:// for cloud compatibility)
db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Determine connection arguments based on database dialect
connect_args = {}
if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
elif "postgresql" in db_url:
    connect_args["connect_timeout"] = 10

# SQLAlchemy Engine
engine = create_engine(
    db_url,
    pool_pre_ping=True,
    pool_timeout=10,
    connect_args=connect_args,
)

# SessionLocal class factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Declarative Base for ORM Models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency for obtaining database sessions per request.

    Yields:
        Session: SQLAlchemy database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> tuple[bool, str]:
    """Safely verify database connectivity.

    Returns:
        tuple[bool, str]: (is_connected, status_message)
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, "connected"
    except Exception as exc:
        logger.warning("Database connection check failed: %s", exc)
        return False, f"disconnected: {exc.__class__.__name__}"


def init_db(bind_engine=None) -> None:
    """Initialize database tables defined by SQLAlchemy models.

    Creates all tables registered with declarative Base if they do not exist.
    Supports supplying an optional engine override (e.g. SQLite for testing).

    Args:
        bind_engine: Optional engine override (defaults to application engine).
    """
    # Import all models to ensure registration with Base.metadata
    import app.models  # noqa: F401

    target_engine = bind_engine or engine
    Base.metadata.create_all(bind=target_engine)
    logger.info("Database tables initialized successfully on engine: %s", target_engine.url)
