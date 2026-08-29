"""SpecialistRunner: one Runner+session-bootstrap helper, shared by every
specialist agent, instead of each one hand-rolling its own.

    .venv/bin/python -m tests.test_specialist_runner
"""
from __future__ import annotations

import asyncio
import logging
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


def _ping(word: str) -> dict:
    """Echo a word back.

    Args:
        word: Anything.

    Returns:
        dict with "pong".
    """
    return {"pong": word}


def _build_tool_agent() -> LlmAgent:
    return LlmAgent(
        name="ToolAgent",
        model=config.reasoning_model(),
        mode=None,
        instruction="Call the ping tool with the word 'hello', then reply with exactly: done.",
        tools=[_ping],
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
        chunks = [c async for c in
                  board_agent.ask_board("write something", ctx)]
        # The LAST chunk is the outcome; the earlier ones are the keep-talking
        # responses. An escaping exception here would be delivered to the
        # student as nothing at all, so a timeout has to arrive as something
        # sayable.
        result = chunks[-1]
        check("a timed-out ask_board ends in an error chunk, not a raise",
              result.get("status") == "error", repr(result))
        check("with something sayable in it", bool(result.get("summary")), repr(result))
    finally:
        board_agent._RUNNER._run_turn_uncapped = real_uncapped
        board_agent._RUNNER._timeout_s = real_timeout


async def run_tracing() -> None:
    """A specialist's own tool calls must be visible in the logs -- before
    this, search_grounding, get_dpm, strike_block and everything else a
    specialist calls internally was invisible even in a full session log,
    since each specialist runs several frames away from main.py's own
    event stream (see specialist_runner._log_tool_activity)."""
    runner = SpecialistRunner("test-tracing-app", _build_tool_agent)
    session_id = f"test_tracing_{uuid.uuid4().hex[:8]}"

    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    logger = logging.getLogger("nityam.specialist_runner")
    handler = _Capture()
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        await runner.run_turn(session_id, "demo_student", "please ping")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    calls = [r for r in records if "test-tracing-app" in r and "_ping(" in r]
    check("the specialist's own tool call was logged", bool(calls), repr(records))
    results = [r for r in records if "test-tracing-app" in r and "pong" in r]
    check("the specialist's own tool result was logged", bool(results), repr(records))


async def run_keep_talking() -> None:
    """A slow specialist must produce progress chunks that make her speak, and
    they must stop the instant the real result is ready.

    This replaces the old nudge test. The mechanism changed underneath: there
    is no sink and no timer any more. `delegate` is an async generator, ADK
    routes it through its streaming path, and every yield becomes a
    `send_tool_response` whose own `scheduling` decides whether she talks.
    So what is asserted is the SHAPE OF THE STREAM, which is the thing the
    Live API actually reacts to.
    """
    from google.genai import types

    from app.agents import board_agent, specialist_runner

    real_interval = specialist_runner.KEEP_TALKING_INTERVAL_S
    specialist_runner.KEEP_TALKING_INTERVAL_S = 0.05

    async def _slow(session_id: str, student_id: str, message: str) -> str:
        await asyncio.sleep(0.3)
        return "acknowledged."

    real_uncapped = board_agent._RUNNER._run_turn_uncapped
    board_agent._RUNNER._run_turn_uncapped = _slow  # type: ignore[method-assign]
    try:
        ctx = SimpleNamespace(
            state={"session_id": f"test_kt_{uuid.uuid4().hex[:8]}",
                   "student_id": "demo_student"}
        )
        chunks = [c async for c in
                  board_agent.ask_board("write something", ctx)]

        check("a slow turn still ends with the real result",
              "acknowledged" in str(chunks[-1].get("summary", "")), repr(chunks[-1]))
        check("and the last chunk is the outcome, not a progress note",
              chunks[-1].get("status") == "done", repr(chunks[-1]))

        progress = [c for c in chunks if isinstance(c, types.FunctionResponse)]
        check("progress chunks were emitted while it was slow",
              len(progress) >= 2, f"{len(progress)} of {len(chunks)}")

        # The opening one is context for the turn she is already taking; ADK's
        # own synthetic pending response is what starts her talking.
        check("the first chunk is SILENT — context for the turn already running",
              progress[0].scheduling == types.FunctionResponseScheduling.SILENT,
              str(progress[0].scheduling))
        # These are the ones that keep her going. SILENT here was measured at
        # 23s of dead air; see tests/probe_live_streaming_tool.py.
        check("every later progress chunk is WHEN_IDLE — what makes her speak",
              all(c.scheduling == types.FunctionResponseScheduling.WHEN_IDLE
                  for c in progress[1:]),
              str([str(c.scheduling) for c in progress[1:]]))
        check("progress chunks count the seconds, so she does not repeat herself",
              all("seconds" in c.response for c in progress))
    finally:
        board_agent._RUNNER._run_turn_uncapped = real_uncapped
        specialist_runner.KEEP_TALKING_INTERVAL_S = real_interval


async def run_no_talking_over_the_student() -> None:
    """A progress chunk must be SKIPPED while the student is speaking.

    WHEN_IDLE is defined against HER generation, not theirs — she can be idle
    while they are mid-sentence, and a chunk delivered then puts her straight
    over the top of them.
    """
    from google.genai import types

    from app.agents import board_agent, specialist_runner

    real_interval = specialist_runner.KEEP_TALKING_INTERVAL_S
    specialist_runner.KEEP_TALKING_INTERVAL_S = 0.05
    session_id = f"test_talk_{uuid.uuid4().hex[:8]}"

    async def _slow(session_id_: str, student_id: str, message: str) -> str:
        await asyncio.sleep(0.3)
        return "acknowledged."

    real_uncapped = board_agent._RUNNER._run_turn_uncapped
    board_agent._RUNNER._run_turn_uncapped = _slow  # type: ignore[method-assign]
    try:
        specialist_runner.heard_student(session_id)   # they are talking, now
        ctx = SimpleNamespace(
            state={"session_id": session_id, "student_id": "demo_student"}
        )
        chunks = [c async for c in
                  board_agent.ask_board("write something", ctx)]
        prompting = [c for c in chunks
                     if isinstance(c, types.FunctionResponse)
                     and c.scheduling
                     == types.FunctionResponseScheduling.WHEN_IDLE]
        check("nothing prompts her to speak while the student is talking",
              not prompting, f"{len(prompting)} chunk(s) would have")
        check("but the real result still arrives",
              chunks[-1].get("status") == "done", repr(chunks[-1]))
    finally:
        board_agent._RUNNER._run_turn_uncapped = real_uncapped
        specialist_runner.KEEP_TALKING_INTERVAL_S = real_interval
        specialist_runner._last_heard.pop(session_id, None)


async def run_no_prompting_while_she_talks() -> None:
    """She must not be prompted to speak while she is already speaking.

    The regression this guards. Keep-talking chunks fired on a pure timer, so
    an 11-second delegation produced five of them and each is an instruction
    to say something. With nothing new to say she asked the same question five
    times in five phrasings — from one real session:

        "...which side of the triangle is adjacent to this angle?"
        "...which side of the triangle is next to that angle?"
        "...Which side of the triangle is adjacent to this angle?"

    A prompt is only ever needed into SILENCE. If she spoke a moment ago the
    delegation is producing a lesson, not dead air.
    """
    from google.genai import types

    from app.agents import board_agent, specialist_runner

    real_interval = specialist_runner.KEEP_TALKING_INTERVAL_S
    specialist_runner.KEEP_TALKING_INTERVAL_S = 0.05
    session_id = f"test_talky_{uuid.uuid4().hex[:8]}"

    async def _slow(session_id_: str, student_id: str, message: str) -> str:
        # Keep "she just spoke" true for the whole delegation, the way a tutor
        # mid-explanation would.
        for _ in range(6):
            specialist_runner.she_spoke(session_id)
            await asyncio.sleep(0.05)
        return "acknowledged."

    real_uncapped = board_agent._RUNNER._run_turn_uncapped
    board_agent._RUNNER._run_turn_uncapped = _slow  # type: ignore[method-assign]
    try:
        ctx = SimpleNamespace(
            state={"session_id": session_id, "student_id": "demo_student"}
        )
        chunks = [c async for c in board_agent.ask_board("write something", ctx)]
        prompting = [c for c in chunks
                     if isinstance(c, types.FunctionResponse)
                     and c.scheduling
                     == types.FunctionResponseScheduling.WHEN_IDLE]
        check("nothing prompts her to speak while she is already talking",
              not prompting, f"{len(prompting)} chunk(s) would have")
        check("and the real result still arrives",
              chunks[-1].get("status") == "done", repr(chunks[-1]))
    finally:
        board_agent._RUNNER._run_turn_uncapped = real_uncapped
        specialist_runner.KEEP_TALKING_INTERVAL_S = real_interval
        specialist_runner.forget_session(session_id)


async def run_no_double_delegation() -> None:
    """The same specialist twice while one is outstanding must be refused.

    Not hygiene: ADK registers streaming-tool tasks by TOOL NAME rather than
    call id, so the second call overwrites the first's entry and orphans it.
    """
    from app.agents import board_agent, specialist_runner

    session_id = f"test_dup_{uuid.uuid4().hex[:8]}"
    key = (session_id, "board")
    specialist_runner._in_flight.add(key)
    try:
        ctx = SimpleNamespace(
            state={"session_id": session_id, "student_id": "demo_student"}
        )
        chunks = [c async for c in board_agent.ask_board("again", ctx)]
        check("a second concurrent ask_board is refused",
              chunks[-1].get("status") == "busy", repr(chunks[-1]))
        check("and says something rather than nothing",
              bool(chunks[-1].get("summary")), repr(chunks[-1]))
    finally:
        specialist_runner._in_flight.discard(key)


def main() -> int:
    asyncio.run(run())
    asyncio.run(run_timeout())
    asyncio.run(run_tracing())
    asyncio.run(run_keep_talking())
    asyncio.run(run_no_talking_over_the_student())
    asyncio.run(run_no_prompting_while_she_talks())
    asyncio.run(run_no_double_delegation())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
