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

from fastapi import APIRouter
from google import genai
from google.cloud import firestore
from pydantic import BaseModel

from app.memory import short_term, store
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
