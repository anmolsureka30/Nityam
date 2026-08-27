from __future__ import annotations

import asyncio

import pytest
import redis.asyncio as redis

from app import config
from app.app_utils import idle_watcher


@pytest.mark.asyncio
async def test_run_one_expiry_cycle_closes_the_expired_session(redis_client, monkeypatch):
    client = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    await client.config_set("notify-keyspace-events", "Ex")
    pubsub = client.pubsub()
    await pubsub.psubscribe("__keyevent@0__:expired")

    closed = []

    async def fake_close(session_id, student_id=None):
        closed.append(session_id)

    monkeypatch.setattr(idle_watcher, "perform_close_session", fake_close)

    try:
        await client.set("session:test_idle_watch_1:heartbeat", "1", px=200)  # 0.2s TTL
        await asyncio.sleep(0.5)
        result = await idle_watcher.run_one_expiry_cycle(pubsub, timeout=2.0)
        assert result == "test_idle_watch_1"
        assert closed == ["test_idle_watch_1"]
    finally:
        await pubsub.aclose()
        await client.aclose()


@pytest.mark.asyncio
async def test_run_one_expiry_cycle_ignores_unrelated_keys(redis_client, monkeypatch):
    client = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    await client.config_set("notify-keyspace-events", "Ex")
    pubsub = client.pubsub()
    await pubsub.psubscribe("__keyevent@0__:expired")

    monkeypatch.setattr(idle_watcher, "perform_close_session", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not close")))

    try:
        await client.set("some_unrelated_key", "1", px=200)
        await asyncio.sleep(0.5)
        result = await idle_watcher.run_one_expiry_cycle(pubsub, timeout=1.0)
        assert result is None
    finally:
        await pubsub.aclose()
        await client.aclose()
