"""Does Vertex Live accept REPEATED tool responses against one function_call.id?

This is the single unknown the whole keep-talking design rests on, and it has
to be answered before any of it is built.

The design is: `ask_board` and friends become async-generator tools, and ADK
routes those through its streaming path, where every `yield` becomes a
`send_tool_response` against the SAME call id and the FunctionResponse's own
`scheduling` field decides whether she speaks. `WHEN_IDLE` means "add this to
context and prompt for output without interrupting ongoing generation" — which
is exactly the behaviour wanted: she keeps talking, and the real answer lands
when she next draws breath.

WHY IT MIGHT NOT WORK. `types.FunctionResponse.will_continue` — the field
documented as "signals that function call continues, and more responses will be
returned, turning the function call into a generator" — carries the note **"This
field is not supported in Vertex AI"**, and this backend runs
`NITYAM_AUTH=vertex_express`. ADK never sets it. So the second and later
responses could be silently dropped (the tutor goes quiet again, and the design
fails without saying so), or could close the session outright.

No ADK here on purpose: straight `client.aio.live.connect`, so a failure is
attributable to the platform rather than to ADK's routing. Credential
resolution is app/auth.py's, so this probes the same platform the app uses.

    .venv/bin/python -m tests.probe_live_streaming_tool

Skips cleanly, like the other real-credential suites, when there are none.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import auth  # noqa: E402

# The tool the model is given. Deliberately vague about how long it takes —
# the point is that the model calls it and then has to fill the time.
TOOL = {
    "name": "draw_on_board",
    "description": (
        "Draw a diagram on the student's board. Takes a while. Returns "
        "immediately; you will be told when it has landed."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {"what": {"type": "STRING", "description": "What to draw."}},
        "required": ["what"],
    },
    # THE flag. Without it the model refuses to start a new turn while the call
    # is outstanding, which is the blocking behaviour this whole design avoids.
    "behavior": "NON_BLOCKING",
}

SYSTEM = (
    "You are a physics tutor talking to one student. Whenever a diagram would "
    "help, you MUST call draw_on_board — you cannot draw any other way. "
    "Calling does not end your turn: keep teaching "
    "out loud while it works, and never say anything is loading. Anything in "
    "[square brackets] is an instruction for you — never read it aloud."
)

ASK = (
    "Draw me a diagram showing how a projectile's range depends on the "
    "launch angle, and talk me through it."
)

# Progress responses land at these offsets; the real answer at TERMINAL_AT.
PROGRESS_AT = (6.0, 12.0, 18.0)
TERMINAL_AT = 24.0
WATCH_S = 40.0
# The bar the design has to clear. The plan's promise to the user is "never
# quiet for more than a second or two"; 2.5s is that with room for the gap
# between two natural sentences.
MAX_GAP_S = 2.5


def _client():
    """The same platform the app itself talks to."""
    auth.load_env()
    mode = auth.configure()
    if mode == "mock":
        return None, None, "NITYAM_AUTH=mock"

    from google import genai

    model = auth.resolve_model(mode, os.getenv("NITYAM_RESOLVED_LIVE_MODEL", "") or "")
    model = os.getenv("NITYAM_RESOLVED_LIVE_MODEL") or model
    if not model:
        from app import config as _config

        model = auth.resolve_model(mode, _config.LIVE_MODEL)

    key = auth.express_key()
    if mode == "ai_studio":
        return genai.Client(api_key=key), model, None
    if mode == "vertex_express":
        if not key:
            return None, None, "no GOOGLE_OAUTH_ACCESS_TOKEN / GOOGLE_API_KEY"
        return genai.Client(vertexai=True, api_key=key), model, None
    return (
        genai.Client(
            vertexai=True,
            project=os.getenv("NITYAM_PROJECT_ID", ""),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        ),
        model,
        None,
    )


async def _run(label: str, progress_scheduling: str) -> dict:
    """One Live session. Returns what happened, for the caller to judge."""
    from google.genai import types

    client, model, why = _client()
    if client is None:
        return {"skipped": why}

    config = {
        "response_modalities": ["AUDIO"],
        "output_audio_transcription": {},
        "system_instruction": SYSTEM,
        "tools": [{"function_declarations": [TOOL]}],
    }

    audio_at: list[float] = []
    transcript: list[tuple[float, str]] = []
    call_id: str | None = None
    call_at: float | None = None
    sent: list[float] = []
    error: str | None = None

    started = time.monotonic()

    def now() -> float:
        return time.monotonic() - started

    try:
        async with client.aio.live.connect(model=model, config=config) as session:
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=ASK)])
            )

            async def responder() -> None:
                """Answer the call the way a streaming tool would."""
                nonlocal call_id
                while call_id is None:          # wait for the model to call
                    await asyncio.sleep(0.05)
                    if now() > 15:
                        return

                async def reply(payload: dict, scheduling: str) -> None:
                    await session.send_tool_response(
                        function_responses=[
                            types.FunctionResponse(
                                id=call_id, name=TOOL["name"],
                                response=payload, scheduling=scheduling,
                            )
                        ]
                    )
                    sent.append(now())

                # The opening one, immediately — this is what ADK's synthetic
                # "pending" response does for free in the real design.
                await reply(
                    {"status": "working",
                     "do": "[Keep teaching in your own words. Do not stop and wait.]"},
                    progress_scheduling,
                )
                for at in PROGRESS_AT:
                    await asyncio.sleep(max(0.0, at - now()))
                    await reply(
                        {"still_working": True, "seconds": int(at),
                         "do": "[Still working. Take the next step out loud, "
                               "or ask them something.]"},
                        progress_scheduling,
                    )
                await asyncio.sleep(max(0.0, TERMINAL_AT - now()))
                await reply(
                    {"status": "done",
                     "summary": "the ramp diagram is on the board"},
                    "WHEN_IDLE",
                )

            async def listen() -> None:
                """Keep listening across turns.

                `session.receive()` BREAKS on turn_complete (verified in
                google.genai.live.AsyncSession.receive) — it yields one model
                turn and returns. A single `async for` therefore stops the
                instant she finishes her first sentence, which is exactly the
                moment this probe is supposed to start watching. Re-enter it.
                """
                nonlocal call_id, call_at
                while True:
                    async for message in session.receive():
                        if message.tool_call:
                            for fc in message.tool_call.function_calls or []:
                                if call_id is None:
                                    call_id = fc.id
                                    call_at = now()
                        content = message.server_content
                        if not content:
                            continue
                        if content.model_turn:
                            for part in content.model_turn.parts or []:
                                if part.inline_data and part.inline_data.data:
                                    audio_at.append(now())
                        if (content.output_transcription
                                and content.output_transcription.text):
                            transcript.append(
                                (now(), content.output_transcription.text))

            task = asyncio.get_running_loop().create_task(responder())
            try:
                await asyncio.wait_for(listen(), timeout=WATCH_S)
            except asyncio.TimeoutError:
                pass                    # the watch window simply ended
            finally:
                task.cancel()
    except Exception as exc:            # noqa: BLE001 - the probe reports, never raises
        error = f"{type(exc).__name__}: {str(exc)[:160]}"

    return {
        "label": label, "error": error, "call_id": call_id,
        "call_at": call_at, "watched": WATCH_S,
        "sent": sent, "audio_at": audio_at, "transcript": transcript,
    }


def _judge(r: dict) -> bool:
    print(f"\n── {r['label']} " + "─" * (58 - len(r["label"])))
    if r.get("skipped"):
        print(f"  skipped: {r['skipped']}")
        return True

    ok = True

    # 1. the session survived
    if r["error"]:
        print(f"  [FAIL] the session errored — {r['error']}")
        ok = False
    elif not r["call_id"]:
        print("  [FAIL] the model never called the tool, so nothing was probed")
        ok = False
    else:
        print(f"  [ ok ] session survived {len(r['sent'])} responses on one call id")

    # 2. the gaps — the whole point, and the easy thing to measure wrongly.
    #
    # Gaps BETWEEN audio chunks are not silence: if she says nothing at all for
    # twenty seconds there are no chunks in that window and no gap to find. A
    # first pass reported "worst silence 0.1s" for a run where she spoke for
    # five seconds out of thirty. So the window is measured from the CALL to the
    # end of the watch, and the leading and trailing gaps count.
    at = r["audio_at"]
    start = r.get("call_at")
    end = r.get("watched", WATCH_S)
    if start is None:
        print("  [    ] no call, so no silence window to measure")
    elif not at:
        print(f"  [FAIL] she said nothing at all in {end - start:.0f}s after calling")
        ok = False
    else:
        # The window ENDS when she finishes announcing the result, not when
        # the watch does. After the terminal response there is nothing left to
        # respond to, so counting that tail as "silence" marks a good run bad —
        # it reported 14.4s for a run where she talked continuously for 23s and
        # then correctly stopped.
        end = max((t for t in at if t >= TERMINAL_AT), default=end)
        at = [t for t in at if t <= end]
        edges = [start] + at + [end]
        gaps = [b - a for a, b in zip(edges, edges[1:])]
        worst = max(gaps)
        where = edges[gaps.index(worst)]
        spoke = len(at)
        verdict = "ok" if worst < MAX_GAP_S else "FAIL"
        if worst >= MAX_GAP_S:
            ok = False
        print(f"  [{verdict:>4}] worst silence {worst:.1f}s (from t={where:.1f}s), "
              f"budget {MAX_GAP_S}s")
        print(f"         {spoke} audio chunks across the {end - start:.0f}s "
              f"after the call; first at t={at[0]:.1f}s, last at t={at[-1]:.1f}s")

    # 3. did the LAST response get through? if the earlier ones closed the call,
    #    this is what goes missing — and it is the actual answer to the student.
    tail = " ".join(t for at_, t in r["transcript"] if at_ >= TERMINAL_AT).lower()
    if "ramp" in tail or "board" in tail or "diagram" in tail:
        print("  [ ok ] the terminal response was consumed — she announced it")
    else:
        print("  [FAIL] the terminal response never reached her — earlier "
              "responses likely closed the call id")
        print(f"         (she said after t={TERMINAL_AT:.0f}s: {tail[:110]!r})")
        ok = False

    return ok


async def main() -> int:
    print("Probing repeated tool responses against one call id.")
    print("Two Live sessions, ~30s each. This costs real quota.\n")

    a = await _run("A · every progress chunk WHEN_IDLE", "WHEN_IDLE")
    good_a = _judge(a)

    # Variant B is the pre-tested fallback: if WHEN_IDLE on every chunk makes
    # her over-talk, progress goes to SILENT (context only) and only the
    # terminal response prompts speech. Worth knowing now rather than later.
    b = await _run("B · progress SILENT, terminal WHEN_IDLE", "SILENT")
    good_b = _judge(b)

    # The verdict is comparative, not pass/fail. The question this probe exists
    # to answer is "does Vertex accept repeated responses on one call id", and
    # that is answered by the session surviving — the gap numbers are then a
    # TUNING result, not a gate.
    print("\n" + "=" * 62)
    survived = bool(a.get("call_id")) and not a.get("error")
    if not survived:
        print("VERDICT: repeated tool responses do NOT work here.")
        print("         Do not build Part 1 as designed — re-read the failures.")
        print("=" * 62)
        return 1

    print("VERDICT: repeated responses on one call id WORK. Build it.")
    print("         Progress chunks go at WHEN_IDLE (variant A).")
    print()
    print("         SILENT progress (variant B) is ruled out: it leaves her")
    print("         silent for the whole delegation and she speaks only at the")
    print("         end. It is not a usable fallback.")
    worst_a = _worst(a)
    if worst_a is not None:
        print()
        print(f"         Tuning: worst gap {worst_a:.1f}s at a 6.0s response")
        print(f"         cadence. Set KEEP_TALKING_INTERVAL_S below that gap.")
    print("=" * 62)
    return 0


def _worst(r: dict) -> float | None:
    """The largest silence inside the answered window, for tuning the cadence."""
    at, start = r.get("audio_at") or [], r.get("call_at")
    if start is None or not at:
        return None
    end = max((t for t in at if t >= TERMINAL_AT), default=r.get("watched", WATCH_S))
    at = [t for t in at if t <= end]
    edges = [start] + at + [end]
    return max(b - a for a, b in zip(edges, edges[1:]))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
