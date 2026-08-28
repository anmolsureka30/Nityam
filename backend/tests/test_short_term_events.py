"""append_turn/append_artifact_event/get_turn_buffer/clear_session each
publish a workflow-tier MemoryEvent, carrying the real session_id/student_id
straight from their own arguments (no context var needed here).

    .venv/bin/python -m tests.test_short_term_events
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
from app.memory import short_term  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


async def run() -> None:
    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    client.delete("smriti:events:recent")

    session_id = f"test_short_term_events_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"

    await short_term.append_turn(session_id, student_id, {"turn": 1, "role": "student", "text": "hi", "concept_id": None, "artifact_id": None})
    await short_term.get_turn_buffer(session_id, student_id)
    await short_term.clear_session(session_id, student_id)

    raw = client.lrange("smriti:events:recent", 0, -1)
    events = [json.loads(r) for r in raw]
    by_fn = {e["source_fn"]: e for e in events}

    check("append_turn published a workflow write event", "append_turn" in by_fn, repr(list(by_fn)))
    check("get_turn_buffer published a workflow read event", "get_turn_buffer" in by_fn, repr(list(by_fn)))
    check("clear_session published a workflow write event", "clear_session" in by_fn, repr(list(by_fn)))
    if "append_turn" in by_fn:
        e = by_fn["append_turn"]
        check("append_turn's event carries the real session/student ids", (
            e["session_id"] == session_id and e["student_id"] == student_id
        ), repr(e))

    client.delete("smriti:events:recent")


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
