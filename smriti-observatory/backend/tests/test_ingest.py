from __future__ import annotations

import asyncio

import pytest

from observatory.broadcaster import Broadcaster
from observatory.events import EnrichedEvent, EnrichedToolCallEvent, MemoryEvent, ToolCallEvent
from observatory.ingest import ingest_one_message, run_ingest_loop
from observatory.snapshot_cache import SnapshotCache


def _event_json(**overrides) -> str:
    base = dict(
        event_id="e1", ts="2026-08-27T00:00:00Z", session_id="s1", student_id="stu1",
        tier="long_term", operation="write", record_type="dpm_profile",
        source_fn="put_dpm", trace_id="abc", span_id="def",
        payload={"student_id": "stu1", "weaknesses": {"x": {"mastery": "known", "strength": "strong", "evidence": ["e1"]}}, "self_reflection": []},
    )
    base.update(overrides)
    return MemoryEvent(**base).model_dump_json()


@pytest.mark.asyncio
async def test_ingest_dpm_write_computes_diff_against_loader():
    cache = SnapshotCache()
    broadcaster = Broadcaster()
    q = broadcaster.subscribe("s1")

    def get_dpm(student_id):
        return {
            "student_id": "stu1",
            "weaknesses": {"x": {"mastery": "partial", "strength": "weak", "evidence": ["e0"]}},
            "self_reflection": [],
        }

    enriched = await ingest_one_message(_event_json(), cache, broadcaster, get_dpm=get_dpm, get_teaching_memory=lambda sid: None)

    assert enriched.event.session_id == "s1"
    labels = {c.path: c.label for c in enriched.diff}
    assert labels["weaknesses.x.mastery"] == "x.mastery: partial -> known"

    delivered = q.get_nowait()
    assert delivered.event.event_id == "e1"


@pytest.mark.asyncio
async def test_ingest_primes_cache_from_a_read_event_so_the_following_write_diffs_against_it():
    cache = SnapshotCache()
    broadcaster = Broadcaster()
    loader_calls = []

    def get_dpm(student_id):
        loader_calls.append(student_id)
        return {"student_id": "stu1", "weaknesses": {}, "self_reflection": []}

    read_event = _event_json(
        event_id="e-read", operation="read", source_fn="get_dpm",
        payload={"student_id": "stu1", "weaknesses": {"x": {"mastery": "partial", "strength": "weak", "evidence": ["e1"]}}, "self_reflection": []},
    )
    write_event = _event_json(
        event_id="e-write", operation="write", source_fn="put_dpm",
        payload={"student_id": "stu1", "weaknesses": {"x": {"mastery": "known", "strength": "strong", "evidence": ["e1", "e2"]}}, "self_reflection": []},
    )

    await ingest_one_message(read_event, cache, broadcaster, get_dpm=get_dpm, get_teaching_memory=lambda sid: None)
    enriched = await ingest_one_message(write_event, cache, broadcaster, get_dpm=get_dpm, get_teaching_memory=lambda sid: None)

    assert loader_calls == []
    labels = {c.path: c.label for c in enriched.diff}
    assert labels["weaknesses.x.mastery"] == "x.mastery: partial -> known"


@pytest.mark.asyncio
async def test_ingest_workflow_event_has_no_diff():
    cache = SnapshotCache()
    broadcaster = Broadcaster()
    broadcaster.subscribe("s1")

    enriched = await ingest_one_message(
        _event_json(tier="workflow", record_type="turn_buffer", payload={"buffer_length": 1}),
        cache, broadcaster, get_dpm=lambda sid: None, get_teaching_memory=lambda sid: None,
    )
    assert enriched.diff == []


@pytest.mark.asyncio
async def test_ingest_broadcasts_to_global_and_session_subscribers():
    cache = SnapshotCache()
    broadcaster = Broadcaster()
    session_q = broadcaster.subscribe("s1")
    global_q = broadcaster.subscribe(None)

    await ingest_one_message(_event_json(), cache, broadcaster, get_dpm=lambda sid: None, get_teaching_memory=lambda sid: None)

    assert session_q.get_nowait().event.event_id == "e1"
    assert global_q.get_nowait().event.event_id == "e1"


@pytest.mark.asyncio
async def test_ingest_does_not_deliver_to_a_different_sessions_queue():
    cache = SnapshotCache()
    broadcaster = Broadcaster()
    other_q = broadcaster.subscribe("some-other-session")

    await ingest_one_message(_event_json(), cache, broadcaster, get_dpm=lambda sid: None, get_teaching_memory=lambda sid: None)

    assert other_q.empty()


def _tool_call_event_json(**overrides) -> str:
    base = dict(
        kind="tool_call", event_id="tc1", ts="2026-08-30T00:00:00Z",
        session_id="s1", student_id="stu1", trace_id="abc", span_id="def",
        actor="board_agent", tool_name="search_grounding", phase="done",
        args_summary=None, result_summary="3 chunks found", duration_ms=842,
    )
    base.update(overrides)
    return ToolCallEvent(**base).model_dump_json()


@pytest.mark.asyncio
async def test_ingest_tool_call_event_broadcasts_without_diffing():
    cache = SnapshotCache()
    broadcaster = Broadcaster()
    q = broadcaster.subscribe("s1")

    enriched = await ingest_one_message(
        _tool_call_event_json(), cache, broadcaster,
        get_dpm=lambda sid: None, get_teaching_memory=lambda sid: None,
    )

    assert isinstance(enriched, EnrichedToolCallEvent)
    assert enriched.event.tool_name == "search_grounding"
    delivered = q.get_nowait()
    assert delivered.event.event_id == "tc1"


@pytest.mark.asyncio
async def test_ingest_distinguishes_tool_call_from_memory_event_on_the_same_channel():
    cache = SnapshotCache()
    broadcaster = Broadcaster()

    memory_result = await ingest_one_message(
        _event_json(), cache, broadcaster,
        get_dpm=lambda sid: None, get_teaching_memory=lambda sid: None,
    )
    tool_result = await ingest_one_message(
        _tool_call_event_json(), cache, broadcaster,
        get_dpm=lambda sid: None, get_teaching_memory=lambda sid: None,
    )

    assert isinstance(memory_result, EnrichedEvent)
    assert isinstance(tool_result, EnrichedToolCallEvent)


class _FakePubSub:
    """Stands in for redis.asyncio's PubSub: a fixed, finite sequence of
    already-received messages, so the real subscribe-forever loop can be
    exercised without an actual Redis connection."""

    def __init__(self, messages: list[dict]) -> None:
        self._messages = messages
        self.subscribed_to: str | None = None
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed_to = channel

    async def listen(self):
        for message in self._messages:
            yield message

    async def aclose(self) -> None:
        self.closed = True


class _FakeRedisClient:
    def __init__(self, messages: list[dict]) -> None:
        self.pubsub_obj = _FakePubSub(messages)
        self.closed = False

    def pubsub(self):
        return self.pubsub_obj

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_run_ingest_loop_survives_a_malformed_message_and_keeps_processing(monkeypatch):
    """Regression test for the finding this guards against: one bad message
    (malformed JSON here; equally a future event kind nobody's updated this
    dispatch for) must not propagate out of the `async for` and end the
    whole ingest loop -- which, before this fix, silently killed live
    Observatory updates for the rest of the process's life."""
    cache = SnapshotCache()
    broadcaster = Broadcaster()
    q = broadcaster.subscribe("s1")

    messages = [
        {"type": "subscribe", "data": 1},  # redis pubsub's own non-"message" control frame
        {"type": "message", "data": "not json at all {{{"},
        {"type": "message", "data": _event_json()},
    ]
    fake_client = _FakeRedisClient(messages)
    monkeypatch.setattr("observatory.ingest.redis.Redis", lambda **kwargs: fake_client)

    await run_ingest_loop(
        "localhost", 6379, cache, broadcaster,
        get_dpm=lambda sid: None, get_teaching_memory=lambda sid: None,
    )

    # The malformed message was skipped, not fatal: the good one right
    # after it still made it all the way through to the broadcaster.
    delivered = q.get_nowait()
    assert delivered.event.event_id == "e1"
    # And the loop still cleaned up its connections on the way out, exactly
    # as it did before this fix.
    assert fake_client.pubsub_obj.closed
    assert fake_client.closed
