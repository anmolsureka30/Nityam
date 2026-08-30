"""publish_tool_call_event_async's started/done pairs must land in
smriti:events:recent in the order they were called, not whichever
independent connection happens to finish its handshake first.

Regression test for the final-review re-review's own empirical finding:
fire-and-forget asyncio.create_task per publish reordered a started/done
pair roughly 1 time in 3 against local Redis, because each publish opened
its own fresh async connection and raced. Fixed with a module-level
asyncio.Lock serializing the actual Redis writes.

    .venv/bin/python -m tests.test_tool_call_publish_ordering
"""
from __future__ import annotations

import asyncio
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


async def run() -> None:
    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    client.delete("smriti:events:recent")

    ROUNDS = 20
    for i in range(ROUNDS):
        started = instrumentation.build_tool_call_event(
            actor="board_agent", tool_name="search_grounding", phase="started",
            session_id=f"order_test_{i}", student_id="stu1",
        )
        done = instrumentation.build_tool_call_event(
            actor="board_agent", tool_name="search_grounding", phase="done",
            session_id=f"order_test_{i}", student_id="stu1", result_summary="ok",
        )
        # Mirrors the real call sites: two independent fire-and-forget tasks,
        # "started" created strictly before "done" in application-code order.
        task_a = asyncio.get_running_loop().create_task(instrumentation.publish_tool_call_event_async(started))
        task_b = asyncio.get_running_loop().create_task(instrumentation.publish_tool_call_event_async(done))
        await asyncio.gather(task_a, task_b)

    raw = client.lrange("smriti:events:recent", 0, -1)
    events = [json.loads(r) for r in raw]

    reordered = 0
    for i in range(ROUNDS):
        session_events = [e for e in events if e["session_id"] == f"order_test_{i}"]
        check(f"round {i}: both events published", len(session_events) == 2, repr(session_events))
        if len(session_events) == 2 and session_events[0]["phase"] != "started":
            reordered += 1

    check(f"zero reorderings across {ROUNDS} rounds", reordered == 0, f"{reordered} reordered")

    client.delete("smriti:events:recent")


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
