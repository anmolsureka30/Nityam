"""FastAPI WebSocket server: browser <-> ADK <-> Gemini Live.

The browser cannot talk to ADK directly — ADK is a server-side Python runtime
with no browser client. This process owns the Runner, the LiveRequestQueue and
the board; the browser owns the microphone, the speaker and the page.
One WebSocket between them.

Five concurrent tasks per connection:

    read_client()        browser -> LiveRequestQueue  (mic, text, gestures, screen)
    downstream()         runner.run_live() -> browser (audio, transcripts, tool calls)
    outbound()           board outbox -> browser      (canvas patches)
    heartbeat()          this connection -> Redis     (tells the Observatory it's live)
    _transcript_writer() transcript queue -> Redis    (every settled exchange, in order)

The third one is why the tutor can write on the page at all. Board tools run
inside a mode='single_turn' sub-agent invocation, several frames deep, with no
reference to this WebSocket — so they publish to a per-session queue
(app/sessions.py) and this task delivers it. Depending on nested sub-agent
events surfacing in the parent's run_live() stream would have been the smaller
change and a much worse bet.

Run:  ./run.sh
"""

# Environment must be settled before the agent modules are imported, because
# google-genai reads its platform variables when it builds a client and
# config.live_model() reads what configure() resolved. This ordering is
# load-bearing.
from app.auth import configure, describe, load_env  # noqa: E402

load_env()
MODE = configure()

import asyncio  # noqa: E402
import contextvars  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app import briefing, incoming, sessions, user_auth  # noqa: E402
# Imported on both paths, not just the live one: the `start` handler is shared
# with mock mode, and this module holds nothing but a contextvar, a dict and
# the ADK Runner plumbing — no client is constructed at import time.
from app.agents import specialist_runner  # noqa: E402
from app.memory import instrumentation, short_term, store  # noqa: E402
from app.memory_routes import router as memory_router  # noqa: E402
from app.session_close import close_session as _close_session_memory  # noqa: E402

from app import logs  # noqa: E402

logs.setup()
log = logging.getLogger("nityam")

APP_NAME = "nityam"

app = FastAPI(title="Nityam backend")
user_auth.init_firebase()
app.include_router(memory_router)

# --------------------------------------------------------------- runtime

runner = None
session_service = None

_recording_context: contextvars.ContextVar[tuple[str, str] | None] = (
    contextvars.ContextVar("nityam_recording_context", default=None)
)
"""(session_id, student_id) for whoever is currently recording transcript
turns — set once per connection in ws_endpoint, same pattern as
instrumentation.set_session_context. Lets trace() record every exchange
without needing session_id/student_id threaded through the ADK Event."""

_transcript_queue_context: contextvars.ContextVar[asyncio.Queue | None] = (
    contextvars.ContextVar("nityam_transcript_queue", default=None)
)
"""The per-connection FIFO _record_turn enqueues onto and _transcript_writer
drains, set once per live connection in run_live. A separate task per
_record_turn call each opening its own Redis connection raced each other and
reordered/dropped entries under real load -- see _record_turn's docstring."""

if MODE != "mock":
    from google.adk.agents.live_request_queue import LiveRequestQueue
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.adk.apps import App
    from google.adk.artifacts import GcsArtifactService
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from app import config
    from app.agents.voice_agent import build_voice_agent

    # Created once at startup and shared by every connection: agents and
    # runners are stateless. Only the queue and RunConfig are per-session.
    #
    # SEAM: InMemorySessionService. Swap for DatabaseSessionService (Cloud SQL)
    # or VertexAiSessionService — a one-line constructor change, no other code
    # moves. See backend/INTEGRATION.md.
    session_service = InMemorySessionService()
    runner = Runner(
        app=App(
            name=APP_NAME,
            root_agent=build_voice_agent(),
            # See config.cache_config: caching 404s on the express-mode
            # endpoint, so it is opt-in via NITYAM_CONTEXT_CACHE rather than
            # logging a failure on every turn.
            context_cache_config=config.cache_config(),
        ),
        session_service=session_service,
        # Wired but not yet load-bearing: nothing calls tool_context.save_artifact()
        # — generated artifacts persist through app/artifacts_gcs.py directly
        # (see artifact_agent.py:_build for why). Worth knowing before a deploy:
        # GcsArtifactService.__init__ eagerly constructs a storage.Client(), so
        # in live mode importing this module now requires resolvable Application
        # Default Credentials, even though this line has no functional effect
        # yet. A box with valid model-serving credentials but no ADC will fail
        # here, and the cause will not be obvious.
        artifact_service=GcsArtifactService(bucket_name=config.GCS_BUCKET),
    )

log.info("starting — %s", describe())


def build_run_config():
    """Per-session streaming configuration."""
    return RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=["AUDIO"],  # native audio models require exactly this
        # Transcription is what gives us on-screen captions even though the
        # response modality is audio-only.
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        # Reconnect across the platform's session cap (~10-15 min) instead of
        # dropping the student mid-lesson.
        session_resumption=types.SessionResumptionConfig(),
        max_llm_calls=int(os.getenv("NITYAM_MAX_LLM_CALLS", "500")),
    )


# --------------------------------------------------------------- socket

@app.websocket("/ws/{user_id}/{session_id}")
async def ws_endpoint(ws: WebSocket, user_id: str, session_id: str) -> None:
    await ws.accept()

    token = ws.query_params.get("token")
    decoded = None
    if token:
        try:
            # In a thread: verify_id_token() is synchronous and makes a real
            # HTTPS call whenever Google's signing certificates are not already
            # cached (the first connection after startup, and periodically
            # after that). Called inline it would stall the whole event loop —
            # and with it every concurrent student's audio stream — for as long
            # as that fetch takes.
            decoded = await asyncio.to_thread(user_auth.verify_token, token)
        except Exception:
            decoded = None
    if not decoded or decoded.get("uid") != user_id:
        # Accept-then-reject, not a pre-accept close: a pre-accept WebSocket
        # rejection carries no reason string the browser can read (a platform
        # limitation, not a FastAPI one), so the actual "please sign in again"
        # message would never reach the screen. Nothing sensitive happens
        # before this check — no session state, no board data.
        await send_control(
            ws, kind="error",
            message="Your sign-in has expired. Please refresh and sign in again.",
        )
        await ws.close(code=4401)
        return

    # First thing, before any other log line: opens backend/logs/<...>.log and
    # sets the ContextVar every task under this connection inherits. Everything
    # from here on is recorded in full, per session, whatever else it prints.
    logs.open_session(
        session_id,
        user_id,
        mode=MODE,
        live_model=os.getenv("NITYAM_RESOLVED_LIVE_MODEL", ""),
        detail=describe(),
    )
    # Same contextvar pattern as logs.open_session just above, for a different
    # reader: every store.py function's instrumentation relies on this to know
    # which session a long_term/episodic read or write belongs to (get_dpm,
    # search_grounding and friends never receive a session_id as an argument
    # at all). Previously only set inside session_close.py, at the very end —
    # meaning every read for the whole live conversation published with
    # session_id=None, and the Observatory (which drops events with no
    # session_id) never saw the session until after it had already closed.
    # asyncio tasks created from here on inherit whatever this coroutine's
    # context holds, so setting it once, this early, covers the whole
    # connection — including each specialist agent's own SpecialistRunner
    # tasks (app/agents/specialist_runner.py).
    instrumentation.set_session_context(session_id)
    _recording_context.set((session_id, user_id))
    state = sessions.get(session_id, student_id=user_id)
    await send_control(
        ws,
        kind="session",
        mode=MODE,
        model=os.getenv("NITYAM_RESOLVED_LIVE_MODEL", ""),
        board=state.board.model_dump(exclude_none=True),
    )
    log.info("connected user=%s session=%s mode=%s", user_id, session_id, MODE)
    try:
        if MODE == "mock":
            await run_mock(ws, user_id, session_id)
        else:
            await run_live(ws, user_id, session_id)
    except WebSocketDisconnect:
        log.info("disconnected user=%s", user_id)
    finally:
        log.info("closed user=%s", user_id)
        # Nested rather than sequenced, which buys both properties at once: the
        # flush's own log lines still land in the per-session file (they would
        # not if the file handle were already closed), AND the debug log closes
        # even if the flush is interrupted (e.g. a server shutdown).
        try:
            if MODE != "mock":
                await _flush_session_memory(session_id, user_id)
        finally:
            # Prints the turn timeline to the terminal and appends it to the file.
            logs.close_session(session_id)


async def _flush_session_memory(session_id: str, student_id: str) -> None:
    """The actual memory write `close_session` exists for — session_log
    persisted, dpm_profile/teaching_memory updated via one Reflect call.

    Buffer comes from Redis, not ADK session state: _record() writes it from
    a detached background task, after the tool invocation that spawned it has
    already returned, and ToolContext's state is scoped to a live invocation —
    so state written through it is not a reliable read-back path from a
    different point in time, which is exactly what this function is. (Same
    reasoning as app/artifacts_gcs.py's own docstring, for the same class of
    problem.) The write-through _record() does is what makes this readable.

    Runs the Reflect call and Firestore round-trips in a thread: this makes
    a real generate_content call plus several blocking Firestore round
    trips, and awaited inline that would stall the whole event loop — and
    with it every concurrent student's audio stream — for however long that
    takes, exactly what app.user_auth.verify_token's own asyncio.to_thread
    call exists to avoid a few hundred lines up in this same file.

    Never raised past this function: a memory-write failure must not
    prevent the WebSocket from closing cleanly.
    """
    try:
        buffer = await short_term.get_turn_buffer(session_id, student_id)
        if not buffer:
            return
        state = sessions.get(session_id, student_id=student_id)

        def _flush() -> None:
            from google import genai

            conn = store.connect()
            client = genai.Client()
            _close_session_memory(
                conn, session_id, student_id, state.started_at, buffer, client,
            )

        await asyncio.to_thread(_flush)
        await short_term.clear_session(session_id, student_id)
        log.info("session memory flushed: %s turn(s)", len(buffer))
    except Exception:  # noqa: BLE001 - closing the socket must not fail on this
        log.warning("failed to flush session memory for %s", session_id, exc_info=True)


async def send_control(ws: WebSocket, **payload) -> None:
    """Our own messages, namespaced so they can't be confused with ADK events."""
    try:
        await ws.send_text(json.dumps({"nityam": payload}))
    except (RuntimeError, WebSocketDisconnect):
        pass


_HEARTBEAT_INTERVAL_S = 20  # well under short_term._HEARTBEAT_TTL_SECONDS (60s)


async def heartbeat(session_id: str) -> None:
    """Tell the Observatory this connection is live, for as long as it is.

    Refreshing this only as a side effect of a TutorAgent delegation (as
    append_turn/append_artifact_event already do) leaves the Observatory
    showing "closed" for every stretch of a real conversation that doesn't
    delegate — which is most of one. This task owns the signal directly, tied
    to the WebSocket's own lifetime instead.
    """
    while True:
        try:
            await short_term.touch_heartbeat(session_id)
        except Exception:  # noqa: BLE001 - a Redis outage must not break a live turn
            pass
        await asyncio.sleep(_HEARTBEAT_INTERVAL_S)


async def _transcript_writer(queue: asyncio.Queue) -> None:
    """Drains transcript turns in the order trace() saw them. One
    consumer, not one task per turn -- see _record_turn's docstring.

    Numbers the turns as it goes. This is the ONLY ordered consumer of the
    queue, so it is the only place in the system that can honestly say
    "this is the nth turn of this session" -- and a number is required:
    memory/schemas.py's `Turn` declares `turn: int = Field(ge=1)`, so the
    hardcoded 0 this used to write failed validation inside
    session_close.close_session for EVERY turn. That failure was swallowed
    by _flush_session_memory's own broad except, so the visible symptom was
    not an error but silence: no SessionLog was ever persisted, no Reflect
    call ever ran, and dpm_profile/teaching_memory never updated, in any
    session. Counting here (and pre-incrementing, so the first turn is 1,
    not 0) is what makes the durable memory write actually happen.
    """
    counters: dict[tuple[str, str], int] = {}
    while True:
        session_id, student_id, role, text = await queue.get()
        try:
            key = (session_id, student_id)
            counters[key] = counters.get(key, 0) + 1
            await short_term.append_turn(
                session_id, student_id,
                {"turn": counters[key], "role": role, "text": text[:2000],
                 "concept_id": None, "artifact_id": None},
            )
        except Exception:  # noqa: BLE001 - a Redis outage must not break a live turn
            log.warning("transcript recording failed", exc_info=True)
        finally:
            queue.task_done()


async def outbound(ws: WebSocket, session_id: str) -> None:
    """board outbox -> browser. One canvas patch per frame, in order."""
    state = sessions.get(session_id)
    while True:
        patch = await state.outbox.get()
        payload = patch.model_dump(exclude_none=True)
        # INFO gets the shape, DEBUG (the file) gets the whole block. An
        # artifact's IR is several kilobytes and belongs in exactly one of those.
        log.info("→ patch %s", payload.get("op", "?"))
        log.debug("patch in full: %s", json.dumps(payload, ensure_ascii=False))
        await send_control(ws, kind="canvas_patch", patch=payload)


# --------------------------------------------------------- shared upstream

async def read_client(ws: WebSocket, session_id: str, sink) -> None:
    """browser -> `sink`, which is whatever can accept text/audio this run.

    `sink` is a small adapter rather than the LiveRequestQueue directly, so the
    mock path and the real path share every message-decoding branch below —
    the branches are where the protocol bugs live, and they should only exist
    once.
    """
    state = sessions.get(session_id)
    frames = 0
    audio_bytes = 0
    while True:
        msg = await ws.receive()
        if msg.get("type") == "websocket.disconnect":
            raise WebSocketDisconnect(msg.get("code", 1000))

        if msg.get("bytes") is not None:
            # Raw PCM16 @16kHz mono, straight off the AudioWorklet. ADK does no
            # format conversion — the wrong rate is garbage, not an error.
            frames += 1
            audio_bytes += len(msg["bytes"])
            # Every frame would be 50 lines a second. A running total every few
            # seconds answers the question the frames are there to answer: is
            # the microphone actually reaching this process at all? Silence in
            # this counter is the signature of the mute/StrictMode class of bug.
            if frames % 250 == 0:
                log.debug(
                    "mic: %s frames, %.1fs of audio (%.0f kB)",
                    frames, audio_bytes / 32000, audio_bytes / 1000,
                )
            sink.audio(msg["bytes"])
            continue

        if msg.get("text") is None:
            continue

        try:
            payload = json.loads(msg["text"])
        except json.JSONDecodeError:
            continue
        kind = payload.get("type")

        if kind == "text" and payload.get("text"):
            logs.heard(payload["text"])
            log.info('  student typed: "%s"', payload["text"][:120])
            sink.text(payload["text"])

        elif kind == "start":
            incoming.apply_plan(state, payload)
            log.info("session plan: %s", state.plan)
            # Brief the voice layer NOW, before the greeting. This is the
            # window: the frontend sends `start` and `greet` on the same tick in
            # that order, so the topic, the student's record and their own
            # teacher's words are in context before the first turn. Without it
            # VoiceAgent has to delegate every question, however small.
            try:
                line = briefing.brief_voice_layer(session_id, state.student_id, sink)
                # Tell the refresh path what the voice layer has already been
                # handed, so the first specialist call of the session doesn't
                # re-inject a byte-identical copy of it.
                specialist_runner.note_brief_sent(session_id, line)
            except Exception:  # noqa: BLE001 - a lesson must start regardless
                log.exception("could not brief the voice layer")

        elif kind == "greet":
            # The agent is told to open the conversation, but nothing makes it
            # take a turn on its own — the Live API waits for input. So hand it
            # a stage direction the student never sees.
            topic = ""
            if state.board.pages and state.board.pages[0].blocks:
                topic = getattr(state.board.pages[0].blocks[0], "text", "")
            sink.text(incoming.describe_greeting(state, topic))

        elif kind == "gesture" and payload.get("packet"):
            packet = payload["packet"]
            state.screen.lastMarked = packet
            ask = bool(payload.get("ask"))
            line = incoming.describe_gesture(packet, ask=ask)
            log.info("gesture (%s): %s", "asked" if ask else "context", line[:150])
            log.debug("gesture packet: %s", json.dumps(packet, ensure_ascii=False))
            log.debug("gesture as sent to the model: %s", line)
            logs.count("highlight")
            sink.text(line, partial=not ask)

        elif kind == "screen":
            # Not sent to the model: it would be a message per slider frame.
            # It sits in state until the tutor calls read_screen.
            incoming.apply_screen(state, payload)
            log.debug("screen: %s", json.dumps(payload, ensure_ascii=False)[:2000])

        elif kind == "textbook_clip" and payload.get("clips"):
            line = incoming.take_clip(state, payload)
            log.info("textbook clip: %s", line[:150])
            log.debug("clip payload: %s", json.dumps(payload, ensure_ascii=False)[:2000])
            logs.count("textbook clip", len(payload["clips"]))
            sink.text(line)

        elif kind == "artifact_evidence" and payload.get("event"):
            line = incoming.describe_artifact_evidence(payload)
            # CONTEXT, not a turn. Seven of these arrived in twelve seconds in
            # one session — one per slider drag — and because each completed a
            # turn, each provoked a reply that the next one cut off. She
            # announced the same simulation three times in three seconds, was
            # interrupted four times, and ended up speaking a full turn behind.
            # A discovery still deserves a real turn; ordinary fiddling does not.
            event = str(payload.get("event") or "")
            worth_saying = "discover" in event or "misconception" in event
            log.info("evidence (%s): %s",
                     "turn" if worth_saying else "context", line[:150])
            sink.text(line, partial=not worth_saying)

        elif kind == "quiz_answer":
            state.screen.quiz = {
                "checkpointId": payload.get("checkpointId"),
                "answered": True,
                "correct": bool(payload.get("correct")),
            }
            sink.text(incoming.describe_quiz_answer(payload))


# --------------------------------------------------------------- real path

class _LiveSink:
    def __init__(self, queue) -> None:
        self._queue = queue

    def audio(self, data: bytes) -> None:
        self._queue.send_realtime(
            types.Blob(mime_type="audio/pcm;rate=16000", data=data)
        )

    def text(self, text: str, partial: bool = False) -> None:
        """`partial=True` adds to the model's context WITHOUT completing the
        turn, so it does not provoke a reply.

        That distinction is what lets a highlight be the subject of a spoken
        question rather than a question of its own: the student marks a term
        and then says "what does this mean", and both have to arrive as one
        thought."""
        self._queue.send_content(
            types.Content(parts=[types.Part(text=text)]), partial=partial
        )


async def run_live(ws: WebSocket, user_id: str, session_id: str) -> None:
    run_config = build_run_config()

    # One FIFO per connection, drained by a single _transcript_writer task
    # below: this is what makes _record_turn's writes land in the order
    # trace() saw them, instead of racing each other over separate Redis
    # connections. Set here (not ws_endpoint) because only the live path
    # calls trace() at all.
    transcript_queue: asyncio.Queue = asyncio.Queue()
    _transcript_queue_context.set(transcript_queue)

    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not session:
        # Seeded state, not defaults set later: every board tool reads
        # session_id out of tool_context.state, and a tool that cannot find it
        # writes to the wrong board silently.
        await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
            state={"session_id": session_id, "student_id": user_id},
        )

    # One queue per session, never reused: the close signal persists in it, so
    # a recycled queue kills the next session the moment it arrives.
    queue = LiveRequestQueue()
    sink = _LiveSink(queue)
    # Hand the sink to the specialists. They re-brief the voice layer after
    # their own turns (specialist_runner.refresh_brief), and a tool running
    # several frames down inside another Runner has no other route back to
    # this connection.
    specialist_runner.set_live_sink(sink)

    async def downstream() -> None:
        async for event in runner.run_live(
            user_id=user_id,
            session_id=session_id,
            live_request_queue=queue,
            run_config=run_config,
        ):
            trace(event)
            await ws.send_text(
                event.model_dump_json(exclude_none=True, by_alias=True)
            )

    tasks = [
        asyncio.create_task(read_client(ws, session_id, sink)),
        asyncio.create_task(downstream()),
        asyncio.create_task(outbound(ws, session_id)),
        asyncio.create_task(heartbeat(session_id)),
        asyncio.create_task(_transcript_writer(transcript_queue)),
    ]
    try:
        # gather(..., return_exceptions=True) alone waits for ALL FIVE to
        # finish — but outbound()/heartbeat()/_transcript_writer() are
        # unconditional `while True: await queue.get()` (or sleep) loops with
        # no termination path of their own, so that never happened on an
        # ordinary disconnect and this whole function never returned.
        # Whichever task finishes FIRST (normally read_client() raising
        # WebSocketDisconnect) now cancels the rest, so the connection
        # actually tears down.
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        # _transcript_writer is one of `pending` at this point (nothing but
        # read_client's disconnect finishes first in the ordinary case) — drain
        # it before cancelling anything, or a turn enqueued right as the
        # connection closed is lost not just from the ephemeral Redis buffer
        # but from the durable session_log _flush_session_memory writes from
        # that same buffer moments later. join() returns immediately when
        # nothing is in flight, so this costs nothing in the common case;
        # bounded so a stuck Redis can't hang teardown.
        try:
            await asyncio.wait_for(transcript_queue.join(), timeout=2.0)
        except asyncio.TimeoutError:
            log.warning("transcript queue did not drain before teardown")
        for t in pending:
            t.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # gather(return_exceptions=True) swallows failures — surface them, or a
        # dead stream just looks like a silent tutor.
        for result in results:
            if isinstance(result, BaseException) and not isinstance(
                result, (WebSocketDisconnect, asyncio.CancelledError)
            ):
                log.error("stream task failed", exc_info=result)
                await send_control(
                    ws, kind="error",
                    message=f"{type(result).__name__}: {str(result)[:300]}",
                )
    finally:
        # If ws_endpoint's own task is cancelled while suspended above (a
        # server shutdown or Cloud Run scale-down sending SIGTERM),
        # asyncio.wait — unlike asyncio.gather — does not cancel its members
        # when the awaiting task itself is cancelled, so the loop body above
        # never runs. Cancel explicitly here (a no-op on tasks already done)
        # so the five tasks are never orphaned regardless of how this
        # function exits.
        for t in tasks:
            t.cancel()
        # Without this the Live API session lingers server-side and keeps
        # counting against the concurrent-session quota.
        queue.close()


def _record_turn(role: str, text: str) -> None:
    """Every settled exchange, not just delegated ones — what makes a
    specialist's "last N turns" context genuine. Enqueues onto an
    ordered per-connection queue rather than spawning an independent
    task per call: two fire-and-forget tasks each opening their own
    Redis connection raced each other and reordered/dropped entries
    under real load (~71% failure rate across reruns, confirmed) —
    a single consumer draining a FIFO queue preserves order.
    """
    ctx = _recording_context.get()
    queue = _transcript_queue_context.get()
    if ctx is None or queue is None:
        return
    session_id, student_id = ctx
    queue.put_nowait((session_id, student_id, role, text))


def trace(event) -> None:
    """One readable line per interesting event, so a manual test is verifiable.

    Audio chunks are deliberately not logged — there are hundreds per sentence
    and they would bury everything that matters.
    """
    who = event.author or "?"

    for part in event.content.parts if event.content and event.content.parts else []:
        call = part.function_call
        if call:
            if call.name == "transfer_to_agent":
                log.info("→ TRANSFER  %s hands off to %s",
                         who, (call.args or {}).get("agent_name"))
            else:
                args = str(call.args)
                log.info("→ TOOL CALL %s calls %s(%s)", who, call.name,
                         args[:200] + ("…" if len(args) > 200 else ""))
                # Truncation is right for the terminal and wrong for a record
                # you are going to read afterwards to work out what she meant.
                log.debug("  args in full: %s", args)

        # Note: for a response_scheduling=WHEN_IDLE tool — which every ask_*
        # delegation is — ADK yields no function_response Event into this
        # stream at all, so nothing hung here would ever fire for a
        # specialist. Re-briefing the voice layer after a delegation is
        # triggered from the specialist's own tool function instead
        # (agents/specialist_runner.refresh_brief).
        response = part.function_response
        if response and response.name != "transfer_to_agent":
            got = str(response.response)
            log.info("← TOOL DONE %s got %s -> %s", who, response.name,
                     got[:200] + ("…" if len(got) > 200 else ""))
            log.debug("  result in full: %s", got)

    # A consolidated transcription can be empty (end-of-turn marker); logging
    # those just adds blank lines.
    if event.output_transcription and event.partial is False:
        said = event.output_transcription.text.strip()
        if said:
            logs.spoke(said)
            log.info('  %s says: "%s"', who, said)
            _record_turn("tutor", said)
    if event.input_transcription and event.partial is False:
        heard = event.input_transcription.text.strip()
        if heard:
            # The turn clock restarts here, not when the audio started: this is
            # the moment the model decided the student had finished, and T+ is
            # meant to read as "how long since I stopped talking".
            logs.heard(heard)
            log.info('  student said: "%s"', heard)
            _record_turn("student", heard)
    if event.interrupted:
        log.info("!! INTERRUPTED %s was cut off by the student", who)


# --------------------------------------------------------------- mock path

async def run_mock(ws: WebSocket, user_id: str, session_id: str) -> None:
    """No credentials, no network: synthetic audio and a scripted board.

    Worth keeping honest rather than minimal, because it is what the frontend's
    own tests run against — the patches below travel the same sessions.publish
    -> outbox -> outbound path the real tools use, so the reducer is exercised
    for real without spending a token.
    """
    from app.mock_board import script_reply
    from app.mock_live import MockLiveSession

    live = MockLiveSession()

    class _MockSink:
        def audio(self, data: bytes) -> None:
            live.send_audio(data)

        def text(self, text: str, partial: bool = False) -> None:
            # A partial turn is context, not a question: record it and stay quiet,
            # exactly as the real path does.
            if partial:
                return
            # Keyed on the wording the real greeting uses; see
            # incoming.describe_greeting. When that wording changed this silently
            # stopped matching and the mock greeting arrived as an ordinary reply
            # several seconds late, which broke two unrelated tests.
            if "has opened" in text:
                live.greet()
            else:
                live.send_text(text)
            script_reply(session_id, text)

    async def downstream() -> None:
        async for event in live.events():
            await ws.send_text(json.dumps(event))

    mock_sink = _MockSink()
    tasks = [
        asyncio.create_task(read_client(ws, session_id, mock_sink)),
        asyncio.create_task(downstream()),
        asyncio.create_task(outbound(ws, session_id)),
    ]
    try:
        # Same fix as run_live() — see its comment there. Without cancelling
        # the rest on first completion, this gather() never returned on an
        # ordinary disconnect either.
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        # See run_live()'s matching comment: outer cancellation while
        # suspended at asyncio.wait() would otherwise orphan these tasks.
        for t in tasks:
            t.cancel()
        live.close()


# --------------------------------------------------------------- static

@app.on_event("shutdown")
async def flush_session_logs() -> None:
    """Print every open session's turn timeline on the way out.

    logs.close_session() normally runs in the WebSocket handler's `finally`,
    which never runs on Ctrl-C — so the one log you most want to read, the one
    from the session you just cut short, was the one with no summary in it.
    """
    for session_id in list(logs._OPEN):
        logs.close_session(session_id)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "mode": MODE,
        # Which memory backend is live. Reported rather than assumed: "is this
        # demo actually on Firestore" is exactly the question you cannot answer
        # by looking at the screen.
        "store": store.backend(),
        "detail": describe(),
    }


DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    # A catch-all rather than StaticFiles(html=True): the frontend is a
    # client-routed SPA, so /session and /summary are not files and would 404.
    # Registered last, so /health and /ws still win. This is also what makes the
    # whole product testable and demoable from ONE port with a real WebSocket
    # and no dev-server proxy in the middle.
    @app.get("/{path:path}")
    async def spa(path: str) -> FileResponse:
        candidate = (DIST / path).resolve()
        if path and DIST in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
else:
    @app.get("/")
    async def no_frontend() -> HTMLResponse:
        return HTMLResponse(
            "<h1>Backend is up</h1>"
            "<p>The React app is not built. Either run the Vite dev server:</p>"
            "<pre>cd frontend &amp;&amp; npm install &amp;&amp; npm run dev</pre>"
            "<p>and open <a href='http://localhost:5173'>localhost:5173</a>, "
            "or build it once with <code>npm run build</code> and reload this page.</p>",
            status_code=200,
        )
