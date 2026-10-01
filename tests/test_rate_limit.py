from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.rate_limit import RateLimiter


def _build_app(limit: str) -> TestClient:
    app = FastAPI()

    @app.get("/limited", dependencies=[Depends(RateLimiter(limit))])
    def limited():
        return {"ok": True}

    return TestClient(app)


def test_rate_limit_parses_limit_string():
    limiter = RateLimiter("5/minute")
    assert limiter.max_requests == 5
    assert limiter.window_seconds == 60


def test_requests_under_limit_succeed():
    client = _build_app("5/minute")
    counter = {"n": 0}

    async def fake_increment(self, key):
        counter["n"] += 1
        return counter["n"]

    with patch.object(RateLimiter, "_increment", new=fake_increment):
        for _ in range(5):
            response = client.get("/limited")
            assert response.status_code == 200


def test_requests_over_limit_return_429():
    client = _build_app("3/minute")
    counter = {"n": 0}

    async def fake_increment(self, key):
        counter["n"] += 1
        return counter["n"]

    with patch.object(RateLimiter, "_increment", new=fake_increment):
        for _ in range(3):
            assert client.get("/limited").status_code == 200
        response = client.get("/limited")
        assert response.status_code == 429
        assert "Retry-After" in response.headers


def test_rate_limiter_fails_open_when_redis_unavailable():
    client = _build_app("1/minute")

    async def broken_increment(self, key):
        raise ConnectionError("redis unreachable")

    with patch.object(RateLimiter, "_increment", new=broken_increment):
        # Even though the "limit" is 1/minute, every request should succeed
        # because the limiter fails open when Redis is unavailable.
        for _ in range(3):
            assert client.get("/limited").status_code == 200
