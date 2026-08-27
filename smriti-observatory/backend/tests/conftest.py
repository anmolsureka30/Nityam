"""Same skip-if-unreachable shape as sub_modules_examples/tutor/tests/conftest.py."""
from __future__ import annotations

import pytest


@pytest.fixture
def firestore_db():
    from app.memory import store

    try:
        client = store.connect()
        client.collection("_healthcheck").document("x").get()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Firestore unreachable ({exc}); run `gcloud auth application-default login`")
    yield client
    client.close()


@pytest.fixture
def redis_client():
    import redis as redis_module
    from app import config

    try:
        client = redis_module.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
        client.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Redis unreachable at {config.REDIS_HOST}:{config.REDIS_PORT} ({exc}); run `brew services start redis`")
    yield client
