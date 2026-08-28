"""The instrumentation decorator publishes a MemoryEvent to Redis without
changing what the wrapped function returns, and never raises even if Redis
is unreachable.

Needs a local Redis on localhost:6379 (`redis-server --daemonize yes`).

    .venv/bin/python -m tests.test_memory_instrumentation
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

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def _ids(args, kwargs, result):
    return args[0], args[1]


@instrumentation.emit_memory_event(
    tier="workflow", record_type="turn_buffer", operation="write", extract_ids=_ids,
)
def _sample_write(session_id: str, student_id: str, value: int) -> int:
    return value * 2


async def run() -> None:
    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    client.delete("smriti:events:recent")

    session_id = f"test_instr_{uuid.uuid4().hex[:8]}"
    result = _sample_write(session_id, "demo_student", 21)
    check("the wrapped function's return value is unchanged", result == 42, repr(result))

    raw = client.lrange("smriti:events:recent", 0, -1)
    check("exactly one event was published", len(raw) == 1, repr(raw))
    if raw:
        event = json.loads(raw[0])
        check("session_id round-trips", event["session_id"] == session_id, event["session_id"])
        check("student_id round-trips", event["student_id"] == "demo_student", event["student_id"])
        check("tier/record_type/operation are set", (
            event["tier"] == "workflow" and event["record_type"] == "turn_buffer" and event["operation"] == "write"
        ), repr(event))

    instrumentation.set_session_context("ctx_session_1")
    check("session context round-trips", instrumentation.get_session_context() == "ctx_session_1")
    instrumentation.set_session_context(None)

    client.delete("smriti:events:recent")


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
