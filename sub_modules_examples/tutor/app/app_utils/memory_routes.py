"""The one real production trigger for close_session — currently the only
path into episodic/long-term memory, previously invoked only by tests. See
docs/superpowers/specs/2026-08-27-smriti-observatory-design.md §6.

perform_close_session is importable so both this router's HTTP handler and
Task 7's idle-timeout background watcher call the exact same logic — no
parallel/fake close path.
"""
from __future__ import annotations

import functools
from datetime import datetime, timezone

import redis as redis_sync
from fastapi import APIRouter
from google import genai
from google.cloud import firestore
from pydantic import BaseModel

from app import config
from app.memory import short_term, store
from app.memory.diff import EnrichedEvent, diff_dpm, diff_teaching_memory
from app.memory.instrumentation import MemoryEvent
from app.memory.schemas import SessionLog
from app.session_close import close_session

router = APIRouter(prefix="/memory")


@functools.cache
def _firestore_client() -> firestore.Client:
    return store.connect()


@functools.cache
def _genai_client() -> genai.Client:
    return genai.Client()


async def perform_close_session(session_id: str, student_id: str | None = None) -> SessionLog:
    resolved_student_id = student_id or "demo_student"
    buffer = await short_term.get_turn_buffer(session_id)
    started_at = await short_term.get_started_at(session_id) or datetime.now(timezone.utc)
    log = close_session(
        _firestore_client(), session_id, resolved_student_id, started_at, buffer, _genai_client(),
    )
    await short_term.clear_session(session_id)
    return log


class CloseSessionRequest(BaseModel):
    student_id: str | None = None


@router.post("/sessions/{session_id}/close")
async def close_session_endpoint(session_id: str, body: CloseSessionRequest):
    log = await perform_close_session(session_id, body.student_id)
    return log.model_dump(mode="json")


@router.get("/sessions/{session_id}/state")
async def session_state_endpoint(session_id: str, student_id: str):
    """Current Working/Episodic/Long-Term snapshot for one session -- what
    ADK web's Memory tab shows. Same read path close_session and the tools
    already use, no separate storage."""
    db = _firestore_client()
    profile = store.get_dpm(db, student_id)
    memory = store.get_teaching_memory(db, student_id)
    session_log = store.get_session_log(db, session_id)
    turn_buffer = await short_term.get_turn_buffer(session_id)
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


def _replay_diffs(events: list[MemoryEvent], student_id: str) -> list[EnrichedEvent]:
    """Walks this session's events in the order they happened, tracking the
    last-seen dpm_profile/teaching_memory payload per record type so each
    long-term write gets a real before/after diff -- the same logic the
    live ingest pipeline used to run continuously (see the now-retired
    smriti-observatory backend's observatory/ingest.py), just computed
    on demand instead of streamed. A write with nothing seen yet in this
    session's own event log falls back to Firestore's current value, which
    is only correct for the most recent write in the whole event history —
    an accepted limitation for a rolling, non-permanent event buffer."""
    last_seen: dict[str, dict | None] = {}
    db = _firestore_client()

    def _load_dpm() -> dict | None:
        profile = store.get_dpm(db, student_id)
        return profile.model_dump(mode="json") if profile else None

    def _load_teaching_memory() -> dict | None:
        memory = store.get_teaching_memory(db, student_id)
        return memory.model_dump(mode="json") if memory else None

    loaders = {"dpm_profile": _load_dpm, "teaching_memory": _load_teaching_memory}
    enriched: list[EnrichedEvent] = []
    for event in events:
        diff = []
        if event.record_type in ("dpm_profile", "teaching_memory"):
            if event.operation == "read":
                last_seen[event.record_type] = event.payload
            else:
                previous = last_seen.get(event.record_type)
                if event.record_type not in last_seen:
                    previous = loaders[event.record_type]()
                diff = (diff_dpm if event.record_type == "dpm_profile" else diff_teaching_memory)(previous, event.payload)
                last_seen[event.record_type] = event.payload
        enriched.append(EnrichedEvent(event=event, diff=diff))
    return enriched


@router.get("/sessions/{session_id}/events")
async def session_events_endpoint(session_id: str, student_id: str, trace_id: str | None = None):
    """Event history for one session, each long-term write enriched with a
    real diff. `trace_id` narrows to one invocation -- what ADK web's
    trace-tab uses to show "what did this trace do to memory"."""
    events = _read_recent_events(session_id)
    enriched = _replay_diffs(events, student_id)
    if trace_id:
        enriched = [e for e in enriched if e.event.trace_id == trace_id]
    return {"events": [e.model_dump(mode="json") for e in enriched]}
