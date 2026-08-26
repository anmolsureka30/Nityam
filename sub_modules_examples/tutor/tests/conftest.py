from __future__ import annotations

import pytest


@pytest.fixture
def firestore_db():
    """Real Firestore (database 'smriti', see app/config.py), fresh client
    per test — not session-scoped, since store.py's own tests want an
    isolated view and clean up after themselves. Skips (not fails) when
    unreachable, matching sub_modules_examples/memory_storage_testbed's
    established pattern."""
    from app.memory import store

    try:
        client = store.connect()
        client.collection("_healthcheck").document("x").get()
    except Exception as exc:  # noqa: BLE001 - any reachability failure should skip, not fail
        pytest.skip(f"Firestore unreachable ({exc}); run `gcloud auth application-default login`")
    yield client
    client.close()


@pytest.fixture
def redis_client():
    """Sync client, used only for test setup/teardown convenience — the real
    write-through path (app/memory/short_term.py) uses redis.asyncio."""
    import redis as redis_module

    from app import config

    try:
        client = redis_module.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
        client.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Redis unreachable at {config.REDIS_HOST}:{config.REDIS_PORT} ({exc}); run `brew services start redis`")
    yield client


@pytest.fixture(autouse=True)
def _reset_memory_session_context():
    """instrumentation.set_session_context's contextvar is process-global —
    reset it around every test so one test's close_session/context call
    can't leak into the next (see Task 1 note in
    docs/superpowers/plans/2026-08-27-smriti-observatory.md)."""
    from app.memory import instrumentation

    instrumentation.set_session_context(None)
    yield
    instrumentation.set_session_context(None)
