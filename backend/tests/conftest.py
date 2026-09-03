"""Pytest test fixtures and configuration."""

from typing import Any, Dict, Optional
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.database import init_db
from app.main import app


class FakeRedis:
    """In-memory Redis substitute for unit testing."""

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._lists: Dict[str, list] = {}

    def lpush(self, name: str, *values: Any) -> int:
        if name not in self._lists:
            self._lists[name] = []
        for v in values:
            self._lists[name].insert(0, v)
        return len(self._lists[name])

    def rpop(self, name: str) -> Optional[str]:
        lst = self._lists.get(name, [])
        if lst:
            return lst.pop()
        return None

    def get(self, name: str) -> Optional[str]:
        return self._data.get(name)

    def set(self, name: str, value: Any, ex: Optional[int] = None) -> bool:
        self._data[name] = str(value)
        return True

    def llen(self, name: str) -> int:
        return len(self._lists.get(name, []))

    def lrange(self, name: str, start: int, end: int) -> list:
        lst = self._lists.get(name, [])
        if end == -1:
            end = len(lst)
        else:
            end = end + 1
        return lst[start:end]

    def ping(self) -> bool:
        return True


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Provides a TestClient instance for issuing requests against the FastAPI application.

    Yields:
        TestClient: Initialized client.
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def fake_redis() -> FakeRedis:
    """Provides a fresh FakeRedis instance for testing."""
    return FakeRedis()


@pytest.fixture
def db_session() -> Session:
    """Provides an isolated in-memory SQLite database session for unit testing."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    init_db(bind_engine=test_engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
