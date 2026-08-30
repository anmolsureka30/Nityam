"""build_tool_call_event/publish_tool_call_event publish exactly one
correctly-shaped ToolCallEvent, distinguishable from a MemoryEvent by its
"kind" field, onto the same channel/list MemoryEvent already uses.

Needs local Redis (same requirement as tests/test_memory_store_events.py).

    .venv/bin/python -m tests.test_tool_call_events
"""
from __future__ import annotations

import json
import sys

import redis as redis_sync

from app.auth import load_env

load_env()

from app import config  # noqa: E402
from app.memory import instrumentation  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def run() -> None:
    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    client.delete("smriti:events:recent")

    event = instrumentation.build_tool_call_event(
        actor="board_agent",
        tool_name="search_grounding",
        phase="done",
        session_id="s1",
        student_id="stu1",
        args_summary="looking for projectile motion",
        result_summary="3 chunks found",
        duration_ms=842,
    )
    check("kind is tool_call", event.kind == "tool_call")

    instrumentation.publish_tool_call_event(event)

    raw = client.lrange("smriti:events:recent", 0, -1)
    check("exactly one event landed in the list", len(raw) == 1, repr(raw))
    body = json.loads(raw[0])
    check("published JSON carries kind=tool_call", body.get("kind") == "tool_call")
    check("actor round-trips", body.get("actor") == "board_agent")
    check("tool_name round-trips", body.get("tool_name") == "search_grounding")
    check("phase round-trips", body.get("phase") == "done")
    check("duration_ms round-trips", body.get("duration_ms") == 842)
    check("args_summary is truncated-or-kept", body.get("args_summary") == "looking for projectile motion")

    long_event = instrumentation.build_tool_call_event(
        actor="voice_agent", tool_name="ask_board", phase="started",
        session_id="s1", student_id="stu1", args_summary="x" * 300,
    )
    check("args_summary over 200 chars is truncated", len(long_event.args_summary) == 200)

    client.delete("smriti:events:recent")


def main() -> int:
    run()
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
