"""GET /memory/sessions/{id}/state and /events, served directly by
backend/'s own FastAPI app — same shape as
sub_modules_examples/tutor/app/app_utils/memory_routes.py, over real HTTP
against a spawned server (this repo's own convention — see
test_close_session_wiring.py), not FastAPI's in-process TestClient.

    .venv/bin/python -m tests.test_memory_routes
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

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
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        self.proc = subprocess.Popen(
            [str(ROOT / ".venv/bin/uvicorn"), "app.main:app",
             "--port", str(port), "--log-level", "warning"],
            cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self.port = port

    def wait(self, timeout: float = 30) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                print(self.proc.stdout.read()[-2000:])
                return False
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=1) as r:
                    if r.status == 200:
                        return True
            except Exception:
                time.sleep(0.3)
        return False

    def stop(self) -> None:
        self.proc.kill()
        self.proc.wait(timeout=5)


def main() -> int:
    from app.auth import load_env

    load_env()
    import redis as redis_sync

    from app import config

    port = free_port()
    session_id = f"test_memory_routes_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"

    redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True).rpush(
        f"session:{student_id}:{session_id}:turns",
        json.dumps({"turn": 1, "role": "student", "text": "hi", "concept_id": None, "artifact_id": None}),
    )

    server = Server(port)
    try:
        if not server.wait():
            check("the server starts", False, "it did not come up")
            return 1
        check("the server starts", True)

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/memory/sessions/{session_id}/state?student_id={student_id}"
        ) as r:
            body = json.loads(r.read())
        check("state endpoint returns the workflow turn buffer", len(body["workflow"]["turn_buffer"]) == 1, repr(body))
        check("state endpoint echoes session/student ids", (
            body["session_id"] == session_id and body["student_id"] == student_id
        ), repr(body))

        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/memory/sessions/{session_id}/events?student_id={student_id}"
        ) as r:
            events_body = json.loads(r.read())
        check("events endpoint responds with an events list", "events" in events_body, repr(events_body))
    finally:
        server.stop()
        redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True).delete(
            f"session:{student_id}:{session_id}:turns"
        )

    print()
    print(f"{FAILED} failed" if FAILED else "all passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
