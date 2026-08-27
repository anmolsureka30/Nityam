from __future__ import annotations

import pytest

from testbed.config import FIRESTORE_DATABASE, GCS_BUCKET, PROJECT_ID, REDIS_HOST, REDIS_PORT


@pytest.fixture(scope="session")
def firestore_db():
    from google.cloud import firestore

    try:
        client = firestore.Client(project=PROJECT_ID, database=FIRESTORE_DATABASE)
        client.collection("_healthcheck").document("x").get()
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any reachability failure should skip, not fail
        pytest.skip(f"Firestore unreachable ({exc}); run `gcloud auth application-default login`")
    yield client


@pytest.fixture(scope="session")
def gcs_bucket():
    from google.cloud import storage

    try:
        client = storage.Client(project=PROJECT_ID)
        bucket = client.bucket(GCS_BUCKET)
        bucket.exists()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"GCS unreachable ({exc}); run `gcloud auth application-default login`")
    yield bucket


@pytest.fixture(scope="session")
def redis_client():
    import redis as redis_module

    try:
        client = redis_module.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        client.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Redis unreachable at {REDIS_HOST}:{REDIS_PORT} ({exc}); run `brew services start redis`")
    yield client
