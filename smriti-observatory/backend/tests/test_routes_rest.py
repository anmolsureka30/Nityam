from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.memory import store
from app.memory.schemas import DPMProfile, TeachingMemory
from observatory.routes_rest import build_router


@pytest.fixture
def client_app(firestore_db, redis_client):
    app = FastAPI()
    app.state.firestore = firestore_db
    app.include_router(build_router(tutor_base_url="http://localhost:9999"))
    return TestClient(app)


def test_session_state_returns_current_long_term_snapshot(client_app, firestore_db, redis_client):
    try:
        store.put_dpm(firestore_db, DPMProfile(student_id="test_rest_student"))
        store.put_teaching_memory(firestore_db, TeachingMemory(student_id="test_rest_student", syllabus=["x"]))
        response = client_app.get(
            "/api/sessions/test_rest_session_1/state", params={"student_id": "test_rest_student"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["long_term"]["dpm_profile"]["student_id"] == "test_rest_student"
        assert body["long_term"]["teaching_memory"]["syllabus"] == ["x"]
        assert body["episodic"]["session_log"] is None
        assert body["workflow"]["turn_buffer"] == []
    finally:
        firestore_db.collection("dpm_profiles").document("test_rest_student").delete()
        firestore_db.collection("teaching_memories").document("test_rest_student").delete()


def test_session_state_handles_missing_records_gracefully(client_app):
    response = client_app.get(
        "/api/sessions/test_rest_missing/state", params={"student_id": "test_rest_missing_student"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["long_term"]["dpm_profile"] is None
    assert body["long_term"]["teaching_memory"] is None


def test_health_reports_redis_and_firestore_reachability(client_app):
    response = client_app.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["redis"] is True
    assert body["firestore"] is True
    assert "tutor_reachable" in body


def test_events_endpoint_returns_recent_backlog(client_app, redis_client):
    redis_client.delete("smriti:events:recent")
    from observatory.events import MemoryEvent
    event = MemoryEvent(
        event_id="e1", ts="2026-08-27T00:00:00Z", session_id="test_rest_session_2", student_id="s",
        tier="workflow", operation="write", record_type="turn_buffer", source_fn="append_turn",
        trace_id=None, span_id=None, payload=None,
    )
    redis_client.rpush("smriti:events:recent", event.model_dump_json())
    response = client_app.get("/api/sessions/test_rest_session_2/events")
    assert response.status_code == 200
    body = response.json()
    assert len(body["events"]) == 1
    assert body["events"][0]["event_id"] == "e1"


def test_events_endpoint_filters_by_session_id(client_app, redis_client):
    redis_client.delete("smriti:events:recent")
    from observatory.events import MemoryEvent
    for i, sid in enumerate(["test_rest_session_3", "test_rest_session_4"]):
        event = MemoryEvent(
            event_id=f"e{i}", ts="2026-08-27T00:00:00Z", session_id=sid, student_id="s",
            tier="workflow", operation="write", record_type="turn_buffer", source_fn="append_turn",
            trace_id=None, span_id=None, payload=None,
        )
        redis_client.rpush("smriti:events:recent", event.model_dump_json())
    response = client_app.get("/api/sessions/test_rest_session_3/events")
    body = response.json()
    assert len(body["events"]) == 1
    assert body["events"][0]["session_id"] == "test_rest_session_3"


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
