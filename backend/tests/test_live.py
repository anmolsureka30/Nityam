"""The real thing: a live Gemini session through the real server.

Costs money and needs credentials, so it is separate from tests/test_wire.py
and skips cleanly when the preflight says voice is unavailable. What it proves
that mock mode cannot:

  * the Live model actually connects and returns audio
  * VoiceAgent delegates to TutorAgent rather than answering physics itself
  * TutorAgent's board tools fire, and the patches reach the socket
  * the whole three-task loop survives a real turn

    .venv/bin/python -m tests.test_live
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.auth import load_env  # noqa: E402

load_env()
FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def _decode(data: str) -> bytes:
    """Google emits base64url and omits the padding, so plain b64decode raises
    `binascii.Error: Incorrect padding`. The browser side already normalises
    both (frontend/src/lib/live/audio.ts); this is the same fix."""
    standard = data.replace("-", "+").replace("_", "/")
    return base64.b64decode(standard + "=" * (-len(standard) % 4))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def collect(ws, seconds: float, stop=None) -> list[dict]:
    """Frames until the window closes, or `stop` says we have what we need."""
    out: list[dict] = []
    loop = asyncio.get_event_loop()
    deadline = loop.time() + seconds
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return out
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            return out
        if isinstance(raw, bytes):
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
        if stop and stop(out):
            return out


def main() -> int:
    mode = os.getenv("NITYAM_AUTH", "").strip().lower()
    if mode in ("", "mock"):
        print("NITYAM_AUTH is mock or unset — nothing to test against. Skipping.")
        return 0

    port = free_port()
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    log_path = Path(tempfile.mkdtemp()) / "server.log"
    log_file = open(log_path, "w")
    proc = subprocess.Popen(
        [str(ROOT / ".venv/bin/uvicorn"), "app.main:app", "--port", str(port),
         "--log-level", "info"],
        cwd=ROOT, env=env, stdout=log_file, stderr=subprocess.STDOUT, text=True,
    )
    try:
        deadline = time.time() + 40
        up = False
        while time.time() < deadline:
            if proc.poll() is not None:
                print(log_path.read_text()[-2000:])
                break
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                    if r.status == 200:
                        up = True
                        break
            except Exception:
                time.sleep(0.3)
        check("the server starts against real credentials", up, f"port {port}, mode {mode}")
        if not up:
            return 1
        asyncio.run(run(port))

        # The reasoning turn happens in the brain runner, off the socket, so the
        # server log is the only place its tool calls are visible.
        log = log_path.read_text()
        check("it grounded the answer in the lecture", "search_grounding" in log,
              " ".join(sorted({
                  line.split("calls ")[1].split("(")[0]
                  for line in log.splitlines() if "TOOL CALL" in line and "calls " in line
              })) or "no tool calls logged")
        check("the brain reported back to the voice layer", "brain replied" in log,
              next((l.split("brain replied")[1][:90] for l in log.splitlines()
                    if "brain replied" in l), "it never did"))
        check("no exception reached the log",
              "Traceback" not in log and "_event_queue" not in log,
              next((l for l in log.splitlines() if "Error" in l or "Traceback" in l), "")[:120])
    finally:
        proc.kill()
        proc.wait(timeout=5)
        log_file.close()

    print()
    print(f"{FAILED} failed" if FAILED else "all passed")
    return 1 if FAILED else 0


async def run(port: int) -> None:
    import websockets

    url = f"ws://127.0.0.1:{port}/ws/demo_student/s_live_test"
    async with websockets.connect(url, max_size=None) as ws:
        hello = await collect(ws, 3.0, stop=lambda f: any(
            x.get("nityam", {}).get("kind") == "session" for x in f))
        session = next(
            (x["nityam"] for x in hello if x.get("nityam", {}).get("kind") == "session"), None
        )
        check("the session frame names the live model", bool(session and session.get("model")),
              (session or {}).get("model", "").rsplit("/", 1)[-1])

        # A real question, typed rather than spoken — same upstream path, and it
        # does not need a microphone in CI.
        await ws.send(json.dumps({
            "type": "text",
            "text": "Why is 45 degrees the best launch angle? Put the formula on my board.",
        }))

        # Live turns take a while: VoiceAgent speaks, delegates, TutorAgent runs
        # its own tool calls, then VoiceAgent speaks again.
        # She bridges, delegates, and only speaks the real answer once the brain
        # returns — which takes as long as grounding plus three board writes
        # takes. Stopping at the last patch captured only "Good question, one
        # second." and reported no transcription; stopping at the first
        # turnComplete would stop after the bridge. So: wait for a turnComplete
        # that arrives AFTER the patches.
        def done(f):
            patches = [i for i, x in enumerate(f)
                       if x.get("nityam", {}).get("kind") == "canvas_patch"]
            if len(patches) < 2:
                return False
            # The bridge and the tool call are one Live turn; the spoken answer
            # is the NEXT one. So a turnComplete after the last patch is not
            # enough — waiting on it alone caught only "Let me look at that with
            # you." Require that she has also said something since.
            tail = f[patches[-1]:]
            spoke = any(
                x.get("outputTranscription", {}).get("text") and x.get("partial") is False
                for x in tail
            )
            return spoke and any(x.get("turnComplete") for x in tail)

        frames = await collect(ws, 150.0, stop=done)

        errors = [x["nityam"]["message"] for x in frames
                  if x.get("nityam", {}).get("kind") == "error"]
        check("no stream errors", not errors, " | ".join(errors)[:200])

        audio = sum(
            len(_decode(part["inlineData"]["data"]))
            for x in frames
            for part in (x.get("content") or {}).get("parts") or []
            if (part.get("inlineData") or {}).get("mimeType", "").startswith("audio/pcm")
        )
        check("she actually speaks", audio > 20000, f"{audio // 1024} KB of audio")

        said = " ".join(
            x["outputTranscription"]["text"]
            for x in frames
            if x.get("outputTranscription", {}).get("text") and x.get("partial") is False
        ).strip()
        check("with a transcription for the caption", len(said) > 40, said[:150])
        check("she bridged before delegating, rather than going silent",
              any(w in said.lower() for w in
                  ("let me", "one sec", "achha", "good question", "hold on", "moment")),
              said[:80])

        calls = [
            part["functionCall"]["name"]
            for x in frames
            for part in (x.get("content") or {}).get("parts") or []
            if part.get("functionCall")
        ]
        check("VoiceAgent delegated rather than answering physics alone",
              "ask_tutor" in calls, str(sorted(set(calls))) or "it called nothing")

        patches = [x["nityam"]["patch"] for x in frames
                   if x.get("nityam", {}).get("kind") == "canvas_patch"]
        check("board patches reached the browser", len(patches) >= 1,
              str([p["op"] for p in patches]))

        written = [p["block"] for p in patches if p["op"] == "append_block"]
        check("including something written on the board", len(written) >= 1,
              str([b["kind"] for b in written]))

        equations = [b for b in written if b["kind"] == "equation"]
        if equations:
            tex = equations[0]["tex"]
            check("the formula is blackboard notation, not LaTeX",
                  "\\" not in tex and "{" not in tex, tex)
            check("and carries an anchor the student can point at",
                  len(equations[0].get("anchors") or []) >= 1,
                  str(equations[0].get("anchors")))
        for block in written:
            text = block.get("text") or block.get("tex") or ""
            check(f"no leftover markup in {block['id']}", "[[" not in text, text[:60])


if __name__ == "__main__":
    sys.exit(main())
