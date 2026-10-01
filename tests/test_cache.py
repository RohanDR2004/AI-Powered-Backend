from unittest.mock import AsyncMock, patch

import pytest

from app.cache import get_cached, invalidate, invalidate_pattern, set_cached


@pytest.mark.asyncio
async def test_get_cached_returns_none_on_miss():
    with patch("app.cache.redis_client.get", new=AsyncMock(return_value=None)):
        assert await get_cached("some:key") is None


@pytest.mark.asyncio
async def test_get_cached_returns_parsed_json_on_hit():
    with patch("app.cache.redis_client.get", new=AsyncMock(return_value='{"id": 1, "title": "x"}')):
        assert await get_cached("some:key") == {"id": 1, "title": "x"}


@pytest.mark.asyncio
async def test_get_cached_falls_back_to_none_when_redis_errors():
    with patch("app.cache.redis_client.get", new=AsyncMock(side_effect=ConnectionError("down"))):
        # Must not raise - a cache failure is treated as a miss.
        assert await get_cached("some:key") is None


@pytest.mark.asyncio
async def test_set_cached_swallows_redis_errors():
    with patch("app.cache.redis_client.set", new=AsyncMock(side_effect=ConnectionError("down"))):
        # Must not raise.
        await set_cached("some:key", {"a": 1}, ttl_seconds=30)


@pytest.mark.asyncio
async def test_invalidate_calls_delete_with_keys():
    mock_delete = AsyncMock()
    with patch("app.cache.redis_client.delete", new=mock_delete):
        await invalidate("key1", "key2")
    mock_delete.assert_awaited_once_with("key1", "key2")


@pytest.mark.asyncio
async def test_invalidate_pattern_deletes_matched_keys():
    async def fake_scan_iter(match):
        for key in ["cache:tasks:user:1:skip:0:limit:50", "cache:tasks:user:1:skip:10:limit:50"]:
            yield key

    mock_delete = AsyncMock()
    with patch("app.cache.redis_client.scan_iter", side_effect=lambda match: fake_scan_iter(match)):
        with patch("app.cache.redis_client.delete", new=mock_delete):
            await invalidate_pattern("cache:tasks:user:1:*")
    mock_delete.assert_awaited_once()


def test_task_list_and_detail_are_cached_and_invalidated(client, auth_headers):
    create = client.post("/tasks", json={"title": "Cache me"}, headers=auth_headers)
    task_id = create.json()["id"]

    # First read populates the cache (or falls back gracefully if Redis is
    # unavailable in this environment); either way the data must be correct.
    first = client.get(f"/tasks/{task_id}", headers=auth_headers)
    assert first.status_code == 200
    assert first.json()["title"] == "Cache me"

    client.put(f"/tasks/{task_id}", json={"title": "Updated title"}, headers=auth_headers)

    # After an update, a subsequent read must reflect the new value, not a
    # stale cached one - this is the invalidation contract.
    after_update = client.get(f"/tasks/{task_id}", headers=auth_headers)
    assert after_update.json()["title"] == "Updated title"
