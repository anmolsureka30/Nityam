"""delegate() opens its own span (`delegate.{label}`) BEFORE creating the
task that runs a specialist's turn, so that task inherits it as parent
context — this is what makes delegate()'s own published events (busy,
no-session error, and the final done/error) share one trace_id with
whatever the specialist's own turn publishes internally (its own
function-call/function-response ToolCallEvents, and any MemoryEvent it
triggers), instead of the delegation's own events always landing with
trace_id=None while the specialist's landed with a real one.

Why this needs its own test rather than trusting the wiring test
(test_tool_call_wiring.py): asyncio.create_task() copies the current
contextvars context at creation time, and changes made *inside* that copy
never propagate back to the creator. That means the mechanism only works if
the span is opened in delegate() itself, before create_task() runs -- opening
it anywhere else (e.g. only inside _run_turn_uncapped, as an earlier version
of this code did) leaves delegate()'s own publishes with trace_id=None even
though the specialist's own turn gets a real one, landing the two halves of
one delegation in two different Observatory trace groups. The busy/
no-session cases below prove every one of delegate()'s own publishes gets a
real, non-None trace_id; the happy-path case (with a fake specialist Runner
that opens its own nested span exactly like _run_turn_uncapped does) proves
the specialist's internal event and delegate()'s own final "done" event
share the identical trace_id.

Needs local Redis (same requirement as tests/test_memory_store_events.py).

    .venv/bin/python -m tests.test_delegate_trace_correlation
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from types import SimpleNamespace

import redis as redis_sync

from app.auth import load_env

load_env()

from app import config, tracing  # noqa: E402
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


async def _wait_for_tool_call_events(client, min_count: int, timeout: float = 2.0) -> list[dict]:
    """Publishing happens in a fire-and-forget asyncio.create_task nobody
    awaits, so poll rather than assume it already landed."""
    deadline = time.monotonic() + timeout
    while True:
        events = _read_tool_call_events(client)
        if len(events) >= min_count or time.monotonic() >= deadline:
            return events
        await asyncio.sleep(0.02)


class _FakeSpecialistRunner:
    """Stands in for a real SpecialistRunner. Its run_turn deliberately
    mirrors _run_turn_uncapped's own shape (a nested span, a specialist's
    own function-call/function-response pair published via
    _log_tool_activity) so this test exercises the REAL context-propagation
    mechanism — asyncio.create_task copying delegate()'s active span into
    this coroutine's task at creation time — rather than asserting against a
    mock that assumes the mechanism works."""

    def __init__(self, session_id: str, student_id: str) -> None:
        self.session_id = session_id
        self.student_id = student_id

    async def run_turn(self, session_id: str, student_id: str, message: str) -> str:
        with tracing.tracer.start_as_current_span("fake_specialist.turn"):
            specialist_runner._log_tool_activity(
                "board", _fake_call_event("search_grounding", "call-happy", {"q": "x"}),
                session_id, student_id,
            )
            await asyncio.sleep(0.01)
            specialist_runner._log_tool_activity(
                "board", _fake_response_event("search_grounding", "call-happy", {"chunks": 1}),
                session_id, student_id,
            )
        return "the answer"


def run() -> None:
    tracing.setup_tracing()
    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)

    # --- busy path: every one of delegate()'s own publishes must get a real
    # trace_id now, even though no specialist task ever runs in this branch.
    client.delete("smriti:events:recent")

    async def _busy_case():
        specialist_runner._in_flight.add(("s-busy", "board"))
        try:
            async for _ in specialist_runner.delegate(
                "board", runner=None, request="x",
                tool_context=SimpleNamespace(state={"session_id": "s-busy", "student_id": "stu-busy"}),
                transcript_n=1, done_default="done", error_text="error",
            ):
                pass
        finally:
            specialist_runner._in_flight.discard(("s-busy", "board"))
        return await _wait_for_tool_call_events(client, min_count=1)

    busy_events = asyncio.run(_busy_case())
    check("busy path published one event", len(busy_events) == 1, repr(busy_events))
    check("busy event's own trace_id is non-None (span now wraps this path)",
          bool(busy_events) and busy_events[0]["trace_id"] is not None, repr(busy_events))

    client.delete("smriti:events:recent")

    # --- no-session path: same claim, the other early-out.
    async def _no_session_case():
        async for _ in specialist_runner.delegate(
            "quiz", runner=None, request="x",
            tool_context=SimpleNamespace(state={}),
            transcript_n=1, done_default="done", error_text="error",
        ):
            pass
        return await _wait_for_tool_call_events(client, min_count=1)

    error_events = asyncio.run(_no_session_case())
    check("no-session path published one event", len(error_events) == 1, repr(error_events))
    check("no-session event's own trace_id is non-None",
          bool(error_events) and error_events[0]["trace_id"] is not None, repr(error_events))

    client.delete("smriti:events:recent")

    # --- happy path: the actual correlation claim. delegate() creates
    # runner.run_turn's task WHILE its own span is active; the fake
    # runner's nested span (opened inside that task) must come up as a
    # CHILD sharing the same trace_id, exactly like _run_turn_uncapped's
    # real nested span does.
    async def _happy_case():
        runner = _FakeSpecialistRunner("s-happy", "stu-happy")
        async for _ in specialist_runner.delegate(
            "board", runner=runner, request="explain something",
            tool_context=SimpleNamespace(state={"session_id": "s-happy", "student_id": "stu-happy"}),
            transcript_n=1, done_default="done", error_text="error",
        ):
            pass
        return await _wait_for_tool_call_events(client, min_count=3)

    happy_events = asyncio.run(_happy_case())
    check("happy path published 3 events (specialist started+done, delegation done)",
          len(happy_events) == 3, repr(happy_events))

    delegation_done = next(
        (e for e in happy_events if e["tool_name"] == "ask_board" and e["phase"] == "done"), None
    )
    specialist_events = [e for e in happy_events if e["tool_name"] == "search_grounding"]

    check("delegation's own final done event was published", delegation_done is not None, repr(happy_events))
    check("delegation's own final done event has a real (non-None) trace_id",
          delegation_done is not None and delegation_done["trace_id"] is not None)
    check("the specialist's own internal events were published", len(specialist_events) == 2, repr(specialist_events))
    check("every specialist-internal event has a real (non-None) trace_id",
          all(e["trace_id"] is not None for e in specialist_events), repr(specialist_events))
    check(
        "the specialist's internal trace_id matches the delegation's own trace_id "
        "-- one delegation, one Observatory trace group",
        delegation_done is not None
        and all(e["trace_id"] == delegation_done["trace_id"] for e in specialist_events),
        repr((delegation_done, specialist_events)),
    )

    client.delete("smriti:events:recent")


def main() -> int:
    run()
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
