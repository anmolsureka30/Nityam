"""REST snapshot endpoints. Historically talked to whichever agent server
was configured purely over HTTP; session_state/session_events now call
backend/'s own memory_routes.py handlers directly, in-process, since this
router is mounted into the same FastAPI app as backend/ (see
docs/superpowers/specs/2026-08-30-observatory-integration-design.md's
Architecture section). agent-graph and health still use tutor_base_url —
left as dead/degraded per that same spec's Non-goals, unrelated to this
change.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

import httpx
import redis as redis_sync
from fastapi import APIRouter, Request

from observatory.events import MemoryEvent

MemoryStateFn = Callable[[str, str], Awaitable[dict[str, Any]]]
MemoryEventsFn = Callable[[str, str, str | None], Awaitable[dict[str, Any]]]


def build_router(
    tutor_base_url: str,
    redis_host: str,
    redis_port: int,
    memory_state_fn: MemoryStateFn,
    memory_events_fn: MemoryEventsFn,
) -> APIRouter:
    router = APIRouter(prefix="/api")
    _agent_graph_cache: dict[str, str] = {}

    @router.get("/agent-graph")
    async def agent_graph():
        """Proxies the tutor app's own ADK dev-ui graph (agents + tools, as
        Graphviz DOT source) so the browser can render it without a direct
        cross-origin request — the ADK dev server doesn't send CORS headers.
        Cached in-process: the agent/tool topology only changes on redeploy.
        Degrades to an empty dot_src when the configured agent server has no
        ADK dev-ui at all (e.g. backend/) — accepted, see the design spec's
        non-goals."""
        if "dot_src" in _agent_graph_cache:
            return {"dot_src": _agent_graph_cache["dot_src"]}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{tutor_base_url}/dev/apps/app/graph", params={"dark_mode": "true"}, timeout=5.0)
            dot_src = response.json().get("dotSrc", "")
        except Exception:
            return {"dot_src": ""}
        _agent_graph_cache["dot_src"] = dot_src
        return {"dot_src": dot_src}

    @router.get("/sessions")
    def list_sessions():
        try:
            client = redis_sync.Redis(host=redis_host, port=redis_port, decode_responses=True)
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
    async def session_state(session_id: str, student_id: str):
        try:
            return await memory_state_fn(session_id, student_id)
        except Exception:
            # A transient failure must not crash the viewer — same
            # graceful-degradation contract as agent_graph() above. Same
            # shape the frontend already handles for "nothing here yet"
            # (see memory_routes.py's own missing-record shape).
            return {
                "session_id": session_id, "student_id": student_id,
                "workflow": {"turn_buffer": []},
                "episodic": {"session_log": None},
                "long_term": {"dpm_profile": None, "teaching_memory": None},
            }

    @router.get("/sessions/{session_id}/events")
    async def session_events(session_id: str, student_id: str = ""):
        try:
            return await memory_events_fn(session_id, student_id, None)
        except Exception:
            return {"events": []}

    @router.get("/health")
    def health(request: Request):
        redis_ok = True
        try:
            redis_sync.Redis(host=redis_host, port=redis_port).ping()
        except Exception:
            redis_ok = False
        firestore_ok = True
        try:
            request.app.state.firestore.collection("_healthcheck").document("x").get()
        except Exception:
            firestore_ok = False
        tutor_ok = True
        try:
            httpx.get(f"{tutor_base_url}/health", timeout=2.0)
        except Exception:
            tutor_ok = False
        return {"redis": redis_ok, "firestore": firestore_ok, "tutor_reachable": tutor_ok}

    return router
