"""main.trace() must NOT publish a "done" ToolCallEvent for the four
ask_* delegation tools — specialist_runner.delegate() already publishes
their real done/error/busy events once the specialist actually finishes.

Regression test for the final-review re-review's own empirical finding:
ADK 2.8.0 sends a synthetic "results are pending" function_response for
these WHEN_IDLE async-generator tools (contrary to this codebase's own,
now-corrected comment claiming ADK sends nothing at all), which trace()
was publishing as a real "done" — showing every delegation completing
instantly in the Observatory, followed by a second, genuine "done" 10-30s
later. scroll_to/read_screen (genuinely not WHEN_IDLE) must still get a
real "done" published, since trace() is the only place their completion
is ever observable.

    .venv/bin/python -m tests.test_trace_delegation_done_suppressed
"""
from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace

import redis as redis_sync

from app.auth import load_env

load_env()

from app import config, main  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def _response_event(name: str, payload: dict) -> SimpleNamespace:
    response = SimpleNamespace(name=name, response=payload)
    part = SimpleNamespace(function_call=None, function_response=response)
    content = SimpleNamespace(parts=[part])
    return SimpleNamespace(
        content=content, author="VoiceAgent",
        output_transcription=None, input_transcription=None,
        partial=None, interrupted=False,
    )


async def _trace_and_wait() -> None:
    token = main._recording_context.set(("s_trace_test", "stu1"))
    try:
        main.trace(_response_event("ask_board", {"status": "The function is running asynchronously and the results are pending."}))
        main.trace(_response_event("scroll_to", {"ok": True}))
        # _publish_tool_call_bg fires each publish as its own background
        # task (create_task, never awaited by trace() itself) — give them
        # a moment to actually land in Redis before reading it back.
        await asyncio.sleep(0.5)
    finally:
        main._recording_context.reset(token)


def run() -> None:
    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    client.delete("smriti:events:recent")

    asyncio.run(_trace_and_wait())

    raw = client.lrange("smriti:events:recent", 0, -1)
    events = [json.loads(r) for r in raw]
    tool_names = [e["tool_name"] for e in events]

    check("ask_board's synthetic pending response publishes nothing", "ask_board" not in tool_names, repr(tool_names))
    check("scroll_to (not WHEN_IDLE) still publishes a real done event", "scroll_to" in tool_names, repr(tool_names))
    scroll_event = next((e for e in events if e["tool_name"] == "scroll_to"), None)
    check("scroll_to's event is phase=done", scroll_event is not None and scroll_event["phase"] == "done")

    client.delete("smriti:events:recent")


def main_() -> int:
    run()
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main_())
