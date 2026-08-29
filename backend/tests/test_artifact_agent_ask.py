"""ArtifactAgent as a standalone specialist reached via ask_artifact: the
whole generate-validate-mount pipeline runs to completion inside one turn,
with no separate detached-task layer needed any more.

    NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_artifact_agent_ask
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
from app.agents.artifact_agent import ask_artifact  # noqa: E402

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
    session_id = f"test_artifact_ask_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    sessions.get(session_id, student_id=student_id)
    ctx = SimpleNamespace(state={"session_id": session_id, "student_id": student_id})

    result = await _last(ask_artifact(
        bridge="Let me build that for you.",
        request="An interactive simulation of projectile range vs launch angle.",
        tool_context=ctx,
    ))
    check("ask_artifact returns a done status", result.get("status") == "done", repr(result))
    check("ask_artifact returns a summary", bool(result.get("summary")), repr(result))

    board = sessions.get(session_id).board
    check("an artifact block actually landed", any(b.kind == "artifact" for b in board.blocks()), repr([b.kind for b in board.blocks()]))

    broken_ctx = SimpleNamespace(state={})
    result2 = await _last(ask_artifact(bridge="ok", request="x", tool_context=broken_ctx))
    check("ask_artifact degrades to an error result rather than raising", "status" in result2, repr(result2))


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
