"""SpecialistRunner.run_turn() strips markup before returning -- the same
protection brain.py's _speakable() gives TutorAgent's replies today,
needed here because brain.py is retired in a later task with nothing else
replacing it.

    NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_specialist_runner_speakable
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from app.auth import configure, load_env

load_env()
configure()

from google.adk.agents import LlmAgent  # noqa: E402

from app.agents.specialist_runner import SpecialistRunner  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def _build_latex_agent() -> LlmAgent:
    from app import config

    return LlmAgent(
        name="LatexAgent",
        model=config.reasoning_model(),
        mode=None,
        instruction=(
            "Reply with EXACTLY this text and nothing else, verbatim, "
            "including the dollar signs and backslashes: "
            "$R = u^2 \\sin(2\\theta) / g$"
        ),
    )


async def run() -> None:
    runner = SpecialistRunner("test-speakable-app", _build_latex_agent)
    session_id = f"test_speakable_{uuid.uuid4().hex[:8]}"
    reply = await runner.run_turn(session_id, "demo_student", "say the formula")

    check("no dollar signs reach the caller", "$" not in reply, repr(reply))
    check("no backslashes reach the caller", "\\" not in reply, repr(reply))
    check("the reply is not empty after stripping", len(reply.strip()) > 0, repr(reply))


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
