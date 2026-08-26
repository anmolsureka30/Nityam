from __future__ import annotations

import pytest

from app.memory import instrumentation


def test_sync_wrapper_publishes_event_with_extracted_ids(redis_client):
    redis_client.delete("smriti:events:recent")

    @instrumentation.emit_memory_event(
        tier="long_term",
        record_type="dpm_profile",
        operation="read",
        extract_ids=lambda args, kwargs, result: (None, "student_x"),
    )
    def fake_get_dpm(db, student_id):
        return {"student_id": student_id}

    fake_get_dpm(None, "student_x")

    raw = redis_client.lrange("smriti:events:recent", -1, -1)
    assert len(raw) == 1
    event = instrumentation.MemoryEvent.model_validate_json(raw[0])
    assert event.tier == "long_term"
    assert event.record_type == "dpm_profile"
    assert event.operation == "read"
    assert event.student_id == "student_x"
    assert event.session_id is None
    assert event.source_fn == "fake_get_dpm"
    assert event.payload == {"student_id": "student_x"}


def test_sync_wrapper_returns_original_result_unchanged(redis_client):
    @instrumentation.emit_memory_event(
        tier="long_term", record_type="dpm_profile", operation="read",
        extract_ids=lambda args, kwargs, result: (None, None),
    )
    def fake_fn(x):
        return x * 2

    assert fake_fn(21) == 42


@pytest.mark.asyncio
async def test_async_wrapper_publishes_event(redis_client):
    redis_client.delete("smriti:events:recent")

    @instrumentation.emit_memory_event(
        tier="workflow", record_type="turn_buffer", operation="write",
        extract_ids=lambda args, kwargs, result: (args[0], None),
    )
    async def fake_append_turn(session_id, turn):
        return {"buffer_length": 1}

    await fake_append_turn("sess-1", {"turn": 1})

    raw = redis_client.lrange("smriti:events:recent", -1, -1)
    event = instrumentation.MemoryEvent.model_validate_json(raw[0])
    assert event.session_id == "sess-1"
    assert event.tier == "workflow"
    assert event.record_type == "turn_buffer"


def test_session_context_fills_in_when_extractor_uses_it(redis_client):
    redis_client.delete("smriti:events:recent")
    instrumentation.set_session_context("sess-ctx")

    def extract(args, kwargs, result):
        return instrumentation.get_session_context(), "student_y"

    @instrumentation.emit_memory_event(
        tier="long_term", record_type="dpm_profile", operation="write", extract_ids=extract,
    )
    def fake_put_dpm(db, student_id):
        return None

    fake_put_dpm(None, "student_y")

    raw = redis_client.lrange("smriti:events:recent", -1, -1)
    event = instrumentation.MemoryEvent.model_validate_json(raw[0])
    assert event.session_id == "sess-ctx"
    instrumentation.set_session_context(None)  # don't leak into other tests


def test_publishes_even_when_both_session_and_student_id_are_none(redis_client):
    redis_client.delete("smriti:events:recent")

    @instrumentation.emit_memory_event(
        tier="long_term", record_type="grounding_chunk", operation="read",
        extract_ids=lambda args, kwargs, result: (None, None),
    )
    def fake_search(db, concept_ids):
        return []

    fake_search(None, ["x"])

    raw = redis_client.lrange("smriti:events:recent", -1, -1)
    assert len(raw) == 1
    event = instrumentation.MemoryEvent.model_validate_json(raw[0])
    assert event.session_id is None
    assert event.student_id is None
    assert event.record_type == "grounding_chunk"


def test_publish_failure_does_not_raise(monkeypatch, redis_client):
    """A Redis hiccup must never break a real memory write — the whole point
    of fire-and-forget."""
    @instrumentation.emit_memory_event(
        tier="workflow", record_type="turn_buffer", operation="write",
        extract_ids=lambda args, kwargs, result: ("sess-broken", None),
    )
    def fake_fn():
        return "ok"

    monkeypatch.setattr(
        instrumentation, "_get_sync_client",
        lambda: (_ for _ in ()).throw(ConnectionError("simulated outage")),
    )
    assert fake_fn() == "ok"  # must not raise
