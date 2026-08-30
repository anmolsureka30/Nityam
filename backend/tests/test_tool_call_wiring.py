"""_log_tool_activity and delegate() publish real ToolCallEvents at the
points identified in the plan: a specialist's own function_call/
function_response pair (both phases), and delegate()'s error/busy early-outs
(the "done" path is exercised for real by
backend/tests/test_artifact_agent_ask.py's own end-to-end delegate() call,
which is a real Gemini call this file's Redis-only style intentionally
avoids duplicating).

Needs local Redis (same requirement as tests/test_memory_store_events.py).

    .venv/bin/python -m tests.test_tool_call_wiring
"""
from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace

import redis as redis_sync

from app.auth import load_env

load_env()

from app import config  # noqa: E402
from app.agents import specialist_runner  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def _fake_call_event(name: str, call_id: str, args: dict) -> SimpleNamespace:
    call = SimpleNamespace(name=name, id=call_id, args=args)
    part = SimpleNamespace(function_call=call, function_response=None)
    return SimpleNamespace(content=SimpleNamespace(parts=[part]))


def _fake_response_event(name: str, call_id: str, response: dict) -> SimpleNamespace:
    resp = SimpleNamespace(name=name, id=call_id, response=response)
    part = SimpleNamespace(function_call=None, function_response=resp)
    return SimpleNamespace(content=SimpleNamespace(parts=[part]))


def _read_tool_call_events(client) -> list[dict]:
    raw = client.lrange("smriti:events:recent", 0, -1)
    events = [json.loads(r) for r in raw]
    return [e for e in events if e.get("kind") == "tool_call"]


def run() -> None:
    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    client.delete("smriti:events:recent")

    specialist_runner._log_tool_activity(
        "board", _fake_call_event("search_grounding", "call-1", {"q": "projectile motion"}),
        "s1", "stu1",
    )
    specialist_runner._log_tool_activity(
        "board", _fake_response_event("search_grounding", "call-1", {"chunks": 3}),
        "s1", "stu1",
    )

    events = _read_tool_call_events(client)
    check("two events published (started + done)", len(events) == 2, repr(events))
    started = next((e for e in events if e["phase"] == "started"), None)
    done = next((e for e in events if e["phase"] == "done"), None)
    check("started event has the right actor/tool_name", started is not None and started["actor"] == "board_agent" and started["tool_name"] == "search_grounding")
    check("done event has a computed duration_ms", done is not None and isinstance(done["duration_ms"], int))

    client.delete("smriti:events:recent")

    async def _busy_case():
        specialist_runner._in_flight.add(("s2", "board"))
        try:
            async for _ in specialist_runner.delegate(
                "board", runner=None, request="x",
                tool_context=SimpleNamespace(state={"session_id": "s2", "student_id": "stu2"}),
                transcript_n=1, done_default="done", error_text="error",
            ):
                pass
        finally:
            specialist_runner._in_flight.discard(("s2", "board"))

    asyncio.run(_busy_case())
    busy_events = _read_tool_call_events(client)
    check("busy delegation published one busy event", len(busy_events) == 1, repr(busy_events))
    check("busy event names the top-level ask_ tool", busy_events[0]["tool_name"] == "ask_board")
    check("busy event phase is busy", busy_events[0]["phase"] == "busy")

    client.delete("smriti:events:recent")

    async def _no_session_case():
        async for _ in specialist_runner.delegate(
            "quiz", runner=None, request="x",
            tool_context=SimpleNamespace(state={}),
            transcript_n=1, done_default="done", error_text="error",
        ):
            pass

    asyncio.run(_no_session_case())
    error_events = _read_tool_call_events(client)
    check("missing session/student id publishes one error event", len(error_events) == 1, repr(error_events))
    check("error event names ask_quiz", error_events[0]["tool_name"] == "ask_quiz")

    client.delete("smriti:events:recent")


def main() -> int:
    run()
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
