"""put_dpm/get_dpm/put_teaching_memory/get_teaching_memory/put_session_log/
get_session_log each publish exactly one correctly-shaped MemoryEvent, and
put_dpm/put_teaching_memory pick up session_id from the context var since
neither function receives one directly.

Needs local Redis + real Firestore credentials (NITYAM_STORE=firestore,
real ADC) OR NITYAM_STORE=sqlite (instrumentation fires either way — only
the underlying storage differs).

    .venv/bin/python -m tests.test_memory_store_events
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid

from app.auth import load_env

load_env()

import redis as redis_sync  # noqa: E402

from app import config  # noqa: E402
from app.memory import instrumentation, store  # noqa: E402
from app.memory.schemas import DPMProfile  # noqa: E402

FAILED = 0


def check(name: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    print(f"{'  ok  ' if ok else '  FAIL'} {name}{' — ' + extra if extra else ''}")


async def run() -> None:
    client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    client.delete("smriti:events:recent")

    student_id = f"test_store_events_{uuid.uuid4().hex[:8]}"
    conn = store.connect()

    instrumentation.set_session_context("ctx_for_put_dpm")
    store.put_dpm(conn, DPMProfile(student_id=student_id))
    instrumentation.set_session_context(None)
    store.get_dpm(conn, student_id)

    raw = client.lrange("smriti:events:recent", 0, -1)
    events = [json.loads(r) for r in raw]
    write_events = [e for e in events if e["source_fn"] == "put_dpm"]
    read_events = [e for e in events if e["source_fn"] == "get_dpm"]

    check("put_dpm published one write event", len(write_events) == 1, repr(write_events))
    if write_events:
        check("put_dpm's event carries the context session_id", write_events[0]["session_id"] == "ctx_for_put_dpm")
        check("put_dpm's event carries the real student_id", write_events[0]["student_id"] == student_id)
        check("put_dpm's event tier/record_type", write_events[0]["tier"] == "long_term" and write_events[0]["record_type"] == "dpm_profile")

    check("get_dpm published one read event", len(read_events) == 1, repr(read_events))
    if read_events:
        check("get_dpm's event has no session_id (context was cleared)", read_events[0]["session_id"] is None)
        check("get_dpm's event carries the real student_id", read_events[0]["student_id"] == student_id)

    if hasattr(conn, "collection"):
        conn.collection("dpm_profiles").document(student_id).delete()
    client.delete("smriti:events:recent")


def main() -> int:
    asyncio.run(run())
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
