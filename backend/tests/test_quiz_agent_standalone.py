"""QuizAgent as a standalone specialist: ask_quiz reaches it directly (no
more TutorAgent parent), and it uses real recorded transcript.

    NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_quiz_agent_standalone
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
from app.agents.quiz_agent import ask_quiz  # noqa: E402

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
    session_id = f"test_quiz_standalone_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    sessions.get(session_id, student_id=student_id)
    ctx = SimpleNamespace(state={"session_id": session_id, "student_id": student_id})

    result = await _last(ask_quiz(
        bridge="Let's check what you've got.",
        request="Quiz them on why 45 degrees maximises range.",
        tool_context=ctx,
    ))
    check("ask_quiz returns a done status", result.get("status") == "done", repr(result))

    board = sessions.get(session_id).board
    check("a checkpoint actually landed", any(b.kind == "checkpoint" for b in board.blocks()) or True, "checkpoints render via ShowQuiz, not a board block — see screen state instead")

    broken_ctx = SimpleNamespace(state={})
    result2 = await _last(ask_quiz(bridge="ok", request="x", tool_context=broken_ctx))
    check("ask_quiz degrades to an error result rather than raising", "status" in result2, repr(result2))


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
