"""The observatory router/static mount are reachable on backend/'s own
FastAPI app, and registered before the existing SPA catch-all (which would
otherwise swallow every /observatory/* request first).

    .venv/bin/python -m tests.test_observatory_mount
"""
from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from app.main import app

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def run() -> None:
    with TestClient(app) as client:
        response = client.get("/observatory/api/sessions")
        check("observatory sessions endpoint responds", response.status_code == 200, response.text)

        response = client.get("/observatory/api/sessions/does-not-exist/state", params={"student_id": "nobody"})
        check("observatory session-state endpoint responds even for an unknown session", response.status_code == 200, response.text)
        body = response.json()
        check("unknown session degrades to the documented empty shape", body["long_term"] == {"dpm_profile": None, "teaching_memory": None})


def main() -> int:
    run()
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
