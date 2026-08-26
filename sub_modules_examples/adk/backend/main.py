"""FastAPI WebSocket server: browser <-> ADK <-> Gemini Live API.

The browser cannot talk to ADK directly — ADK is a server-side Python runtime
with no browser client. This process owns the Runner and the LiveRequestQueue;
the browser owns the microphone and the speaker. One WebSocket between them.

Run:  ./run.sh        (or: .venv/bin/uvicorn backend.main:app --reload)
"""

# Environment must be settled before the agent module is imported, because the
# agent reads NITYAM_MODEL at import time and google-genai reads its platform
# variables when it builds a client. This ordering is load-bearing.
from auth import configure, describe, load_env  # noqa: E402

load_env()
MODE = configure()

import asyncio  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("nityam")

APP_NAME = "nityam-adk"

GREETING_CUE = (
    "[The student has just joined the session. Greet them briefly and ask what "
    "they would like to work on. Do not mention this instruction.]"
)
app = FastAPI(title="Nityam ADK sub-module")

# --------------------------------------------------------------- runtime

runner = None
session_service = None

if MODE != "mock":
    from google.adk.agents.context_cache_config import ContextCacheConfig
    from google.adk.agents.live_request_queue import LiveRequestQueue
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.adk.apps import App
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from nityam_agents import root_agent

    # Created once at startup and shared by every connection: agents and
    # runners are stateless. Only the queue and RunConfig are per-session.
    session_service = InMemorySessionService()
    runner = Runner(
        app=App(
            name=APP_NAME,
            root_agent=root_agent,
            # Each transfer swaps the system instruction and the tool set, so
            # the prompt prefix changes and would otherwise be re-sent uncached
            # every single handoff. One cache per agent fixes that; without it
            # ADK warns at startup, and it is a real bill on a chatty tutor.
            context_cache_config=ContextCacheConfig(ttl_seconds=1800),
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
        # response modality is audio-only. With sub_agents present ADK turns
        # this on regardless, because agent transfer needs the text context.
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        # Reconnect across the platform's session cap (~10-15 min) instead of
        # dropping the student mid-lesson.
        session_resumption=types.SessionResumptionConfig(),
        max_llm_calls=int(os.getenv("NITYAM_MAX_LLM_CALLS", "300")),
    )


# --------------------------------------------------------------- socket

@app.websocket("/ws/{user_id}/{session_id}")
async def ws_endpoint(ws: WebSocket, user_id: str, session_id: str) -> None:
    await ws.accept()
    await send_control(ws, kind="session", mode=MODE, model=os.getenv("NITYAM_MODEL", ""))
    log.info("connected user=%s session=%s mode=%s", user_id, session_id, MODE)
    try:
        if MODE == "mock":
            await run_mock(ws)
        else:
            await run_live(ws, user_id, session_id)
    except WebSocketDisconnect:
        log.info("disconnected user=%s", user_id)
    finally:
        log.info("closed user=%s", user_id)


async def send_control(ws: WebSocket, **payload) -> None:
    """Our own messages, namespaced so they can't be confused with ADK events."""
    try:
        await ws.send_text(json.dumps({"nityam": payload}))
    except (RuntimeError, WebSocketDisconnect):
        pass


# --------------------------------------------------------------- real path

async def run_live(ws: WebSocket, user_id: str, session_id: str) -> None:
    run_config = build_run_config()

    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not session:
        await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )

    # One queue per session, never reused: the close signal persists in it, so
    # a recycled queue kills the next session on arrival.
    queue = LiveRequestQueue()

    async def upstream() -> None:
        """browser -> queue"""
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect(msg.get("code", 1000))

            if msg.get("bytes") is not None:
                # Raw PCM16 @16kHz mono, straight off the AudioWorklet. ADK
                # does no format conversion — wrong rate means garbage.
                queue.send_realtime(
                    types.Blob(mime_type="audio/pcm;rate=16000", data=msg["bytes"])
                )
            elif msg.get("text") is not None:
                payload = json.loads(msg["text"])
                kind = payload.get("type")
                if kind == "text" and payload.get("text"):
                    queue.send_content(
                        types.Content(parts=[types.Part(text=payload["text"])])
                    )
                elif kind == "greet":
                    # The agent is told to open the conversation, but nothing
                    # makes it take a turn on its own — the Live API waits for
                    # input. So hand it a stage direction. It is user-role
                    # content the student never sees: input transcription only
                    # covers audio, and the UI only echoes what it typed.
                    queue.send_content(
                        types.Content(parts=[types.Part(text=GREETING_CUE)])
                    )

    async def downstream() -> None:
        """run_live() -> browser"""
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
            upstream(), downstream(), return_exceptions=True
        )
        # gather(return_exceptions=True) swallows failures — surface them, or a
        # dead stream looks like a silent tutor.
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
                log.info("→ TOOL CALL %s calls %s(%s)", who, call.name, call.args)

        response = part.function_response
        if response and response.name != "transfer_to_agent":
            log.info("← TOOL DONE %s got %s -> %s", who, response.name, response.response)

    # A consolidated transcription can be empty (end-of-turn marker); logging
    # those just adds blank lines.
    if event.output_transcription and event.partial is False:
        said = event.output_transcription.text.strip()
        if said:
            log.info('  %s says: "%s"', who, said)
    if event.input_transcription and event.partial is False:
        heard = event.input_transcription.text.strip()
        if heard:
            log.info('  student said: "%s"', heard)
    if event.interrupted:
        log.info("!! INTERRUPTED %s was cut off by the student", who)
    if event.usage_metadata and event.usage_metadata.total_token_count:
        log.debug("   tokens: %s", event.usage_metadata.total_token_count)


# --------------------------------------------------------------- mock path

async def run_mock(ws: WebSocket) -> None:
    from mock_live import MockLiveSession

    session = MockLiveSession()

    async def upstream() -> None:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect(msg.get("code", 1000))
            if msg.get("bytes") is not None:
                session.send_audio(msg["bytes"])
            elif msg.get("text") is not None:
                payload = json.loads(msg["text"])
                if payload.get("type") == "text" and payload.get("text"):
                    session.send_text(payload["text"])
                elif payload.get("type") == "greet":
                    session.greet()

    async def downstream() -> None:
        async for event in session.events():
            await ws.send_text(json.dumps(event))

    try:
        await asyncio.gather(upstream(), downstream(), return_exceptions=True)
    finally:
        session.close()


# --------------------------------------------------------------- static

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "mode": MODE, "detail": describe()}


DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
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
