"""The workflow-tier write-through: appending a turn or an artifact event
through the real call sites lands in Redis, keyed by student_id + session_id,
not just in whatever in-process state the caller happens to hold.

Needs a local Redis on localhost:6379 (`redis-server --daemonize yes`).

    .venv/bin/python -m tests.test_short_term_writethrough
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from app.auth import load_env

load_env()

from app.agents.brain import _record
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
    await short_term.clear_session(session_id, "demo_student")

    ctx = _FakeToolContext()
    ctx.state["session_id"] = session_id
    ctx.state["student_id"] = "demo_student"
    ctx.state["turn_buffer"] = []
    await _record(session_id, "demo_student", "why 45 degrees?", "because sin(2θ) peaks there", ctx)

    turns = await short_term.get_turn_buffer(session_id, "demo_student")
    check("a recorded turn lands in Redis", len(turns) == 2, repr(turns))
    check("student half is first", turns[0]["role"] == "student" if turns else False)
    check("tutor half is second", turns[1]["role"] == "tutor" if len(turns) > 1 else False)

    result = await log_artifact_evidence("discovered_optimum", "art_1", ctx)
    check("log_artifact_evidence still returns its ack", result == {"logged": True}, repr(result))

    await short_term.clear_session(session_id, "demo_student")


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
