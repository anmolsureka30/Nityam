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

from app.agents.tutor_agent import build_tutor_agent

log = logging.getLogger("nityam.brain")

BRAIN_APP = "nityam-brain"

# How long the voice layer will wait. A reasoning turn with grounding, a couple
# of board writes and possibly a delegated quiz is genuinely slow; past this the
# student has been listening to silence too long and deserves an answer even if
# it is an apology.
TIMEOUT_S = float(os.getenv("NITYAM_BRAIN_TIMEOUT", "70"))

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


def _speakable(text: str) -> str:
    """Strip markup from a reply that is about to be read aloud.

    The instruction asks for plain speech, and mostly gets it — but a model that
    slips once produces "dollar backslash sin open brace two backslash theta" in
    the student's ear, which is worse than any amount of belt-and-braces here.
    Seen for real: the reply came back as `$\\sin(2\\theta)$`.
    """
    cleaned = _MARKUP.sub(" ", text)
    return " ".join(cleaned.split()).strip()


async def ask_tutor(request: str, tool_context: ToolContext) -> dict:
    """Consult your teaching layer. Use this for anything with teaching content.

    It decides what to teach, grounds it in this student's own lecture, writes on
    their board, and can bring in a simulation or a quiz. It hands you back a
    short line to say out loud.

    Args:
        request: What the student needs, in your own words — their question or
            doubt, plus anything you noticed. Be specific: "explain why 45
            degrees maximises range, they think it is about throwing harder"
            beats "help with projectiles".

    Returns:
        dict with "reply" — say this in your own voice — or {"error": ...}.
    """
    session_id = tool_context.state.get("session_id") or "unknown"
    student_id = tool_context.state.get("student_id") or "demo_student"

    try:
        await _ensure_session(session_id, student_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("could not open a brain session")
        return {"error": f"could not reach the teaching layer ({type(exc).__name__})"}

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

    try:
        await asyncio.wait_for(drive(), timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        log.warning("brain timed out after %ss on %r", TIMEOUT_S, request[:80])
        return {
            "error": "the teaching layer took too long",
            "reply": "Sorry — that took me too long to work out. Ask me again?",
        }
    except Exception as exc:  # noqa: BLE001 - never take the voice session down
        log.exception("brain turn failed")
        return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}

    reply = _speakable(" ".join(said))
    log.info("brain replied in %s tool call(s): %r", len(calls), reply[:120])
    if not reply:
        return {
            "reply": "I've put that on your board — take a look.",
            "tools_used": calls,
        }
    return {"reply": reply, "tools_used": calls}
