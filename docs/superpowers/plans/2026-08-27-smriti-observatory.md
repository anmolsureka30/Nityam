# SMRITI Observatory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real-time companion UI that visualizes every SMRITI memory-layer read/write (workflow / episodic / long-term tiers) as a tutor agent session runs, correlated to the live OpenTelemetry trace span that caused it, styled and structured as a natural extension of the real ADK web dev UI.

**Architecture:** Instrument `store.py`/`short_term.py` at the I/O boundary to publish structured `MemoryEvent`s to one global Redis Pub/Sub channel; a standalone FastAPI backend ingests them, computes schema-aware diffs against a live snapshot cache, and serves REST snapshots plus WebSocket streams; a standalone React frontend renders three tier panels and a trace-linked event timeline. Also wires `close_session` (currently invoked only by tests) into the real running app via an explicit endpoint plus an idle-timeout safety net.

**Tech Stack:** Python 3.12, FastAPI, `redis` (sync) + `redis.asyncio`, `google-cloud-firestore`, Pydantic v2, `opentelemetry-api`, `uv`; React 19 + TypeScript 6 + Vite 8 + CSS Modules + oxlint.

**Spec:** `docs/superpowers/specs/2026-08-27-smriti-observatory-design.md`

## Global Constraints

- Every persisted memory operation is instrumented at `store.py`/`short_term.py` — never at `tools.py`, for the event-emission layer specifically (Task 1-3). `tools.py` does get two small, unrelated one-line additions later, for heartbeat/started-at tracking (Task 5).
- All tests run against **real** Firestore (project `nityam-506707`, database `smriti`) and **real local Redis**, skip (don't fail, don't mock) when unreachable — reuse `sub_modules_examples/tutor/tests/conftest.py`'s existing `firestore_db`/`redis_client` fixtures exactly as they are; the Observatory backend's own `conftest.py` (Task 8) copies the same shape.
- Redis event transport is one global channel/list pair — `smriti:events:live` (PUBLISH) and `smriti:events:recent` (RPUSH, capped to 2000 via LTRIM) — never per-session.
- The Observatory backend never re-implements a Firestore/Redis read `store.py`/`short_term.py` already provides — it imports and calls them via a `uv` path dependency on the tutor package.
- The Observatory never re-implements `close_session` — `POST /api/sessions/{id}/close` proxies to the tutor app's own `POST /memory/sessions/{id}/close`.
- Frontend matches `frontend/`'s existing conventions exactly: React 19, Vite 8, TypeScript 6, oxlint, plain CSS Modules (no CSS framework), no UI test-framework dependency — visual tests via a headless-Chrome-over-CDP script, same shape as `frontend/tests/ui.mjs`.
- ADK web's exact dark-theme token values (hex codes in Task 16) are used verbatim, read from the real installed `google-adk==2.7.1` package — not approximated.
- No placeholder/TODO code anywhere. No new dependency without a concrete reason stated in the task that adds it.

---

## Part A — Tutor app: instrumentation (`sub_modules_examples/tutor`)

### Task 1: Memory event schema + instrumentation decorator

**Files:**
- Create: `sub_modules_examples/tutor/app/memory/instrumentation.py`
- Modify: `sub_modules_examples/tutor/tests/conftest.py` (add one autouse fixture)
- Test: `sub_modules_examples/tutor/tests/unit/memory/test_instrumentation.py`

**Interfaces:**
- Produces: `MemoryEvent` (Pydantic model with fields `event_id, ts, session_id, student_id, tier, operation, record_type, source_fn, trace_id, span_id, payload`), `emit_memory_event(tier, record_type, operation, extract_ids)` decorator factory where `extract_ids(args, kwargs, result) -> (session_id, student_id)`, `set_session_context(session_id: str | None) -> None`, `get_session_context() -> str | None`.
- Consumes: nothing from other tasks (foundation task).

**Note on the autouse fixture:** `set_session_context`'s contextvar is process-global for the duration it's set — nothing resets it automatically between test functions (Task 4's `close_session` test, for instance, sets it and has no reason to know it must clean up after itself). Rather than requiring every future test that touches this to remember manual cleanup, `conftest.py` gets one autouse fixture resetting it before and after every test — this is the correct place to guarantee isolation once, rather than scattered `finally` blocks.

- [ ] **Step 1: Write the failing tests**

```python
# sub_modules_examples/tutor/tests/unit/memory/test_instrumentation.py
from __future__ import annotations

import pytest

from app.memory import instrumentation


def test_sync_wrapper_publishes_event_with_extracted_ids(redis_client):
    redis_client.delete("smriti:events:recent")

    @instrumentation.emit_memory_event(
        tier="long_term",
        record_type="dpm_profile",
        operation="read",
        extract_ids=lambda args, kwargs, result: (None, "student_x"),
    )
    def fake_get_dpm(db, student_id):
        return {"student_id": student_id}

    fake_get_dpm(None, "student_x")

    raw = redis_client.lrange("smriti:events:recent", -1, -1)
    assert len(raw) == 1
    event = instrumentation.MemoryEvent.model_validate_json(raw[0])
    assert event.tier == "long_term"
    assert event.record_type == "dpm_profile"
    assert event.operation == "read"
    assert event.student_id == "student_x"
    assert event.session_id is None
    assert event.source_fn == "fake_get_dpm"
    assert event.payload == {"student_id": "student_x"}


def test_sync_wrapper_returns_original_result_unchanged(redis_client):
    @instrumentation.emit_memory_event(
        tier="long_term", record_type="dpm_profile", operation="read",
        extract_ids=lambda args, kwargs, result: (None, None),
    )
    def fake_fn(x):
        return x * 2

    assert fake_fn(21) == 42


@pytest.mark.asyncio
async def test_async_wrapper_publishes_event(redis_client):
    redis_client.delete("smriti:events:recent")

    @instrumentation.emit_memory_event(
        tier="workflow", record_type="turn_buffer", operation="write",
        extract_ids=lambda args, kwargs, result: (args[0], None),
    )
    async def fake_append_turn(session_id, turn):
        return {"buffer_length": 1}

    await fake_append_turn("sess-1", {"turn": 1})

    raw = redis_client.lrange("smriti:events:recent", -1, -1)
    event = instrumentation.MemoryEvent.model_validate_json(raw[0])
    assert event.session_id == "sess-1"
    assert event.tier == "workflow"
    assert event.record_type == "turn_buffer"


def test_session_context_fills_in_when_extractor_uses_it(redis_client):
    redis_client.delete("smriti:events:recent")
    instrumentation.set_session_context("sess-ctx")

    def extract(args, kwargs, result):
        return instrumentation.get_session_context(), "student_y"

    @instrumentation.emit_memory_event(
        tier="long_term", record_type="dpm_profile", operation="write", extract_ids=extract,
    )
    def fake_put_dpm(db, student_id):
        return None

    fake_put_dpm(None, "student_y")

    raw = redis_client.lrange("smriti:events:recent", -1, -1)
    event = instrumentation.MemoryEvent.model_validate_json(raw[0])
    assert event.session_id == "sess-ctx"
    instrumentation.set_session_context(None)  # don't leak into other tests


def test_publishes_even_when_both_session_and_student_id_are_none(redis_client):
    """search_grounding/search_grounding_semantic/put_grounding_chunk (Task 2)
    never have either id at all — grounding_chunk records aren't per-session
    or per-student. The whole point of the global (not per-session) channel
    is that these still publish, not get silently dropped."""
    redis_client.delete("smriti:events:recent")

    @instrumentation.emit_memory_event(
        tier="long_term", record_type="grounding_chunk", operation="read",
        extract_ids=lambda args, kwargs, result: (None, None),
    )
    def fake_search(db, concept_ids):
        return []

    fake_search(None, ["x"])

    raw = redis_client.lrange("smriti:events:recent", 0, -1)
    assert len(raw) == 1
    event = instrumentation.MemoryEvent.model_validate_json(raw[0])
    assert event.session_id is None
    assert event.student_id is None
    assert event.record_type == "grounding_chunk"


def test_publish_failure_does_not_raise(monkeypatch, redis_client):
    """A Redis hiccup must never break a real memory write — the whole point
    of fire-and-forget."""
    @instrumentation.emit_memory_event(
        tier="workflow", record_type="turn_buffer", operation="write",
        extract_ids=lambda args, kwargs, result: ("sess-broken", None),
    )
    def fake_fn():
        return "ok"

    monkeypatch.setattr(
        instrumentation, "_get_sync_client",
        lambda: (_ for _ in ()).throw(ConnectionError("simulated outage")),
    )
    assert fake_fn() == "ok"  # must not raise


def test_broken_extractor_does_not_raise(redis_client):
    """Tasks 2-4 write ~13 extract_ids functions — a bug in one of them must
    never propagate out and break the real memory write it's observing."""
    @instrumentation.emit_memory_event(
        tier="workflow", record_type="turn_buffer", operation="write",
        extract_ids=lambda args, kwargs, result: (_ for _ in ()).throw(IndexError("bad extractor")),
    )
    def fake_fn():
        return "ok"

    assert fake_fn() == "ok"  # must not raise, despite the broken extractor
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd sub_modules_examples/tutor && uv run pytest tests/unit/memory/test_instrumentation.py -v`
Expected: FAIL / ERROR — `ModuleNotFoundError: No module named 'app.memory.instrumentation'`

- [ ] **Step 3: Implement `instrumentation.py`**

```python
# sub_modules_examples/tutor/app/memory/instrumentation.py
"""Publishes a structured MemoryEvent to Redis for every persisted memory
operation, so an external observer (the SMRITI Observatory) can watch
memory tiers change in real time without touching store.py/short_term.py's
own logic. Fire-and-forget: a Redis hiccup here must never break a real
memory write. One global channel/list, not per-session — several store.py
functions (get_dpm, put_dpm, get_teaching_memory, put_teaching_memory)
never receive a session_id at all, and a per-session scheme would silently
drop them (see google_cloud_storage_integration.md-adjacent design note in
docs/superpowers/specs/2026-08-27-smriti-observatory-design.md §5).
"""
from __future__ import annotations

import contextvars
import functools
import inspect
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Literal

import redis as redis_sync
import redis.asyncio as redis_async
from opentelemetry import trace
from pydantic import BaseModel

from app import config

_CHANNEL = "smriti:events:live"
_LIST_KEY = "smriti:events:recent"
_LIST_CAP = 2000

Tier = Literal["workflow", "episodic", "long_term"]
Operation = Literal["read", "write"]
RecordType = Literal[
    "grounding_chunk", "dpm_profile", "teaching_memory",
    "session_log", "turn_buffer", "artifact_event",
]

_session_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "smriti_session_id", default=None
)


def set_session_context(session_id: str | None) -> None:
    """Set the session id long-term-tier writes should carry when their own
    arguments don't include one (only session_close.py calls this — see
    Task 4)."""
    _session_ctx.set(session_id)


def get_session_context() -> str | None:
    return _session_ctx.get()


class MemoryEvent(BaseModel):
    event_id: str
    ts: str
    session_id: str | None
    student_id: str | None
    tier: Tier
    operation: Operation
    record_type: RecordType
    source_fn: str
    trace_id: str | None
    span_id: str | None
    payload: Any = None


_sync_client: redis_sync.Redis | None = None


def _get_sync_client() -> redis_sync.Redis:
    global _sync_client
    if _sync_client is None:
        _sync_client = redis_sync.Redis(
            host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True
        )
    return _sync_client


def _current_trace_ids() -> tuple[str | None, str | None]:
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None, None
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value


def _build_event(
    tier: Tier, record_type: RecordType, operation: Operation, fn_name: str,
    session_id: str | None, student_id: str | None, result: Any,
) -> MemoryEvent:
    trace_id, span_id = _current_trace_ids()
    return MemoryEvent(
        event_id=str(uuid.uuid4()),
        ts=datetime.now(timezone.utc).isoformat(),
        session_id=session_id,
        student_id=student_id,
        tier=tier,
        operation=operation,
        record_type=record_type,
        source_fn=fn_name,
        trace_id=trace_id,
        span_id=span_id,
        payload=_to_jsonable(result),
    )


def _publish_sync(event: MemoryEvent) -> None:
    """No gate on session_id/student_id here — several long-term-tier
    functions (search_grounding, search_grounding_semantic,
    put_grounding_chunk) never have either at all, and the whole point of
    the global (not per-session) channel is that those events are still
    worth seeing, not silently dropped. See spec §5: "every event — scoped
    or not — publishes.\""""
    try:
        client = _get_sync_client()
        body = event.model_dump_json()
        client.publish(_CHANNEL, body)
        client.rpush(_LIST_KEY, body)
        client.ltrim(_LIST_KEY, -_LIST_CAP, -1)
    except Exception:
        pass


async def _publish_async(event: MemoryEvent) -> None:
    try:
        client = redis_async.Redis(
            host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True
        )
        body = event.model_dump_json()
        await client.publish(_CHANNEL, body)
        await client.rpush(_LIST_KEY, body)
        await client.ltrim(_LIST_KEY, -_LIST_CAP, -1)
        await client.aclose()
    except Exception:
        pass


def emit_memory_event(
    tier: Tier,
    record_type: RecordType,
    operation: Operation,
    extract_ids: Callable[[tuple, dict, Any], tuple[str | None, str | None]],
):
    """extract_ids(args, kwargs, result) -> (session_id, student_id).

    Sync-wrapped functions (store.py) publish via a plain blocking
    redis.Redis client; async-wrapped functions (short_term.py) publish
    with await on their own redis.asyncio client — this split means the
    decorator never has to create an event loop from inside a sync call
    path, and never blocks an async caller on a second client's setup.
    """
    def decorator(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                result = await fn(*args, **kwargs)
                try:
                    session_id, student_id = extract_ids(args, kwargs, result)
                    event = _build_event(
                        tier, record_type, operation, fn.__name__, session_id, student_id, result
                    )
                    await _publish_async(event)
                except Exception:
                    # A bug in a future extract_ids (Tasks 2-4 write ~13 of
                    # them) must never propagate out of a real memory write
                    # it's merely observing — same fire-and-forget guarantee
                    # as _publish_sync/_publish_async's own try/except.
                    pass
                return result
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(*args, **kwargs):
                result = fn(*args, **kwargs)
                try:
                    session_id, student_id = extract_ids(args, kwargs, result)
                    event = _build_event(
                        tier, record_type, operation, fn.__name__, session_id, student_id, result
                    )
                    _publish_sync(event)
                except Exception:
                    pass
                return result
            return sync_wrapper
    return decorator
```

- [ ] **Step 4: Add the autouse isolation fixture**

Append to `sub_modules_examples/tutor/tests/conftest.py`:

```python
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
```

(`pytest` is already imported at the top of `conftest.py`.)

- [ ] **Step 5: Run to verify it passes**

Run: `cd sub_modules_examples/tutor && uv run pytest tests/unit/memory/test_instrumentation.py -v`
Expected: 7 passed (or skipped if Redis is unreachable — start it first: `brew services start redis` / `redis-server`)

- [ ] **Step 6: Commit**

```bash
cd sub_modules_examples/tutor
git add app/memory/instrumentation.py tests/conftest.py tests/unit/memory/test_instrumentation.py
git commit -m "feat: add memory-event instrumentation decorator"
```

---

### Task 2: Instrument `store.py`'s 9 functions

**Files:**
- Modify: `sub_modules_examples/tutor/app/memory/store.py`
- Test: `sub_modules_examples/tutor/tests/unit/memory/test_store.py` (append new tests; every existing test in this file must keep passing unmodified — the decorator is a transparent pass-through)

**Interfaces:**
- Consumes: `instrumentation.emit_memory_event`, `instrumentation.get_session_context` (Task 1).
- Produces: no new public API — `store.py`'s existing function names/signatures/return values are unchanged. Downstream tasks (7 backend tasks) rely on this being true.

Exact tier/record_type/operation mapping, and why each function's `extract_ids` looks the way it does:

| Function | tier | record_type | operation | session_id source | student_id source |
|---|---|---|---|---|---|
| `put_grounding_chunk` | long_term | grounding_chunk | write | none (chunks aren't per-student) | none |
| `search_grounding` | long_term | grounding_chunk | read | none | none |
| `search_grounding_semantic` | long_term | grounding_chunk | read | none | none |
| `get_dpm` | long_term | dpm_profile | read | context var | `args[1]`/`student_id` kwarg |
| `put_dpm` | long_term | dpm_profile | write | context var | `profile.student_id` |
| `get_teaching_memory` | long_term | teaching_memory | read | context var | `args[1]`/`student_id` kwarg |
| `put_teaching_memory` | long_term | teaching_memory | write | context var | `memory.student_id` |
| `put_session_log` | episodic | session_log | write | `log.session_id` | `log.student_id` |
| `get_session_log` | episodic | session_log | read | `args[1]`/`session_id` kwarg | none |

- [ ] **Step 1: Write the failing tests**

Append to `sub_modules_examples/tutor/tests/unit/memory/test_store.py`:

```python
from app.memory import instrumentation


def test_put_dpm_publishes_event_scoped_by_context(firestore_db, redis_client):
    redis_client.delete("smriti:events:recent")
    instrumentation.set_session_context("test_store_sess_1")
    try:
        store.put_dpm(firestore_db, DPMProfile(student_id="test_instr_student"))
        raw = redis_client.lrange("smriti:events:recent", -1, -1)
        event = instrumentation.MemoryEvent.model_validate_json(raw[0])
        assert event.tier == "long_term"
        assert event.record_type == "dpm_profile"
        assert event.operation == "write"
        assert event.session_id == "test_store_sess_1"
        assert event.student_id == "test_instr_student"
    finally:
        instrumentation.set_session_context(None)
        firestore_db.collection("dpm_profiles").document("test_instr_student").delete()


def test_get_dpm_publishes_read_event_with_student_id_no_session(firestore_db, redis_client):
    redis_client.delete("smriti:events:recent")
    store.get_dpm(firestore_db, "test_instr_student_missing")
    raw = redis_client.lrange("smriti:events:recent", -1, -1)
    event = instrumentation.MemoryEvent.model_validate_json(raw[0])
    assert event.tier == "long_term"
    assert event.record_type == "dpm_profile"
    assert event.operation == "read"
    assert event.student_id == "test_instr_student_missing"
    assert event.session_id is None  # no context set in this test -> no publish check needed, but call must not raise


def test_put_session_log_publishes_event_scoped_by_log(firestore_db, redis_client):
    redis_client.delete("smriti:events:recent")
    log = SessionLog(
        session_id="test_store_sess_2", student_id="test_instr_student_2",
        started_at=datetime.now(timezone.utc), ended_at=datetime.now(timezone.utc), turns=[],
    )
    try:
        store.put_session_log(firestore_db, log)
        raw = redis_client.lrange("smriti:events:recent", -1, -1)
        event = instrumentation.MemoryEvent.model_validate_json(raw[0])
        assert event.tier == "episodic"
        assert event.record_type == "session_log"
        assert event.session_id == "test_store_sess_2"
        assert event.student_id == "test_instr_student_2"
    finally:
        firestore_db.collection("session_logs").document("test_store_sess_2").delete()


def test_existing_store_behavior_unaffected_by_instrumentation(firestore_db):
    """Sanity check: decoration must not change return values. Full coverage
    already lives in the tests above this one in the file."""
    assert store.get_dpm(firestore_db, "test_instr_student_missing") is None
```

(Note: `datetime`, `timezone`, and `SessionLog` are already imported at the top of `test_store.py` per its existing test functions — no new imports needed beyond `instrumentation`.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd sub_modules_examples/tutor && uv run pytest tests/unit/memory/test_store.py -v -k instrumentation or publishes`
Expected: FAIL — `AttributeError` (no `redis_client` events published because `store.py` isn't decorated yet) or import errors; the new assertions fail against an empty list.

- [ ] **Step 3: Decorate `store.py`**

Add the import and 9 decorators. Full resulting file:

```python
# sub_modules_examples/tutor/app/memory/store.py
"""One shared Firestore backing store for the memory layer — the same tool
functions in app/memory/tools.py call these, so TutorAgent and ArtifactAgent
read through one physical store, not separate copies (memory_layer.md §3, §5).

Replaces the earlier SQLite implementation 1:1 by function name/shape — see
project_documentation/memory_nityam_architecture/google_cloud_storage_integration.md
§3.5 for the migration this was ported from.

Every function below is instrumented (docs/superpowers/specs/2026-08-27-smriti-observatory-design.md
§5) — the decorator is a transparent pass-through, return values are unchanged.
"""
from __future__ import annotations

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector

from app import config
from app.memory import instrumentation
from app.memory.schemas import DPMProfile, GroundingChunk, SessionLog, TeachingMemory


def connect(project: str | None = None, database: str | None = None) -> firestore.Client:
    return firestore.Client(
        project=project or config.GCP_PROJECT,
        database=database or config.FIRESTORE_DATABASE,
    )


def _ids_none(args, kwargs, result):
    return None, None


def _ids_student_from_arg1(args, kwargs, result):
    student_id = kwargs.get("student_id", args[1] if len(args) > 1 else None)
    return instrumentation.get_session_context(), student_id


def _ids_from_profile(args, kwargs, result):
    profile = kwargs.get("profile", args[1] if len(args) > 1 else None)
    return instrumentation.get_session_context(), getattr(profile, "student_id", None)


def _ids_from_memory(args, kwargs, result):
    memory = kwargs.get("memory", args[1] if len(args) > 1 else None)
    return instrumentation.get_session_context(), getattr(memory, "student_id", None)


def _ids_from_log(args, kwargs, result):
    log = kwargs.get("log", args[1] if len(args) > 1 else None)
    return getattr(log, "session_id", None), getattr(log, "student_id", None)


def _ids_session_from_arg1(args, kwargs, result):
    session_id = kwargs.get("session_id", args[1] if len(args) > 1 else None)
    return session_id, None


@instrumentation.emit_memory_event(
    tier="long_term", record_type="grounding_chunk", operation="write", extract_ids=_ids_none,
)
def put_grounding_chunk(
    db: firestore.Client, chunk: GroundingChunk, embedding: list[float] | None = None
) -> None:
    """`embedding` is optional: Shruti's own embedder currently emits 3072-dim
    vectors, over Firestore's 2048-dim vector-index cap (see
    google_cloud_storage_integration.md §3.3 — a companion, smaller-dimension
    embedding for this field is a still-open item). Concept-id search
    (search_grounding) works identically with or without it; semantic search
    (search_grounding_semantic) only returns a chunk once it has one."""
    payload = chunk.model_dump(mode="json")
    if embedding is not None:
        payload["embedding"] = Vector(embedding)
    db.collection("grounding_chunks").document(chunk.chunk_id).set(payload)


@instrumentation.emit_memory_event(
    tier="long_term", record_type="grounding_chunk", operation="read", extract_ids=_ids_none,
)
def search_grounding(db: firestore.Client, concept_ids: list[str], limit: int = 5) -> list[GroundingChunk]:
    if not concept_ids:
        return []
    docs = (
        db.collection("grounding_chunks")
        .where(filter=FieldFilter("concept_ids", "array_contains_any", concept_ids))
        .limit(limit)
        .get()
    )
    return [
        GroundingChunk.model_validate({k: v for k, v in d.to_dict().items() if k != "embedding"})
        for d in docs
    ]


@instrumentation.emit_memory_event(
    tier="long_term", record_type="grounding_chunk", operation="read", extract_ids=_ids_none,
)
def search_grounding_semantic(
    db: firestore.Client,
    query_embedding: list[float],
    concept_ids: list[str] | None = None,
    limit: int = 5,
) -> list[GroundingChunk]:
    """Vector-similarity variant — use when a query doesn't cleanly resolve to
    known concept_ids. Only returns chunks that were written with an
    embedding (see put_grounding_chunk)."""
    q = db.collection("grounding_chunks")
    if concept_ids:
        q = q.where(filter=FieldFilter("concept_ids", "array_contains_any", concept_ids))
    docs = q.find_nearest(
        vector_field="embedding",
        query_vector=Vector(query_embedding),
        distance_measure=DistanceMeasure.COSINE,
        limit=limit,
    ).get()
    return [
        GroundingChunk.model_validate({k: v for k, v in d.to_dict().items() if k != "embedding"})
        for d in docs
    ]


@instrumentation.emit_memory_event(
    tier="long_term", record_type="dpm_profile", operation="read", extract_ids=_ids_student_from_arg1,
)
def get_dpm(db: firestore.Client, student_id: str) -> DPMProfile | None:
    doc = db.collection("dpm_profiles").document(student_id).get()
    return DPMProfile.model_validate(doc.to_dict()) if doc.exists else None


@instrumentation.emit_memory_event(
    tier="long_term", record_type="dpm_profile", operation="write", extract_ids=_ids_from_profile,
)
def put_dpm(db: firestore.Client, profile: DPMProfile) -> None:
    db.collection("dpm_profiles").document(profile.student_id).set(profile.model_dump(mode="json"))


@instrumentation.emit_memory_event(
    tier="long_term", record_type="teaching_memory", operation="read", extract_ids=_ids_student_from_arg1,
)
def get_teaching_memory(db: firestore.Client, student_id: str) -> TeachingMemory | None:
    doc = db.collection("teaching_memories").document(student_id).get()
    return TeachingMemory.model_validate(doc.to_dict()) if doc.exists else None


@instrumentation.emit_memory_event(
    tier="long_term", record_type="teaching_memory", operation="write", extract_ids=_ids_from_memory,
)
def put_teaching_memory(db: firestore.Client, memory: TeachingMemory) -> None:
    db.collection("teaching_memories").document(memory.student_id).set(memory.model_dump(mode="json"))


@instrumentation.emit_memory_event(
    tier="episodic", record_type="session_log", operation="write", extract_ids=_ids_from_log,
)
def put_session_log(db: firestore.Client, log: SessionLog) -> None:
    db.collection("session_logs").document(log.session_id).set(log.model_dump(mode="json"))


@instrumentation.emit_memory_event(
    tier="episodic", record_type="session_log", operation="read", extract_ids=_ids_session_from_arg1,
)
def get_session_log(db: firestore.Client, session_id: str) -> SessionLog | None:
    doc = db.collection("session_logs").document(session_id).get()
    return SessionLog.model_validate(doc.to_dict()) if doc.exists else None
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd sub_modules_examples/tutor && uv run pytest tests/unit/memory/test_store.py -v`
Expected: all tests pass, including every pre-existing test in the file (unchanged assertions) plus the new instrumentation tests.

- [ ] **Step 5: Commit**

```bash
cd sub_modules_examples/tutor
git add app/memory/store.py tests/unit/memory/test_store.py
git commit -m "feat: instrument store.py's 9 functions with memory events"
```

---

### Task 3: Instrument `short_term.py`'s 4 functions

**Files:**
- Modify: `sub_modules_examples/tutor/app/memory/short_term.py`
- Test: `sub_modules_examples/tutor/tests/unit/memory/test_short_term.py` (new file — no such test file exists today; `short_term.py` is currently only exercised indirectly via `test_tools.py`)

**Interfaces:**
- Consumes: `instrumentation.emit_memory_event` (Task 1).
- Produces: no change to `short_term.py`'s existing signatures/behavior.

| Function | tier | record_type | operation |
|---|---|---|---|
| `append_turn` | workflow | turn_buffer | write |
| `append_artifact_event` | workflow | artifact_event | write |
| `get_turn_buffer` | workflow | turn_buffer | read |
| `clear_session` | workflow | turn_buffer | write |

All four take `session_id` as their first positional argument — one shared extractor.

- [ ] **Step 1: Write the failing test**

```python
# sub_modules_examples/tutor/tests/unit/memory/test_short_term.py
from __future__ import annotations

import pytest

from app.memory import instrumentation, short_term


@pytest.mark.asyncio
async def test_append_turn_publishes_workflow_event(redis_client):
    redis_client.delete("smriti:events:recent")
    try:
        await short_term.append_turn("test_st_sess_1", {"turn": 1, "role": "student", "text": "hi"})
        raw = redis_client.lrange("smriti:events:recent", -1, -1)
        event = instrumentation.MemoryEvent.model_validate_json(raw[0])
        assert event.tier == "workflow"
        assert event.record_type == "turn_buffer"
        assert event.operation == "write"
        assert event.session_id == "test_st_sess_1"
    finally:
        redis_client.delete("session:test_st_sess_1:turns")


@pytest.mark.asyncio
async def test_get_turn_buffer_publishes_read_event(redis_client):
    redis_client.delete("smriti:events:recent")
    try:
        await short_term.append_turn("test_st_sess_2", {"turn": 1, "role": "student", "text": "hi"})
        redis_client.delete("smriti:events:recent")  # isolate the read event
        result = await short_term.get_turn_buffer("test_st_sess_2")
        assert result == [{"turn": 1, "role": "student", "text": "hi"}]
        raw = redis_client.lrange("smriti:events:recent", -1, -1)
        event = instrumentation.MemoryEvent.model_validate_json(raw[0])
        assert event.operation == "read"
        assert event.session_id == "test_st_sess_2"
    finally:
        redis_client.delete("session:test_st_sess_2:turns")


@pytest.mark.asyncio
async def test_clear_session_publishes_write_event(redis_client):
    redis_client.delete("smriti:events:recent")
    await short_term.append_turn("test_st_sess_3", {"turn": 1, "role": "student", "text": "hi"})
    redis_client.delete("smriti:events:recent")
    await short_term.clear_session("test_st_sess_3")
    raw = redis_client.lrange("smriti:events:recent", -1, -1)
    event = instrumentation.MemoryEvent.model_validate_json(raw[0])
    assert event.tier == "workflow"
    assert event.record_type == "turn_buffer"
    assert event.operation == "write"
    assert event.session_id == "test_st_sess_3"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd sub_modules_examples/tutor && uv run pytest tests/unit/memory/test_short_term.py -v`
Expected: FAIL — no events published yet, `redis_client.lrange(...)` returns `[]`, `raw[0]` raises `IndexError`.

- [ ] **Step 3: Decorate `short_term.py`**

```python
# sub_modules_examples/tutor/app/memory/short_term.py
"""Write-through mirror of the workflow tier's turn buffer into Redis
(Memorystore in deployment). Deliberately NOT a swap of ADK's own
SessionService — log_turn/log_artifact_evidence keep writing to
tool_context.state first (free, in-process, unchanged), and additionally
write through here so the buffer survives outside one process's memory.
See project_documentation/memory_nityam_architecture/google_cloud_storage_integration.md
§5.2 for why this is a mirror, not a session-service swap.

Every function below is instrumented (docs/superpowers/specs/2026-08-27-smriti-observatory-design.md
§5) — the decorator is a transparent pass-through, return values are unchanged.
"""
from __future__ import annotations

import json

import redis.asyncio as redis

from app import config
from app.memory import instrumentation

_SAFETY_TTL_SECONDS = 60 * 60 * 6  # 6h - close_session should flush well before this


def _client(host: str | None = None, port: int | None = None) -> redis.Redis:
    return redis.Redis(
        host=host or config.REDIS_HOST,
        port=port or config.REDIS_PORT,
        decode_responses=True,
    )


def _ids_from_session_id_arg(args, kwargs, result):
    session_id = kwargs.get("session_id", args[0] if len(args) > 0 else None)
    return session_id, None


@instrumentation.emit_memory_event(
    tier="workflow", record_type="turn_buffer", operation="write",
    extract_ids=_ids_from_session_id_arg,
)
async def append_turn(session_id: str, turn: dict) -> None:
    client = _client()
    key = f"session:{session_id}:turns"
    await client.rpush(key, json.dumps(turn))
    await client.expire(key, _SAFETY_TTL_SECONDS)
    await client.aclose()


@instrumentation.emit_memory_event(
    tier="workflow", record_type="artifact_event", operation="write",
    extract_ids=_ids_from_session_id_arg,
)
async def append_artifact_event(session_id: str, event: dict) -> None:
    client = _client()
    key = f"session:{session_id}:artifact_events"
    await client.rpush(key, json.dumps(event))
    await client.expire(key, _SAFETY_TTL_SECONDS)
    await client.aclose()


@instrumentation.emit_memory_event(
    tier="workflow", record_type="turn_buffer", operation="read",
    extract_ids=_ids_from_session_id_arg,
)
async def get_turn_buffer(session_id: str) -> list[dict]:
    client = _client()
    raw = await client.lrange(f"session:{session_id}:turns", 0, -1)
    await client.aclose()
    return [json.loads(r) for r in raw]


@instrumentation.emit_memory_event(
    tier="workflow", record_type="turn_buffer", operation="write",
    extract_ids=_ids_from_session_id_arg,
)
async def clear_session(session_id: str) -> None:
    client = _client()
    await client.delete(f"session:{session_id}:turns", f"session:{session_id}:artifact_events")
    await client.aclose()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd sub_modules_examples/tutor && uv run pytest tests/unit/memory/test_short_term.py tests/unit/memory/test_tools.py -v`
Expected: all pass — including `test_tools.py`'s pre-existing `log_turn`/`log_artifact_evidence` tests, unaffected by the decoration.

- [ ] **Step 5: Commit**

```bash
cd sub_modules_examples/tutor
git add app/memory/short_term.py tests/unit/memory/test_short_term.py
git commit -m "feat: instrument short_term.py's 4 functions with memory events"
```

---

### Task 4: Thread session id into `close_session`

**Files:**
- Modify: `sub_modules_examples/tutor/app/session_close.py:101-120` (the `close_session` function)
- Test: `sub_modules_examples/tutor/tests/unit/test_session_close.py` (append one test)

**Interfaces:**
- Consumes: `instrumentation.set_session_context` (Task 1).
- Produces: no change to `close_session`'s signature or return value.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_session_close.py`:

```python
from app.memory import instrumentation


def test_close_session_scopes_long_term_writes_to_session_context(firestore_db, monkeypatch, redis_client):
    """The whole point of Task 4: put_dpm/put_teaching_memory don't receive
    a session_id argument, so close_session must set the context var itself
    before calling them."""
    redis_client.delete("smriti:events:recent")
    stub_result = ReflectResult(
        summary="", operations=[ReflectOp(op="set_mastery", args={
            "concept_id": "projectile.range", "mastery": "partial",
            "strength": "weak", "evidence": ["s1#2"],
        })],
    )
    monkeypatch.setattr(session_close, "reflect", lambda client, log: stub_result)

    try:
        close_session(
            firestore_db, "test_s_ctx_1", "test_demo_student_ctx", datetime.now(timezone.utc),
            [{"turn": 1, "role": "student", "text": "x", "concept_id": None, "artifact_id": None}],
            client=None,
        )
        events = [
            instrumentation.MemoryEvent.model_validate_json(raw)
            for raw in redis_client.lrange("smriti:events:recent", 0, -1)
        ]
        dpm_writes = [e for e in events if e.record_type == "dpm_profile" and e.operation == "write"]
        assert len(dpm_writes) == 1
        assert dpm_writes[0].session_id == "test_s_ctx_1"
    finally:
        firestore_db.collection("session_logs").document("test_s_ctx_1").delete()
        firestore_db.collection("dpm_profiles").document("test_demo_student_ctx").delete()
        firestore_db.collection("teaching_memories").document("test_demo_student_ctx").delete()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd sub_modules_examples/tutor && uv run pytest tests/unit/test_session_close.py -v -k session_context`
Expected: FAIL — `dpm_writes[0].session_id` is `None`, not `"test_s_ctx_1"`.

- [ ] **Step 3: Add the one line**

Modify `app/session_close.py`: add the import at the top and one line at the start of `close_session`'s body.

```python
# app/session_close.py:16 — add to the existing import block
from app.memory import ops, store
from app.memory import instrumentation  # NEW
```

```python
# app/session_close.py:101-110 — close_session, before the existing body
def close_session(
    conn: firestore.Client,
    session_id: str,
    student_id: str,
    started_at: datetime,
    buffer: list[dict],
    client: genai.Client,
) -> SessionLog:
    instrumentation.set_session_context(session_id)  # NEW — see Task 4
    log = build_session_log(session_id, student_id, started_at, buffer)
    store.put_session_log(conn, log)
    ...  # rest of the function is unchanged
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd sub_modules_examples/tutor && uv run pytest tests/unit/test_session_close.py -v`
Expected: all pass, including the pre-existing orchestration test.

- [ ] **Step 5: Commit**

```bash
cd sub_modules_examples/tutor
git add app/session_close.py tests/unit/test_session_close.py
git commit -m "feat: scope close_session's long-term writes to the session context var"
```

---

## Part B — Tutor app: wiring `close_session` into production

### Task 5: Heartbeat + started-at tracking in `short_term.py`, wired into `tools.py`

**Files:**
- Modify: `sub_modules_examples/tutor/app/memory/short_term.py` (add 3 functions)
- Modify: `sub_modules_examples/tutor/app/memory/tools.py:68-115` (`log_turn`, `log_artifact_evidence`)
- Modify: `sub_modules_examples/tutor/app/config.py` (one new env var)
- Test: `sub_modules_examples/tutor/tests/unit/memory/test_short_term.py` (append), `tests/unit/memory/test_tools.py` (append)

**Interfaces:**
- Produces: `short_term.refresh_heartbeat(session_id, ttl_seconds) -> None`, `short_term.ensure_started_at(session_id) -> None`, `short_term.get_started_at(session_id) -> datetime | None`.
- Consumed by: Task 6 (`memory_routes.py` reads `get_started_at`), Task 7 (idle-timeout watcher relies on the heartbeat key expiring).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/memory/test_short_term.py`:

```python
from datetime import datetime

import time as _time


@pytest.mark.asyncio
async def test_refresh_heartbeat_sets_a_ttl_key(redis_client):
    try:
        await short_term.refresh_heartbeat("test_st_hb_1", ttl_seconds=2)
        assert redis_client.get("session:test_st_hb_1:heartbeat") == "1"
        ttl = redis_client.ttl("session:test_st_hb_1:heartbeat")
        assert 0 < ttl <= 2
    finally:
        redis_client.delete("session:test_st_hb_1:heartbeat")


@pytest.mark.asyncio
async def test_ensure_started_at_is_idempotent(redis_client):
    try:
        await short_term.ensure_started_at("test_st_sa_1")
        first = await short_term.get_started_at("test_st_sa_1")
        _time.sleep(0.05)
        await short_term.ensure_started_at("test_st_sa_1")  # second call must not move it
        second = await short_term.get_started_at("test_st_sa_1")
        assert first == second
        assert isinstance(first, datetime)
    finally:
        redis_client.delete("session:test_st_sa_1:started_at")


@pytest.mark.asyncio
async def test_get_started_at_returns_none_when_unset(redis_client):
    assert await short_term.get_started_at("test_st_sa_missing") is None
```

Append to `tests/unit/memory/test_tools.py`:

```python
@pytest.mark.asyncio
async def test_log_turn_refreshes_heartbeat_and_started_at(redis_client):
    ctx = make_tool_context({}, session_id="test_session_heartbeat_1")
    try:
        await tools.log_turn("hi", "student", "", "", ctx)
        assert redis_client.ttl("session:test_session_heartbeat_1:heartbeat") > 0
        assert redis_client.get("session:test_session_heartbeat_1:started_at") is not None
    finally:
        redis_client.delete(
            "session:test_session_heartbeat_1:turns",
            "session:test_session_heartbeat_1:heartbeat",
            "session:test_session_heartbeat_1:started_at",
        )
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd sub_modules_examples/tutor && uv run pytest tests/unit/memory/test_short_term.py tests/unit/memory/test_tools.py -v -k "heartbeat or started_at"`
Expected: FAIL — `AttributeError: module 'app.memory.short_term' has no attribute 'refresh_heartbeat'`.

- [ ] **Step 3: Implement**

Add to `app/config.py`, right after the existing `REDIS_PORT` line:

```python
SESSION_IDLE_TIMEOUT_SECONDS = int(os.environ.get("SESSION_IDLE_TIMEOUT_SECONDS", str(30 * 60)))
"""How long a session can go without a log_turn/log_artifact_evidence call
before the idle-timeout watcher (Task 7) auto-closes it. 30 minutes is a
starting value, not derived from a product requirement — tune via env var."""
```

Add to `app/memory/short_term.py`, after `_SAFETY_TTL_SECONDS`:

```python
async def refresh_heartbeat(session_id: str, ttl_seconds: int) -> None:
    client = _client()
    await client.set(f"session:{session_id}:heartbeat", "1", ex=ttl_seconds)
    await client.aclose()


async def ensure_started_at(session_id: str) -> None:
    """NX so the first call from a session wins; later calls are no-ops."""
    client = _client()
    await client.set(
        f"session:{session_id}:started_at",
        datetime.now(timezone.utc).isoformat(),
        nx=True,
    )
    await client.aclose()


async def get_started_at(session_id: str) -> datetime | None:
    client = _client()
    raw = await client.get(f"session:{session_id}:started_at")
    await client.aclose()
    return datetime.fromisoformat(raw) if raw else None
```

Add the matching import at the top of `short_term.py`:

```python
from datetime import datetime, timezone
```

Modify `app/memory/tools.py:68-94` (`log_turn`) and `:97-114` (`log_artifact_evidence`) — add one call each, right after the existing `short_term.append_*` call:

```python
async def log_turn(text: str, role: str, concept_id: str, artifact_id: str, tool_context: ToolContext) -> dict:
    """...(docstring unchanged)..."""
    buffer = tool_context.state.get("turn_buffer", [])
    turn = {
        "turn": len(buffer) + 1,
        "role": role,
        "text": text,
        "concept_id": concept_id or None,
        "artifact_id": artifact_id or None,
    }
    buffer.append(turn)
    tool_context.state["turn_buffer"] = buffer
    await short_term.append_turn(tool_context.session.id, turn)
    await short_term.ensure_started_at(tool_context.session.id)  # NEW
    await short_term.refresh_heartbeat(tool_context.session.id, config.SESSION_IDLE_TIMEOUT_SECONDS)  # NEW
    return {"buffer_length": len(buffer)}


async def log_artifact_evidence(event: str, artifact_id: str, tool_context: ToolContext) -> dict:
    """...(docstring unchanged)..."""
    events = tool_context.state.get("artifact_events", [])
    entry = {"event": event, "artifact_id": artifact_id}
    events.append(entry)
    tool_context.state["artifact_events"] = events
    await short_term.append_artifact_event(tool_context.session.id, entry)
    await short_term.refresh_heartbeat(tool_context.session.id, config.SESSION_IDLE_TIMEOUT_SECONDS)  # NEW
    return {"logged": True}
```

Add `from app import config` to `tools.py`'s imports (it currently only imports `from app.memory import short_term, store`).

- [ ] **Step 4: Run to verify it passes**

Run: `cd sub_modules_examples/tutor && uv run pytest tests/unit/memory/ -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd sub_modules_examples/tutor
git add app/config.py app/memory/short_term.py app/memory/tools.py tests/unit/memory/test_short_term.py tests/unit/memory/test_tools.py
git commit -m "feat: track session heartbeat and started-at timestamp in Redis"
```

---

### Task 6: `POST /memory/sessions/{id}/close` endpoint

**Files:**
- Create: `sub_modules_examples/tutor/app/app_utils/memory_routes.py`
- Modify: `sub_modules_examples/tutor/app/fast_api_app.py`
- Test: `sub_modules_examples/tutor/tests/unit/test_memory_routes.py`

**Interfaces:**
- Produces: `perform_close_session(session_id: str, student_id: str | None = None) -> SessionLog` (importable, reused by Task 7's idle-timeout watcher), FastAPI `router` mounted at `/memory`.
- Consumes: `store.connect`, `short_term.get_turn_buffer`, `short_term.get_started_at`, `short_term.clear_session`, `session_close.close_session` (all pre-existing).

- [ ] **Step 1: Write the failing test**

```python
# sub_modules_examples/tutor/tests/unit/test_memory_routes.py
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd sub_modules_examples/tutor && uv run pytest tests/unit/test_memory_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.app_utils.memory_routes'`

- [ ] **Step 3: Implement**

```python
# sub_modules_examples/tutor/app/app_utils/memory_routes.py
"""The one real production trigger for close_session — currently the only
path into episodic/long-term memory, previously invoked only by tests. See
docs/superpowers/specs/2026-08-27-smriti-observatory-design.md §6.

perform_close_session is importable so both this router's HTTP handler and
Task 7's idle-timeout background watcher call the exact same logic — no
parallel/fake close path.
"""
from __future__ import annotations

import functools
from datetime import datetime, timezone

from fastapi import APIRouter
from google import genai
from google.cloud import firestore
from pydantic import BaseModel

from app.memory import short_term, store
from app.memory.schemas import SessionLog
from app.session_close import close_session

router = APIRouter(prefix="/memory")


@functools.cache
def _firestore_client() -> firestore.Client:
    return store.connect()


@functools.cache
def _genai_client() -> genai.Client:
    return genai.Client()


async def perform_close_session(session_id: str, student_id: str | None = None) -> SessionLog:
    resolved_student_id = student_id or "demo_student"
    buffer = await short_term.get_turn_buffer(session_id)
    started_at = await short_term.get_started_at(session_id) or datetime.now(timezone.utc)
    log = close_session(
        _firestore_client(), session_id, resolved_student_id, started_at, buffer, _genai_client(),
    )
    await short_term.clear_session(session_id)
    return log


class CloseSessionRequest(BaseModel):
    student_id: str | None = None


@router.post("/sessions/{session_id}/close")
async def close_session_endpoint(session_id: str, body: CloseSessionRequest):
    log = await perform_close_session(session_id, body.student_id)
    return log.model_dump(mode="json")
```

- [ ] **Step 4: Mount the router**

Modify `app/fast_api_app.py` — add the import and one `include_router` call after `app` is constructed:

```python
# app/fast_api_app.py — add to imports
from app.app_utils.memory_routes import router as memory_router
```

```python
# app/fast_api_app.py — right after `app.description = "API for interacting with the Agent tutor"`
app.description = "API for interacting with the Agent tutor"
app.include_router(memory_router)  # NEW
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd sub_modules_examples/tutor && uv run pytest tests/unit/test_memory_routes.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
cd sub_modules_examples/tutor
git add app/app_utils/memory_routes.py app/fast_api_app.py tests/unit/test_memory_routes.py
git commit -m "feat: wire close_session into production via POST /memory/sessions/{id}/close"
```

---

### Task 7: Idle-timeout background watcher

**Files:**
- Modify: `sub_modules_examples/tutor/app/fast_api_app.py` (lifespan)
- Test: `sub_modules_examples/tutor/tests/unit/test_idle_watcher.py`

**Interfaces:**
- Consumes: `memory_routes.perform_close_session` (Task 6), the `session:{id}:heartbeat` key (Task 5).
- Produces: `app/app_utils/idle_watcher.py`'s `watch_idle_sessions() -> None` (an infinite loop, no arguments — it builds its own Redis client internally; tested via a bounded variant, see below), and `run_one_expiry_cycle(pubsub, timeout) -> str | None` (waits up to `timeout` seconds total for one real expiry notification, returns the closed session id or `None` — this is what the test drives, so the test doesn't need to run or cancel an infinite loop).

- [ ] **Step 1: Write the failing test**

```python
# sub_modules_examples/tutor/tests/unit/test_idle_watcher.py
from __future__ import annotations

import asyncio

import pytest
import redis.asyncio as redis

from app import config
from app.app_utils import idle_watcher


@pytest.mark.asyncio
async def test_run_one_expiry_cycle_closes_the_expired_session(redis_client, monkeypatch):
    client = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    await client.config_set("notify-keyspace-events", "Ex")
    pubsub = client.pubsub()
    await pubsub.psubscribe("__keyevent@0__:expired")

    closed = []

    async def fake_close(session_id, student_id=None):
        closed.append(session_id)

    monkeypatch.setattr(idle_watcher, "perform_close_session", fake_close)

    try:
        await client.set("session:test_idle_watch_1:heartbeat", "1", px=200)  # 0.2s TTL
        await asyncio.sleep(0.5)
        result = await idle_watcher.run_one_expiry_cycle(pubsub, timeout=2.0)
        assert result == "test_idle_watch_1"
        assert closed == ["test_idle_watch_1"]
    finally:
        await pubsub.aclose()
        await client.aclose()


@pytest.mark.asyncio
async def test_run_one_expiry_cycle_ignores_unrelated_keys(redis_client, monkeypatch):
    client = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    await client.config_set("notify-keyspace-events", "Ex")
    pubsub = client.pubsub()
    await pubsub.psubscribe("__keyevent@0__:expired")

    monkeypatch.setattr(idle_watcher, "perform_close_session", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not close")))

    try:
        await client.set("some_unrelated_key", "1", px=200)
        await asyncio.sleep(0.5)
        result = await idle_watcher.run_one_expiry_cycle(pubsub, timeout=1.0)
        assert result is None
    finally:
        await pubsub.aclose()
        await client.aclose()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd sub_modules_examples/tutor && uv run pytest tests/unit/test_idle_watcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.app_utils.idle_watcher'`

- [ ] **Step 3: Implement**

```python
# sub_modules_examples/tutor/app/app_utils/idle_watcher.py
"""Idle-timeout safety net for close_session — mirrors the same
safety-net-TTL philosophy already used for the Redis turn buffer
(app/memory/short_term.py's _SAFETY_TTL_SECONDS). A session that never gets
explicitly closed (Task 6's endpoint) still gets reflected into long-term
memory once its heartbeat key (app/memory/short_term.py:refresh_heartbeat)
expires. See docs/superpowers/specs/2026-08-27-smriti-observatory-design.md
§6.2.

Managed Memorystore may restrict runtime CONFIG SET — if so, configure
notify-keyspace-events via the instance's parameter group instead; this
module's own CONFIG SET call is a no-op-if-already-set convenience for
local dev, not a hard dependency of the watch loop itself.
"""
from __future__ import annotations

import logging
import time

import redis.asyncio as redis

from app import config
from app.app_utils.memory_routes import perform_close_session

logger = logging.getLogger(__name__)


async def run_one_expiry_cycle(pubsub: redis.client.PubSub, timeout: float | None = 5.0) -> str | None:
    """Waits up to `timeout` seconds (total) for one expiry notification.

    redis-py's get_message() reads exactly one raw frame per call. Right
    after psubscribe(), the first frame on the wire is always the PSUBSCRIBE
    confirmation itself; with ignore_subscribe_messages=True that frame is
    suppressed and the call returns None immediately — it does *not* keep
    reading within the same call to find a real message, even though
    `timeout` budget remains. A single get_message() call (a naive first
    draft of this function did exactly that) therefore spuriously returns
    None on the very first invocation after subscribing, regardless of
    whether a real expiry notification was waiting right behind it on the
    socket. This loops past those protocol-level confirmations, spending
    only the remaining timeout budget on each subsequent read, so the
    result reflects the first real message (or true timeout), not a
    subscribe ack.

    Returns the session id it closed, or None if the message wasn't a
    session heartbeat key (or nothing arrived in time)."""
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        remaining = timeout if deadline is None else max(0.0, deadline - time.monotonic())
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=remaining)
        if message is None:
            if deadline is not None and time.monotonic() >= deadline:
                return None
            continue
        if message.get("type") != "pmessage":
            continue
        key = message["data"]
        if not (key.startswith("session:") and key.endswith(":heartbeat")):
            return None
        session_id = key.split(":")[1]
        try:
            await perform_close_session(session_id)
        except Exception:
            logger.exception("idle-timeout close_session failed for session_id=%s", session_id)
            return None
        return session_id


async def watch_idle_sessions() -> None:
    client = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
    try:
        await client.config_set("notify-keyspace-events", "Ex")
    except Exception:
        logger.warning("could not set notify-keyspace-events at runtime; configure it on the Redis instance directly")
    pubsub = client.pubsub()
    await pubsub.psubscribe("__keyevent@0__:expired")
    try:
        while True:
            await run_one_expiry_cycle(pubsub, timeout=None)
    finally:
        await pubsub.aclose()
        await client.aclose()
```

(`get_message(..., timeout=None)` blocks until a message arrives — correct for the real infinite loop; the test always passes an explicit `timeout` so it never hangs.)

- [ ] **Step 4: Wire into `fast_api_app.py`'s lifespan**

```python
# app/fast_api_app.py — add to imports
from app.app_utils.idle_watcher import watch_idle_sessions
```

```python
# app/fast_api_app.py — inside `lifespan`, after `app.state.agent_app_name = adk_app.name`
    app.state.agent_app_name = adk_app.name
    idle_watcher_task = asyncio.create_task(watch_idle_sessions())  # NEW
    await attach_a2a_routes(
        app,
        agent=root_agent,
        runner=runner,
        task_store=InMemoryTaskStore(),
        rpc_path=f"/a2a/{adk_app.name}",
    )
    yield
    idle_watcher_task.cancel()  # NEW
```

Add `import asyncio` to `fast_api_app.py`'s imports if not already present (it currently imports `contextlib`, `os`, `collections.abc.AsyncIterator` — `asyncio` needs adding).

- [ ] **Step 5: Run to verify it passes**

Run: `cd sub_modules_examples/tutor && uv run pytest tests/unit/test_idle_watcher.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
cd sub_modules_examples/tutor
git add app/app_utils/idle_watcher.py app/fast_api_app.py tests/unit/test_idle_watcher.py
git commit -m "feat: auto-close idle sessions via Redis keyspace-expiry notifications"
```

---

## Part C — Observatory backend (`smriti-observatory/backend`)

### Task 8: Scaffold the backend package

**Files:**
- Create: `smriti-observatory/backend/pyproject.toml`
- Create: `smriti-observatory/backend/.env.example`
- Create: `smriti-observatory/backend/observatory/__init__.py`
- Create: `smriti-observatory/backend/observatory/events.py`
- Create: `smriti-observatory/backend/tests/__init__.py`
- Create: `smriti-observatory/backend/tests/conftest.py`
- Test: `smriti-observatory/backend/tests/test_events.py`

**Interfaces:**
- Produces: `observatory.events.MemoryEvent` (re-exported from the tutor package — never redefined), `observatory.events.EnrichedEvent` (adds a `diff` field, Task 9 fills it in).

- [ ] **Step 1: Write the failing test**

```python
# smriti-observatory/backend/tests/test_events.py
from __future__ import annotations

from observatory.events import EnrichedEvent, MemoryEvent


def test_memory_event_is_the_tutor_apps_own_class():
    from app.memory.instrumentation import MemoryEvent as TutorMemoryEvent
    assert MemoryEvent is TutorMemoryEvent


def test_enriched_event_wraps_a_memory_event_with_an_optional_diff():
    event = MemoryEvent(
        event_id="e1", ts="2026-08-27T00:00:00Z", session_id="s1", student_id="stu1",
        tier="long_term", operation="write", record_type="dpm_profile",
        source_fn="put_dpm", trace_id=None, span_id=None, payload={"student_id": "stu1"},
    )
    enriched = EnrichedEvent(event=event, diff=[])
    assert enriched.event.session_id == "s1"
    assert enriched.diff == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_events.py -v`
Expected: FAIL — package doesn't exist yet (`uv sync` hasn't run, no `pyproject.toml`).

- [ ] **Step 3: Create the package**

```toml
# smriti-observatory/backend/pyproject.toml
[project]
name = "smriti-observatory-backend"
version = "0.1.0"
description = "Real-time visualization backend for the SMRITI memory layer."
requires-python = ">=3.11,<3.14"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "redis>=5.0",
    "pydantic>=2.0",
    "tutor",
]

[tool.uv.sources]
# The path dependency name must match the `[project] name` declared in
# sub_modules_examples/tutor/pyproject.toml ("tutor"), not the importable
# top-level module it ships (`app`) — uv matches sources by distribution
# name. The import in observatory/events.py is still `from app...`.
tutor = { path = "../../sub_modules_examples/tutor", editable = true }

[dependency-groups]
dev = [
    "pytest>=9.0.2,<10.0.0",
    "pytest-asyncio>=1.0.0,<2.0.0",
    "httpx>=0.27",
]

[tool.pytest.ini_options]
pythonpath = "."
asyncio_default_fixture_loop_scope = "session"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["observatory"]
```

```bash
# smriti-observatory/backend/.env.example
GCP_PROJECT=nityam-506707
FIRESTORE_DATABASE=smriti
REDIS_HOST=localhost
REDIS_PORT=6379
TUTOR_BASE_URL=http://localhost:8000
```

```python
# smriti-observatory/backend/observatory/__init__.py
```

```python
# smriti-observatory/backend/observatory/events.py
"""Re-exports the tutor app's own MemoryEvent — the Observatory must never
decode a real memory-layer event with a schema that could drift from the
one that published it (see the pyproject.toml path dependency on `app`)."""
from __future__ import annotations

from app.memory.instrumentation import MemoryEvent
from pydantic import BaseModel


class FieldChange(BaseModel):
    path: str
    kind: str  # "added" | "removed" | "changed"
    old: object = None
    new: object = None
    label: str


class EnrichedEvent(BaseModel):
    event: MemoryEvent
    diff: list[FieldChange] = []


__all__ = ["MemoryEvent", "FieldChange", "EnrichedEvent"]
```

```python
# smriti-observatory/backend/tests/__init__.py
```

```python
# smriti-observatory/backend/tests/conftest.py
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd smriti-observatory/backend && uv sync && uv run pytest tests/test_events.py -v`
Expected: 2 passed. This is also the first proof the `uv.sources` path dependency on the tutor package resolves correctly — if `uv sync` fails to find `app`, fix the relative path before continuing to any later task.

- [ ] **Step 5: Commit**

```bash
git add smriti-observatory/backend/pyproject.toml smriti-observatory/backend/.env.example \
        smriti-observatory/backend/observatory/__init__.py smriti-observatory/backend/observatory/events.py \
        smriti-observatory/backend/tests/__init__.py smriti-observatory/backend/tests/conftest.py \
        smriti-observatory/backend/tests/test_events.py smriti-observatory/backend/uv.lock
git commit -m "feat: scaffold smriti-observatory backend package"
```

---

### Task 9: `diff.py` — schema-aware DPM/TeachingMemory diffing

**Files:**
- Create: `smriti-observatory/backend/observatory/diff.py`
- Test: `smriti-observatory/backend/tests/test_diff.py`

**Interfaces:**
- Consumes: `observatory.events.FieldChange` (Task 8).
- Produces: `diff_dpm(old: dict | None, new: dict) -> list[FieldChange]`, `diff_teaching_memory(old: dict | None, new: dict) -> list[FieldChange]`. Both take/return plain dicts (the `.model_dump(mode="json")` shape of `DPMProfile`/`TeachingMemory` — matches the `payload` field on write events). Pure, no I/O — this task needs no Firestore/Redis fixtures.

- [ ] **Step 1: Write the failing test**

```python
# smriti-observatory/backend/tests/test_diff.py
from __future__ import annotations

from observatory.diff import diff_dpm, diff_teaching_memory


def test_diff_dpm_reports_new_weakness():
    old = {"student_id": "s1", "weaknesses": {}, "self_reflection": []}
    new = {
        "student_id": "s1",
        "weaknesses": {"projectile.range": {"mastery": "partial", "strength": "weak", "evidence": ["x#1"]}},
        "self_reflection": [],
    }
    changes = diff_dpm(old, new)
    assert len(changes) == 1
    assert changes[0].kind == "added"
    assert "projectile.range" in changes[0].label


def test_diff_dpm_reports_mastery_transition():
    old = {"student_id": "s1", "weaknesses": {
        "projectile.range": {"mastery": "partial", "strength": "weak", "evidence": ["x#1"]},
    }, "self_reflection": []}
    new = {"student_id": "s1", "weaknesses": {
        "projectile.range": {"mastery": "known", "strength": "strong", "evidence": ["x#1", "x#2"]},
    }, "self_reflection": []}
    changes = diff_dpm(old, new)
    labels = {c.path: c.label for c in changes}
    assert labels["weaknesses.projectile.range.mastery"] == "projectile.range.mastery: partial -> known"
    assert labels["weaknesses.projectile.range.strength"] == "projectile.range.strength: weak -> strong"


def test_diff_dpm_no_changes_when_identical():
    profile = {"student_id": "s1", "weaknesses": {
        "x": {"mastery": "known", "strength": "strong", "evidence": ["e1"]},
    }, "self_reflection": []}
    assert diff_dpm(profile, profile) == []


def test_diff_dpm_treats_missing_old_as_empty():
    new = {"student_id": "s1", "weaknesses": {}, "self_reflection": [{"note": "responds well to worked examples", "evidence": ["x#1"]}]}
    changes = diff_dpm(None, new)
    assert len(changes) == 1
    assert changes[0].kind == "added"
    assert "responds well to worked examples" in changes[0].label


def test_diff_teaching_memory_reports_coverage_transition():
    old = {"student_id": "s1", "covered": {"projectile.range": {"status": "in_progress"}}, "open_doubts": []}
    new = {"student_id": "s1", "covered": {"projectile.range": {"status": "covered"}}, "open_doubts": []}
    changes = diff_teaching_memory(old, new)
    assert len(changes) == 1
    assert changes[0].label == "projectile.range coverage: in_progress -> covered"


def test_diff_teaching_memory_reports_doubt_lifecycle_transition():
    old = {"student_id": "s1", "covered": {}, "open_doubts": [
        {"concept_id": "projectile.range", "status": "active", "doubt": "d", "correct_understanding": "c", "evidence": ["x#1"]},
    ]}
    new = {"student_id": "s1", "covered": {}, "open_doubts": [
        {"concept_id": "projectile.range", "status": "resolved", "doubt": "d", "correct_understanding": "c", "evidence": ["x#1"]},
    ]}
    changes = diff_teaching_memory(old, new)
    assert len(changes) == 1
    assert changes[0].label == "doubt on projectile.range: active -> resolved"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_diff.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'observatory.diff'`

- [ ] **Step 3: Implement**

```python
# smriti-observatory/backend/observatory/diff.py
"""Schema-aware diffing for DPMProfile/TeachingMemory writes — walks the
four fields memory_layer.md §2.2-2.3 actually documents as evolving
(weaknesses.*.mastery/strength, self_reflection, covered.*.status,
open_doubts.*.status), not a generic recursive dict differ. Keeps the UI's
language schema-literate ("mastery: partial -> known") instead of
JSON-Pointer-literate.
"""
from __future__ import annotations

from observatory.events import FieldChange


def diff_dpm(old: dict | None, new: dict) -> list[FieldChange]:
    old = old or {}
    changes: list[FieldChange] = []
    old_weaknesses = old.get("weaknesses", {})
    for concept_id, weakness in new.get("weaknesses", {}).items():
        prev = old_weaknesses.get(concept_id)
        if prev is None:
            changes.append(FieldChange(
                path=f"weaknesses.{concept_id}", kind="added", new=weakness,
                label=f"new weakness tracked: {concept_id} ({weakness.get('mastery')})",
            ))
            continue
        for field in ("mastery", "strength"):
            if prev.get(field) != weakness.get(field):
                changes.append(FieldChange(
                    path=f"weaknesses.{concept_id}.{field}", kind="changed",
                    old=prev.get(field), new=weakness.get(field),
                    label=f"{concept_id}.{field}: {prev.get(field)} -> {weakness.get(field)}",
                ))

    old_notes = {n["note"] for n in old.get("self_reflection", [])}
    for note in new.get("self_reflection", []):
        if note["note"] not in old_notes:
            changes.append(FieldChange(
                path="self_reflection", kind="added", new=note["note"],
                label=f"new self-reflection: \"{note['note']}\"",
            ))
    return changes


def diff_teaching_memory(old: dict | None, new: dict) -> list[FieldChange]:
    old = old or {}
    changes: list[FieldChange] = []

    old_covered = old.get("covered", {})
    for concept_id, covered in new.get("covered", {}).items():
        prev = old_covered.get(concept_id)
        prev_status = prev.get("status") if prev else None
        if prev_status != covered.get("status"):
            changes.append(FieldChange(
                path=f"covered.{concept_id}.status", kind="changed" if prev else "added",
                old=prev_status, new=covered.get("status"),
                label=f"{concept_id} coverage: {prev_status or 'not started'} -> {covered.get('status')}",
            ))

    old_doubts = {d["concept_id"]: d for d in old.get("open_doubts", [])}
    for doubt in new.get("open_doubts", []):
        prev = old_doubts.get(doubt["concept_id"])
        prev_status = prev.get("status") if prev else None
        if prev_status != doubt.get("status"):
            changes.append(FieldChange(
                path=f"open_doubts.{doubt['concept_id']}.status", kind="changed" if prev else "added",
                old=prev_status, new=doubt.get("status"),
                label=f"doubt on {doubt['concept_id']}: {prev_status or 'new'} -> {doubt.get('status')}",
            ))
    return changes
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_diff.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add smriti-observatory/backend/observatory/diff.py smriti-observatory/backend/tests/test_diff.py
git commit -m "feat: add schema-aware DPM/TeachingMemory diffing"
```

---

### Task 10: `snapshot_cache.py`

**Files:**
- Create: `smriti-observatory/backend/observatory/snapshot_cache.py`
- Test: `smriti-observatory/backend/tests/test_snapshot_cache.py`

**Interfaces:**
- Produces: `SnapshotCache` class with `get_and_set(student_id: str, record_type: str, new_value: dict, loader: Callable[[], dict | None]) -> dict | None` — returns the previous value (from cache, or `loader()` on first miss), then stores `new_value` as the new current value; and `set(student_id: str, record_type: str, value: dict | None) -> None` — unconditionally overwrites the cached value, no loader involved.
- Consumed by: Task 11 (`ingest.py`) — `set()` exists specifically so a **read** event (e.g. `close_session`'s own `store.get_dpm` call, which always happens immediately before its `put_dpm` write) can prime the cache with the true pre-write state. Without this, the first write ever seen for a given student would diff against `loader()`'s result — but by the time an event is published, its own write has already committed to Firestore, so a write-triggered loader call would read the *post-write* value and produce a false empty diff. Priming from the read that precedes it avoids this entirely.

- [ ] **Step 1: Write the failing test**

```python
# smriti-observatory/backend/tests/test_snapshot_cache.py
from __future__ import annotations

from observatory.snapshot_cache import SnapshotCache


def test_first_call_uses_loader_as_previous_value():
    cache = SnapshotCache()
    loader_calls = []

    def loader():
        loader_calls.append(1)
        return {"student_id": "s1", "weaknesses": {}}

    prev = cache.get_and_set("s1", "dpm_profile", {"student_id": "s1", "weaknesses": {"x": 1}}, loader)
    assert prev == {"student_id": "s1", "weaknesses": {}}
    assert len(loader_calls) == 1


def test_second_call_uses_cached_value_not_loader():
    cache = SnapshotCache()
    cache.get_and_set("s1", "dpm_profile", {"v": 1}, lambda: {"v": 0})

    loader_calls = []
    prev = cache.get_and_set("s1", "dpm_profile", {"v": 2}, lambda: loader_calls.append(1))
    assert prev == {"v": 1}
    assert loader_calls == []


def test_loader_returning_none_yields_none_as_previous():
    cache = SnapshotCache()
    prev = cache.get_and_set("s1", "dpm_profile", {"v": 1}, lambda: None)
    assert prev is None


def test_different_record_types_are_independent():
    cache = SnapshotCache()
    cache.get_and_set("s1", "dpm_profile", {"v": "dpm"}, lambda: None)
    cache.get_and_set("s1", "teaching_memory", {"v": "tm"}, lambda: None)
    assert cache.get_and_set("s1", "dpm_profile", {"v": "dpm2"}, lambda: None) == {"v": "dpm"}
    assert cache.get_and_set("s1", "teaching_memory", {"v": "tm2"}, lambda: None) == {"v": "tm"}


def test_set_primes_the_cache_so_a_later_get_and_set_skips_the_loader():
    cache = SnapshotCache()
    cache.set("s1", "dpm_profile", {"v": "from_a_read_event"})

    loader_calls = []
    prev = cache.get_and_set("s1", "dpm_profile", {"v": "written"}, lambda: loader_calls.append(1))
    assert prev == {"v": "from_a_read_event"}
    assert loader_calls == []


def test_set_can_prime_with_none():
    cache = SnapshotCache()
    cache.set("s1", "dpm_profile", None)
    loader_calls = []
    prev = cache.get_and_set("s1", "dpm_profile", {"v": "written"}, lambda: loader_calls.append(1))
    assert prev is None
    assert loader_calls == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_snapshot_cache.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# smriti-observatory/backend/observatory/snapshot_cache.py
"""In-memory per-(student_id, record_type) last-seen state, so ingest.py can
diff a new long-term write against what came before it without an extra
Firestore round-trip on every event. Seeded lazily via `loader` on first
miss for a given key.
"""
from __future__ import annotations

from typing import Callable


class SnapshotCache:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict | None] = {}

    def get_and_set(
        self, student_id: str, record_type: str, new_value: dict,
        loader: Callable[[], dict | None],
    ) -> dict | None:
        key = (student_id, record_type)
        if key not in self._store:
            self._store[key] = loader()
        previous = self._store[key]
        self._store[key] = new_value
        return previous

    def set(self, student_id: str, record_type: str, value: dict | None) -> None:
        self._store[(student_id, record_type)] = value
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_snapshot_cache.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add smriti-observatory/backend/observatory/snapshot_cache.py smriti-observatory/backend/tests/test_snapshot_cache.py
git commit -m "feat: add per-student snapshot cache for diffing"
```

---

### Task 11: `broadcaster.py` + `ingest.py`

**Files:**
- Create: `smriti-observatory/backend/observatory/broadcaster.py`
- Create: `smriti-observatory/backend/observatory/ingest.py`
- Test: `smriti-observatory/backend/tests/test_ingest.py`

**Interfaces:**
- Produces: `Broadcaster` class with `subscribe(session_id: str | None) -> asyncio.Queue[EnrichedEvent]` (pass `None` for the global/`/ws/global` feed) and `publish(enriched: EnrichedEvent) -> None` (fans out to the matching session queue, plus always to every global-feed queue); `ingest_one_message(raw: str, cache: SnapshotCache, broadcaster: Broadcaster, get_dpm, get_teaching_memory) -> EnrichedEvent` (processes one already-received pubsub message body — the real subscribe loop, `run_ingest_loop`, just calls this per message forever, so the test never needs to run an infinite loop).

- [ ] **Step 1: Write the failing tests**

```python
# smriti-observatory/backend/tests/test_ingest.py
from __future__ import annotations

import asyncio

import pytest

from observatory.broadcaster import Broadcaster
from observatory.events import MemoryEvent
from observatory.ingest import ingest_one_message
from observatory.snapshot_cache import SnapshotCache


def _event_json(**overrides) -> str:
    base = dict(
        event_id="e1", ts="2026-08-27T00:00:00Z", session_id="s1", student_id="stu1",
        tier="long_term", operation="write", record_type="dpm_profile",
        source_fn="put_dpm", trace_id="abc", span_id="def",
        payload={"student_id": "stu1", "weaknesses": {"x": {"mastery": "known", "strength": "strong", "evidence": ["e1"]}}, "self_reflection": []},
    )
    base.update(overrides)
    return MemoryEvent(**base).model_dump_json()


@pytest.mark.asyncio
async def test_ingest_dpm_write_computes_diff_against_loader():
    """No preceding read event was ingested for this student, so this write
    falls back to the loader — which here simulates Firestore already
    holding an existing weakness for concept "x" at a different mastery,
    producing a genuine "changed" diff. (A loader returning an empty
    weaknesses dict would legitimately produce an "added" diff instead —
    see test_ingest_primes_cache_from_a_read_event... below for that
    distinction, and Task 9's diff.py tests for both shapes individually.)
    """
    cache = SnapshotCache()
    broadcaster = Broadcaster()
    q = broadcaster.subscribe("s1")

    def get_dpm(student_id):
        return {
            "student_id": "stu1",
            "weaknesses": {"x": {"mastery": "partial", "strength": "weak", "evidence": ["e0"]}},
            "self_reflection": [],
        }

    enriched = await ingest_one_message(_event_json(), cache, broadcaster, get_dpm=get_dpm, get_teaching_memory=lambda sid: None)

    assert enriched.event.session_id == "s1"
    assert len(enriched.diff) == 1
    assert enriched.diff[0].path == "weaknesses.x.mastery"
    assert enriched.diff[0].label == "x.mastery: partial -> known"

    delivered = q.get_nowait()
    assert delivered.event.event_id == "e1"


@pytest.mark.asyncio
async def test_ingest_primes_cache_from_a_read_event_so_the_following_write_diffs_against_it():
    """close_session always calls store.get_dpm (a read) immediately before
    store.put_dpm (the write) — by the time the write's event is published,
    its own Firestore write has already committed, so a write-triggered
    loader() call would read the *post-write* value and produce a false
    empty diff. Priming the cache from the preceding read avoids this."""
    cache = SnapshotCache()
    broadcaster = Broadcaster()
    loader_calls = []

    def get_dpm(student_id):
        loader_calls.append(student_id)
        return {"student_id": "stu1", "weaknesses": {}, "self_reflection": []}  # would be WRONG if used

    read_event = _event_json(
        event_id="e-read", operation="read", source_fn="get_dpm",
        payload={"student_id": "stu1", "weaknesses": {"x": {"mastery": "partial", "strength": "weak", "evidence": ["e1"]}}, "self_reflection": []},
    )
    write_event = _event_json(
        event_id="e-write", operation="write", source_fn="put_dpm",
        payload={"student_id": "stu1", "weaknesses": {"x": {"mastery": "known", "strength": "strong", "evidence": ["e1", "e2"]}}, "self_reflection": []},
    )

    await ingest_one_message(read_event, cache, broadcaster, get_dpm=get_dpm, get_teaching_memory=lambda sid: None)
    enriched = await ingest_one_message(write_event, cache, broadcaster, get_dpm=get_dpm, get_teaching_memory=lambda sid: None)

    assert loader_calls == []  # the read event primed the cache; the write never had to fall back to the loader
    labels = {c.path: c.label for c in enriched.diff}
    assert labels["weaknesses.x.mastery"] == "x.mastery: partial -> known"


@pytest.mark.asyncio
async def test_ingest_workflow_event_has_no_diff():
    cache = SnapshotCache()
    broadcaster = Broadcaster()
    broadcaster.subscribe("s1")

    enriched = await ingest_one_message(
        _event_json(tier="workflow", record_type="turn_buffer", payload={"buffer_length": 1}),
        cache, broadcaster, get_dpm=lambda sid: None, get_teaching_memory=lambda sid: None,
    )
    assert enriched.diff == []


@pytest.mark.asyncio
async def test_ingest_broadcasts_to_global_and_session_subscribers():
    cache = SnapshotCache()
    broadcaster = Broadcaster()
    session_q = broadcaster.subscribe("s1")
    global_q = broadcaster.subscribe(None)

    await ingest_one_message(_event_json(), cache, broadcaster, get_dpm=lambda sid: None, get_teaching_memory=lambda sid: None)

    assert session_q.get_nowait().event.event_id == "e1"
    assert global_q.get_nowait().event.event_id == "e1"


@pytest.mark.asyncio
async def test_ingest_does_not_deliver_to_a_different_sessions_queue():
    cache = SnapshotCache()
    broadcaster = Broadcaster()
    other_q = broadcaster.subscribe("some-other-session")

    await ingest_one_message(_event_json(), cache, broadcaster, get_dpm=lambda sid: None, get_teaching_memory=lambda sid: None)

    assert other_q.empty()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# smriti-observatory/backend/observatory/broadcaster.py
"""In-process WebSocket fan-out registry. One queue per connected client;
publish() delivers to that client's session-scoped queue (if any) and to
every global-feed queue (subscribed with session_id=None)."""
from __future__ import annotations

import asyncio

from observatory.events import EnrichedEvent


class Broadcaster:
    def __init__(self) -> None:
        self._session_queues: dict[str, list[asyncio.Queue]] = {}
        self._global_queues: list[asyncio.Queue] = []

    def subscribe(self, session_id: str | None) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        if session_id is None:
            self._global_queues.append(queue)
        else:
            self._session_queues.setdefault(session_id, []).append(queue)
        return queue

    def unsubscribe(self, session_id: str | None, queue: asyncio.Queue) -> None:
        if session_id is None:
            if queue in self._global_queues:
                self._global_queues.remove(queue)
        elif session_id in self._session_queues and queue in self._session_queues[session_id]:
            self._session_queues[session_id].remove(queue)

    def publish(self, enriched: EnrichedEvent) -> None:
        session_id = enriched.event.session_id
        if session_id and session_id in self._session_queues:
            for queue in self._session_queues[session_id]:
                queue.put_nowait(enriched)
        for queue in self._global_queues:
            queue.put_nowait(enriched)
```

```python
# smriti-observatory/backend/observatory/ingest.py
"""Ingests MemoryEvents published by the tutor app (see
sub_modules_examples/tutor/app/memory/instrumentation.py) from Redis, diffs
long-term writes against the snapshot cache, and broadcasts the enriched
result. run_ingest_loop is the real subscribe-forever entry point; the
per-message logic lives in ingest_one_message so it's testable without an
infinite loop.
"""
from __future__ import annotations

from typing import Callable

import redis.asyncio as redis

from observatory.broadcaster import Broadcaster
from observatory.diff import diff_dpm, diff_teaching_memory
from observatory.events import EnrichedEvent, MemoryEvent
from observatory.snapshot_cache import SnapshotCache

_CHANNEL = "smriti:events:live"


async def ingest_one_message(
    raw: str,
    cache: SnapshotCache,
    broadcaster: Broadcaster,
    get_dpm: Callable[[str], dict | None],
    get_teaching_memory: Callable[[str], dict | None],
) -> EnrichedEvent:
    event = MemoryEvent.model_validate_json(raw)
    diff = []
    if event.record_type in ("dpm_profile", "teaching_memory") and event.student_id:
        loader = (
            (lambda: get_dpm(event.student_id)) if event.record_type == "dpm_profile"
            else (lambda: get_teaching_memory(event.student_id))
        )
        if event.operation == "read":
            # Reads always reflect the true state at the moment they happened.
            # close_session calls get_dpm/get_teaching_memory immediately
            # before put_dpm/put_teaching_memory, so priming from the read
            # gives the write its correct pre-write "previous" value — a
            # write-triggered loader() call would instead read Firestore
            # *after* that same write already committed (see snapshot_cache.py
            # Task 10 docstring).
            cache.set(event.student_id, event.record_type, event.payload)
        else:
            previous = cache.get_and_set(event.student_id, event.record_type, event.payload, loader)
            diff = diff_dpm(previous, event.payload) if event.record_type == "dpm_profile" else diff_teaching_memory(previous, event.payload)
    enriched = EnrichedEvent(event=event, diff=diff)
    broadcaster.publish(enriched)
    return enriched


async def run_ingest_loop(
    redis_host: str, redis_port: int, cache: SnapshotCache, broadcaster: Broadcaster,
    get_dpm: Callable[[str], dict | None], get_teaching_memory: Callable[[str], dict | None],
) -> None:
    client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            await ingest_one_message(message["data"], cache, broadcaster, get_dpm, get_teaching_memory)
    finally:
        await pubsub.aclose()
        await client.aclose()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_ingest.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add smriti-observatory/backend/observatory/broadcaster.py smriti-observatory/backend/observatory/ingest.py smriti-observatory/backend/tests/test_ingest.py
git commit -m "feat: add Redis ingest loop with diffing and WebSocket fan-out"
```

---

### Task 12: REST routes

**Files:**
- Create: `smriti-observatory/backend/observatory/routes_rest.py`
- Test: `smriti-observatory/backend/tests/test_routes_rest.py`

**Interfaces:**
- Consumes: `app.memory.store` (`get_dpm`, `get_teaching_memory`, `get_session_log`), `app.memory.short_term.get_turn_buffer` (all from the tutor package, via the path dependency).
- Produces: FastAPI `router` with `GET /api/sessions`, `GET /api/sessions/{id}/state`, `GET /api/sessions/{id}/events`, `POST /api/sessions/{id}/close`, `GET /api/health`.

- [ ] **Step 1: Write the failing tests**

```python
# smriti-observatory/backend/tests/test_routes_rest.py
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
        assert match["status"] == "closed"  # no heartbeat key set in this test
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_routes_rest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'observatory.routes_rest'`

- [ ] **Step 3: Implement**

```python
# smriti-observatory/backend/observatory/routes_rest.py
"""REST snapshot endpoints. Never re-implements a Firestore/Redis read —
every read goes through app.memory.store / app.memory.short_term directly
(the tutor package, via the pyproject.toml path dependency)."""
from __future__ import annotations

import httpx
import redis as redis_sync
from fastapi import APIRouter, Request

from app import config
from app.memory import short_term, store
from observatory.events import MemoryEvent


def build_router(tutor_base_url: str) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/sessions/{session_id}/state")
    async def session_state(session_id: str, student_id: str, request: Request):
        db = request.app.state.firestore
        profile = store.get_dpm(db, student_id)
        memory = store.get_teaching_memory(db, student_id)
        session_log = store.get_session_log(db, session_id)
        turn_buffer = await short_term.get_turn_buffer(session_id)
        return {
            "session_id": session_id,
            "student_id": student_id,
            "workflow": {"turn_buffer": turn_buffer},
            "episodic": {"session_log": session_log.model_dump(mode="json") if session_log else None},
            "long_term": {
                "dpm_profile": profile.model_dump(mode="json") if profile else None,
                "teaching_memory": memory.model_dump(mode="json") if memory else None,
            },
        }

    @router.get("/sessions")
    def list_sessions():
        try:
            client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
            raw_events = client.lrange("smriti:events:recent", 0, -1)
        except Exception:
            return {"sessions": []}
        events = [MemoryEvent.model_validate_json(raw) for raw in raw_events]
        by_session: dict[str, dict] = {}
        for event in events:
            if not event.session_id:
                continue
            entry = by_session.setdefault(event.session_id, {
                "session_id": event.session_id,
                "student_id": event.student_id,
                "started_at": event.ts,
                "last_event_at": event.ts,
            })
            entry["last_event_at"] = event.ts
            if event.student_id:
                entry["student_id"] = event.student_id
        for session_id, entry in by_session.items():
            try:
                entry["status"] = "live" if client.exists(f"session:{session_id}:heartbeat") else "closed"
            except Exception:
                entry["status"] = "closed"
        return {"sessions": sorted(by_session.values(), key=lambda s: s["last_event_at"], reverse=True)}

    @router.get("/sessions/{session_id}/events")
    def session_events(session_id: str):
        try:
            client = redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, decode_responses=True)
            raw_events = client.lrange("smriti:events:recent", 0, -1)
        except Exception:
            return {"events": []}
        events = [MemoryEvent.model_validate_json(raw) for raw in raw_events]
        matching = [e.model_dump(mode="json") for e in events if e.session_id == session_id]
        return {"events": matching}

    @router.post("/sessions/{session_id}/close")
    async def close_session_proxy(session_id: str, body: dict):
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{tutor_base_url}/memory/sessions/{session_id}/close", json=body)
        return response.json()

    @router.get("/health")
    def health(request: Request):
        redis_ok = True
        try:
            redis_sync.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT).ping()
        except Exception:
            redis_ok = False
        firestore_ok = True
        try:
            request.app.state.firestore.collection("_healthcheck").document("x").get()
        except Exception:
            firestore_ok = False
        tutor_ok = True
        try:
            httpx.get(f"{tutor_base_url}/list-apps", timeout=2.0)
        except Exception:
            tutor_ok = False
        return {"redis": redis_ok, "firestore": firestore_ok, "tutor_reachable": tutor_ok}

    return router
```

- [ ] **Step 4: Add the `httpx` dependency**

Modify `smriti-observatory/backend/pyproject.toml`'s `dependencies` list, adding `"httpx>=0.27"` (it's already in `dev` for `TestClient`'s transport — move it to the main `dependencies` list instead, since `routes_rest.py` needs it at runtime, not just in tests). Run `uv sync` after editing.

- [ ] **Step 5: Run to verify it passes**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_routes_rest.py -v`
Expected: 8 passed (the `close_session_proxy` route isn't covered by an isolated test here since it needs a running tutor server — exercised end-to-end in Task 23 instead).

- [ ] **Step 6: Commit**

```bash
git add smriti-observatory/backend/observatory/routes_rest.py smriti-observatory/backend/pyproject.toml smriti-observatory/backend/uv.lock smriti-observatory/backend/tests/test_routes_rest.py
git commit -m "feat: add REST snapshot endpoints to the Observatory backend"
```

---

### Task 13: WebSocket routes + trace/ADK-web link builders

**Files:**
- Create: `smriti-observatory/backend/observatory/routes_ws.py`
- Create: `smriti-observatory/backend/observatory/trace_links.py`
- Test: `smriti-observatory/backend/tests/test_routes_ws.py`, `smriti-observatory/backend/tests/test_trace_links.py`

**Interfaces:**
- Produces: `build_ws_router(broadcaster: Broadcaster) -> APIRouter` with `/ws/sessions/{id}` and `/ws/global`; `cloud_trace_url(trace_id: str, gcp_project: str) -> str`, `adk_web_url(tutor_base_url: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# smriti-observatory/backend/tests/test_trace_links.py
from __future__ import annotations

from observatory.trace_links import adk_web_url, cloud_trace_url


def test_cloud_trace_url_includes_trace_id_and_project():
    url = cloud_trace_url("abc123", "nityam-506707")
    assert url == "https://console.cloud.google.com/traces/list?tid=abc123&project=nityam-506707"


def test_adk_web_url_points_at_dev_ui_root():
    assert adk_web_url("http://localhost:8000") == "http://localhost:8000/dev-ui/"
```

```python
# smriti-observatory/backend/tests/test_routes_ws.py
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.broadcaster import Broadcaster
from observatory.events import EnrichedEvent, MemoryEvent
from observatory.routes_ws import build_ws_router


@pytest.fixture
def app_and_broadcaster():
    broadcaster = Broadcaster()
    app = FastAPI()
    app.include_router(build_ws_router(broadcaster))
    return app, broadcaster


def test_session_websocket_receives_published_events(app_and_broadcaster):
    app, broadcaster = app_and_broadcaster
    client = TestClient(app)
    with client.websocket_connect("/ws/sessions/s1") as ws:
        event = MemoryEvent(
            event_id="e1", ts="2026-08-27T00:00:00Z", session_id="s1", student_id="stu",
            tier="workflow", operation="write", record_type="turn_buffer",
            source_fn="append_turn", trace_id=None, span_id=None, payload=None,
        )
        broadcaster.publish(EnrichedEvent(event=event, diff=[]))
        received = ws.receive_json()
        assert received["event"]["event_id"] == "e1"


def test_global_websocket_receives_all_sessions_events(app_and_broadcaster):
    app, broadcaster = app_and_broadcaster
    client = TestClient(app)
    with client.websocket_connect("/ws/global") as ws:
        event = MemoryEvent(
            event_id="e2", ts="2026-08-27T00:00:00Z", session_id="any-session", student_id="stu",
            tier="workflow", operation="write", record_type="turn_buffer",
            source_fn="append_turn", trace_id=None, span_id=None, payload=None,
        )
        broadcaster.publish(EnrichedEvent(event=event, diff=[]))
        received = ws.receive_json()
        assert received["event"]["event_id"] == "e2"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_trace_links.py tests/test_routes_ws.py -v`
Expected: FAIL — both modules don't exist yet.

- [ ] **Step 3: Implement**

```python
# smriti-observatory/backend/observatory/trace_links.py
"""URL builders for deep-linking out to the real Cloud Trace console and the
real ADK web dev UI — the Observatory shows genuine trace/session data, it
doesn't reimplement either surface."""
from __future__ import annotations


def cloud_trace_url(trace_id: str, gcp_project: str) -> str:
    return f"https://console.cloud.google.com/traces/list?tid={trace_id}&project={gcp_project}"


def adk_web_url(tutor_base_url: str) -> str:
    """ADK web mounts at /dev-ui/ (confirmed against the real installed
    google-adk==2.7.1 package). No confirmed session-scoping query param —
    per docs/superpowers/specs/2026-08-27-smriti-observatory-design.md §7,
    this links to the dev-ui root; the session id is shown alongside for
    manual paste into its own session search box."""
    return f"{tutor_base_url.rstrip('/')}/dev-ui/"
```

```python
# smriti-observatory/backend/observatory/routes_ws.py
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from observatory.broadcaster import Broadcaster


def build_ws_router(broadcaster: Broadcaster) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/sessions/{session_id}")
    async def session_ws(websocket: WebSocket, session_id: str):
        await websocket.accept()
        queue = broadcaster.subscribe(session_id)
        try:
            while True:
                enriched = await queue.get()
                await websocket.send_json(enriched.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        finally:
            broadcaster.unsubscribe(session_id, queue)

    @router.websocket("/ws/global")
    async def global_ws(websocket: WebSocket):
        await websocket.accept()
        queue = broadcaster.subscribe(None)
        try:
            while True:
                enriched = await queue.get()
                await websocket.send_json(enriched.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        finally:
            broadcaster.unsubscribe(None, queue)

    return router
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_trace_links.py tests/test_routes_ws.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add smriti-observatory/backend/observatory/routes_ws.py smriti-observatory/backend/observatory/trace_links.py \
        smriti-observatory/backend/tests/test_routes_ws.py smriti-observatory/backend/tests/test_trace_links.py
git commit -m "feat: add WebSocket routes and Cloud Trace / ADK web link builders"
```

---

### Task 14: `main.py` — wire the backend together

**Files:**
- Create: `smriti-observatory/backend/observatory/main.py`
- Create: `smriti-observatory/README.md`
- Test: `smriti-observatory/backend/tests/test_main.py`

**Interfaces:**
- Produces: `observatory.main.app` — the assembled FastAPI application. This is the module `uvicorn observatory.main:app` runs.

- [ ] **Step 1: Write the failing test**

```python
# smriti-observatory/backend/tests/test_main.py
"""app.main's lifespan calls store.connect() and starts a real Redis
subscribe loop — both `redis_client`/`firestore_db` fixtures are taken as
parameters purely to force this file's usual skip-if-unreachable gate
before TestClient's `with` block triggers that lifespan; neither fixture
is otherwise used directly here."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_app_serves_health_endpoint(redis_client, firestore_db):
    from observatory.main import app

    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert set(response.json().keys()) == {"redis", "firestore", "tutor_reachable"}


def test_app_allows_cors_from_localhost_vite_origin(redis_client, firestore_db):
    """Tests the actual response header CORSMiddleware produces, rather than
    introspecting Starlette's internal middleware-stack representation
    (attribute names there vary across Starlette versions)."""
    from observatory.main import app

    with TestClient(app) as client:
        response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# smriti-observatory/backend/observatory/main.py
"""SMRITI Observatory backend entry point. Run with:
    uv run uvicorn observatory.main:app --reload --port 8100
"""
from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.memory import store
from observatory.broadcaster import Broadcaster
from observatory.ingest import run_ingest_loop
from observatory.routes_rest import build_router
from observatory.routes_ws import build_ws_router
from observatory.snapshot_cache import SnapshotCache

load_dotenv()

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
TUTOR_BASE_URL = os.environ.get("TUTOR_BASE_URL", "http://localhost:8000")

broadcaster = Broadcaster()
snapshot_cache = SnapshotCache()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.firestore = store.connect()

    def get_dpm(student_id: str):
        profile = store.get_dpm(app.state.firestore, student_id)
        return profile.model_dump(mode="json") if profile else None

    def get_teaching_memory(student_id: str):
        memory = store.get_teaching_memory(app.state.firestore, student_id)
        return memory.model_dump(mode="json") if memory else None

    ingest_task = asyncio.create_task(
        run_ingest_loop(REDIS_HOST, REDIS_PORT, snapshot_cache, broadcaster, get_dpm, get_teaching_memory)
    )
    yield
    ingest_task.cancel()
    app.state.firestore.close()


app = FastAPI(title="SMRITI Observatory", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(build_router(tutor_base_url=TUTOR_BASE_URL))
app.include_router(build_ws_router(broadcaster))
```

```markdown
# smriti-observatory/README.md (new file — the product's top-level README, not yet the full one Task 23 finishes)

# SMRITI Observatory

A real-time companion to Google ADK web: watches every SMRITI memory-layer
read/write (workflow / episodic / long-term tiers) as a tutor agent session
runs, correlated to the live OpenTelemetry trace span that caused it.

See `docs/superpowers/specs/2026-08-27-smriti-observatory-design.md` for the
full design, and `docs/superpowers/plans/2026-08-27-smriti-observatory.md`
for how it was built.

## Running locally

```bash
# 1. The tutor app (separate terminal, from sub_modules_examples/tutor/)
uv run uvicorn app.fast_api_app:app --port 8000

# 2. This backend
cd backend && uv run uvicorn observatory.main:app --reload --port 8100

# 3. This frontend
cd frontend && npm run dev
```

Requires local Redis (`brew services start redis`) and `gcloud auth
application-default login` against the `nityam-506707` project — see
`backend/.env.example`.
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_main.py -v`
Expected: 2 passed (skips gracefully if Firestore/Redis are unreachable, matching this repo's convention — `store.connect()` inside `lifespan` will raise if totally misconfigured, which is the correct fail-fast behavior for a real server process, distinct from tests skipping).

- [ ] **Step 5: Commit**

```bash
git add smriti-observatory/backend/observatory/main.py smriti-observatory/backend/tests/test_main.py smriti-observatory/README.md
git commit -m "feat: assemble the Observatory backend FastAPI app"
```

---

## Part D — Observatory frontend (`smriti-observatory/frontend`)

### Task 15: Scaffold the frontend package

**Files:**
- Create: `smriti-observatory/frontend/package.json`, `vite.config.ts`, `tsconfig.json`, `tsconfig.node.json`, `index.html`
- Create: `smriti-observatory/frontend/src/main.tsx`, `src/App.tsx`

**Interfaces:**
- Produces: a working `npm run dev`/`npm run build` — nothing functional yet, this is scaffolding.

- [ ] **Step 1: Write the failing check**

There's no unit test for scaffolding — the "test" is that the build succeeds. Run first to confirm it currently fails:

Run: `cd smriti-observatory/frontend && npm run build 2>&1 | head -5`
Expected: FAIL — `package.json` doesn't exist, `npm error code ENOENT`.

- [ ] **Step 2: Create the package** (matches `frontend/package.json`'s versions exactly)

```json
{
  "name": "smriti-observatory-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "oxlint",
    "preview": "vite preview",
    "test": "node tests/ui.mjs"
  },
  "dependencies": {
    "react": "^19.2.8",
    "react-dom": "^19.2.8"
  },
  "devDependencies": {
    "@types/node": "^24.13.3",
    "@types/react": "^19.2.18",
    "@types/react-dom": "^19.2.4",
    "@vitejs/plugin-react": "^6.1.0",
    "oxlint": "^1.79.0",
    "typescript": "~6.0.2",
    "vite": "^8.2.2"
  }
}
```

```typescript
// smriti-observatory/frontend/vite.config.ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
```

```json
// smriti-observatory/frontend/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

```json
// smriti-observatory/frontend/tsconfig.node.json
{
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

```html
<!-- smriti-observatory/frontend/index.html -->
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>SMRITI Observatory</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

```tsx
// smriti-observatory/frontend/src/main.tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

```tsx
// smriti-observatory/frontend/src/App.tsx
export default function App() {
  return <div>SMRITI Observatory</div>;
}
```

- [ ] **Step 3: Run to verify it passes**

Run: `cd smriti-observatory/frontend && npm install && npm run build`
Expected: builds cleanly, `dist/` produced.

- [ ] **Step 4: Commit**

```bash
git add smriti-observatory/frontend/package.json smriti-observatory/frontend/package-lock.json \
        smriti-observatory/frontend/vite.config.ts smriti-observatory/frontend/tsconfig*.json \
        smriti-observatory/frontend/index.html smriti-observatory/frontend/src/main.tsx smriti-observatory/frontend/src/App.tsx
git commit -m "feat: scaffold smriti-observatory frontend package"
```

---

### Task 16: Design tokens — ADK web's exact palette

**Files:**
- Create: `smriti-observatory/frontend/src/styles/tokens.css`
- Create: `smriti-observatory/frontend/src/styles/base.css`
- Modify: `smriti-observatory/frontend/src/main.tsx` (import the stylesheets)

**Interfaces:**
- Produces: CSS custom properties every later component reads (`--surface`, `--primary`, etc.) — this is the contract Tasks 18-21's `.module.css` files depend on.

- [ ] **Step 1: Write the check**

No unit test for CSS — visually verified in Task 22's headless-browser test, which asserts computed styles. For now, verify the file parses:

Run: `cd smriti-observatory/frontend && npx vite build 2>&1 | tail -5` (before creating the files)
Expected: builds fine today (nothing references the new files yet) — this step exists to confirm a clean baseline before the change.

- [ ] **Step 2: Implement**

```css
/* smriti-observatory/frontend/src/styles/tokens.css
   Values read directly from the installed google-adk==2.7.1 package's
   built Angular assets (google/adk/cli/browser/styles-*.css) — see
   docs/superpowers/specs/2026-08-27-smriti-observatory-design.md §8.1.
   Dark is the default, matching ADK web's own default. */

:root {
  --surface: #121212;
  --surface-container-low: #1a1a1a;
  --surface-container: #1e1e1e;
  --surface-container-high: #2a2a2a;
  --surface-container-highest: #3a3a3a;

  --primary: #7cc4ff;
  --on-primary: #003366;
  --primary-container: #004b8d;
  --on-primary-container: #d1e4ff;

  --secondary: #b5c9e2;
  --on-secondary: #203246;
  --secondary-container: #3a485a;

  --tertiary: #d5baff;
  --tertiary-container: #5f00c0;

  --error: #ffb4ab;
  --error-container: #93000a;

  --outline: #958e99;
  --outline-variant: #49454e;
  --on-surface: #e6e1e6;

  --graph-canvas: #0e172a;

  --radius-xs: 4px;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 28px;
  --radius-pill: 9999px;

  --font-ui: "Google Sans", Roboto, "Helvetica Neue", sans-serif;
  --font-mono: "Google Sans Mono", ui-monospace, monospace;

  /* SMRITI tier accents — not part of ADK web, this project's own additions */
  --tier-workflow: #7cc4ff;
  --tier-episodic: #e8a33d;
  --tier-long-term: #6bcf8a;
}

[data-theme="light"] {
  --surface: #ffffff;
  --surface-container-low: #fafafa;
  --surface-container: #f5f5f5;
  --surface-container-high: #eeeeee;
  --surface-container-highest: #e0e0e0;

  --primary: #005fb7;
  --on-primary: #ffffff;
  --primary-container: #d1e4ff;
  --on-primary-container: #001c37;

  --secondary: #535f70;
  --error: #ba1a1a;
  --outline: #7b757f;
}
```

```css
/* smriti-observatory/frontend/src/styles/base.css */
@import url("https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&display=swap");

* {
  box-sizing: border-box;
}

html,
body,
#root {
  height: 100%;
  margin: 0;
}

body {
  background: var(--surface);
  color: var(--on-surface);
  font-family: var(--font-ui);
}

code,
pre {
  font-family: var(--font-mono);
}
```

Modify `src/main.tsx` — add two import lines above the existing `import App from "./App"`:

```tsx
import "./styles/tokens.css";
import "./styles/base.css";
import App from "./App";
```

- [ ] **Step 3: Run to verify it passes**

Run: `cd smriti-observatory/frontend && npm run build`
Expected: builds cleanly.

- [ ] **Step 4: Commit**

```bash
git add smriti-observatory/frontend/src/styles/tokens.css smriti-observatory/frontend/src/styles/base.css smriti-observatory/frontend/src/main.tsx
git commit -m "feat: add ADK-web-matched design tokens"
```

---

### Task 17: `lib/types.ts` + `lib/ws.ts`

**Files:**
- Create: `smriti-observatory/frontend/src/lib/types.ts`
- Create: `smriti-observatory/frontend/src/lib/ws.ts`
- Create: `smriti-observatory/frontend/tests/ws.test.mjs` (a small Node-only script, run directly with `node`, not part of the CDP UI harness)

**Interfaces:**
- Produces: `MemoryEvent`, `FieldChange`, `EnrichedEvent` TypeScript types (mirroring `observatory/events.py`); `connectSessionSocket(baseUrl: string, sessionId: string, onEvent: (e: EnrichedEvent) => void) -> () => void` (returns an unsubscribe/close function), with automatic reconnect on close (1s backoff).

- [ ] **Step 1: Write the failing test**

```javascript
// smriti-observatory/frontend/tests/ws.test.mjs
// Pure Node test (no browser) for the reconnect state machine — run with:
//   node tests/ws.test.mjs
import assert from "node:assert";
import { WebSocketServer } from "ws";
import { connectSessionSocket } from "../src/lib/ws.ts";

// Minimal fake: this test exercises the reconnect *logic* by driving a
// real local WebSocket server, not by importing the .ts file directly
// (Node can't run TS without a loader) — so this file documents the
// contract and is executed via `npx tsx tests/ws.test.mjs` from package.json's
// pretest step. See Step 3 for the tsx devDependency this requires.

const wss = new WebSocketServer({ port: 0 });
const port = wss.address().port;
const received = [];

wss.on("connection", (socket) => {
  socket.send(JSON.stringify({ event: { event_id: "e1" }, diff: [] }));
});

const close = connectSessionSocket(`ws://localhost:${port}`, "s1", (e) => received.push(e));

await new Promise((r) => setTimeout(r, 200));
assert.strictEqual(received.length, 1);
assert.strictEqual(received[0].event.event_id, "e1");

close();
wss.close();
console.log("ws.test.mjs: PASS");
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd smriti-observatory/frontend && npm install --save-dev ws tsx && npx tsx tests/ws.test.mjs`
Expected: FAIL — `Cannot find module '../src/lib/ws.ts'`.

- [ ] **Step 3: Implement**

```typescript
// smriti-observatory/frontend/src/lib/types.ts
export type Tier = "workflow" | "episodic" | "long_term";
export type Operation = "read" | "write";
export type RecordType =
  | "grounding_chunk"
  | "dpm_profile"
  | "teaching_memory"
  | "session_log"
  | "turn_buffer"
  | "artifact_event";

export interface MemoryEvent {
  event_id: string;
  ts: string;
  session_id: string | null;
  student_id: string | null;
  tier: Tier;
  operation: Operation;
  record_type: RecordType;
  source_fn: string;
  trace_id: string | null;
  span_id: string | null;
  payload: unknown;
}

export interface FieldChange {
  path: string;
  kind: "added" | "removed" | "changed";
  old: unknown;
  new: unknown;
  label: string;
}

export interface EnrichedEvent {
  event: MemoryEvent;
  diff: FieldChange[];
}

export interface SessionState {
  session_id: string;
  student_id: string;
  workflow: { turn_buffer: Record<string, unknown>[] };
  episodic: { session_log: Record<string, unknown> | null };
  long_term: {
    dpm_profile: Record<string, unknown> | null;
    teaching_memory: Record<string, unknown> | null;
  };
}
```

```typescript
// smriti-observatory/frontend/src/lib/ws.ts
import type { EnrichedEvent } from "./types";

const RECONNECT_DELAY_MS = 1000;

export function connectSessionSocket(
  baseUrl: string,
  sessionId: string,
  onEvent: (event: EnrichedEvent) => void,
): () => void {
  let socket: WebSocket | null = null;
  let closedByCaller = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const connect = () => {
    socket = new WebSocket(`${baseUrl}/ws/sessions/${sessionId}`);
    socket.onmessage = (message) => {
      onEvent(JSON.parse(message.data as string) as EnrichedEvent);
    };
    socket.onclose = () => {
      if (!closedByCaller) {
        reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      }
    };
  };
  connect();

  return () => {
    closedByCaller = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    socket?.close();
  };
}
```

Add `"pretest": "true"` is unnecessary; instead add a `package.json` script for this specific check:

```json
{
  "scripts": {
    "test:ws": "tsx tests/ws.test.mjs"
  }
}
```

(Merge this into the existing `scripts` block from Task 15 rather than replacing it.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd smriti-observatory/frontend && npm run test:ws`
Expected: `ws.test.mjs: PASS`

- [ ] **Step 5: Commit**

```bash
git add smriti-observatory/frontend/src/lib/types.ts smriti-observatory/frontend/src/lib/ws.ts \
        smriti-observatory/frontend/tests/ws.test.mjs smriti-observatory/frontend/package.json smriti-observatory/frontend/package-lock.json
git commit -m "feat: add MemoryEvent types and reconnecting WebSocket client"
```

---

### Task 18: `SidePanel.tsx` + `SessionDrawer.tsx`

**Files:**
- Create: `smriti-observatory/frontend/src/components/SidePanel.tsx`, `SidePanel.module.css`
- Create: `smriti-observatory/frontend/src/components/SessionDrawer.tsx`, `SessionDrawer.module.css`

**Interfaces:**
- Produces: `<SidePanel tabs={{id, label, content}[]} defaultWidth={480} minWidth={360} maxWidthVw={50} />`; `<SessionDrawer sessions={SessionSummary[]} selectedId={string | null} onSelect={(id) => void} />` where `SessionSummary = {session_id, student_id, status, started_at, last_event_at}`.
- Consumed by: Task 21 (`SessionView.tsx`).

This task has no backend/data-flow behavior to unit test (it's pure presentational layout) — its correctness is verified visually in Task 22's headless-browser test. Per this plan's TDD default, write a minimal DOM-shape check now with `tsx` + `happy-dom`-free plain assertions is impractical without a test renderer this repo doesn't have (no Vitest/RTL — see Global Constraints), so this task's "test" step is the Task 22 CDP script asserting the resize handle and 5 tabs exist; implement here, verify there.

- [ ] **Step 1: Implement `SidePanel`**

```tsx
// smriti-observatory/frontend/src/components/SidePanel.tsx
import { useRef, useState } from "react";
import styles from "./SidePanel.module.css";

export interface SidePanelTab {
  id: string;
  label: string;
  content: React.ReactNode;
}

interface SidePanelProps {
  tabs: SidePanelTab[];
  defaultWidth?: number;
  minWidth?: number;
  maxWidthVw?: number;
}

export function SidePanel({ tabs, defaultWidth = 480, minWidth = 360, maxWidthVw = 50 }: SidePanelProps) {
  const [width, setWidth] = useState(defaultWidth);
  const [activeTab, setActiveTab] = useState(tabs[0]?.id);
  const dragging = useRef(false);

  const onPointerDown = () => {
    dragging.current = true;
    const onMove = (event: PointerEvent) => {
      if (!dragging.current) return;
      const maxWidth = (window.innerWidth * maxWidthVw) / 100;
      setWidth(Math.min(maxWidth, Math.max(minWidth, window.innerWidth - event.clientX)));
    };
    const onUp = () => {
      dragging.current = false;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  return (
    <aside className={styles.panel} style={{ width }}>
      <div className={styles.resizeHandler} onPointerDown={onPointerDown} data-testid="resize-handler" />
      <div className={styles.tabBar} role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            className={activeTab === tab.id ? styles.tabActive : styles.tab}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className={styles.tabContent}>{tabs.find((t) => t.id === activeTab)?.content}</div>
    </aside>
  );
}
```

```css
/* smriti-observatory/frontend/src/components/SidePanel.module.css */
.panel {
  position: relative;
  display: flex;
  flex-direction: column;
  background: var(--surface-container);
  border-left: 1px solid var(--outline-variant);
  height: 100%;
  flex-shrink: 0;
}

.resizeHandler {
  position: absolute;
  left: -4px;
  top: 0;
  bottom: 0;
  width: 8px;
  cursor: col-resize;
}

.tabBar {
  display: flex;
  border-bottom: 1px solid var(--outline-variant);
}

.tab,
.tabActive {
  height: 48px;
  padding: 0 16px;
  background: none;
  border: none;
  color: var(--on-surface);
  font-family: var(--font-ui);
  cursor: pointer;
}

.tabActive {
  border-bottom: 2px solid var(--primary);
  color: var(--primary);
}

.tabContent {
  flex: 1;
  overflow: auto;
  padding: 12px;
}
```

- [ ] **Step 2: Implement `SessionDrawer`**

```tsx
// smriti-observatory/frontend/src/components/SessionDrawer.tsx
import styles from "./SessionDrawer.module.css";

export interface SessionSummary {
  session_id: string;
  student_id: string;
  status: "live" | "closed";
  started_at: string;
  last_event_at: string;
}

interface SessionDrawerProps {
  sessions: SessionSummary[];
  selectedId: string | null;
  onSelect: (sessionId: string) => void;
}

export function SessionDrawer({ sessions, selectedId, onSelect }: SessionDrawerProps) {
  return (
    <nav className={styles.drawer} aria-label="Sessions">
      <div className={styles.header}>Sessions</div>
      <ul className={styles.list}>
        {sessions.map((session) => (
          <li key={session.session_id}>
            <button
              className={session.session_id === selectedId ? styles.itemActive : styles.item}
              onClick={() => onSelect(session.session_id)}
            >
              <span className={session.status === "live" ? styles.dotLive : styles.dotClosed} />
              <span className={styles.label}>{session.session_id}</span>
              <span className={styles.sublabel}>{session.student_id}</span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
```

```css
/* smriti-observatory/frontend/src/components/SessionDrawer.module.css */
.drawer {
  width: 260px;
  flex-shrink: 0;
  background: var(--surface-container-low);
  border-right: 1px solid var(--outline-variant);
  height: 100%;
  overflow-y: auto;
}

.header {
  padding: 16px;
  font-family: var(--font-ui);
  font-weight: 500;
  color: var(--on-surface);
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.item,
.itemActive {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 16px;
  background: none;
  border: none;
  color: var(--on-surface);
  text-align: left;
  cursor: pointer;
  border-radius: var(--radius-sm);
}

.itemActive {
  background: var(--primary-container);
  color: var(--on-primary-container);
}

.dotLive,
.dotClosed {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-pill);
  flex-shrink: 0;
}

.dotLive {
  background: var(--tier-workflow);
}

.dotClosed {
  background: var(--outline);
}

.label {
  font-family: var(--font-mono);
  font-size: 0.8rem;
}

.sublabel {
  margin-left: auto;
  font-size: 0.75rem;
  color: var(--outline);
}
```

- [ ] **Step 3: Verify the build**

Run: `cd smriti-observatory/frontend && npm run build`
Expected: builds cleanly (`App.tsx` doesn't import these yet, so no runtime check possible until Task 21 — this step only guards against a TypeScript error).

- [ ] **Step 4: Commit**

```bash
git add smriti-observatory/frontend/src/components/SidePanel.tsx smriti-observatory/frontend/src/components/SidePanel.module.css \
        smriti-observatory/frontend/src/components/SessionDrawer.tsx smriti-observatory/frontend/src/components/SessionDrawer.module.css
git commit -m "feat: add resizable SidePanel and SessionDrawer components"
```

---

### Task 19: `TierPanel.tsx` + `DiffView.tsx`

**Files:**
- Create: `smriti-observatory/frontend/src/components/TierPanel.tsx`, `TierPanel.module.css`
- Create: `smriti-observatory/frontend/src/components/DiffView.tsx`, `DiffView.module.css`

**Interfaces:**
- Produces: `<TierPanel tier="workflow"|"episodic"|"long_term" title={string} events={EnrichedEvent[]} content={React.ReactNode} />`; `<DiffView changes={FieldChange[]} />`.
- Consumed by: Task 21.

- [ ] **Step 1: Implement `DiffView`** (simplest, no dependency on `TierPanel`)

```tsx
// smriti-observatory/frontend/src/components/DiffView.tsx
import type { FieldChange } from "../lib/types";
import styles from "./DiffView.module.css";

export function DiffView({ changes }: { changes: FieldChange[] }) {
  if (changes.length === 0) {
    return <p className={styles.empty}>No changes yet.</p>;
  }
  return (
    <ul className={styles.list} data-testid="diff-view">
      {changes.map((change, i) => (
        <li key={i} className={styles[change.kind]} data-testid="diff-row">
          {change.label}
        </li>
      ))}
    </ul>
  );
}
```

```css
/* smriti-observatory/frontend/src/components/DiffView.module.css */
.list {
  list-style: none;
  margin: 0;
  padding: 0;
  font-family: var(--font-mono);
  font-size: 0.8rem;
}

.added,
.changed,
.removed {
  padding: 4px 8px;
  border-radius: var(--radius-xs);
  margin-bottom: 4px;
}

.added {
  background: color-mix(in srgb, var(--tier-long-term) 20%, transparent);
}

.changed {
  background: color-mix(in srgb, var(--primary) 20%, transparent);
}

.removed {
  background: color-mix(in srgb, var(--error) 20%, transparent);
}

.empty {
  color: var(--outline);
  font-size: 0.85rem;
}
```

- [ ] **Step 2: Implement `TierPanel`**

```tsx
// smriti-observatory/frontend/src/components/TierPanel.tsx
import type { EnrichedEvent, Tier } from "../lib/types";
import styles from "./TierPanel.module.css";

const TIER_CLASS: Record<Tier, string> = {
  workflow: styles.workflow,
  episodic: styles.episodic,
  long_term: styles.longTerm,
};

interface TierPanelProps {
  tier: Tier;
  title: string;
  events: EnrichedEvent[];
  content: React.ReactNode;
}

export function TierPanel({ tier, title, events, content }: TierPanelProps) {
  const isPulsing = events.length > 0 && Date.now() - new Date(events[events.length - 1].event.ts).getTime() < 1500;
  return (
    <section className={`${styles.panel} ${TIER_CLASS[tier]}`} data-testid={`tier-panel-${tier}`}>
      <header className={styles.header}>
        <span className={isPulsing ? styles.dotPulsing : styles.dot} />
        <h3 className={styles.title}>{title}</h3>
        <span className={styles.count}>{events.length}</span>
      </header>
      <div className={styles.body}>{content}</div>
    </section>
  );
}
```

```css
/* smriti-observatory/frontend/src/components/TierPanel.module.css */
.panel {
  border: 1px solid var(--outline-variant);
  border-radius: var(--radius-md);
  background: var(--surface-container-low);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--outline-variant);
}

.title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 500;
  font-family: var(--font-ui);
}

.count {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--outline);
}

.dot,
.dotPulsing {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-pill);
}

.dotPulsing {
  animation: pulse 1s ease-out;
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 currentColor;
  }
  100% {
    box-shadow: 0 0 0 8px transparent;
  }
}

.body {
  padding: 12px;
  overflow-y: auto;
  flex: 1;
}

.workflow .dot,
.workflow .dotPulsing {
  background: var(--tier-workflow);
  color: var(--tier-workflow);
}

.episodic .dot,
.episodic .dotPulsing {
  background: var(--tier-episodic);
  color: var(--tier-episodic);
}

.longTerm .dot,
.longTerm .dotPulsing {
  background: var(--tier-long-term);
  color: var(--tier-long-term);
}
```

- [ ] **Step 3: Verify the build**

Run: `cd smriti-observatory/frontend && npm run build`
Expected: builds cleanly.

- [ ] **Step 4: Commit**

```bash
git add smriti-observatory/frontend/src/components/TierPanel.tsx smriti-observatory/frontend/src/components/TierPanel.module.css \
        smriti-observatory/frontend/src/components/DiffView.tsx smriti-observatory/frontend/src/components/DiffView.module.css
git commit -m "feat: add TierPanel and DiffView components"
```

---

### Task 20: `EventTimeline.tsx`

**Files:**
- Create: `smriti-observatory/frontend/src/components/EventTimeline.tsx`, `EventTimeline.module.css`
- Create: `smriti-observatory/frontend/src/lib/traceLinks.ts`

**Interfaces:**
- Produces: `cloudTraceUrl(traceId: string, gcpProject: string): string`, `adkWebUrl(tutorBaseUrl: string): string` (TS mirrors of `observatory/trace_links.py`); `<EventTimeline events={EnrichedEvent[]} gcpProject={string} />` with a Timeline ⟷ Trace toggle. (`adkWebUrl` is consumed directly by `SessionView.tsx` in Task 21, not by `EventTimeline` — `EventTimeline` only needs `gcpProject`, for `cloudTraceUrl`.)
- Consumed by: Task 21.

- [ ] **Step 1: Implement `traceLinks.ts`**

```typescript
// smriti-observatory/frontend/src/lib/traceLinks.ts
export function cloudTraceUrl(traceId: string, gcpProject: string): string {
  return `https://console.cloud.google.com/traces/list?tid=${traceId}&project=${gcpProject}`;
}

export function adkWebUrl(tutorBaseUrl: string): string {
  return `${tutorBaseUrl.replace(/\/$/, "")}/dev-ui/`;
}
```

- [ ] **Step 2: Implement `EventTimeline`**

```tsx
// smriti-observatory/frontend/src/components/EventTimeline.tsx
import { useState } from "react";
import type { EnrichedEvent } from "../lib/types";
import { cloudTraceUrl } from "../lib/traceLinks";
import styles from "./EventTimeline.module.css";

type ViewMode = "timeline" | "trace";

interface EventTimelineProps {
  events: EnrichedEvent[];
  gcpProject: string;
}

export function EventTimeline({ events, gcpProject }: EventTimelineProps) {
  const [mode, setMode] = useState<ViewMode>("timeline");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className={styles.container}>
      <div className={styles.toggleGroup} role="group" aria-label="View mode">
        <button
          className={mode === "timeline" ? styles.toggleActive : styles.toggle}
          onClick={() => setMode("timeline")}
        >
          Timeline
        </button>
        <button className={mode === "trace" ? styles.toggleActive : styles.toggle} onClick={() => setMode("trace")}>
          Trace
        </button>
      </div>
      <ul className={styles.list} data-testid="event-list">
        {events.map((enriched) => {
          const { event } = enriched;
          const isExpanded = expandedId === event.event_id;
          return (
            <li key={event.event_id} className={styles.row}>
              <button className={styles.rowHeader} onClick={() => setExpandedId(isExpanded ? null : event.event_id)}>
                <span className={styles.recordType}>{event.record_type}</span>
                <span className={styles.op}>{event.operation}</span>
                <span className={styles.fn}>{event.source_fn}</span>
                <span className={styles.ts}>{new Date(event.ts).toLocaleTimeString()}</span>
              </button>
              {isExpanded && (
                <div className={styles.detail}>
                  {mode === "trace" && event.trace_id ? (
                    <a href={cloudTraceUrl(event.trace_id, gcpProject)} target="_blank" rel="noreferrer">
                      Open in Cloud Trace
                    </a>
                  ) : (
                    <pre className={styles.payload}>{JSON.stringify(event.payload, null, 2)}</pre>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
```

```css
/* smriti-observatory/frontend/src/components/EventTimeline.module.css */
.container {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.toggleGroup {
  display: flex;
  gap: 4px;
  padding: 8px;
}

.toggle,
.toggleActive {
  padding: 4px 12px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--outline-variant);
  background: none;
  color: var(--on-surface);
  cursor: pointer;
}

.toggleActive {
  background: var(--primary-container);
  color: var(--on-primary-container);
  border-color: var(--primary);
}

.list {
  list-style: none;
  margin: 0;
  padding: 0 8px;
  overflow-y: auto;
  flex: 1;
}

.row {
  border-bottom: 1px solid var(--outline-variant);
}

.rowHeader {
  display: flex;
  gap: 12px;
  width: 100%;
  padding: 8px 4px;
  background: none;
  border: none;
  color: var(--on-surface);
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  text-align: left;
}

.recordType {
  color: var(--primary);
}

.ts {
  margin-left: auto;
  color: var(--outline);
}

.detail {
  padding: 8px 12px 12px;
}

.payload {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  white-space: pre-wrap;
  background: var(--surface-container-high);
  border-radius: var(--radius-sm);
  padding: 8px;
  margin: 0;
}
```

- [ ] **Step 3: Verify the build**

Run: `cd smriti-observatory/frontend && npm run build`
Expected: builds cleanly.

- [ ] **Step 4: Commit**

```bash
git add smriti-observatory/frontend/src/components/EventTimeline.tsx smriti-observatory/frontend/src/components/EventTimeline.module.css \
        smriti-observatory/frontend/src/lib/traceLinks.ts
git commit -m "feat: add EventTimeline with Timeline/Trace toggle"
```

---

### Task 21: `SessionView.tsx` + `App.tsx` wiring

**Files:**
- Create: `smriti-observatory/frontend/src/features/session/SessionView.tsx`
- Modify: `smriti-observatory/frontend/src/App.tsx`
- Create: `smriti-observatory/frontend/.env.example`

**Interfaces:**
- Produces: the fully wired app — this is where every prior component and `lib/ws.ts` come together.

- [ ] **Step 1: Implement `SessionView`**

```tsx
// smriti-observatory/frontend/src/features/session/SessionView.tsx
import { useEffect, useState } from "react";
import { DiffView } from "../../components/DiffView";
import { EventTimeline } from "../../components/EventTimeline";
import { SessionDrawer, type SessionSummary } from "../../components/SessionDrawer";
import { SidePanel } from "../../components/SidePanel";
import { TierPanel } from "../../components/TierPanel";
import { adkWebUrl } from "../../lib/traceLinks";
import type { EnrichedEvent, SessionState } from "../../lib/types";
import { connectSessionSocket } from "../../lib/ws";

const BACKEND_URL = import.meta.env.VITE_OBSERVATORY_BACKEND_URL ?? "http://localhost:8100";
const TUTOR_BASE_URL = import.meta.env.VITE_TUTOR_BASE_URL ?? "http://localhost:8000";
const GCP_PROJECT = import.meta.env.VITE_GCP_PROJECT ?? "nityam-506707";

export function SessionView() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [state, setState] = useState<SessionState | null>(null);
  const [events, setEvents] = useState<EnrichedEvent[]>([]);

  useEffect(() => {
    fetch(`${BACKEND_URL}/api/sessions`)
      .then((r) => r.json())
      .then((body) => setSessions(body.sessions ?? []));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setEvents([]);
    const studentId = sessions.find((s) => s.session_id === selectedId)?.student_id ?? "demo_student";
    fetch(`${BACKEND_URL}/api/sessions/${selectedId}/state?student_id=${studentId}`)
      .then((r) => r.json())
      .then(setState);
    fetch(`${BACKEND_URL}/api/sessions/${selectedId}/events`)
      .then((r) => r.json())
      .then((body) => setEvents((body.events ?? []).map((event: EnrichedEvent["event"]) => ({ event, diff: [] }))));

    return connectSessionSocket(BACKEND_URL.replace("http", "ws"), selectedId, (enriched) => {
      setEvents((prev) => [...prev, enriched]);
    });
  }, [selectedId, sessions]);

  const workflowEvents = events.filter((e) => e.event.tier === "workflow");
  const episodicEvents = events.filter((e) => e.event.tier === "episodic");
  const longTermEvents = events.filter((e) => e.event.tier === "long_term" && e.event.operation === "write");
  const latestDiff = longTermEvents.at(-1)?.diff ?? [];

  return (
    <div style={{ display: "flex", height: "100vh" }}>
      <SessionDrawer sessions={sessions} selectedId={selectedId} onSelect={setSelectedId} />
      <main style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {selectedId && (
          <>
            <header style={{ padding: 12, display: "flex", gap: 12, alignItems: "center" }}>
              <strong>{selectedId}</strong>
              <a href={adkWebUrl(TUTOR_BASE_URL)} target="_blank" rel="noreferrer">
                Open in ADK web
              </a>
            </header>
            <div style={{ flex: 1, overflow: "hidden" }}>
              <EventTimeline events={events} gcpProject={GCP_PROJECT} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, padding: 8 }}>
              <TierPanel
                tier="workflow"
                title="Workflow"
                events={workflowEvents}
                content={<pre>{JSON.stringify(state?.workflow.turn_buffer ?? [], null, 2)}</pre>}
              />
              <TierPanel
                tier="episodic"
                title="Episodic"
                events={episodicEvents}
                content={<pre>{JSON.stringify(state?.episodic.session_log, null, 2)}</pre>}
              />
              <TierPanel tier="long_term" title="Long-term" events={longTermEvents} content={<DiffView changes={latestDiff} />} />
            </div>
          </>
        )}
      </main>
      <SidePanel
        tabs={[
          { id: "workflow", label: "Workflow", content: <pre>{JSON.stringify(state?.workflow, null, 2)}</pre> },
          { id: "episodic", label: "Episodic", content: <pre>{JSON.stringify(state?.episodic, null, 2)}</pre> },
          { id: "long_term", label: "Long-term", content: <pre>{JSON.stringify(state?.long_term, null, 2)}</pre> },
          { id: "diff", label: "Diff", content: <DiffView changes={latestDiff} /> },
          { id: "sessions", label: "Sessions", content: <SessionDrawer sessions={sessions} selectedId={selectedId} onSelect={setSelectedId} /> },
        ]}
      />
    </div>
  );
}
```

- [ ] **Step 2: Wire `App.tsx`**

```tsx
// smriti-observatory/frontend/src/App.tsx
import { SessionView } from "./features/session/SessionView";

export default function App() {
  return <SessionView />;
}
```

```bash
# smriti-observatory/frontend/.env.example
VITE_OBSERVATORY_BACKEND_URL=http://localhost:8100
VITE_TUTOR_BASE_URL=http://localhost:8000
VITE_GCP_PROJECT=nityam-506707
```

- [ ] **Step 3: Verify the build**

Run: `cd smriti-observatory/frontend && npm run build`
Expected: builds cleanly, no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add smriti-observatory/frontend/src/features/session/SessionView.tsx smriti-observatory/frontend/src/App.tsx smriti-observatory/frontend/.env.example
git commit -m "feat: wire SessionView into App — full frontend data flow"
```

---

### Task 22: Headless-browser smoke test

**Files:**
- Create: `smriti-observatory/frontend/tests/ui.mjs`

**Interfaces:**
- Consumes: nothing new — drives the built app exactly as `frontend/tests/ui.mjs` drives the product frontend.

- [ ] **Step 1: Write the test** (adapted from `sub_modules_examples/tutor`'s sibling `frontend/tests/ui.mjs` pattern — same headless-Chrome-over-CDP approach, no Puppeteer/Playwright)

```javascript
// smriti-observatory/frontend/tests/ui.mjs
/* Drives the built Observatory frontend in headless Chrome over the
 * DevTools protocol — same approach as frontend/tests/ui.mjs (the product
 * app's own harness). No Puppeteer, no test runner.
 *
 *   npm run build && node tests/ui.mjs
 */
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const freePort = () =>
  new Promise((r) => {
    const s = createServer();
    s.unref();
    s.listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => r(port));
    });
  });

const APP = await freePort();
const CDP = await freePort();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const srv = spawn("npx", ["vite", "preview", "--port", String(APP), "--strictPort", "--host", "127.0.0.1"], {
  cwd: ROOT,
  stdio: "ignore",
});
const profile = mkdtempSync(resolve(tmpdir(), "smriti-obs-v-"));
const CHROME = process.env.CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const chrome = spawn(
  CHROME,
  [
    "--headless=new",
    `--remote-debugging-port=${CDP}`,
    `--user-data-dir=${profile}`,
    "--no-first-run",
    "--disable-gpu",
    "--hide-scrollbars",
    "--window-size=1440,1000",
    "about:blank",
  ],
  { stdio: "ignore" },
);
process.on("exit", () => {
  chrome.kill("SIGKILL");
  srv.kill("SIGKILL");
});

for (let i = 0; i < 200; i++) {
  try {
    if ((await fetch(`http://127.0.0.1:${APP}/`)).ok) break;
  } catch {}
  await sleep(120);
}

let url;
for (let i = 0; i < 90; i++) {
  try {
    const list = await (await fetch(`http://127.0.0.1:${CDP}/json/list`)).json();
    const page = list.find((t) => t.type === "page");
    if (page?.webSocketDebuggerUrl) {
      url = page.webSocketDebuggerUrl;
      break;
    }
  } catch {}
  await sleep(150);
}

let id = 1;
const pending = new Map();
const ws = new WebSocket(url);
await new Promise((resolvePromise, reject) => {
  ws.onopen = resolvePromise;
  ws.onerror = reject;
});
ws.onmessage = ({ data }) => {
  const parsed = JSON.parse(data);
  const waiter = pending.get(parsed.id);
  if (waiter) {
    pending.delete(parsed.id);
    parsed.error ? waiter.reject(new Error(parsed.error.message)) : waiter.resolve(parsed.result);
  }
};
const send = (method, params = {}) =>
  new Promise((resolvePromise, reject) => {
    const thisId = id++;
    pending.set(thisId, { resolve: resolvePromise, reject });
    ws.send(JSON.stringify({ id: thisId, method, params }));
  });
const evaluate = async (expression) => {
  const result = await send("Runtime.evaluate", { expression: `(()=>{${expression}})()`, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description);
  return result.result.value;
};

await send("Page.enable");
await send("Runtime.enable");
const errors = [];
ws.addEventListener("message", ({ data }) => {
  const parsed = JSON.parse(data);
  if (parsed.method === "Runtime.exceptionThrown") errors.push(parsed.params.exceptionDetails.text);
});

await send("Page.navigate", { url: `http://127.0.0.1:${APP}/` });
await sleep(1500);

const hasDrawer = await evaluate(`return document.querySelector('nav[aria-label="Sessions"]') !== null;`);
if (!hasDrawer) throw new Error("SessionDrawer did not render");

const bodyBackground = await evaluate(`return getComputedStyle(document.body).backgroundColor;`);
if (bodyBackground !== "rgb(18, 18, 18)") {
  throw new Error(`expected ADK-web dark background rgb(18, 18, 18), got ${bodyBackground}`);
}

if (errors.length > 0) {
  throw new Error(`console errors during load: ${errors.join("; ")}`);
}

console.log("ui.mjs: PASS — SessionDrawer renders, dark theme tokens applied, no console errors");
```

- [ ] **Step 2: Run to verify it currently fails / passes**

Run: `cd smriti-observatory/frontend && npm run build && node tests/ui.mjs`
Expected (given Tasks 15-21 are already implemented at this point in the plan): PASS. If this is the first time running it, it should already pass since the app was built in prior tasks — this step's real purpose is proving the harness itself works, matching how `frontend/tests/ui.mjs` operates.

- [ ] **Step 3: Commit**

```bash
git add smriti-observatory/frontend/tests/ui.mjs
git commit -m "test: add headless-Chrome smoke test for the Observatory frontend"
```

---

## Part E — End-to-end validation

### Task 23: End-to-end acceptance test

**Files:**
- Create: `smriti-observatory/backend/tests/test_end_to_end.py`

**Interfaces:**
- Consumes: everything built in Tasks 1-14 (tutor instrumentation + close wiring, Observatory backend). This is the proof the whole pipeline works together, per spec §9's acceptance criteria.

- [ ] **Step 1: Write the failing test**

```python
# smriti-observatory/backend/tests/test_end_to_end.py
"""The actual proof this system works: instrument a real conversation
against real Firestore/Redis, watch events arrive over the ingest pipeline
in order with correct trace linkage, close the session for real, and
confirm the long-term diff matches Firestore's actual post-close state.
Per docs/superpowers/specs/2026-08-27-smriti-observatory-design.md §9.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.memory import instrumentation, short_term, store
from app.memory.schemas import DPMProfile, Weakness
from app.session_close import ReflectOp, ReflectResult
from observatory.broadcaster import Broadcaster
from observatory.ingest import ingest_one_message
from observatory.snapshot_cache import SnapshotCache


@pytest.mark.asyncio
async def test_full_pipeline_turn_logging_through_close_and_diff(firestore_db, redis_client, monkeypatch):
    session_id = "test_e2e_session_1"
    student_id = "test_e2e_student_1"

    cache = SnapshotCache()
    broadcaster = Broadcaster()
    session_queue = broadcaster.subscribe(session_id)

    def get_dpm(sid):
        profile = store.get_dpm(firestore_db, sid)
        return profile.model_dump(mode="json") if profile else None

    def get_teaching_memory(sid):
        memory = store.get_teaching_memory(firestore_db, sid)
        return memory.model_dump(mode="json") if memory else None

    try:
        # 0. Seed an existing DPM so the close-triggered write below is a
        #    genuine "partial -> known" transition, not a brand-new-student
        #    "added" entry — the more representative, demo-worthy case.
        #    Done before clearing the event list so the seed's own publish
        #    isn't mistaken for something close_session produced.
        store.put_dpm(firestore_db, DPMProfile(
            student_id=student_id,
            weaknesses={"projectile.range": Weakness(mastery="partial", strength="weak", evidence=[f"{session_id}#0"])},
        ))
        redis_client.delete("smriti:events:recent")

        # 1. Drive two turns through the real tools/short_term path.
        ctx = MagicMock()
        ctx.state = {}
        ctx.session.id = session_id
        from app.memory import tools
        monkeypatch.setattr(tools, "_conn", lambda: firestore_db)
        await tools.log_turn("why 45 degrees?", "student", "", "", ctx)
        await tools.log_turn("range formula", "tutor", "projectile.range", "", ctx)

        # 2. Ingest whatever landed on the Redis list (simulates the ingest
        #    loop consuming what was published, without needing a live
        #    subscribe-forever task in this test).
        for raw in redis_client.lrange("smriti:events:recent", 0, -1):
            await ingest_one_message(raw, cache, broadcaster, get_dpm, get_teaching_memory)

        delivered = []
        while not session_queue.empty():
            delivered.append(session_queue.get_nowait())
        turn_events = [d for d in delivered if d.event.record_type == "turn_buffer" and d.event.operation == "write"]
        assert len(turn_events) == 2

        # 3. Close the session for real (reflect() stubbed — no live API call).
        import app.session_close as session_close
        monkeypatch.setattr(session_close, "reflect", lambda client, log: ReflectResult(
            summary="", operations=[ReflectOp(op="set_mastery", args={
                "concept_id": "projectile.range", "mastery": "known",
                "strength": "strong", "evidence": [f"{session_id}#2"],
            })],
        ))
        from app.app_utils import memory_routes
        monkeypatch.setattr(memory_routes, "_genai_client", lambda: None)
        monkeypatch.setattr(memory_routes, "_firestore_client", lambda: firestore_db)

        redis_client.delete("smriti:events:recent")
        log = await memory_routes.perform_close_session(session_id, student_id)
        assert len(log.turns) == 2

        # 4. Ingest the close-triggered events and confirm the diff matches
        #    Firestore's real post-close state.
        for raw in redis_client.lrange("smriti:events:recent", 0, -1):
            await ingest_one_message(raw, cache, broadcaster, get_dpm, get_teaching_memory)

        delivered = []
        while not session_queue.empty():
            delivered.append(session_queue.get_nowait())
        dpm_writes = [d for d in delivered if d.event.record_type == "dpm_profile" and d.event.operation == "write"]
        assert len(dpm_writes) == 1
        assert dpm_writes[0].event.session_id == session_id  # Task 4's context-var scoping proven live
        mastery_change = next(c for c in dpm_writes[0].diff if c.path == "weaknesses.projectile.range.mastery")
        assert mastery_change.label == "projectile.range.mastery: partial -> known"

        real_profile = store.get_dpm(firestore_db, student_id)
        assert real_profile.weaknesses["projectile.range"].mastery == "known"
    finally:
        instrumentation.set_session_context(None)
        firestore_db.collection("session_logs").document(session_id).delete()
        firestore_db.collection("dpm_profiles").document(student_id).delete()
        firestore_db.collection("teaching_memories").document(student_id).delete()
        redis_client.delete(
            f"session:{session_id}:turns", f"session:{session_id}:started_at", f"session:{session_id}:heartbeat",
        )
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_end_to_end.py -v`
Expected: FAIL if any prior task's wiring has a gap (this is the integration test that catches cross-task interface mismatches — if it fails, the bug is almost certainly in how two earlier tasks connect, not in this test itself).

- [ ] **Step 3: Fix any integration gaps found**

There is no new production code to write for this task — if Step 2 fails, the fix is in whichever Task 1-14 file the failure points to. Re-run Step 2 after each fix.

- [ ] **Step 4: Run to verify it passes**

Run: `cd smriti-observatory/backend && uv run pytest tests/test_end_to_end.py -v`
Expected: 1 passed.

- [ ] **Step 5: Run the full test suite one last time**

Run:
```bash
cd sub_modules_examples/tutor && uv run pytest tests/ -v
cd ../../smriti-observatory/backend && uv run pytest tests/ -v
cd ../frontend && npm run build && node tests/ui.mjs
```
Expected: everything green. Paste the actual pass/fail counts — per this repo's standing rule, evidence before assertions.

- [ ] **Step 6: Update the top-level README and commit**

Expand `smriti-observatory/README.md` (from Task 14) with a "What you'll see" section describing the three tier panels, the Timeline/Trace toggle, and the "Open in ADK web" link — written after actually running the system end to end, not before.

```bash
git add smriti-observatory/backend/tests/test_end_to_end.py smriti-observatory/README.md
git commit -m "test: add end-to-end acceptance test proving the full pipeline"
```

---

## Final self-review notes (for whoever executes this plan)

- **Spec coverage:** §5 (instrumentation) → Tasks 1-4; §6 (close_session wiring) → Tasks 5-7; §7 (backend) → Tasks 8-14; §8 (frontend) → Tasks 15-22; §9 (testing) → Task 23 plus per-task tests throughout.
- **Open item to watch during execution:** spec §10.1 — the "Open in ADK web" link (Task 21) links to the dev-ui root, not a session-scoped URL, because no such query param was confirmed. If one is discovered while running the real system in Task 23, update `trace_links.py`/`traceLinks.ts` accordingly — that's a small, expected refinement, not a plan gap.
- **Do not skip Task 8's Step 4** (`uv sync` resolving the path dependency on the tutor package) — every backend task from 9 onward assumes `app.memory.*` imports resolve correctly.
