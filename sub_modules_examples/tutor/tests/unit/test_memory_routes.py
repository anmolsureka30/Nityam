from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.app_utils.memory_routes import router
from app.memory import short_term, store


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
