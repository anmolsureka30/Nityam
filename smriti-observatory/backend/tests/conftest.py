"""Fixtures build their own Firestore/Redis clients directly from this
package's own env vars — no import from either agent app's `app` package
(see docs/superpowers/specs/2026-08-28-backend-memory-observatory-design.md §3).
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def firestore_db():
    from google.cloud import firestore

    project = os.environ.get("GCP_PROJECT", "nityam-506707")
    database = os.environ.get("FIRESTORE_DATABASE", "smriti")
    try:
        client = firestore.Client(project=project, database=database)
        client.collection("_healthcheck").document("x").get()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Firestore unreachable ({exc}); run `gcloud auth application-default login`")
    yield client
    client.close()


@pytest.fixture
def redis_client():
    import redis as redis_module

    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    try:
        client = redis_module.Redis(host=host, port=port, decode_responses=True)
        client.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Redis unreachable at {host}:{port} ({exc}); run `brew services start redis`")
    yield client
