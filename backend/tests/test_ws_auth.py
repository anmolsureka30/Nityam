"""Auth on the WebSocket handshake, against a real server process (mock mode,
so this needs no model credentials and spends nothing): no token, a garbage
token, and a valid token with the wrong uid are all rejected — closed with
4401, but only after the browser actually receives the
`{nityam:{kind:"error",...}}` frame explaining why. A valid token with a
matching uid connects normally.

    .venv/bin/python -m tests.test_ws_auth
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


async def expect_rejected(url: str, name: str) -> None:
    import websockets
    from websockets.exceptions import ConnectionClosed

    async with websockets.connect(url) as ws:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
        except ConnectionClosed as exc:
            check(f"{name}: sends an error frame before closing", False, "closed with no frame")
            check(f"{name}: closes with 4401", exc.code == 4401, f"got {exc.code!r}")
            return

        frame = json.loads(raw)
        check(
            f"{name}: sends an error frame before closing",
            frame.get("nityam", {}).get("kind") == "error",
            repr(frame)[:150],
        )
        try:
            await asyncio.wait_for(ws.recv(), timeout=2.0)
            check(f"{name}: closes with 4401", False, "connection stayed open")
        except ConnectionClosed as exc:
            check(f"{name}: closes with 4401", exc.code == 4401, f"got {exc.code!r}")


async def run(port: int) -> None:
    import websockets

    token = mint_id_token("demo@nityam.local", "nityam-demo-2026")

    await expect_rejected(f"ws://127.0.0.1:{port}/ws/demo_student/s_auth_1", "no token")
    await expect_rejected(
        f"ws://127.0.0.1:{port}/ws/demo_student/s_auth_2?token=not-a-real-token",
        "garbage token",
    )
    await expect_rejected(
        f"ws://127.0.0.1:{port}/ws/someone_else/s_auth_3?token={token}",
        "valid token, wrong uid",
    )

    url = f"ws://127.0.0.1:{port}/ws/demo_student/s_auth_4?token={token}"
    async with websockets.connect(url) as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
        frame = json.loads(raw)
        check(
            "valid token, matching uid: connects normally",
            frame.get("nityam", {}).get("kind") == "session",
            repr(frame)[:150],
        )


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
