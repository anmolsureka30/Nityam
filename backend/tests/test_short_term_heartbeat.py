"""append_turn/append_artifact_event refresh a session-scoped heartbeat key
(`session:{session_id}:heartbeat`, not student-namespaced — carries no data,
just a liveness flag) with a short TTL, and clear_session deletes it
immediately on close. This is what smriti-observatory/backend's
list_sessions() checks to report a session's status as "live" vs "closed"
(observatory/routes_rest.py's `client.exists(f"session:{session_id}:
heartbeat")`) -- without this, backend/'s sessions would never show as live
there, even mid-conversation.

    .venv/bin/python -m tests.test_short_term_heartbeat
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from app.auth import load_env

load_env()

import redis as redis_sync  # noqa: E402

from app import config  # noqa: E402
from app.memory import short_term  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


async def run() -> None:
    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    session_id = f"test_heartbeat_{uuid.uuid4().hex[:8]}"
    student_id = "demo_student"
    key = f"session:{session_id}:heartbeat"

    client.delete(key)
    await short_term.append_turn(session_id, student_id, {"turn": 1, "role": "student", "text": "hi", "concept_id": None, "artifact_id": None})
    check("append_turn sets the heartbeat key", client.exists(key) == 1)
    ttl = client.ttl(key)
    check("the heartbeat key has a short, positive TTL", 0 < ttl <= 60, repr(ttl))

    await short_term.append_artifact_event(session_id, student_id, {"event": "discovered_optimum", "artifact_id": "art_1"})
    check("append_artifact_event also refreshes the heartbeat key", client.exists(key) == 1)

    await short_term.clear_session(session_id, student_id)
    check("clear_session deletes the heartbeat key", client.exists(key) == 0)


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
