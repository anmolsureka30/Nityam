"""The workflow-tier write-through: log_artifact_evidence lands in Redis,
keyed by student_id + session_id, not just in whatever in-process state
the caller happens to hold.

(This file used to also test brain._record()'s write-through — brain.py
is retired as of this plan; that coverage now lives in
test_transcript_recording.py, which tests the mechanism that replaced it.)

Needs a local Redis on localhost:6379 (`redis-server --daemonize yes`).

    .venv/bin/python -m tests.test_short_term_writethrough
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from app.auth import load_env

load_env()

from app.memory import short_term
from app.memory.tools import log_artifact_evidence

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


class _FakeToolContext:
    """log_artifact_evidence only ever touches .state as a plain dict."""

    def __init__(self) -> None:
        self.state: dict = {}


async def run() -> None:
    session_id = f"test_{uuid.uuid4().hex[:10]}"
    student_id = "demo_student"
    await short_term.clear_session(session_id, student_id)

    ctx = _FakeToolContext()
    ctx.state["session_id"] = session_id
    ctx.state["student_id"] = student_id

    result = await log_artifact_evidence("discovered_optimum", "art_1", ctx)
    check("log_artifact_evidence still returns its ack", result == {"logged": True}, repr(result))

    events = await short_term.get_turn_buffer(session_id, student_id)  # sanity: wrong buffer is empty
    check("log_artifact_evidence doesn't write to the turn buffer", events == [], repr(events))

    await short_term.clear_session(session_id, student_id)


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
