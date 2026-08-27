from __future__ import annotations

import asyncio

import pytest

from observatory.broadcaster import Broadcaster
from observatory.events import MemoryEvent
from observatory.ingest import ingest_one_message
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
