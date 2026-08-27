from __future__ import annotations

from fastapi.testclient import TestClient


def test_app_serves_health_endpoint(redis_client, firestore_db):
    from observatory.main import app

    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert set(response.json().keys()) == {"redis", "firestore", "tutor_reachable"}


def test_app_allows_cors_from_localhost_vite_origin(redis_client, firestore_db):
    from observatory.main import app

    with TestClient(app) as client:
        response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
