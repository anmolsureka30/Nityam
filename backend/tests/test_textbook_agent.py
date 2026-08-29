"""TextbookAgent: fetches or places real textbook material, and ask_textbook
never raises even when the request can't be satisfied.

    NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_textbook_agent
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
from app.agents.textbook_agent import ask_textbook  # noqa: E402

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
    session_id = f"test_textbook_agent_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    sessions.get(session_id, student_id=student_id)
    ctx = SimpleNamespace(state={"session_id": session_id, "student_id": student_id})

    result = await _last(ask_textbook(
        bridge="One second, let me find that.",
        request="Show figure 3.14 from the textbook.",
        tool_context=ctx,
    ))
    check("ask_textbook returns a done status", result.get("status") == "done", repr(result))
    check("ask_textbook returns a summary", bool(result.get("summary")), repr(result))

    result2 = await _last(ask_textbook(
        bridge="Let me check.",
        request="Show figure 9.99, which does not exist.",
        tool_context=ctx,
    ))
    check("a figure that doesn't exist still returns a done result, not an error", result2.get("status") == "done", repr(result2))

    broken_ctx = SimpleNamespace(state={})
    result3 = await _last(ask_textbook(bridge="ok", request="x", tool_context=broken_ctx))
    check("ask_textbook degrades to an error result rather than raising", "status" in result3, repr(result3))


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
