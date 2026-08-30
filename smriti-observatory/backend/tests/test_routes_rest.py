from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.routes_rest import build_router


@pytest.fixture
def client_app(firestore_db, redis_client):
    async def unreachable_state_fn(session_id, student_id):
        raise RuntimeError("agent server unreachable")

    async def unreachable_events_fn(session_id, student_id, trace_id):
        raise RuntimeError("agent server unreachable")

    app = FastAPI()
    app.state.firestore = firestore_db
    app.include_router(
        build_router(
            tutor_base_url="http://localhost:9999", redis_host="localhost", redis_port=6379,
            memory_state_fn=unreachable_state_fn, memory_events_fn=unreachable_events_fn,
        )
    )
    return TestClient(app)


def test_agent_graph_returns_empty_dot_src_when_tutor_unreachable(client_app):
    response = client_app.get("/api/agent-graph")
    assert response.status_code == 200
    assert response.json() == {"dot_src": ""}


def test_agent_graph_proxies_and_caches_the_tutor_apps_dot_source(monkeypatch):
    calls = []

    class FakeResponse:
        def json(self):
            return {"dotSrc": "strict digraph { TutorAgent }"}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kwargs):
            calls.append(url)
            return FakeResponse()

    monkeypatch.setattr("observatory.routes_rest.httpx.AsyncClient", FakeAsyncClient)

    async def fake_state_fn(session_id, student_id):
        return {}

    async def fake_events_fn(session_id, student_id, trace_id):
        return {"events": []}

    app = FastAPI()
    app.include_router(
        build_router(
            tutor_base_url="http://fake-tutor", redis_host="localhost", redis_port=6379,
            memory_state_fn=fake_state_fn, memory_events_fn=fake_events_fn,
        )
    )
    client = TestClient(app)

    first = client.get("/api/agent-graph")
    second = client.get("/api/agent-graph")

    assert first.json() == {"dot_src": "strict digraph { TutorAgent }"}
    assert second.json() == {"dot_src": "strict digraph { TutorAgent }"}
    assert calls == ["http://fake-tutor/dev/apps/app/graph"]  # second call served from cache, not re-fetched


def test_session_state_calls_memory_state_fn_directly():
    calls = []

    async def fake_state_fn(session_id, student_id):
        calls.append((session_id, student_id))
        return {"session_id": session_id, "student_id": student_id, "workflow": {"turn_buffer": []}}

    async def fake_events_fn(session_id, student_id, trace_id):
        return {"events": []}

    router = build_router(
        tutor_base_url="http://unused", redis_host="localhost", redis_port=6379,
        memory_state_fn=fake_state_fn, memory_events_fn=fake_events_fn,
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/api/sessions/s1/state", params={"student_id": "stu1"})
    assert response.status_code == 200
    assert calls == [("s1", "stu1")]


def test_session_state_degrades_gracefully_when_memory_state_fn_raises():
    async def raising_state_fn(session_id, student_id):
        raise RuntimeError("boom")

    async def fake_events_fn(session_id, student_id, trace_id):
        return {"events": []}

    router = build_router(
        tutor_base_url="http://unused", redis_host="localhost", redis_port=6379,
        memory_state_fn=raising_state_fn, memory_events_fn=fake_events_fn,
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/api/sessions/s1/state", params={"student_id": "stu1"})
    assert response.status_code == 200
    body = response.json()
    assert body["long_term"] == {"dpm_profile": None, "teaching_memory": None}


def test_session_state_degrades_gracefully_when_the_agent_server_is_unreachable(client_app):
    response = client_app.get(
        "/api/sessions/test_rest_session_unreachable/state", params={"student_id": "whoever"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["workflow"]["turn_buffer"] == []
    assert body["long_term"]["dpm_profile"] is None


def test_health_reports_redis_and_firestore_reachability(client_app):
    response = client_app.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["redis"] is True
    assert body["firestore"] is True
    assert "tutor_reachable" in body


def test_session_events_calls_memory_events_fn_directly():
    calls = []

    async def fake_state_fn(session_id, student_id):
        return {}

    async def fake_events_fn(session_id, student_id, trace_id):
        calls.append((session_id, student_id, trace_id))
        return {"events": [{"event_id": "e1", "session_id": session_id}]}

    router = build_router(
        tutor_base_url="http://unused", redis_host="localhost", redis_port=6379,
        memory_state_fn=fake_state_fn, memory_events_fn=fake_events_fn,
    )
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/api/sessions/s1/events", params={"student_id": "stu1"})
    assert response.status_code == 200
    assert response.json()["events"][0]["event_id"] == "e1"
    assert calls == [("s1", "stu1", None)]


def test_session_events_degrades_gracefully_when_the_agent_server_is_unreachable(client_app):
    """client_app points tutor_base_url at http://localhost:9999, which
    nothing is listening on -- the viewer must not crash for it."""
    response = client_app.get("/api/sessions/test_rest_session_unreachable/events")
    assert response.status_code == 200
    assert response.json() == {"events": []}


def test_list_sessions_derives_from_recent_events(client_app, redis_client):
    redis_client.delete("smriti:events:recent")
    from observatory.events import MemoryEvent

    event = MemoryEvent(
        event_id="e1", ts="2026-08-27T00:00:00Z", session_id="test_rest_session_list", student_id="stu_list",
        tier="workflow", operation="write", record_type="turn_buffer", source_fn="append_turn",
        trace_id=None, span_id=None, payload=None,
    )
    redis_client.rpush("smriti:events:recent", event.model_dump_json())
    try:
        response = client_app.get("/api/sessions")
        assert response.status_code == 200
        sessions = response.json()["sessions"]
        match = next(s for s in sessions if s["session_id"] == "test_rest_session_list")
        assert match["student_id"] == "stu_list"
        assert match["status"] == "closed"
    finally:
        redis_client.delete("smriti:events:recent")


def test_list_sessions_marks_a_session_with_a_live_heartbeat_as_live(client_app, redis_client):
    redis_client.delete("smriti:events:recent")
    from observatory.events import MemoryEvent

    event = MemoryEvent(
        event_id="e2", ts="2026-08-27T00:00:00Z", session_id="test_rest_session_live", student_id="stu_live",
        tier="workflow", operation="write", record_type="turn_buffer", source_fn="append_turn",
        trace_id=None, span_id=None, payload=None,
    )
    redis_client.rpush("smriti:events:recent", event.model_dump_json())
    redis_client.set("session:test_rest_session_live:heartbeat", "1", ex=60)
    try:
        response = client_app.get("/api/sessions")
        sessions = response.json()["sessions"]
        match = next(s for s in sessions if s["session_id"] == "test_rest_session_live")
        assert match["status"] == "live"
    finally:
        redis_client.delete("smriti:events:recent", "session:test_rest_session_live:heartbeat")


def test_list_sessions_does_not_crash_on_a_tool_call_event_in_the_same_list(client_app, redis_client):
    """Regression test: smriti:events:recent holds a mix of MemoryEvent and
    ToolCallEvent JSON on the same list (see ingest.py's own kind-based
    dispatch) — list_sessions used to call MemoryEvent.model_validate_json()
    on every entry unconditionally, which raised a pydantic ValidationError
    (missing source_fn/record_type) the moment any ToolCallEvent had ever
    been published, a 500 confirmed live in production before this fix."""
    redis_client.delete("smriti:events:recent")
    from observatory.events import ToolCallEvent

    tool_call = ToolCallEvent(
        event_id="tc1", ts="2026-08-30T00:00:00Z", session_id="test_rest_session_toolcall",
        student_id="stu_toolcall", trace_id=None, span_id=None,
        actor="board_agent", tool_name="search_grounding", phase="done",
        args_summary=None, result_summary=None, duration_ms=100,
    )
    redis_client.rpush("smriti:events:recent", tool_call.model_dump_json())
    try:
        response = client_app.get("/api/sessions")
        assert response.status_code == 200
        sessions = response.json()["sessions"]
        match = next(s for s in sessions if s["session_id"] == "test_rest_session_toolcall")
        assert match["student_id"] == "stu_toolcall"
    finally:
        redis_client.delete("smriti:events:recent")
