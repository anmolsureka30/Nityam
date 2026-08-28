"""SpecialistRunner: one Runner+session-bootstrap helper, shared by every
specialist agent, instead of each one hand-rolling its own.

    .venv/bin/python -m tests.test_specialist_runner
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from types import SimpleNamespace

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


async def run_timeout() -> None:
    """A hung specialist turn must raise, not hang forever.

    The retired brain.py capped its delegated call at 70s. Without a cap
    there is no failure mode left that is merely slow: a WHEN_IDLE tool
    delivers nothing at all until its coroutine returns, and VoiceAgent will
    not re-issue a call that is still outstanding — so a specialist that
    never comes back is not a late answer, it is silence for the rest of the
    session, with no error anywhere.

    Runs against a deliberately-slow stand-in with a 0.1s cap rather than
    waiting out the real 70.
    """
    runner = SpecialistRunner("test-timeout-app", _build_echo_agent, timeout_s=0.1)

    async def _hang(session_id: str, student_id: str, message: str) -> str:
        await asyncio.sleep(30)
        return "never reached"

    runner._run_turn_uncapped = _hang  # type: ignore[method-assign]

    started = asyncio.get_running_loop().time()
    try:
        await runner.run_turn("s", "demo_student", "please hang")
        check("a hung turn raises instead of hanging", False, "returned normally")
    except asyncio.TimeoutError:
        elapsed = asyncio.get_running_loop().time() - started
        check("a hung turn raises TimeoutError", True)
        check("and does so promptly, at the cap", elapsed < 5, f"{elapsed:.2f}s")
    except Exception as exc:  # noqa: BLE001
        check("a hung turn raises TimeoutError", False, repr(exc))

    check(
        "TimeoutError is an ordinary Exception, so each ask_* handler catches it",
        isinstance(asyncio.TimeoutError(), Exception),
    )

    # The whole chain, for real: a timing-out runner reaching ask_board's own
    # `except Exception` and coming back as the error-shaped dict the voice
    # layer knows how to say out loud -- not an escaping exception, which on
    # the WHEN_IDLE path is delivered to the student as nothing at all.
    from app.agents import board_agent

    real_uncapped = board_agent._RUNNER._run_turn_uncapped
    real_timeout = board_agent._RUNNER._timeout_s
    board_agent._RUNNER._run_turn_uncapped = _hang  # type: ignore[method-assign]
    board_agent._RUNNER._timeout_s = 0.1
    try:
        ctx = SimpleNamespace(
            state={"session_id": f"test_to_{uuid.uuid4().hex[:8]}",
                   "student_id": "demo_student"}
        )
        result = await board_agent.ask_board("one sec", "write something", ctx)
        check("a timed-out ask_board returns an error dict, not a raise",
              result.get("status") == "error", repr(result))
        check("with something sayable in it", bool(result.get("summary")), repr(result))
    finally:
        board_agent._RUNNER._run_turn_uncapped = real_uncapped
        board_agent._RUNNER._timeout_s = real_timeout


def main() -> int:
    asyncio.run(run())
    asyncio.run(run_timeout())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
