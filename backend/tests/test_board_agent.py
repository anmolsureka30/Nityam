"""BoardAgent: given a request and recent transcript, writes real content
citing the actual grounding corpus, and ask_board never raises even when
its internals fail.

    NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_board_agent
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from types import SimpleNamespace

from app.auth import configure, load_env

load_env()
configure()

from app import sessions  # noqa: E402
from app.agents.board_agent import ask_board  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


async def _last(agen):
    """Drain a delegation and return its OUTCOME chunk.

    `ask_*` are async generators now, not coroutines: the earlier chunks are the
    keep-talking responses that stop her going silent while the specialist
    works, and the final one is the result. See
    app/agents/specialist_runner.delegate.
    """
    chunks = [c async for c in agen]
    return chunks[-1]


async def run() -> None:
    session_id = f"test_board_agent_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    sessions.get(session_id, student_id=student_id)
    ctx = SimpleNamespace(state={"session_id": session_id, "student_id": student_id})

    result = await _last(ask_board(
        request="Explain why maximum range happens at 45 degrees.",
        tool_context=ctx,
    ))
    check("ask_board returns a done status", result.get("status") == "done", repr(result))
    check("ask_board returns a summary", bool(result.get("summary")), repr(result))

    board = sessions.get(session_id).board
    check("something actually landed on the board", len(board.blocks()) > 1, repr([b.kind for b in board.blocks()]))

    # ask_board must never raise, even on a garbage request — it should
    # degrade to an error-shaped result (WHEN_IDLE swallows a raised
    # exception with no delivery to the model at all).
    broken_ctx = SimpleNamespace(state={})  # no session_id/student_id at all
    result2 = await _last(ask_board(request="x" * 10, tool_context=broken_ctx))
    check("ask_board degrades to an error result rather than raising", "status" in result2, repr(result2))


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
