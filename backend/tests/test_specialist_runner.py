"""SpecialistRunner: one Runner+session-bootstrap helper, shared by every
specialist agent, instead of each one hand-rolling its own.

    .venv/bin/python -m tests.test_specialist_runner
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from app.auth import configure, load_env

load_env()
configure()

from google.adk.agents import LlmAgent  # noqa: E402

from app import config  # noqa: E402
from app.agents.specialist_runner import SpecialistRunner, recent_transcript  # noqa: E402
from app.memory import short_term  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def _build_echo_agent() -> LlmAgent:
    return LlmAgent(
        name="EchoAgent",
        model=config.reasoning_model(),
        mode=None,
        instruction="Reply with exactly the words: acknowledged.",
    )


async def run() -> None:
    runner = SpecialistRunner("test-specialist-app", _build_echo_agent)
    session_id = f"test_specialist_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"

    reply = await runner.run_turn(session_id, student_id, "say the word")
    check("run_turn returns real text", "acknowledged" in reply.lower(), repr(reply))

    # A second call against the same session_id must not re-create the
    # session (the whole point of _known / _ensure_session).
    reply2 = await runner.run_turn(session_id, student_id, "say it again")
    check("a second turn against the same session works", "acknowledged" in reply2.lower(), repr(reply2))

    # recent_transcript
    await short_term.append_turn(session_id, student_id, {"turn": 1, "role": "student", "text": "hi", "concept_id": None, "artifact_id": None})
    await short_term.append_turn(session_id, student_id, {"turn": 2, "role": "tutor", "text": "hello", "concept_id": None, "artifact_id": None})
    text = await recent_transcript(session_id, student_id, n=10)
    check("recent_transcript includes both turns", "hi" in text and "hello" in text, repr(text))

    empty = await recent_transcript(f"nothing_{uuid.uuid4().hex[:8]}", student_id, n=10)
    check("recent_transcript degrades gracefully with no history", "No prior" in empty, repr(empty))

    await short_term.clear_session(session_id, student_id)


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
