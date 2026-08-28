"""close_session is now actually invoked when a WebSocket session ends —
before this task it silently never was, and only the debug log file got
closed. Needs real credentials (NITYAM_AUTH != mock) because
_flush_session_memory is deliberately a no-op in mock mode — see this
task's own note in the plan. Seeds a turn into Memorystore under the test's
session id (bypassing an actual live conversation, which this test isn't
about), connects just long enough to get the session frame, disconnects, and
checks the store for a session_log afterward.

    NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_close_session_wiring
"""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from app.auth import load_env  # noqa: E402

load_env()

from app.memory import short_term, store  # noqa: E402
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
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}  # real NITYAM_AUTH, inherited as-is
        self.proc = subprocess.Popen(
            [str(ROOT / ".venv/bin/uvicorn"), "app.main:app",
             "--port", str(port), "--log-level", "warning"],
            cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

    def wait(self, timeout: float = 30) -> bool:
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
                time.sleep(0.3)
        return False

    def stop(self) -> None:
        self.proc.kill()
        self.proc.wait(timeout=5)


async def run(port: int, session_id: str) -> None:
    import websockets

    await short_term.append_turn(session_id, {
        "turn": 1, "role": "student", "text": "why 45 degrees?",
        "concept_id": "projectile.horizontal_range", "artifact_id": None,
    })
    await short_term.append_turn(session_id, {
        "turn": 2, "role": "tutor", "text": "because sin(2θ) peaks there",
        "concept_id": "projectile.horizontal_range", "artifact_id": None,
    })

    token = mint_id_token("demo@nityam.local", "nityam-demo-2026")
    url = f"ws://127.0.0.1:{port}/ws/demo_student/{session_id}?token={token}"
    async with websockets.connect(url) as ws:
        await ws.recv()  # the session frame — then disconnect immediately
    # ws_endpoint's finally block runs server-side after the close; give the
    # one Reflect call room to finish.
    await asyncio.sleep(6.0)


def main() -> int:
    mode = os.getenv("NITYAM_AUTH", "").strip().lower()
    if mode in ("", "mock"):
        print("NITYAM_AUTH is mock or unset — nothing to test against. Skipping.")
        return 0

    port = free_port()
    session_id = f"s_close_session_wiring_{uuid.uuid4().hex[:8]}"
    server = Server(port)
    try:
        if not server.wait():
            check("the server starts against real credentials", False, "it did not come up")
            return 1
        check("the server starts against real credentials", True, f"port {port}, mode {mode}")
        asyncio.run(run(port, session_id))
    finally:
        server.stop()

    conn = store.connect()
    log = store.get_session_log(conn, session_id)
    check("a session_log now exists after the socket closes", log is not None)
    if log:
        check("it carries the turns that were in the buffer", len(log.turns) == 2, repr(log.turns))

    print()
    print(f"{FAILED} failed" if FAILED else "all passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
