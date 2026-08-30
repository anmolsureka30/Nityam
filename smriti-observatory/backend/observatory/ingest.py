"""Ingests MemoryEvents published by the tutor app (see
sub_modules_examples/tutor/app/memory/instrumentation.py) from Redis, diffs
long-term writes against the snapshot cache, and broadcasts the enriched
result. run_ingest_loop is the real subscribe-forever entry point; the
per-message logic lives in ingest_one_message so it's testable without an
infinite loop.
"""
from __future__ import annotations

from typing import Callable

import redis.asyncio as redis

from observatory.broadcaster import Broadcaster
from observatory.diff import diff_dpm, diff_teaching_memory
from observatory.events import EnrichedEvent, EnrichedToolCallEvent, MemoryEvent, ToolCallEvent
from observatory.snapshot_cache import SnapshotCache

_CHANNEL = "smriti:events:live"


async def ingest_one_message(
    raw: str,
    cache: SnapshotCache,
    broadcaster: Broadcaster,
    get_dpm: Callable[[str], dict | None],
    get_teaching_memory: Callable[[str], dict | None],
) -> EnrichedEvent | EnrichedToolCallEvent:
    import json

    if json.loads(raw).get("kind") == "tool_call":
        tool_event = ToolCallEvent.model_validate_json(raw)
        enriched_tool_call = EnrichedToolCallEvent(event=tool_event)
        broadcaster.publish(enriched_tool_call)
        return enriched_tool_call

    event = MemoryEvent.model_validate_json(raw)
    diff = []
    if event.record_type in ("dpm_profile", "teaching_memory") and event.student_id:
        loader = (
            (lambda: get_dpm(event.student_id)) if event.record_type == "dpm_profile"
            else (lambda: get_teaching_memory(event.student_id))
        )
        if event.operation == "read":
            # Reads always reflect the true state at the moment they happened.
            # close_session calls get_dpm/get_teaching_memory immediately
            # before put_dpm/put_teaching_memory, so priming from the read
            # gives the write its correct pre-write "previous" value — a
            # write-triggered loader() call would instead read Firestore
            # *after* that same write already committed (see snapshot_cache.py
            # docstring).
            cache.set(event.student_id, event.record_type, event.payload)
        else:
            previous = cache.get_and_set(event.student_id, event.record_type, event.payload, loader)
            diff = diff_dpm(previous, event.payload) if event.record_type == "dpm_profile" else diff_teaching_memory(previous, event.payload)
    enriched = EnrichedEvent(event=event, diff=diff)
    broadcaster.publish(enriched)
    return enriched


async def run_ingest_loop(
    redis_host: str, redis_port: int, cache: SnapshotCache, broadcaster: Broadcaster,
    get_dpm: Callable[[str], dict | None], get_teaching_memory: Callable[[str], dict | None],
) -> None:
    client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            await ingest_one_message(message["data"], cache, broadcaster, get_dpm, get_teaching_memory)
    finally:
        await pubsub.aclose()
        await client.aclose()
