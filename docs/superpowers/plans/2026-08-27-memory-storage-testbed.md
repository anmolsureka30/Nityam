# Memory Storage Testbed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove, against real Google Cloud resources, that Firestore (structured records + native
vector search), GCS (via ADK's `GcsArtifactService`), and local Redis (standing in for
Memorystore) work as SMRITI's storage backends — as a standalone package, before
`sub_modules_examples/tutor/app/memory/store.py` is rewritten for real.

**Architecture:** A new, standalone `sub_modules_examples/memory_storage_testbed/` package with
its own venv. Three independent storage modules (`firestore_store.py`, `gcs_artifacts.py`,
`redis_shortterm.py`), each proven with its own pytest suite against real cloud resources, then
one `demo_end_to_end.py` wiring all three together in the sequence the real system will use.

**Tech Stack:** Python 3.12, `uv`, `pydantic`, `google-cloud-firestore`, `google-cloud-storage`,
`google-adk==2.7.1` (for `GcsArtifactService` — the same version already installed in
`sub_modules_examples/tutor/.venv`), `redis` (async client), `pytest` + `pytest-asyncio`.

**Spec:** `docs/superpowers/specs/2026-08-27-memory-storage-testbed-design.md`, which itself
argues from `project_documentation/memory_nityam_architecture/memory_layer.md` (v2.0) and
`project_documentation/memory_nityam_architecture/google_cloud_storage_integration.md` (v1.1).

## Global Constraints

- **Never modify anything under `sub_modules_examples/tutor/`.** This is a standalone proving
  ground; nothing about the real module changes as part of this plan.
- **Use the real, already-provisioned cloud resources — do not create new ones.** Project
  `nityam-506707`, Firestore database `smriti-testbed` (Native mode, `us-central1`), GCS bucket
  `gs://nityam-506707-memory-testbed`. All three exist and were live-verified reachable via ADC
  before this plan was written.
- **Every test that touches a real backend (Firestore/GCS/Redis) must clean up the documents/
  objects/keys it creates**, so re-running the suite never accumulates test data.
- **Every fixture touching a real backend must skip (via `pytest.skip`), never fail,** when that
  backend is unreachable — this package must be safely runnable in an environment without cloud
  credentials or local Redis.
- **`firestore_store.py`'s function names mirror the real `store.py` exactly**
  (`put_chunk`/`search_chunks`/`search_chunks_semantic`/`get_dpm`/`put_dpm`/`get_teaching_memory`/
  `put_teaching_memory`/`put_session_log`/`get_session_log`) — same call shape, so porting into
  the real file later is closer to a copy than a rewrite.
- **Vector search uses synthetic 1536-dimension test vectors, never real Shruti embeddings.** The
  Firestore vector-index dimension cap vs. Shruti's real 3072-dim embedder
  (`google_cloud_storage_integration.md` §3.3) stays open, tracked separately — not something this
  plan resolves.
- **No `Co-Authored-By` trailer on any commit** — matches this repo's existing convention (see
  recent `git log`).
- **Run all commands from inside `sub_modules_examples/memory_storage_testbed/`** once Task 1
  creates it, using `uv run ...` for everything (never bare `python3`).

---

### Task 1: Package scaffolding

**Files:**
- Create: `sub_modules_examples/memory_storage_testbed/pyproject.toml`
- Create: `sub_modules_examples/memory_storage_testbed/.env.example`
- Create: `sub_modules_examples/memory_storage_testbed/.gitignore`
- Create: `sub_modules_examples/memory_storage_testbed/testbed/__init__.py`
- Create: `sub_modules_examples/memory_storage_testbed/testbed/config.py`
- Create: `sub_modules_examples/memory_storage_testbed/tests/__init__.py`
- Create: `sub_modules_examples/memory_storage_testbed/tests/conftest.py`
- Test: `sub_modules_examples/memory_storage_testbed/tests/test_setup.py`

**Interfaces:**
- Produces: `testbed/config.py`'s module-level constants read from env (`PROJECT_ID`,
  `FIRESTORE_DATABASE`, `GCS_BUCKET`, `REDIS_HOST`, `REDIS_PORT`) — application code (including
  `demo_end_to_end.py`'s `__main__` block in Task 6) imports these from `testbed.config`, never
  from `tests.conftest`. Also produces `firestore_db`, `gcs_bucket`, `redis_client` pytest
  fixtures (session-scoped, defined in `tests/conftest.py`, built on top of `testbed.config`) that
  every later task's tests consume. Each skips cleanly if its backend is unreachable.

- [ ] **Step 1: Create the package directory and `pyproject.toml`**

```toml
[project]
name = "memory-storage-testbed"
version = "0.1.0"
description = "Standalone testbed proving Firestore/GCS/Redis as SMRITI's Google-managed storage backends, before porting into sub_modules_examples/tutor."
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
    "google-cloud-firestore>=2.16",
    "google-cloud-storage>=2.16",
    "google-adk==2.7.1",
    "redis>=5.0",
    "python-dotenv>=1.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["testbed"]
```

- [ ] **Step 2: Create `.env.example`**

```bash
GCP_PROJECT=nityam-506707
FIRESTORE_DATABASE=smriti-testbed
GCS_BUCKET=nityam-506707-memory-testbed
REDIS_HOST=localhost
REDIS_PORT=6379
```

Copy this to `.env` (not committed — see `.gitignore` below) with the same real values; there are
no secrets in it since auth flows entirely through ADC and local Redis has no password by default.

- [ ] **Step 3: Create `.gitignore`**

```
.venv/
.env
__pycache__/
*.pyc
.pytest_cache/
uv.lock
```

- [ ] **Step 4: Create `testbed/__init__.py`** (empty — marks the package)

- [ ] **Step 5: Create `testbed/config.py`**

```python
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.environ.get("GCP_PROJECT", "nityam-506707")
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "smriti-testbed")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "nityam-506707-memory-testbed")
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
```

- [ ] **Step 6: Create `tests/__init__.py`** (empty)

- [ ] **Step 7: Create `tests/conftest.py`**

```python
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
```

- [ ] **Step 8: Write the smoke test**

```python
# tests/test_setup.py
def test_package_imports():
    import testbed
    from testbed import config

    assert testbed is not None
    assert config.PROJECT_ID == "nityam-506707"
```

- [ ] **Step 9: Install and run**

```bash
cd sub_modules_examples/memory_storage_testbed
cp .env.example .env
uv sync
uv run pytest -v
```

Expected: 1 passed (`test_package_imports`).

- [ ] **Step 10: Commit**

```bash
git add sub_modules_examples/memory_storage_testbed/
git commit -m "feat: scaffold standalone memory storage testbed package"
```

(`git add` on the whole directory is fine here — nothing else exists in it yet, and `.gitignore`
from Step 3 already excludes `.venv/`, `.env`, `uv.lock`, and cache directories.)

---

### Task 2: Firestore — structured-record CRUD

**Files:**
- Create: `sub_modules_examples/memory_storage_testbed/testbed/schemas.py`
- Create: `sub_modules_examples/memory_storage_testbed/testbed/firestore_store.py`
- Test: `sub_modules_examples/memory_storage_testbed/tests/test_firestore_store.py`

**Interfaces:**
- Consumes: `firestore_db` fixture from Task 1's `conftest.py`.
- Produces: `TestChunk`, `TestTurn`, `TestSessionLog`, `TestProfile` (schemas.py); `put_chunk(db,
  chunk, embedding)`, `search_chunks(db, concept_ids, limit=5)`, `get_dpm(db, student_id)`,
  `put_dpm(db, profile)`, `get_teaching_memory(db, student_id)`, `put_teaching_memory(db,
  memory)`, `put_session_log(db, log)`, `get_session_log(db, session_id)` (firestore_store.py) —
  Task 3 extends this same file with `search_chunks_semantic`.

- [ ] **Step 1: Write `testbed/schemas.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class TestChunk(BaseModel):
    chunk_id: str
    concept_ids: list[str] = Field(min_length=1)
    text: str


class TestTurn(BaseModel):
    turn: int
    role: str
    text: str


class TestSessionLog(BaseModel):
    session_id: str
    student_id: str
    turns: list[TestTurn]


class TestProfile(BaseModel):
    student_id: str
    note: str
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_firestore_store.py
import random

from testbed import firestore_store
from testbed.schemas import TestChunk, TestProfile, TestSessionLog, TestTurn


def _dummy_embedding(seed: int, dim: int = 1536) -> list[float]:
    rng = random.Random(seed)
    return [rng.uniform(-1, 1) for _ in range(dim)]


def test_chunk_roundtrip(firestore_db):
    chunk = TestChunk(
        chunk_id="test_chunk_1",
        concept_ids=["kinematics.projectile"],
        text="Range = u^2 sin(2 theta) / g",
    )
    try:
        firestore_store.put_chunk(firestore_db, chunk, _dummy_embedding(seed=1))
        results = firestore_store.search_chunks(firestore_db, ["kinematics.projectile"])
        assert any(c.chunk_id == "test_chunk_1" for c in results)
    finally:
        firestore_db.collection("grounding_chunks").document("test_chunk_1").delete()


def test_dpm_roundtrip(firestore_db):
    profile = TestProfile(student_id="test_student_1", note="prefers worked examples")
    try:
        firestore_store.put_dpm(firestore_db, profile)
        fetched = firestore_store.get_dpm(firestore_db, "test_student_1")
        assert fetched is not None
        assert fetched.note == "prefers worked examples"
    finally:
        firestore_db.collection("dpm_profiles").document("test_student_1").delete()


def test_teaching_memory_roundtrip(firestore_db):
    memory = TestProfile(student_id="test_student_1", note="covered projectile motion")
    try:
        firestore_store.put_teaching_memory(firestore_db, memory)
        fetched = firestore_store.get_teaching_memory(firestore_db, "test_student_1")
        assert fetched is not None
        assert fetched.note == "covered projectile motion"
    finally:
        firestore_db.collection("teaching_memories").document("test_student_1").delete()


def test_session_log_roundtrip(firestore_db):
    log = TestSessionLog(
        session_id="test_session_1",
        student_id="test_student_1",
        turns=[TestTurn(turn=1, role="student", text="What is range?")],
    )
    try:
        firestore_store.put_session_log(firestore_db, log)
        fetched = firestore_store.get_session_log(firestore_db, "test_session_1")
        assert fetched is not None
        assert fetched.turns[0].text == "What is range?"
    finally:
        firestore_db.collection("session_logs").document("test_session_1").delete()
```

- [ ] **Step 3: Run to verify failure**

```bash
uv run pytest tests/test_firestore_store.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'testbed.firestore_store'`.

- [ ] **Step 4: Write `testbed/firestore_store.py`**

```python
from __future__ import annotations

from google.cloud import firestore
from google.cloud.firestore_v1.vector import Vector

from testbed.schemas import TestChunk, TestProfile, TestSessionLog


def connect(project: str, database: str) -> firestore.Client:
    return firestore.Client(project=project, database=database)


def put_chunk(db: firestore.Client, chunk: TestChunk, embedding: list[float]) -> None:
    payload = chunk.model_dump(mode="json")
    payload["embedding"] = Vector(embedding)
    db.collection("grounding_chunks").document(chunk.chunk_id).set(payload)


def search_chunks(db: firestore.Client, concept_ids: list[str], limit: int = 5) -> list[TestChunk]:
    if not concept_ids:
        return []
    docs = (
        db.collection("grounding_chunks")
        .where("concept_ids", "array_contains_any", concept_ids)
        .limit(limit)
        .get()
    )
    return [
        TestChunk.model_validate({k: v for k, v in d.to_dict().items() if k != "embedding"})
        for d in docs
    ]


def get_dpm(db: firestore.Client, student_id: str) -> TestProfile | None:
    doc = db.collection("dpm_profiles").document(student_id).get()
    return TestProfile.model_validate(doc.to_dict()) if doc.exists else None


def put_dpm(db: firestore.Client, profile: TestProfile) -> None:
    db.collection("dpm_profiles").document(profile.student_id).set(profile.model_dump(mode="json"))


def get_teaching_memory(db: firestore.Client, student_id: str) -> TestProfile | None:
    doc = db.collection("teaching_memories").document(student_id).get()
    return TestProfile.model_validate(doc.to_dict()) if doc.exists else None


def put_teaching_memory(db: firestore.Client, memory: TestProfile) -> None:
    db.collection("teaching_memories").document(memory.student_id).set(memory.model_dump(mode="json"))


def put_session_log(db: firestore.Client, log: TestSessionLog) -> None:
    db.collection("session_logs").document(log.session_id).set(log.model_dump(mode="json"))


def get_session_log(db: firestore.Client, session_id: str) -> TestSessionLog | None:
    doc = db.collection("session_logs").document(session_id).get()
    return TestSessionLog.model_validate(doc.to_dict()) if doc.exists else None
```

- [ ] **Step 5: Run to verify pass**

```bash
uv run pytest tests/test_firestore_store.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add sub_modules_examples/memory_storage_testbed/testbed/schemas.py \
        sub_modules_examples/memory_storage_testbed/testbed/firestore_store.py \
        sub_modules_examples/memory_storage_testbed/tests/test_firestore_store.py
git commit -m "feat: add Firestore CRUD for chunk/profile/session_log shapes"
```

---

### Task 3: Firestore — native vector search

**Files:**
- Modify: `sub_modules_examples/memory_storage_testbed/testbed/firestore_store.py`
- Modify: `sub_modules_examples/memory_storage_testbed/tests/test_firestore_store.py`

**Interfaces:**
- Consumes: `put_chunk` from Task 2 (already writes the `embedding` field — no signature change).
- Produces: `search_chunks_semantic(db, query_embedding, concept_ids=None, limit=5)`.

- [ ] **Step 1: Create the vector index (one-time infra, not code)**

```bash
gcloud firestore indexes composite create \
  --collection-group=grounding_chunks \
  --query-scope=COLLECTION \
  --database=smriti-testbed \
  --field-config field-path=embedding,vector-config='{"dimension":"1536","flat":{}}' \
  --project=nityam-506707
```

Firestore vector index builds are asynchronous. Poll until `READY` before running the test in
Step 4:

```bash
gcloud firestore indexes composite list --database=smriti-testbed --project=nityam-506707
```

- [ ] **Step 2: Write the failing test**

```python
# append to tests/test_firestore_store.py

def test_semantic_search_finds_similar(firestore_db):
    base = _dummy_embedding(seed=42)
    similar = [v + 0.001 for v in base]
    different = _dummy_embedding(seed=999)

    chunk_a = TestChunk(chunk_id="test_sem_a", concept_ids=["kinematics.range"], text="chunk A")
    chunk_b = TestChunk(chunk_id="test_sem_b", concept_ids=["kinematics.range"], text="chunk B (near-duplicate of A)")
    chunk_c = TestChunk(chunk_id="test_sem_c", concept_ids=["kinematics.range"], text="chunk C (unrelated)")

    firestore_store.put_chunk(firestore_db, chunk_a, base)
    firestore_store.put_chunk(firestore_db, chunk_b, similar)
    firestore_store.put_chunk(firestore_db, chunk_c, different)

    try:
        results = firestore_store.search_chunks_semantic(firestore_db, base, limit=2)
        result_ids = [c.chunk_id for c in results]
        assert "test_sem_a" in result_ids
        assert "test_sem_b" in result_ids
    finally:
        for cid in ["test_sem_a", "test_sem_b", "test_sem_c"]:
            firestore_db.collection("grounding_chunks").document(cid).delete()
```

- [ ] **Step 3: Run to verify failure**

```bash
uv run pytest tests/test_firestore_store.py::test_semantic_search_finds_similar -v
```

Expected: FAIL — `AttributeError: module 'testbed.firestore_store' has no attribute 'search_chunks_semantic'`.

- [ ] **Step 4: Add `search_chunks_semantic` to `testbed/firestore_store.py`**

```python
# add import at top of testbed/firestore_store.py
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure


def search_chunks_semantic(
    db: firestore.Client,
    query_embedding: list[float],
    concept_ids: list[str] | None = None,
    limit: int = 5,
) -> list[TestChunk]:
    q = db.collection("grounding_chunks")
    if concept_ids:
        q = q.where("concept_ids", "array_contains_any", concept_ids)
    docs = q.find_nearest(
        vector_field="embedding",
        query_vector=Vector(query_embedding),
        distance_measure=DistanceMeasure.COSINE,
        limit=limit,
    ).get()
    return [
        TestChunk.model_validate({k: v for k, v in d.to_dict().items() if k != "embedding"})
        for d in docs
    ]
```

- [ ] **Step 5: Run to verify pass**

```bash
uv run pytest tests/test_firestore_store.py -v
```

Expected: 5 passed. If `test_semantic_search_finds_similar` fails with an index-not-ready error,
re-check Step 1's polling command and wait longer before retrying.

- [ ] **Step 6: Commit**

```bash
git add sub_modules_examples/memory_storage_testbed/testbed/firestore_store.py \
        sub_modules_examples/memory_storage_testbed/tests/test_firestore_store.py
git commit -m "feat: add Firestore native vector search for grounding_chunk"
```

---

### Task 4: GCS artifacts via `GcsArtifactService`

**Files:**
- Create: `sub_modules_examples/memory_storage_testbed/testbed/gcs_artifacts.py`
- Test: `sub_modules_examples/memory_storage_testbed/tests/test_gcs_artifacts.py`

**Interfaces:**
- Consumes: `gcs_bucket` fixture (used only to confirm reachability in `conftest.py`; the module
  itself talks to GCS through `GcsArtifactService`, not the raw bucket object).
- Produces: `make_service(bucket_name)`, `save_text_artifact(service, app_name, user_id,
  session_id, filename, text)`, `load_text_artifact(service, app_name, user_id, session_id,
  filename)`.

Exact method signatures below are taken directly from the installed `google-adk==2.7.1` source
(`BaseArtifactService.save_artifact`/`load_artifact`, both `async`, keyword-only args) — verified
live before this plan was written, not assumed from docs.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gcs_artifacts.py
import pytest

from testbed import gcs_artifacts
from testbed.config import GCS_BUCKET


@pytest.mark.asyncio
async def test_artifact_roundtrip(gcs_bucket):
    service = gcs_artifacts.make_service(GCS_BUCKET)
    try:
        await gcs_artifacts.save_text_artifact(
            service,
            app_name="memory_storage_testbed",
            user_id="test_user_1",
            session_id="test_session_1",
            filename="test_artifact.txt",
            text="hello from the testbed",
        )
        text = await gcs_artifacts.load_text_artifact(
            service,
            app_name="memory_storage_testbed",
            user_id="test_user_1",
            session_id="test_session_1",
            filename="test_artifact.txt",
        )
        assert text == "hello from the testbed"
    finally:
        await service.delete_artifact(
            app_name="memory_storage_testbed",
            user_id="test_user_1",
            session_id="test_session_1",
            filename="test_artifact.txt",
        )
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_gcs_artifacts.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'testbed.gcs_artifacts'`.

- [ ] **Step 3: Write `testbed/gcs_artifacts.py`**

```python
from __future__ import annotations

from google.adk.artifacts import GcsArtifactService
from google.genai.types import Blob, Part


def make_service(bucket_name: str) -> GcsArtifactService:
    return GcsArtifactService(bucket_name=bucket_name)


async def save_text_artifact(
    service: GcsArtifactService,
    app_name: str,
    user_id: str,
    session_id: str,
    filename: str,
    text: str,
) -> int:
    part = Part(inline_data=Blob(mime_type="text/plain", data=text.encode("utf-8")))
    return await service.save_artifact(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        filename=filename,
        artifact=part,
    )


async def load_text_artifact(
    service: GcsArtifactService,
    app_name: str,
    user_id: str,
    session_id: str,
    filename: str,
) -> str:
    part = await service.load_artifact(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        filename=filename,
    )
    if part is None or part.inline_data is None:
        raise ValueError(f"No artifact found for {filename!r}")
    return part.inline_data.data.decode("utf-8")
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_gcs_artifacts.py -v
```

Expected: 1 passed. Confirm the object actually landed in the bucket:

```bash
gcloud storage ls gs://nityam-506707-memory-testbed/memory_storage_testbed/ --recursive
```

- [ ] **Step 5: Commit**

```bash
git add sub_modules_examples/memory_storage_testbed/testbed/gcs_artifacts.py \
        sub_modules_examples/memory_storage_testbed/tests/test_gcs_artifacts.py
git commit -m "feat: add GCS artifact save/load via ADK's GcsArtifactService"
```

---

### Task 5: Redis — workflow-tier write-through

**Files:**
- Create: `sub_modules_examples/memory_storage_testbed/testbed/redis_shortterm.py`
- Test: `sub_modules_examples/memory_storage_testbed/tests/test_redis_shortterm.py`

**Interfaces:**
- Consumes: `redis_client` fixture (used only to confirm reachability; the module makes its own
  `redis.asyncio` connection since the real write-through calls are async — see
  `google_cloud_storage_integration.md` §5.3).
- Produces: `append_turn(session_id, turn, host, port)`, `get_turn_buffer(session_id, host,
  port)`, `clear_session(session_id, host, port)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_redis_shortterm.py
import pytest

from testbed import redis_shortterm
from testbed.config import REDIS_HOST, REDIS_PORT


@pytest.mark.asyncio
async def test_turn_buffer_roundtrip(redis_client):
    session_id = "test_session_redis_1"
    await redis_shortterm.clear_session(session_id, REDIS_HOST, REDIS_PORT)

    await redis_shortterm.append_turn(
        session_id, {"turn": 1, "role": "student", "text": "hi"}, REDIS_HOST, REDIS_PORT
    )
    await redis_shortterm.append_turn(
        session_id, {"turn": 2, "role": "tutor", "text": "hello"}, REDIS_HOST, REDIS_PORT
    )

    buffer = await redis_shortterm.get_turn_buffer(session_id, REDIS_HOST, REDIS_PORT)
    assert len(buffer) == 2
    assert buffer[0]["text"] == "hi"
    assert buffer[1]["role"] == "tutor"

    await redis_shortterm.clear_session(session_id, REDIS_HOST, REDIS_PORT)
    assert await redis_shortterm.get_turn_buffer(session_id, REDIS_HOST, REDIS_PORT) == []
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_redis_shortterm.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'testbed.redis_shortterm'`.

- [ ] **Step 3: Write `testbed/redis_shortterm.py`**

```python
from __future__ import annotations

import json

import redis.asyncio as redis

_SAFETY_TTL_SECONDS = 60 * 60 * 6  # 6h — close_session should flush well before this


def _client(host: str, port: int) -> redis.Redis:
    return redis.Redis(host=host, port=port, decode_responses=True)


async def append_turn(session_id: str, turn: dict, host: str, port: int) -> None:
    client = _client(host, port)
    key = f"session:{session_id}:turns"
    await client.rpush(key, json.dumps(turn))
    await client.expire(key, _SAFETY_TTL_SECONDS)
    await client.aclose()


async def get_turn_buffer(session_id: str, host: str, port: int) -> list[dict]:
    client = _client(host, port)
    raw = await client.lrange(f"session:{session_id}:turns", 0, -1)
    await client.aclose()
    return [json.loads(r) for r in raw]


async def clear_session(session_id: str, host: str, port: int) -> None:
    client = _client(host, port)
    await client.delete(f"session:{session_id}:turns")
    await client.aclose()
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_redis_shortterm.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add sub_modules_examples/memory_storage_testbed/testbed/redis_shortterm.py \
        sub_modules_examples/memory_storage_testbed/tests/test_redis_shortterm.py
git commit -m "feat: add Redis write-through turn buffer for the workflow tier"
```

---

### Task 6: End-to-end demo + AGENTS.md

**Files:**
- Create: `sub_modules_examples/memory_storage_testbed/testbed/demo_end_to_end.py`
- Test: `sub_modules_examples/memory_storage_testbed/tests/test_demo_end_to_end.py`
- Create: `sub_modules_examples/memory_storage_testbed/AGENTS.md`

**Interfaces:**
- Consumes: `put_chunk`/`search_chunks` (Task 2/3), `get_dpm`/`put_dpm`/`put_session_log`/
  `get_session_log` (Task 2), `make_service`/`save_text_artifact`/`load_text_artifact` (Task 4),
  `append_turn`/`get_turn_buffer`/`clear_session` (Task 5). `search_chunks_semantic` (Task 3) is
  not exercised here — it's already covered by its own test in Task 3, and nothing in the
  close_session sequence this demo models does a semantic (as opposed to concept_id-filtered)
  lookup.
- Produces: `run_demo(session_id, student_id, ...)` — the full sequence: seed + retrieve a
  grounding chunk (simulating `search_grounding`), append turns to Redis, build a
  `TestSessionLog` from the Redis buffer, write it to Firestore, put a `dpm`-shaped record, save
  an artifact to GCS, read everything back, return a dict for the caller (test or CLI) to assert
  against/print.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_demo_end_to_end.py
import pytest

from testbed import demo_end_to_end, gcs_artifacts
from testbed.config import GCS_BUCKET, REDIS_HOST, REDIS_PORT


@pytest.mark.asyncio
async def test_full_sequence(firestore_db, gcs_bucket, redis_client):
    try:
        result = await demo_end_to_end.run_demo(
            session_id="test_e2e_session_1",
            student_id="test_e2e_student_1",
            firestore_db=firestore_db,
            gcs_bucket_name=GCS_BUCKET,
            redis_host=REDIS_HOST,
            redis_port=REDIS_PORT,
        )
        assert any(c.chunk_id == "test_e2e_session_1_chunk_1" for c in result["grounding_chunks"])
        assert result["session_log"].turns[0].text == "What is projectile range?"
        assert result["dpm"].note == "asked about projectile range"
        assert result["artifact_text"] == "demo artifact for test_e2e_session_1"
    finally:
        firestore_db.collection("grounding_chunks").document("test_e2e_session_1_chunk_1").delete()
        firestore_db.collection("session_logs").document("test_e2e_session_1").delete()
        firestore_db.collection("dpm_profiles").document("test_e2e_student_1").delete()
        await gcs_artifacts.make_service(GCS_BUCKET).delete_artifact(
            app_name="memory_storage_testbed",
            user_id="test_e2e_student_1",
            session_id="test_e2e_session_1",
            filename="demo_artifact.txt",
        )
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_demo_end_to_end.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'testbed.demo_end_to_end'`.

- [ ] **Step 3: Write `testbed/demo_end_to_end.py`**

```python
from __future__ import annotations

import random

from google.cloud import firestore as firestore_module

from testbed import firestore_store, gcs_artifacts, redis_shortterm
from testbed.schemas import TestChunk, TestProfile, TestSessionLog, TestTurn


def _dummy_embedding(seed: int, dim: int = 1536) -> list[float]:
    rng = random.Random(seed)
    return [rng.uniform(-1, 1) for _ in range(dim)]


async def run_demo(
    session_id: str,
    student_id: str,
    firestore_db: firestore_module.Client,
    gcs_bucket_name: str,
    redis_host: str,
    redis_port: int,
) -> dict:
    # 0. Seed a grounding chunk and retrieve it, simulating TutorAgent's search_grounding
    #    call before it answers the student's question.
    chunk_id = f"{session_id}_chunk_1"
    firestore_store.put_chunk(
        firestore_db,
        TestChunk(chunk_id=chunk_id, concept_ids=["kinematics.projectile_range"], text="Range = u^2 sin(2 theta) / g"),
        _dummy_embedding(seed=7),
    )
    grounding_chunks = firestore_store.search_chunks(firestore_db, ["kinematics.projectile_range"])

    # 1. Live turns land in Redis, exactly like log_turn's write-through would.
    await redis_shortterm.clear_session(session_id, redis_host, redis_port)
    await redis_shortterm.append_turn(
        session_id, {"turn": 1, "role": "student", "text": "What is projectile range?"}, redis_host, redis_port
    )
    await redis_shortterm.append_turn(
        session_id, {"turn": 2, "role": "tutor", "text": "Range = u^2 sin(2 theta) / g."}, redis_host, redis_port
    )

    # 2. close_session reads the buffer back and builds the durable session_log.
    buffer = await redis_shortterm.get_turn_buffer(session_id, redis_host, redis_port)
    log = TestSessionLog(
        session_id=session_id,
        student_id=student_id,
        turns=[TestTurn(**t) for t in buffer],
    )
    firestore_store.put_session_log(firestore_db, log)

    # 3. The Reflect-equivalent step updates the student's long-term profile.
    profile = TestProfile(student_id=student_id, note="asked about projectile range")
    firestore_store.put_dpm(firestore_db, profile)

    # 4. ArtifactAgent's output gets saved to GCS.
    artifact_service = gcs_artifacts.make_service(gcs_bucket_name)
    artifact_text = f"demo artifact for {session_id}"
    await gcs_artifacts.save_text_artifact(
        artifact_service,
        app_name="memory_storage_testbed",
        user_id=student_id,
        session_id=session_id,
        filename="demo_artifact.txt",
        text=artifact_text,
    )

    # 5. Read everything back, proving the round trip end to end.
    read_back_log = firestore_store.get_session_log(firestore_db, session_id)
    read_back_dpm = firestore_store.get_dpm(firestore_db, student_id)
    read_back_artifact = await gcs_artifacts.load_text_artifact(
        artifact_service,
        app_name="memory_storage_testbed",
        user_id=student_id,
        session_id=session_id,
        filename="demo_artifact.txt",
    )

    await redis_shortterm.clear_session(session_id, redis_host, redis_port)

    return {
        "grounding_chunks": grounding_chunks,
        "session_log": read_back_log,
        "dpm": read_back_dpm,
        "artifact_text": read_back_artifact,
    }


if __name__ == "__main__":
    import asyncio

    from testbed import firestore_store as _fs
    from testbed.config import FIRESTORE_DATABASE, GCS_BUCKET, PROJECT_ID, REDIS_HOST, REDIS_PORT

    async def _main() -> None:
        db = _fs.connect(PROJECT_ID, FIRESTORE_DATABASE)
        result = await run_demo(
            session_id="manual_demo_session",
            student_id="manual_demo_student",
            firestore_db=db,
            gcs_bucket_name=GCS_BUCKET,
            redis_host=REDIS_HOST,
            redis_port=REDIS_PORT,
        )
        print("session_log:", result["session_log"].model_dump_json(indent=2))
        print("dpm:", result["dpm"].model_dump_json(indent=2))
        print("artifact_text:", result["artifact_text"])

    asyncio.run(_main())
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_demo_end_to_end.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Run the full suite together**

```bash
uv run pytest -v
```

Expected: all tests across all five test files pass.

- [ ] **Step 6: Manual verification run against real resources**

```bash
uv run python -m testbed.demo_end_to_end
```

Confirm by hand: the printed `session_log`/`dpm`/`artifact_text` look right, the session log
document is visible in the Firestore console under `smriti-testbed` → `session_logs`, and
`demo_artifact.txt` is visible under `gs://nityam-506707-memory-testbed/memory_storage_testbed/
manual_demo_student/manual_demo_session/`. This manual document/object is left in place
afterward as a visible, inspectable artifact of the run — delete it by hand later if desired, it's
not cleaned up automatically the way the pytest-created records are.

- [ ] **Step 7: Write `AGENTS.md`**

```markdown
# Memory Storage Testbed

## Intent

Proves Firestore (structured records + native vector search), GCS (via ADK's
`GcsArtifactService`), and local Redis (standing in for Memorystore) as SMRITI's Google-managed
storage backends — standalone, before `sub_modules_examples/tutor/app/memory/store.py` is
rewritten to use them for real. Spec:
`docs/superpowers/specs/2026-08-27-memory-storage-testbed-design.md`. Research behind the
choices: `project_documentation/memory_nityam_architecture/google_cloud_storage_integration.md`.

## What was proven

- Firestore CRUD for chunk/profile/session_log-shaped documents, against the real
  `smriti-testbed` database.
- Firestore native vector search (`find_nearest`) correctly ranks a near-duplicate vector above
  an unrelated one, against a real vector index.
- `GcsArtifactService.save_artifact`/`load_artifact` round-trip a real object in
  `gs://nityam-506707-memory-testbed`.
- The Redis write-through pattern for the workflow tier: append, read back, clear, TTL.
- The full sequence end to end: turns → Redis → session_log + profile update → Firestore →
  artifact → GCS → read-back.

## What was NOT proven (open items, tracked in google_cloud_storage_integration.md §7)

- Compatibility with Shruti's real 3072-dim embeddings — this testbed used synthetic 1536-dim
  vectors throughout. The dimension conflict (Firestore's 2048 cap) is still open.
- Real Memorystore — local Redis stood in per the design decision in
  `google_cloud_storage_integration.md` §5.4. Validate against real Memorystore once there's a
  Cloud Run deployment to attach it to via VPC.
- Any behavior specific to the real `store.py`'s four actual schemas
  (`GroundingChunk`/`DPMProfile`/`TeachingMemory`/`SessionLog`) — this testbed used deliberately
  minimal standalone shapes (`testbed/schemas.py`) to prove the storage *pattern*, not the exact
  production schema.

## Porting into the real `store.py`

`firestore_store.py`'s functions mirror the real `store.py`'s functions 1:1 by name — porting is
close to: swap `TestChunk`/`TestProfile`/`TestSessionLog` for the real
`GroundingChunk`/`DPMProfile`/`TeachingMemory`/`SessionLog`, point `connect()` at the real
project's Firestore database (not `smriti-testbed`, which stays this testbed's own), and resolve
the embedding-dimension question first (see google_cloud_storage_integration.md §3.3).

## Where to run things

```bash
cd sub_modules_examples/memory_storage_testbed
uv sync
uv run pytest -v                        # full suite, real cloud resources
uv run python -m testbed.demo_end_to_end  # manual run, prints each step's result
```

Requires: `gcloud auth application-default login` done once against project `nityam-506707`,
local Redis running (`brew services start redis`).
```

- [ ] **Step 8: Final commit**

```bash
git add sub_modules_examples/memory_storage_testbed/testbed/demo_end_to_end.py \
        sub_modules_examples/memory_storage_testbed/tests/test_demo_end_to_end.py \
        sub_modules_examples/memory_storage_testbed/AGENTS.md
git commit -m "feat: wire Firestore/GCS/Redis together in demo_end_to_end, document what was proven"
```

---

## After this plan

Nothing in `sub_modules_examples/tutor/` changes automatically. Once every task above is reviewed
and the manual verification run in Task 6 has been inspected by hand (Firestore console, GCS
console), the natural next step — a separate plan, not part of this one — is porting
`firestore_store.py`'s proven pattern into the real `app/memory/store.py`, resolving the
embedding-dimension open item first.
