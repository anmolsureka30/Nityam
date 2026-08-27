"""REST snapshot endpoints. Never re-implements a Firestore/Redis read —
every read goes through app.memory.store / app.memory.short_term directly
(the tutor package, via the pyproject.toml path dependency)."""
from __future__ import annotations

import httpx
import redis as redis_sync
from fastapi import APIRouter, Request

from app import config
from app.memory import short_term, store
from observatory.events import MemoryEvent


def build_router(tutor_base_url: str) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/sessions")
    def list_sessions():
        try:
            client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
            raw_events = client.lrange("smriti:events:recent", 0, -1)
        except Exception:
            return {"sessions": []}
        events = [MemoryEvent.model_validate_json(raw) for raw in raw_events]
        by_session: dict[str, dict] = {}
        for event in events:
            if not event.session_id:
                continue
            entry = by_session.setdefault(event.session_id, {
                "session_id": event.session_id,
                "student_id": event.student_id,
                "started_at": event.ts,
                "last_event_at": event.ts,
            })
            entry["last_event_at"] = event.ts
            if event.student_id:
                entry["student_id"] = event.student_id
        for session_id, entry in by_session.items():
            try:
                entry["status"] = "live" if client.exists(f"session:{session_id}:heartbeat") else "closed"
            except Exception:
                entry["status"] = "closed"
        return {"sessions": sorted(by_session.values(), key=lambda s: s["last_event_at"], reverse=True)}

    @router.get("/sessions/{session_id}/state")
    async def session_state(session_id: str, student_id: str, request: Request):
        db = request.app.state.firestore
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

    @router.get("/sessions/{session_id}/events")
    def session_events(session_id: str):
        try:
            client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
            raw_events = client.lrange("smriti:events:recent", 0, -1)
        except Exception:
            return {"events": []}
        events = [MemoryEvent.model_validate_json(raw) for raw in raw_events]
        matching = [e.model_dump(mode="json") for e in events if e.session_id == session_id]
        return {"events": matching}

    @router.post("/sessions/{session_id}/close")
    async def close_session_proxy(session_id: str, body: dict):
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{tutor_base_url}/memory/sessions/{session_id}/close", json=body)
        return response.json()

    @router.get("/health")
    def health(request: Request):
        redis_ok = True
        try:
            redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT).ping()
        except Exception:
            redis_ok = False
        firestore_ok = True
        try:
            request.app.state.firestore.collection("_healthcheck").document("x").get()
        except Exception:
            firestore_ok = False
        tutor_ok = True
        try:
            httpx.get(f"{tutor_base_url}/list-apps", timeout=2.0)
        except Exception:
            tutor_ok = False
        return {"redis": redis_ok, "firestore": firestore_ok, "tutor_reachable": tutor_ok}

    return router
