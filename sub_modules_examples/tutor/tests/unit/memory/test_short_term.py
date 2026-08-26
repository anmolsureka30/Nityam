from __future__ import annotations

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
