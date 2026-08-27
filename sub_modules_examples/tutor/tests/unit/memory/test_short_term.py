from __future__ import annotations

from datetime import datetime

import time as _time

import pytest

from app.memory import instrumentation, short_term


@pytest.mark.asyncio
async def test_append_turn_publishes_workflow_event(redis_client):
    redis_client.delete("smriti:events:recent")
    try:
        await short_term.append_turn("test_st_sess_1", {"turn": 1, "role": "student", "text": "hi"})
        raw = redis_client.lrange("smriti:events:recent", -1, -1)
        event = instrumentation.MemoryEvent.model_validate_json(raw[0])
        assert event.tier == "workflow"
        assert event.record_type == "turn_buffer"
        assert event.operation == "write"
        assert event.session_id == "test_st_sess_1"
    finally:
        redis_client.delete("session:test_st_sess_1:turns")


@pytest.mark.asyncio
async def test_get_turn_buffer_publishes_read_event(redis_client):
    redis_client.delete("smriti:events:recent")
    try:
        await short_term.append_turn("test_st_sess_2", {"turn": 1, "role": "student", "text": "hi"})
        redis_client.delete("smriti:events:recent")  # isolate the read event
        result = await short_term.get_turn_buffer("test_st_sess_2")
        assert result == [{"turn": 1, "role": "student", "text": "hi"}]
        raw = redis_client.lrange("smriti:events:recent", -1, -1)
        event = instrumentation.MemoryEvent.model_validate_json(raw[0])
        assert event.operation == "read"
        assert event.session_id == "test_st_sess_2"
    finally:
        redis_client.delete("session:test_st_sess_2:turns")


@pytest.mark.asyncio
async def test_clear_session_publishes_write_event(redis_client):
    redis_client.delete("smriti:events:recent")
    await short_term.append_turn("test_st_sess_3", {"turn": 1, "role": "student", "text": "hi"})
    redis_client.delete("smriti:events:recent")
    await short_term.clear_session("test_st_sess_3")
    raw = redis_client.lrange("smriti:events:recent", -1, -1)
    event = instrumentation.MemoryEvent.model_validate_json(raw[0])
    assert event.tier == "workflow"
    assert event.record_type == "turn_buffer"
    assert event.operation == "write"
    assert event.session_id == "test_st_sess_3"


@pytest.mark.asyncio
async def test_refresh_heartbeat_sets_a_ttl_key(redis_client):
    try:
        await short_term.refresh_heartbeat("test_st_hb_1", ttl_seconds=2)
        assert redis_client.get("session:test_st_hb_1:heartbeat") == "1"
        ttl = redis_client.ttl("session:test_st_hb_1:heartbeat")
        assert 0 < ttl <= 2
    finally:
        redis_client.delete("session:test_st_hb_1:heartbeat")


@pytest.mark.asyncio
async def test_ensure_started_at_is_idempotent(redis_client):
    try:
        await short_term.ensure_started_at("test_st_sa_1")
        first = await short_term.get_started_at("test_st_sa_1")
        _time.sleep(0.05)
        await short_term.ensure_started_at("test_st_sa_1")  # second call must not move it
        second = await short_term.get_started_at("test_st_sa_1")
        assert first == second
        assert isinstance(first, datetime)
    finally:
        redis_client.delete("session:test_st_sa_1:started_at")


@pytest.mark.asyncio
async def test_get_started_at_returns_none_when_unset(redis_client):
    assert await short_term.get_started_at("test_st_sa_missing") is None
