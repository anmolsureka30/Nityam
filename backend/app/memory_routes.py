"""Read-only memory endpoints on backend/'s own FastAPI server — the same
shape as sub_modules_examples/tutor/app/app_utils/memory_routes.py's two
GET routes, so smriti-observatory/backend can proxy to either agent server
identically (see docs/superpowers/specs/2026-08-28-backend-memory-observatory-design.md).

No POST /close endpoint here: unlike the tutor scaffold, backend/'s own
_flush_session_memory (app/main.py) already calls the real close_session on
every WebSocket teardown -- there's no missing trigger to add.
"""
from __future__ import annotations

import functools

import redis as redis_sync
from fastapi import APIRouter

from app import config
from app.memory import short_term, store
from app.memory.instrumentation import MemoryEvent

router = APIRouter(prefix="/memory")


@functools.cache
def _firestore_client():
    return store.connect()


@router.get("/sessions/{session_id}/state")
async def session_state_endpoint(session_id: str, student_id: str):
    db = _firestore_client()
    profile = store.get_dpm(db, student_id)
    memory = store.get_teaching_memory(db, student_id)
    session_log = store.get_session_log(db, session_id)
    turn_buffer = await short_term.get_turn_buffer(session_id, student_id)
    return {
        "session_id": session_id,
        "student_id": student_id,
        "workflow": {"turn_buffer": turn_buffer},
        "episodic": {"session_log": session_log.model_dump(mode="json") if session_log else None},
        "long_term": {
            "dpm_profile": profile.model_dump(mode="json") if profile else None,
            "teaching_memory": memory.model_dump(mode="json") if memory else None,
        },
    }


def _read_recent_events(session_id: str) -> list[MemoryEvent]:
    try:
        client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
        raw_events = client.lrange("smriti:events:recent", 0, -1)
    except Exception:
        return []
    events = [MemoryEvent.model_validate_json(raw) for raw in raw_events]
    return [e for e in events if e.session_id == session_id]


@router.get("/sessions/{session_id}/events")
async def session_events_endpoint(session_id: str, student_id: str, trace_id: str | None = None):
    events = _read_recent_events(session_id)
    if trace_id:
        events = [e for e in events if e.trace_id == trace_id]
    return {"events": [e.model_dump(mode="json") for e in events]}
