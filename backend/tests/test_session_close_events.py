"""close_session's own long-term writes (put_dpm/put_teaching_memory/
put_session_log) carry the real session_id on their MemoryEvents — the one
gap none of the four DPM/TeachingMemory store functions can close on their
own, since neither function receives a session_id directly.

Needs real Gemini credentials (this calls the real reflect() LLM call) —
same requirement as test_close_session_wiring.py.

    NITYAM_AUTH=vertex_express .venv/bin/python -m tests.test_session_close_events
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone

from app.auth import configure, load_env

load_env()
configure()

import redis as redis_sync  # noqa: E402
from google import genai  # noqa: E402

from app import config  # noqa: E402
from app.memory import store  # noqa: E402
from app.session_close import close_session  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


def main() -> int:
    mode = os.getenv("NITYAM_AUTH", "").strip().lower()
    if mode in ("", "mock"):
        print("NITYAM_AUTH is mock or unset — nothing to test against. Skipping.")
        return 0

    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    client.delete("smriti:events:recent")

    session_id = f"test_session_close_events_{uuid.uuid4().hex[:8]}"
    student_id = f"test_student_{uuid.uuid4().hex[:8]}"
    buffer = [
        {"turn": 1, "role": "student", "text": "why 45 degrees?", "concept_id": "projectile.range", "artifact_id": None},
        {"turn": 2, "role": "tutor", "text": "because sin(2θ) peaks there", "concept_id": "projectile.range", "artifact_id": None},
    ]
    conn = store.connect()
    close_session(conn, session_id, student_id, datetime.now(timezone.utc), buffer, genai.Client())

    raw = client.lrange("smriti:events:recent", 0, -1)
    events = [json.loads(r) for r in raw]
    long_term_writes = [e for e in events if e["tier"] == "long_term" and e["operation"] == "write"]

    check("close_session produced at least one long-term write event", len(long_term_writes) >= 1, repr(long_term_writes))
    for e in long_term_writes:
        check(f"{e['source_fn']}'s event carries the real session_id", e["session_id"] == session_id, repr(e))

    client.delete("smriti:events:recent")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
