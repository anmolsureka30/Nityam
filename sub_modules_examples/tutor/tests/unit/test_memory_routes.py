from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.app_utils.memory_routes import router
from app.memory import short_term, store
from app.memory.instrumentation import MemoryEvent


@pytest.fixture
def client_app():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.mark.asyncio
async def test_close_endpoint_closes_a_seeded_session(client_app, firestore_db, redis_client, monkeypatch):
    session_id = "test_route_close_1"
    student_id = "test_route_student_1"
    try:
        await short_term.append_turn(session_id, {
            "turn": 1, "role": "student", "text": "why 45 degrees?",
            "concept_id": None, "artifact_id": None,
        })
        await short_term.ensure_started_at(session_id)

        from app.app_utils import memory_routes
        import app.session_close as session_close
        from app.session_close import ReflectResult

        monkeypatch.setattr(session_close, "reflect", lambda client, log: ReflectResult(summary="", operations=[]))
        monkeypatch.setattr(memory_routes, "_genai_client", lambda: None)
        monkeypatch.setattr(memory_routes, "_firestore_client", lambda: firestore_db)

        response = client_app.post(f"/memory/sessions/{session_id}/close", json={"student_id": student_id})

        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == session_id
        assert body["student_id"] == student_id

        stored = store.get_session_log(firestore_db, session_id)
        assert stored is not None
        assert len(stored.turns) == 1

        # buffer cleared after a successful close
        assert await short_term.get_turn_buffer(session_id) == []
    finally:
        firestore_db.collection("session_logs").document(session_id).delete()
        firestore_db.collection("dpm_profiles").document(student_id).delete()
        firestore_db.collection("teaching_memories").document(student_id).delete()
        redis_client.delete(f"session:{session_id}:turns", f"session:{session_id}:started_at", f"session:{session_id}:heartbeat")


def test_close_endpoint_defaults_student_id_to_demo_student(client_app, firestore_db, monkeypatch):
    session_id = "test_route_close_default"
    from app.app_utils import memory_routes
    import app.session_close as session_close
    from app.session_close import ReflectResult

    monkeypatch.setattr(session_close, "reflect", lambda client, log: ReflectResult(summary="", operations=[]))
    monkeypatch.setattr(memory_routes, "_genai_client", lambda: None)
    monkeypatch.setattr(memory_routes, "_firestore_client", lambda: firestore_db)

    try:
        response = client_app.post(f"/memory/sessions/{session_id}/close", json={})
        assert response.status_code == 200
        assert response.json()["student_id"] == "demo_student"
    finally:
        firestore_db.collection("session_logs").document(session_id).delete()
        firestore_db.collection("dpm_profiles").document("demo_student").delete()
        firestore_db.collection("teaching_memories").document("demo_student").delete()


def test_state_endpoint_returns_current_long_term_snapshot(client_app, firestore_db):
    from app.app_utils import memory_routes
    from app.memory.schemas import DPMProfile, TeachingMemory

    orig = memory_routes._firestore_client
    memory_routes._firestore_client = lambda: firestore_db
    try:
        store.put_dpm(firestore_db, DPMProfile(student_id="test_route_state_student"))
        store.put_teaching_memory(firestore_db, TeachingMemory(student_id="test_route_state_student", syllabus=["x"]))

        response = client_app.get(
            "/memory/sessions/test_route_state_session/state",
            params={"student_id": "test_route_state_student"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["long_term"]["dpm_profile"]["student_id"] == "test_route_state_student"
        assert body["long_term"]["teaching_memory"]["syllabus"] == ["x"]
        assert body["episodic"]["session_log"] is None
        assert body["workflow"]["turn_buffer"] == []
    finally:
        memory_routes._firestore_client = orig
        firestore_db.collection("dpm_profiles").document("test_route_state_student").delete()
        firestore_db.collection("teaching_memories").document("test_route_state_student").delete()


def _push_event(redis_client, **overrides) -> None:
    defaults = dict(
        event_id="e", ts="2026-08-27T00:00:00Z", session_id="test_route_events_session",
        student_id="test_route_events_student", tier="workflow", operation="write",
        record_type="turn_buffer", source_fn="append_turn", trace_id=None, span_id=None, payload=None,
    )
    defaults.update(overrides)
    redis_client.rpush("smriti:events:recent", MemoryEvent(**defaults).model_dump_json())


def test_events_endpoint_returns_only_this_sessions_events(client_app, redis_client):
    _push_event(redis_client, event_id="a", session_id="test_route_events_session")
    _push_event(redis_client, event_id="b", session_id="a_different_session")
    response = client_app.get(
        "/memory/sessions/test_route_events_session/events",
        params={"student_id": "test_route_events_student"},
    )
    assert response.status_code == 200
    ids = [e["event"]["event_id"] for e in response.json()["events"]]
    assert "a" in ids
    assert "b" not in ids


def test_events_endpoint_filters_by_trace_id(client_app, redis_client):
    _push_event(redis_client, event_id="c1", trace_id="trace-1")
    _push_event(redis_client, event_id="c2", trace_id="trace-2")
    response = client_app.get(
        "/memory/sessions/test_route_events_session/events",
        params={"student_id": "test_route_events_student", "trace_id": "trace-1"},
    )
    ids = [e["event"]["event_id"] for e in response.json()["events"]]
    assert "c1" in ids
    assert "c2" not in ids


def test_events_endpoint_computes_a_diff_for_a_long_term_write(client_app, redis_client, firestore_db):
    from app.app_utils import memory_routes

    orig = memory_routes._firestore_client
    memory_routes._firestore_client = lambda: firestore_db
    try:
        # A read establishes the "before" snapshot, then a write with a
        # changed mastery value should produce a real diff — the same
        # read-before-write pattern close_session itself follows.
        _push_event(
            redis_client, event_id="r1", operation="read", record_type="dpm_profile",
            payload={"student_id": "test_route_events_student", "weaknesses": {}, "self_reflection": [], "persona": {"interests": []}},
        )
        _push_event(
            redis_client, event_id="w1", operation="write", record_type="dpm_profile",
            payload={
                "student_id": "test_route_events_student",
                "weaknesses": {"projectile.range": {"mastery": "known", "strength": "strong", "evidence": ["s#1"]}},
                "self_reflection": [], "persona": {"interests": []},
            },
        )
        response = client_app.get(
            "/memory/sessions/test_route_events_session/events",
            params={"student_id": "test_route_events_student"},
        )
        events = response.json()["events"]
        write_event = next(e for e in events if e["event"]["event_id"] == "w1")
        assert len(write_event["diff"]) == 1
        assert write_event["diff"][0]["path"] == "weaknesses.projectile.range"
        assert write_event["diff"][0]["kind"] == "added"
    finally:
        memory_routes._firestore_client = orig
