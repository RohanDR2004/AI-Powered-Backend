import asyncio
import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_backend_test",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
# Separate logical Redis DB for tests (db 1, not the dev default db 0), so
# test runs never pollute or get polluted by real rate-limit/cache state.
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/1")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.redis_client import redis_client

# NullPool: fixtures and the TestClient's internal event loop each get a fresh
# asyncpg connection instead of sharing a pooled one across different loops.
engine = create_async_engine(settings.database_url, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def _drop_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _reset_db():
    asyncio.run(_create_tables())
    yield
    asyncio.run(_drop_tables())


async def _flush_test_redis():
    try:
        await redis_client.flushdb()
    except Exception:
        # Redis may not be running in some environments - tests must still
        # pass (rate limiting/caching fail open), so a flush failure here
        # is not fatal, just means less isolation between tests that run.
        pass


@pytest.fixture(autouse=True)
def _reset_redis():
    """Each test gets a clean rate-limit/cache slate, mirroring _reset_db.
    Without this, real rate-limit counters (now that Redis is live) persist
    across tests within the same 60s window and tests start seeing 429s
    from each other's requests, not from their own behavior under test."""
    asyncio.run(_flush_test_redis())
    yield


async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def registered_user(client):
    payload = {"name": "Test User", "email": "testuser@example.com", "password": "StrongPass123"}
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201
    return payload


@pytest.fixture
def auth_headers(client, registered_user):
    response = client.post(
        "/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
