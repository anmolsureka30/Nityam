"""Reaching TutorAgent from the voice loop.

## Why this file exists

`architecture.md` §2 specifies `VoiceAgent(sub_agents=[TutorAgent(mode='single_turn')])`,
verified against the installed ADK source. That verification was done by
*reading* the source, and it is correct about everything except one thing that
only shows up when you run it on the live path:

    RuntimeError: _enqueue_event called but _event_queue is not set.
                  Ensure the Runner initialises _event_queue on InvocationContext.

A `mode='single_turn'` sub-agent is executed by `workflow/_node_runner.py`, which
enqueues its events onto `InvocationContext._event_queue`. That queue is created
by `Runner`'s **run_async** machinery (`runners.py:595` and `:752`) and **not** by
`run_live` (`runners.py:1738`). So on the streaming path the delegation fails at
the first event, the tool returns an error string, and the tutor apologises to
the student about a technical hiccup — which is exactly what it did.

## What this does instead

TutorAgent runs in its **own Runner, through run_async**, invoked from an
ordinary async tool function. Nothing nested, nothing streaming, so nothing
touches the missing queue.

This is not a workaround with a cost — it is closer to what the architecture
wanted. `architecture.md` §2's "confirmed side benefit" was that TutorAgent
should execute as a normal invocation so guardrail callbacks
(`before_model_callback` and friends, which never fire under `run_live`) get
their full lifecycle. Running it under its own `run_async` is the most direct
way to get that, rather than a consequence of a delegation mechanism.

## Session continuity

One brain session per student session, keyed by the same id, so TutorAgent
accumulates conversation history across turns instead of waking up amnesiac
every time the voice layer asks it something. The board tools read `session_id`
out of `tool_context.state`, so that state is seeded at creation — a tool that
cannot find it would write to the wrong board silently.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import ToolContext
from google.genai import types

from app import logs, sessions
from app.agents.tutor_agent import build_tutor_agent

log = logging.getLogger("nityam.brain")

BRAIN_APP = "nityam-brain"

# How long the voice layer will wait. A reasoning turn with grounding, a couple
# of board writes and possibly a delegated quiz is genuinely slow; past this the
# student has been listening to silence too long and deserves an answer even if
# it is an apology.
TIMEOUT_S = float(os.getenv("NITYAM_BRAIN_TIMEOUT", "70"))

#: How long the student will sit in silence before being told it is taking a
#: while. Well inside TIMEOUT_S: a rate-limited turn spends over a minute inside
#: one google-genai retry loop, and saying nothing for that long is the worst
#: thing this system can do short of lying.
PATIENCE_S = float(os.getenv("NITYAM_BRAIN_PATIENCE", "14"))

def _cache_config():
    """Context caching, when the platform actually supports it.

    On Vertex express mode this fails with `404 Not Found` on every turn —
    `Failed to create cache` in the log — so it is off by default. It is worth
    switching on once running under full ADC/Cloud Run, where delegating swaps
    the system instruction and tool set and the prompt prefix would otherwise be
    re-sent uncached on every call.
    """
    if os.getenv("NITYAM_CONTEXT_CACHE", "").strip() not in ("1", "true", "TRUE"):
        return None
    return ContextCacheConfig(ttl_seconds=1800)


_runner: Runner | None = None
_sessions: InMemorySessionService | None = None
_known: set[str] = set()


def runner() -> Runner:
    """Built once. Agents and runners are stateless; only sessions are not."""
    global _runner, _sessions
    if _runner is None:
        _sessions = InMemorySessionService()
        _runner = Runner(
            app=App(
                name=BRAIN_APP,
                root_agent=build_tutor_agent(),  # mode=None -> valid as a root
                context_cache_config=_cache_config(),
            ),
            session_service=_sessions,
        )
        log.info("brain runner built")
    return _runner


async def _ensure_session(session_id: str, student_id: str) -> None:
    if session_id in _known:
        return
    runner()
    existing = await _sessions.get_session(
        app_name=BRAIN_APP, user_id=student_id, session_id=session_id
    )
    if not existing:
        await _sessions.create_session(
            app_name=BRAIN_APP,
            user_id=student_id,
            session_id=session_id,
            state={"session_id": session_id, "student_id": student_id},
        )
    _known.add(session_id)


_MARKUP = re.compile(r"\$+|\\[a-zA-Z]+|[*_`#]|\\[(){}\[\]]")


def _record(session_id: str, student_id: str, asked: str, replied: str,
            tool_context: ToolContext) -> None:
    """Append the exchange to the session buffer, here rather than as a tool.

    `log_turn` used to be something TutorAgent called, and every call is a model
    round trip: two of them per turn, five to eight seconds of the student
    listening to silence, for bookkeeping they never see. Both halves of the
    exchange are already in hand at this point, so write them directly and give
    the time back to teaching.
    """
    buffer = list(tool_context.state.get("turn_buffer", []))
    for role, text in (("student", asked), ("tutor", replied)):
        clean = (text or "").strip()
        if not clean:
            continue
        # Stage directions are not things the student said.
        if role == "student" and clean.startswith("["):
            clean = clean[:400]
        buffer.append({
            "turn": len(buffer) + 1,
            "role": role,
            "text": clean[:2000],
            "concept_id": None,
            "artifact_id": None,
        })
    tool_context.state["turn_buffer"] = buffer


def _rate_limited(exc: BaseException) -> bool:
    """Is this a 429, anywhere in the cause chain?

    google-genai retries a RESOURCE_EXHAUSTED internally with backoff, so a
    rate-limited turn does not fail fast — it sits inside one generate_content
    for over a minute and then surfaces as a timeout or a _ResourceExhaustedError
    several `raise ... from ...` levels deep. Walk the chain.
    """
    seen = 0
    current: BaseException | None = exc
    while current is not None and seen < 8:
        text = f"{type(current).__name__} {current}"
        if "RESOURCE_EXHAUSTED" in text or "429" in text:
            return True
        current = current.__cause__ or current.__context__
        seen += 1
    return False


def _speakable(text: str) -> str:
    """Strip markup from a reply that is about to be read aloud.

    The instruction asks for plain speech, and mostly gets it — but a model that
    slips once produces "dollar backslash sin open brace two backslash theta" in
    the student's ear, which is worse than any amount of belt-and-braces here.
    Seen for real: the reply came back as `$\\sin(2\\theta)$`.
    """
    cleaned = _MARKUP.sub(" ", text)
    return " ".join(cleaned.split()).strip()


_PROMISE = re.compile(
    r"\b(board|page|screen|simulation|artifact|diagram|figure|likh|daal|"
    r"dekh|bhej)\w*", re.IGNORECASE
)


def _promises_a_visual(reply: str) -> bool:
    """Does this reply tell the student to look at something?

    Deliberately generous — it only gates a log line, and a false positive costs
    one WARNING while a false negative costs a silent lie.
    """
    return bool(_PROMISE.search(reply or ""))


#: Sessions with a brain turn in flight, and the one request waiting behind it.
#:
#: Two turns cannot run concurrently: they share one ADK session, so their state
#: writes would interleave. But dropping the second is worse than making it
#: wait — a student who asks a follow-up five seconds later would simply never
#: get an answer to it. So the latest request is held and run when the current
#: turn finishes. Latest, not a full queue: if they have asked twice, the second
#: question is the one they are still waiting on, and replaying a stale one puts
#: the lesson behind the conversation.
_running: set[str] = set()
_pending: dict[str, tuple[str, str, ToolContext]] = {}


async def _turn(session_id: str, student_id: str, request: str,
                tool_context: ToolContext) -> None:
    """One brain turn, off the voice layer's critical path.

    Everything it produces reaches the student two ways: the board writes go
    straight to the browser as patches (they are already on screen before this
    returns), and the spoken line comes back as a nudge, which makes her say it.
    """
    said: list[str] = []
    calls: list[str] = []

    async def drive() -> None:
        async for event in runner().run_async(
            user_id=student_id,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=request)]),
        ):
            for part in event.content.parts if event.content and event.content.parts else []:
                if part.function_call:
                    calls.append(part.function_call.name)
                    args = str(part.function_call.args)
                    log.info("→ TOOL CALL %s calls %s(%s)", event.author,
                             part.function_call.name,
                             args[:180] + ("…" if len(args) > 180 else ""))
                if part.function_response:
                    got = str(part.function_response.response)
                    log.info("← TOOL DONE %s got %s -> %s", event.author,
                             part.function_response.name,
                             got[:180] + ("…" if len(got) > 180 else ""))
                if part.text and event.author == "TutorAgent":
                    said.append(part.text)

    async def keep_alive() -> None:
        """So a slow turn is never silent.

        A rate-limited turn spends over a minute inside one google-genai retry
        loop. That produced seventy seconds of dead air and a student saying
        "Hello?" into it.
        """
        await asyncio.sleep(PATIENCE_S)
        log.info("brain still working after %ss — keeping the student company",
                 PATIENCE_S)
        sessions.nudge(
            session_id,
            "[Your teaching layer is still working and the student has been "
            "waiting a while. Say one short line to let them know you are still "
            "on it. Do not guess at the answer.]",
        )

    company = asyncio.get_running_loop().create_task(keep_alive())
    try:
        with logs.span("ask_tutor"):
            await asyncio.wait_for(drive(), timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        log.warning("brain timed out after %ss on %r", TIMEOUT_S, request[:80])
        sessions.nudge(
            session_id,
            "[Your teaching layer could not finish that one — it took too long. "
            "NOTHING went on the student's board. Tell them briefly and honestly "
            "that it did not work and ask them to try again. Do not claim "
            "anything is on their page.]",
        )
        return
    except Exception as exc:  # noqa: BLE001 - never take the voice session down
        log.exception("brain turn failed")
        if _rate_limited(exc):
            sessions.nudge(
                session_id,
                "[Your teaching layer is being rate limited by the platform "
                "right now — this is not the student's fault and not something "
                "they can fix. NOTHING went on their board. Say so plainly, in "
                "one line, and suggest trying again in a few seconds.]",
            )
        else:
            sessions.nudge(
                session_id,
                "[Your teaching layer failed on that one. NOTHING went on the "
                "student's board. Say so briefly and ask them to try again.]",
            )
        return
    finally:
        company.cancel()
        _running.discard(session_id)
        _drain_pending(session_id)

    reply = _speakable(" ".join(said))
    _record(session_id, student_id, request, reply, tool_context)
    log.info("brain replied in %s tool call(s): %r", len(calls), reply[:120])
    log.debug("reply in full: %s", reply)
    log.debug("tools used: %s", calls)

    wrote = [c for c in calls if c.startswith("write_") or c == "show_textbook_figure"]
    building = "commission_artifact" in calls or "create_artifact" in calls
    if _promises_a_visual(reply) and not (wrote or building):
        log.warning(
            "PROMISE WITHOUT ACTION — the reply says something appeared but no "
            "board or artifact tool was called this turn: %r",
            reply[:160],
        )
        logs.count("empty promise")

    # Ground truth goes in SILENTLY, as context. It is facts for her to reason
    # from, not words for her to say, so it travels the same channel as the
    # board deltas and never reaches the student.
    facts = []
    if wrote:
        facts.append("Something new IS on their board now — you may tell them to look")
    if building:
        facts.append("A simulation IS being built and will land in about half a minute")
    if not facts:
        facts.append("NOTHING went on their board this turn — say nothing about "
                     "their screen")
    sessions.inject(session_id, f"[{'. '.join(facts)}.]")

    # And the words go out with the WORDS OUTSIDE THE BRACKET.
    #
    # The previous format wrapped everything in one bracket — the instruction,
    # the line in quotes, and the facts in parentheses — and she read the whole
    # thing out loud, brackets included:
    #
    #   "[Your teaching layer has finished. "Here is figure 3.10 from your NCERT
    #    textbook." (on board: figure 3.10, block_3_10)]Here is figure 3.10 from
    #    your NCERT textbook."
    #
    # She already obeys "never read a bracketed message out". So the bracket now
    # holds only the instruction and the words sit OUTSIDE it, where that rule
    # leaves them alone. Nothing quoted, nothing parenthesised, nothing to echo.
    sessions.nudge(
        session_id,
        "[Say the words after this bracket aloud now, in your own voice. Say "
        "only those words. Never say this bracket.] "
        + (reply or "Take a look at your board."),
    )


def _drain_pending(session_id: str) -> None:
    """Run whatever came in while the last turn was busy."""
    held = _pending.pop(session_id, None)
    if held is None:
        return
    student_id, request, tool_context = held
    log.info("running the request held during the last turn: %r", request[:90])
    _running.add(session_id)
    task = asyncio.get_running_loop().create_task(
        _turn(session_id, student_id, request, tool_context)
    )
    sessions.track(session_id, task)


async def ask_tutor(bridge: str, request: str, tool_context: ToolContext) -> dict:
    """Consult your teaching layer. Returns IMMEDIATELY — do not wait for it.

    Say the `bridge` line out loud the moment this returns, then stop and let the
    student breathe. The answer comes back to you a few seconds later as a
    bracketed message telling you exactly what to say; the board updates on its
    own before that, so they are already looking at something.

    Args:
        bridge: What you say RIGHT NOW, out loud, while it works — "achha, ek
            second", "good question, let me look at that with you", "sure, I'll
            put that on the board". One short sentence, in your own voice.
            Required, and it is the only thing you say this turn.
        request: What the student needs, in your own words — their question or
            doubt, plus anything you noticed. Be specific: "explain why 45
            degrees maximises range, they think it is about throwing harder"
            beats "help with projectiles".

    Returns:
        dict with "say" — say exactly that and then wait.
    """
    session_id = tool_context.state.get("session_id") or "unknown"
    student_id = tool_context.state.get("student_id") or "demo_student"
    spoken = (bridge or "").strip() or "Ek second."

    log.info("bridge: %r", spoken[:120])
    log.debug("request in full: %s", request)

    # Fire-and-forget, and this is the whole point.
    #
    # It used to await the brain. The Live model will not begin a new turn while
    # a function call is outstanding, so nothing — not a nudge, not an
    # injection — could reach the student until the brain came back. Measured:
    # the holding line was produced at 1.2s and not spoken until 11.5s, and a
    # rate-limited turn gave seventy seconds of total silence. Returning at once
    # means she says the holding line at ~1.5s and the answer arrives as a nudge
    # when it is ready.
    if session_id in _running:
        # Held, not dropped. It runs the moment the current turn finishes.
        _pending[session_id] = (student_id, request, tool_context)
        log.info("brain busy for %s — holding this request", session_id)
        return {
            "say": spoken,
            "note": "Your teaching layer is still on the previous question. Say "
                    "the line and wait — this one is queued behind it and you "
                    "will be told about both.",
        }

    try:
        await _ensure_session(session_id, student_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("could not open a brain session")
        return {
            "say": "Sorry — I cannot reach my teaching layer just now.",
            "error": f"could not reach the teaching layer ({type(exc).__name__})",
            "wrote_on_board": False,
            "artifact_building": False,
        }

    _running.add(session_id)
    task = asyncio.get_running_loop().create_task(
        _turn(session_id, student_id, request, tool_context)
    )
    sessions.track(session_id, task)

    return {
        "say": spoken,
        "note": "Say exactly that now, then stop. The answer will reach you in a "
                "moment as a bracketed message, and their board may update "
                "before it does.",
    }
