"""One Runner+session bootstrap, shared by every specialist agent reached
from VoiceAgent (BoardAgent, ArtifactAgent, QuizAgent, TextbookAgent).

Each specialist runs in its own Runner via run_async, for the same reason
brain.py's TutorAgent always did: run_live never initialises
InvocationContext._event_queue, so a mode='single_turn' sub-agent nested
under a live VoiceAgent crashes on its first event. Reached instead as a
plain async function tool, tagged response_scheduling=WHEN_IDLE so the
Gemini Live API itself holds the result until VoiceAgent is between things
— see docs/superpowers/specs/2026-08-28-agent-orchestration-redesign-design.md §2.

This used to be hand-rolled once per specialist (brain.py's runner()/
_ensure_session()/_known, artifact_agent.py's near-identical copy) — written
once here instead.

It also owns `refresh_brief` and the sink every specialist needs to reach to
re-brief the voice layer. That lives here rather than in main.py for an
import-graph reason: main.py already imports all four specialists (indirectly,
through voice_agent.py), so a specialist importing main.py back is a cycle.
Every specialist already imports this module.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import re
from typing import Callable

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.memory import short_term

log = logging.getLogger("nityam.specialist_runner")

_MARKUP = re.compile(r"\$+|\\[a-zA-Z]+|[*_`#]|\\[(){}\[\]]")

TURN_TIMEOUT_S = 70
"""How long one specialist turn may take before it is abandoned.

Inherited value, not a new guess: the retired brain.py wrapped its own
delegated call in `asyncio.wait_for(..., timeout=70)`. Losing that in the
port was worse than it sounds — a WHEN_IDLE tool delivers nothing at all
unless the coroutine returns, and VoiceAgent will not re-issue a call that
is still outstanding, so a hung specialist is not a slow answer, it is
permanent silence with no error and no way back."""


def _speakable(text: str) -> str:
    """Strip markup from text that is about to be spoken by VoiceAgent.

    Moved from brain.py's identical function (retired elsewhere in this
    plan) — every specialist's spoken summary now flows through
    run_turn() below, so sanitizing once here replaces sanitizing in each
    of Board/Artifact/Quiz/TextbookAgent's own tool functions. Seen for
    real, historically: a reply came back as `$\\sin(2\\theta)$`, which
    is worse read aloud than any amount of belt-and-braces here.
    """
    cleaned = _MARKUP.sub(" ", text)
    return " ".join(cleaned.split()).strip()


class SpecialistRunner:
    """Builds its agent and Runner once; ensures a session per session_id."""

    def __init__(
        self,
        app_name: str,
        build_agent: Callable[[], LlmAgent],
        timeout_s: float = TURN_TIMEOUT_S,
    ) -> None:
        self._app_name = app_name
        self._build_agent = build_agent
        self._timeout_s = timeout_s
        self._runner: Runner | None = None
        self._sessions: InMemorySessionService | None = None
        self._known: set[str] = set()

    def _runner_instance(self) -> Runner:
        if self._runner is None:
            self._sessions = InMemorySessionService()
            self._runner = Runner(
                app=App(name=self._app_name, root_agent=self._build_agent()),
                session_service=self._sessions,
            )
        return self._runner

    async def _ensure_session(self, session_id: str, student_id: str) -> None:
        if session_id in self._known:
            return
        runner = self._runner_instance()
        existing = await self._sessions.get_session(
            app_name=self._app_name, user_id=student_id, session_id=session_id,
        )
        if not existing:
            await self._sessions.create_session(
                app_name=self._app_name, user_id=student_id, session_id=session_id,
                state={"session_id": session_id, "student_id": student_id},
            )
        self._known.add(session_id)
        _ = runner  # built as a side effect of _runner_instance(); kept for clarity

    async def _run_turn_uncapped(
        self, session_id: str, student_id: str, message: str
    ) -> str:
        await self._ensure_session(session_id, student_id)
        said: list[str] = []
        async for event in self._runner_instance().run_async(
            user_id=student_id, session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
        ):
            for part in event.content.parts if event.content and event.content.parts else []:
                if part.text:
                    said.append(part.text)
        return _speakable(" ".join(said))

    async def run_turn(self, session_id: str, student_id: str, message: str) -> str:
        """Run one turn to completion; return whatever text the specialist said.

        Capped at `self._timeout_s` (70s by default, brain.py's own value).
        The resulting `asyncio.TimeoutError` is deliberately allowed to
        propagate: every `ask_*` tool already wraps this in `except
        Exception` and turns it into the error-shaped dict the voice layer
        knows how to say out loud, and TimeoutError is an ordinary Exception
        subclass. Swallowing it here would put us back where we started —
        a delegation that never resolves and is never spoken about.
        """
        return await asyncio.wait_for(
            self._run_turn_uncapped(session_id, student_id, message),
            timeout=self._timeout_s,
        )


_live_sink_context: contextvars.ContextVar[object | None] = contextvars.ContextVar(
    "nityam_live_sink", default=None
)
"""The current connection's sink, so a specialist can inject context back into
the live conversation it was called from. Set once per connection by
main.py's run_live; unset everywhere else, which is what makes `refresh_brief`
a silent no-op under test and in mock mode."""

_last_brief: dict[str, str] = {}
"""session_id -> the last brief text actually sent, so an unchanged brief is
not re-injected. Without this the refresh works directly against its own
purpose: the brief exists to keep a small amount of relevant material in the
voice layer's context, and re-sending byte-identical text after every
specialist call just fills that context with copies of itself."""


def set_live_sink(sink) -> None:
    """Called once per live connection, from main.py's run_live."""
    _live_sink_context.set(sink)
    _last_brief.clear()


def note_brief_sent(session_id: str, line: str) -> None:
    """Record a brief someone else already delivered, so `refresh_brief`
    doesn't immediately re-send it. Called by main.py's `start` handler with
    the opening brief — without it, the first specialist call of every
    session re-injects text the voice layer was handed seconds earlier."""
    if line:
        _last_brief[session_id] = line


async def refresh_brief(session_id: str, student_id: str) -> None:
    """Re-brief the voice layer, if anything actually changed.

    Called from each specialist's own `ask_*` tool after its turn succeeds —
    a specialist's work is exactly the moment the student's record is most
    likely to have moved. It lives at the tool's own call site rather than on
    a `function_response` event in main.py's `trace()`, because ADK never
    yields a function_response Event into run_live's stream for a
    `response_scheduling=WHEN_IDLE` tool: `_execute_single_function_call_live`
    returns None, `handle_function_calls_live` filters it out, and
    base_llm_flow.py's yield is guarded on the result. The tool function,
    on the other hand, definitely runs to completion — that is what
    WHEN_IDLE is waiting for.

    Composes in a thread: `compose_brief` makes several blocking Firestore
    round trips (3+ seconds, measured), and this runs mid-lesson, on the same
    event loop as every concurrent student's audio.

    Never raises. A stale brief is a worse lesson; a raised exception here
    would be caught by the tool's own handler and turn a perfectly good
    specialist answer into "something went wrong on my end".
    """
    sink = _live_sink_context.get()
    if sink is None:
        return
    try:
        from app import briefing

        line = await asyncio.to_thread(briefing.compose_brief, session_id, student_id)
        if not line or _last_brief.get(session_id) == line:
            log.debug("brief unchanged for %s; not re-sending", session_id)
            return
        _last_brief[session_id] = line
        sink.text(line, partial=True)
        log.info("re-briefed the voice layer: %s chars", len(line))
    except Exception:  # noqa: BLE001 - a stale brief must never break a live turn
        log.warning("brief refresh failed", exc_info=True)


def schedule_brief_refresh(session_id: str, student_id: str) -> None:
    """Fire-and-forget `refresh_brief`, so its own Firestore-backed compose
    (3+ seconds, measured) never sits on a specialist's own return to
    VoiceAgent. That return is already the entire reason a delegation feels
    slow to the student; the brief refresh is a nice-to-have layered on top
    of it, not part of the answer itself, and has no business adding to the
    same silence VoiceAgent is sitting through.

    Tracked via `sessions.track` — asyncio holds only a weak reference to an
    unawaited task, so without this it can be garbage collected mid-flight
    and simply never finish, with no error anywhere.
    """
    task = asyncio.get_running_loop().create_task(
        refresh_brief(session_id, student_id)
    )
    from app import sessions

    sessions.track(session_id, task)


async def recent_transcript(session_id: str, student_id: str, n: int) -> str:
    """The last n recorded turns, formatted for a specialist's prompt."""
    buffer = await short_term.get_turn_buffer(session_id, student_id)
    recent = buffer[-n:]
    if not recent:
        return "No prior turns recorded yet this session."
    lines = [f"{turn['role']}: {turn['text']}" for turn in recent]
    return "Recent conversation:\n" + "\n".join(lines)
