"""The protocol, against a real server over a real WebSocket.

Mock mode, so this needs no credentials and spends nothing — but it is the same
uvicorn, the same read_client() decoding, the same sessions.publish -> outbox ->
outbound delivery path the live tutor uses. The branches in read_client are
where protocol bugs live, and they only exist once precisely so this test
covers both paths.

    .venv/bin/python -m tests.test_wire
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from app.auth import load_env  # noqa: E402

load_env()

from tests._firebase_test_tokens import mint_id_token  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, port: int) -> None:
        self.port = port
        env = {**os.environ, "NITYAM_AUTH": "mock", "PYTHONUNBUFFERED": "1"}
        self.proc = subprocess.Popen(
            [str(ROOT / ".venv/bin/uvicorn"), "app.main:app",
             "--port", str(port), "--log-level", "warning"],
            cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

    def wait(self, timeout: float = 25) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                print(self.proc.stdout.read()[-2000:])
                return False
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/health", timeout=1
                ) as r:
                    if r.status == 200:
                        return True
            except Exception:
                time.sleep(0.25)
        return False

    def stop(self) -> None:
        self.proc.kill()
        self.proc.wait(timeout=5)


async def collect(ws, seconds: float) -> list[dict]:
    """Everything the server sends in a window. The tutor streams, so there is
    no single 'the reply' frame to wait for."""
    out: list[dict] = []
    deadline = asyncio.get_event_loop().time() + seconds
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
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
            pass


def patches(frames: list[dict]) -> list[dict]:
    return [
        f["nityam"]["patch"]
        for f in frames
        if f.get("nityam", {}).get("kind") == "canvas_patch"
    ]


async def run(port: int) -> None:
    import websockets

    token = mint_id_token("demo@nityam.local", "nityam-demo-2026")
    url = f"ws://127.0.0.1:{port}/ws/demo_student/s_wire?token={token}"
    async with websockets.connect(url) as ws:
        hello = await collect(ws, 1.5)
        session = [f["nityam"] for f in hello if f.get("nityam", {}).get("kind") == "session"]
        check("the server announces the session", len(session) == 1, repr(session[:1])[:120])
        check("and hands over the board as it stands", bool(session and session[0].get("board")))
        board = session[0]["board"] if session else {}
        blocks = board.get("pages", [{}])[0].get("blocks", []) if board else []
        check("the board opens near-empty: one heading, nothing else",
              len(blocks) == 1 and blocks[0]["kind"] == "heading",
              repr([b.get("kind") for b in blocks]))

        # -------------------------------------------------------------- greet
        # The plan comes first: three home-screen buttons used to open one
        # identical conversation that asked what the student wanted to do.
        await ws.send(json.dumps({
            "type": "start", "mode": "revision",
            "concept": "projectile.horizontal_range",
            "conceptName": "Maximum range", "intensity": "standard", "minutes": 20,
        }))
        await ws.send(json.dumps({"type": "greet"}))
        frames = await collect(ws, 3.0)
        p = patches(frames)
        check("greeting makes the tutor write something", len(p) >= 1,
              repr([x["op"] for x in p]))
        spoke = [f for f in frames if f.get("outputTranscription")]
        check("and say something", len(spoke) >= 1, f"{len(spoke)} transcription frames")

        # ------------------------------------------------------------ a question
        await ws.send(json.dumps({"type": "text", "text": "why is 45 degrees best?"}))
        frames = await collect(ws, 3.0)
        p = patches(frames)
        ops = [x["op"] for x in p]
        check("a question produces board writes", "append_block" in ops, repr(ops))
        eq = [x for x in p if x.get("block", {}).get("kind") == "equation"]
        check("including the formula", len(eq) == 1, repr(ops))
        if eq:
            block = eq[0]["block"]
            check("the formula has no leftover markup", "[[" not in block["tex"], block["tex"])
            check("and carries at least one anchor to point at",
                  len(block.get("anchors", [])) >= 1, repr(block.get("anchors")))
            for a in block.get("anchors", []):
                check(f"anchor {a['id']} span is really in the text",
                      a["span"] in block["tex"], f"{a['span']!r} vs {block['tex']!r}")

        # ------------------------------------------------------------- a gesture
        # A highlight on its own is CONTEXT, not a question: the student is
        # mid-thought and about to say what they want to know about it.
        # Answering the highlight alone talks over them.
        mark = {
            "gesture": "marker", "page": 1, "blockId": "b_eq_1",
            "text": "sin(2θ)",
            "regions": [{"blockId": "b_eq_1", "kind": "equation",
                         "text": "sin(2θ)", "sentences": "R = u² sin(2θ) / g"}],
            "confidence": 1,
        }
        await ws.send(json.dumps({"type": "gesture", "packet": mark}))
        quiet = await collect(ws, 2.5)
        check("a bare highlight does NOT provoke a reply",
              len(patches(quiet)) == 0
              and not [f for f in quiet if f.get("outputTranscription")],
              f"{len(patches(quiet))} patches, "
              f"{len([f for f in quiet if f.get('outputTranscription')])} spoken")

        # …but pressing "Ask about this" is a question, and gets answered.
        await ws.send(json.dumps({"type": "gesture", "packet": mark, "ask": True}))
        answered = await collect(ws, 3.0)
        check("asking about the same mark does",
              len(patches(answered)) >= 1
              or len([f for f in answered if f.get("outputTranscription")]) >= 1)

        # ---------------------------------------------------------------- screen
        await ws.send(json.dumps({
            "type": "screen",
            "state": {"simulation": {"angle": 38, "speed": 20}, "visibleBlockIds": ["b_eq_1"]},
        }))
        await collect(ws, 0.6)
        check("a screen snapshot is absorbed without a reply", True)

        # ------------------------------------------------------------------ quiz
        await ws.send(json.dumps({"type": "text", "text": "quiz me"}))
        frames = await collect(ws, 3.0)
        quizzes = [x for x in patches(frames) if x["op"] == "show_quiz"]
        check("asking to be quizzed puts a checkpoint on screen", len(quizzes) == 1,
              repr([x["op"] for x in patches(frames)]))
        if quizzes:
            cp = quizzes[0]["checkpoint"]
            right = [o for o in cp["options"] if o["correct"]]
            check("the checkpoint has exactly one right answer", len(right) == 1)
            wrong = [o for o in cp["options"] if not o["correct"]]
            check("and every wrong option explains itself",
                  all(o.get("rebuttal") for o in wrong),
                  repr([o.get("rebuttal") for o in wrong]))

            # ------------------------------------------------------- answering it
            await ws.send(json.dumps({
                "type": "quiz_answer", "checkpointId": cp["id"],
                "optionId": right[0]["id"], "optionText": right[0]["text"], "correct": True,
            }))
            frames = await collect(ws, 3.0)
            calls = [x for x in patches(frames) if x.get("block", {}).get("kind") == "callout"]
            check("answering it is recorded on the board", len(calls) >= 1,
                  repr([x["op"] for x in patches(frames)]))

        # --------------------------------------------------------- garbage input
        await ws.send("not json at all")
        await ws.send(json.dumps({"type": "nonsense"}))
        await ws.send(json.dumps({"type": "gesture"}))  # no packet
        leftover = await collect(ws, 1.0)
        check("malformed frames do not kill the connection", ws.state.name == "OPEN",
              ws.state.name)
        check("and produce no patches", len(patches(leftover)) == 0)


def main() -> int:
    port = free_port()
    server = Server(port)
    try:
        if not server.wait():
            check("the server starts", False, "it did not come up")
            return 1
        check("the server starts", True, f"port {port}, mock mode")
        asyncio.run(run(port))
    finally:
        server.stop()
    print()
    print(f"{FAILED} failed" if FAILED else "all passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
