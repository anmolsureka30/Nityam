"""session_events_endpoint (backend/app/memory_routes.py) reads
smriti:events:recent, which holds a mix of MemoryEvent and ToolCallEvent
JSON on the same list. Regression test: it used to call
MemoryEvent.model_validate_json() unconditionally, which raised a pydantic
ValidationError (missing source_fn/record_type) the moment any
ToolCallEvent had ever been published — confirmed live in production, and
silently masked by routes_rest.py's own try/except into an empty
{"events": []} response instead of a loud error.

Needs local Redis (same requirement as tests/test_memory_store_events.py).

    .venv/bin/python -m tests.test_memory_routes_events
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid

from app.auth import load_env

load_env()

import redis as redis_sync  # noqa: E402

from app import config  # noqa: E402
from app.memory import instrumentation  # noqa: E402
from app.memory_routes import session_events_endpoint  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


async def run() -> None:
    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    client.delete("smriti:events:recent")

    session_id = f"test_events_{uuid.uuid4().hex[:8]}"

    memory_event = instrumentation.MemoryEvent(
        event_id="e1", ts="2026-08-30T00:00:00Z", session_id=session_id, student_id="stu1",
        tier="workflow", operation="write", record_type="turn_buffer", source_fn="append_turn",
        trace_id=None, span_id=None, payload=None,
    )
    tool_call_event = instrumentation.build_tool_call_event(
        actor="board_agent", tool_name="search_grounding", phase="done",
        session_id=session_id, student_id="stu1", result_summary="3 chunks",
    )
    client.rpush("smriti:events:recent", memory_event.model_dump_json())
    client.rpush("smriti:events:recent", tool_call_event.model_dump_json())

    try:
        result = await session_events_endpoint(session_id, "stu1")
        events = result["events"]
        check("endpoint does not raise on a mixed-kind list", True)
        check("both events for this session are returned", len(events) == 2, repr(events))
        kinds = {e.get("kind") for e in events}
        check("the tool-call event keeps its kind field", "tool_call" in kinds, repr(kinds))
        memory_entry = next((e for e in events if e.get("source_fn") == "append_turn"), None)
        check("the memory event has no kind field (wire format unchanged)", memory_entry is not None and "kind" not in memory_entry)
    except Exception as exc:  # noqa: BLE001
        check("endpoint does not raise on a mixed-kind list", False, f"{exc.__class__.__name__}: {exc}")

    client.delete("smriti:events:recent")


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
