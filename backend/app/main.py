"""FastAPI WebSocket server: browser <-> ADK <-> Gemini Live.

The browser cannot talk to ADK directly — ADK is a server-side Python runtime
with no browser client. This process owns the Runner, the LiveRequestQueue and
the board; the browser owns the microphone, the speaker and the page.
One WebSocket between them.

Five concurrent tasks per connection:

    read_client() browser -> LiveRequestQueue     (mic, text, gestures, screen)
    downstream()  runner.run_live() -> browser    (audio, transcripts, tool calls)
    outbound()    board outbox -> browser         (canvas patches)
    nudges()      background work -> the model    (an artifact finished building)
    injections()  board state -> the model        (context only; she must not reply)

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
import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app import incoming, sessions  # noqa: E402

from app import logs  # noqa: E402

logs.setup()
log = logging.getLogger("nityam")

APP_NAME = "nityam"

app = FastAPI(title="Nityam backend")

# --------------------------------------------------------------- runtime

runner = None
session_service = None

if MODE != "mock":
    from google.adk.agents.live_request_queue import LiveRequestQueue
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.adk.apps import App
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from app.agents.brain import _cache_config
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
            # See brain._cache_config: caching 404s on the express-mode
            # endpoint, so it is opt-in via NITYAM_CONTEXT_CACHE rather than
            # logging a failure on every turn.
            context_cache_config=_cache_config(),
        ),
        session_service=session_service,
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
        # Prints the turn timeline to the terminal and appends it to the file.
        logs.close_session(session_id)


async def send_control(ws: WebSocket, **payload) -> None:
    """Our own messages, namespaced so they can't be confused with ADK events."""
    try:
        await ws.send_text(json.dumps({"nityam": payload}))
    except (RuntimeError, WebSocketDisconnect):
        pass


async def nudges(sink, session_id: str) -> None:
    """Background work -> the live conversation, as a COMPLETED turn.

    An artifact takes half a minute to build, so the tutor starts it and keeps
    teaching. This is how it finds out the thing landed: a completed turn, not
    a partial one, because she is supposed to interrupt herself and say so.
    """
    state = sessions.get(session_id)
    while True:
        text = await state.nudges.get()
        log.info("nudge: %s", text[:140])
        log.debug("nudge in full: %s", text)
        sink.text(text)


async def injections(sink, session_id: str) -> None:
    """Background work -> the live conversation, as CONTEXT ONLY.

    The sibling of nudges() and the opposite half of the same idea: a nudge
    makes her talk, an injection makes her *know*. Board writes and the
    session's grounding pack arrive here, as partial content, so she can answer
    "which formula was it?" or "did that go on the board?" herself instead of
    spending nine seconds asking the reasoning layer what it just did.

    Two tasks rather than one because a single task awaiting two queues would
    have to poll or race; `asyncio.Queue.get()` on its own coroutine is the
    honest way to wait on both.
    """
    state = sessions.get(session_id)
    while True:
        text = await state.context.get()
        log.info("→ context: %s", text[:140])
        log.debug("context in full: %s", text)
        sink.text(text, partial=True)


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
            from app import briefing

            try:
                briefing.brief_voice_layer(session_id, state.student_id)
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

    try:
        results = await asyncio.gather(
            read_client(ws, session_id, sink),
            downstream(),
            outbound(ws, session_id),
            nudges(sink, session_id),
            injections(sink, session_id),
            return_exceptions=True,
        )
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
        # Without this the Live API session lingers server-side and keeps
        # counting against the concurrent-session quota.
        queue.close()


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
    if event.input_transcription and event.partial is False:
        heard = event.input_transcription.text.strip()
        if heard:
            # The turn clock restarts here, not when the audio started: this is
            # the moment the model decided the student had finished, and T+ is
            # meant to read as "how long since I stopped talking".
            logs.heard(heard)
            log.info('  student said: "%s"', heard)
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

    try:
        mock_sink = _MockSink()
        await asyncio.gather(
            read_client(ws, session_id, mock_sink),
            downstream(),
            outbound(ws, session_id),
            nudges(mock_sink, session_id),
            injections(mock_sink, session_id),
            return_exceptions=True,
        )
    finally:
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
    from app.memory import store

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
