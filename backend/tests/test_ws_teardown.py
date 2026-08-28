"""ws_endpoint's `finally:` block must actually run after a real client
disconnect — before this fix, three of run_live()/run_mock()'s five gathered
tasks (outbound, nudges, injections) never terminate on their own, so
asyncio.gather(..., return_exceptions=True) waited forever for them and
`finally` never fired.

The mock-mode check always runs (free, no credentials). The live-mode check
needs real credentials and skips otherwise, matching tests/test_live.py's
own convention — downstream() calls the real Live API there, a materially
different code path from mock mode's synthetic one, so mock passing alone
does not prove run_live's fix works too.

    .venv/bin/python -m tests.test_ws_teardown
"""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import tempfile
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
    def __init__(self, port: int, extra_env: dict | None = None) -> None:
        self.port = port
        env = {**os.environ, **(extra_env or {}), "PYTHONUNBUFFERED": "1"}
        self.log_path = Path(tempfile.mkdtemp()) / "server.log"
        self.log_file = open(self.log_path, "w")
        self.proc = subprocess.Popen(
            [str(ROOT / ".venv/bin/uvicorn"), "app.main:app",
             "--port", str(port), "--log-level", "info"],
            cwd=ROOT, env=env,
            stdout=self.log_file, stderr=subprocess.STDOUT, text=True,
        )

    def wait(self, timeout: float = 30) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                print(self.log_path.read_text()[-2000:])
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

    def log(self) -> str:
        return self.log_path.read_text()

    def stop(self) -> None:
        self.proc.kill()
        self.proc.wait(timeout=5)
        self.log_file.close()


async def connect_and_disconnect(url: str) -> None:
    import websockets

    async with websockets.connect(url) as ws:
        await ws.recv()  # the session frame
    # `async with` closes the socket on exit — nothing else to do here.


def check_graceful_teardown(mode_label: str, url: str, server: Server) -> None:
    asyncio.run(connect_and_disconnect(url))
    deadline = time.time() + 10
    closed = False
    while time.time() < deadline:
        if "closed user=" in server.log():
            closed = True
            break
        time.sleep(0.3)
    check(f"{mode_label}: finally: runs within 10s of a real disconnect", closed,
          "no 'closed user=' line appeared" if not closed else "")


def main() -> int:
    # ---------------------------------------------------------- mock mode
    port = free_port()
    server = Server(port, {"NITYAM_AUTH": "mock"})
    try:
        if not server.wait():
            check("mock server starts", False, "it did not come up")
            return 1
        check("mock server starts", True, f"port {port}")
        token = mint_id_token("demo@nityam.local", "nityam-demo-2026")
        url = f"ws://127.0.0.1:{port}/ws/demo_student/s_teardown_mock?token={token}"
        check_graceful_teardown("mock mode", url, server)
    finally:
        server.stop()

    # ---------------------------------------------------------- live mode
    mode = os.getenv("NITYAM_AUTH", "").strip().lower()
    if mode in ("", "mock"):
        print("NITYAM_AUTH is mock or unset — skipping the live-mode teardown check.")
        print()
        print(f"{FAILED} failed" if FAILED else "all passed (mock-mode only)")
        return 1 if FAILED else 0

    port = free_port()
    server = Server(port)  # no override — inherits the real NITYAM_AUTH
    try:
        if not server.wait():
            check("live server starts against real credentials", False, "it did not come up")
            return 1
        check("live server starts against real credentials", True, f"port {port}, mode {mode}")
        token = mint_id_token("demo@nityam.local", "nityam-demo-2026")
        url = f"ws://127.0.0.1:{port}/ws/demo_student/s_teardown_live?token={token}"
        check_graceful_teardown("live mode", url, server)
    finally:
        server.stop()

    print()
    print(f"{FAILED} failed" if FAILED else "all passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
