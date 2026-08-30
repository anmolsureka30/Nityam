"""One Runner+session bootstrap, shared by every specialist agent reached
from VoiceAgent (BoardAgent, ArtifactAgent, QuizAgent, TextbookAgent).

Each specialist runs in its own Runner via run_async, for the same reason
brain.py's TutorAgent always did: run_live never initialises
InvocationContext._event_queue, so a mode='single_turn' sub-agent nested
under a live VoiceAgent crashes on its first event. Reached instead as a
plain async function tool, tagged response_scheduling=WHEN_IDLE so the
Gemini Live API itself holds the result until VoiceAgent is between things
— see docs/superpowers/specs/2026-08-28-agent-orchestration-redesign-design.md §2.

`delegate` below is the entry point all four use, and it is an ASYNC GENERATOR
rather than a coroutine. That is the whole mechanism for not going silent: ADK
routes an async-generator tool through its streaming path, so every yield is a
`send_tool_response` on the same call id and each one carries its own
`scheduling`. `WHEN_IDLE` on a progress chunk means "speak as soon as you stop",
which is what keeps her talking for the ten to thirty seconds a specialist
takes.

This replaced a timer that injected client content from the side every 7s, three
times. That was the wrong channel — Google warns `send_client_content` races
with the realtime audio stream, and Gemini 3.1 Live rejects it after the first
turn — and it was blind to whether she was already speaking, so it talked over
her. It also only covered 21s of a 70s cap. See git history, and
tests/probe_live_streaming_tool.py for the measurements that settled this.

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
import time
from typing import AsyncIterator, Callable

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app import tracing
from app.memory import instrumentation, short_term

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


_ACTOR_FOR_LABEL: dict[str, "instrumentation.ToolActor"] = {
    "board": "board_agent", "artifact": "artifact_agent",
    "quiz": "quiz_agent", "textbook": "textbook_agent",
}

_pending_calls: dict[str, float] = {}
"""function_call.id -> when it started, so the matching function_response
can compute a real duration_ms. Module-level and keyed by call id (not by
session): ADK's FunctionCall/FunctionResponse both carry a stable `id` field
that already correlates a call with its result, so no session-scoping is
needed here — a stale entry from an abandoned call is simply never popped,
which is harmless (it never affects a future call's own duration)."""


def _log_tool_activity(
    label: str, event, session_id: str | None, student_id: str | None
) -> None:
    """Log a specialist's own tool calls and results, the same way main.py's
    trace() does for VoiceAgent, AND publish each one as a ToolCallEvent —
    search_grounding, get_dpm, strike_block and everything else a specialist
    calls internally was previously invisible even in a full session log,
    since each specialist runs in its own Runner several frames away from
    main.py's own event stream. Published from inside the span
    _run_turn_uncapped opens, so these events share one trace with the
    MemoryEvents that same tool activity triggers (e.g. get_dpm's own
    published read)."""
    actor = _ACTOR_FOR_LABEL.get(label, "board_agent")
    for part in event.content.parts if event.content and event.content.parts else []:
        call = part.function_call
        if call:
            args = str(call.args)
            log.info("  [%s] → %s(%s)", label, call.name,
                      args[:200] + ("…" if len(args) > 200 else ""))
            if call.id:
                _pending_calls[call.id] = time.monotonic()
            instrumentation.publish_tool_call_event(
                instrumentation.build_tool_call_event(
                    actor=actor, tool_name=call.name, phase="started",
                    session_id=session_id, student_id=student_id,
                    args_summary=args,
                )
            )
        response = part.function_response
        if response:
            got = str(response.response)
            log.info("  [%s] ← %s -> %s", label, response.name,
                      got[:200] + ("…" if len(got) > 200 else ""))
            duration_ms = None
            if response.id and response.id in _pending_calls:
                duration_ms = int((time.monotonic() - _pending_calls.pop(response.id)) * 1000)
            instrumentation.publish_tool_call_event(
                instrumentation.build_tool_call_event(
                    actor=actor, tool_name=response.name, phase="done",
                    session_id=session_id, student_id=student_id,
                    result_summary=got, duration_ms=duration_ms,
                )
            )


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
        with tracing.tracer.start_as_current_span(f"{self._app_name}.turn"):
            async for event in self._runner_instance().run_async(
                user_id=student_id, session_id=session_id,
                new_message=types.Content(role="user", parts=[types.Part(text=message)]),
            ):
                _log_tool_activity(self._app_name, event, session_id, student_id)
                for part in event.content.parts if event.content and event.content.parts else []:
                    if part.text:
                        said.append(part.text)
        return _speakable(" ".join(said))

    async def run_turn(self, session_id: str, student_id: str, message: str) -> str:
        """Run one turn to completion; return whatever text the specialist said.

        Capped at `self._timeout_s` (70s by default). The resulting
        `asyncio.TimeoutError` is deliberately allowed to propagate: `delegate`
        below turns it into the error-shaped chunk the voice layer knows how to
        say out loud. Swallowing it here would put us back where we started —
        a delegation that never resolves and is never spoken about.

        No longer spawns anything alongside itself. Keeping the conversation
        alive while this runs is `delegate`'s job now, and it does it by
        yielding tool responses rather than by injecting client content on a
        timer — see that function.
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


KEEP_TALKING_INTERVAL_S = 4.5
"""How often, while a specialist runs, she is handed a reason to keep talking.

Measured, not reasoned. `tests/probe_live_streaming_tool.py` against real
Vertex Live: at a 6.0s cadence the worst silence inside a delegation was 3.3s —
the gap between the last progress response and the real answer. 4.5s closes it.

It is NOT the target silence. A WHEN_IDLE response does not mean "speak now",
it means "speak when you next stop", so a response arriving mid-sentence is
queued rather than acted on. What the cadence has to beat is the length of one
of her utterances, so that whenever she draws breath there is already an
unconsumed reason to carry on. Two or three sentences of Live audio is ~6-9s.
Tightening this to 1-2s does not reduce silence further; it queues three or
four triggers per utterance and produces a tutor who never draws breath."""

_QUIET_AFTER_STUDENT_S = 2.0
"""Skip a scheduled response if the student was speaking this recently.

WHEN_IDLE is defined against HER generation, not theirs — if she is idle and
they are mid-sentence, a response can put her straight over the top of them."""

_STRETCH_AFTER_S = 30
"""Past this, stop asking her to continue the same thread and move her on."""

_OPENING_CLAUSE = {
    "board": "Ask them what they already know about it.",
    "artifact": "Ask them to predict what the simulation will show.",
    "quiz": "Ask them to recall the key point before the questions appear.",
    "textbook": "Ask what they remember of the figure you are looking for.",
}
"""One line each, sent only in that specialist's own opening response.

Deliberately here and not in VOICE_INSTRUCTION: the instruction is re-billed on
every turn of the session, and each of these is relevant for a few seconds of
one delegation. ~15 tokens, paid only when it applies."""


def _opening(label: str) -> dict:
    return {
        "still_working": label,
        "seconds": 0,
        "do": (
            "[Being prepared now — IT IS NOT ON THE BOARD YET, so do not say "
            "it is. Keep teaching meanwhile, as a conversation: a sentence or "
            "two, then a question, then let them answer. "
            + _OPENING_CLAUSE.get(label, "")
            + "]"
        ),
    }


def _holding(label: str, seconds: int) -> object:
    """One reason to keep talking, scheduled to fire the moment she goes quiet.

    `WHEN_IDLE` per chunk is what makes her speak at all — the probe measured
    the alternative (`SILENT`) as 23 seconds of dead air, because a silent
    response gives her nothing to react to. The `seconds` count is a cheap
    stand-in for a sentence telling her not to repeat herself.
    """
    if seconds >= _STRETCH_AFTER_S:
        do = (
            "[Still being prepared, still not on the board. Move to a "
            "different idea entirely, or ask them to try something. Do not "
            "repeat anything you have already said.]"
        )
    else:
        # "or ask them something" let her monologue: given the choice she took
        # the next step out loud, at length, and never handed the turn back.
        # Asking is the instruction now, not one of two options.
        do = (
            "[Still being prepared, still not on the board. They have gone "
            "quiet — move the lesson on with something NEW. Never re-ask a "
            "question you have already asked.]"
        )
    return types.FunctionResponse(
        response={"still_working": label, "seconds": seconds, "do": do},
        scheduling=types.FunctionResponseScheduling.WHEN_IDLE,
    )


_last_heard: dict[str, float] = {}
"""session_id -> when the student was last heard saying something.

Stamped by main.trace() off `input_transcription`, never off microphone bytes:
those arrive continuously whether or not anyone is speaking, so they would
report the student as permanently mid-sentence."""


_last_spoke: dict[str, float] = {}
"""session_id -> when SHE last finished saying something.

Same source as _last_heard, the other side of it: main.trace() off
`output_transcription`. Used to decide whether she is mid-exchange, and so
whether an event from the page should be allowed to make her talk."""

_MID_EXCHANGE_S = 10.0
"""How long after she speaks she is still considered mid-exchange.

She asks a question and then waits; the student takes several seconds to
answer. An event arriving in that gap must not make her speak, or she talks
into her own unanswered question. Measured against the real case: she asked
"did you find what that angle is?" and an artifact event 14s later made her
ask the same thing again, in different words, before the student had
answered."""


def heard_student(session_id: str) -> None:
    if session_id:
        _last_heard[session_id] = time.monotonic()


def she_spoke(session_id: str) -> None:
    if session_id:
        _last_spoke[session_id] = time.monotonic()


_SHE_JUST_SPOKE_S = 3.5
"""Do not prompt her again this soon after she last spoke.

THE BUG THIS FIXES. The keep-talking chunks fired on a pure timer, so an
11-second delegation produced five of them, and each one is an instruction to
say something. She had nothing new to say, so she asked the same question five
times in five different phrasings:

    03:40:29  "...which side of the triangle is adjacent to this angle?"
    03:40:33  "...which side of the triangle is next to that angle?"
    03:40:38  "...Which side of the triangle is adjacent to this angle?"
    03:40:45  "...which side of the triangle is next to the angle?"
    03:40:47  "...it's the side adjacent to the angle theta."

A prompt to speak is only ever needed into SILENCE. If she spoke two seconds
ago the delegation is not producing dead air, it is producing a lesson, and
the right number of extra prompts is zero. So the cadence sets how often the
question is ASKED, and this decides the answer."""


def _student_is_talking(session_id: str) -> bool:
    last = _last_heard.get(session_id)
    return last is not None and (time.monotonic() - last) < _QUIET_AFTER_STUDENT_S


def _she_just_spoke(session_id: str) -> bool:
    last = _last_spoke.get(session_id)
    return last is not None and (time.monotonic() - last) < _SHE_JUST_SPOKE_S


def mid_exchange(session_id: str) -> bool:
    """True while she is waiting on an answer she has just asked for.

    Read by main.py before letting a page event complete a turn. An event that
    merely reports what the student is doing is never worth interrupting an
    exchange for — it can arrive as context and be mentioned when she next
    speaks naturally.
    """
    spoke = _last_spoke.get(session_id)
    heard = _last_heard.get(session_id)
    if spoke is None:
        return False
    if heard is not None and heard > spoke:
        return False        # they have answered; the exchange has moved on
    return (time.monotonic() - spoke) < _MID_EXCHANGE_S


def forget_session(session_id: str) -> None:
    """Drop a closed session's conversation timings."""
    _last_heard.pop(session_id, None)
    _last_spoke.pop(session_id, None)


_in_flight: set[tuple[str, str]] = set()
"""(session_id, label) pairs with a delegation currently running.

Not belt-and-braces. ADK registers streaming-tool tasks in
`active_streaming_tools` keyed by TOOL NAME rather than call id
(flows/llm_flows/functions.py), so a second ask_board while one is outstanding
overwrites the entry and orphans the first task. And each SpecialistRunner
holds one ADK session per session_id, so two concurrent turns on the same
specialist would interleave inside it. Two DIFFERENT specialists at once is
fine and expected; the same one twice is not."""


async def delegate(
    label: str,
    runner: "SpecialistRunner",
    request: str,
    tool_context,
    *,
    transcript_n: int,
    done_default: str,
    error_text: str,
) -> AsyncIterator[object]:
    """The whole delegation: keep her talking while the specialist works, then
    hand her its report.

    An async generator ON PURPOSE. ADK routes an async-generator tool through
    its streaming path, where every yield becomes a `send_tool_response`
    against the same call id, and the FunctionResponse's own `scheduling`
    field decides whether she speaks. That is a model-level "speak when you
    next go idle" primitive, and it replaces the timer that used to inject
    client content from the side — which was both the wrong channel (Google
    warns it races with the realtime audio stream, and Gemini 3.1 Live rejects
    it outright after the first turn) and blind to whether she was already
    talking.

    Verified against real Vertex Live before this was written; see
    tests/probe_live_streaming_tool.py for the numbers.
    """
    session_id = tool_context.state.get("session_id")
    student_id = tool_context.state.get("student_id")
    if not session_id or not student_id:
        log.warning("ask_%s called with no session/student id in state", label)
        instrumentation.publish_tool_call_event(
            instrumentation.build_tool_call_event(
                actor="voice_agent", tool_name=f"ask_{label}", phase="error",
                session_id=session_id, student_id=student_id,
                result_summary="no session/student id in state",
            )
        )
        yield {"status": "error",
               "summary": "Something went wrong on my end — let's move on."}
        return

    key = (session_id, label)
    if key in _in_flight:
        log.info("ask_%s called while one was already running; refused", label)
        instrumentation.publish_tool_call_event(
            instrumentation.build_tool_call_event(
                actor="voice_agent", tool_name=f"ask_{label}", phase="busy",
                session_id=session_id, student_id=student_id,
            )
        )
        yield {"status": "busy",
               "summary": f"Already working on that — no need to ask again."}
        return

    yield types.FunctionResponse(
        response=_opening(label),
        # SILENT: this one is context for the turn she is ALREADY taking. ADK
        # has just handed her its own synthetic pending response at WHEN_IDLE,
        # which is what actually starts her talking; a second prompt here would
        # only stack up behind it.
        scheduling=types.FunctionResponseScheduling.SILENT,
    )

    _in_flight.add(key)
    task = None
    try:
        transcript = await recent_transcript(session_id, student_id, n=transcript_n)
        # The board goes in the prompt rather than behind read_screen. A tool
        # only helps if the specialist thinks to call it, and mostly it did
        # not — so BoardAgent would describe a figure TextbookAgent had just
        # placed, having no idea it was there.
        from app.canvas.tools import board_digest

        board = board_digest(session_id)
        task = asyncio.get_running_loop().create_task(
            runner.run_turn(
                session_id, student_id, f"{request}\n\n{board}\n\n{transcript}"
            )
        )
        started = time.monotonic()
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=KEEP_TALKING_INTERVAL_S)
            if done:
                break
            if _student_is_talking(session_id):
                continue          # skip rather than talk over them
            if _she_just_spoke(session_id):
                continue          # she is teaching; there is no silence to fill
            yield _holding(label, int(time.monotonic() - started))
    finally:
        _in_flight.discard(key)
        # A generator torn down mid-flight (a session_resumption reconnect, the
        # run ending) must not leave the specialist running with nobody to
        # receive it.
        if task is not None and not task.done():
            task.cancel()

    duration_ms = int((time.monotonic() - started) * 1000)
    try:
        summary = task.result()
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - the tool must always report something
        log.exception("%sAgent turn failed", label.capitalize())
        instrumentation.publish_tool_call_event(
            instrumentation.build_tool_call_event(
                actor="voice_agent", tool_name=f"ask_{label}", phase="error",
                session_id=session_id, student_id=student_id,
                duration_ms=duration_ms,
            )
        )
        yield {"status": "error", "summary": error_text}
        return

    # A specialist's own work is the moment the student's record is most likely
    # to have moved. Scheduled, not awaited: compose_brief makes several
    # blocking Firestore round trips (3+ seconds, measured) and has no business
    # delaying the answer she is about to give.
    schedule_brief_refresh(session_id, student_id)
    instrumentation.publish_tool_call_event(
        instrumentation.build_tool_call_event(
            actor="voice_agent", tool_name=f"ask_{label}", phase="done",
            session_id=session_id, student_id=student_id,
            result_summary=summary or done_default, duration_ms=duration_ms,
        )
    )
    yield {"status": "done", "summary": summary or done_default}


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
